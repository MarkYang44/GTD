"""Bilibili 专用 CDN 候选提取与下载加速策略。"""

import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from yt_dlp.extractor.bilibili import BiliBiliIE as YtdlpBiliBiliIE
from yt_dlp.networking.common import Request


CDN_CANDIDATES_FIELD = "_bilibili_cdn_candidates"
MAX_CDN_HOSTS = 4
BILIBILI_HTTP_CHUNK_SIZE = 10 * 1024 * 1024
BILIBILI_SMALL_CHUNK_SIZE = 4 * 1024 * 1024
BILIBILI_LARGE_FILE_THRESHOLD = 50 * 1024 * 1024
CDN_PROBE_BYTES = 512 * 1024
CDN_CACHE_TTL_SECONDS = 30 * 60
CDN_PROBE_TIMEOUT_SECONDS = 3
STANDARD = "standard"
TURBO = "turbo"
SPEED_MODES = {STANDARD, TURBO}
PROJECT_DIR = Path(__file__).resolve().parent
PROJECT_ARIA2_DIR = PROJECT_DIR / "tools" / "aria2"


@dataclass(frozen=True)
class CdnChoice:
    host: str | None
    http_chunk_size: int


@dataclass(frozen=True)
class AccelerationPlan:
    adaptive: bool
    cdn_host: str | None
    http_chunk_size: int


class CdnProbeCache:
    """带 TTL 和 single-flight 的线程安全 CDN 选择缓存。"""

    def __init__(
        self,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, ...], tuple[float, CdnChoice]] = {}
        self._in_flight: dict[tuple[str, ...], threading.Event] = {}

    def get_or_probe(
        self,
        hosts: tuple[str, ...],
        probe: Callable[[], CdnChoice],
    ) -> CdnChoice:
        key = tuple(sorted(set(hosts)))
        while True:
            with self._lock:
                now = self.clock()
                expired = [
                    entry_key
                    for entry_key, (expires_at, _) in self._entries.items()
                    if expires_at <= now
                ]
                for entry_key in expired:
                    self._entries.pop(entry_key, None)

                entry = self._entries.get(key)
                if entry:
                    return entry[1]

                event = self._in_flight.get(key)
                if event is None:
                    event = self._in_flight[key] = threading.Event()
                    owner = True
                else:
                    owner = False
            if owner:
                break
            event.wait()

        try:
            choice = probe()
            with self._lock:
                self._entries[key] = (
                    self.clock() + self.ttl_seconds,
                    choice,
                )
            return choice
        finally:
            with self._lock:
                self._in_flight.pop(key).set()


CDN_PROBE_CACHE = CdnProbeCache(CDN_CACHE_TTL_SECONDS)
_ARIA2C_PATH_UNSET = object()
_aria2c_path_cached: str | None | object = _ARIA2C_PATH_UNSET
_aria2c_path_lock = threading.Lock()


def _discover_aria2c_path() -> str | None:
    """Locate an explicit, project-local, PATH, or common package install."""
    executable_name = "aria2c.exe" if os.name == "nt" else "aria2c"
    candidates: list[str | Path | None] = [
        os.environ.get("MVD_ARIA2C_PATH"),
        os.environ.get("ARIA2C_PATH"),
        PROJECT_ARIA2_DIR / executable_name,
        shutil.which("aria2c"),
    ]
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        user_profile = os.environ.get("USERPROFILE")
        if local_app_data:
            winget_root = Path(local_app_data) / "Microsoft" / "WinGet"
            candidates.append(winget_root / "Links" / executable_name)
            packages_root = winget_root / "Packages"
            try:
                candidates.extend(
                    sorted(
                        packages_root.glob(
                            "aria2.aria2_*/aria2-*-win-*bit-*/aria2c.exe"
                        ),
                        reverse=True,
                    )
                )
            except OSError:
                pass
        if user_profile:
            candidates.append(
                Path(user_profile) / "scoop" / "shims" / executable_name
            )
    elif sys.platform == "darwin":
        candidates.extend(
            ("/opt/homebrew/bin/aria2c", "/usr/local/bin/aria2c")
        )

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path.resolve())
    return None


def aria2c_path(refresh: bool = False) -> str | None:
    """Return the process-cached aria2c path, refreshing only when requested."""
    global _aria2c_path_cached
    with _aria2c_path_lock:
        if refresh or _aria2c_path_cached is _ARIA2C_PATH_UNSET:
            _aria2c_path_cached = _discover_aria2c_path()
        return _aria2c_path_cached


def reset_aria2c_path_cache() -> None:
    """Clear cached executable discovery for tests and service reconfiguration."""
    global _aria2c_path_cached
    with _aria2c_path_lock:
        _aria2c_path_cached = _ARIA2C_PATH_UNSET


def effective_speed_mode(
    platform: str,
    requested: str,
    executable: str | None,
) -> str:
    if requested not in SPEED_MODES:
        raise ValueError(f"不支持的速度模式: {requested}")
    if platform == "bilibili" and requested == TURBO and executable:
        return TURBO
    return STANDARD


def configure_aria2(options: dict, executable: str) -> None:
    options["external_downloader"] = {"http": executable}
    options["external_downloader_args"] = {
        "aria2c": [
            "--max-connection-per-server=4",
            "--split=4",
            "--max-concurrent-downloads=4",
            "--min-split-size=1M",
        ],
    }


def _https_candidates(stream: dict) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("baseUrl", "base_url", "url"):
        value = stream.get(key)
        if isinstance(value, str):
            values.append(value)
            break

    for key in ("backupUrl", "backup_url", "backup_urls"):
        backups = stream.get(key)
        if isinstance(backups, str):
            values.append(backups)
        elif isinstance(backups, list):
            values.extend(value for value in backups if isinstance(value, str))

    result: list[str] = []
    for value in values:
        try:
            is_https = urlparse(value).scheme.lower() == "https"
        except ValueError:
            is_https = False
        if is_https and value not in result:
            result.append(value)
    return tuple(result)


def _dash_streams(play_info: dict) -> list[dict]:
    dash = play_info.get("dash")
    if not isinstance(dash, dict):
        raise TypeError("Bilibili dash data is not a mapping")

    streams: list[dict] = []
    for key in ("video", "audio"):
        values = dash.get(key) or []
        if isinstance(values, list):
            streams.extend(value for value in values if isinstance(value, dict))

    dolby = dash.get("dolby")
    if isinstance(dolby, dict):
        values = dolby.get("audio") or []
        if isinstance(values, list):
            streams.extend(value for value in values if isinstance(value, dict))

    flac = dash.get("flac")
    if isinstance(flac, dict) and isinstance(flac.get("audio"), dict):
        streams.append(flac["audio"])
    return streams


def enrich_bilibili_formats(play_info: dict, formats: list[dict]) -> list[dict]:
    """把同一媒体流的主 URL 和备用 URL 附加到 yt-dlp 格式字典。"""
    try:
        by_primary_url = {}
        for stream in _dash_streams(play_info):
            candidates = _https_candidates(stream)
            if candidates:
                by_primary_url[candidates[0]] = candidates
    except (AttributeError, TypeError, ValueError):
        return formats

    for fmt in formats:
        candidates = by_primary_url.get(fmt.get("url"))
        if candidates:
            fmt[CDN_CANDIDATES_FIELD] = candidates
    return formats


class BiliBiliIE(YtdlpBiliBiliIE):
    """实例级适配器：保留 yt-dlp 选择信息并补充备用 CDN。"""

    def extract_formats(self, play_info):
        formats = super().extract_formats(play_info)
        return enrich_bilibili_formats(play_info, formats)


def register_bilibili_extractor(ydl) -> None:
    """仅在当前 YoutubeDL 实例中覆盖 Bilibili 提取器。"""
    ydl.add_info_extractor(BiliBiliIE())


def selected_formats(info: dict) -> list[dict]:
    """返回 yt-dlp 已选中的视频/音频格式。"""
    requested = info.get("requested_formats")
    if isinstance(requested, list) and requested:
        return [fmt for fmt in requested if isinstance(fmt, dict)]
    return [info]


def selected_size(info: dict) -> int | None:
    """计算全部所选流大小；任一流大小未知时返回 None。"""
    total = 0
    for fmt in selected_formats(info):
        value = fmt.get("filesize") or fmt.get("filesize_approx")
        if not isinstance(value, (int, float)) or value <= 0:
            return None
        total += int(value)
    return total or None


def _host(url: object) -> str | None:
    if not isinstance(url, str):
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return None
    return parsed.hostname.lower()


def _format_candidates(fmt: dict) -> tuple[str, ...]:
    stored = fmt.get(CDN_CANDIDATES_FIELD)
    values = stored if isinstance(stored, (list, tuple)) else (fmt.get("url"),)
    return tuple(value for value in values if _host(value))


def candidate_hosts(info: dict) -> dict[str, str]:
    """按主 URL 优先顺序返回最多四个候选主机及代表 URL。"""
    result: dict[str, str] = {}
    formats = selected_formats(info)

    for fmt in formats:
        primary = fmt.get("url")
        host = _host(primary)
        if host and host not in result:
            result[host] = primary

    for fmt in formats:
        for url in _format_candidates(fmt):
            host = _host(url)
            if host and host not in result:
                result[host] = url
            if len(result) >= MAX_CDN_HOSTS:
                return result
    return result


def primary_host(info: dict) -> str | None:
    formats = selected_formats(info)
    return _host(formats[0].get("url")) if formats else None


def _candidate_for_host(fmt: dict, host: str) -> str | None:
    return next(
        (url for url in _format_candidates(fmt) if _host(url) == host),
        None,
    )


def needs_cdn_host_switch(info: dict, host: str | None) -> bool:
    """目标主机会改变任一已选流时返回 True。"""
    if not host:
        return False
    return any(
        (selected := _candidate_for_host(fmt, host)) is not None
        and fmt.get("url") != selected
        for fmt in selected_formats(info)
    )


def apply_cdn_host(info: dict, host: str | None) -> bool:
    """把每条所选流切换到同一候选主机；缺少候选的流保持原样。"""
    if not host:
        return False

    formats = selected_formats(info)
    changed = False
    for fmt in formats:
        selected = _candidate_for_host(fmt, host)
        if selected and fmt.get("url") != selected:
            fmt["url"] = selected
            changed = True

    if "requested_formats" not in info and formats:
        info["url"] = formats[0]["url"]
    return changed


def measure_range(
    ydl,
    url: str,
    size: int,
    start: int = 0,
    headers: dict | None = None,
) -> float | None:
    """读取一个经校验的 Range 样本并返回 bytes/s。"""
    request_headers = dict(headers or {})
    request_headers["Range"] = f"bytes={start}-{start + size - 1}"
    request = Request(
        url,
        headers=request_headers,
        extensions={"timeout": CDN_PROBE_TIMEOUT_SECONDS},
    )
    started = time.monotonic()
    try:
        with ydl.urlopen(request) as response:
            if getattr(response, "status", None) != 206:
                return None
            content_range = str(
                getattr(response, "headers", {}).get("Content-Range", "")
            )
            if not content_range.startswith("bytes "):
                return None
            payload = response.read(size)
    except Exception:
        return None

    elapsed = time.monotonic() - started
    if not payload or elapsed <= 0:
        return None
    return len(payload) / elapsed


def _probe_choice(ydl, info: dict, hosts: dict[str, str]) -> CdnChoice:
    headers = info.get("http_headers")
    headers = headers if isinstance(headers, dict) else None
    successful: dict[str, float] = {}
    for host, url in hosts.items():
        speed = measure_range(
            ydl,
            url,
            CDN_PROBE_BYTES,
            headers=headers,
        )
        if speed is not None:
            successful[host] = speed

    if not successful:
        return CdnChoice(primary_host(info), BILIBILI_HTTP_CHUNK_SIZE)

    fastest = max(successful, key=successful.get)
    url = hosts[fastest]
    small_speed = measure_range(
        ydl,
        url,
        BILIBILI_SMALL_CHUNK_SIZE,
        CDN_PROBE_BYTES,
        headers=headers,
    )
    normal_speed = measure_range(
        ydl,
        url,
        BILIBILI_HTTP_CHUNK_SIZE,
        CDN_PROBE_BYTES + BILIBILI_SMALL_CHUNK_SIZE,
        headers=headers,
    )
    chunk_size = (
        BILIBILI_SMALL_CHUNK_SIZE
        if (
            small_speed is not None
            and normal_speed is not None
            and small_speed > normal_speed
        )
        else BILIBILI_HTTP_CHUNK_SIZE
    )
    return CdnChoice(fastest, chunk_size)


def build_acceleration_plan(
    ydl,
    info: dict,
    cache: CdnProbeCache = CDN_PROBE_CACHE,
) -> AccelerationPlan:
    """按 50 MiB 阈值生成固定或自适应下载计划。"""
    size = selected_size(info)
    original_host = primary_host(info)
    if size is None or size <= BILIBILI_LARGE_FILE_THRESHOLD:
        return AccelerationPlan(
            False,
            original_host,
            BILIBILI_HTTP_CHUNK_SIZE,
        )

    hosts = candidate_hosts(info)
    if not hosts:
        return AccelerationPlan(
            False,
            original_host,
            BILIBILI_HTTP_CHUNK_SIZE,
        )

    choice = cache.get_or_probe(
        tuple(hosts),
        lambda: _probe_choice(ydl, info, hosts),
    )
    return AccelerationPlan(
        True,
        choice.host,
        choice.http_chunk_size,
    )
