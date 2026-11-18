"""Private desktop transport over authenticated IPv4 loopback.

The parent supplies one bearer token over stdin and keeps the pipe open for
the lifetime of the application. Stdout is reserved for the readiness frame.
"""
from __future__ import annotations

import argparse
from hmac import compare_digest
import json
import logging
import os
from pathlib import Path
import re
import signal
from socketserver import TCPServer
import sys
from tempfile import NamedTemporaryFile
from threading import Event, RLock, Thread

from flask import jsonify, request
from werkzeug.datastructures import FileStorage
from werkzeug.serving import ThreadedWSGIServer

from app import create_app
from download_errors import DownloadFailure, public_error
from media_sources import PLATFORM_NAMES
from output_files import ensure_downloads_dir, prepare_output_dir
from task_control import TaskSeed
from web_runtime import get_runtime

DOWNLOAD_ROUTES = {
    "api_capabilities", "api_preview", "api_download", "api_batches",
    "api_batch_status", "api_cancel_task", "api_retry_task", "api_redownload_task",
    "api_retry_failed",
}
COOKIE_SIZE_LIMIT = 4 * 1024**2


class LoopbackServer(ThreadedWSGIServer):
    def server_bind(self):
        # HTTPServer normally resolves the bound host via reverse DNS.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address


def _atomic_write(path: Path, text: str) -> None:
    handle = NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
    temp = Path(handle.name)
    try:
        with handle:
            handle.write(text)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _read_cookie_file(path: Path) -> str:
    if not path.is_file():
        raise ValueError("请选择有效的 Cookies 文件 / Choose a valid cookies file.")
    with path.open("rb") as handle:
        raw = handle.read(COOKIE_SIZE_LIMIT + 1)
    if len(raw) > COOKIE_SIZE_LIMIT:
        raise ValueError("Cookies 文件超过 4 MiB / Cookies file exceeds 4 MiB.")
    text = raw.decode("utf-8-sig")
    lines = text.splitlines()
    if not lines or not re.match(r"^#( Netscape)? HTTP Cookie File", lines[0]):
        raise ValueError("需要 Netscape 格式 / Choose a Netscape cookies file.")
    for line in lines[1:]:
        if line.startswith("#HttpOnly_"):
            line = line.removeprefix("#HttpOnly_")
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split("\t")
        if (len(fields) != 7 or fields[1] not in {"TRUE", "FALSE"}
                or fields[3] not in {"TRUE", "FALSE"}
                or fields[0].startswith(".") != (fields[1] == "TRUE")
                or (fields[4] and not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", fields[4]))):
            raise ValueError("Cookies 条目无效 / The cookies file has an invalid entry.")
    return "\n".join(lines) + "\n"


class DesktopSettings:
    def __init__(self, data_dir: Path, default_download_dir: Path):
        data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.file = data_dir / "settings.json"
        self.cookies = data_dir / "cookies"
        self.cookies.mkdir(mode=0o700, exist_ok=True)
        self.default_dir = default_download_dir
        self.lock = RLock()
        self.values = {"theme": "system", "language": "en", "download_dir": ""}
        if self.file.is_file():
            try:
                self.values.update(self._validate(json.loads(self.file.read_text(encoding="utf-8"))))
            except (OSError, ValueError):
                # Restore defaults if the configuration is edited or damaged.
                pass

    @staticmethod
    def _validate(changes):
        if not isinstance(changes, dict) or changes.keys() - {"theme", "language", "download_dir"}:
            raise ValueError("设置无效 / Invalid settings.")
        if "theme" in changes and changes["theme"] not in ("system", "light", "dark"):
            raise ValueError("主题无效 / Invalid theme.")
        if "language" in changes and changes["language"] not in ("zh", "en"):
            raise ValueError("语言无效 / Invalid language.")
        if "download_dir" in changes:
            location = changes["download_dir"]
            if not isinstance(location, str) or (location and not Path(location).is_absolute()):
                raise ValueError("请选择绝对路径 / Choose an absolute download path.")
        return changes

    def snapshot(self):
        with self.lock:
            return {
                **self.values,
                "default_download_dir": str(self.default_dir),
                "cookies": {name: self.cookie_path(name).is_file() for name in PLATFORM_NAMES},
            }

    def cookie_path(self, platform):
        return self.cookies / f"{platform}_cookies.txt"

    def update(self, changes):
        changes = self._validate(changes)
        if changes.get("download_dir"):
            changes = {**changes, "download_dir": str(self.ensure_directory(changes["download_dir"]))}
        with self.lock:
            values = {**self.values, **changes}
            _atomic_write(self.file, json.dumps(values, ensure_ascii=False) + "\n")
            self.values = values
            return self.snapshot()

    def ensure_directory(self, location):
        if location and not Path(location).is_absolute():
            raise ValueError("请选择绝对路径 / Choose an absolute download path.")
        return ensure_downloads_dir(location, downloads_dir=self.default_dir)

    def prepare_directory(self, location):
        with self.lock:
            selected = location or self.values["download_dir"]
        return prepare_output_dir(selected, ensure_directory=self.ensure_directory)


def _error(code, message, status=400):
    return jsonify(error_code=code, message=message), status


def create_desktop_app(data_dir: Path, download_dir: Path, token: str):
    settings = DesktopSettings(data_dir, download_dir)
    application = create_app({
        "GTD_DESKTOP": True,
        "GTD_DOWNLOAD_DIR": download_dir,
        "GTD_DIRECTORY_PREPARER": settings.prepare_directory,
        "GTD_HISTORY_PATH": data_dir / "tasks.sqlite3",
        "GTD_UPLOAD_ROOT": data_dir / "audio_uploads",
        "MAX_CONTENT_LENGTH": 512 * 1024,
    })

    @application.before_request
    def guard():
        if (not re.fullmatch(r"127\.0\.0\.1(?::[0-9]+)?", request.host)
                or request.headers.get("Origin") is not None
                or not compare_digest(request.headers.get("Authorization", "").encode("utf-8"),
                                      f"Bearer {token}".encode("utf-8"))):
            return _error("ACCESS_DENIED", "Forbidden", 403)
        if request.endpoint not in DOWNLOAD_ROUTES and request.endpoint not in {
            "desktop_settings", "desktop_cookies", "desktop_extract", "desktop_batch_action",
        }:
            return _error("UNKNOWN_ROUTE", "Not found", 404)

    @application.route("/api/desktop/settings", methods=["GET", "POST"])
    def desktop_settings():
        if request.method == "GET":
            return jsonify(settings.snapshot())
        try:
            return jsonify(settings.update(request.get_json(silent=True)))
        except ValueError as error:
            return _error("INVALID_SETTINGS", str(error))
        except OSError:
            return _error("SETTINGS_WRITE_FAILED", "无法保存设置 / Could not save settings.", 507)

    @application.post("/api/desktop/cookies")
    def desktop_cookies():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _error("INVALID_REQUEST", "需要 JSON 对象 / Expected a JSON object.")
        platform, source = body.get("platform"), body.get("path")
        if (not isinstance(platform, str) or platform not in PLATFORM_NAMES
                or (source is not None and (not isinstance(source, str) or not Path(source).is_absolute()))):
            return _error("INVALID_COOKIES", "请选择平台和文件 / Choose a platform and cookie file.")
        with settings.lock:
            target = settings.cookie_path(platform)
            try:
                if source is None:
                    target.unlink(missing_ok=True)
                else:
                    _atomic_write(target, _read_cookie_file(Path(source)))
            except UnicodeError:
                return _error("INVALID_COOKIES", "Cookies 文件需要 UTF-8 / Expected a UTF-8 cookies file.")
            except ValueError as error:
                return _error("INVALID_COOKIES", str(error))
            except OSError:
                return _error("COOKIE_IO_ERROR", "无法读写 Cookies 文件 / Could not read or write the cookies file.", 507)
            return jsonify(settings.snapshot())

    @application.post("/api/desktop/extract")
    def desktop_extract():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _error("INVALID_REQUEST", "需要 JSON 对象 / Expected a JSON object.")
        source, mode, location = body.get("path"), body.get("audio_format", "source"), body.get("download_dir")
        if (not isinstance(source, str) or not Path(source).is_absolute()
                or mode not in ("source", "mp3")
                or (location is not None and not isinstance(location, str))):
            return _error("INVALID_UPLOAD", "请选择视频和音频格式 / Choose a video and audio format.")
        path = Path(source)
        if not path.is_file():
            return _error("INVALID_UPLOAD", "找不到视频文件 / Video file not found.")
        runtime = get_runtime(application)
        store, manager = runtime.upload_store, runtime.task_manager
        key = None
        try:
            directory = settings.prepare_directory(location)
            manager.cleanup_inputs("local", store.cleanup)
            with path.open("rb") as handle:
                key = store.save(FileStorage(stream=handle, filename=path.name))
            batch = manager.create_batch([TaskSeed("local", key, title=path.name)], "audio", mode, "standard", directory)
            return jsonify(batch_id=batch["id"], task_count=batch["total"]), 202
        except DownloadFailure as error:
            if key is not None:
                store.remove(key)
            status = {"UPLOAD_TOO_LARGE": 413, "UPLOAD_STORAGE_FULL": 507}.get(error.info.error_code, 400)
            return jsonify(public_error(error)), status
        except ValueError as error:
            if key is not None:
                store.remove(key)
            return _error("INVALID_DOWNLOAD_DIR", str(error))
        except OSError:
            if key is not None:
                store.remove(key)
            return _error("UPLOAD_STORAGE_FULL", "无法复制视频 / Could not copy the video file.", 507)

    @application.post("/api/desktop/batch-action")
    def desktop_batch_action():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _error("INVALID_REQUEST", "需要 JSON 对象 / Expected a JSON object.")
        action, tasks = body.get("action"), body.get("tasks")
        if (action not in ("cancel", "retry", "redownload") or not isinstance(tasks, list)
                or not 1 <= len(tasks) <= 300 or not all(
                    isinstance(item, dict)
                    and all(isinstance(item.get(k), str) for k in ("batch_id", "task_id"))
                    for item in tasks)):
            return _error("INVALID_REQUEST", "批量操作无效 / Invalid batch action.")
        manager = get_runtime(application).task_manager
        operation = {"cancel": manager.cancel, "retry": manager.retry, "redownload": manager.redownload}[action]
        targets = dict.fromkeys((task["batch_id"], task["task_id"]) for task in tasks)
        errors = []
        for batch_id, task_id in targets:
            try:
                operation(batch_id, task_id)
            except (ValueError, KeyError) as error:
                errors.append(dict(batch_id=batch_id, task_id=task_id, message=str(error).strip("'")))
        return jsonify(succeeded=len(targets) - len(errors), errors=errors)

    return application


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--download-dir", type=Path, required=True)
    parser.add_argument("--owned-process-group", action="store_true")
    args = parser.parse_args()
    token = sys.stdin.readline(256).strip()
    if not token:
        parser.error("parent did not provide a bearer token")

    ready_output = sys.stdout
    sys.stdout = sys.stderr
    os.environ["GTD_COOKIE_DIR"] = str(args.data_dir / "cookies")
    os.environ["GTD_LOG_DIR"] = str(args.data_dir / "logs")
    application = create_desktop_app(args.data_dir, args.download_dir, token)
    manager = get_runtime(application).task_manager
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    server = LoopbackServer("127.0.0.1", 0, application)
    server.timeout = 0.2
    parent_closed = Event()

    def watch_parent():
        sys.stdin.read()  # EOF when the shell exits or intentionally drops the pipe.
        parent_closed.set()

    Thread(target=watch_parent, daemon=True, name="parent-watch").start()
    print(f"GTD_READY {server.server_port}", file=ready_output, flush=True)
    try:
        # EOF can arrive before serving the first request.
        while not parent_closed.is_set():
            server.handle_request()
    finally:
        try:
            server.server_close()
            for batch in manager.list_batches():
                if batch["all_done"]:
                    continue
                try:
                    tasks = manager.snapshot(batch["id"])["tasks"]
                except KeyError:  # A worker finished and pruned the batch.
                    continue
                for task in tasks:
                    if task["can_cancel"]:
                        try:
                            manager.cancel(batch["id"], task["id"])
                        except (KeyError, ValueError):
                            pass  # Task completed or changed cancellation mode in flight.
            manager.shutdown(wait=manager.wait_for_idle(2))
        finally:
            if args.owned_process_group and os.name == "posix" and os.getpgrp() == os.getpid():
                # Cover abrupt parent death as well as normal shutdown, including media children.
                os.killpg(os.getpgrp(), signal.SIGKILL)


if __name__ == "__main__":
    main()
