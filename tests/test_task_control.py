import threading
import time
import unittest
from unittest.mock import patch

from download_errors import DownloadErrorInfo, DownloadFailure
from task_control import TaskManager, TaskSeed


class TaskManagerTests(unittest.TestCase):
    def test_queued_task_cancels_without_calling_runner(self):
        release = threading.Event()
        calls = []

        def runner(url, **kwargs):
            calls.append(url)
            release.wait(1)
            return {"title": url, "filepath": f"/tmp/{len(calls)}.mp4"}

        manager = TaskManager(runner, max_workers=1)
        batch = manager.create_batch(
            [
                TaskSeed("youtube", "https://youtu.be/one", "One", 1),
                TaskSeed("youtube", "https://youtu.be/two", "Two", 2),
            ],
            "video",
            "mp3",
            "standard",
        )
        second_id = batch["tasks"][1]["id"]
        manager.cancel(batch["id"], second_id)
        release.set()
        manager.shutdown()

        snapshot = manager.snapshot(batch["id"])
        self.assertEqual(snapshot["tasks"][1]["status"], "cancelled")
        self.assertEqual(calls, ["https://youtu.be/one"])
        self.assertEqual(snapshot["completed"], 1)
        self.assertEqual(snapshot["cancelled"], 1)
        self.assertTrue(snapshot["all_done"])

    def test_retry_reuses_task_and_appends_attempt(self):
        attempts = 0

        def runner(url, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise DownloadFailure(
                    DownloadErrorInfo(
                        "NETWORK_TIMEOUT",
                        "超时",
                        "重试",
                        True,
                        "timeout",
                    )
                )
            return {"title": "ok", "filepath": "/tmp/ok.mp4"}

        manager = TaskManager(runner, max_workers=1)
        batch = manager.create_batch(
            [TaskSeed("youtube", "https://youtu.be/x", "X", 1)],
            "video",
            "mp3",
            "standard",
        )
        self.assertTrue(manager.wait_for_idle())
        task_id = batch["tasks"][0]["id"]
        manager.retry(batch["id"], task_id)
        self.assertTrue(manager.wait_for_idle())
        task = manager.snapshot(batch["id"])["tasks"][0]
        manager.shutdown()

        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["attempt_count"], 2)
        self.assertEqual(len(task["attempts"]), 2)

    def test_running_standard_task_cooperatively_cancels(self):
        entered = threading.Event()

        def runner(url, cancel_token=None, **kwargs):
            entered.set()
            while not cancel_token.cancelled:
                time.sleep(0.005)
            cancel_token.raise_if_cancelled()

        manager = TaskManager(runner, max_workers=1)
        batch = manager.create_batch(
            [TaskSeed("youtube", "https://youtu.be/x")],
            "video",
            "mp3",
            "standard",
        )
        self.assertTrue(entered.wait(1))
        task_id = batch["tasks"][0]["id"]
        manager.cancel(batch["id"], task_id)
        manager.wait_for_idle()
        snapshot = manager.snapshot(batch["id"])
        manager.shutdown()

        self.assertEqual(snapshot["cancelled"], 1)
        self.assertEqual(snapshot["failed"], 0)
        self.assertEqual(snapshot["tasks"][0]["attempts"][0]["status"], "cancelled")

    def test_retry_failed_only_requeues_retryable_failures(self):
        calls = {}

        def runner(url, **kwargs):
            calls[url] = calls.get(url, 0) + 1
            if calls[url] == 1:
                retryable = url.endswith("retry")
                raise DownloadFailure(
                    DownloadErrorInfo(
                        "NETWORK_TIMEOUT" if retryable else "GEO_RESTRICTED",
                        "失败",
                        "建议",
                        retryable,
                        "detail",
                    )
                )
            return {"title": url, "filepath": "/tmp/ok.mp4"}

        manager = TaskManager(runner, max_workers=2)
        batch = manager.create_batch(
            [
                TaskSeed("youtube", "https://x/retry"),
                TaskSeed("youtube", "https://x/fixed"),
            ],
            "video",
            "mp3",
            "standard",
        )
        manager.wait_for_idle()
        manager.retry_failed(batch["id"])
        manager.wait_for_idle()
        snapshot = manager.snapshot(batch["id"])
        manager.shutdown()

        self.assertEqual(snapshot["completed"], 1)
        self.assertEqual(snapshot["failed"], 1)
        self.assertEqual(calls["https://x/retry"], 2)
        self.assertEqual(calls["https://x/fixed"], 1)

    def test_turbo_mode_event_closes_cancel_window_for_fallback_too(self):
        entered = threading.Event()
        release = threading.Event()

        def runner(url, progress_callback=None, **kwargs):
            progress_callback(
                "mode",
                {"speed_mode": "turbo", "turbo_fallback": False},
            )
            progress_callback(
                "mode",
                {"speed_mode": "standard", "turbo_fallback": True},
            )
            entered.set()
            release.wait(1)
            return {"title": "done", "filepath": "/tmp/done.mp4"}

        manager = TaskManager(runner, max_workers=1)
        batch = manager.create_batch(
            [TaskSeed("bilibili", "https://b23.tv/x", "X", 1)],
            "video",
            "mp3",
            "turbo",
        )
        self.assertTrue(entered.wait(1))
        task_id = batch["tasks"][0]["id"]
        with self.assertRaisesRegex(ValueError, "极速任务不可取消"):
            manager.cancel(batch["id"], task_id)
        release.set()
        manager.shutdown()

    def test_redownload_reserves_sequential_versions(self):
        release = threading.Event()

        def runner(url, output_version=1, **kwargs):
            if output_version > 1:
                release.wait(1)
            return {
                "title": "done",
                "filepath": f"/tmp/done{output_version}.mp4",
            }

        manager = TaskManager(runner, max_workers=3)
        batch = manager.create_batch(
            [TaskSeed("youtube", "https://youtu.be/x")],
            "video",
            "mp3",
            "standard",
        )
        manager.wait_for_idle()
        task_id = batch["tasks"][0]["id"]
        first = manager.redownload(batch["id"], task_id)
        second = manager.redownload(batch["id"], task_id)
        release.set()
        manager.shutdown()

        self.assertEqual(
            [first["output_version"], second["output_version"]],
            [2, 3],
        )

    def test_manager_keeps_global_three_and_bilibili_two_limits(self):
        lock = threading.Lock()
        active = 0
        active_bilibili = 0
        maximum_active = 0
        maximum_bilibili = 0

        def runner(url, platform=None, **kwargs):
            nonlocal active, active_bilibili
            nonlocal maximum_active, maximum_bilibili
            with lock:
                active += 1
                if platform == "bilibili":
                    active_bilibili += 1
                maximum_active = max(maximum_active, active)
                maximum_bilibili = max(maximum_bilibili, active_bilibili)
            time.sleep(0.02)
            with lock:
                active -= 1
                if platform == "bilibili":
                    active_bilibili -= 1
            return {"title": url, "filepath": f"/tmp/{url[-1]}.mp4"}

        manager = TaskManager(runner, max_workers=3, max_bilibili=2)
        manager.create_batch(
            [
                TaskSeed("bilibili", f"https://b23.tv/{index}")
                for index in range(5)
            ]
            + [TaskSeed("youtube", "https://youtu.be/x")],
            "video",
            "mp3",
            "standard",
        )
        manager.wait_for_idle()
        manager.shutdown()

        self.assertLessEqual(maximum_active, 3)
        self.assertLessEqual(maximum_bilibili, 2)

    def test_completed_batches_are_pruned_but_active_batch_is_retained(self):
        release = threading.Event()

        def runner(url, **kwargs):
            if url.endswith("active"):
                release.wait(2)
            return {"title": url, "filepath": "/tmp/out.mp4"}

        manager = TaskManager(runner, max_workers=2, max_batches=3)
        active = manager.create_batch(
            [TaskSeed("youtube", "https://youtu.be/active")],
            "video",
            "mp3",
            "standard",
        )
        completed_ids = []
        for index in range(4):
            batch = manager.create_batch(
                [TaskSeed("youtube", f"https://youtu.be/{index}")],
                "video",
                "mp3",
                "standard",
            )
            completed_ids.append(batch["id"])
            while True:
                try:
                    if manager.snapshot(batch["id"])["all_done"]:
                        break
                except KeyError:
                    break
                time.sleep(0.005)

        self.assertEqual(manager.snapshot(active["id"])["id"], active["id"])
        with self.assertRaises(KeyError):
            manager.snapshot(completed_ids[0])
        release.set()
        manager.shutdown()

    def test_logs_error_code_without_leaking_technical_detail_to_snapshot(self):
        failure = DownloadFailure(
            DownloadErrorInfo(
                "NETWORK_TIMEOUT",
                "超时",
                "重试",
                True,
                "token=secret",
            )
        )
        events = []
        with patch(
            "task_control.log_download_event",
            side_effect=lambda logger, event, **fields: events.append(
                (event, fields)
            ),
        ):
            manager = TaskManager(
                lambda url, **kwargs: (_ for _ in ()).throw(failure),
                max_workers=1,
                logger=object(),
            )
            batch = manager.create_batch(
                [TaskSeed("youtube", "https://youtu.be/x")],
                "video",
                "mp3",
                "standard",
            )
            manager.wait_for_idle()
            snapshot = manager.snapshot(batch["id"])
            manager.shutdown()

        self.assertEqual(snapshot["tasks"][0]["error"]["error_code"], "NETWORK_TIMEOUT")
        self.assertNotIn("technical_detail", repr(snapshot))
        failed = [fields for event, fields in events if event == "failed"]
        self.assertEqual(failed[0]["error_code"], "NETWORK_TIMEOUT")
        self.assertNotIn("secret", repr(failed[0]))


if __name__ == "__main__":
    unittest.main()
