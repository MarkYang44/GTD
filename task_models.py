"""Static task contracts; public JSON and SQLite allowlists remain unchanged.

Optional keys also describe older persisted records. These types document data,
not runtime validation, and do not serialize private execution capabilities.
"""

from typing import Literal, TypedDict

from output_files import _PreparedOutputDir


TaskStatus = Literal["queued", "running", "running_uninterruptible",
                     "completed", "failed", "cancelled"]
TerminalStatus = Literal["completed", "failed", "cancelled"]


class PublicError(TypedDict):
    error_code: str
    message: str
    suggestion: str
    retryable: bool


class ProgressSnapshot(TypedDict, total=False):
    percent_text: str
    speed_mbps: float | None
    speed_text: str
    eta_text: str
    total_size_bytes: int | None
    total_size_text: str
    total_size_is_estimate: bool
    stage_text: str
    stage: str
    detail_text: str


class TaskResult(TypedDict, total=False):
    title: str
    filepath: str
    filesize: str
    platform: str
    media_type: str
    format: str
    acodec: str | None
    vcodec: str
    resolution: str
    fps: float | str
    speed_mode_requested: str
    speed_mode_used: str
    turbo_fallback: bool
    output_version_actual: int
    cdn_host: str
    http_chunk_size: int
    cover_embedded: bool
    cover_source: str
    fallback_cover: str | None
    audio_format_requested: str
    audio_format_used: str
    audio_format_fallback: bool
    output_ext: str
    source_acodec: str | None
    source_abr_kbps: int | str | None
    subtitle_status: str
    subtitle_tracks: int
    subtitle_warnings: list[str]
    local_extraction: bool
    audio_stream_index: int
    download_url: str


class AttemptState(TypedDict):
    number: int
    status: TaskStatus
    started_at: float
    finished_at: float | None
    output_version: int
    error: PublicError | None


class TaskState(ProgressSnapshot, total=False):
    id: str
    index: int
    platform: str
    url: str
    title: str | None
    position: int | None
    media_type: str
    audio_format: str
    speed_mode: str
    download_dir: str | None
    subtitle_options: dict[str, bool]
    speed_mode_used: str | None
    turbo_fallback: bool
    output_version: int
    version_key: str | None
    base_filepath: str | None
    status: TaskStatus
    attempt_count: int
    attempts: list[AttemptState]
    error: PublicError | None
    result: TaskResult | None
    progress: ProgressSnapshot | None
    postprocessing: ProgressSnapshot
    cancel_requested: bool
    _prepared_output_dir: _PreparedOutputDir | None


class BatchState(TypedDict):
    id: str
    created_at: float
    media_type: str
    audio_format: str
    speed_mode: str
    download_dir: str
    subtitle_options: dict[str, bool]
    tasks: list[TaskState]
