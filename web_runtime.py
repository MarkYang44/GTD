"""Own one lazily initialized set of Web execution resources per Flask app."""

from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from collection_resolver import PreviewStore
from downloader import download_video, _prepare_output_dir
from local_audio import UploadStore, extract_audio
from task_control import TaskManager
from task_history import TaskHistoryStore


@dataclass(frozen=True)
class WebRuntime:
    task_manager: TaskManager
    preview_store: PreviewStore
    upload_store: UploadStore


def configure_runtime(application, *, manager=None, uploads=None):
    """Install lifecycle metadata only; no executors, history I/O, or cleanup."""
    application.extensions["gtd.runtime_lock"] = RLock()
    application.extensions["gtd.dependencies"] = (manager, uploads)


def get_runtime(application) -> WebRuntime:
    """Initialize once, including concurrent first requests to the same app."""
    with application.extensions["gtd.runtime_lock"]:
        runtime = application.extensions.get("gtd.runtime")
        if runtime is None:
            runtime = _create_runtime(application)
            application.extensions["gtd.runtime"] = runtime
        return runtime


def _create_runtime(application) -> WebRuntime:
    manager, uploads = application.extensions["gtd.dependencies"]
    owns_manager = manager is None
    if uploads is None:
        uploads = UploadStore(Path(application.config["GTD_UPLOAD_ROOT"]))

    # Workers run outside Flask request contexts. Capture this application's store.
    def run_media_task(url, **kwargs):
        if kwargs.get("platform") == "local":
            return extract_audio(url, store=uploads, **kwargs)
        return download_video(url, **kwargs)

    if manager is None:
        manager = TaskManager(run_media_task, max_workers=3, max_bilibili=2,
            max_instagram=1, max_batches=application.config["GTD_MAX_STORED_BATCHES"],
            capability_aware_runner=True, directory_preparer=_prepare_output_dir,
            history_store=TaskHistoryStore(application.config["GTD_HISTORY_PATH"]))
    try:
        manager.cleanup_inputs("local", uploads.cleanup)
    except BaseException:
        if owns_manager:
            manager.shutdown()
        raise
    return WebRuntime(manager, PreviewStore(ttl_seconds=1800), uploads)
