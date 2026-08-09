"""Bilibili 专用 CDN 候选提取与下载加速策略。"""

from urllib.parse import urlparse

from yt_dlp.extractor.bilibili import BiliBiliIE as YtdlpBiliBiliIE


CDN_CANDIDATES_FIELD = "_bilibili_cdn_candidates"


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
