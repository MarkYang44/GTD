"""Thread-safe primitives used to control download attempts."""

from __future__ import annotations

import re
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from download_errors import (
    DownloadCancelled,
    DownloadFailure,
    classify_download_error,
    public_error,
)
from download_logging import (
    get_download_logger,
    log_download_event,
    redact_value,
)


class CancellationToken:
    """A cooperative, one-way cancellation signal."""

    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise DownloadCancelled()


@dataclass(frozen=True)
class TaskSeed:
    platform: str
    url: str
    title: str | None = None
    position: int | None = None


class TaskManager:
    """Own a process-wide executor and public task state transitions."""

    TERMINAL_STATES = {"completed", "failed", "cancelled"}
    ACTIVE_STATES = {"running", "running_uninterruptible"}

    def __init__(
        self,
        runner: Callable[..., dict[str, object] | None],
        max_workers: int = 3,
        max_bilibili: int = 2,
        max_batches: int = 100,
        logger=None,
    ) -> None:
        if max_workers < 1 or max_bilibili < 1 or max_batches < 1:
            raise ValueError("任务管理器容量必须大于零")
        self._runner = runner
        self._max_batches = max_batches
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="media-download",
        )
        self._bilibili_executor = ThreadPoolExecutor(
            max_workers=max_bilibili,
            thread_name_prefix="bilibili-download",
        )
        self._global_slots = threading.BoundedSemaphore(max_workers)
        self._batches: dict[str, dict[str, object]] = {}
        self._tokens: dict[str, CancellationToken] = {}
        self._futures: dict[str, Future] = {}
        self._generations: dict[str, int] = {}
        self._version_reservations: dict[str, set[int]] = {}
        self._logger = logger if logger is not None else get_download_logger()

    def create_batch(
        self,
        entries: list[TaskSeed],
        media_type: str,
        audio_format: str,
        speed_mode: str,
        download_dir: str | None = None,
    ) -> dict[str, object]:
        if not isinstance(entries, list) or not entries:
            raise ValueError("下载批次不能为空")
        if len(entries) > 100:
            raise ValueError("一次最多创建 100 个下载任务")
        if not all(isinstance(entry, TaskSeed) for entry in entries):
            raise ValueError("下载任务格式无效")

        with self._lock:
            batch_id = uuid.uuid4().hex
            tasks = []
            for index, entry in enumerate(entries, start=1):
                version_key = self._seed_version_key(
                    entry,
                    media_type,
                    audio_format,
                    download_dir,
                )
                output_version = self._reserve_version_locked(version_key)
                tasks.append(
                    self._new_task(
                        entry,
                        index,
                        media_type,
                        audio_format,
                        speed_mode,
                        download_dir=download_dir,
                        output_version=output_version,
                        version_key=version_key,
                    )
                )
            batch: dict[str, object] = {
                "id": batch_id,
                "created_at": time.time(),
                "media_type": media_type,
                "audio_format": audio_format,
                "speed_mode": speed_mode,
                "download_dir": download_dir,
                "tasks": tasks,
            }
            self._batches[batch_id] = batch
            log_download_event(
                self._logger,
                "batch_created",
                batch_id=batch_id,
                task_count=len(tasks),
                media_type=media_type,
                audio_format=audio_format,
                speed_mode=speed_mode,
            )
            for task in tasks:
                self._submit_locked(batch_id, task)
            self._prune_locked()
            return self._public_batch(batch)

    def snapshot(self, batch_id: str) -> dict[str, object]:
        with self._lock:
            batch = self._require_batch(batch_id)
            return self._public_batch(batch)

    def cancel(self, batch_id: str, task_id: str) -> dict[str, object]:
        with self._lock:
            task = self._require_task(batch_id, task_id)
            status = task["status"]
            if status == "running_uninterruptible":
                raise ValueError("aria2c 极速任务不可取消，请等待下载完成")
            if status in self.TERMINAL_STATES:
                raise ValueError("当前任务状态不可取消")

            token = self._tokens[task_id]
            token.cancel()
            task["cancel_requested"] = True
            if status == "queued":
                task["status"] = "cancelled"
                future = self._futures.get(task_id)
                if future:
                    future.cancel()
                log_download_event(
                    self._logger,
                    "cancelled",
                    batch_id=batch_id,
                    task_id=task_id,
                    platform=task["platform"],
                    attempt_number=task["attempt_count"],
                )
                self._prune_locked()
            else:
                log_download_event(
                    self._logger,
                    "cancel_requested",
                    batch_id=batch_id,
                    task_id=task_id,
                    platform=task["platform"],
                    attempt_number=task["attempt_count"],
                )
            return self._public_task(task)

    def retry(self, batch_id: str, task_id: str) -> dict[str, object]:
        with self._lock:
            task = self._require_task(batch_id, task_id)
            if task["status"] not in {"failed", "cancelled"}:
                raise ValueError("当前任务状态不可重试")
            error = task.get("error")
            if (
                task["status"] == "failed"
                and isinstance(error, dict)
                and not error.get("retryable")
            ):
                raise ValueError("该错误不支持重试")
            task.update(
                {
                    "status": "queued",
                    "error": None,
                    "result": None,
                    "progress": None,
                    "cancel_requested": False,
                }
            )
            self._clear_progress_fields(task)
            log_download_event(
                self._logger,
                "retry",
                batch_id=batch_id,
                task_id=task_id,
                platform=task["platform"],
                attempt_number=task["attempt_count"] + 1,
            )
            self._submit_locked(batch_id, task)
            return self._public_task(task)

    def retry_failed(self, batch_id: str) -> dict[str, object]:
        with self._lock:
            batch = self._require_batch(batch_id)
            task_ids = [
                task["id"]
                for task in batch["tasks"]
                if task["status"] == "failed"
                and isinstance(task.get("error"), dict)
                and task["error"].get("retryable")
            ]
            for task_id in task_ids:
                self.retry(batch_id, task_id)
            return self._public_batch(batch)

    def redownload(self, batch_id: str, task_id: str) -> dict[str, object]:
        with self._lock:
            batch = self._require_batch(batch_id)
            source = self._require_task(batch_id, task_id)
            if source["status"] != "completed":
                raise ValueError("仅已完成任务可以重新下载")
            result = source.get("result")
            filepath = result.get("filepath") if isinstance(result, dict) else None
            if not isinstance(filepath, str) or not filepath:
                raise ValueError("已完成任务缺少输出文件信息")

            reservation_key = str(source.get("version_key") or filepath)
            base_filepath = str(source.get("base_filepath") or filepath)
            version = self._reserve_version_locked(
                reservation_key,
                start=2,
                base_filepath=base_filepath,
            )

            seed = TaskSeed(
                str(source["platform"]),
                str(source["url"]),
                source.get("title"),
                source.get("position"),
            )
            task = self._new_task(
                seed,
                len(batch["tasks"]) + 1,
                str(source["media_type"]),
                str(source["audio_format"]),
                str(source["speed_mode"]),
                download_dir=source.get("download_dir"),
                output_version=version,
                version_key=reservation_key,
            )
            batch["tasks"].append(task)
            log_download_event(
                self._logger,
                "redownload",
                batch_id=batch_id,
                task_id=task["id"],
                source_task_id=task_id,
                platform=task["platform"],
                output_version=version,
            )
            self._submit_locked(batch_id, task)
            return self._public_task(task)

    def wait_for_idle(self, timeout: float = 5) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                busy = any(
                    task["status"] not in self.TERMINAL_STATES
                    for batch in self._batches.values()
                    for task in batch["tasks"]
                )
            if not busy:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)
        self._bilibili_executor.shutdown(wait=wait)

    def _new_task(
        self,
        seed: TaskSeed,
        index: int,
        media_type: str,
        audio_format: str,
        speed_mode: str,
        download_dir: str | None = None,
        output_version: int = 1,
        version_key: str | None = None,
    ) -> dict[str, object]:
        return {
            "id": uuid.uuid4().hex,
            "index": index,
            "platform": seed.platform,
            "url": seed.url,
            "title": seed.title,
            "position": seed.position,
            "media_type": media_type,
            "audio_format": audio_format,
            "speed_mode": speed_mode,
            "download_dir": download_dir,
            "speed_mode_used": None,
            "turbo_fallback": False,
            "output_version": output_version,
            "version_key": version_key,
            "base_filepath": None,
            "status": "queued",
            "attempt_count": 0,
            "attempts": [],
            "error": None,
            "result": None,
            "progress": None,
            "cancel_requested": False,
        }

    def _submit_locked(
        self,
        batch_id: str,
        task: dict[str, object],
    ) -> None:
        task_id = str(task["id"])
        generation = self._generations.get(task_id, 0) + 1
        self._generations[task_id] = generation
        token = CancellationToken()
        self._tokens[task_id] = token
        executor = (
            self._bilibili_executor
            if task["platform"] == "bilibili"
            else self._executor
        )
        self._futures[task_id] = executor.submit(
            self._execute,
            batch_id,
            task_id,
            generation,
            token,
        )

    def _execute(
        self,
        batch_id: str,
        task_id: str,
        generation: int,
        token: CancellationToken,
    ) -> None:
        with self._global_slots:
            self._run_attempt(batch_id, task_id, generation, token)

    def _run_attempt(
        self,
        batch_id: str,
        task_id: str,
        generation: int,
        token: CancellationToken,
    ) -> None:
        with self._lock:
            if self._generations.get(task_id) != generation:
                return
            task = self._require_task(batch_id, task_id)
            if task["status"] == "cancelled" or token.cancelled:
                return
            task["status"] = "running"
            task["attempt_count"] += 1
            attempt_number = task["attempt_count"]
            attempt = {
                "number": attempt_number,
                "status": "running",
                "started_at": time.time(),
                "finished_at": None,
                "output_version": task["output_version"],
                "error": None,
            }
            task["attempts"].append(attempt)
            started_at = time.monotonic()
            runner_fields = {
                "platform": task["platform"],
                "media_type": task["media_type"],
                "audio_format": task["audio_format"],
                "speed_mode": task["speed_mode"],
                "output_version": task["output_version"],
            }
            url = str(task["url"])
            log_download_event(
                self._logger,
                "attempt_started",
                batch_id=batch_id,
                task_id=task_id,
                attempt_number=attempt_number,
                **runner_fields,
            )

        def relay(event: str, data: dict[str, object]) -> None:
            with self._lock:
                if self._generations.get(task_id) != generation:
                    return
                current = self._require_task(batch_id, task_id)
                if current["status"] in self.TERMINAL_STATES:
                    return
                if event == "mode":
                    if data.get("speed_mode") == "turbo" and token.cancelled:
                        raise DownloadCancelled()
                    current["speed_mode_used"] = data.get("speed_mode")
                    current["turbo_fallback"] = bool(
                        data.get("turbo_fallback")
                    )
                    if data.get("speed_mode") == "turbo":
                        current["status"] = "running_uninterruptible"
                    log_download_event(
                        self._logger,
                        "mode",
                        batch_id=batch_id,
                        task_id=task_id,
                        attempt_number=attempt_number,
                        speed_mode=data.get("speed_mode"),
                        turbo_fallback=bool(data.get("turbo_fallback")),
                    )
                elif event == "progress":
                    current.pop("postprocessing", None)
                    current["progress"] = deepcopy(data)
                    for key in (
                        "percent_text",
                        "speed_mbps",
                        "speed_text",
                        "eta_text",
                        "total_size_bytes",
                        "total_size_text",
                        "total_size_is_estimate",
                    ):
                        if key in data:
                            current[key] = data[key]
                elif event == "postprocessing":
                    current["progress"] = None
                    self._clear_progress_fields(current)
                    current["postprocessing"] = deepcopy(data)

        try:
            result = self._runner(
                url,
                platform=runner_fields["platform"],
                progress_callback=relay,
                media_type=runner_fields["media_type"],
                audio_format=runner_fields["audio_format"],
                speed_mode=runner_fields["speed_mode"],
                cancel_token=token,
                output_version=runner_fields["output_version"],
                output_dir=task.get("download_dir"),
                raise_errors=True,
            )
            if result is None:
                raise DownloadFailure(
                    classify_download_error(
                        RuntimeError("download returned no result"),
                        str(runner_fields["platform"]),
                    )
                )
            self._finish_attempt(
                batch_id,
                task_id,
                generation,
                "completed",
                started_at,
                result=result,
            )
        except DownloadCancelled as error:
            self._finish_attempt(
                batch_id,
                task_id,
                generation,
                "cancelled",
                started_at,
                error=error,
            )
        except DownloadFailure as error:
            self._finish_attempt(
                batch_id,
                task_id,
                generation,
                "failed",
                started_at,
                error=error,
            )
        except Exception as error:
            self._finish_attempt(
                batch_id,
                task_id,
                generation,
                "failed",
                started_at,
                error=DownloadFailure(
                    classify_download_error(
                        error,
                        str(runner_fields["platform"]),
                    )
                ),
            )

    def _finish_attempt(
        self,
        batch_id: str,
        task_id: str,
        generation: int,
        status: str,
        started_at: float,
        result: dict[str, object] | None = None,
        error: DownloadFailure | None = None,
    ) -> None:
        with self._lock:
            if self._generations.get(task_id) != generation:
                return
            task = self._require_task(batch_id, task_id)
            if task["status"] in self.TERMINAL_STATES:
                return
            attempt = task["attempts"][-1]
            attempt["status"] = status
            attempt["finished_at"] = time.time()
            elapsed = round(time.monotonic() - started_at, 3)
            event_fields: dict[str, object] = {
                "batch_id": batch_id,
                "task_id": task_id,
                "platform": task["platform"],
                "media_type": task["media_type"],
                "audio_format": task["audio_format"],
                "speed_mode": task["speed_mode"],
                "attempt_number": task["attempt_count"],
                "elapsed_seconds": elapsed,
            }
            if status == "completed":
                task["result"] = deepcopy(result)
                task["error"] = None
                if isinstance(result, dict):
                    filepath = result.get("filepath")
                    if isinstance(filepath, str) and filepath:
                        output_version = int(task["output_version"])
                        actual_version = result.get("output_version_actual")
                        if (
                            isinstance(actual_version, int)
                            and not isinstance(actual_version, bool)
                            and actual_version >= output_version
                        ):
                            output_version = actual_version
                        elif task["media_type"] == "audio":
                            match = re.search(
                                r"\[[^\]]+\] \((\d+)\)$",
                                Path(filepath).stem,
                            )
                            if match:
                                output_version = max(
                                    output_version,
                                    int(match.group(1)),
                                )
                        task["output_version"] = output_version
                        attempt["output_version"] = output_version
                        key = task.get("version_key")
                        if isinstance(key, str):
                            self._version_reservations.setdefault(
                                key,
                                set(),
                            ).add(output_version)
                        task["base_filepath"] = self._base_version_path(
                            filepath,
                            output_version,
                        )
            else:
                if error is None:
                    raise ValueError("终止失败任务时必须提供错误")
                safe_error = public_error(error)
                task["error"] = safe_error
                attempt["error"] = deepcopy(safe_error)
                event_fields.update(safe_error)
                event_fields["technical_detail"] = redact_value(
                    error.info.technical_detail
                )
            task["status"] = status
            task["cancel_requested"] = False
            self._clear_progress_fields(task)
            log_download_event(self._logger, status, **event_fields)
            self._prune_locked()

    def _public_batch(self, batch: dict[str, object]) -> dict[str, object]:
        tasks = [self._public_task(task) for task in batch["tasks"]]
        counts = {
            "active": sum(task["status"] in self.ACTIVE_STATES for task in tasks),
            "queued": sum(task["status"] == "queued" for task in tasks),
            "completed": sum(task["status"] == "completed" for task in tasks),
            "failed": sum(task["status"] == "failed" for task in tasks),
            "cancelled": sum(task["status"] == "cancelled" for task in tasks),
        }
        return {
            "id": batch["id"],
            "media_type": batch["media_type"],
            "audio_format": batch["audio_format"],
            "speed_mode": batch["speed_mode"],
            "download_dir": batch.get("download_dir"),
            "total": len(tasks),
            **counts,
            "all_done": bool(tasks)
            and all(task["status"] in self.TERMINAL_STATES for task in tasks),
            "tasks": tasks,
        }

    def _public_task(self, task: dict[str, object]) -> dict[str, object]:
        status = task["status"]
        public = {
            key: deepcopy(value)
            for key, value in task.items()
            if key not in {"cancel_requested", "version_key", "base_filepath"}
        }
        public["can_cancel"] = status == "queued" or (
            status == "running" and not task["cancel_requested"]
        )
        error = task.get("error")
        public["can_retry"] = status == "cancelled" or (
            status == "failed"
            and isinstance(error, dict)
            and bool(error.get("retryable"))
        )
        public["can_redownload"] = status == "completed"
        return public

    def _require_batch(self, batch_id: str) -> dict[str, object]:
        batch = self._batches.get(batch_id)
        if batch is None:
            raise KeyError("下载批次不存在")
        return batch

    def _require_task(
        self,
        batch_id: str,
        task_id: str,
    ) -> dict[str, object]:
        batch = self._require_batch(batch_id)
        for task in batch["tasks"]:
            if task["id"] == task_id:
                return task
        raise KeyError("下载任务不存在")

    def _prune_locked(self) -> None:
        while len(self._batches) > self._max_batches:
            removable = next(
                (
                    batch_id
                    for batch_id, batch in self._batches.items()
                    if all(
                        task["status"] in self.TERMINAL_STATES
                        for task in batch["tasks"]
                    )
                ),
                None,
            )
            if removable is None:
                return
            batch = self._batches.pop(removable)
            for task in batch["tasks"]:
                task_id = str(task["id"])
                self._tokens.pop(task_id, None)
                self._futures.pop(task_id, None)
                self._generations.pop(task_id, None)
            self._rebuild_version_reservations_locked()

    @staticmethod
    def _clear_progress_fields(task: dict[str, object]) -> None:
        for key in (
            "percent_text",
            "speed_mbps",
            "speed_text",
            "eta_text",
            "total_size_bytes",
            "total_size_text",
            "total_size_is_estimate",
            "postprocessing",
        ):
            task.pop(key, None)

    @staticmethod
    def _version_path_exists(filepath: str, version: int) -> bool:
        path = Path(filepath)
        candidate = path.with_name(f"{path.stem} ({version}){path.suffix}")
        return candidate.exists()

    @staticmethod
    def _seed_version_key(
        seed: TaskSeed,
        media_type: str,
        audio_format: str,
        download_dir: str | None = None,
    ) -> str:
        identity = (seed.title or seed.url).strip().casefold()
        location = str(download_dir or "").strip().casefold()
        return "\x1f".join(
            (seed.platform, media_type, audio_format, location, identity)
        )

    def _reserve_version_locked(
        self,
        reservation_key: str,
        start: int = 1,
        base_filepath: str | None = None,
    ) -> int:
        reserved = self._version_reservations.setdefault(reservation_key, set())
        version = start
        while version in reserved or (
            base_filepath is not None
            and self._version_path_exists(base_filepath, version)
        ):
            version += 1
        reserved.add(version)
        return version

    @staticmethod
    def _base_version_path(filepath: str, output_version: int) -> str:
        path = Path(filepath)
        suffix = "" if output_version == 1 else f" ({output_version})"
        stem = path.stem
        if suffix and stem.endswith(suffix):
            stem = stem[: -len(suffix)]
        return str(path.with_name(f"{stem}{path.suffix}"))

    def _rebuild_version_reservations_locked(self) -> None:
        reservations: dict[str, set[int]] = {}
        for batch in self._batches.values():
            for task in batch["tasks"]:
                key = task.get("version_key")
                version = task.get("output_version")
                if isinstance(key, str) and isinstance(version, int):
                    reservations.setdefault(key, set()).add(version)
        self._version_reservations = reservations
