#!/usr/bin/env python3
"""
GTD — Generalized Transmedia Downloader — Web 界面入口。

启动本地 Flask 服务，通过浏览器访问网页界面进行批量下载操作。
"""

from runtime_requirements import require_supported_python

require_supported_python()

import os
import mimetypes
from pathlib import Path, PurePosixPath

from flask import Flask, current_app, has_app_context, jsonify, render_template, request
from werkzeug.local import LocalProxy

mimetypes.add_type("text/javascript", ".js")

from collection_resolver import (
    CollectionResolveError,
    PreviewStore,
    resolve_inputs,
)
from download_errors import public_error

from downloader import (
    DOWNLOADS_DIR,
    aria2c_path,
    check_ffmpeg,
    ensure_downloads_dir,
    _prepare_output_dir,
    make_task,
    normalize_url,
)
from folder_picker import (
    FolderPickerUnavailable,
    choose_folder,
    folder_picker_available,
    prepare_folder_picker,
)
from guide_renderer import render_markdown_file
from lmu_guide_data import CARS, CIRCUITS, GUIDE_UPDATED
from lmu_content import template_context as lmu_content_context
from audio_extract_routes import extraction_blueprint, with_download_links
from download_requests import DownloadRequestError, parse_download_request
from web_runtime import configure_runtime, get_runtime

WEB_HOST = "0.0.0.0"
WEB_PORT = 8233
MAX_STORED_BATCHES = 100
WEB_GUIDE_PATH = Path(__file__).resolve().parent / "docs" / "WEB_GUIDE.md"


def _guide_static_image_exists(relative_path: str) -> bool:
    """Return whether a guide asset is a file below Flask's static root."""
    if not relative_path or "\\" in relative_path:
        return False
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        return False
    static_root = Path(_active_application().static_folder).resolve()
    candidate = (static_root / path).resolve()
    try:
        candidate.relative_to(static_root)
    except ValueError:
        return False
    return candidate.is_file()


def _available_guide_images(circuits, cars) -> frozenset[str]:
    """Build the small availability mapping required by the guide."""
    image_paths = {item.image for item in circuits}
    image_paths.update(item.image for item in cars)
    return frozenset(path for path in image_paths if _guide_static_image_exists(path))

def _active_application():
    return current_app._get_current_object() if has_app_context() else app


# Preserve legacy imports and test seams while resolving per-application resources.
task_manager = LocalProxy(lambda: get_runtime(_active_application()).task_manager)
preview_store = LocalProxy(lambda: get_runtime(_active_application()).preview_store)
upload_store = LocalProxy(lambda: get_runtime(_active_application()).upload_store)


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
def index():
    """主页面。"""
    return render_template("index.html")


def guide():
    """Render the Web-only usage guide from the curated Markdown source."""
    return render_template(
        "guide.html",
        guide_content=render_markdown_file(WEB_GUIDE_PATH),
        guide_content_en=render_markdown_file(WEB_GUIDE_PATH.with_name("WEB_GUIDE.en.md")),
    )


def kozekilmu():
    """Render the hidden LMU Fuji GT3 victory archive."""
    return render_template("kozekilmu.html")


def kozekilmu_tracks():
    """Render the read-only LMU circuit and car recommendation guide."""
    return render_template(
        "kozekilmu_tracks.html",
        cars=CARS,
        circuits=CIRCUITS,
        guide_updated=GUIDE_UPDATED,
        available_images=_available_guide_images(CIRCUITS, CARS.values()),
        **lmu_content_context(),
    )


def kozekilmu_cars():
    """Browse every catalog car with its source-derived circuit recommendations."""
    recommendations = {slug: [] for slug in CARS}
    for circuit in CIRCUITS:
        for class_name, class_recommendations in (
            ("LMGT3", circuit.lmgt3),
            ("Hypercar", circuit.hypercar),
        ):
            for recommendation in class_recommendations:
                recommendations[recommendation.car_slug].append(
                    (circuit, recommendation, False, class_name)
                )
        for class_name, recommendation in (
            ("LMGT3", circuit.sleeper_lmgt3),
            ("Hypercar", circuit.sleeper_hypercar),
        ):
            recommendations[recommendation.car_slug].append(
                (circuit, recommendation, True, class_name)
            )
    return render_template(
        "kozekilmu_tracks.html", is_catalog=True,
        page_title_zh="LMU 车型图鉴", page_title_en="LMU Car Catalog",
        cars=CARS, circuits=CIRCUITS, car_recommendations=recommendations,
        guide_updated=GUIDE_UPDATED,
        available_images=_available_guide_images(CIRCUITS, CARS.values()),
        **lmu_content_context(),
    )


def favicon():
    """Serve the multi-resolution icon at the legacy browser location."""
    return current_app.send_static_file("icons/favicon.ico")


def api_capabilities():
    """返回当前服务可用的可选下载能力。"""
    return jsonify(
        {
            "aria2c_available": aria2c_path() is not None,
            "default_download_dir": str(DOWNLOADS_DIR.resolve()),
            "folder_picker_available": folder_picker_available(),
        }
    )


def api_select_directory():
    """Open the host OS folder picker for this local-only Web service."""
    body = request.get_json(silent=True)
    if body is None:
        body = {}
    if not isinstance(body, dict):
        return _invalid_request("请求正文必须是 JSON 对象")
    initial_dir = body.get("initial_dir")
    if initial_dir is not None and not isinstance(initial_dir, str):
        return _invalid_request("initial_dir 必须是路径字符串")
    try:
        selected = choose_folder(initial_dir or DOWNLOADS_DIR)
        if selected is None:
            return jsonify({"cancelled": True})
        resolved = ensure_downloads_dir(selected)
    except FolderPickerUnavailable as error:
        return _api_error(
            "FOLDER_PICKER_UNAVAILABLE",
            str(error),
            "请在下载位置输入框中手动输入文件夹路径",
            503,
        )
    except ValueError as error:
        return _api_error(
            "INVALID_DOWNLOAD_DIR",
            str(error),
            "请选择或输入一个可创建且可写的文件夹",
            400,
        )
    return jsonify({"cancelled": False, "download_dir": str(resolved)})


def _api_error(
    error_code: str,
    message: str,
    suggestion: str,
    status: int,
    retryable: bool = False,
):
    """Return one stable Web error shape while retaining legacy `error`."""
    return (
        jsonify(
            {
                "error_code": error_code,
                "message": message,
                "suggestion": suggestion,
                "retryable": retryable,
                "error": message,
            }
        ),
        status,
    )


def _invalid_request(message: str):
    return _api_error(
        "INVALID_REQUEST",
        message,
        "请检查请求内容后重试",
        400,
    )


def api_preview():
    """展开一组普通链接与合集链接，返回可选择的只读预览。"""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _invalid_request("请求正文必须是 JSON 对象")
    inputs = body.get("inputs")
    if not isinstance(inputs, list) or not inputs or not all(
        isinstance(value, str) and value.strip() for value in inputs
    ):
        return _invalid_request("inputs 必须是非空字符串列表")
    try:
        preview = resolve_inputs(inputs)
    except CollectionResolveError as error:
        payload = public_error(error)
        return jsonify({**payload, "error": payload["message"]}), 400
    except ValueError as error:
        return _invalid_request(str(error))
    preview_store.put(preview)
    return jsonify(preview.to_dict())


def api_download():
    """Parse one submission, then hand execution to the application's manager."""
    try:
        submission = parse_download_request(
            request.get_json(silent=True), previews=preview_store,
            prepare_directory=_prepare_output_dir, task_factory=make_task,
            normalizer=normalize_url,
        )
    except DownloadRequestError as error:
        return _api_error(error.error_code, error.message, error.suggestion,
                          error.status, error.retryable)
    try:
        preferences = submission.preferences
        batch = task_manager.create_batch(
            submission.seeds, preferences.media_type, preferences.audio_format,
            preferences.speed_mode, submission.output_dir,
            **({"subtitle_options": submission.subtitle_options} if submission.subtitle_options else {}),
        )
    except ValueError as error:
        return _api_error("INVALID_DOWNLOAD_DIR", str(error),
                          "请输入一个可创建且可写的文件夹，留空则使用默认 downloads", 400)
    return jsonify(batch_id=batch["id"], task_count=batch["total"],
                   rejected_count=len(submission.rejected), rejected=submission.rejected,
                   download_dir=batch["download_dir"])


def api_batches():
    """List locally saved batch summaries, newest first."""
    return jsonify({"batches": task_manager.list_batches()})


def api_batch_status(batch_id: str):
    """轮询接口：返回指定 batch 的当前状态。"""
    try:
        return jsonify(with_download_links(task_manager.snapshot(batch_id)))
    except KeyError:
        return _api_error(
            "BATCH_NOT_FOUND",
            "任务批次不存在或已过期",
            "请重新提交下载任务",
            404,
        )


def _task_operation(operation, batch_id: str, task_id: str):
    try:
        return jsonify(operation(batch_id, task_id))
    except KeyError as error:
        return _api_error(
            "TASK_NOT_FOUND",
            str(error).strip("'"),
            "请刷新任务列表后重试",
            404,
        )
    except ValueError as error:
        return _api_error(
            "TASK_STATE_CONFLICT",
            str(error),
            "请刷新任务状态后再操作",
            409,
        )


def api_cancel_task(batch_id: str, task_id: str):
    return _task_operation(task_manager.cancel, batch_id, task_id)


def api_retry_task(batch_id: str, task_id: str):
    return _task_operation(task_manager.retry, batch_id, task_id)


def api_redownload_task(batch_id: str, task_id: str):
    return _task_operation(task_manager.redownload, batch_id, task_id)


def api_retry_failed(batch_id: str):
    try:
        return jsonify(task_manager.retry_failed(batch_id))
    except KeyError:
        return _api_error(
            "BATCH_NOT_FOUND",
            "任务批次不存在或已过期",
            "请刷新任务列表后重试",
            404,
        )
    except ValueError as error:
        return _api_error(
            "TASK_STATE_CONFLICT",
            str(error),
            "请检查下载目录并刷新任务状态后重试",
            409,
        )


def create_app(config=None, *, manager=None, uploads=None):
    """Build an isolated Web app; initialize execution resources on first use.

    The caller owns shutdown of the task manager in ``extensions['gtd.runtime']``
    after initialization. Importing this module performs no history I/O.
    """
    application = Flask(__name__)
    root = Path(__file__).resolve().parent
    application.config.from_mapping(
        GTD_HISTORY_PATH=os.environ.get("GTD_HISTORY_PATH", str(root / "state" / "tasks.sqlite3")),
        GTD_UPLOAD_ROOT=os.environ.get("GTD_UPLOAD_ROOT", str(root / "state" / "audio_uploads")),
        GTD_MAX_STORED_BATCHES=MAX_STORED_BATCHES,
    )
    application.config.update(config or {})
    configure_runtime(application, manager=manager, uploads=uploads)
    for rule, view, methods in (
        ("/", index, ["GET"]),
        ("/guide", guide, ["GET"]),
        ("/kozekilmu", kozekilmu, ["GET"]),
        ("/kozekilmu/tracks", kozekilmu_tracks, ["GET"]),
        ("/kozekilmu/cars", kozekilmu_cars, ["GET"]),
        ("/favicon.ico", favicon, ["GET"]),
        ("/api/capabilities", api_capabilities, ["GET"]),
        ("/api/select-directory", api_select_directory, ["POST"]),
        ("/api/preview", api_preview, ["POST"]),
        ("/api/download", api_download, ["POST"]),
        ("/api/batches", api_batches, ["GET"]),
        ("/api/batch/<batch_id>", api_batch_status, ["GET"]),
        ("/api/batch/<batch_id>/task/<task_id>/cancel", api_cancel_task, ["POST"]),
        ("/api/batch/<batch_id>/task/<task_id>/retry", api_retry_task, ["POST"]),
        ("/api/batch/<batch_id>/task/<task_id>/redownload", api_redownload_task, ["POST"]),
        ("/api/batch/<batch_id>/retry-failed", api_retry_failed, ["POST"]),
    ):
        application.add_url_rule(rule, view_func=view, methods=methods)
    application.register_blueprint(extraction_blueprint(task_manager, upload_store))
    return application


app = create_app()


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    get_runtime(app)
    if not check_ffmpeg():
        print("⚠️  警告：未检测到 FFmpeg，最高质量下载需要 FFmpeg。")
    try:
        prepare_folder_picker()
    except FolderPickerUnavailable as error:
        print(f"⚠️  文件夹选择器准备失败：{error}；仍可手动输入下载路径。")

    print("=" * 56)
    print("  🎬 GTD — Generalized Transmedia Downloader — Web 模式")
    print("=" * 56)
    print(f"  本机访问:    http://127.0.0.1:{WEB_PORT}")
    print(f"  局域网访问:  http://<本机局域网 IP>:{WEB_PORT}")
    print(f"  默认下载目录: {DOWNLOADS_DIR.resolve()}")
    print("  按 Ctrl+C 停止服务")
    print("=" * 56)

    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)
