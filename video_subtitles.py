"""Optional soft subtitle packaging; no speech recognition or burned-in OCR.

Manual tracks: up to 24. Automatic: original/source plus English and Chinese,
up to 8 (translated languages outside that set are deliberately excluded).
Bilibili advanced/script danmaku is ignored; XML is bounded before parsing.
"""
from __future__ import annotations

import copy
import math
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

import yt_dlp

from download_errors import DownloadCancelled

MAX_XML_BYTES = 16 * 1024 * 1024
MAX_COMMENTS = 20000


def select_tracks(info: dict, options: dict) -> list[tuple[str, dict, str]]:
    tracks = []
    counts = {'manual': 0, 'automatic': 0, 'danmaku': 0}
    limits = {'manual': 24, 'automatic': 8, 'danmaku': 1}
    supported = ('ass', 'srt', 'vtt', 'ttml')
    for source in ('subtitles', 'automatic_captions'):
        for language, formats in (info.get(source) or {}).items():
            kind = ('danmaku' if language == 'danmaku' else
                    'automatic' if source == 'automatic_captions' or language.startswith('ai-') else 'manual')
            enabled = options.get({'manual': 'subtitles', 'automatic': 'automatic', 'danmaku': 'danmaku'}[kind])
            if not enabled or counts[kind] >= limits[kind]:
                continue
            if source == 'automatic_captions':
                base = language.split('-')[0]
                if not (language.endswith('-orig') or base in {'en', 'zh', (info.get('language') or '').split('-')[0]}):
                    continue
            preferences = ('xml',) if kind == 'danmaku' else supported
            selected = next((f for ext in preferences for f in formats if f.get('ext') == ext), None)
            if selected is not None:
                tracks.append((language, copy.deepcopy(selected), kind))
                counts[kind] += 1
    # Prefer dialogue over danmaku for the player's default track.
    return sorted(tracks, key=lambda item: item[2] == 'danmaku')


def _timestamp(seconds):
    centiseconds = int(seconds * 100)
    return f'{centiseconds // 360000}:{centiseconds // 6000 % 60:02}:{centiseconds // 100 % 60:02}.{centiseconds % 100:02}'


def danmaku_ass(xml: str) -> str:
    if len(xml.encode('utf-8')) > MAX_XML_BYTES or re.search(r'<!\s*(?:DOCTYPE|ENTITY)', xml, re.I):
        raise ValueError('Unsafe or oversized danmaku XML')
    root = ET.fromstring(xml)
    lines = ['[Script Info]', 'ScriptType: v4.00+', 'PlayResX: 1920', 'PlayResY: 1080', 'WrapStyle: 2', '', '[V4+ Styles]', 'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding', 'Style: Default,Arial,42,&H00FFFFFF,&H00FFFFFF,&H00111111,&H00000000,0,0,0,0,100,100,0,0,1,2,0,7,20,20,20,1', '', '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    lane = 0
    for node in list(root)[:MAX_COMMENTS]:
        if node.tag != 'd':
            continue
        try:
            fields = node.attrib['p'].split(',')
            start, mode, color = float(fields[0]), int(fields[1]), int(fields[3])
            if not math.isfinite(start) or not 0 <= start <= 604800 or mode not in (1, 2, 3, 4, 5, 6):
                continue
        except (KeyError, ValueError, IndexError):
            continue
        text = ''.join(node.itertext())[:300].translate(str.maketrans({'\\':'＼','{':'｛','}':'｝','\n':' ','\r':' '}))
        text = ''.join(c for c in text if ord(c) >= 32)
        if not text:
            continue
        y = 40 + (lane % 18) * 54
        lane += 1
        if mode == 5:
            position = r'\an8\pos(960,40)'
        elif mode == 4:
            position = r'\an2\pos(960,1040)'
        else:
            width = max(100, len(text) * 44)
            a, b = (-width, 1920) if mode == 6 else (1920, -width)
            position = f'\\move({a},{y},{b},{y})'
        color &= 0xFFFFFF
        bgr = ((color & 255) << 16) | (color & 0xFF00) | (color >> 16)
        lines.append(f'Dialogue: 0,{_timestamp(start)},{_timestamp(start + (5 if mode in (4,5) else 8))},Default,,0,0,0,,{{{position}\\c&H{bgr:06X}&}}{text}')
    return '\n'.join(lines) + '\n'


def mux_tracks(source: Path, target: Path, tracks, cancel_token=None):
    command = [shutil.which('ffmpeg') or 'ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(source)]
    for path, _, _ in tracks:
        command += ['-i', str(path)]
    command += ['-map', '0:v?', '-map', '0:a?', '-map', '0:s?', '-map', '0:t?']
    for i in range(len(tracks)):
        command += ['-map', f'{i+1}:s:0']
    probe = subprocess.run([shutil.which('ffprobe') or 'ffprobe', '-v', 'error', '-select_streams', 's', '-show_entries', 'stream=index,codec_name:stream_disposition=default', '-of', 'json', str(source)], capture_output=True, check=True, timeout=30)
    streams = json.loads(probe.stdout).get('streams', [])
    existing = len(streams)
    command += ['-c', 'copy']
    # MP4 mov_text cannot be copied into Matroska. Convert existing text tracks;
    # preserve bitmap tracks and stream metadata/dispositions.
    for i, stream in enumerate(streams):
        if stream.get('codec_name') in {'mov_text', 'webvtt', 'subrip', 'text', 'ttml'}:
            command += [f'-c:s:{i}', 'ass']

    for i, (_, language, kind) in enumerate(tracks):
        index = existing + i
        command += [f'-c:s:{index}', 'ass', f'-metadata:s:s:{index}', f'title={kind}:{language}', f'-metadata:s:s:{index}', f'language={language}']
    if tracks and not existing:
        command += ['-disposition:s:0', 'default']
    command += [str(target)]
    # A file-backed stderr prevents pipe deadlocks; cancellation kills FFmpeg.
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors)
        try:
            deadline = time.monotonic() + 3600
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError("Subtitle remux timed out")
                if cancel_token:
                    cancel_token.raise_if_cancelled()
                try:
                    code = process.wait(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
            if code:
                errors.seek(0)
                raise RuntimeError(errors.read(2048).decode('utf-8', 'replace'))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    return target


def package_subtitles(info, source: Path, options: dict, ydl_options: dict, cancel_token=None, url=None):
    """Fetch optional tracks privately; retain the downloaded video on failure."""
    warnings, tracks = [], []
    subtitle_info = info
    # Bilibili's extractor omits its entire subtitle list unless explicitly asked.
    # Probe separately so subtitle API failures cannot abort the video download.
    if url and (not info.get('subtitles') or (options.get('automatic') and not info.get('automatic_captions'))):
        if cancel_token:
            cancel_token.raise_if_cancelled()
        try:
            probe_opts = {key: ydl_options[key] for key in ('cookiefile', 'http_headers', 'logger', 'js_runtimes', 'remote_components') if key in ydl_options}
            probe_opts.update(quiet=True, no_warnings=True, skip_download=True, listsubtitles=True, noplaylist=True, socket_timeout=15, retries=1, extractor_retries=1)
            with yt_dlp.YoutubeDL(probe_opts) as ydl:
                from media_sources import detect_platform, BILIBILI
                if detect_platform(url) == BILIBILI:
                    from bilibili_acceleration import register_bilibili_extractor
                    register_bilibili_extractor(ydl)
                fetched = ydl.extract_info(url, download=False)
            if fetched:
                subtitle_info = dict(info, **{key: fetched[key] for key in ('subtitles', 'automatic_captions', 'language') if key in fetched})
        except DownloadCancelled:
            raise
        except Exception:
            warnings.append('subtitle_metadata:unavailable')
    chosen = select_tracks(subtitle_info, options)
    with tempfile.TemporaryDirectory(prefix='subtitles-', dir=source.parent) as directory:
        work = Path(directory)
        for i, (language, subtitle, kind) in enumerate(chosen):
            if cancel_token:
                cancel_token.raise_if_cancelled()
            try:
                opts = {key: ydl_options[key] for key in ('cookiefile', 'http_headers', 'logger', 'socket_timeout') if key in ydl_options}
                if cancel_token:
                    opts['progress_hooks'] = [lambda _: cancel_token.raise_if_cancelled()]
                opts.update({'quiet': True, 'no_warnings': True, 'skip_download': True, 'writesubtitles': True, 'writeautomaticsub': True, 'outtmpl': str(work / f'{i}.%(ext)s'), 'external_downloader': {'default': 'native'}, 'retries': 1, 'max_filesize': MAX_XML_BYTES})
                data = copy.deepcopy(subtitle_info)
                data.update({'requested_subtitles': {'track': subtitle}, 'ext': 'mp4', '__files_to_move': {}})
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.process_info(data)
                path = Path(subtitle['filepath'])
                if not path.is_file() or path.stat().st_size > MAX_XML_BYTES:
                    raise ValueError('Missing or oversized subtitle')
                if kind == 'danmaku':
                    converted = path.with_suffix('.ass')
                    ass = danmaku_ass(path.read_text(encoding='utf-8-sig'))
                    if 'Dialogue:' not in ass:
                        raise ValueError('No supported danmaku events')
                    converted.write_text(ass, encoding='utf-8')
                    path = converted
                tracks.append((path, language, kind))
            except DownloadCancelled:
                raise
            except Exception:
                warnings.append(f'{kind}:{language}:unavailable')
        for kind, key in [('manual','subtitles'), ('automatic','automatic'), ('danmaku','danmaku')]:
            if options.get(key) and not any(x[2] == kind for x in chosen):
                warnings.append(f'{kind}:unavailable')
        target = source.with_name(source.stem + '.subtitled.mkv')
        try:
            mux_tracks(source, target, tracks, cancel_token)
        except DownloadCancelled:
            target.unlink(missing_ok=True)
            raise
        except Exception:
            target.unlink(missing_ok=True)
            warnings.append('subtitle_embedding:failed')
            # A broken subtitle should not discard an otherwise usable video.
            tracks = []
            try:
                mux_tracks(source, target, [], cancel_token)
            except DownloadCancelled:
                raise
            except Exception:
                target.unlink(missing_ok=True)
                target = source
                warnings.append('mkv_remux:failed')
        if target != source:
            final = source.with_suffix('.mkv')
            target.replace(final)
            if source != final:
                source.unlink()
            target = final
    try:
        probe = subprocess.run([shutil.which('ffprobe') or 'ffprobe', '-v', 'error', '-select_streams', 's', '-show_entries', 'stream=index', '-of', 'json', str(target)], capture_output=True, check=True, timeout=30)
        embedded_count = len(json.loads(probe.stdout).get('streams', []))
    except Exception:
        embedded_count = len(tracks)
    info['_subtitle_status'] = 'partial' if embedded_count and warnings else ('embedded' if embedded_count else 'unavailable')
    info['_subtitle_tracks'] = embedded_count
    info['_subtitle_warnings'] = warnings
    return target
