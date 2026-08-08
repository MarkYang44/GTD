import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as web_app
import downloader
import main as cli_main


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

    def test_removes_trailing_share_punctuation_but_keeps_query(self):
        share_text = (
            "推荐：https://www.bilibili.com/video/BV1xRuu6fEeA?p=2】。"
        )

        self.assertEqual(
            downloader.normalize_url(share_text),
            "https://www.bilibili.com/video/BV1xRuu6fEeA?p=2",
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
                self.assertEqual(
                    options["throttled_rate"],
                    256 * 1024,
                )

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


class BilibiliSurfaceIntegrationTests(unittest.TestCase):
    def setUp(self):
        web_app._batches.clear()
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

        with patch("app.threading.Thread") as thread_class:
            response = self.client.post(
                "/api/download",
                json={"urls": [url], "media_type": downloader.AUDIO},
            )

        self.assertEqual(response.status_code, 200)
        batch = web_app._batches[response.get_json()["batch_id"]]
        self.assertEqual(
            batch["tasks"][0]["platform"],
            downloader.BILIBILI,
        )
        self.assertEqual(batch["tasks"][0]["platform_name"], "Bilibili")
        self.assertEqual(
            thread_class.call_args.kwargs["args"][2],
            downloader.AUDIO,
        )

    def test_page_names_bilibili_without_adding_new_input(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("YOUTUBE + INSTAGRAM + BILIBILI / ONLINE", html)
        self.assertIn("YouTube / Instagram / Bilibili", html)
        self.assertEqual(html.count('id="videoUrls"'), 1)
        self.assertEqual(html.count('id="audioUrls"'), 1)

    def test_cli_and_api_errors_name_all_supported_platforms(self):
        source = Path("main.py").read_text(encoding="utf-8")
        app_source = Path("app.py").read_text(encoding="utf-8")

        self.assertIn("YouTube、Instagram 或 Bilibili", source)
        self.assertIn("YouTube、Instagram 或 Bilibili", app_source)


class BilibiliDocumentationTests(unittest.TestCase):
    def test_readme_documents_bilibili_workflow_and_boundaries(self):
        readme = Path("README.md").read_text(encoding="utf-8")

        required = [
            "YouTube + Instagram + Bilibili",
            "bilibili_cookies.txt",
            "https://www.bilibili.com/video/BV",
            "https://www.bilibili.com/video/av",
            "https://b23.tv/",
            "分 P",
            "只下载链接指定的分 P",
            "不自动展开合集、收藏夹或番剧",
            "标题 [内容ID].mp4",
            "标题 [内容ID].mp3",
            "Bilibili 风控或 `HTTP 412`",
            "10 MB HTTP 分块",
            "最多同时运行 2 个 Bilibili 下载任务",
            "实际速度仍取决于 Bilibili 分配的 CDN 和网络路由",
        ]
        for text in required:
            with self.subTest(text=text):
                self.assertIn(text, readme)


class ShareTextSurfaceTests(unittest.TestCase):
    def setUp(self):
        web_app._batches.clear()
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

        with patch("app.threading.Thread"):
            response = self.client.post(
                "/api/download",
                json={"urls": [share_text], "media_type": downloader.VIDEO},
            )

        self.assertEqual(response.status_code, 200)
        batch = web_app._batches[response.get_json()["batch_id"]]
        self.assertEqual(batch["tasks"][0]["url"], expected)

    def test_page_and_readme_explain_share_text_input(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")
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
