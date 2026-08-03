import unittest
from pathlib import Path
from unittest.mock import patch

import app as web_app
import downloader


class WebConfigurationTests(unittest.TestCase):
    def test_default_web_port_and_readme_are_8233(self):
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertEqual(web_app.WEB_HOST, "127.0.0.1")
        self.assertEqual(web_app.WEB_PORT, 8233)
        self.assertIn("http://127.0.0.1:8233", readme)
        self.assertNotIn("http://127.0.0.1:5000", readme)


class WebProgressStateTests(unittest.TestCase):
    def test_batch_tasks_start_with_empty_progress(self):
        batch = web_app._create_batch([(downloader.YOUTUBE, "https://youtu.be/example")])

        self.assertIn("progress", batch["tasks"][0])
        self.assertIsNone(batch["tasks"][0]["progress"])

    def test_progress_event_updates_current_task_metrics(self):
        batch = web_app._create_batch([(downloader.YOUTUBE, "https://youtu.be/example")])

        web_app._apply_progress_event(
            batch,
            0,
            "progress",
            {
                "percent_text": "12.3%",
                "speed_text": "2.50 MB/s",
                "eta_text": "01:05",
            },
        )

        task = batch["tasks"][0]
        self.assertEqual(task["status"], "downloading")
        self.assertEqual(task["progress"]["percent_text"], "12.3%")
        self.assertEqual(task["progress"]["speed_text"], "2.50 MB/s")
        self.assertEqual(task["progress"]["eta_text"], "01:05")

    def test_completion_clears_stale_progress_metrics(self):
        batch = web_app._create_batch([(downloader.YOUTUBE, "https://youtu.be/example")])
        web_app._apply_progress_event(
            batch,
            0,
            "progress",
            {"speed_text": "2.50 MB/s", "eta_text": "01:05"},
        )

        web_app._apply_progress_event(batch, 0, "completed", {"title": "done"})

        task = batch["tasks"][0]
        self.assertEqual(task["status"], "completed")
        self.assertIsNone(task["progress"])

    def test_duplicate_terminal_event_does_not_increment_count_twice(self):
        batch = web_app._create_batch([(downloader.YOUTUBE, "https://youtu.be/example")])

        web_app._apply_progress_event(batch, 0, "completed", {"title": "done"})
        web_app._apply_progress_event(batch, 0, "completed", {"title": "done"})

        self.assertEqual(batch["completed"], 1)
        self.assertEqual(batch["failed"], 0)

    def test_progress_after_terminal_event_does_not_regress_status(self):
        batch = web_app._create_batch([(downloader.YOUTUBE, "https://youtu.be/example")])

        web_app._apply_progress_event(batch, 0, "failed", {"error": "failed"})
        web_app._apply_progress_event(batch, 0, "progress", {"percent_text": "99%"})

        self.assertEqual(batch["tasks"][0]["status"], "failed")
        self.assertEqual(batch["failed"], 1)

    def test_frontend_renders_speed_and_eta_inside_task_card(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("renderDownloadProgress", html)
        self.assertIn("下载速度", html)
        self.assertIn("预计剩余", html)

    def test_frontend_has_separate_video_and_audio_download_inputs(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn('id="videoUrls"', html)
        self.assertIn('id="audioUrls"', html)
        self.assertIn('id="videoDownloadButton"', html)
        self.assertIn('id="audioDownloadButton"', html)
        self.assertIn("startDownload('video')", html)
        self.assertIn("startDownload('audio')", html)

    def test_frontend_sends_media_type_and_disables_both_sections(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("media_type: mediaType", html)
        self.assertIn("setControlsDisabled(true)", html)
        self.assertIn("videoDownloadButton", html)
        self.assertIn("audioDownloadButton", html)

    def test_frontend_renders_audio_results_without_video_resolution(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn('batch.media_type === "audio"', html)
        self.assertIn("格式:", html)
        self.assertIn("音频编码:", html)

    def test_task_metadata_wraps_long_output_paths_on_mobile(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertRegex(
            html,
            r"\.task-meta\s*\{[^}]*overflow-wrap:\s*anywhere",
        )

    def test_frontend_uses_dark_petronas_theme_tokens(self):
        html = Path("templates/index.html").read_text(encoding="utf-8").lower()

        self.assertIn("--background: #0f172a", html)
        self.assertIn("--surface: #111827", html)
        self.assertIn("--primary: #009b95", html)
        self.assertIn("--accent: #00a19b", html)

    def test_frontend_has_operational_metrics_with_expected_defaults(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertRegex(html, r'id="metric-active"[^>]*>00<')
        self.assertRegex(html, r'id="metric-queue"[^>]*>00<')
        self.assertRegex(html, r'id="metric-limit"[^>]*>03<')

    def test_frontend_computes_active_and_queued_task_counts(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("function updateOperationalMetrics(batch)", html)
        self.assertIn('task.status === "downloading"', html)
        self.assertIn('task.status === "pending"', html)
        self.assertIn('padStart(2, "0")', html)

    def test_frontend_has_progressive_motion_and_reduced_motion_fallback(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn('id="scroll-progress"', html)
        self.assertIn('id="pointer-light"', html)
        self.assertIn("data-reveal", html)
        self.assertIn("IntersectionObserver", html)
        self.assertIn("requestAnimationFrame", html)
        self.assertIn("prefers-reduced-motion: reduce", html)

    def test_frontend_has_approved_page_structure_without_service_label(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn('class="topbar"', html)
        self.assertIn('class="hero', html)
        self.assertIn('class="download-grid"', html)
        self.assertIn('class="task-panel', html)
        self.assertIn("Capture. Convert. Keep.", html)
        self.assertNotIn("LOCAL SERVICE · 8233", html)


class WebDownloadApiTests(unittest.TestCase):
    def setUp(self):
        web_app._batches.clear()
        self.client = web_app.app.test_client()

    def test_download_api_defaults_to_video_batch(self):
        with patch("app.threading.Thread"):
            response = self.client.post(
                "/api/download",
                json={"urls": ["https://youtu.be/example"]},
            )

        self.assertEqual(response.status_code, 200)
        batch = web_app._batches[response.get_json()["batch_id"]]
        self.assertEqual(batch["media_type"], downloader.VIDEO)

    def test_download_api_creates_audio_batch_and_forwards_media_type(self):
        with patch("app.threading.Thread") as thread_class:
            response = self.client.post(
                "/api/download",
                json={
                    "urls": ["https://youtu.be/example"],
                    "media_type": downloader.AUDIO,
                },
            )

        self.assertEqual(response.status_code, 200)
        batch = web_app._batches[response.get_json()["batch_id"]]
        self.assertEqual(batch["media_type"], downloader.AUDIO)
        self.assertEqual(thread_class.call_args.kwargs["args"][2], downloader.AUDIO)

    def test_download_api_rejects_unknown_media_type(self):
        with patch("app.threading.Thread") as thread_class:
            response = self.client.post(
                "/api/download",
                json={
                    "urls": ["https://youtu.be/example"],
                    "media_type": "unknown",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("下载类型", response.get_json()["error"])
        thread_class.assert_not_called()

    def test_download_api_rejects_non_string_media_type(self):
        with patch("app.threading.Thread") as thread_class:
            response = self.client.post(
                "/api/download",
                json={
                    "urls": ["https://youtu.be/example"],
                    "media_type": [downloader.AUDIO],
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("下载类型", response.get_json()["error"])
        thread_class.assert_not_called()


if __name__ == "__main__":
    unittest.main()
