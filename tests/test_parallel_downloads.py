import contextlib
import io
import threading
import time
import unittest
from unittest.mock import patch

import downloader
from download_errors import DownloadCancelled, DownloadErrorInfo, DownloadFailure


class ParallelDownloadTests(unittest.TestCase):
    def test_bilibili_runs_at_most_two_tasks_concurrently(self):
        tasks = [
            (downloader.BILIBILI, f"https://b23.tv/video-{index}")
            for index in range(5)
        ]
        lock = threading.Lock()
        active = 0
        maximum_active = 0

        def fake_download(url, **kwargs):
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return {"title": url}

        with patch("downloader._download_video_with_prepared_dir", side_effect=fake_download):
            results = downloader.download_tasks(tasks)

        self.assertEqual(maximum_active, 2)
        self.assertEqual(
            [result["title"] for _, result in results],
            [url for _, url in tasks],
        )

    def test_mixed_batch_keeps_three_global_workers_and_two_bilibili_slots(self):
        tasks = [
            (downloader.BILIBILI, "https://b23.tv/first"),
            (downloader.BILIBILI, "https://b23.tv/second"),
            (downloader.YOUTUBE, "https://youtu.be/third"),
        ]
        barrier = threading.Barrier(3)
        lock = threading.Lock()
        active = 0
        active_bilibili = 0
        maximum_active = 0
        maximum_bilibili = 0

        def fake_download(url, platform=None, **kwargs):
            nonlocal active, active_bilibili, maximum_active, maximum_bilibili
            with lock:
                active += 1
                if platform == downloader.BILIBILI:
                    active_bilibili += 1
                maximum_active = max(maximum_active, active)
                maximum_bilibili = max(maximum_bilibili, active_bilibili)
            barrier.wait(timeout=1)
            with lock:
                active -= 1
                if platform == downloader.BILIBILI:
                    active_bilibili -= 1
            return {"title": url}

        with patch("downloader._download_video_with_prepared_dir", side_effect=fake_download):
            downloader.download_tasks(tasks)

        self.assertEqual(maximum_active, 3)
        self.assertEqual(maximum_bilibili, 2)

    def test_waiting_bilibili_task_emits_started_after_a_slot_opens(self):
        tasks = [
            (downloader.BILIBILI, f"https://b23.tv/video-{index}")
            for index in range(3)
        ]
        event_lock = threading.Lock()
        download_lock = threading.Lock()
        two_downloads_active = threading.Event()
        release_downloads = threading.Event()
        started_indices = []
        entered_downloads = 0

        def callback(index, event, data):
            if event == "started":
                with event_lock:
                    started_indices.append(index)

        def fake_download(url, **kwargs):
            nonlocal entered_downloads
            with download_lock:
                entered_downloads += 1
                if entered_downloads == 2:
                    two_downloads_active.set()
            release_downloads.wait(timeout=1)
            return {"title": url}

        with patch("downloader._download_video_with_prepared_dir", side_effect=fake_download):
            batch_thread = threading.Thread(
                target=downloader.download_tasks,
                args=(tasks, callback),
            )
            batch_thread.start()
            try:
                self.assertTrue(two_downloads_active.wait(timeout=1))
                time.sleep(0.02)
                with event_lock:
                    waiting_started_count = len(started_indices)
            finally:
                release_downloads.set()
                batch_thread.join(timeout=1)

        self.assertFalse(batch_thread.is_alive())
        self.assertEqual(waiting_started_count, 2)
        self.assertEqual(started_indices, [0, 1, 2])

    def test_download_tasks_runs_at_most_three_concurrently_and_preserves_order(self):
        tasks = [
            (downloader.YOUTUBE, f"https://youtu.be/video-{index}")
            for index in range(5)
        ]
        lock = threading.Lock()
        active = 0
        maximum_active = 0

        def fake_download(url, **kwargs):
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.02 * (5 - int(url.rsplit("-", 1)[1])))
            with lock:
                active -= 1
            return {"title": url}

        with patch("downloader._download_video_with_prepared_dir", side_effect=fake_download):
            results = downloader.download_tasks(tasks)

        self.assertEqual(maximum_active, 3)
        self.assertEqual(
            [result["title"] for _, result in results],
            [url for _, url in tasks],
        )

    def test_progress_events_keep_each_tasks_original_index(self):
        tasks = [
            (downloader.YOUTUBE, "https://youtu.be/first"),
            (downloader.INSTAGRAM, "https://instagram.com/reel/second"),
        ]
        events = []
        event_lock = threading.Lock()

        def callback(index, event, data):
            with event_lock:
                events.append((index, event, data))

        def fake_download(url, progress_callback=None, **kwargs):
            progress_callback("progress", {"percent_text": url})
            return {"title": url}

        with patch("downloader._download_video_with_prepared_dir", side_effect=fake_download):
            downloader.download_tasks(tasks, progress_callback=callback)

        for index, (_, url) in enumerate(tasks):
            task_events = [
                (event, data)
                for event_index, event, data in events
                if event_index == index
            ]
            self.assertEqual(
                [event for event, _ in task_events],
                ["started", "progress", "completed"],
            )
            self.assertEqual(task_events[1][1]["percent_text"], url)

    def test_worker_exception_marks_only_that_task_failed(self):
        tasks = [
            (downloader.YOUTUBE, "https://youtu.be/good-1"),
            (downloader.YOUTUBE, "https://youtu.be/bad"),
            (downloader.YOUTUBE, "https://youtu.be/good-2"),
        ]
        events = []

        def fake_download(url, **kwargs):
            if url.endswith("bad"):
                raise RuntimeError("boom")
            return {"title": url}

        with patch("downloader._download_video_with_prepared_dir", side_effect=fake_download):
            with contextlib.redirect_stdout(io.StringIO()):
                results = downloader.download_tasks(
                    tasks,
                    progress_callback=lambda index, event, data: events.append((index, event)),
                )

        self.assertIsNotNone(results[0][1])
        self.assertIsNone(results[1][1])
        self.assertIsNotNone(results[2][1])
        self.assertIn((1, "failed"), events)
        self.assertIn((2, "completed"), events)

    def test_structured_failure_event_keeps_public_error_fields(self):
        events = []
        failure = DownloadFailure(
            DownloadErrorInfo(
                "NETWORK_TIMEOUT",
                "网络超时",
                "请重试",
                True,
                "private timeout detail",
            )
        )

        with patch("downloader._download_video_with_prepared_dir", side_effect=failure):
            downloader.download_tasks(
                [(downloader.YOUTUBE, "https://youtu.be/fail")],
                progress_callback=lambda index, event, data: events.append(
                    (event, data)
                ),
            )

        event, data = events[-1]
        self.assertEqual(event, "failed")
        self.assertEqual(data["error_code"], "NETWORK_TIMEOUT")
        self.assertNotIn("technical_detail", data)

    def test_cancelled_worker_emits_cancelled_terminal_event(self):
        events = []

        with patch(
            "downloader._download_video_with_prepared_dir",
            side_effect=DownloadCancelled(),
        ):
            downloader.download_tasks(
                [(downloader.YOUTUBE, "https://youtu.be/cancel")],
                progress_callback=lambda index, event, data: events.append(
                    (event, data)
                ),
            )

        self.assertEqual(events[-1][0], "cancelled")
        self.assertEqual(events[-1][1]["error_code"], "CANCELLED")

    def test_audio_media_type_is_forwarded_to_every_task(self):
        tasks = [
            (downloader.YOUTUBE, "https://youtu.be/first"),
            (downloader.INSTAGRAM, "https://instagram.com/reel/second"),
        ]

        def fake_download(url, **kwargs):
            return {
                "title": url,
                "media_type": kwargs["media_type"],
                "audio_format": kwargs["audio_format"],
            }

        with patch("downloader._download_video_with_prepared_dir", side_effect=fake_download) as mocked:
            results = downloader.download_tasks(
                tasks,
                media_type=downloader.AUDIO,
                audio_format=downloader.FLAC,
            )

        self.assertEqual(mocked.call_count, 2)
        self.assertTrue(
            all(call.kwargs["media_type"] == downloader.AUDIO for call in mocked.call_args_list)
        )
        self.assertTrue(
            all(
                call.kwargs["audio_format"] == downloader.FLAC
                for call in mocked.call_args_list
            )
        )
        self.assertEqual(
            [result["media_type"] for _, result in results],
            [downloader.AUDIO, downloader.AUDIO],
        )
        self.assertEqual(
            [result["audio_format"] for _, result in results],
            [downloader.FLAC, downloader.FLAC],
        )

    def test_speed_mode_is_forwarded_to_every_task(self):
        tasks = [
            (downloader.BILIBILI, "https://b23.tv/first"),
            (downloader.YOUTUBE, "https://youtu.be/second"),
        ]

        with patch(
            "downloader._download_video_with_prepared_dir",
            side_effect=lambda url, **kwargs: {
                "title": url,
                "speed_mode_requested": kwargs["speed_mode"],
            },
        ) as mocked:
            results = downloader.download_tasks(
                tasks,
                speed_mode=downloader.TURBO,
            )

        self.assertEqual(mocked.call_count, 2)
        self.assertTrue(all(
            call.kwargs["speed_mode"] == downloader.TURBO
            for call in mocked.call_args_list
        ))
        self.assertTrue(all(
            result["speed_mode_requested"] == downloader.TURBO
            for _, result in results
        ))

    def test_unknown_batch_speed_mode_fails_before_workers_start(self):
        for speed_mode in ("warp", []):
            with (
                self.subTest(speed_mode=speed_mode),
                patch("downloader.ThreadPoolExecutor") as executor,
            ):
                with self.assertRaisesRegex(ValueError, "速度模式"):
                    downloader.download_tasks(
                        [(downloader.BILIBILI, "https://b23.tv/example")],
                        speed_mode=speed_mode,
                    )

                executor.assert_not_called()

    def test_unknown_batch_media_type_fails_before_workers_start(self):
        with patch("downloader.ThreadPoolExecutor") as executor:
            with self.assertRaisesRegex(ValueError, "下载类型"):
                downloader.download_tasks(
                    [(downloader.YOUTUBE, "https://youtu.be/example")],
                    media_type="document",
                )

        executor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
