#!/usr/bin/env python3
"""
YouTube & Instagram 视频批量下载工具 — Web 界面入口。

启动本地 Flask 服务，通过浏览器访问网页界面进行批量下载操作。
"""

import threading
import uuid
from flask import Flask, jsonify, render_template, request

from downloader import (
    MEDIA_TYPES,
    PLATFORM_NAMES,
    VIDEO,
    check_ffmpeg,
    download_tasks,
    make_task,
)

app = Flask(__name__)
WEB_HOST = "127.0.0.1"
WEB_PORT = 8233

# ---------------------------------------------------------------------------
# 内存状态存储（服务重启后清空）
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_batches: dict[str, dict] = {}


def _create_batch(tasks: list, media_type: str = VIDEO) -> dict:
    """根据任务列表创建初始 batch 数据结构。"""
    batch_id = uuid.uuid4().hex[:8]
    batch = {
        "id": batch_id,
        "media_type": media_type,
        "tasks": [
            {
                "index": i,
                "url": url,
                "platform": platform,
                "platform_name": PLATFORM_NAMES.get(platform, "未知"),
                "status": "pending",       # pending | downloading | completed | failed
                "title": None,
                "result": None,
                "error": None,
                "progress": None,
            }
            for i, (platform, url) in enumerate(tasks)
        ],
        "total": len(tasks),
        "completed": 0,
        "failed": 0,
        "all_done": False,
    }
    with _lock:
        _batches[batch_id] = batch
    return batch


def _apply_progress_event(batch: dict, task_index: int, event: str, data: object) -> None:
    """将下载器事件写入 batch 中对应任务的 Web 状态。"""
    if task_index < 0 or task_index >= len(batch["tasks"]):
        return

    task = batch["tasks"][task_index]
    if task["status"] in {"completed", "failed"}:
        return

    if event == "started":
        task["status"] = "downloading"
        task["error"] = None
        task["progress"] = None
    elif event == "progress" and isinstance(data, dict):
        task["status"] = "downloading"
        task["progress"] = {
            key: data.get(key)
            for key in ("percent_text", "speed_mbps", "speed_text", "eta_text")
            if key in data
        }
    elif event == "completed" and isinstance(data, dict):
        task["status"] = "completed"
        task["result"] = {k: str(v) for k, v in data.items()}
        task["progress"] = None
        batch["completed"] += 1
    elif event == "failed" and isinstance(data, dict):
        task["status"] = "failed"
        task["error"] = str(data.get("error", "下载失败"))
        task["progress"] = None
        batch["failed"] += 1


def _run_downloads(batch_id: str, tasks: list, media_type: str = VIDEO) -> None:
    """后台线程：并行执行下载并更新 batch 状态。"""

    def _on_progress(task_index: int, event: str, data: object) -> None:
        with _lock:
            batch = _batches.get(batch_id)
            if not batch:
                return
            _apply_progress_event(batch, task_index, event, data)

    download_tasks(
        tasks,
        progress_callback=_on_progress,
        media_type=media_type,
    )

    with _lock:
        batch = _batches.get(batch_id)
        if batch:
            batch["all_done"] = True


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """主页面。"""
    return render_template("index.html")


@app.route("/api/download", methods=["POST"])
def api_download():
    """接收 URL 列表，启动后台下载线程，返回 batch_id。"""
    body = request.get_json(silent=True) or {}
    urls: list[str] = body.get("urls", [])
    media_type = body.get("media_type", VIDEO)

    if not isinstance(media_type, str) or media_type not in MEDIA_TYPES:
        return jsonify({"error": "不支持的下载类型"}), 400

    if not urls:
        return jsonify({"error": "请至少提供一个视频链接"}), 400

    # 过滤出合法链接
    tasks = []
    for url in urls:
        task = make_task(url)
        if task:
            tasks.append(task)

    if not tasks:
        return jsonify({"error": "未识别到任何受支持的 YouTube 或 Instagram 链接"}), 400

    batch = _create_batch(tasks, media_type=media_type)

    thread = threading.Thread(
        target=_run_downloads,
        args=(batch["id"], tasks, media_type),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "batch_id": batch["id"],
        "task_count": batch["total"],
    })


@app.route("/api/batch/<batch_id>")
def api_batch_status(batch_id: str):
    """轮询接口：返回指定 batch 的当前状态。"""
    with _lock:
        batch = _batches.get(batch_id)
    if not batch:
        return jsonify({"error": "任务批次不存在或已过期"}), 404
    return jsonify(batch)


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not check_ffmpeg():
        print("⚠️  警告：未检测到 FFmpeg，最高质量下载需要 FFmpeg。")

    print("=" * 56)
    print("  🎬 Ytb/Ins Downloader — Web 模式")
    print("=" * 56)
    print(f"  浏览器访问:  http://{WEB_HOST}:{WEB_PORT}")
    print(f"  下载目录:    downloader.py 同级的 downloads/")
    print("  按 Ctrl+C 停止服务")
    print("=" * 56)

    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)
