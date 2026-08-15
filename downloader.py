#!/usr/bin/env python3
"""
YouTube & Instagram 视频下载核心逻辑。

本模块提供链接识别、下载参数构建、yt-dlp 调用等通用功能。
main.py（命令行）和 app.py（Web 服务）均通过导入本模块复用下载能力。
"""

import copy
import logging
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

import yt_dlp

import audio_output
import download_progress
from audio_output import (
    AudioOutputProfile,
    audio_format_name as _audio_format_name,
    audio_postprocessors as _audio_postprocessors,
    audio_quality_label as _audio_quality_label,
    display_audio_codec as _display_audio_codec,
    profile_for_output_path as _profile_for_output_path,
    selected_audio_info as _selected_audio_info,
)
from download_progress import (
    ANSI_ESCAPE_RE,
    format_download_speed as _format_download_speed,
    format_eta as _format_eta,
    format_size_bytes as _format_size_bytes,
    postprocessing_preparation as _postprocessing_preparation,
    postprocessor_stage as _postprocessor_stage,
    progress_total_size as _progress_total_size,
    strip_ansi as _strip_ansi,
)
import media_sources
import output_files
from download_errors import (
    DownloadCancelled,
    DownloadFailure,
    classify_download_error,
    format_cli_error,
    public_error,
)
from download_logging import get_download_logger, log_download_event
from media_cover import CoverOutcome, ensure_media_cover as _ensure_media_cover
from task_control import CancellationToken

from bilibili_acceleration import (
    BILIBILI_HTTP_CHUNK_SIZE,
    SPEED_MODES,
    STANDARD,
    TURBO,
    AccelerationPlan,
    apply_cdn_host,
    aria2c_path,
    build_acceleration_plan,
    candidate_hosts,
    configure_aria2,
    effective_speed_mode,
    needs_cdn_host_switch,
    primary_host,
    register_bilibili_extractor,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = PROJECT_DIR / "downloads"
logger = logging.getLogger(__name__)

YOUTUBE = media_sources.YOUTUBE
INSTAGRAM = media_sources.INSTAGRAM
BILIBILI = media_sources.BILIBILI
VIDEO = "video"
AUDIO = "audio"
MEDIA_TYPES = {VIDEO, AUDIO}
MP3 = "mp3"
FLAC = "flac"
SOURCE = "source"
WAV = "wav"
AUDIO_FORMATS = {MP3, FLAC, SOURCE, WAV}
PLATFORM_NAMES = media_sources.PLATFORM_NAMES
MAX_PARALLEL_DOWNLOADS = 3
MAX_PARALLEL_BILIBILI_DOWNLOADS = 2
SHARE_URL_RE = media_sources.SHARE_URL_RE
TRAILING_URL_PUNCTUATION = media_sources.TRAILING_URL_PUNCTUATION
ATTEMPT_OUTPUT_MARKER_RE = output_files.ATTEMPT_OUTPUT_MARKER_RE
_NODE_PATH_UNSET = object()
_node_path_cached: str | None | object = _NODE_PATH_UNSET
_node_path_lock = threading.Lock()

# 类型别名
VideoTask = media_sources.VideoTask  # (platform, normalized_url)
DownloadResult = dict[str, object]   # 单视频下载结果
ProgressCallback = Callable[[int, str, object], None] | None
YtdlpProgressCallback = Callable[[str, dict[str, object]], None] | None
# ProgressCallback(task_index, event, data)
#   event: 'started' | 'progress' | 'completed' | 'failed'
#   data:  dict — 具体字段视 event 而定


class _QuietYtdlpLogger:
    """Suppress yt-dlp's raw error text; this module prints localized errors."""

    def debug(self, message: str) -> None:
        return None

    def warning(self, message: str) -> None:
        return None

    def error(self, message: str) -> None:
        return None


def _node_path(refresh: bool = False) -> str | None:
    """Return the process-cached Node executable used for YouTube JS support."""
    global _node_path_cached
    with _node_path_lock:
        if refresh or _node_path_cached is _NODE_PATH_UNSET:
            _node_path_cached = shutil.which("node")
        return _node_path_cached


def _reset_node_path_cache() -> None:
    """Clear Node discovery for tests and explicit service reconfiguration."""
    global _node_path_cached
    with _node_path_lock:
        _node_path_cached = _NODE_PATH_UNSET


# ---------------------------------------------------------------------------
# 目录工具
# ---------------------------------------------------------------------------
def ensure_downloads_dir(download_dir: str | Path | None = None) -> Path:
    """Compatibility wrapper retaining downloader-level filesystem seams."""
    return output_files.ensure_downloads_dir(
        download_dir,
        project_dir=PROJECT_DIR,
        downloads_dir=DOWNLOADS_DIR,
        path_cls=Path,
        os_module=os,
        uuid_module=uuid,
    )


_PreparedOutputDir = output_files._PreparedOutputDir


def _prepare_output_dir(download_dir: str | Path | None) -> _PreparedOutputDir:
    return output_files.prepare_output_dir(
        download_dir,
        ensure_directory=ensure_downloads_dir,
    )


def _prepared_output_dir(prepared: object) -> Path:
    return output_files.prepared_output_dir(prepared)


# ---------------------------------------------------------------------------
# 链接识别与校验
# ---------------------------------------------------------------------------
def normalize_url(url: str) -> str:
    return media_sources.normalize_url(url)


def _detect_normalized_platform(normalized: str) -> Optional[str]:
    return media_sources._detect_normalized_platform(normalized)


def detect_platform(url: str) -> Optional[str]:
    return media_sources.detect_platform(
        url,
        normalizer=normalize_url,
        detector=_detect_normalized_platform,
    )


def detect_collection_platform(url: str) -> Optional[str]:
    return media_sources.detect_collection_platform(url, normalizer=normalize_url)


def is_valid_youtube_url(url: str) -> bool:
    return detect_platform(url) == YOUTUBE


def is_valid_instagram_url(url: str) -> bool:
    return detect_platform(url) == INSTAGRAM


def is_valid_bilibili_url(url: str) -> bool:
    return detect_platform(url) == BILIBILI


def make_task(url: str) -> Optional[VideoTask]:
    return media_sources.make_task(
        url,
        normalizer=normalize_url,
        detector=_detect_normalized_platform,
    )


# ---------------------------------------------------------------------------
# Cookie 查找
# ---------------------------------------------------------------------------
def find_cookie_file(platform: str) -> Optional[Path]:
    return media_sources.find_cookie_file(platform, project_dir=PROJECT_DIR)


def _find_cookie_file(platform: str) -> Optional[Path]:
    return find_cookie_file(platform)


def platform_http_headers(platform: str) -> dict[str, str]:
    return media_sources.platform_http_headers(platform)


def _extract_progress_snapshot(data: dict) -> dict[str, object]:
    """Compatibility wrapper retaining downloader-level patch seams."""
    return download_progress.extract_progress_snapshot(
        data,
        format_download_speed_fn=_format_download_speed,
        strip_ansi_fn=_strip_ansi,
        progress_total_size_fn=_progress_total_size,
        format_eta_fn=_format_eta,
        format_size_bytes_fn=_format_size_bytes,
    )


def _make_progress_hook(
    index: int,
    total: int,
    progress_callback: YtdlpProgressCallback = None,
    cancel_token: CancellationToken | None = None,
    media_type: str = VIDEO,
    audio_format: str = MP3,
):
    """Compatibility wrapper retaining downloader-level patch seams."""
    return download_progress.make_progress_hook(
        index,
        total,
        progress_callback,
        cancel_token,
        media_type,
        audio_format,
        extract_progress_snapshot_fn=lambda data: _extract_progress_snapshot(data),
        postprocessing_preparation_fn=lambda current_media_type, current_audio_format: (
            _postprocessing_preparation(current_media_type, current_audio_format)
        ),
    )


def _make_postprocessor_status_hook(
    index: int,
    total: int,
    progress_callback: YtdlpProgressCallback = None,
    media_type: str = VIDEO,
    audio_format: str = MP3,
):
    """Compatibility wrapper retaining downloader-level patch seams."""
    return download_progress.make_postprocessor_status_hook(
        index,
        total,
        progress_callback,
        media_type,
        audio_format,
        postprocessor_stage_fn=lambda postprocessor, current_media_type, current_audio_format: (
            _postprocessor_stage(
                postprocessor,
                current_media_type,
                current_audio_format,
            )
        ),
    )


def _make_cancel_hook(cancel_token: CancellationToken):
    """Compatibility wrapper retaining downloader-level hook metadata."""
    return download_progress.make_cancel_hook(cancel_token)


def _audio_output_profile(info: dict, requested: str) -> AudioOutputProfile:
    """Compatibility wrapper retaining downloader-level patch seams."""
    return audio_output.audio_output_profile(
        info,
        requested,
        selected_audio_info_fn=_selected_audio_info,
        display_audio_codec_fn=_display_audio_codec,
    )


def _ensure_source_copy_supported(
    info: dict,
    profile: AudioOutputProfile,
) -> None:
    """Compatibility wrapper retaining downloader-level patch seams."""
    return audio_output.ensure_source_copy_supported(
        info,
        profile,
        selected_audio_info_fn=_selected_audio_info,
        classify_download_error_fn=classify_download_error,
        download_failure_cls=DownloadFailure,
    )


def _validate_output_version(output_version: int) -> None:
    output_files.validate_output_version(output_version)


def _output_template(
    platform: str,
    output_dir: Path,
    output_version: int,
) -> str:
    return output_files.output_template(platform, output_dir, output_version)


def _attempt_output_template(
    platform: str,
    output_dir: Path,
    attempt_workspace: Path,
) -> str:
    return output_files.attempt_output_template(platform, output_dir, attempt_workspace)


# ---------------------------------------------------------------------------
# yt-dlp 选项构建
# ---------------------------------------------------------------------------
def _build_ydl_options(
    platform: str,
    output_dir: Path,
    index: int,
    total: int,
    progress_callback: YtdlpProgressCallback = None,
    media_type: str = VIDEO,
    audio_format: str = MP3,
    speed_mode: str = STANDARD,
    aria2_executable: str | None = None,
    selected_audio: dict | None = None,
    cancel_token: CancellationToken | None = None,
    output_version: int = 1,
    attempt_workspace: Path | None = None,
) -> dict:
    """生成公共配置，并追加平台专用配置。"""
    if not isinstance(media_type, str) or media_type not in MEDIA_TYPES:
        raise ValueError(f"不支持的下载类型: {media_type}")
    if not isinstance(audio_format, str) or audio_format not in AUDIO_FORMATS:
        raise ValueError(f"不支持的音频格式: {audio_format}")
    if not isinstance(speed_mode, str) or speed_mode not in SPEED_MODES:
        raise ValueError(f"不支持的速度模式: {speed_mode}")
    _validate_output_version(output_version)

    output_template = (
        _attempt_output_template(platform, output_dir, attempt_workspace)
        if attempt_workspace is not None
        else _output_template(platform, output_dir, output_version)
    )
    options = {
        "outtmpl": output_template,
        "progress_hooks": [
            _make_progress_hook(
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
        "logger": _QuietYtdlpLogger(),
        "retries": 10,
        "fragment_retries": 10,
        "extractor_retries": 5,
        "socket_timeout": 30,
        "overwrites": False,
    }
    if attempt_workspace is not None:
        options["paths"] = {"temp": str(attempt_workspace)}

    if platform == YOUTUBE:
        node_path = _node_path()
        options["js_runtimes"] = {"node": {"path": node_path} if node_path else {}}
        options["remote_components"] = ["ejs:github"]
    elif platform == INSTAGRAM:
        options.update(
            {
                "http_headers": platform_http_headers(INSTAGRAM),
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
        audio_profile = _audio_output_profile(
            profile_info or {},
            audio_format,
        )
        postprocessors = _audio_postprocessors(audio_profile)
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

    cookie_file = _find_cookie_file(platform)
    if cookie_file:
        options["cookiefile"] = str(cookie_file)

    if platform == BILIBILI and speed_mode == TURBO and aria2_executable:
        configure_aria2(options, aria2_executable)

    postprocessor_hooks = []
    if cancel_token:
        postprocessor_hooks.append(_make_cancel_hook(cancel_token))
    postprocessor_hooks.append(
        _make_postprocessor_status_hook(
            index,
            total,
            progress_callback,
            media_type,
            audio_format,
        )
    )
    options["postprocessor_hooks"] = postprocessor_hooks

    return options


def _rename_audio_output(
    filepath: Path,
    profile: AudioOutputProfile,
    output_version: int = 1,
) -> Path:
    _validate_output_version(output_version)
    version_suffix = "" if output_version == 1 else f" ({output_version})"
    stem = ATTEMPT_OUTPUT_MARKER_RE.sub("", filepath.stem)
    if version_suffix and stem.endswith(version_suffix):
        stem = stem[: -len(version_suffix)]
    return _claim_final_output(
        filepath,
        f"{stem} [{_audio_quality_label(profile)}]",
        output_version,
    )


def _claim_final_output(
    filepath: Path,
    final_stem: str,
    output_version: int,
) -> Path:
    return output_files.claim_final_output(
        filepath,
        final_stem,
        output_version,
        os_module=os,
        claim_output=_claim_final_output_with_version,
    )


def _claim_final_output_with_version(
    filepath: Path,
    final_stem: str,
    output_version: int,
) -> tuple[Path, int]:
    return output_files.claim_final_output_with_version(
        filepath,
        final_stem,
        output_version,
        os_module=os,
        validate_version=_validate_output_version,
    )


def _finalize_video_output(
    filepath: Path,
    output_version: int = 1,
) -> Path:
    return output_files.finalize_video_output(
        filepath,
        output_version,
        os_module=os,
        claim_output=_claim_final_output_with_version,
    )


def _finalize_video_output_with_version(
    filepath: Path,
    output_version: int = 1,
) -> tuple[Path, int]:
    return output_files.finalize_video_output_with_version(
        filepath,
        output_version,
        os_module=os,
        claim_output=_claim_final_output_with_version,
    )


def _audio_output_version(filepath: Path, requested: int) -> int:
    return output_files.audio_output_version(filepath, requested)


def _resolve_output_path(
    ydl,
    info: dict,
    output_dir: Path,
    media_type: str = VIDEO,
    audio_format: str = MP3,
    audio_profile: AudioOutputProfile | None = None,
    audio_output_ext: str | None = None,
) -> Path:
    return output_files.resolve_output_path(
        ydl,
        info,
        output_dir,
        media_type,
        audio_format,
        audio_profile,
        audio_output_ext,
        path_cls=Path,
    )


def _format_filesize(filepath: Path, info: dict) -> str:
    return output_files.format_filesize(filepath, info)


# ---------------------------------------------------------------------------
# 错误处理
# ---------------------------------------------------------------------------
def _handle_download_error(
    error_msg: str,
    platform: Optional[str] = None,
    media_type: str = VIDEO,
) -> None:
    """根据平台和 yt-dlp 错误信息提供中文提示。"""
    msg = error_msg.lower()
    platform_name = PLATFORM_NAMES.get(platform or "", "视频平台")

    if "ffmpeg" in msg or "ffprobe" in msg:
        print("\n❌ 错误：未找到 FFmpeg。")
        if media_type == AUDIO:
            print("   MP3 音频转换需要 FFmpeg。")
        print("   macOS: brew install ffmpeg")
        print("   Windows: 从 https://ffmpeg.org/download.html 下载并添加到 PATH")
        print("   Ubuntu: sudo apt install ffmpeg")
    elif media_type == AUDIO and (
        "requested format is not available" in msg or "no audio" in msg
    ):
        print("\n❌ 错误：未找到可下载的音频流。")
    elif platform == INSTAGRAM and "empty media response" in msg:
        cookie_path = PROJECT_DIR / "instagram_cookies.txt"
        print("\n❌ 错误：Instagram 返回了空媒体数据。")
        print("   这通常表示该内容在当前未登录状态下不可访问，或当前访问环境被限制。")
        print(f"   请先确认浏览器登录账号能打开该链接，再导出 Cookie 保存为: {cookie_path}")
        print("   也可以保存为通用 cookies.txt，但 instagram_cookies.txt 优先级更高。")
    elif platform == INSTAGRAM and "http error 400" in msg:
        cookie_path = PROJECT_DIR / "instagram_cookies.txt"
        print("\n❌ 错误：Instagram API 拒绝了该请求 (HTTP 400)。")
        print("   这通常表示 Cookie 会话不完整、账号被风控、链接对当前账号不可访问，或 Instagram 接口策略变更。")
        print("   请先在同一个浏览器中确认该链接能正常播放，再重新导出完整 Cookie。")
        print(f"   Cookie 文件路径: {cookie_path}")
    elif platform == BILIBILI and "http error 412" in msg:
        cookie_path = PROJECT_DIR / "bilibili_cookies.txt"
        print("\n❌ 错误：请求触发了 Bilibili 风控 (HTTP 412)。")
        print("   请降低请求频率、切换到可正常访问 Bilibili 的网络环境后稍后重试。")
        print(f"   如内容需要登录，请导出有效 Cookie 并保存为: {cookie_path}")
    elif "http error 429" in msg or "rate limit" in msg or "too many request" in msg:
        print(f"\n❌ 错误：请求过于频繁，{platform_name} 已限制访问，请稍后重试。")
    elif "http error 403" in msg:
        print(f"\n❌ 错误：{platform_name} 拒绝访问 (HTTP 403)。")
        print("   可尝试配置对应平台的 Cookie 后重试。")
    elif "http error 404" in msg:
        print("\n❌ 错误：内容未找到 (HTTP 404)，链接可能已失效或内容已删除。")
    elif "private" in msg and ("account" in msg or "video" in msg):
        print("\n❌ 错误：账号或视频为私密内容，当前凭证无权访问。")
    elif platform == BILIBILI and any(
        marker in msg
        for marker in ("premium", "member only", "members only", "login", "sign in")
    ):
        cookie_path = PROJECT_DIR / "bilibili_cookies.txt"
        print("\n❌ 错误：当前账号无权访问该 Bilibili 内容，或该内容需要登录/会员权限。")
        print("   请先确认浏览器中的 Bilibili 账号可以播放该视频。")
        print(f"   然后导出完整 Cookie 并保存为: {cookie_path}")
    elif "login" in msg or "sign in" in msg:
        print(f"\n❌ 错误：需要登录 {platform_name} 才能访问该内容。")
        print(f"   请将 Cookie 保存为 {platform or '平台'}_cookies.txt 或 cookies.txt 后重试。")
    elif "story" in msg and ("expired" in msg or "unavailable" in msg):
        print("\n❌ 错误：该 Instagram Story 已过期或不可用。")
    elif "video unavailable" in msg or "video has been removed" in msg:
        print("\n❌ 错误：视频不可用或已被删除。")
    elif "copyright" in msg or "blocked" in msg:
        print("\n❌ 错误：视频受版权或地区访问限制。")
    elif "age" in msg and ("restricted" in msg or "verify" in msg):
        print("\n❌ 错误：内容有年龄限制，需要登录验证。")
    elif "network" in msg or "connection" in msg or "timeout" in msg:
        print("\n❌ 错误：网络连接失败，请检查网络设置后重试。")
    else:
        print(f"\n❌ 下载失败: {error_msg}")


# ---------------------------------------------------------------------------
# Bilibili 自适应下载
# ---------------------------------------------------------------------------
def _extract_bilibili_info(url: str, options: dict):
    """使用实例级适配器提取一次已选格式信息，但不下载媒体。"""
    ydl = yt_dlp.YoutubeDL(options)
    register_bilibili_extractor(ydl)
    try:
        info = ydl.extract_info(url, download=False)
        return ydl, info
    except Exception:
        ydl.close()
        raise


def _new_attempt_workspace(output_dir: Path) -> Path:
    return output_files.new_attempt_workspace(output_dir, uuid_module=uuid)


def _cleanup_attempt_workspace(workspace: Path) -> None:
    output_files.cleanup_attempt_workspace(
        workspace,
        path_cls=Path,
        shutil_module=shutil,
    )


def _process_bilibili_attempt(
    prepared_info: dict,
    options: dict,
    output_dir: Path,
) -> tuple[dict, Path]:
    """处理已提取的格式信息，执行传输与 yt-dlp 后处理。"""
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.process_info(prepared_info)
        filepath = _resolve_output_path(
            ydl,
            prepared_info,
            output_dir,
            prepared_info["_media_type"],
            prepared_info.get("_audio_format_used", MP3),
            audio_output_ext=prepared_info.get("_audio_output_ext"),
        )
    return prepared_info, filepath


def _is_aria2_failure(error: Exception) -> bool:
    message = str(error).lower()
    return "aria2c" in message and (
        "exited" in message or "external downloader" in message
    )


def _is_cdn_access_failure(error: Exception) -> bool:
    message = str(error).lower()
    return "http error 403" in message or "http error 412" in message


def _is_cdn_transport_failure(error: Exception) -> bool:
    """Return whether another Bilibili CDN may recover a broken transfer."""
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "winerror 10053",
            "winerror 10054",
            "connection reset",
            "connection aborted",
            "connection broken",
            "forcibly closed",
            "remote host closed",
            "incomplete read",
            "远程主机强迫关闭",
        )
    )


def _build_download_result(
    info: dict,
    filepath: Path,
    platform_name: str,
    media_type: str,
    requested_mode: str,
    used_mode: str,
    turbo_fallback: bool,
    plan: AccelerationPlan,
    audio_profile: AudioOutputProfile | None = None,
    output_version_actual: int = 1,
) -> DownloadResult:
    resolution = info.get("resolution") or (
        f"{info.get('width')}x{info.get('height')}"
        if info.get("width") and info.get("height")
        else "未知"
    )
    cover_embedded = info.get("_cover_embedded")
    cover_source = info.get("_cover_source")
    fallback_cover = info.get("_fallback_cover")
    if not isinstance(cover_embedded, bool) or cover_source not in {
        "source",
        "fallback",
        "none",
    }:
        cover_embedded = False
        cover_source = "none"
        fallback_cover = None
    elif not cover_embedded or cover_source == "none":
        cover_embedded = False
        cover_source = "none"
        fallback_cover = None
    elif cover_source == "source":
        fallback_cover = None
    elif not isinstance(fallback_cover, str) or not fallback_cover:
        cover_embedded = False
        cover_source = "none"
        fallback_cover = None

    result = {
        "platform": platform_name,
        "title": info.get("title", "未知标题"),
        "filepath": str(filepath),
        "filesize": _format_filesize(filepath, info),
        "media_type": media_type,
        "speed_mode_requested": requested_mode,
        "speed_mode_used": used_mode,
        "turbo_fallback": turbo_fallback,
        "cdn_host": plan.cdn_host or "未知",
        "http_chunk_size": plan.http_chunk_size,
        "output_version_actual": output_version_actual,
        "cover_embedded": cover_embedded,
        "cover_source": cover_source,
        "fallback_cover": fallback_cover,
    }
    if media_type == AUDIO:
        if audio_profile is None:
            raise ValueError("音频结果缺少输出格式信息")
        result.update(
            {
                "format": _audio_format_name(audio_profile),
                "acodec": (
                    audio_profile.source_acodec
                    if audio_profile.used == SOURCE
                    else audio_profile.used
                ),
                "audio_format_requested": audio_profile.requested,
                "audio_format_used": audio_profile.used,
                "audio_format_fallback": audio_profile.fallback,
                "output_ext": audio_profile.output_ext,
                "source_acodec": audio_profile.source_acodec or "未知",
                "source_abr_kbps": (
                    audio_profile.source_abr_kbps or "未知"
                ),
            }
        )
    else:
        result.update(
            {
                "resolution": resolution,
                "fps": info.get("fps") or "未知",
                "vcodec": info.get("vcodec") or "未知",
                "acodec": info.get("acodec") or "未知",
            }
        )
    return result


def _local_source_thumbnail(info: dict, media_path: Path) -> Path | None:
    """Resolve a task-owned thumbnail even after yt-dlp moved its sidecars."""
    thumbnails = info.get("thumbnails")
    if not isinstance(thumbnails, list):
        return None
    for thumbnail in reversed(thumbnails):
        if not isinstance(thumbnail, dict):
            continue
        raw_path = thumbnail.get("filepath")
        if not isinstance(raw_path, (str, os.PathLike)):
            continue
        try:
            original = Path(raw_path)
            candidates = (original, media_path.parent / original.name)
            for candidate in candidates:
                if (
                    candidate.resolve().parent == media_path.parent.resolve()
                    and ATTEMPT_OUTPUT_MARKER_RE.search(candidate.stem)
                    and candidate.is_file()
                ):
                    return candidate
        except (OSError, RuntimeError, TypeError, ValueError):
            continue
    return None


def _remove_owned_thumbnail(thumbnail: Path | None) -> None:
    """Remove only a verified task-private sidecar; never fail the download."""
    if thumbnail is None or not ATTEMPT_OUTPUT_MARKER_RE.search(thumbnail.stem):
        return
    try:
        thumbnail.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("无法清理临时源封面 %s：%s", thumbnail, exc)


def _finalize_download_output(
    info: dict,
    filepath: Path,
    media_type: str,
    profile: AudioOutputProfile | None,
    output_version: int,
) -> tuple[Path, AudioOutputProfile | None, int]:
    """Claim a visible output name and retain the metadata for its real file."""
    _validate_output_version(output_version)
    source_cover = _local_source_thumbnail(info, filepath)
    if media_type == AUDIO:
        if profile is None:
            raise ValueError("音频结果缺少输出格式信息")
        profile = _profile_for_output_path(profile, filepath)
        if output_version == 1:
            filepath = _rename_audio_output(filepath, profile)
        else:
            filepath = _rename_audio_output(
                filepath,
                profile,
                output_version=output_version,
            )
        output_version_actual = _audio_output_version(filepath, output_version)
    else:
        filepath, output_version_actual = _finalize_video_output_with_version(
            filepath,
            output_version,
        )
        profile = None

    try:
        cover_outcome = _ensure_media_cover(
            filepath,
            source_cover=source_cover,
        )
    except Exception as exc:
        logger.warning("媒体封面处理失败但下载文件已保留 %s：%s", filepath, exc)
        cover_outcome = CoverOutcome(False, "none")
    finally:
        _remove_owned_thumbnail(source_cover)
    info["_cover_embedded"] = cover_outcome.embedded
    info["_cover_source"] = cover_outcome.source
    info["_fallback_cover"] = cover_outcome.fallback_name
    return filepath, profile, output_version_actual


def _download_bilibili(
    url: str,
    index: int,
    total: int,
    output_dir: Path,
    progress_callback: YtdlpProgressCallback,
    media_type: str,
    speed_mode: str,
    audio_format: str,
    cancel_token: CancellationToken | None = None,
    output_version: int = 1,
) -> DownloadResult:
    if cancel_token:
        cancel_token.raise_if_cancelled()
    executable = aria2c_path()
    used_mode = effective_speed_mode(BILIBILI, speed_mode, executable)
    metadata_options = _build_ydl_options(
        BILIBILI,
        output_dir,
        index,
        total,
        progress_callback=progress_callback,
        media_type=media_type,
        audio_format=audio_format,
        speed_mode=STANDARD,
        cancel_token=cancel_token,
        output_version=output_version,
    )
    media_name = "音频" if media_type == AUDIO else "视频"
    print(f"\n{'─' * 56}")
    print(
        f"[{index}/{total}] [{PLATFORM_NAMES[BILIBILI]}] "
        f"🔍 正在获取{media_name}信息: {url}\n"
    )

    metadata_ydl, extracted = _extract_bilibili_info(url, metadata_options)
    try:
        if cancel_token:
            cancel_token.raise_if_cancelled()
        if not extracted:
            raise yt_dlp.utils.DownloadError("下载器未返回视频信息")
        plan = build_acceleration_plan(metadata_ydl, extracted)
    finally:
        metadata_ydl.close()

    audio_profile = (
        _audio_output_profile(extracted, audio_format)
        if media_type == AUDIO
        else None
    )
    if audio_profile:
        _ensure_source_copy_supported(extracted, audio_profile)

    original_info = extracted
    original_cdn_host = primary_host(original_info)
    cdn_switched = needs_cdn_host_switch(original_info, plan.cdn_host)
    if cdn_switched:
        optimized_info = copy.deepcopy(original_info)
        apply_cdn_host(optimized_info, plan.cdn_host)
    else:
        optimized_info = original_info

    prepared_infos = [original_info]
    if optimized_info is not original_info:
        prepared_infos.append(optimized_info)
    for prepared in prepared_infos:
        prepared["_media_type"] = media_type
        if audio_profile:
            prepared["_audio_format_used"] = audio_profile.used
            prepared["_audio_output_ext"] = audio_profile.output_ext

    attempts = [(used_mode, optimized_info, plan, False)]
    if used_mode == TURBO:
        attempts.append(
            (STANDARD, copy.deepcopy(optimized_info), plan, True)
        )

    original_plan = AccelerationPlan(
        False,
        original_cdn_host,
        BILIBILI_HTTP_CHUNK_SIZE,
    )
    if cdn_switched:
        attempts.append(
            (
                STANDARD,
                original_info,
                original_plan,
                used_mode == TURBO,
            )
        )

    # A successful short range probe does not guarantee that a CDN will keep a
    # long transfer alive. Keep the remaining hosts available for lazy failover.
    represented_hosts = {
        attempt_plan.cdn_host
        for _, _, attempt_plan, _ in attempts
        if attempt_plan.cdn_host
    }
    backup_hosts = [
        host
        for host in candidate_hosts(original_info)
        if host not in represented_hosts
    ]

    last_error = None
    for attempt_index, (
        attempt_mode,
        prepared_info,
        attempt_plan,
        fallback,
    ) in enumerate(attempts):
        if cancel_token:
            cancel_token.raise_if_cancelled()
        attempt_workspace = _new_attempt_workspace(output_dir)
        try:
            options = _build_ydl_options(
                BILIBILI,
                output_dir,
                index,
                total,
                progress_callback=progress_callback,
                media_type=media_type,
                audio_format=(audio_profile.used if audio_profile else MP3),
                speed_mode=attempt_mode,
                aria2_executable=executable,
                selected_audio=(extracted if audio_profile else None),
                cancel_token=cancel_token,
                output_version=output_version,
                attempt_workspace=attempt_workspace,
            )
            options["http_chunk_size"] = attempt_plan.http_chunk_size
            if progress_callback:
                progress_callback(
                    "mode",
                    {
                        "speed_mode": attempt_mode,
                        "turbo_fallback": fallback,
                    },
                )
            final_info, filepath = _process_bilibili_attempt(
                prepared_info,
                options,
                output_dir,
            )
            filepath, audio_profile, output_version_actual = (
                _finalize_download_output(
                    final_info,
                    filepath,
                    media_type,
                    audio_profile,
                    output_version,
                )
            )
            return _build_download_result(
                final_info,
                filepath,
                PLATFORM_NAMES[BILIBILI],
                media_type,
                speed_mode,
                attempt_mode,
                fallback,
                attempt_plan,
                audio_profile,
                output_version_actual,
            )
        except DownloadCancelled:
            raise
        except yt_dlp.utils.DownloadError as error:
            last_error = error
            if (
                _is_cdn_access_failure(error)
                or _is_cdn_transport_failure(error)
            ):
                while backup_hosts:
                    backup_host = backup_hosts.pop(0)
                    backup_info = copy.deepcopy(original_info)
                    if not apply_cdn_host(backup_info, backup_host):
                        continue
                    backup_info["_media_type"] = media_type
                    if audio_profile:
                        backup_info["_audio_format_used"] = audio_profile.used
                        backup_info["_audio_output_ext"] = audio_profile.output_ext
                    attempts.append(
                        (
                            STANDARD,
                            backup_info,
                            AccelerationPlan(
                                True,
                                backup_host,
                                BILIBILI_HTTP_CHUNK_SIZE,
                            ),
                            used_mode == TURBO,
                        )
                    )
                    represented_hosts.add(backup_host)
                    break
            next_is_standard = (
                attempt_index + 1 < len(attempts)
                and attempts[attempt_index + 1][0] == STANDARD
            )
            can_retry_aria2 = (
                attempt_mode == TURBO
                and _is_aria2_failure(error)
                and next_is_standard
            )
            can_retry_cdn = (
                _is_cdn_access_failure(error)
                and any(
                    future_plan.cdn_host != attempt_plan.cdn_host
                    for _, _, future_plan, _ in attempts[attempt_index + 1 :]
                )
            )
            can_retry_transport = (
                _is_cdn_transport_failure(error)
                and any(
                    future_plan.cdn_host != attempt_plan.cdn_host
                    for _, _, future_plan, _ in attempts[attempt_index + 1 :]
                )
            )
            if not can_retry_aria2 and not can_retry_cdn and not can_retry_transport:
                raise
        finally:
            _cleanup_attempt_workspace(attempt_workspace)

    raise last_error or yt_dlp.utils.DownloadError("Bilibili 下载失败")


# ---------------------------------------------------------------------------
# 单视频下载
# ---------------------------------------------------------------------------
def download_video(
    url: str,
    index: int = 1,
    total: int = 1,
    platform: Optional[str] = None,
    progress_callback: YtdlpProgressCallback = None,
    media_type: str = VIDEO,
    audio_format: str = MP3,
    speed_mode: str = STANDARD,
    cancel_token: CancellationToken | None = None,
    output_version: int = 1,
    raise_errors: bool = False,
    output_dir: str | Path | None = None,
) -> Optional[DownloadResult]:
    """自动识别平台并使用 yt-dlp 下载单个视频。"""
    platform = platform or detect_platform(url)
    if platform is None:
        print(f"\n❌ 无法识别视频平台: {url}")
        return None
    if not isinstance(media_type, str) or media_type not in MEDIA_TYPES:
        raise ValueError(f"不支持的下载类型: {media_type}")
    if not isinstance(speed_mode, str) or speed_mode not in SPEED_MODES:
        raise ValueError(f"不支持的速度模式: {speed_mode}")
    if not isinstance(audio_format, str) or audio_format not in AUDIO_FORMATS:
        raise ValueError(f"不支持的音频格式: {audio_format}")
    _validate_output_version(output_version)
    if cancel_token:
        cancel_token.raise_if_cancelled()

    prepared_dir = (
        _prepared_output_dir(output_dir)
        if isinstance(output_dir, _PreparedOutputDir)
        else ensure_downloads_dir(output_dir)
    )
    return _download_video(
        url,
        index=index,
        total=total,
        platform=platform,
        progress_callback=progress_callback,
        media_type=media_type,
        audio_format=audio_format,
        speed_mode=speed_mode,
        cancel_token=cancel_token,
        output_version=output_version,
        raise_errors=raise_errors,
        output_dir=prepared_dir,
    )


def _download_video(
    url: str,
    index: int = 1,
    total: int = 1,
    platform: Optional[str] = None,
    progress_callback: YtdlpProgressCallback = None,
    media_type: str = VIDEO,
    audio_format: str = MP3,
    speed_mode: str = STANDARD,
    cancel_token: CancellationToken | None = None,
    output_version: int = 1,
    raise_errors: bool = False,
    output_dir: Path = DOWNLOADS_DIR,
) -> Optional[DownloadResult]:
    """Download to an already prepared absolute directory."""
    platform = platform or detect_platform(url)
    if platform is None:
        print(f"\n❌ 无法识别视频平台: {url}")
        return None
    if not isinstance(media_type, str) or media_type not in MEDIA_TYPES:
        raise ValueError(f"不支持的下载类型: {media_type}")
    if not isinstance(speed_mode, str) or speed_mode not in SPEED_MODES:
        raise ValueError(f"不支持的速度模式: {speed_mode}")
    if not isinstance(audio_format, str) or audio_format not in AUDIO_FORMATS:
        raise ValueError(f"不支持的音频格式: {audio_format}")
    _validate_output_version(output_version)
    if cancel_token:
        cancel_token.raise_if_cancelled()

    if platform == BILIBILI:
        try:
            return _download_bilibili(
                url,
                index,
                total,
                output_dir,
                progress_callback,
                media_type,
                speed_mode,
                audio_format,
                cancel_token,
                output_version,
            )
        except DownloadCancelled as error:
            if raise_errors:
                raise
            print(f"\n{format_cli_error(error)}")
            return None
        except DownloadFailure as error:
            if raise_errors:
                raise
            print(f"\n{format_cli_error(error)}")
            return None
        except Exception as error:
            info = classify_download_error(error, platform)
            if raise_errors:
                raise DownloadFailure(info) from error
            print(f"\n{format_cli_error(info)}")
            return None

    platform_name = PLATFORM_NAMES[platform]
    media_name = "音频" if media_type == AUDIO else "视频"

    attempt_workspace = _new_attempt_workspace(output_dir)
    try:
        print(f"\n{'─' * 56}")
        print(f"[{index}/{total}] [{platform_name}] 🔍 正在获取{media_name}信息: {url}\n")
        if media_type == AUDIO:
            metadata_options = _build_ydl_options(
                platform,
                output_dir,
                index,
                total,
                progress_callback=progress_callback,
                media_type=media_type,
                audio_format=audio_format,
                cancel_token=cancel_token,
                output_version=output_version,
                attempt_workspace=attempt_workspace,
            )
            if cancel_token:
                cancel_token.raise_if_cancelled()
            with yt_dlp.YoutubeDL(metadata_options) as metadata_ydl:
                info = metadata_ydl.extract_info(url, download=False)
            if cancel_token:
                cancel_token.raise_if_cancelled()
            if not info:
                print("\n❌ 下载器未返回视频信息。")
                return None

            audio_profile = _audio_output_profile(info, audio_format)
            _ensure_source_copy_supported(info, audio_profile)
            options = _build_ydl_options(
                platform,
                output_dir,
                index,
                total,
                progress_callback=progress_callback,
                media_type=media_type,
                audio_format=audio_profile.used,
                selected_audio=info,
                cancel_token=cancel_token,
                output_version=output_version,
                attempt_workspace=attempt_workspace,
            )
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.process_info(info)
                filepath = _resolve_output_path(
                    ydl,
                    info,
                    output_dir,
                    media_type=media_type,
                    audio_format=audio_profile.used,
                    audio_profile=audio_profile,
                )
            filepath, audio_profile, output_version_actual = (
                _finalize_download_output(
                    info,
                    filepath,
                    media_type,
                    audio_profile,
                    output_version,
                )
            )
            return _build_download_result(
                info,
                filepath,
                platform_name,
                media_type,
                speed_mode,
                STANDARD,
                False,
                AccelerationPlan(False, None, 0),
                audio_profile,
                output_version_actual,
            )

        options = _build_ydl_options(
            platform,
            output_dir,
            index,
            total,
            progress_callback=progress_callback,
            media_type=media_type,
            audio_format=audio_format,
            cancel_token=cancel_token,
            output_version=output_version,
            attempt_workspace=attempt_workspace,
        )
        if cancel_token:
            cancel_token.raise_if_cancelled()
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                print("\n❌ 下载器未返回视频信息。")
                return None

            filepath = _resolve_output_path(
                ydl,
                info,
                output_dir,
                media_type=media_type,
            )
            filepath, _, output_version_actual = _finalize_download_output(
                info,
                filepath,
                media_type,
                None,
                output_version,
            )
            return _build_download_result(
                info,
                filepath,
                platform_name,
                media_type,
                speed_mode,
                STANDARD,
                False,
                AccelerationPlan(False, None, 0),
                None,
                output_version_actual,
            )

    except DownloadCancelled as error:
        if raise_errors:
            raise
        print(f"\n{format_cli_error(error)}")
        return None
    except DownloadFailure as error:
        if raise_errors:
            raise
        print(f"\n{format_cli_error(error)}")
        return None
    except Exception as error:
        info = classify_download_error(error, platform)
        if raise_errors:
            raise DownloadFailure(info) from error
        print(f"\n{format_cli_error(info)}")
        return None
    finally:
        _cleanup_attempt_workspace(attempt_workspace)


# ---------------------------------------------------------------------------
# 批量下载
# ---------------------------------------------------------------------------
def download_tasks(
    tasks: list[VideoTask],
    progress_callback: ProgressCallback = None,
    media_type: str = VIDEO,
    audio_format: str = MP3,
    speed_mode: str = STANDARD,
    output_dir: str | Path | None = None,
) -> list[tuple[VideoTask, Optional[DownloadResult]]]:
    """最多并行执行三个混合平台下载任务，并保持结果顺序。

    Parameters
    ----------
    tasks : list[VideoTask]
        待下载的任务列表，每项为 (platform, url)。
    progress_callback : ProgressCallback or None
        可选进度回调，签名为 callback(task_index, event, data)。
        - event='started' 时 data 含 url、platform。
        - event='progress' 时 data 含 percent_text、speed_text、speed_mbps、eta_text。
        - event='completed' 时 data 为 DownloadResult。
        - event='failed' 时 data 含 error 字段。
    media_type : str
        `video` 下载视频，`audio` 下载最高可用音轨。
    audio_format : str
        `mp3` 输出 MP3 V0；`flac` 仅在源音轨为 FLAC 时无损输出，
        否则自动回退为 MP3 V0。
    speed_mode : str
        `standard` 使用原生下载器，`turbo` 仅对 Bilibili 尝试 aria2c。
    output_dir : str, Path or None
        自定义下载目录；留空时继续使用项目内的 `downloads`。
    """
    if not isinstance(media_type, str) or media_type not in MEDIA_TYPES:
        raise ValueError(f"不支持的下载类型: {media_type}")
    if not isinstance(speed_mode, str) or speed_mode not in SPEED_MODES:
        raise ValueError(f"不支持的速度模式: {speed_mode}")
    if not isinstance(audio_format, str) or audio_format not in AUDIO_FORMATS:
        raise ValueError(f"不支持的音频格式: {audio_format}")
    output_dir = (
        output_dir
        if isinstance(output_dir, _PreparedOutputDir)
        else _prepare_output_dir(output_dir)
    )

    total = len(tasks)
    if not tasks:
        return []

    bilibili_slots = threading.BoundedSemaphore(
        MAX_PARALLEL_BILIBILI_DOWNLOADS
    )
    logger = get_download_logger()

    def _run_task(index_and_task):
        task_index, task = index_and_task
        platform, url = task

        def _relay_progress(event: str, data: dict[str, object]) -> None:
            if progress_callback:
                progress_callback(task_index, event, data)

        def _download_current_task():
            started_at = time.monotonic()
            if progress_callback:
                progress_callback(
                    task_index,
                    "started",
                    {"url": url, "platform": platform},
                )
            log_download_event(
                logger,
                "started",
                platform=platform,
                media_type=media_type,
                audio_format=audio_format,
                speed_mode=speed_mode,
                task_index=task_index + 1,
                attempt_number=1,
            )
            try:
                result = download_video(
                    url,
                    index=task_index + 1,
                    total=total,
                    platform=platform,
                    progress_callback=(
                        _relay_progress if progress_callback else None
                    ),
                    media_type=media_type,
                    audio_format=audio_format,
                    speed_mode=speed_mode,
                    output_dir=output_dir,
                    raise_errors=True,
                )
                if result is None:
                    raise DownloadFailure(
                        classify_download_error(
                            RuntimeError("download returned no result"),
                            platform,
                        )
                    )
                elapsed = round(time.monotonic() - started_at, 3)
                log_download_event(
                    logger,
                    "completed",
                    platform=platform,
                    media_type=media_type,
                    audio_format=audio_format,
                    speed_mode=speed_mode,
                    task_index=task_index + 1,
                    attempt_number=1,
                    elapsed_seconds=elapsed,
                )
                if progress_callback:
                    progress_callback(task_index, "completed", result)
                return result
            except DownloadCancelled as error:
                elapsed = round(time.monotonic() - started_at, 3)
                data = public_error(error)
                log_download_event(
                    logger,
                    "cancelled",
                    platform=platform,
                    media_type=media_type,
                    audio_format=audio_format,
                    speed_mode=speed_mode,
                    task_index=task_index + 1,
                    attempt_number=1,
                    elapsed_seconds=elapsed,
                    **data,
                )
                if progress_callback:
                    progress_callback(task_index, "cancelled", data)
                return None
            except DownloadFailure as error:
                elapsed = round(time.monotonic() - started_at, 3)
                data = public_error(error)
                log_download_event(
                    logger,
                    "failed",
                    platform=platform,
                    media_type=media_type,
                    audio_format=audio_format,
                    speed_mode=speed_mode,
                    task_index=task_index + 1,
                    attempt_number=1,
                    elapsed_seconds=elapsed,
                    technical_detail=error.info.technical_detail,
                    **data,
                )
                if progress_callback:
                    progress_callback(task_index, "failed", data)
                else:
                    print(f"\n{format_cli_error(error)}")
                return None
            except Exception as error:
                info = classify_download_error(error, platform)
                failure = DownloadFailure(info)
                elapsed = round(time.monotonic() - started_at, 3)
                data = public_error(failure)
                log_download_event(
                    logger,
                    "failed",
                    platform=platform,
                    media_type=media_type,
                    audio_format=audio_format,
                    speed_mode=speed_mode,
                    task_index=task_index + 1,
                    attempt_number=1,
                    elapsed_seconds=elapsed,
                    technical_detail=info.technical_detail,
                    **data,
                )
                if progress_callback:
                    progress_callback(task_index, "failed", data)
                else:
                    print(f"\n{format_cli_error(failure)}")
                return None

        if platform == BILIBILI:
            with bilibili_slots:
                result = _download_current_task()
        else:
            result = _download_current_task()
        return task, result

    worker_count = min(MAX_PARALLEL_DOWNLOADS, total)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        return list(executor.map(_run_task, enumerate(tasks)))


def download_videos(urls: list[str]):
    """兼容旧程序接口：自动识别 URL 列表后执行批量下载。"""
    tasks = [task for url in urls if (task := make_task(url)) is not None]
    task_results = download_tasks(tasks)
    return [(task[1], result) for task, result in task_results]


# ---------------------------------------------------------------------------
# 环境检查
# ---------------------------------------------------------------------------
def check_ffmpeg() -> bool:
    """检测 FFmpeg 是否在 PATH 中可用。"""
    return shutil.which("ffmpeg") is not None
