"""yt-dlp option construction, independent of download I/O coordination.

The compatibility adapter supplies its current helper functions explicitly so
callers can continue patching downloader-level hooks and discovery helpers.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import media_sources
from audio_output import AUDIO_FORMATS, FLAC, MP3, SOURCE, WAV
from bilibili_acceleration import BILIBILI_HTTP_CHUNK_SIZE, SPEED_MODES, STANDARD, TURBO
from download_progress import YtdlpProgressCallback
from task_control import CancellationToken

YOUTUBE = media_sources.YOUTUBE
INSTAGRAM = media_sources.INSTAGRAM
BILIBILI = media_sources.BILIBILI
VIDEO = "video"
AUDIO = "audio"
MEDIA_TYPES = {VIDEO, AUDIO}


@dataclass(frozen=True)
class DownloadPreferences:
    """Media, output-format and transfer choices shared by option builders."""

    media_type: str = VIDEO
    audio_format: str = MP3
    speed_mode: str = STANDARD


@dataclass(frozen=True)
class OptionsHooks:
    """Current compatibility helpers supplied by the download orchestrator."""

    validate_output_version: Callable
    output_template: Callable
    attempt_output_template: Callable
    make_progress_hook: Callable
    logger_factory: Callable
    node_path: Callable
    platform_http_headers: Callable
    audio_output_profile: Callable
    audio_postprocessors: Callable
    find_cookie_file: Callable
    configure_aria2: Callable
    make_cancel_hook: Callable
    make_postprocessor_status_hook: Callable


def build_ydl_options(
    platform: str,
    output_dir: Path,
    index: int,
    total: int,
    *,
    preferences: DownloadPreferences,
    hooks: OptionsHooks,
    progress_callback: YtdlpProgressCallback = None,
    aria2_executable: str | None = None,
    selected_audio: dict | None = None,
    cancel_token: CancellationToken | None = None,
    output_version: int = 1,
    attempt_workspace: Path | None = None,
) -> dict:
    """Build fresh options while preserving helper call and hook order."""
    media_type = preferences.media_type
    audio_format = preferences.audio_format
    speed_mode = preferences.speed_mode
    if not isinstance(media_type, str) or media_type not in MEDIA_TYPES:
        raise ValueError(f"不支持的下载类型: {media_type}")
    if not isinstance(audio_format, str) or audio_format not in AUDIO_FORMATS:
        raise ValueError(f"不支持的音频格式: {audio_format}")
    if not isinstance(speed_mode, str) or speed_mode not in SPEED_MODES:
        raise ValueError(f"不支持的速度模式: {speed_mode}")
    hooks.validate_output_version(output_version)

    output_template = (
        hooks.attempt_output_template(platform, output_dir, attempt_workspace)
        if attempt_workspace is not None
        else hooks.output_template(platform, output_dir, output_version)
    )
    options = {
        "proxy": "",
        "outtmpl": output_template,
        "progress_hooks": [
            hooks.make_progress_hook(
                index,
                total,
                progress_callback,
                cancel_token,
                media_type,
                audio_format,
            )
        ],
        "writesubtitles": False,
        "writeautomaticsub": False,
        "embedmetadata": True,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "logger": hooks.logger_factory(),
        "retries": 10,
        "fragment_retries": 10,
        "extractor_retries": 5,
        "socket_timeout": 30,
        "overwrites": False,
    }
    if attempt_workspace is not None:
        options["paths"] = {"temp": str(attempt_workspace)}

    if platform == YOUTUBE:
        options.update(media_sources.youtube_js_options(hooks.node_path()))
    elif platform == INSTAGRAM:
        options.update(
            {
                "http_headers": hooks.platform_http_headers(INSTAGRAM),
                "sleep_interval": 1,
                "max_sleep_interval": 3,
                "sleep_interval_requests": 1,
            }
        )
    elif platform == BILIBILI:
        options.update(
            {
                "http_chunk_size": BILIBILI_HTTP_CHUNK_SIZE,
            }
        )

    if media_type == AUDIO:
        profile_info = selected_audio
        if profile_info is None and audio_format == FLAC:
            # 元数据预检前尚不知道源编码；先保留用户请求的 FLAC
            # 后处理配置，拿到真实格式后再决定是否回退到 MP3。
            profile_info = {"acodec": "flac", "ext": "flac"}
        audio_profile = hooks.audio_output_profile(
            profile_info or {},
            audio_format,
        )
        postprocessors = hooks.audio_postprocessors(audio_profile)
        options.update(
            {
                "format": (
                    "bestaudio[acodec^=flac]/bestaudio/best"
                    if audio_format == FLAC
                    else (
                        "bestaudio[acodec!=none]/best[acodec!=none]"
                        if audio_format in {SOURCE, WAV}
                        else "bestaudio/best"
                    )
                ),
                "writethumbnail": audio_profile.cover_embedded,
                "postprocessors": postprocessors,
            }
        )
    elif platform in {YOUTUBE, BILIBILI}:
        # 优先下载可用的最高质量视频流和音频流。
        options.update(
            {
                "format": "bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
                "writethumbnail": True,
            }
        )
    else:
        # Instagram 优先选择 MP4/M4A，并统一将最终容器封装为 MP4。
        options.update(
            {
                "format": (
                    "bestvideo[ext=mp4]+bestaudio[ext=m4a]"
                    "/bestvideo[ext=mp4]+bestaudio"
                    "/bestvideo+bestaudio[ext=m4a]"
                    "/best[ext=mp4]"
                    "/best"
                ),
                "merge_output_format": "mp4",
                "writethumbnail": True,
                "postprocessors": [
                    {
                        "key": "FFmpegVideoRemuxer",
                        "preferedformat": "mp4",
                    },
                ],
            }
        )

    cookie_file = hooks.find_cookie_file(platform)
    if cookie_file:
        options["cookiefile"] = str(cookie_file)

    if platform == BILIBILI and speed_mode == TURBO and aria2_executable:
        hooks.configure_aria2(options, aria2_executable)

    postprocessor_hooks = []
    if cancel_token:
        postprocessor_hooks.append(hooks.make_cancel_hook(cancel_token))
    postprocessor_hooks.append(
        hooks.make_postprocessor_status_hook(
            index,
            total,
            progress_callback,
            media_type,
            audio_format,
        )
    )
    options["postprocessor_hooks"] = postprocessor_hooks

    return options
