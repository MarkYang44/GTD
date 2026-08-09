"""Bilibili 专用 CDN 候选提取与下载加速策略。"""

from urllib.parse import urlparse

from yt_dlp.extractor.bilibili import BiliBiliIE as YtdlpBiliBiliIE


CDN_CANDIDATES_FIELD = "_bilibili_cdn_candidates"
MAX_CDN_HOSTS = 4


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


def apply_cdn_host(info: dict, host: str | None) -> bool:
    """把每条所选流切换到同一候选主机；缺少候选的流保持原样。"""
    if not host:
        return False

    formats = selected_formats(info)
    changed = False
    for fmt in formats:
        selected = next(
            (url for url in _format_candidates(fmt) if _host(url) == host),
            None,
        )
        if selected and fmt.get("url") != selected:
            fmt["url"] = selected
            changed = True

    if "requested_formats" not in info and formats:
        info["url"] = formats[0]["url"]
    return changed
