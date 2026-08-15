"""Inspect and embed source-preserving fallback cover art in final media files."""

from __future__ import annotations

import base64
import logging
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Sequence

from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis


logger = logging.getLogger(__name__)

SUPPORTED_COVER_EXTENSIONS = {
    ".flac",
    ".m4a",
    ".m4v",
    ".mov",
    ".mp3",
    ".mp4",
    ".ogg",
    ".opus",
}
_FALLBACK_NAMES = (
    "cover-01.png",
    "cover-02.jpg",
    "cover-03.jpg",
    "cover-04.png",
    "cover-05.png",
    "cover-06.jpg",
)
_FALLBACK_DIR = Path(__file__).resolve().parent / "assets" / "fallback_covers"


@dataclass(frozen=True)
class CoverOutcome:
    embedded: bool
    source: Literal["source", "fallback", "none"]
    fallback_name: str | None = None


def fallback_cover_paths() -> tuple[Path, ...]:
    """Return the bundled fallback assets in their stable display order."""
    return tuple(_FALLBACK_DIR / name for name in _FALLBACK_NAMES)


def _image_data(path: Path) -> tuple[bytes, str]:
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return data, "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return data, "image/jpeg"
    raise ValueError(f"unsupported fallback image: {path}")


def _ogg_picture_values(media: OggVorbis | OggOpus) -> list[str]:
    if media.tags is None:
        return []
    return list(media.tags.get("metadata_block_picture", []))


def _has_cover(filepath: Path) -> bool:
    extension = filepath.suffix.lower()
    if extension == ".mp3":
        media = MP3(filepath)
        return bool(media.tags and media.tags.getall("APIC"))
    if extension == ".flac":
        return bool(FLAC(filepath).pictures)
    if extension in {".m4a", ".m4v", ".mov", ".mp4"}:
        media = MP4(filepath)
        return bool(media.tags and media.tags.get("covr"))
    if extension == ".ogg":
        return bool(_ogg_picture_values(OggVorbis(filepath)))
    if extension == ".opus":
        return bool(_ogg_picture_values(OggOpus(filepath)))
    return False


def _picture_block(data: bytes, mime: str) -> Picture:
    picture = Picture()
    picture.type = 3
    picture.mime = mime
    picture.desc = "Cover"
    picture.data = data
    return picture


def _embed_cover(filepath: Path, cover_path: Path) -> None:
    extension = filepath.suffix.lower()
    data, mime = _image_data(cover_path)
    if extension == ".mp3":
        media = MP3(filepath)
        if media.tags is None:
            media.add_tags()
        media.tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=data))
        media.save(v2_version=3)
        return
    if extension == ".flac":
        media = FLAC(filepath)
        media.add_picture(_picture_block(data, mime))
        media.save()
        return
    if extension in {".m4a", ".m4v", ".mov", ".mp4"}:
        media = MP4(filepath)
        if media.tags is None:
            media.add_tags()
        image_format = (
            MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
        )
        media.tags["covr"] = [MP4Cover(data, imageformat=image_format)]
        media.save()
        return
    if extension in {".ogg", ".opus"}:
        media = OggVorbis(filepath) if extension == ".ogg" else OggOpus(filepath)
        if media.tags is None:
            media.add_tags()
        encoded = base64.b64encode(_picture_block(data, mime).write()).decode("ascii")
        media.tags["metadata_block_picture"] = [encoded]
        media.save()
        return
    raise ValueError(f"unsupported media container: {extension}")


def ensure_media_cover(
    filepath: Path,
    *,
    source_cover: Path | None = None,
    chooser: Callable[[Sequence[Path]], Path] | None = None,
) -> CoverOutcome:
    """Ensure a final media file has cover art without replacing source art."""
    media_path = Path(filepath)
    if media_path.suffix.lower() not in SUPPORTED_COVER_EXTENSIONS:
        return CoverOutcome(False, "none")
    try:
        if _has_cover(media_path):
            return CoverOutcome(True, "source")
    except Exception as exc:
        logger.warning("无法检查媒体文件 %s 的封面：%s", media_path, exc)
        return CoverOutcome(False, "none")

    if source_cover is not None:
        source_path = Path(source_cover)
        try:
            _embed_cover(media_path, source_path)
            if not _has_cover(media_path):
                raise ValueError("source cover verification failed")
            return CoverOutcome(True, "source")
        except Exception as exc:
            logger.warning(
                "无法为媒体文件 %s 使用源封面 %s：%s",
                media_path,
                source_path,
                exc,
            )

    try:
        cover_path = Path((chooser or secrets.choice)(fallback_cover_paths()))
        _embed_cover(media_path, cover_path)
        if not _has_cover(media_path):
            raise ValueError("cover verification failed")
        return CoverOutcome(True, "fallback", cover_path.name)
    except Exception as exc:  # Cover metadata must never invalidate a download.
        logger.warning("无法为媒体文件 %s 写入封面：%s", media_path, exc)
        return CoverOutcome(False, "none")
