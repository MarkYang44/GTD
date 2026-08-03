import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import downloader
import yt_dlp


class DownloadErrorMessageTests(unittest.TestCase):
    def test_ydl_options_use_quiet_logger_for_handled_errors(self):
        options = downloader._build_ydl_options(
            downloader.INSTAGRAM,
            downloader.DOWNLOADS_DIR,
            1,
            1,
        )

        logger = options.get("logger")
        self.assertIsNotNone(logger)
        self.assertTrue(callable(getattr(logger, "error", None)))
        self.assertIsNone(logger.error("suppressed by downloader"))

    def test_youtube_options_enable_js_challenge_solver(self):
        options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            downloader.DOWNLOADS_DIR,
            1,
            1,
        )

        self.assertIn("node", options.get("js_runtimes", {}))
        self.assertIn("ejs:github", options.get("remote_components", []))

    def test_instagram_empty_media_response_points_to_cookie_file(self):
        buffer = io.StringIO()

        with contextlib.redirect_stdout(buffer):
            downloader._handle_download_error(
                "ERROR: [Instagram] abc: Instagram sent an empty media response.",
                downloader.INSTAGRAM,
            )

        output = buffer.getvalue()
        self.assertIn("Instagram 返回了空媒体数据", output)
        self.assertIn("instagram_cookies.txt", output)
        self.assertIn(str(downloader.PROJECT_DIR / "instagram_cookies.txt"), output)

    def test_instagram_http_400_explains_api_rejection(self):
        buffer = io.StringIO()

        with contextlib.redirect_stdout(buffer):
            downloader._handle_download_error(
                "ERROR: [Instagram] abc: Video info extraction failed: HTTP Error 400: Bad Request",
                downloader.INSTAGRAM,
            )

        output = buffer.getvalue()
        self.assertIn("Instagram API 拒绝了该请求", output)
        self.assertIn("重新导出完整 Cookie", output)
        self.assertIn("浏览器中确认该链接能正常播放", output)


class DownloadOutputTemplateTests(unittest.TestCase):
    def test_instagram_same_title_different_ids_prepare_distinct_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            options = downloader._build_ydl_options(
                downloader.INSTAGRAM,
                output_dir,
                1,
                2,
            )
            with yt_dlp.YoutubeDL(options) as ydl:
                first_path = Path(ydl.prepare_filename({
                    "id": "AAA111",
                    "title": "Video by same.author",
                    "ext": "mp4",
                }))
                second_path = Path(ydl.prepare_filename({
                    "id": "BBB222",
                    "title": "Video by same.author",
                    "ext": "mp4",
                }))

        self.assertNotEqual(first_path, second_path)
        self.assertEqual(first_path.name, "Video by same.author [AAA111].mp4")
        self.assertEqual(second_path.name, "Video by same.author [BBB222].mp4")

    def test_youtube_output_template_keeps_existing_filename(self):
        output_dir = Path("/tmp/downloads")

        options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            output_dir,
            1,
            1,
        )

        self.assertEqual(
            options["outtmpl"],
            str(output_dir / "%(title)s.%(ext)s"),
        )


class DownloadAudioOptionsTests(unittest.TestCase):
    def test_audio_options_select_best_audio_and_extract_highest_quality_mp3(self):
        output_dir = Path("/tmp/downloads")

        options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            output_dir,
            1,
            1,
            media_type=downloader.AUDIO,
        )

        self.assertEqual(options["format"], "bestaudio/best")
        self.assertEqual(
            options["postprocessors"],
            [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "0",
                }
            ],
        )
        self.assertEqual(
            options["outtmpl"],
            str(output_dir / "%(title)s.%(ext)s"),
        )

    def test_instagram_audio_keeps_id_suffix_in_output_template(self):
        output_dir = Path("/tmp/downloads")

        options = downloader._build_ydl_options(
            downloader.INSTAGRAM,
            output_dir,
            1,
            1,
            media_type=downloader.AUDIO,
        )

        self.assertEqual(
            options["outtmpl"],
            str(output_dir / "%(title)s [%(id)s].%(ext)s"),
        )

    def test_audio_output_path_resolves_postprocessed_mp3(self):
        class FakeYdl:
            def prepare_filename(self, info):
                return str(output_dir / "Example.webm")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            expected = output_dir / "Example.mp3"
            expected.touch()

            actual = downloader._resolve_output_path(
                FakeYdl(),
                {"title": "Example", "ext": "webm"},
                output_dir,
                media_type=downloader.AUDIO,
            )

        self.assertEqual(actual, expected)


class DownloadProgressHookTests(unittest.TestCase):
    def test_progress_hook_emits_complete_line_for_parallel_cli_output(self):
        hook = downloader._make_progress_hook(2, 3)
        buffer = io.StringIO()

        with contextlib.redirect_stdout(buffer):
            hook({
                "status": "downloading",
                "_percent_str": "25.0%",
                "speed": 1024 * 1024,
                "eta": 10,
            })

        output = buffer.getvalue()
        self.assertTrue(output.endswith("\n"))
        self.assertNotIn("\r", output)
        self.assertIn("[2/3]", output)

    def test_progress_snapshot_removes_ansi_color_codes_from_percent(self):
        snapshot = downloader._extract_progress_snapshot({
            "_percent_str": "\x1b[0;94m100.0%\x1b[0m",
            "speed": 1024 * 1024,
            "eta": 0,
        })

        self.assertEqual(snapshot["percent_text"], "100.0%")
        self.assertNotIn("\x1b", snapshot["percent_text"])

    def test_ydl_options_emit_speed_and_eta_progress_for_web_callback(self):
        events = []

        options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            downloader.DOWNLOADS_DIR,
            1,
            1,
            progress_callback=lambda event, data: events.append((event, data)),
        )

        hook = options["progress_hooks"][0]
        with contextlib.redirect_stdout(io.StringIO()):
            hook({
                "status": "downloading",
                "_percent_str": " 12.3%",
                "speed": 2.5 * 1024 * 1024,
                "eta": 65,
            })

        self.assertEqual(len(events), 1)
        event, data = events[0]
        self.assertEqual(event, "progress")
        self.assertEqual(data["percent_text"], "12.3%")
        self.assertEqual(data["speed_mbps"], 2.5)
        self.assertEqual(data["speed_text"], "2.50 MB/s")
        self.assertEqual(data["eta_text"], "01:05")

    def test_ydl_options_progress_uses_unknown_text_when_speed_or_eta_missing(self):
        events = []

        options = downloader._build_ydl_options(
            downloader.INSTAGRAM,
            downloader.DOWNLOADS_DIR,
            1,
            1,
            progress_callback=lambda event, data: events.append((event, data)),
        )

        hook = options["progress_hooks"][0]
        with contextlib.redirect_stdout(io.StringIO()):
            hook({"status": "downloading"})

        self.assertEqual(events[0][0], "progress")
        self.assertEqual(events[0][1]["speed_text"], "计算中")
        self.assertEqual(events[0][1]["eta_text"], "计算中")


if __name__ == "__main__":
    unittest.main()
