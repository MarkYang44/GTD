#!/usr/bin/env python3
"""
YouTube & Instagram 视频下载核心逻辑。

本模块提供链接识别、下载参数构建、yt-dlp 调用等通用功能。
main.py（命令行）和 app.py（Web 服务）均通过导入本模块复用下载能力。
"""

import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

import yt_dlp

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
PLATFORM_NAMES = {
    YOUTUBE: "YouTube",
    INSTAGRAM: "Instagram",
    BILIBILI: "Bilibili",
}
MAX_PARALLEL_DOWNLOADS = 3
MAX_PARALLEL_BILIBILI_DOWNLOADS = 2
BILIBILI_HTTP_CHUNK_SIZE = 10 * 1024 * 1024
ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
SHARE_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
TRAILING_URL_PUNCTUATION = "】）》」』〕〉)]}>\"',.!?;:，。！？；："

# 类型别名
VideoTask = tuple[str, str]          # (platform, normalized_url)
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


# ---------------------------------------------------------------------------
# 目录工具
# ---------------------------------------------------------------------------
def ensure_downloads_dir() -> Path:
    """确保 downloads 文件夹存在，返回其路径。"""
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return DOWNLOADS_DIR


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


def detect_platform(url: str) -> Optional[str]:
    """识别合法视频链接的平台；无法识别时返回 None。"""
    normalized = normalize_url(url)
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
    platform = detect_platform(normalized)
    if platform is None:
        return None
    return platform, normalized


# ---------------------------------------------------------------------------
# Cookie 查找
# ---------------------------------------------------------------------------
def _find_cookie_file(platform: str) -> Optional[Path]:
    """优先使用平台专用 Cookie，随后使用通用 cookies.txt。"""
    candidates = [
        PROJECT_DIR / f"{platform}_cookies.txt",
        PROJECT_DIR / "cookies.txt",
    ]
    return next((path for path in candidates if path.is_file()), None)


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


def _extract_progress_snapshot(data: dict) -> dict[str, object]:
    """提取前端任务卡需要展示的下载进度字段。"""
    speed_mbps, speed_text = _format_download_speed(data.get("speed"))
    percent_text = _strip_ansi(data.get("_percent_str")) or "计算中"

    return {
        "percent_text": percent_text,
        "speed_mbps": speed_mbps,
        "speed_text": speed_text,
        "eta_text": _format_eta(data.get("eta")),
    }


def _make_progress_hook(
    index: int,
    total: int,
    progress_callback: YtdlpProgressCallback = None,
):
    """创建带任务序号的 yt-dlp 进度回调（命令行模式）。"""

    def _progress_hook(data: dict) -> None:
        status = data.get("status")
        if status == "downloading":
            snapshot = _extract_progress_snapshot(data)
            if progress_callback:
                progress_callback("progress", snapshot)

            print(
                f"  [{index}/{total}] ⏳ 下载中... {snapshot['percent_text']}  "
                f"速度: {snapshot['speed_text']}  剩余时间: {snapshot['eta_text']}"
            )
        elif status == "finished":
            print(f"\n  [{index}/{total}] ✅ 数据下载完成，正在处理文件...")

    return _progress_hook


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
) -> dict:
    """生成公共配置，并追加平台专用配置。"""
    if media_type not in MEDIA_TYPES:
        raise ValueError(f"不支持的下载类型: {media_type}")

    options = {
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "progress_hooks": [_make_progress_hook(index, total, progress_callback)],
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
    }

    if platform == YOUTUBE:
        node_path = shutil.which("node")
        options["js_runtimes"] = {"node": {"path": node_path} if node_path else {}}
        options["remote_components"] = ["ejs:github"]
    elif platform == INSTAGRAM:
        options.update(
            {
                "outtmpl": str(output_dir / "%(title)s [%(id)s].%(ext)s"),
                "http_headers": {
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
                },
                "sleep_interval": 1,
                "max_sleep_interval": 3,
                "sleep_interval_requests": 1,
            }
        )
    elif platform == BILIBILI:
        options.update(
            {
                "outtmpl": str(output_dir / "%(title)s [%(id)s].%(ext)s"),
                "http_chunk_size": BILIBILI_HTTP_CHUNK_SIZE,
            }
        )

    if media_type == AUDIO:
        # 选择源站可获取的最高质量音轨，再以 FFmpeg 的最高 VBR 品质输出 MP3。
        options.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "0",
                    }
                ],
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

    return options


# ---------------------------------------------------------------------------
# 文件路径与大小
# ---------------------------------------------------------------------------
def _resolve_output_path(
    ydl,
    info: dict,
    output_dir: Path,
    media_type: str = VIDEO,
) -> Path:
    """根据 yt-dlp 的输出信息定位后处理后的实际文件。"""
    prepared = Path(ydl.prepare_filename(info))
    output_suffix = ".mp3" if media_type == AUDIO else ".mp4"
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
# 单视频下载
# ---------------------------------------------------------------------------
def download_video(
    url: str,
    index: int = 1,
    total: int = 1,
    platform: Optional[str] = None,
    progress_callback: YtdlpProgressCallback = None,
    media_type: str = VIDEO,
) -> Optional[DownloadResult]:
    """自动识别平台并使用 yt-dlp 下载单个视频。"""
    platform = platform or detect_platform(url)
    if platform is None:
        print(f"\n❌ 无法识别视频平台: {url}")
        return None

    output_dir = ensure_downloads_dir()
    options = _build_ydl_options(
        platform,
        output_dir,
        index,
        total,
        progress_callback=progress_callback,
        media_type=media_type,
    )
    platform_name = PLATFORM_NAMES[platform]
    media_name = "音频" if media_type == AUDIO else "视频"

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            print(f"\n{'─' * 56}")
            print(f"[{index}/{total}] [{platform_name}] 🔍 正在获取{media_name}信息: {url}\n")
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
            }
            if media_type == AUDIO:
                result.update({"format": "MP3", "acodec": "mp3"})
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

    except yt_dlp.utils.DownloadError as error:
        _handle_download_error(str(error), platform, media_type)
        return None
    except Exception as error:
        print(f"\n❌ 发生未知错误: {error}")
        return None


# ---------------------------------------------------------------------------
# 批量下载
# ---------------------------------------------------------------------------
def download_tasks(
    tasks: list[VideoTask],
    progress_callback: ProgressCallback = None,
    media_type: str = VIDEO,
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
        `video` 下载视频，`audio` 下载最高可用音质并转换为 MP3。
    """
    total = len(tasks)
    if not tasks:
        return []

    bilibili_slots = threading.BoundedSemaphore(
        MAX_PARALLEL_BILIBILI_DOWNLOADS
    )

    def _run_task(index_and_task):
        task_index, task = index_and_task
        platform, url = task

        def _relay_progress(event: str, data: dict[str, object]) -> None:
            if progress_callback:
                progress_callback(task_index, event, data)

        def _download_current_task():
            if progress_callback:
                progress_callback(
                    task_index,
                    "started",
                    {"url": url, "platform": platform},
                )
            return download_video(
                url,
                index=task_index + 1,
                total=total,
                platform=platform,
                progress_callback=_relay_progress if progress_callback else None,
                media_type=media_type,
            )

        try:
            if platform == BILIBILI:
                with bilibili_slots:
                    result = _download_current_task()
            else:
                result = _download_current_task()
        except Exception as error:
            print(f"\n❌ 任务 {task_index + 1} 发生未知错误: {error}")
            result = None

        if progress_callback:
            if result:
                progress_callback(task_index, "completed", result)
            else:
                progress_callback(task_index, "failed", {"error": "下载失败"})
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
