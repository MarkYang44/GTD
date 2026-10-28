"""Turn Web download inputs into a validated submission, without Flask state."""

from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

from collection_resolver import PreviewStore, select_preview_entries
from audio_output import AUDIO_FORMATS, MP3
from bilibili_acceleration import SPEED_MODES, STANDARD
from download_options import DownloadPreferences, MEDIA_TYPES, VIDEO
from media_sources import make_task, normalize_url
from output_files import _PreparedOutputDir, prepare_output_dir
from task_control import TaskSeed
from subtitle_preferences import normalize_subtitle_options


class DownloadRequestError(ValueError):
    """A public request rejection; the HTTP adapter owns JSON serialization."""

    def __init__(self, error_code, message, suggestion, status=400, retryable=False):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.suggestion = suggestion
        self.status = status
        self.retryable = retryable


@dataclass(frozen=True)
class DownloadSubmission:
    preferences: DownloadPreferences
    subtitle_options: dict
    output_dir: _PreparedOutputDir
    seeds: list[TaskSeed]
    rejected: list[dict[str, object]]


def _invalid(message):
    return DownloadRequestError("INVALID_REQUEST", message, "请检查请求内容后重试")


def _settings(body):
    if not isinstance(body, dict):
        raise _invalid("请求正文必须是 JSON 对象")
    media_type = body.get("media_type", VIDEO)
    speed_mode = body.get("speed_mode", STANDARD)
    audio_format = body.get("audio_format", MP3)
    try:
        subtitles = normalize_subtitle_options(body.get("subtitle_options"), media_type)
    except ValueError as error:
        raise _invalid(str(error)) from error
    for value, allowed, message in (
        (media_type, MEDIA_TYPES, "不支持的下载类型"),
        (speed_mode, SPEED_MODES, "不支持的速度模式"),
        (audio_format, AUDIO_FORMATS, "不支持的音频格式"),
    ):
        if not isinstance(value, str) or value not in allowed:
            raise _invalid(message)
    directory = body.get("download_dir")
    if directory is not None and not isinstance(directory, str):
        raise _invalid("download_dir 必须是路径字符串")
    return DownloadPreferences(media_type, audio_format, speed_mode), subtitles, directory


def _preview_seeds(body, previews):
    preview_id = body.get("preview_id")
    entry_ids = body.get("selected_entry_ids")
    if not isinstance(preview_id, str) or not preview_id:
        raise _invalid("preview_id 格式无效")
    if not isinstance(entry_ids, list) or not all(isinstance(value, str) for value in entry_ids):
        raise _invalid("selected_entry_ids 格式无效")
    if len(entry_ids) > 100:
        raise _invalid("一次最多选择 100 个条目")
    preview = previews.get(preview_id)
    if preview is None:
        raise DownloadRequestError("PREVIEW_EXPIRED", "下载预览不存在或已过期",
                                   "请重新解析链接并选择条目", 404, True)
    try:
        selected = select_preview_entries(preview, entry_ids)
    except ValueError as error:
        raise _invalid(str(error)) from error
    return [TaskSeed(entry.platform, str(entry.url), entry.title, entry.position)
            for entry in selected]


def _direct_seeds(body, task_factory, normalizer):
    urls = body.get("urls")
    if not isinstance(urls, list) or not all(isinstance(url, str) for url in urls):
        raise _invalid("链接列表格式无效")
    if not urls:
        raise _invalid("请至少提供一个视频链接")
    if len(urls) > 100:
        raise _invalid("一次最多提交 100 个链接")
    seeds, rejected = [], []
    for index, value in enumerate(urls, start=1):
        task = task_factory(value)
        if task is not None:
            seeds.append(TaskSeed(*task))
            continue
        parsed = urlparse(normalizer(value))
        is_http_url = parsed.scheme in {"http", "https"} and parsed.hostname
        rejected.append({"index": index,
            "error_code": "UNSUPPORTED_PLATFORM" if is_http_url else "INVALID_URL",
            "message": "该链接不是受支持的 YouTube、Instagram 或 Bilibili 视频页面" if is_http_url else "链接格式无效"})
    if not seeds:
        first = rejected[0]
        suggestion = ("播放列表、合集与分 P 请先使用预览功能"
                      if first["error_code"] == "UNSUPPORTED_PLATFORM" else "请粘贴完整的 HTTP(S) 视频链接")
        raise DownloadRequestError(first["error_code"], first["message"], suggestion)
    return seeds, rejected


def parse_download_request(body, *, previews: PreviewStore,
                           prepare_directory: Callable = prepare_output_dir,
                           task_factory: Callable = make_task,
                           normalizer: Callable = normalize_url) -> DownloadSubmission:
    """Keep validation order, explicit preview selection, and rejected URL indexes."""
    preferences, subtitles, directory = _settings(body)
    try:
        output_dir = prepare_directory(directory)
    except ValueError as error:
        raise DownloadRequestError("INVALID_DOWNLOAD_DIR", str(error),
                                   "请输入一个可创建且可写的文件夹，留空则使用默认 downloads") from error
    has_urls = "urls" in body
    has_preview = "preview_id" in body or "selected_entry_ids" in body
    if has_urls == has_preview:
        raise _invalid("请提供 urls，或 preview_id 与所选条目，且不能同时提供")
    seeds, rejected = ((_preview_seeds(body, previews), []) if has_preview
                       else _direct_seeds(body, task_factory, normalizer))
    return DownloadSubmission(preferences, subtitles, output_dir, seeds, rejected)

