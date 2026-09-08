"""Local uploads and cancellable FFmpeg extraction for the shared task queue."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid

from audio_output import MP3, SOURCE
from download_errors import DownloadErrorInfo, DownloadFailure
from output_files import prepared_output_dir, claim_final_output_with_version

MAX_FILE_BYTES = 2 * 1024**3
INPUT_TTL = 24 * 3600
# Exclude playlists, concat and image-sequence demuxers that can reference other inputs.
INPUT_FORMATS = 'mov,matroska,webm,avi,mpegts,mpeg,flv,asf,ogg'


def failure(code, message, suggestion='请检查文件后重新上传', retryable=False):
    return DownloadFailure(DownloadErrorInfo(code, message, suggestion, retryable))


class UploadStore:
    def __init__(self, root, max_file_bytes=MAX_FILE_BYTES, max_total_bytes=8 * 1024**3):
        self.root = Path(root)
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes
        self.lock = threading.RLock()

    def resolve(self, key):
        if not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{32}', key):
            raise failure('INPUT_EXPIRED', '源视频不存在或已过期')
        path = self.root / (key + '.bin')
        meta = self.root / (key + '.json')
        try:
            if path.is_symlink() or meta.is_symlink() or not path.is_file():
                raise OSError('Missing input')
            name = json.loads(meta.read_text())['name']
            if not isinstance(name, str):
                raise ValueError('Invalid name')
            return path, name
        except (OSError, ValueError, KeyError):
            raise failure('INPUT_EXPIRED', '源视频不存在或已过期') from None

    def remove(self, key):
        if re.fullmatch(r'[a-f0-9]{32}', key):
            for suffix in ('.bin', '.json', '.part'):
                (self.root / (key + suffix)).unlink(missing_ok=True)

    def cleanup(self, active=(), now=None):
        with self.lock:
            now = time.time() if now is None else now
            for path in self.root.glob('*'):
                if (re.fullmatch(r'[a-f0-9]{32}\.(bin|json|part)', path.name)
                        and path.stem not in active and not path.is_symlink() and path.exists()
                        and now - path.stat().st_mtime > INPUT_TTL):
                    self.remove(path.stem)

    def save(self, upload):
        with self.lock:
            self.root.mkdir(parents=True, exist_ok=True)
            if not upload or not upload.filename:
                raise failure('INVALID_UPLOAD', '请选择一个视频文件')
            name = upload.filename.replace('\\', '/').split('/')[-1]
            name = ''.join(c for c in name if ord(c) >= 32)[:200] or 'video'
            key = uuid.uuid4().hex
            retained = [p for p in self.root.glob('*') if p.suffix in {'.bin', '.part'} and not p.is_symlink()]
            used = sum(p.stat().st_size for p in retained)
            if len(retained) >= 256:
                raise failure('UPLOAD_STORAGE_FULL', '临时视频数量已达上限', '请等待过期视频自动清理后再试')
            size = 0
            try:
                with (self.root / (key + '.part')).open('xb') as target:
                    while chunk := upload.stream.read(1024 * 1024):
                        size += len(chunk)
                        if size > self.max_file_bytes:
                            raise failure('UPLOAD_TOO_LARGE', '视频文件不能超过 2 GiB')
                        if used + size > self.max_total_bytes:
                            raise failure('UPLOAD_STORAGE_FULL', '临时视频存储空间已满', '请等待过期视频自动清理后再试')
                        target.write(chunk)
                if size == 0:
                    raise failure('INVALID_UPLOAD', '视频文件为空')
                (self.root / (key + '.json')).write_text(json.dumps({'name': name}, ensure_ascii=False))
                (self.root / (key + '.part')).rename(self.root / (key + '.bin'))
                return key
            except BaseException:
                self.remove(key)
                raise


def run_process(command, token, progress=None, timeout=21600):
    """Drain both pipes with bounded buffers; terminate promptly on cancellation."""
    token.raise_if_cancelled()
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    buffers = [bytearray(), bytearray()]
    def drain(pipe, index):
        pending = b''
        while chunk := pipe.read1(4096):
            buffers[index].extend(chunk)
            del buffers[index][:-1024 * 1024]
            if index == 0 and progress:
                pending += chunk
                lines = pending.split(b'\n')
                pending = lines.pop()[-4096:]
                for line in lines:
                    if line.startswith(b'out_time_us='):
                        try:
                            progress(int(line.split(b'=', 1)[1]) / 1_000_000)
                        except (ValueError, TypeError):
                            pass
    threads = [threading.Thread(target=drain, args=(pipe, i), daemon=True)
               for i, pipe in enumerate((process.stdout, process.stderr))]
    for thread in threads:
        thread.start()
    started = time.monotonic()
    try:
        while process.poll() is None:
            token.raise_if_cancelled()
            if time.monotonic() - started > timeout:
                raise failure('EXTRACTION_FAILED', '音频处理超时', retryable=True)
            time.sleep(.05)
        token.raise_if_cancelled()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
        for thread in threads:
            thread.join()
        process.stdout.close(); process.stderr.close()
    if process.returncode:
        raise failure('EXTRACTION_FAILED', '无法处理该视频或音轨', '请确认视频完整且格式受支持')
    return bytes(buffers[0])


def extract_audio(key, *, store, audio_format, output_dir, cancel_token,
                  progress_callback=None, output_version=1, **_kwargs):
    if audio_format not in {SOURCE, MP3}:
        raise failure('INVALID_UPLOAD', '不支持的音频格式')
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise failure('FFMPEG_MISSING', '未找到 FFmpeg 或 ffprobe', '请安装 FFmpeg 后重试', True)
    path, name = store.resolve(key)
    input_options = ['-protocol_whitelist', 'file,pipe', '-format_whitelist', INPUT_FORMATS]
    try:
        raw = run_process(['ffprobe', '-v', 'error', *input_options, '-show_entries',
                           'stream=index,codec_name,codec_type:stream_disposition=default,attached_pic:format=duration',
                           '-of', 'json', str(path)], cancel_token, timeout=30)
        info = json.loads(raw)
    except (ValueError, KeyError):
        raise failure('INVALID_MEDIA', '无法识别视频文件') from None
    streams = info.get('streams', [])
    if not any(s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic') for s in streams):
        raise failure('INVALID_MEDIA', '输入文件不包含视频画面')
    audio = [s for s in streams if s.get('codec_type') == 'audio']
    if not audio:
        raise failure('NO_AUDIO', '该视频没有音轨')
    stream = next((s for s in audio if s.get('disposition', {}).get('default')), audio[0])
    codec = stream.get('codec_name', '')
    ext = 'mp3' if audio_format == MP3 else {
        'aac': 'm4a', 'alac': 'm4a', 'mp3': 'mp3', 'opus': 'opus',
        'vorbis': 'ogg', 'flac': 'flac', 'ac3': 'ac3', 'eac3': 'eac3',
    }.get(codec, 'mka')
    directory = prepared_output_dir(output_dir)
    private = directory / ('.extract-' + uuid.uuid4().hex + '.' + ext)
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', Path(name).stem).strip('. ')[:120] or 'audio'
    # A stable upload id prevents unrelated same-named inputs from sharing versions.
    stem += f' [local-{key[:12]}]'
    try:
        duration = float(info.get('format', {}).get('duration', 0))
    except (TypeError, ValueError):
        duration = 0
    def progress(seconds):
        if progress_callback:
            progress_callback('progress', {'percent_text': f'{min(99, max(0, seconds / duration * 100)):.1f}%' if duration > 0 else '', 'stage_text': '正在提取音频'})
    try:
        if progress_callback:
            progress_callback('postprocessing', {'stage_text': '正在提取音频'})
        run_process(['ffmpeg', '-hide_banner', '-v', 'error', '-nostdin', *input_options,
                     '-i', str(path), '-map', f'0:{stream["index"]}', '-vn', '-sn', '-dn',
                     '-map_metadata', '-1', '-map_chapters', '-1',
                     *(['-c:a', 'libmp3lame', '-q:a', '0'] if audio_format == MP3 else ['-c:a', 'copy']),
                     '-progress', 'pipe:1', '-nostats', '-n', str(private)], cancel_token, progress)
        cancel_token.raise_if_cancelled()
        final, version = claim_final_output_with_version(private, stem, output_version)
    finally:
        private.unlink(missing_ok=True)
    return {'title': name, 'filepath': str(final), 'format': ext.upper(),
            'acodec': 'mp3' if audio_format == MP3 else codec, 'source_acodec': codec,
            'audio_format_used': audio_format, 'filesize': f'{final.stat().st_size / 1024**2:.2f} MB',
            'output_version_actual': version, 'audio_stream_index': stream['index'],
            'local_extraction': True}
