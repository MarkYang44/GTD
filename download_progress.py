"""yt-dlp progress formatting and callback factories.

This module deliberately depends only on the small cancellation protocol below,
so progress reporting remains reusable without importing the download orchestrator.
"""

import re
from typing import Callable, Protocol


VIDEO = "video"
MP3 = "mp3"
ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
YtdlpProgressCallback = Callable[[str, dict[str, object]], None] | None


class CancellationProtocol(Protocol):
    def raise_if_cancelled(self) -> None: ...


def strip_ansi(value: object) -> str:
    """Remove terminal control sequences from display text."""
    return ANSI_ESCAPE_RE.sub("", str(value or "")).strip()


def format_download_speed(speed: object) -> tuple[float | None, str]:
    """Convert a yt-dlp bytes/s speed to an MB/s display string."""
    try:
        speed_value = float(speed)
    except (TypeError, ValueError):
        return None, "计算中"

    if speed_value <= 0:
        return None, "计算中"

    speed_mbps = round(speed_value / (1024 * 1024), 2)
    return speed_mbps, f"{speed_mbps:.2f} MB/s"


def format_eta(eta: object) -> str:
    """Convert yt-dlp ETA seconds to MM:SS or HH:MM:SS."""
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


def format_size_bytes(value: object) -> str:
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


def progress_total_size(data: dict) -> tuple[int | None, bool]:
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


def extract_progress_snapshot(
    data: dict,
    *,
    format_download_speed_fn: Callable[[object], tuple[float | None, str]] = format_download_speed,
    strip_ansi_fn: Callable[[object], str] = strip_ansi,
    progress_total_size_fn: Callable[[dict], tuple[int | None, bool]] = progress_total_size,
    format_eta_fn: Callable[[object], str] = format_eta,
    format_size_bytes_fn: Callable[[object], str] = format_size_bytes,
) -> dict[str, object]:
    """Extract the fields displayed by a Web task card."""
    speed_mbps, speed_text = format_download_speed_fn(data.get("speed"))
    percent_text = strip_ansi_fn(data.get("_percent_str")) or "计算中"
    total_size_bytes, total_size_is_estimate = progress_total_size_fn(data)

    return {
        "percent_text": percent_text,
        "speed_mbps": speed_mbps,
        "speed_text": speed_text,
        "eta_text": format_eta_fn(data.get("eta")),
        "total_size_bytes": total_size_bytes,
        "total_size_text": format_size_bytes_fn(total_size_bytes),
        "total_size_is_estimate": total_size_is_estimate,
    }


def postprocessing_preparation(
    media_type: str,
    audio_format: str,
) -> dict[str, object]:
    if media_type != "audio":
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
    if audio_format == "wav":
        stage_text = "正在准备将完整音轨解码为 WAV。"
    elif audio_format == "flac":
        stage_text = "正在准备提取 FLAC 音轨。"
    else:
        stage_text = "正在准备整理原始音轨。"
    return {
        "stage": "preparing",
        "stage_text": stage_text,
        "detail_text": "随后还会写入元数据与封面；长音频或大文件可能需要一些时间。",
    }


def postprocessor_stage(
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
        if audio_format == "wav":
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


def make_progress_hook(
    index: int,
    total: int,
    progress_callback: YtdlpProgressCallback = None,
    cancel_token: CancellationProtocol | None = None,
    media_type: str = VIDEO,
    audio_format: str = MP3,
    *,
    extract_progress_snapshot_fn: Callable[[dict], dict[str, object]] = extract_progress_snapshot,
    postprocessing_preparation_fn: Callable[[str, str], dict[str, object]] = postprocessing_preparation,
):
    """Create a numbered yt-dlp progress callback for CLI output."""

    def progress_hook(data: dict) -> None:
        if cancel_token:
            cancel_token.raise_if_cancelled()
        status = data.get("status")
        if status == "downloading":
            snapshot = extract_progress_snapshot_fn(data)
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
            payload = postprocessing_preparation_fn(media_type, audio_format)
            if progress_callback:
                progress_callback("postprocessing", payload)
            print(
                f"\n  [{index}/{total}] ✅ 数据下载完成。"
                f"{payload['stage_text']}"
            )
            print(f"  [{index}/{total}] ℹ️  {payload['detail_text']}")

    return progress_hook


def make_cancel_hook(cancel_token: CancellationProtocol):
    def cancel_hook(data: dict) -> None:
        if data.get("status") != "finished":
            cancel_token.raise_if_cancelled()

    return cancel_hook


def make_postprocessor_status_hook(
    index: int,
    total: int,
    progress_callback: YtdlpProgressCallback = None,
    media_type: str = VIDEO,
    audio_format: str = MP3,
    *,
    postprocessor_stage_fn: Callable[[object, str, str], tuple[str, str, str]] = postprocessor_stage,
):
    def status_hook(data: dict) -> None:
        if data.get("status") != "started":
            return
        stage, stage_text, detail_text = postprocessor_stage_fn(
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

    return status_hook
