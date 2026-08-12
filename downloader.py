#!/usr/bin/env python3
"""
YouTube & Instagram 视频下载核心逻辑。

本模块提供链接识别、下载参数构建、yt-dlp 调用等通用功能。
main.py（命令行）和 app.py（Web 服务）均通过导入本模块复用下载能力。
"""

import copy
import os
import re
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

import yt_dlp

from download_errors import (
    DownloadCancelled,
    DownloadFailure,
    classify_download_error,
    format_cli_error,
    public_error,
)
from download_logging import get_download_logger, log_download_event
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

YOUTUBE = "youtube"
INSTAGRAM = "instagram"
BILIBILI = "bilibili"
VIDEO = "video"
AUDIO = "audio"
MEDIA_TYPES = {VIDEO, AUDIO}
MP3 = "mp3"
FLAC = "flac"
SOURCE = "source"
WAV = "wav"
AUDIO_FORMATS = {MP3, FLAC, SOURCE, WAV}
PLATFORM_NAMES = {
    YOUTUBE: "YouTube",
    INSTAGRAM: "Instagram",
    BILIBILI: "Bilibili",
}
MAX_PARALLEL_DOWNLOADS = 3
MAX_PARALLEL_BILIBILI_DOWNLOADS = 2
ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
SHARE_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
TRAILING_URL_PUNCTUATION = "】）》」』〕〉)]}>\"'“”‘’,.!?;:，。！？；："
ATTEMPT_OUTPUT_MARKER_RE = re.compile(r" \[\.__mvd_[A-Za-z0-9_-]+\]$")

# 类型别名
VideoTask = tuple[str, str]          # (platform, normalized_url)
DownloadResult = dict[str, object]   # 单视频下载结果
ProgressCallback = Callable[[int, str, object], None] | None
YtdlpProgressCallback = Callable[[str, dict[str, object]], None] | None
# ProgressCallback(task_index, event, data)
#   event: 'started' | 'progress' | 'completed' | 'failed'
#   data:  dict — 具体字段视 event 而定


@dataclass(frozen=True)
class AudioOutputProfile:
    requested: str
    used: str
    fallback: bool
    source_acodec: str | None
    source_abr_kbps: int | None
    output_ext: str
    cover_embedded: bool


class _QuietYtdlpLogger:
    """Suppress yt-dlp's raw error text; this module prints localized errors."""

    def debug(self, message: str) -> None:
        return None

    def warning(self, message: str) -> None:
        return None

    def error(self, message: str) -> None:
        return None


# ---------------------------------------------------------------------------
# 目录工具
# ---------------------------------------------------------------------------
def ensure_downloads_dir(download_dir: str | Path | None = None) -> Path:
    """Resolve, create, and verify a user-selected download directory."""
    if download_dir is None or (
        isinstance(download_dir, str) and not download_dir.strip()
    ):
        target = DOWNLOADS_DIR
    elif not isinstance(download_dir, (str, os.PathLike)):
        raise ValueError("下载目录必须是路径字符串")
    else:
        raw = os.path.expandvars(str(download_dir).strip())
        if "\x00" in raw:
            raise ValueError("下载目录包含无效字符")
        if os.name != "nt" and re.match(r"^[A-Za-z]:[\\/]", raw):
            raise ValueError("当前系统不能使用 Windows 盘符路径")
        path = Path(raw).expanduser()
        target = path if path.is_absolute() else PROJECT_DIR / path

    try:
        target = target.resolve(strict=False)
        target.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ValueError(f"无法创建下载目录: {target}") from error
    if not target.is_dir():
        raise ValueError(f"下载位置不是文件夹: {target}")

    probe = target / f".__mvd_write_test_{uuid.uuid4().hex}.tmp"
    try:
        with probe.open("x", encoding="utf-8") as handle:
            handle.write("ok")
        probe.unlink()
    except OSError as error:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
        raise ValueError(f"下载目录不可写: {target}") from error
    return target


_PREPARED_OUTPUT_DIR_CAPABILITY = object()


class _PreparedOutputDir(str):
    """A private capability created only after full directory validation."""

    def __new__(cls, path: Path, capability: object):
        prepared = super().__new__(cls, str(path))
        prepared.path = path
        prepared.capability = capability
        return prepared



def _prepare_output_dir(download_dir: str | Path | None) -> _PreparedOutputDir:
    """Fully validate a batch directory and create its private capability."""
    return _PreparedOutputDir(
        ensure_downloads_dir(download_dir),
        _PREPARED_OUTPUT_DIR_CAPABILITY,
    )


def _prepared_output_dir(prepared: object) -> Path:
    """Read a previously validated directory without repeating its write probe."""
    if not isinstance(prepared, _PreparedOutputDir) or (
        prepared.capability is not _PREPARED_OUTPUT_DIR_CAPABILITY
    ):
        raise ValueError("已验证下载目录必须由内部批次准备")
    if not prepared.path.is_absolute() or not prepared.path.is_dir():
        raise ValueError(f"下载位置不是文件夹: {prepared.path}")
    return prepared.path


# ---------------------------------------------------------------------------
# 链接识别与校验
# ---------------------------------------------------------------------------
def normalize_url(url: str) -> str:
    """提取输入中的首个 HTTP(S) URL，清理末尾标点并补全协议。"""
    value = url.strip()
    match = SHARE_URL_RE.search(value)
    normalized = match.group(0) if match else value
    normalized = normalized.rstrip(TRAILING_URL_PUNCTUATION)
    if normalized and not re.match(r"^https?://", normalized, re.IGNORECASE):
        normalized = f"https://{normalized}"
    return normalized


def _detect_normalized_platform(normalized: str) -> Optional[str]:
    """识别已标准化链接的平台；无法识别时返回 None。"""
    if not normalized:
        return None

    try:
        parsed = urlparse(normalized)
    except ValueError:
        return None

    if parsed.scheme not in {"http", "https"}:
        return None

    host = (parsed.hostname or "").lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    # -- YouTube --
    youtube_hosts = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
    }
    if host in youtube_hosts:
        if parsed.path == "/watch" and parse_qs(parsed.query).get("v"):
            return YOUTUBE
        if len(path_parts) >= 2 and path_parts[0] in {"shorts", "embed", "live"}:
            return YOUTUBE

    if host in {"youtu.be", "www.youtu.be"} and path_parts:
        return YOUTUBE

    # -- Instagram --
    instagram_hosts = {
        "instagram.com",
        "www.instagram.com",
        "m.instagram.com",
    }
    if (
        host in instagram_hosts
        and len(path_parts) >= 2
        and path_parts[0] in {"p", "reel", "reels", "tv", "stories"}
    ):
        return INSTAGRAM

    # -- Bilibili --
    bilibili_hosts = {
        "bilibili.com",
        "www.bilibili.com",
        "m.bilibili.com",
    }
    if (
        host in bilibili_hosts
        and len(path_parts) >= 2
        and path_parts[0] == "video"
        and re.fullmatch(
            r"(?:BV[0-9A-Za-z]+|av\d+)",
            path_parts[1],
            re.IGNORECASE,
        )
    ):
        return BILIBILI

    if host in {"b23.tv", "www.b23.tv"} and path_parts:
        return BILIBILI

    return None


def detect_platform(url: str) -> Optional[str]:
    """识别合法视频链接的平台；无法识别时返回 None。"""
    return _detect_normalized_platform(normalize_url(url))


def detect_collection_platform(url: str) -> Optional[str]:
    """识别当前项目明确支持展开的播放列表、合集或多条目链接。"""
    normalized = normalize_url(url)
    try:
        parsed = urlparse(normalized)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None

    host = (parsed.hostname or "").lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)
    youtube_hosts = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
    }
    if host in youtube_hosts and (
        parsed.path == "/playlist" or bool(query.get("list"))
    ):
        return YOUTUBE

    bilibili_hosts = {
        "bilibili.com",
        "www.bilibili.com",
        "m.bilibili.com",
    }
    if host in bilibili_hosts and path_parts:
        if path_parts[0] in {"video", "medialist", "list"}:
            return BILIBILI
    if (
        host == "space.bilibili.com"
        and len(path_parts) >= 3
        and path_parts[0].isdigit()
        and path_parts[1] == "lists"
    ):
        return BILIBILI
    if host in {"b23.tv", "www.b23.tv"} and path_parts:
        return BILIBILI

    instagram_hosts = {
        "instagram.com",
        "www.instagram.com",
        "m.instagram.com",
    }
    if (
        host in instagram_hosts
        and len(path_parts) >= 2
        and path_parts[0] in {"p", "reel", "reels", "tv"}
    ):
        return INSTAGRAM
    return None


def is_valid_youtube_url(url: str) -> bool:
    """判断链接是否为支持的 YouTube 视频链接。"""
    return detect_platform(url) == YOUTUBE


def is_valid_instagram_url(url: str) -> bool:
    """判断链接是否为支持的 Instagram 视频链接。"""
    return detect_platform(url) == INSTAGRAM


def is_valid_bilibili_url(url: str) -> bool:
    """判断链接是否为支持的 Bilibili 单视频或短链接。"""
    return detect_platform(url) == BILIBILI


def make_task(url: str) -> Optional[VideoTask]:
    """将用户输入转换为下载任务。"""
    normalized = normalize_url(url)
    platform = _detect_normalized_platform(normalized)
    if platform is None:
        return None
    return platform, normalized


# ---------------------------------------------------------------------------
# Cookie 查找
# ---------------------------------------------------------------------------
def find_cookie_file(platform: str) -> Optional[Path]:
    """优先使用平台专用 Cookie，随后使用通用 cookies.txt。"""
    candidates = [
        PROJECT_DIR / f"{platform}_cookies.txt",
        PROJECT_DIR / "cookies.txt",
    ]
    return next((path for path in candidates if path.is_file()), None)


def _find_cookie_file(platform: str) -> Optional[Path]:
    """保留内部兼容入口。"""
    return find_cookie_file(platform)


def platform_http_headers(platform: str) -> dict[str, str]:
    """返回元数据提取与下载共用的平台安全请求头。"""
    if platform != INSTAGRAM:
        return {}
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }


# ---------------------------------------------------------------------------
# 进度回调
# ---------------------------------------------------------------------------
def _strip_ansi(value: object) -> str:
    """删除显示文本中的终端控制序列。"""
    return ANSI_ESCAPE_RE.sub("", str(value or "")).strip()


def _format_download_speed(speed: object) -> tuple[float | None, str]:
    """将 yt-dlp 的 bytes/s 速度转换为 MB/s 文本。"""
    try:
        speed_value = float(speed)
    except (TypeError, ValueError):
        return None, "计算中"

    if speed_value <= 0:
        return None, "计算中"

    speed_mbps = round(speed_value / (1024 * 1024), 2)
    return speed_mbps, f"{speed_mbps:.2f} MB/s"


def _format_eta(eta: object) -> str:
    """将 yt-dlp 的秒数 ETA 转成 MM:SS 或 HH:MM:SS。"""
    try:
        seconds = int(float(eta))
    except (TypeError, ValueError):
        return "计算中"

    if seconds < 0:
        return "计算中"

    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _format_size_bytes(value: object) -> str:
    try:
        size = float(value)
    except (TypeError, ValueError):
        return ""
    if size <= 0:
        return ""
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    precision = 0 if unit_index == 0 else 2
    return f"{size:.{precision}f} {units[unit_index]}"


def _progress_total_size(data: dict) -> tuple[int | None, bool]:
    """Return selected transfer size and whether it is only an estimate."""
    info = data.get("info_dict")
    if isinstance(info, dict):
        requested = info.get("requested_formats")
        if isinstance(requested, list) and requested:
            total = 0
            estimated = False
            for fmt in requested:
                if not isinstance(fmt, dict):
                    total = 0
                    break
                size = fmt.get("filesize")
                if not isinstance(size, (int, float)) or size <= 0:
                    size = fmt.get("filesize_approx")
                    estimated = True
                if not isinstance(size, (int, float)) or size <= 0:
                    total = 0
                    break
                total += int(size)
            if total > 0:
                return total, estimated

    exact = data.get("total_bytes")
    if isinstance(exact, (int, float)) and exact > 0:
        return int(exact), False
    estimate = data.get("total_bytes_estimate")
    if isinstance(estimate, (int, float)) and estimate > 0:
        return int(estimate), True

    if isinstance(info, dict):
        exact = info.get("filesize")
        if isinstance(exact, (int, float)) and exact > 0:
            return int(exact), False
        estimate = info.get("filesize_approx")
        if isinstance(estimate, (int, float)) and estimate > 0:
            return int(estimate), True
    return None, False


def _extract_progress_snapshot(data: dict) -> dict[str, object]:
    """提取前端任务卡需要展示的下载进度字段。"""
    speed_mbps, speed_text = _format_download_speed(data.get("speed"))
    percent_text = _strip_ansi(data.get("_percent_str")) or "计算中"
    total_size_bytes, total_size_is_estimate = _progress_total_size(data)

    return {
        "percent_text": percent_text,
        "speed_mbps": speed_mbps,
        "speed_text": speed_text,
        "eta_text": _format_eta(data.get("eta")),
        "total_size_bytes": total_size_bytes,
        "total_size_text": _format_size_bytes(total_size_bytes),
        "total_size_is_estimate": total_size_is_estimate,
    }


def _make_progress_hook(
    index: int,
    total: int,
    progress_callback: YtdlpProgressCallback = None,
    cancel_token: CancellationToken | None = None,
    media_type: str = VIDEO,
    audio_format: str = MP3,
):
    """创建带任务序号的 yt-dlp 进度回调（命令行模式）。"""

    def _progress_hook(data: dict) -> None:
        if cancel_token:
            cancel_token.raise_if_cancelled()
        status = data.get("status")
        if status == "downloading":
            snapshot = _extract_progress_snapshot(data)
            if progress_callback:
                progress_callback("progress", snapshot)

            print(
                f"  [{index}/{total}] ⏳ 下载中... {snapshot['percent_text']}  "
                f"速度: {snapshot['speed_text']}  剩余时间: {snapshot['eta_text']}"
                + (
                    f"  {'预计总大小' if snapshot['total_size_is_estimate'] else '总大小'}: "
                    f"{snapshot['total_size_text']}"
                    if snapshot["total_size_text"]
                    else "  总大小: 计算中"
                )
            )
        elif status == "finished":
            payload = _postprocessing_preparation(media_type, audio_format)
            if progress_callback:
                progress_callback("postprocessing", payload)
            print(
                f"\n  [{index}/{total}] ✅ 数据下载完成。"
                f"{payload['stage_text']}"
            )
            print(f"  [{index}/{total}] ℹ️  {payload['detail_text']}")

    return _progress_hook


def _make_cancel_hook(cancel_token: CancellationToken):
    def _cancel_hook(data: dict) -> None:
        if data.get("status") != "finished":
            cancel_token.raise_if_cancelled()

    return _cancel_hook


def _postprocessing_preparation(
    media_type: str,
    audio_format: str,
) -> dict[str, object]:
    if media_type != AUDIO:
        return {
            "stage": "preparing",
            "stage_text": "正在准备合并音视频并整理最终文件。",
            "detail_text": "高分辨率或长视频可能需要一些时间，界面保持此状态属正常现象。",
        }
    if audio_format == MP3:
        return {
            "stage": "preparing",
            "stage_text": "正在准备将完整音轨转码为 MP3 V0。",
            "detail_text": "随后还会写入元数据与封面；长音频可能需要数十秒至数分钟。",
        }
    if audio_format == WAV:
        stage_text = "正在准备将完整音轨解码为 WAV。"
    elif audio_format == FLAC:
        stage_text = "正在准备提取 FLAC 音轨。"
    else:
        stage_text = "正在准备整理原始音轨。"
    return {
        "stage": "preparing",
        "stage_text": stage_text,
        "detail_text": "随后还会写入元数据与封面；长音频或大文件可能需要一些时间。",
    }


def _postprocessor_stage(
    postprocessor: object,
    media_type: str,
    audio_format: str,
) -> tuple[str, str, str]:
    name = str(postprocessor or "")
    normalized = name.casefold()
    if "extractaudio" in normalized:
        if audio_format == MP3:
            return (
                "transcoding_audio",
                "正在将完整音轨转码为 MP3 V0…",
                "长音频需要完整解码并重新编码，可能持续数十秒至数分钟。",
            )
        if audio_format == WAV:
            return (
                "decoding_audio",
                "正在将完整音轨解码为 WAV…",
                "长音频需要完整解码，期间没有下载进度属于正常现象。",
            )
        return (
            "extracting_audio",
            "正在提取并整理音轨…",
            "大文件需要读取并写入完整音轨，请耐心等待。",
        )
    if "embedthumbnail" in normalized:
        return (
            "embedding_thumbnail",
            "正在嵌入封面…",
            "程序正在把封面写入最终媒体文件。",
        )
    if "metadata" in normalized:
        return (
            "writing_metadata",
            "正在写入媒体信息…",
            "程序正在保存标题、作者和其他媒体标签。",
        )
    if "merger" in normalized:
        return (
            "merging_streams",
            "正在合并视频与音频…",
            "高分辨率或长视频需要读取并写入完整媒体流。",
        )
    if "remux" in normalized:
        return (
            "remuxing_video",
            "正在整理视频封装…",
            "程序正在生成兼容性更好的最终视频文件。",
        )
    if "movefiles" in normalized:
        return (
            "finalizing",
            "正在整理最终文件…",
            "处理即将完成，程序正在确认文件名与保存位置。",
        )
    return (
        "postprocessing",
        "正在处理媒体文件…",
        "程序仍在正常工作，请保持窗口打开。",
    )


def _make_postprocessor_status_hook(
    index: int,
    total: int,
    progress_callback: YtdlpProgressCallback = None,
    media_type: str = VIDEO,
    audio_format: str = MP3,
):
    def _status_hook(data: dict) -> None:
        if data.get("status") != "started":
            return
        stage, stage_text, detail_text = _postprocessor_stage(
            data.get("postprocessor"),
            media_type,
            audio_format,
        )
        payload = {
            "stage": stage,
            "stage_text": stage_text,
            "detail_text": detail_text,
        }
        if progress_callback:
            progress_callback("postprocessing", payload)
        print(f"  [{index}/{total}] ⚙️  {stage_text}")
        print(f"  [{index}/{total}] ℹ️  {detail_text}")

    return _status_hook


def _validate_output_version(output_version: int) -> None:
    if (
        isinstance(output_version, bool)
        or not isinstance(output_version, int)
        or output_version < 1
    ):
        raise ValueError("输出版本必须是大于等于 1 的整数")


def _output_template(
    platform: str,
    output_dir: Path,
    output_version: int,
) -> str:
    suffix = "" if output_version == 1 else f" ({output_version})"
    name = (
        f"%(title)s [%(id)s]{suffix}.%(ext)s"
        if platform in {INSTAGRAM, BILIBILI}
        else f"%(title)s{suffix}.%(ext)s"
    )
    return str(output_dir / name)


def _attempt_output_template(
    platform: str,
    output_dir: Path,
    attempt_workspace: Path,
) -> str:
    """Use an attempt-unique working name before atomic final claiming."""
    base = (
        "%(title)s [%(id)s]"
        if platform in {INSTAGRAM, BILIBILI}
        else "%(title)s"
    )
    return str(
        output_dir
        / f"{base} [.__mvd_{attempt_workspace.name}].%(ext)s"
    )


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
        node_path = shutil.which("node")
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
                "postprocessors": [
                    {
                        "key": "FFmpegVideoRemuxer",
                        "preferedformat": "mp4",
                    }
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


# ---------------------------------------------------------------------------
# 音频质量与文件路径
# ---------------------------------------------------------------------------
def _selected_audio_info(info: dict) -> dict:
    requested = info.get("requested_formats")
    if isinstance(requested, list):
        for candidate in requested:
            if (
                isinstance(candidate, dict)
                and candidate.get("acodec") not in {None, "none"}
            ):
                return candidate
    return info


def _display_audio_codec(value: object) -> str | None:
    codec = str(value or "").lower()
    if codec.startswith("flac"):
        return "FLAC"
    if codec.startswith(("aac", "mp4a")):
        return "AAC"
    if "opus" in codec:
        return "Opus"
    if codec.startswith("mp3"):
        return "MP3"
    return codec.upper() or None


def _audio_output_profile(info: dict, requested: str) -> AudioOutputProfile:
    if requested not in AUDIO_FORMATS:
        raise ValueError(f"不支持的音频格式: {requested}")
    selected = _selected_audio_info(info)
    source_acodec = _display_audio_codec(selected.get("acodec"))
    raw_bitrate = selected.get("abr") or selected.get("tbr")
    source_abr_kbps = (
        round(raw_bitrate)
        if isinstance(raw_bitrate, (int, float)) and raw_bitrate > 0
        else None
    )
    source_ext = str(selected.get("ext") or "").lower()
    if requested == FLAC:
        used = FLAC if source_acodec == "FLAC" else MP3
        output_ext = FLAC if used == FLAC else MP3
    elif requested == SOURCE:
        used = SOURCE
        output_ext = source_ext or "mka"
    elif requested == WAV:
        used = WAV
        output_ext = WAV
    else:
        used = MP3
        output_ext = MP3
    cover_embedded = output_ext in {
        "flac",
        "m4a",
        "mp3",
        "mp4",
        "ogg",
        "opus",
    }
    return AudioOutputProfile(
        requested=requested,
        used=used,
        fallback=requested == FLAC and used == MP3,
        source_acodec=source_acodec,
        source_abr_kbps=source_abr_kbps,
        output_ext=output_ext,
        cover_embedded=cover_embedded,
    )


def _audio_quality_label(profile: AudioOutputProfile) -> str:
    if profile.used == FLAC:
        parts = ["FLAC Lossless"]
    elif profile.used == SOURCE:
        parts = [
            f"Source {profile.source_acodec or profile.output_ext.upper()}"
        ]
    elif profile.used == WAV:
        parts = ["WAV PCM"]
    else:
        parts = ["MP3 V0"]
    if profile.used == FLAC:
        if profile.source_abr_kbps:
            parts.append(f"{profile.source_abr_kbps}kbps")
    elif profile.used == SOURCE:
        if profile.source_abr_kbps:
            parts.append(f"{profile.source_abr_kbps}kbps")
    elif profile.source_acodec:
        source = f"源{profile.source_acodec}"
        if profile.source_abr_kbps:
            source += f" {profile.source_abr_kbps}kbps"
        parts.append(source)
    return " · ".join(parts)


def _audio_postprocessors(
    profile: AudioOutputProfile,
) -> list[dict[str, object]]:
    preferred_codec = {
        MP3: MP3,
        FLAC: FLAC,
        SOURCE: "best",
        WAV: WAV,
    }[profile.used]
    extractor: dict[str, object] = {
        "key": "FFmpegExtractAudio",
        "preferredcodec": preferred_codec,
    }
    if profile.used == MP3:
        extractor["preferredquality"] = "0"
    postprocessors: list[dict[str, object]] = [
        extractor,
        {
            "key": "FFmpegMetadata",
            "add_metadata": True,
            "add_chapters": False,
            "add_infojson": False,
        },
    ]
    if profile.cover_embedded:
        postprocessors.append(
            {
                "key": "EmbedThumbnail",
                "already_have_thumbnail": False,
            }
        )
    return postprocessors


def _audio_format_name(profile: AudioOutputProfile) -> str:
    if profile.used == FLAC:
        return "FLAC"
    if profile.used == SOURCE:
        return f"SOURCE {profile.output_ext.upper()}"
    if profile.used == WAV:
        return "WAV PCM"
    return "MP3 V0"


def _profile_for_output_path(
    profile: AudioOutputProfile,
    filepath: Path,
) -> AudioOutputProfile:
    """Report the container that yt-dlp/FFmpeg actually produced."""
    if profile.used != SOURCE:
        return profile
    actual_ext = filepath.suffix.lstrip(".").lower() or profile.output_ext
    return replace(
        profile,
        output_ext=actual_ext,
        cover_embedded=actual_ext in {
            "flac",
            "m4a",
            "mp3",
            "mp4",
            "ogg",
            "opus",
        },
    )


def _ensure_source_copy_supported(
    info: dict,
    profile: AudioOutputProfile,
) -> None:
    """Reject source outputs that yt-dlp would silently transcode to MP3."""
    if profile.used != SOURCE:
        return
    selected = _selected_audio_info(info)
    codec = str(selected.get("acodec") or "").lower()
    supported = (
        "aac",
        "alac",
        "flac",
        "mp3",
        "mp4a",
        "opus",
        "vorbis",
    )
    if not codec.startswith(supported):
        raise DownloadFailure(
            classify_download_error(
                ValueError(
                    f"requested format cannot be copied without transcoding: {codec or 'unknown'}"
                )
            )
        )


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
    return _claim_final_output_with_version(
        filepath,
        final_stem,
        output_version,
    )[0]


def _claim_final_output_with_version(
    filepath: Path,
    final_stem: str,
    output_version: int,
) -> tuple[Path, int]:
    """Atomically claim a no-overwrite final path in the same directory."""
    _validate_output_version(output_version)
    version = output_version
    while True:
        suffix = "" if version == 1 else f" ({version})"
        target = filepath.with_name(f"{final_stem}{suffix}{filepath.suffix}")
        try:
            os.link(filepath, target)
        except FileExistsError:
            version += 1
            continue
        filepath.unlink()
        return target, version


def _finalize_video_output(
    filepath: Path,
    output_version: int = 1,
) -> Path:
    return _finalize_video_output_with_version(filepath, output_version)[0]


def _finalize_video_output_with_version(
    filepath: Path,
    output_version: int = 1,
) -> tuple[Path, int]:
    """Remove the private marker and atomically reserve the visible filename."""
    final_stem = ATTEMPT_OUTPUT_MARKER_RE.sub("", filepath.stem)
    if final_stem == filepath.stem:
        return filepath, output_version
    return _claim_final_output_with_version(
        filepath,
        final_stem,
        output_version,
    )


def _audio_output_version(filepath: Path, requested: int) -> int:
    """Read the version suffix that this module adds after the quality label."""
    match = re.search(r"\[[^\]]+\] \((\d+)\)$", filepath.stem)
    return max(requested, int(match.group(1))) if match else requested


def _resolve_output_path(
    ydl,
    info: dict,
    output_dir: Path,
    media_type: str = VIDEO,
    audio_format: str = MP3,
    audio_profile: AudioOutputProfile | None = None,
    audio_output_ext: str | None = None,
) -> Path:
    """根据 yt-dlp 的输出信息定位后处理后的实际文件。"""
    if audio_format not in AUDIO_FORMATS:
        raise ValueError(f"不支持的音频格式: {audio_format}")
    prepared = Path(ydl.prepare_filename(info))
    output_ext = (
        audio_output_ext
        or (audio_profile.output_ext if audio_profile is not None else None)
        or audio_format
    )
    output_suffix = f".{output_ext}" if media_type == AUDIO else ".mp4"
    candidates = [prepared.with_suffix(output_suffix), prepared]

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    matches = sorted(
        output_dir.glob(f"{prepared.stem}.*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else prepared.with_suffix(output_suffix)


def _format_filesize(filepath: Path, info: dict) -> str:
    """优先使用磁盘上的最终文件大小。"""
    if filepath.is_file():
        size = filepath.stat().st_size
    else:
        size = info.get("filesize_approx") or info.get("filesize")
    return f"{size / (1024 * 1024):.2f} MB" if size else "未知（请查看文件）"


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
    """Create a private temporary directory owned by one download attempt."""
    root = output_dir / ".attempts"
    root.mkdir(parents=True, exist_ok=True)
    workspace = root / uuid.uuid4().hex
    workspace.mkdir()
    return workspace


def _cleanup_attempt_workspace(workspace: Path) -> None:
    """Delete only a workspace created for one attempt."""
    workspace = Path(workspace)
    if workspace.parent.name != ".attempts":
        raise ValueError("拒绝清理非任务临时目录")
    shutil.rmtree(workspace, ignore_errors=True)
    try:
        workspace.parent.rmdir()
    except OSError:
        pass


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
                "cover_embedded": audio_profile.cover_embedded,
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
            if audio_profile:
                audio_profile = _profile_for_output_path(audio_profile, filepath)
                if output_version == 1:
                    filepath = _rename_audio_output(filepath, audio_profile)
                else:
                    filepath = _rename_audio_output(
                        filepath,
                        audio_profile,
                        output_version=output_version,
                    )
                output_version_actual = _audio_output_version(
                    filepath,
                    output_version,
                )
            else:
                filepath, output_version_actual = (
                    _finalize_video_output_with_version(
                        filepath,
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
            audio_profile = _profile_for_output_path(audio_profile, filepath)
            if output_version == 1:
                filepath = _rename_audio_output(filepath, audio_profile)
            else:
                filepath = _rename_audio_output(
                    filepath,
                    audio_profile,
                    output_version=output_version,
                )
            output_version_actual = _audio_output_version(
                filepath,
                output_version,
            )
            result = {
                "platform": platform_name,
                "title": info.get("title", "未知标题"),
                "filepath": str(filepath),
                "filesize": _format_filesize(filepath, info),
                "media_type": media_type,
                "speed_mode_requested": speed_mode,
                "speed_mode_used": STANDARD,
                "turbo_fallback": False,
                "cdn_host": "未知",
                "http_chunk_size": 0,
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
                "cover_embedded": audio_profile.cover_embedded,
                "source_acodec": audio_profile.source_acodec or "未知",
                "source_abr_kbps": (
                    audio_profile.source_abr_kbps or "未知"
                ),
                "output_version_actual": output_version_actual,
            }
            return result

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
            filepath, output_version_actual = (
                _finalize_video_output_with_version(
                    filepath,
                    output_version,
                )
            )
            resolution = info.get("resolution") or (
                f"{info.get('width')}x{info.get('height')}"
                if info.get("width") and info.get("height")
                else "未知"
            )

            result = {
                "platform": platform_name,
                "title": info.get("title", "未知标题"),
                "filepath": str(filepath),
                "filesize": _format_filesize(filepath, info),
                "media_type": media_type,
                "speed_mode_requested": speed_mode,
                "speed_mode_used": STANDARD,
                "turbo_fallback": False,
                "cdn_host": "未知",
                "http_chunk_size": 0,
                "output_version_actual": output_version_actual,
            }
            result.update(
                {
                    "resolution": resolution,
                    "fps": info.get("fps") or "未知",
                    "vcodec": info.get("vcodec") or "未知",
                    "acodec": info.get("acodec") or "未知",
                }
            )
            return result

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
    output_dir = _prepare_output_dir(output_dir)

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
