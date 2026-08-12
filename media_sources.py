"""Platform recognition, share-text parsing, and cookie lookup helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse


PROJECT_DIR = Path(__file__).resolve().parent

YOUTUBE = "youtube"
INSTAGRAM = "instagram"
BILIBILI = "bilibili"
PLATFORM_NAMES = {
    YOUTUBE: "YouTube",
    INSTAGRAM: "Instagram",
    BILIBILI: "Bilibili",
}
SHARE_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
TRAILING_URL_PUNCTUATION = "】）》」』〕〉)]}>\"'“”‘’,.!?;:，。！？；："

VideoTask = tuple[str, str]


def normalize_url(url: str) -> str:
    """Extract the first HTTP(S) URL and remove trailing share punctuation."""
    value = url.strip()
    match = SHARE_URL_RE.search(value)
    normalized = match.group(0) if match else value
    normalized = normalized.rstrip(TRAILING_URL_PUNCTUATION)
    if normalized and not re.match(r"^https?://", normalized, re.IGNORECASE):
        normalized = f"https://{normalized}"
    return normalized


def _detect_normalized_platform(normalized: str) -> Optional[str]:
    """Recognize a normalized media URL, returning ``None`` when unsupported."""
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

    bilibili_hosts = {"bilibili.com", "www.bilibili.com", "m.bilibili.com"}
    if (
        host in bilibili_hosts
        and len(path_parts) >= 2
        and path_parts[0] == "video"
        and re.fullmatch(r"(?:BV[0-9A-Za-z]+|av\d+)", path_parts[1], re.IGNORECASE)
    ):
        return BILIBILI
    if host in {"b23.tv", "www.b23.tv"} and path_parts:
        return BILIBILI
    return None


def detect_platform(
    url: str,
    normalizer: Callable[[str], str] = normalize_url,
    detector: Callable[[str], Optional[str]] = _detect_normalized_platform,
) -> Optional[str]:
    """Recognize a supported single-media URL."""
    return detector(normalizer(url))


def detect_collection_platform(
    url: str,
    normalizer: Callable[[str], str] = normalize_url,
) -> Optional[str]:
    """Recognize a supported playlist, collection, or multipart URL."""
    normalized = normalizer(url)
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
    if host in youtube_hosts and (parsed.path == "/playlist" or bool(query.get("list"))):
        return YOUTUBE

    bilibili_hosts = {"bilibili.com", "www.bilibili.com", "m.bilibili.com"}
    if host in bilibili_hosts and path_parts and path_parts[0] in {"video", "medialist", "list"}:
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
    return detect_platform(url) == YOUTUBE


def is_valid_instagram_url(url: str) -> bool:
    return detect_platform(url) == INSTAGRAM


def is_valid_bilibili_url(url: str) -> bool:
    return detect_platform(url) == BILIBILI


def make_task(
    url: str,
    normalizer: Callable[[str], str] = normalize_url,
    detector: Callable[[str], Optional[str]] = _detect_normalized_platform,
) -> Optional[VideoTask]:
    """Convert a user input string into a normalized download task."""
    normalized = normalizer(url)
    platform = detector(normalized)
    return (platform, normalized) if platform is not None else None


def find_cookie_file(platform: str, project_dir: Path | None = None) -> Optional[Path]:
    """Prefer a platform cookie file, then fall back to ``cookies.txt``."""
    directory = PROJECT_DIR if project_dir is None else project_dir
    candidates = [directory / f"{platform}_cookies.txt", directory / "cookies.txt"]
    return next((path for path in candidates if path.is_file()), None)


def platform_http_headers(platform: str) -> dict[str, str]:
    """Return the platform-specific metadata/download request headers."""
    if platform != INSTAGRAM:
        return {}
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
