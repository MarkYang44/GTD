import re
import unittest
from pathlib import Path
from unittest.mock import patch

import app as web_app
import downloader
from collection_resolver import CollectionEntry, CollectionPreview


class WebConfigurationTests(unittest.TestCase):
    def test_readme_uses_current_project_directory_name(self):
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertTrue(readme.startswith("# Multiple_Video_Downloader\n"))
        self.assertIn("Multiple_Video_Downloader", readme)
        self.assertNotIn("Ytb_Ins_Video_Download", readme)

    def test_web_startup_banner_uses_current_project_name(self):
        source = Path("app.py").read_text(encoding="utf-8")
        readme = Path("README.md").read_text(encoding="utf-8")

        expected = "🎬 Multiple_Video_Downloader — Web 模式"
        self.assertIn(expected, source)
        self.assertIn(expected, readme)
        self.assertNotIn("Ytb/Ins/Bili Downloader", source)
        self.assertNotIn("Ytb/Ins/Bili Downloader", readme)

    def test_default_web_port_and_readme_are_8233(self):
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertEqual(web_app.WEB_HOST, "127.0.0.1")
        self.assertEqual(web_app.WEB_PORT, 8233)
        self.assertIn("http://127.0.0.1:8233", readme)
        self.assertNotIn("http://127.0.0.1:5000", readme)

    def test_web_uses_one_bounded_process_task_manager(self):
        self.assertEqual(
            web_app.task_manager._max_batches,
            web_app.MAX_STORED_BATCHES,
        )
        self.assertFalse(hasattr(web_app, "_batches"))

    def test_readme_documents_new_task_collection_and_audio_features(self):
        readme = Path("README.md").read_text(encoding="utf-8")

        for text in (
            "取消、重试与重新下载",
            "播放列表、合集与分 P",
            "原始音频",
            "WAV",
            "logs/downloader.jsonl",
            "浏览器扩展",
        ):
            self.assertIn(text, readme)


class WebProgressStateTests(unittest.TestCase):
    def test_frontend_has_four_audio_formats_and_collection_preview(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        for value in ("mp3", "flac", "source", "wav"):
            self.assertIn(f'value="{value}"', html)
        self.assertIn('id="collectionPreview"', html)
        self.assertIn("renderCollectionPreview", html)
        self.assertIn("selectedEntryIds", html)
        self.assertIn("最多选择 100 项", html)

    def test_frontend_has_cancel_retry_redownload_and_retry_failed_actions(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("operateTask('cancel'", html)
        self.assertIn("operateTask('retry'", html)
        self.assertIn("operateTask('redownload'", html)
        self.assertIn("retryFailedTasks", html)
        self.assertIn("极速任务不可取消", html)

    def test_frontend_renders_structured_error_and_attempt_history(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("error_code", html)
        self.assertIn("suggestion", html)
        self.assertIn("attempt_count", html)
        self.assertIn("attempts", html)

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

    def test_desktop_cards_reserve_matching_format_row_height(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn(
            '<div class="format-control-spacer" aria-hidden="true"></div>',
            html,
        )
        self.assertIn(
            ".format-control, .format-control-spacer",
            html,
        )
        self.assertIn("min-height: 98px", html)
        self.assertIn(".format-control-spacer { display: none; }", html)

    def test_frontend_submits_and_renders_audio_format_details(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn(
            "audio_format: pendingDownloadSettings.audioFormat",
            html,
        )
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
            "speed_mode: pendingDownloadSettings.speedMode",
            html,
        )
        self.assertIn("body: JSON.stringify(payload)", html)

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
        self.assertIn("Number.isInteger(batch.active)", html)
        self.assertIn("Number.isInteger(batch.queued)", html)
        self.assertIn('task.status === "queued"', html)
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
            "<title>Multiple_Video_Downloader - Designed by Mark Yang</title>",
            html,
        )
        self.assertIn(
            '<span class="brand-mark">Mark Yang</span><span>/ DOWNLOADER</span>',
            html,
        )
        self.assertIn(
            "<strong>最高画质视频，或最高音质音频下载。</strong><br>",
            html,
        )
        self.assertIn("<h3>最高画质视频</h3>", html)
        self.assertIn("下载源站可获取的最高画质视频，并统一输出为 MP4。", html)
        self.assertNotIn("最高质量视频", html)
        self.assertIn("粘贴链接，其余交给下载队列。", html)
        self.assertIn(
            "请仅下载自己拥有权利、获得授权或平台允许下载的视频或音频。 -- Kozeki Ui",
            html,
        )
        self.assertIn(
            "Please only download videos or audio that you own, are authorized to use, or the platform permits you to download. -- Kozeki Ui",
            html,
        )
        self.assertIn('class="footer-line footer-line-en"', html)
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
        self.client = web_app.app.test_client()

    def test_download_api_defaults_to_video_batch(self):
        with patch.object(web_app.task_manager, "create_batch") as create:
            create.return_value = {"id": "batch", "total": 1}
            response = self.client.post(
                "/api/download",
                json={"urls": ["https://youtu.be/example"]},
            )

        self.assertEqual(response.status_code, 200)
        args = create.call_args.args
        self.assertEqual(args[1], downloader.VIDEO)
        self.assertEqual(args[2], downloader.MP3)

    def test_download_api_creates_audio_batch_and_forwards_media_type(self):
        with patch.object(web_app.task_manager, "create_batch") as create:
            create.return_value = {"id": "batch", "total": 1}
            response = self.client.post(
                "/api/download",
                json={
                    "urls": ["https://youtu.be/example"],
                    "media_type": downloader.AUDIO,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(create.call_args.args[1], downloader.AUDIO)
        self.assertEqual(create.call_args.args[2], downloader.MP3)

    def test_download_api_creates_flac_audio_batch(self):
        with patch.object(web_app.task_manager, "create_batch") as create:
            create.return_value = {"id": "batch", "total": 1}
            response = self.client.post(
                "/api/download",
                json={
                    "urls": ["https://b23.tv/example"],
                    "media_type": downloader.AUDIO,
                    "audio_format": downloader.FLAC,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(create.call_args.args[2], downloader.FLAC)

    def test_download_api_rejects_unknown_and_non_string_audio_format(self):
        for value in ("ogg", [downloader.FLAC]):
            with (
                self.subTest(value=value),
                patch.object(web_app.task_manager, "create_batch") as create,
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
                create.assert_not_called()

    def test_download_api_rejects_unknown_media_type(self):
        with patch.object(web_app.task_manager, "create_batch") as create:
            response = self.client.post(
                "/api/download",
                json={
                    "urls": ["https://youtu.be/example"],
                    "media_type": "unknown",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("下载类型", response.get_json()["error"])
        create.assert_not_called()

    def test_download_api_rejects_non_string_media_type(self):
        with patch.object(web_app.task_manager, "create_batch") as create:
            response = self.client.post(
                "/api/download",
                json={
                    "urls": ["https://youtu.be/example"],
                    "media_type": [downloader.AUDIO],
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("下载类型", response.get_json()["error"])
        create.assert_not_called()

    def test_download_api_rejects_non_object_json_without_starting_a_thread(self):
        for payload in ([], "https://youtu.be/example"):
            with (
                self.subTest(payload=payload),
                patch.object(web_app.task_manager, "create_batch") as create,
            ):
                response = self.client.post("/api/download", json=payload)

                self.assertEqual(response.status_code, 400)
                self.assertIn("JSON 对象", response.get_json()["error"])
                create.assert_not_called()

    def test_download_api_rejects_invalid_url_list_types_early(self):
        for urls in (
            "https://youtu.be/example",
            ["https://youtu.be/example", 42],
        ):
            with (
                self.subTest(urls=urls),
                patch.object(web_app.task_manager, "create_batch") as create,
            ):
                response = self.client.post(
                    "/api/download",
                    json={"urls": urls},
                )

                self.assertEqual(response.status_code, 400)
                self.assertIn("链接列表", response.get_json()["error"])
                create.assert_not_called()


class WebTurboApiTests(unittest.TestCase):
    def setUp(self):
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
        with patch.object(web_app.task_manager, "create_batch") as create:
            create.return_value = {"id": "batch", "total": 1}
            response = self.client.post(
                "/api/download",
                json={"urls": ["https://b23.tv/example"]},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(create.call_args.args[3], downloader.STANDARD)

    def test_download_forwards_turbo_to_background_thread(self):
        with patch.object(web_app.task_manager, "create_batch") as create:
            create.return_value = {"id": "batch", "total": 1}
            response = self.client.post(
                "/api/download",
                json={
                    "urls": ["https://b23.tv/example"],
                    "media_type": downloader.AUDIO,
                    "speed_mode": downloader.TURBO,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(create.call_args.args[3], downloader.TURBO)

    def test_download_rejects_non_string_and_unknown_speed_modes(self):
        for value in (["turbo"], "warp"):
            with self.subTest(value=value), patch(
                "app.task_manager.create_batch"
            ) as create:
                response = self.client.post(
                    "/api/download",
                    json={
                        "urls": ["https://b23.tv/example"],
                        "speed_mode": value,
                    },
                )

                self.assertEqual(response.status_code, 400)
                self.assertIn("速度模式", response.get_json()["error"])
                create.assert_not_called()


class WebTaskOperationApiTests(unittest.TestCase):
    def setUp(self):
        self.client = web_app.app.test_client()

    def test_preview_returns_collection_entries(self):
        preview = {
            "preview_id": "preview-1",
            "title": "List",
            "platform": "youtube",
            "is_single": False,
            "requires_selection": True,
            "entries": [
                {"id": "1:a", "title": "A", "selectable": True}
            ],
        }
        with patch("app.resolve_inputs") as resolve:
            resolve.return_value.id = "preview-1"
            resolve.return_value.to_dict.return_value = preview
            response = self.client.post(
                "/api/preview",
                json={
                    "inputs": [
                        "https://youtube.com/playlist?list=x"
                    ]
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["preview_id"], "preview-1")

    def test_preview_submission_rejects_more_than_100(self):
        response = self.client.post(
            "/api/download",
            json={
                "preview_id": "preview-1",
                "selected_entry_ids": [str(index) for index in range(101)],
                "media_type": "video",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error_code"], "INVALID_REQUEST")

    def test_cancel_conflict_returns_409_structured_error(self):
        with patch.object(
            web_app.task_manager,
            "cancel",
            side_effect=ValueError("极速任务不可取消"),
        ):
            response = self.client.post("/api/batch/b/task/t/cancel")

        self.assertEqual(response.status_code, 409)
        self.assertIn("error_code", response.get_json())

    def test_audio_api_accepts_source_and_wav(self):
        for value in ("source", "wav"):
            with self.subTest(value=value), patch.object(
                web_app.task_manager,
                "create_batch",
            ) as create:
                create.return_value = {"id": "b", "total": 1}
                response = self.client.post(
                    "/api/download",
                    json={
                        "urls": ["https://youtu.be/example"],
                        "media_type": "audio",
                        "audio_format": value,
                    },
                )

                self.assertEqual(response.status_code, 200)

    def test_selected_preview_entries_keep_user_order_and_metadata(self):
        preview = CollectionPreview(
            "selection-preview",
            "Parts",
            "bilibili",
            (
                CollectionEntry(
                    "1:p1",
                    "P1",
                    "bilibili",
                    "https://www.bilibili.com/video/BV1?p=1",
                    1,
                    None,
                    True,
                    None,
                ),
                CollectionEntry(
                    "2:p2",
                    "P2",
                    "bilibili",
                    "https://www.bilibili.com/video/BV1?p=2",
                    2,
                    None,
                    True,
                    None,
                ),
            ),
            False,
            True,
        )
        web_app.preview_store.put(preview)

        with patch.object(web_app.task_manager, "create_batch") as create:
            create.return_value = {"id": "batch", "total": 2}
            response = self.client.post(
                "/api/download",
                json={
                    "preview_id": preview.id,
                    "selected_entry_ids": ["2:p2", "1:p1"],
                    "media_type": "video",
                },
            )

        self.assertEqual(response.status_code, 200)
        seeds = create.call_args.args[0]
        self.assertEqual([seed.title for seed in seeds], ["P2", "P1"])
        self.assertEqual([seed.position for seed in seeds], [2, 1])

    def test_batch_status_and_operation_not_found_are_structured(self):
        with patch.object(
            web_app.task_manager,
            "snapshot",
            side_effect=KeyError("missing"),
        ):
            response = self.client.get("/api/batch/missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error_code"], "BATCH_NOT_FOUND")

        with patch.object(
            web_app.task_manager,
            "retry",
            side_effect=KeyError("missing"),
        ):
            response = self.client.post(
                "/api/batch/missing/task/missing/retry"
            )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error_code"], "TASK_NOT_FOUND")

if __name__ == "__main__":
    unittest.main()
