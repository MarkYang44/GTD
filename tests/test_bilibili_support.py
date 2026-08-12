import contextlib
import copy
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import app as web_app
from bilibili_acceleration import CDN_CANDIDATES_FIELD
import downloader
import main as cli_main


def frontend_template_source():
    return Path("templates/index.html").read_text(encoding="utf-8")


class BilibiliUrlDetectionTests(unittest.TestCase):
    def test_accepts_single_video_and_short_link_urls(self):
        accepted = [
            "https://www.bilibili.com/video/BV1GJ411x7h7",
            "https://www.bilibili.com/video/av170001?p=2",
            "https://m.bilibili.com/video/BV1GJ411x7h7",
            "https://bilibili.com/video/av170001",
            "https://b23.tv/BV1GJ411x7h7",
        ]

        for url in accepted:
            with self.subTest(url=url):
                self.assertEqual(
                    downloader.detect_platform(url),
                    downloader.BILIBILI,
                )
                self.assertTrue(downloader.is_valid_bilibili_url(url))
                self.assertEqual(
                    downloader.make_task(url),
                    (downloader.BILIBILI, url),
                )

    def test_rejects_non_video_bilibili_pages(self):
        rejected = [
            "https://space.bilibili.com/2",
            "https://www.bilibili.com/bangumi/play/ep1",
            "https://www.bilibili.com/list/watchlater",
            "https://www.bilibili.com/medialist/play/1",
            "https://www.bilibili.com/video/",
            "https://www.bilibili.com/video/not-a-video-id",
            "https://b23.tv/",
        ]

        for url in rejected:
            with self.subTest(url=url):
                self.assertIsNone(downloader.detect_platform(url))
                self.assertFalse(downloader.is_valid_bilibili_url(url))


class ShareTextUrlExtractionTests(unittest.TestCase):
    def test_extracts_user_provided_bilibili_share_text(self):
        share_text = (
            "【【梗百科】不X你们X什么是啥梗？！】"
            "https://www.bilibili.com/video/BV1xRuu6fEeA"
            "?vd_source=c29bf1bb20fc12664dae270045332759"
        )
        expected = (
            "https://www.bilibili.com/video/BV1xRuu6fEeA"
            "?vd_source=c29bf1bb20fc12664dae270045332759"
        )

        self.assertEqual(downloader.normalize_url(share_text), expected)
        self.assertEqual(
            downloader.make_task(share_text),
            (downloader.BILIBILI, expected),
        )

    def test_make_task_normalizes_share_text_only_once(self):
        share_text = "【标题】https://www.bilibili.com/video/BV1xRuu6fEeA?vd_source=test"

        with patch.object(
            downloader,
            "normalize_url",
            wraps=downloader.normalize_url,
        ) as normalize:
            task = downloader.make_task(share_text)

        self.assertEqual(task[0], downloader.BILIBILI)
        normalize.assert_called_once_with(share_text)

    def test_removes_trailing_share_punctuation_but_keeps_query(self):
        share_text = (
            "推荐：https://www.bilibili.com/video/BV1xRuu6fEeA?p=2】。"
        )

        self.assertEqual(
            downloader.normalize_url(share_text),
            "https://www.bilibili.com/video/BV1xRuu6fEeA?p=2",
        )

    def test_removes_curly_quote_from_reported_short_link(self):
        share_text = "https://b23.tv/ofoghaj“"

        self.assertEqual(
            downloader.normalize_url(share_text),
            "https://b23.tv/ofoghaj",
        )
        self.assertEqual(
            downloader.make_task(share_text),
            (downloader.BILIBILI, "https://b23.tv/ofoghaj"),
        )

    def test_shared_parser_also_handles_youtube_and_instagram_text(self):
        cases = [
            (
                "观看 (https://www.youtube.com/watch?v=abc123).",
                downloader.YOUTUBE,
                "https://www.youtube.com/watch?v=abc123",
            ),
            (
                "Reel：https://www.instagram.com/reel/ABC123/！",
                downloader.INSTAGRAM,
                "https://www.instagram.com/reel/ABC123/",
            ),
        ]

        for share_text, platform, expected in cases:
            with self.subTest(share_text=share_text):
                self.assertEqual(
                    downloader.make_task(share_text),
                    (platform, expected),
                )

    def test_rejects_text_without_url_and_non_video_url(self):
        self.assertIsNone(downloader.make_task("只有标题，没有链接"))
        self.assertIsNone(
            downloader.make_task("主页 https://space.bilibili.com/2。")
        )


class BilibiliDownloadOptionsTests(unittest.TestCase):
    def test_native_acceleration_applies_to_bilibili_video_and_audio(self):
        output_dir = Path("/tmp/downloads")

        for media_type in (downloader.VIDEO, downloader.AUDIO):
            with self.subTest(media_type=media_type):
                options = downloader._build_ydl_options(
                    downloader.BILIBILI,
                    output_dir,
                    1,
                    1,
                    media_type=media_type,
                )
                self.assertEqual(
                    options["http_chunk_size"],
                    10 * 1024 * 1024,
                )
                self.assertNotIn("throttled_rate", options)

    def test_native_acceleration_does_not_change_other_platforms(self):
        output_dir = Path("/tmp/downloads")

        for platform in (downloader.YOUTUBE, downloader.INSTAGRAM):
            with self.subTest(platform=platform):
                options = downloader._build_ydl_options(
                    platform,
                    output_dir,
                    1,
                    1,
                )
                self.assertNotIn("http_chunk_size", options)
                self.assertNotIn("throttled_rate", options)

    def test_video_uses_best_streams_mp4_merge_and_id_suffix(self):
        output_dir = Path("/tmp/downloads")

        options = downloader._build_ydl_options(
            downloader.BILIBILI,
            output_dir,
            1,
            1,
        )

        self.assertEqual(options["format"], "bestvideo+bestaudio/best")
        self.assertEqual(options["merge_output_format"], "mp4")
        self.assertTrue(options["noplaylist"])
        self.assertEqual(
            options["outtmpl"],
            str(output_dir / "%(title)s [%(id)s].%(ext)s"),
        )
        self.assertNotIn("http_headers", options)

    def test_audio_uses_best_audio_mp3_and_id_suffix(self):
        output_dir = Path("/tmp/downloads")

        options = downloader._build_ydl_options(
            downloader.BILIBILI,
            output_dir,
            1,
            1,
            media_type=downloader.AUDIO,
        )

        self.assertEqual(options["format"], "bestaudio/best")
        self.assertEqual(
            options["postprocessors"][0]["key"],
            "FFmpegExtractAudio",
        )
        self.assertEqual(
            options["postprocessors"][0]["preferredquality"],
            "0",
        )
        self.assertEqual(
            options["outtmpl"],
            str(output_dir / "%(title)s [%(id)s].%(ext)s"),
        )

    def test_platform_cookie_precedes_generic_cookie(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            generic = project_dir / "cookies.txt"
            platform_cookie = project_dir / "bilibili_cookies.txt"
            generic.touch()
            platform_cookie.touch()

            with patch.object(downloader, "PROJECT_DIR", project_dir):
                self.assertEqual(
                    downloader._find_cookie_file(downloader.BILIBILI),
                    platform_cookie,
                )

    def test_bilibili_cookie_file_is_ignored(self):
        gitignore = Path(".gitignore").read_text(encoding="utf-8")

        self.assertIn("bilibili_cookies.txt", gitignore.splitlines())

    def test_membership_error_points_to_bilibili_cookie(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            downloader._handle_download_error(
                "This video is for premium members only",
                downloader.BILIBILI,
            )

        self.assertIn("Bilibili", output.getvalue())
        self.assertIn("bilibili_cookies.txt", output.getvalue())

    def test_http_412_explains_bilibili_risk_control(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            downloader._handle_download_error(
                "Unable to download webpage: HTTP Error 412: Precondition Failed",
                downloader.BILIBILI,
            )

        self.assertIn("Bilibili 风控", output.getvalue())
        self.assertIn("bilibili_cookies.txt", output.getvalue())
        self.assertIn("稍后重试", output.getvalue())


class BilibiliTurboDownloadTests(unittest.TestCase):
    def test_standard_download_avoids_copy_when_cdn_host_is_unchanged(self):
        info = {
            "id": "BV1TEST",
            "title": "Example",
            "url": "https://primary.example/video.m4s",
            "filesize": 60 * 1024 * 1024,
            "ext": "mp4",
        }
        plan = downloader.AccelerationPlan(
            adaptive=False,
            cdn_host="primary.example",
            http_chunk_size=10 * 1024 * 1024,
        )

        with (
            patch("downloader.aria2c_path", return_value=None),
            patch("downloader._extract_bilibili_info", return_value=(Mock(), info)),
            patch("downloader.build_acceleration_plan", return_value=plan),
            patch(
                "downloader._process_bilibili_attempt",
                return_value=(info, Path("/tmp/Example [BV1TEST].mp4")),
            ),
            patch("downloader._format_filesize", return_value="60.00 MB"),
            patch("downloader.copy.deepcopy", side_effect=copy.deepcopy) as deepcopy,
        ):
            result = downloader.download_video(
                "https://b23.tv/example",
                platform=downloader.BILIBILI,
            )

        self.assertIsNotNone(result)
        deepcopy.assert_not_called()

    def test_multi_stream_download_switches_each_available_stream_to_chosen_cdn(self):
        info = {
            "id": "BV1TEST",
            "title": "Example",
            "ext": "mp4",
            "requested_formats": [
                {
                    "url": "https://chosen.example/video.m4s",
                    CDN_CANDIDATES_FIELD: (
                        "https://chosen.example/video.m4s",
                    ),
                },
                {
                    "url": "https://audio-original.example/audio.m4s",
                    CDN_CANDIDATES_FIELD: (
                        "https://audio-original.example/audio.m4s",
                        "https://chosen.example/audio.m4s",
                    ),
                },
            ],
        }
        plan = downloader.AccelerationPlan(
            adaptive=True,
            cdn_host="chosen.example",
            http_chunk_size=4 * 1024 * 1024,
        )
        attempted_urls = []

        def fake_attempt(prepared_info, options, output_dir):
            attempted_urls.append([
                fmt["url"] for fmt in prepared_info["requested_formats"]
            ])
            return prepared_info, Path("/tmp/Example [BV1TEST].mp4")

        with (
            patch("downloader.aria2c_path", return_value=None),
            patch("downloader._extract_bilibili_info", return_value=(Mock(), info)),
            patch("downloader.build_acceleration_plan", return_value=plan),
            patch("downloader._process_bilibili_attempt", side_effect=fake_attempt),
            patch("downloader._format_filesize", return_value="60.00 MB"),
            patch("downloader.copy.deepcopy", side_effect=copy.deepcopy) as deepcopy,
        ):
            result = downloader.download_video(
                "https://b23.tv/example",
                platform=downloader.BILIBILI,
            )

        self.assertIsNotNone(result)
        self.assertEqual(deepcopy.call_count, 1)
        self.assertEqual(attempted_urls[0], [
            "https://chosen.example/video.m4s",
            "https://chosen.example/audio.m4s",
        ])

    def test_flac_request_uses_real_flac_source(self):
        info = {
            "id": "BV1TEST",
            "title": "Example",
            "url": "https://primary.example/audio.m4s",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "flac",
            "format_id": "30251",
            "abr": 1521.267,
            "filesize": 60 * 1024 * 1024,
        }
        seen_options = []

        def fake_attempt(prepared_info, options, output_dir):
            seen_options.append(options)
            return prepared_info, output_dir / "Example [BV1TEST].flac"

        with (
            patch("downloader.aria2c_path", return_value=None),
            patch("downloader._extract_bilibili_info", return_value=(Mock(), info)),
            patch(
                "downloader.build_acceleration_plan",
                return_value=Mock(
                    adaptive=False,
                    cdn_host="primary.example",
                    http_chunk_size=10 * 1024 * 1024,
                ),
            ),
            patch("downloader._process_bilibili_attempt", side_effect=fake_attempt),
            patch("downloader._rename_audio_output", side_effect=lambda path, profile: path),
            patch("downloader._format_filesize", return_value="60.00 MB"),
        ):
            result = downloader.download_video(
                "https://b23.tv/example",
                platform=downloader.BILIBILI,
                media_type=downloader.AUDIO,
                audio_format=downloader.FLAC,
            )

        self.assertEqual(
            seen_options[0]["postprocessors"][0]["preferredcodec"],
            downloader.FLAC,
        )
        self.assertEqual(result["audio_format_requested"], downloader.FLAC)
        self.assertEqual(result["audio_format_used"], downloader.FLAC)
        self.assertFalse(result["audio_format_fallback"])
        self.assertEqual(result["source_acodec"], "FLAC")
        self.assertEqual(result["source_abr_kbps"], 1521)

    def test_flac_request_falls_back_to_mp3_for_aac_source(self):
        info = {
            "id": "BV1TEST",
            "title": "Example",
            "url": "https://primary.example/audio.m4s",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "format_id": "30280",
            "abr": 245.75,
            "filesize": 20 * 1024 * 1024,
        }
        seen_options = []

        def fake_attempt(prepared_info, options, output_dir):
            seen_options.append(options)
            return prepared_info, output_dir / "Example [BV1TEST].mp3"

        with (
            patch("downloader.aria2c_path", return_value=None),
            patch("downloader._extract_bilibili_info", return_value=(Mock(), info)),
            patch(
                "downloader.build_acceleration_plan",
                return_value=Mock(
                    adaptive=False,
                    cdn_host="primary.example",
                    http_chunk_size=10 * 1024 * 1024,
                ),
            ),
            patch("downloader._process_bilibili_attempt", side_effect=fake_attempt),
            patch("downloader._rename_audio_output", side_effect=lambda path, profile: path),
            patch("downloader._format_filesize", return_value="20.00 MB"),
        ):
            result = downloader.download_video(
                "https://b23.tv/example",
                platform=downloader.BILIBILI,
                media_type=downloader.AUDIO,
                audio_format=downloader.FLAC,
            )

        self.assertEqual(
            seen_options[0]["postprocessors"][0]["preferredcodec"],
            downloader.MP3,
        )
        self.assertEqual(result["audio_format_requested"], downloader.FLAC)
        self.assertEqual(result["audio_format_used"], downloader.MP3)
        self.assertTrue(result["audio_format_fallback"])
        self.assertEqual(result["source_acodec"], "AAC")
        self.assertEqual(result["source_abr_kbps"], 246)

    def test_source_audio_result_reports_actual_postprocessed_extension(self):
        info = {
            "id": "BV1TEST",
            "title": "Example",
            "url": "https://primary.example/audio.m4s",
            "ext": "webm",
            "vcodec": "none",
            "acodec": "opus",
            "format_id": "30280",
            "abr": 128,
            "filesize": 20 * 1024 * 1024,
        }

        with (
            patch("downloader.aria2c_path", return_value=None),
            patch("downloader._extract_bilibili_info", return_value=(Mock(), info)),
            patch(
                "downloader.build_acceleration_plan",
                return_value=Mock(
                    adaptive=False,
                    cdn_host="primary.example",
                    http_chunk_size=10 * 1024 * 1024,
                ),
            ),
            patch(
                "downloader._process_bilibili_attempt",
                return_value=(info, Path("/tmp/Example.opus")),
            ),
            patch(
                "downloader._rename_audio_output",
                side_effect=lambda path, profile: path,
            ),
            patch("downloader._format_filesize", return_value="20.00 MB"),
        ):
            result = downloader.download_video(
                "https://b23.tv/example",
                platform=downloader.BILIBILI,
                media_type=downloader.AUDIO,
                audio_format=downloader.SOURCE,
            )

        self.assertEqual(result["output_ext"], "opus")
        self.assertEqual(result["format"], "SOURCE OPUS")

    def test_turbo_options_only_apply_to_bilibili(self):
        output_dir = Path("/tmp/downloads")
        bili = downloader._build_ydl_options(
            downloader.BILIBILI,
            output_dir,
            1,
            1,
            speed_mode=downloader.TURBO,
            aria2_executable="/bin/aria2c",
        )
        youtube = downloader._build_ydl_options(
            downloader.YOUTUBE,
            output_dir,
            1,
            1,
            speed_mode=downloader.TURBO,
            aria2_executable="/bin/aria2c",
        )

        self.assertEqual(
            bili["external_downloader"]["http"],
            "/bin/aria2c",
        )
        self.assertNotIn("external_downloader", youtube)

    def test_unknown_speed_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "速度模式"):
            downloader._build_ydl_options(
                downloader.BILIBILI,
                Path("/tmp/downloads"),
                1,
                1,
                speed_mode="warp",
            )

    def test_aria2_failure_retries_once_with_standard_mode(self):
        info = {
            "id": "BV1TEST",
            "title": "Example",
            "url": "https://primary.example/audio.m4s?token=secret",
            "filesize": 60 * 1024 * 1024,
            "ext": "m4a",
        }
        events = []
        attempts = []

        def fake_attempt(prepared_info, options, output_dir):
            attempts.append(options.get("external_downloader"))
            if len(attempts) == 1:
                raise downloader.yt_dlp.utils.DownloadError(
                    "aria2c exited with code 1"
                )
            return prepared_info, output_dir / "Example [BV1TEST].mp3"

        with (
            patch("downloader.aria2c_path", return_value="/bin/aria2c"),
            patch(
                "downloader._extract_bilibili_info",
                return_value=(Mock(), info),
            ),
            patch(
                "downloader.build_acceleration_plan",
                return_value=Mock(
                    adaptive=True,
                    cdn_host="primary.example",
                    http_chunk_size=4 * 1024 * 1024,
                ),
            ),
            patch(
                "downloader._process_bilibili_attempt",
                side_effect=fake_attempt,
            ),
            patch(
                "downloader._rename_audio_output",
                side_effect=lambda path, profile: path,
            ),
            patch("downloader._format_filesize", return_value="60.00 MB"),
        ):
            result = downloader.download_video(
                "https://b23.tv/example",
                platform=downloader.BILIBILI,
                media_type=downloader.AUDIO,
                speed_mode=downloader.TURBO,
                progress_callback=lambda event, data: events.append(
                    (event, data)
                ),
            )

        self.assertEqual(attempts, [{"http": "/bin/aria2c"}, None])
        self.assertEqual(result["speed_mode_used"], downloader.STANDARD)
        self.assertTrue(result["turbo_fallback"])
        self.assertNotIn("token=", repr(result))
        self.assertIn(("mode", {
            "speed_mode": downloader.STANDARD,
            "turbo_fallback": True,
        }), events)

    def test_non_aria2_download_error_does_not_retry_as_standard(self):
        info = {
            "id": "BV1TEST",
            "title": "Example",
            "url": "https://a.example/v",
            "filesize": 60,
        }
        with (
            patch("downloader.aria2c_path", return_value="/bin/aria2c"),
            patch(
                "downloader._extract_bilibili_info",
                return_value=(Mock(), info),
            ),
            patch(
                "downloader.build_acceleration_plan",
                return_value=Mock(
                    adaptive=False,
                    cdn_host="a.example",
                    http_chunk_size=10 * 1024 * 1024,
                ),
            ),
            patch(
                "downloader._process_bilibili_attempt",
                side_effect=downloader.yt_dlp.utils.DownloadError(
                    "ffmpeg merge failed"
                ),
            ) as process,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = downloader.download_video(
                "https://b23.tv/example",
                platform=downloader.BILIBILI,
                speed_mode=downloader.TURBO,
            )

        self.assertIsNone(result)
        self.assertEqual(process.call_count, 1)

    def test_selected_cdn_403_retries_original_url_and_ten_mib_chunk(self):
        info = {
            "id": "BV1TEST",
            "title": "Example",
            "url": "https://primary.example/audio.m4s",
            "filesize": 60 * 1024 * 1024,
            "ext": "m4a",
            "_bilibili_cdn_candidates": (
                "https://primary.example/audio.m4s",
                "https://fast.example/audio.m4s",
            ),
        }
        seen = []

        def fake_attempt(prepared_info, options, output_dir):
            seen.append((prepared_info["url"], options["http_chunk_size"]))
            if len(seen) == 1:
                raise downloader.yt_dlp.utils.DownloadError("HTTP Error 403")
            return prepared_info, output_dir / "Example [BV1TEST].mp3"

        with (
            patch(
                "downloader._extract_bilibili_info",
                return_value=(Mock(), info),
            ),
            patch(
                "downloader.build_acceleration_plan",
                return_value=Mock(
                    adaptive=True,
                    cdn_host="fast.example",
                    http_chunk_size=4 * 1024 * 1024,
                ),
            ),
            patch(
                "downloader._process_bilibili_attempt",
                side_effect=fake_attempt,
            ),
            patch(
                "downloader._rename_audio_output",
                side_effect=lambda path, profile: path,
            ),
            patch("downloader._format_filesize", return_value="60.00 MB"),
        ):
            result = downloader.download_video(
                "https://b23.tv/example",
                platform=downloader.BILIBILI,
                media_type=downloader.AUDIO,
            )

        self.assertEqual(seen, [
            ("https://fast.example/audio.m4s", 4 * 1024 * 1024),
            ("https://primary.example/audio.m4s", 10 * 1024 * 1024),
        ])
        self.assertEqual(result["cdn_host"], "primary.example")

    def test_connection_reset_retries_a_backup_cdn(self):
        info = {
            "id": "BV1TEST",
            "title": "Example",
            "url": "https://primary.example/audio.m4s",
            "filesize": 1024 * 1024 * 1024,
            "ext": "m4a",
            "_bilibili_cdn_candidates": (
                "https://primary.example/audio.m4s",
                "https://backup.example/audio.m4s",
            ),
        }
        attempted_urls = []

        def fake_attempt(prepared_info, options, output_dir):
            attempted_urls.append(prepared_info["url"])
            if len(attempted_urls) == 1:
                raise downloader.yt_dlp.utils.DownloadError(
                    "[WinError 10054] 远程主机强迫关闭了一个现有的连接"
                )
            return prepared_info, output_dir / "Example [BV1TEST].mp3"

        with (
            patch("downloader.aria2c_path", return_value=None),
            patch(
                "downloader._extract_bilibili_info",
                return_value=(Mock(), info),
            ),
            patch(
                "downloader.build_acceleration_plan",
                return_value=downloader.AccelerationPlan(
                    adaptive=True,
                    cdn_host="primary.example",
                    http_chunk_size=10 * 1024 * 1024,
                ),
            ),
            patch(
                "downloader._process_bilibili_attempt",
                side_effect=fake_attempt,
            ),
            patch(
                "downloader._rename_audio_output",
                side_effect=lambda path, profile: path,
            ),
            patch("downloader._format_filesize", return_value="1000.00 MB"),
        ):
            result = downloader.download_video(
                "https://b23.tv/ofoghaj",
                platform=downloader.BILIBILI,
                media_type=downloader.AUDIO,
            )

        self.assertEqual(
            attempted_urls,
            [
                "https://primary.example/audio.m4s",
                "https://backup.example/audio.m4s",
            ],
        )
        self.assertEqual(result["cdn_host"], "backup.example")

    def test_failed_attempt_cleanup_only_removes_owned_workspace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            first = downloader._new_attempt_workspace(output_dir)
            second = downloader._new_attempt_workspace(output_dir)
            new_part = first / "Example.mp4.part"
            new_format = first / "Example.f137.mp4"
            other_part = second / "Other.mp4.part"
            final_file = output_dir / "Example.mp4"
            new_part.write_bytes(b"partial")
            new_format.write_bytes(b"partial")
            other_part.write_bytes(b"keep")
            final_file.write_bytes(b"final")

            downloader._cleanup_attempt_workspace(first)

            self.assertFalse(new_part.exists())
            self.assertFalse(new_format.exists())
            self.assertEqual(other_part.read_bytes(), b"keep")
            self.assertTrue(final_file.exists())


class BilibiliSurfaceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = web_app.app.test_client()

    def test_cli_accepts_bilibili_in_mixed_arguments(self):
        urls = [
            "https://youtu.be/example",
            "https://www.bilibili.com/video/BV1GJ411x7h7?p=2",
        ]

        tasks = cli_main.get_tasks_from_args(urls)

        self.assertEqual(tasks[1][0], downloader.BILIBILI)
        self.assertEqual(tasks[1][1], urls[1])

    def test_web_api_creates_bilibili_audio_task(self):
        url = "https://b23.tv/BV1GJ411x7h7"

        with patch.object(web_app.task_manager, "create_batch") as create:
            create.return_value = {"id": "batch", "total": 1, "download_dir": "/tmp/downloads"}
            response = self.client.post(
                "/api/download",
                json={"urls": [url], "media_type": downloader.AUDIO},
            )

        self.assertEqual(response.status_code, 200)
        seeds = create.call_args.args[0]
        self.assertEqual(seeds[0].platform, downloader.BILIBILI)
        self.assertEqual(create.call_args.args[1], downloader.AUDIO)

    def test_page_names_bilibili_without_adding_new_input(self):
        html = frontend_template_source()

        self.assertIn("YOUTUBE + INSTAGRAM + BILIBILI", html)
        self.assertNotIn("/ ONLINE", html)
        self.assertIn("YouTube / Instagram / Bilibili", html)
        self.assertEqual(html.count('id="videoUrls"'), 1)
        self.assertEqual(html.count('id="audioUrls"'), 1)

    def test_cli_and_api_errors_name_all_supported_platforms(self):
        source = Path("main.py").read_text(encoding="utf-8")
        app_source = Path("app.py").read_text(encoding="utf-8")

        self.assertIn("YouTube、Instagram 或 Bilibili", source)
        self.assertIn("YouTube、Instagram 或 Bilibili", app_source)


class BilibiliDocumentationTests(unittest.TestCase):
    def test_readme_documents_audio_formats_covers_and_fallback(self):
        readme = Path("README.md").read_text(encoding="utf-8")

        required = [
            "MP3 V0 / 源 FLAC",
            "python main.py --audio --flac",
            "源站未提供 FLAC，已自动回退至 MP3 V0",
            "[MP3 V0 · 源FLAC 1521kbps].mp3",
            "[FLAC Lossless · 1521kbps].flac",
            "自动嵌入视频封面",
            "没有封面时仍正常输出音频",
            "mutagen",
            "MP3 成品仍是有损音频",
        ]
        for text in required:
            with self.subTest(text=text):
                self.assertIn(text, readme)

    def test_readme_documents_bilibili_workflow_and_boundaries(self):
        readme = Path("README.md").read_text(encoding="utf-8")

        required = [
            "YouTube + Instagram + Bilibili",
            "bilibili_cookies.txt",
            "https://www.bilibili.com/video/BV",
            "https://www.bilibili.com/video/av",
            "https://b23.tv/",
            "分 P",
            "预览并选择 YouTube 播放列表、Bilibili 多分 P",
            "不承诺支持需要额外业务接口、DRM 或特殊账号权限的 Bilibili 番剧",
            "一次最多选择 100 项",
            "标题 [内容ID].mp4",
            "标题 [内容ID].mp3",
            "Bilibili 风控或 `HTTP 412`",
            "10 MB HTTP 分块",
            "最多同时运行 2 个 Bilibili 下载任务",
            "实际速度仍取决于 Bilibili 分配的 CDN 和网络路由",
            "bilibili_acceleration.py",
            "brew install aria2",
            "aria2c --version",
            "--turbo",
            "--audio --turbo",
            "50 MiB",
            "30 分钟",
            "不可中断",
            "自动切换回标准模式",
            "最多测试 4 个",
            "不修改或猜测 CDN 域名",
        ]
        for text in required:
            with self.subTest(text=text):
                self.assertIn(text, readme)


class CookieExtensionDocumentationTests(unittest.TestCase):
    def test_readme_documents_cookie_extension_install_and_export(self):
        readme = Path("README.md").read_text(encoding="utf-8")
        cookie_section = readme.split(
            "## 六、需要登录时配置 Cookie",
            maxsplit=1,
        )[1].split("## 七、常见问题", maxsplit=1)[0]

        required = [
            "Get cookies.txt LOCALLY",
            "https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc",
            "https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt-locally/",
            "https://github.com/kairi003/Get-cookies.txt-LOCALLY",
            "Chrome / Edge 安装",
            "Firefox 安装",
            "Netscape",
            "# Netscape HTTP Cookie File",
            "仅导出当前平台域名",
            "youtube_cookies.txt",
            "instagram_cookies.txt",
            "bilibili_cookies.txt",
            "重启 8233 Web 服务",
            "不要上传、分享、截图或提交到 Git",
        ]
        for text in required:
            with self.subTest(text=text):
                self.assertIn(text, cookie_section)


class ShareTextSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.client = web_app.app.test_client()

    def test_web_api_stores_only_clean_url_from_share_text(self):
        share_text = (
            "【视频】https://www.bilibili.com/video/BV1xRuu6fEeA"
            "?vd_source=source123"
        )
        expected = (
            "https://www.bilibili.com/video/BV1xRuu6fEeA"
            "?vd_source=source123"
        )

        with patch.object(web_app.task_manager, "create_batch") as create:
            create.return_value = {"id": "batch", "total": 1, "download_dir": "/tmp/downloads"}
            response = self.client.post(
                "/api/download",
                json={"urls": [share_text], "media_type": downloader.VIDEO},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(create.call_args.args[0][0].url, expected)

    def test_page_and_readme_explain_share_text_input(self):
        html = frontend_template_source()
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertGreaterEqual(html.count("链接或平台分享文案"), 2)
        self.assertIn("可以直接粘贴平台生成的分享文案", readme)
        self.assertIn(
            "自动忽略标题并提取其中的第一个 HTTP(S) 链接",
            readme,
        )
        self.assertIn("【【梗百科】", readme)


if __name__ == "__main__":
    unittest.main()
