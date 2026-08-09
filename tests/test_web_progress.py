import re
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

    def test_frontend_has_mp3_and_source_flac_selector(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn('id="audioFormatMp3"', html)
        self.assertIn('id="audioFormatFlac"', html)
        self.assertIn('name="audioFormat"', html)
        self.assertRegex(
            html,
            r'id="audioFormatMp3"[^>]*value="mp3"[^>]*checked',
        )
        self.assertIn("formatInputs", html)
        self.assertIn("formatInput.disabled = disabled", html)

    def test_frontend_submits_and_renders_audio_format_details(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("audio_format: audioFormat", html)
        self.assertIn('input[name="audioFormat"]:checked', html)
        self.assertIn("源站未提供 FLAC，已自动回退至 MP3 V0", html)
        self.assertIn("source_acodec", html)
        self.assertIn("source_abr_kbps", html)

    def test_frontend_sends_media_type_and_disables_both_sections(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("media_type: mediaType", html)
        self.assertIn("setControlsDisabled(true)", html)
        self.assertIn("videoDownloadButton", html)
        self.assertIn("audioDownloadButton", html)

    def test_frontend_has_independent_video_and_audio_turbo_switches(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn('id="videoTurboToggle"', html)
        self.assertIn('id="audioTurboToggle"', html)
        self.assertEqual(
            html.count('<span class="turbo-title">极速模式</span>'),
            2,
        )
        self.assertIn('fetch("/api/capabilities")', html)
        self.assertIn("aria2c_available", html)

    def test_frontend_submits_section_speed_mode(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn(
            'const speedMode = control.turboToggle.checked ? "turbo" : "standard";',
            html,
        )
        self.assertIn(
            "JSON.stringify({ urls, media_type: mediaType, speed_mode: speedMode, audio_format: audioFormat })",
            html,
        )

    def test_frontend_renders_turbo_and_fallback_states(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("高速下载中", html)
        self.assertIn("极速模式不可用，已切换标准模式", html)
        self.assertIn('t.speed_mode_used === "turbo"', html)
        self.assertIn("!t.turbo_fallback", html)

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

    def test_mobile_hero_clips_decorative_orbit_overflow(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertRegex(
            html,
            r"\.hero\s*\{[^}]*overflow:\s*hidden",
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

    def test_frontend_uses_mark_yang_brand_copy(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn(
            "<title>YTB / Ins Downloader - Designed By Mark Yang</title>",
            html,
        )
        self.assertIn(
            '<span class="brand-mark">Mark Yang</span><span>/ DOWNLOADER</span>',
            html,
        )
        self.assertIn(
            "<strong>最高质量视频，或最高音质音频下载。</strong><br>",
            html,
        )
        self.assertIn("粘贴链接，其余交给下载队列。", html)
        self.assertIn(
            "请仅下载自己拥有权利、获得授权或平台允许下载的视频或音频。 -- Kozeki Ui",
            html,
        )
        self.assertNotIn('<span class="brand-mark">YD</span>', html)
        self.assertNotIn('<span class="brand-mark">MARK YANG</span>', html)

    def test_frontend_loads_only_cormorant_google_font(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("fonts.googleapis.com/css2?", html)
        self.assertIn("family=Cormorant+Garamond:ital,wght@1,400", html)
        self.assertIn("display=swap", html)
        self.assertNotIn("family=Allura", html)
        self.assertNotIn("family=Manrope", html)

    def test_frontend_applies_cormorant_and_palatino_typography(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")
        body_match = re.search(r"\n  body\s*\{([^}]*)\}", html)
        brand_match = re.search(r"\.brand\s*\{([^}]*)\}", html)
        brand_mark_match = re.search(r"\.brand-mark\s*\{([^}]*)\}", html)
        hero_title_match = re.search(r"\.hero h1\s*\{([^}]*)\}", html)
        shared_label_match = re.search(
            r"\.hero-kicker,\s*\.section-index,\s*\.card-index,\s*"
            r"\.metric-label\s*\{([^}]*)\}",
            html,
        )

        self.assertIsNotNone(body_match)
        self.assertIsNotNone(brand_match)
        self.assertIsNotNone(brand_mark_match)
        self.assertIsNotNone(hero_title_match)
        self.assertIsNotNone(shared_label_match)

        body_rule = body_match.group(1)
        brand_rule = brand_match.group(1)
        brand_mark_rule = brand_mark_match.group(1)
        hero_title_rule = hero_title_match.group(1)
        shared_label_rule = shared_label_match.group(1)

        self.assertIn('@font-face {', html)
        self.assertIn('font-family: "Palatino UI Italic";', html)
        self.assertIn('local("Palatino Italic")', html)
        self.assertIn('local("Palatino-Italic")', html)
        self.assertIn('--ui-font: "Palatino UI Italic", Palatino,', html)
        self.assertIn("font-family: var(--ui-font);", body_rule)
        self.assertIn("font-family: var(--ui-font);", brand_rule)
        self.assertIn("font-family: var(--ui-font);", brand_mark_rule)
        self.assertIn(
            'font-family: "Cormorant Garamond", Georgia, serif;',
            hero_title_rule,
        )
        self.assertIn("font-style: italic;", hero_title_rule)
        self.assertIn("font-size: clamp(48px, 8vw, 102px);", hero_title_rule)
        self.assertIn("font-weight: 400;", hero_title_rule)
        self.assertIn("font-family: var(--ui-font);", shared_label_rule)
        self.assertIn("font-size: 11px;", shared_label_rule)
        self.assertIn(
            ".hero h1 { font-size: clamp(44px, 15vw, 64px); }",
            html,
        )


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
        self.assertEqual(batch["audio_format"], downloader.MP3)

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
        self.assertEqual(batch["audio_format"], downloader.MP3)
        self.assertEqual(thread_class.call_args.kwargs["args"][2], downloader.AUDIO)

    def test_download_api_creates_flac_audio_batch(self):
        with patch("app.threading.Thread") as thread_class:
            response = self.client.post(
                "/api/download",
                json={
                    "urls": ["https://b23.tv/example"],
                    "media_type": downloader.AUDIO,
                    "audio_format": downloader.FLAC,
                },
            )

        self.assertEqual(response.status_code, 200)
        batch = web_app._batches[response.get_json()["batch_id"]]
        self.assertEqual(batch["audio_format"], downloader.FLAC)
        self.assertEqual(
            thread_class.call_args.kwargs["args"][4],
            downloader.FLAC,
        )

    def test_download_api_rejects_unknown_and_non_string_audio_format(self):
        for value in ("wav", [downloader.FLAC]):
            with (
                self.subTest(value=value),
                patch("app.threading.Thread") as thread_class,
            ):
                response = self.client.post(
                    "/api/download",
                    json={
                        "urls": ["https://youtu.be/example"],
                        "media_type": downloader.AUDIO,
                        "audio_format": value,
                    },
                )

                self.assertEqual(response.status_code, 400)
                self.assertIn("音频格式", response.get_json()["error"])
                thread_class.assert_not_called()

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


class WebTurboApiTests(unittest.TestCase):
    def setUp(self):
        web_app._batches.clear()
        self.client = web_app.app.test_client()

    def test_capabilities_reports_aria2_boolean(self):
        with patch(
            "app.aria2c_path",
            return_value="/opt/homebrew/bin/aria2c",
        ):
            response = self.client.get("/api/capabilities")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"aria2c_available": True})

    def test_download_defaults_to_standard_speed_mode(self):
        with patch("app.threading.Thread"):
            response = self.client.post(
                "/api/download",
                json={"urls": ["https://b23.tv/example"]},
            )

        batch = web_app._batches[response.get_json()["batch_id"]]
        self.assertEqual(batch["speed_mode"], downloader.STANDARD)
        self.assertEqual(
            batch["tasks"][0]["speed_mode_used"],
            downloader.STANDARD,
        )

    def test_download_forwards_turbo_to_background_thread(self):
        with patch("app.threading.Thread") as thread_class:
            response = self.client.post(
                "/api/download",
                json={
                    "urls": ["https://b23.tv/example"],
                    "media_type": downloader.AUDIO,
                    "speed_mode": downloader.TURBO,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            thread_class.call_args.kwargs["args"][3],
            downloader.TURBO,
        )

    def test_download_rejects_non_string_and_unknown_speed_modes(self):
        for value in (["turbo"], "warp"):
            with self.subTest(value=value), patch(
                "app.threading.Thread"
            ) as thread_class:
                response = self.client.post(
                    "/api/download",
                    json={
                        "urls": ["https://b23.tv/example"],
                        "speed_mode": value,
                    },
                )

                self.assertEqual(response.status_code, 400)
                self.assertIn("速度模式", response.get_json()["error"])
                thread_class.assert_not_called()

    def test_mode_event_updates_task_without_creating_terminal_state(self):
        batch = web_app._create_batch(
            [(downloader.BILIBILI, "https://b23.tv/example")],
            speed_mode=downloader.TURBO,
        )

        web_app._apply_progress_event(
            batch,
            0,
            "mode",
            {
                "speed_mode": downloader.STANDARD,
                "turbo_fallback": True,
            },
        )

        task = batch["tasks"][0]
        self.assertEqual(task["speed_mode_used"], downloader.STANDARD)
        self.assertTrue(task["turbo_fallback"])
        self.assertEqual(batch["completed"], 0)
        self.assertEqual(batch["failed"], 0)


if __name__ == "__main__":
    unittest.main()
