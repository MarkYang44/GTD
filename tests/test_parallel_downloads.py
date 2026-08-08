import contextlib
import io
import threading
import time
import unittest
from unittest.mock import patch

import downloader


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

        with patch("downloader.download_video", side_effect=fake_download):
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

        with patch("downloader.download_video", side_effect=fake_download):
            downloader.download_tasks(tasks)

        self.assertEqual(maximum_active, 3)
        self.assertEqual(maximum_bilibili, 2)

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

        with patch("downloader.download_video", side_effect=fake_download):
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

        with patch("downloader.download_video", side_effect=fake_download):
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

        with patch("downloader.download_video", side_effect=fake_download):
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

    def test_audio_media_type_is_forwarded_to_every_task(self):
        tasks = [
            (downloader.YOUTUBE, "https://youtu.be/first"),
            (downloader.INSTAGRAM, "https://instagram.com/reel/second"),
        ]

        def fake_download(url, **kwargs):
            return {"title": url, "media_type": kwargs["media_type"]}

        with patch("downloader.download_video", side_effect=fake_download) as mocked:
            results = downloader.download_tasks(tasks, media_type=downloader.AUDIO)

        self.assertEqual(mocked.call_count, 2)
        self.assertTrue(
            all(call.kwargs["media_type"] == downloader.AUDIO for call in mocked.call_args_list)
        )
        self.assertEqual(
            [result["media_type"] for _, result in results],
            [downloader.AUDIO, downloader.AUDIO],
        )


if __name__ == "__main__":
    unittest.main()
