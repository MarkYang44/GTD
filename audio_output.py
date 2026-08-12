"""Audio format profiles and yt-dlp postprocessor choices."""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from download_errors import DownloadFailure, classify_download_error


MP3 = "mp3"
FLAC = "flac"
SOURCE = "source"
WAV = "wav"
AUDIO_FORMATS = {MP3, FLAC, SOURCE, WAV}


@dataclass(frozen=True)
class AudioOutputProfile:
    requested: str
    used: str
    fallback: bool
    source_acodec: str | None
    source_abr_kbps: int | None
    output_ext: str
    cover_embedded: bool


def selected_audio_info(info: dict) -> dict:
    requested = info.get("requested_formats")
    if isinstance(requested, list):
        for candidate in requested:
            if (
                isinstance(candidate, dict)
                and candidate.get("acodec") not in {None, "none"}
            ):
                return candidate
    return info


def display_audio_codec(value: object) -> str | None:
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


def audio_output_profile(
    info: dict,
    requested: str,
    *,
    selected_audio_info_fn: Callable[[dict], dict] = selected_audio_info,
    display_audio_codec_fn: Callable[[object], str | None] = display_audio_codec,
) -> AudioOutputProfile:
    if requested not in AUDIO_FORMATS:
        raise ValueError(f"不支持的音频格式: {requested}")
    selected = selected_audio_info_fn(info)
    source_acodec = display_audio_codec_fn(selected.get("acodec"))
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


def audio_quality_label(profile: AudioOutputProfile) -> str:
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


def audio_postprocessors(
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


def audio_format_name(profile: AudioOutputProfile) -> str:
    if profile.used == FLAC:
        return "FLAC"
    if profile.used == SOURCE:
        return f"SOURCE {profile.output_ext.upper()}"
    if profile.used == WAV:
        return "WAV PCM"
    return "MP3 V0"


def profile_for_output_path(
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


def ensure_source_copy_supported(
    info: dict,
    profile: AudioOutputProfile,
    *,
    selected_audio_info_fn: Callable[[dict], dict] = selected_audio_info,
    classify_download_error_fn: Callable[[Exception], object] = classify_download_error,
    download_failure_cls: type[DownloadFailure] = DownloadFailure,
) -> None:
    """Reject source outputs that yt-dlp would silently transcode to MP3."""
    if profile.used != SOURCE:
        return
    selected = selected_audio_info_fn(info)
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
        raise download_failure_cls(
            classify_download_error_fn(
                ValueError(
                    f"requested format cannot be copied without transcoding: {codec or 'unknown'}"
                )
            )
        )
