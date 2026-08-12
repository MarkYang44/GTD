#!/usr/bin/env python3
"""
Multiple_Video_Downloader — Web 界面入口。

启动本地 Flask 服务，通过浏览器访问网页界面进行批量下载操作。
"""

from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request

from collection_resolver import (
    CollectionResolveError,
    PreviewStore,
    resolve_inputs,
    select_preview_entries,
)
from download_errors import public_error

from downloader import (
    AUDIO_FORMATS,
    DOWNLOADS_DIR,
    MEDIA_TYPES,
    MP3,
    SPEED_MODES,
    STANDARD,
    VIDEO,
    aria2c_path,
    check_ffmpeg,
    download_video,
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
from task_control import TaskManager, TaskSeed

app = Flask(__name__)
WEB_HOST = "127.0.0.1"
WEB_PORT = 8233
MAX_STORED_BATCHES = 100
WEB_GUIDE_PATH = Path(__file__).resolve().parent / "docs" / "WEB_GUIDE.md"

preview_store = PreviewStore(ttl_seconds=1800)
task_manager = TaskManager(
    download_video,
    max_workers=3,
    max_bilibili=2,
    max_batches=MAX_STORED_BATCHES,
    capability_aware_runner=True,
)

# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """主页面。"""
    return render_template("index.html")


@app.route("/guide")
def guide():
    """Render the Web-only usage guide from the curated Markdown source."""
    return render_template(
        "guide.html",
        guide_content=render_markdown_file(WEB_GUIDE_PATH),
    )


@app.route("/kozekilmu")
def kozekilmu():
    """A hidden LMU Fuji GT3 victory page reached from the task mascot."""
    return render_template("kozekilmu.html")


@app.route("/favicon.ico")
def favicon():
    """Serve the multi-resolution icon at the legacy browser location."""
    return app.send_static_file("icons/favicon.ico")


@app.route("/api/capabilities")
def api_capabilities():
    """返回当前服务可用的可选下载能力。"""
    return jsonify(
        {
            "aria2c_available": aria2c_path() is not None,
            "default_download_dir": str(DOWNLOADS_DIR.resolve()),
            "folder_picker_available": folder_picker_available(),
        }
    )


@app.post("/api/select-directory")
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


@app.post("/api/preview")
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


@app.route("/api/download", methods=["POST"])
def api_download():
    """接收直接 URL 或预览选择，交由进程级任务管理器执行。"""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _invalid_request("请求正文必须是 JSON 对象")

    media_type = body.get("media_type", VIDEO)
    speed_mode = body.get("speed_mode", STANDARD)
    audio_format = body.get("audio_format", MP3)
    download_dir = body.get("download_dir")

    if not isinstance(media_type, str) or media_type not in MEDIA_TYPES:
        return _invalid_request("不支持的下载类型")
    if not isinstance(speed_mode, str) or speed_mode not in SPEED_MODES:
        return _invalid_request("不支持的速度模式")
    if not isinstance(audio_format, str) or audio_format not in AUDIO_FORMATS:
        return _invalid_request("不支持的音频格式")
    if download_dir is not None and not isinstance(download_dir, str):
        return _invalid_request("download_dir 必须是路径字符串")
    try:
        prepared_download_dir = _prepare_output_dir(download_dir)
    except ValueError as error:
        return _api_error(
            "INVALID_DOWNLOAD_DIR",
            str(error),
            "请输入一个可创建且可写的文件夹，留空则使用默认 downloads",
            400,
        )
    has_urls = "urls" in body
    has_preview = "preview_id" in body or "selected_entry_ids" in body
    if has_urls == has_preview:
        return _invalid_request("请提供 urls，或 preview_id 与所选条目，且不能同时提供")

    seeds: list[TaskSeed] = []
    rejected: list[dict[str, object]] = []
    if has_preview:
        preview_id = body.get("preview_id")
        entry_ids = body.get("selected_entry_ids")
        if not isinstance(preview_id, str) or not preview_id:
            return _invalid_request("preview_id 格式无效")
        if not isinstance(entry_ids, list) or not all(
            isinstance(value, str) for value in entry_ids
        ):
            return _invalid_request("selected_entry_ids 格式无效")
        if len(entry_ids) > 100:
            return _invalid_request("一次最多选择 100 个条目")
        preview = preview_store.get(preview_id)
        if preview is None:
            return _api_error(
                "PREVIEW_EXPIRED",
                "下载预览不存在或已过期",
                "请重新解析链接并选择条目",
                404,
                True,
            )
        try:
            selected = select_preview_entries(preview, entry_ids)
        except ValueError as error:
            return _invalid_request(str(error))
        seeds = [
            TaskSeed(
                entry.platform,
                str(entry.url),
                entry.title,
                entry.position,
            )
            for entry in selected
        ]
    else:
        urls = body.get("urls")
        if not isinstance(urls, list) or not all(
            isinstance(url, str) for url in urls
        ):
            return _invalid_request("链接列表格式无效")
        if not urls:
            return _invalid_request("请至少提供一个视频链接")
        if len(urls) > 100:
            return _invalid_request("一次最多提交 100 个链接")
        for index, value in enumerate(urls, start=1):
            task = make_task(value)
            if task is None:
                normalized = normalize_url(value)
                parsed = urlparse(normalized)
                if parsed.scheme in {"http", "https"} and parsed.hostname:
                    rejected.append(
                        {
                            "index": index,
                            "error_code": "UNSUPPORTED_PLATFORM",
                            "message": "该链接不是受支持的 YouTube、Instagram 或 Bilibili 视频页面",
                        }
                    )
                else:
                    rejected.append(
                        {
                            "index": index,
                            "error_code": "INVALID_URL",
                            "message": "链接格式无效",
                        }
                    )
                continue
            platform, normalized = task
            seeds.append(TaskSeed(platform, normalized))

        if not seeds:
            first = rejected[0]
            if first["error_code"] == "UNSUPPORTED_PLATFORM":
                return _api_error(
                    "UNSUPPORTED_PLATFORM",
                    str(first["message"]),
                    "播放列表、合集与分 P 请先使用预览功能",
                    400,
                )
            return _api_error(
                "INVALID_URL",
                str(first["message"]),
                "请粘贴完整的 HTTP(S) 视频链接",
                400,
            )

    try:
        batch = task_manager.create_batch(
            seeds,
            media_type,
            audio_format,
            speed_mode,
            prepared_download_dir,
        )
    except ValueError as error:
        return _api_error(
            "INVALID_DOWNLOAD_DIR",
            str(error),
            "请输入一个可创建且可写的文件夹，留空则使用默认 downloads",
            400,
        )

    return jsonify(
        {
            "batch_id": batch["id"],
            "task_count": batch["total"],
            "rejected_count": len(rejected),
            "rejected": rejected,
            "download_dir": batch["download_dir"],
        }
    )


@app.route("/api/batch/<batch_id>")
def api_batch_status(batch_id: str):
    """轮询接口：返回指定 batch 的当前状态。"""
    try:
        return jsonify(task_manager.snapshot(batch_id))
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


@app.post("/api/batch/<batch_id>/task/<task_id>/cancel")
def api_cancel_task(batch_id: str, task_id: str):
    return _task_operation(task_manager.cancel, batch_id, task_id)


@app.post("/api/batch/<batch_id>/task/<task_id>/retry")
def api_retry_task(batch_id: str, task_id: str):
    return _task_operation(task_manager.retry, batch_id, task_id)


@app.post("/api/batch/<batch_id>/task/<task_id>/redownload")
def api_redownload_task(batch_id: str, task_id: str):
    return _task_operation(task_manager.redownload, batch_id, task_id)


@app.post("/api/batch/<batch_id>/retry-failed")
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


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not check_ffmpeg():
        print("⚠️  警告：未检测到 FFmpeg，最高质量下载需要 FFmpeg。")
    try:
        prepare_folder_picker()
    except FolderPickerUnavailable as error:
        print(f"⚠️  文件夹选择器准备失败：{error}；仍可手动输入下载路径。")

    print("=" * 56)
    print("  🎬 Multiple_Video_Downloader — Web 模式")
    print("=" * 56)
    print(f"  浏览器访问:  http://{WEB_HOST}:{WEB_PORT}")
    print(f"  默认下载目录: {DOWNLOADS_DIR.resolve()}")
    print("  按 Ctrl+C 停止服务")
    print("=" * 56)

    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)
