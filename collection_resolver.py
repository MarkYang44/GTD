"""Read-only preview expansion for playlists, collections, and multipart media."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass, replace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yt_dlp

from download_errors import DownloadFailure, classify_download_error
from downloader import (
    BILIBILI,
    INSTAGRAM,
    YOUTUBE,
    detect_collection_platform,
    detect_platform,
    find_cookie_file,
    normalize_url,
    platform_http_headers,
)


class CollectionResolveError(DownloadFailure):
    """A collection could not be safely expanded into a public preview."""


@dataclass(frozen=True)
class CollectionEntry:
    id: str
    title: str
    platform: str
    url: str | None
    position: int
    thumbnail: str | None
    selectable: bool
    unavailable_reason: str | None


@dataclass(frozen=True)
class CollectionPreview:
    id: str
    title: str
    platform: str
    entries: tuple[CollectionEntry, ...]
    is_single: bool
    requires_selection: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "preview_id": self.id,
            "title": self.title,
            "platform": self.platform,
            "is_single": self.is_single,
            "requires_selection": self.requires_selection,
            "entries": [asdict(entry) for entry in self.entries],
        }


def select_preview_entries(
    preview: CollectionPreview,
    entry_ids: list[str],
    limit: int = 100,
) -> list[CollectionEntry]:
    if not isinstance(entry_ids, list) or not all(
        isinstance(value, str) for value in entry_ids
    ):
        raise ValueError("条目选择格式无效")
    if not entry_ids:
        raise ValueError("请至少选择一个条目")
    if len(entry_ids) > limit:
        raise ValueError(f"一次最多选择 {limit} 个条目")
    if len(set(entry_ids)) != len(entry_ids):
        raise ValueError("不能重复选择同一条目")

    by_id = {entry.id: entry for entry in preview.entries}
    if any(entry_id not in by_id for entry_id in entry_ids):
        raise ValueError("所选条目不存在或预览已变化")
    selected = [by_id[entry_id] for entry_id in entry_ids]
    if any(not entry.selectable or not entry.url for entry in selected):
        raise ValueError("所选条目中包含不可下载内容")
    return selected


def _preview_options(platform: str) -> dict[str, object]:
    options: dict[str, object] = {
        "extract_flat": "in_playlist",
        "skip_download": True,
        "lazy_playlist": True,
        "noplaylist": False,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "extractor_retries": 3,
    }
    headers = platform_http_headers(platform)
    if headers:
        options["http_headers"] = headers
    cookie_file = find_cookie_file(platform)
    if cookie_file:
        options["cookiefile"] = str(cookie_file)
    return options


def _entry_url(
    entry: dict,
    platform: str,
    source_url: str,
    position: int,
    multipart: bool,
) -> str | None:
    raw_url = (
        entry.get("webpage_url")
        or entry.get("original_url")
        or entry.get("url")
    )
    if isinstance(raw_url, str) and raw_url.startswith(("http://", "https://")):
        resolved = raw_url
    elif platform == YOUTUBE and entry.get("id"):
        resolved = f"https://www.youtube.com/watch?v={entry['id']}"
    elif platform == BILIBILI and entry.get("bvid"):
        resolved = f"https://www.bilibili.com/video/{entry['bvid']}"
    elif multipart:
        resolved = source_url
    else:
        return None

    if platform == BILIBILI and multipart:
        parts = urlsplit(resolved)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["p"] = str(position)
        resolved = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )
    return normalize_url(resolved)


def _unavailable_reason(entry: dict) -> str | None:
    availability = str(entry.get("availability") or "").lower()
    if availability in {"private", "premium_only", "subscriber_only"}:
        return "内容不可访问"
    if entry.get("url") is None and not entry.get("webpage_url"):
        return "源站未提供可下载链接"
    return None


def _platform_for_url(normalized: str) -> str | None:
    return detect_collection_platform(normalized) or detect_platform(normalized)


def resolve_collection(
    text: str,
    ydl_factory=yt_dlp.YoutubeDL,
) -> CollectionPreview:
    normalized = normalize_url(text)
    platform = _platform_for_url(normalized)
    if platform not in {YOUTUBE, INSTAGRAM, BILIBILI}:
        raise CollectionResolveError(
            classify_download_error(
                ValueError("unsupported collection URL"),
                stage="collection",
            )
        )

    try:
        with ydl_factory(_preview_options(platform)) as ydl:
            info = ydl.extract_info(normalized, download=False)
    except Exception as error:
        raise CollectionResolveError(
            classify_download_error(error, platform, stage="collection")
        ) from error
    if not isinstance(info, dict):
        raise CollectionResolveError(
            classify_download_error(
                ValueError("extractor returned no metadata"),
                platform,
                stage="collection",
            )
        )

    raw_entries = info.get("entries")
    is_expanded = isinstance(raw_entries, (list, tuple)) or (
        raw_entries is not None and info.get("_type") in {"playlist", "multi_video"}
    )
    if is_expanded:
        entries_data = list(raw_entries or ())
    else:
        entries_data = [info]
    multipart = platform == BILIBILI and (
        info.get("_type") == "multi_video" or len(entries_data) > 1
    )

    entries: list[CollectionEntry] = []
    for position, raw_entry in enumerate(entries_data, start=1):
        entry = raw_entry if isinstance(raw_entry, dict) else {}
        url = _entry_url(entry, platform, normalized, position, multipart)
        unavailable_reason = _unavailable_reason(entry)
        selectable = bool(url) and unavailable_reason is None
        extractor_id = entry.get("id") or entry.get("display_id") or position
        entries.append(
            CollectionEntry(
                id=f"{position}:{extractor_id}",
                title=str(entry.get("title") or f"第 {position} 项"),
                platform=platform,
                url=url,
                position=position,
                thumbnail=(
                    str(entry["thumbnail"])
                    if entry.get("thumbnail")
                    else None
                ),
                selectable=selectable,
                unavailable_reason=unavailable_reason,
            )
        )

    is_single = not is_expanded and len(entries) == 1
    return CollectionPreview(
        id=uuid.uuid4().hex,
        title=str(info.get("title") or entries[0].title if entries else "未命名合集"),
        platform=platform,
        entries=tuple(entries),
        is_single=is_single,
        requires_selection=(not is_single or any(not entry.selectable for entry in entries)),
    )


def resolve_inputs(
    inputs: list[str],
    ydl_factory=yt_dlp.YoutubeDL,
) -> CollectionPreview:
    if not isinstance(inputs, list) or not inputs or not all(
        isinstance(value, str) and value.strip() for value in inputs
    ):
        raise ValueError("请输入至少一个有效链接")

    merged_entries: list[CollectionEntry] = []
    previews: list[CollectionPreview] = []
    for input_position, text in enumerate(inputs, start=1):
        preview = resolve_collection(text, ydl_factory=ydl_factory)
        previews.append(preview)
        for entry in preview.entries:
            merged_entries.append(
                replace(
                    entry,
                    id=f"{input_position}:{entry.id}",
                    position=len(merged_entries) + 1,
                )
            )

    platforms = {entry.platform for entry in merged_entries}
    platform = next(iter(platforms)) if len(platforms) == 1 else "mixed"
    is_single = (
        len(previews) == 1
        and previews[0].is_single
        and len(merged_entries) == 1
    )
    requires_selection = (
        not is_single
        or any(preview.requires_selection for preview in previews)
        or any(not entry.selectable for entry in merged_entries)
    )
    return CollectionPreview(
        id=uuid.uuid4().hex,
        title=(previews[0].title if is_single else f"下载预览（{len(merged_entries)} 项）"),
        platform=platform,
        entries=tuple(merged_entries),
        is_single=is_single,
        requires_selection=requires_selection,
    )


class PreviewStore:
    def __init__(self, ttl_seconds: int = 1800):
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._items: dict[str, tuple[float, CollectionPreview]] = {}

    def put(self, preview: CollectionPreview) -> str:
        with self._lock:
            self._items[preview.id] = (
                time.monotonic() + self.ttl_seconds,
                preview,
            )
        return preview.id

    def get(self, preview_id: str) -> CollectionPreview | None:
        self.prune()
        with self._lock:
            item = self._items.get(preview_id)
            return item[1] if item else None

    def prune(self) -> None:
        now = time.monotonic()
        with self._lock:
            expired = [
                key
                for key, (deadline, _) in self._items.items()
                if deadline <= now
            ]
            for key in expired:
                self._items.pop(key, None)
