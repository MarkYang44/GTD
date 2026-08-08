import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import downloader


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


class BilibiliDownloadOptionsTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
