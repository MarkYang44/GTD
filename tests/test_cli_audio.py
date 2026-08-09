import contextlib
import io
import sys
import unittest
from unittest.mock import patch

import downloader
import main as cli_main


class CliAudioModeTests(unittest.TestCase):
    def test_parse_command_line_selects_audio_and_removes_flag(self):
        url = "https://youtu.be/example"

        media_type, audio_format, speed_mode, urls = cli_main.parse_command_line(
            ["--audio", url]
        )

        self.assertEqual(media_type, downloader.AUDIO)
        self.assertEqual(audio_format, downloader.MP3)
        self.assertEqual(speed_mode, downloader.STANDARD)
        self.assertEqual(urls, [url])

    def test_parse_command_line_defaults_to_video(self):
        url = "https://youtu.be/example"

        media_type, audio_format, speed_mode, urls = cli_main.parse_command_line(
            [url]
        )

        self.assertEqual(media_type, downloader.VIDEO)
        self.assertEqual(audio_format, downloader.MP3)
        self.assertEqual(speed_mode, downloader.STANDARD)
        self.assertEqual(urls, [url])

    def test_parse_command_line_combines_audio_and_turbo(self):
        url = "https://b23.tv/example"

        media_type, audio_format, speed_mode, urls = cli_main.parse_command_line(
            ["--audio", url, "--turbo"]
        )

        self.assertEqual(media_type, downloader.AUDIO)
        self.assertEqual(audio_format, downloader.MP3)
        self.assertEqual(speed_mode, downloader.TURBO)
        self.assertEqual(urls, [url])

    def test_parse_command_line_selects_source_flac(self):
        url = "https://b23.tv/example"

        media_type, audio_format, speed_mode, urls = cli_main.parse_command_line(
            ["--audio", "--flac", url]
        )

        self.assertEqual(media_type, downloader.AUDIO)
        self.assertEqual(audio_format, downloader.FLAC)
        self.assertEqual(speed_mode, downloader.STANDARD)
        self.assertEqual(urls, [url])

    def test_flac_flag_requires_audio_mode(self):
        with self.assertRaisesRegex(
            ValueError,
            "--flac 只能与 --audio 一起使用",
        ):
            cli_main.parse_command_line([
                "--flac",
                "https://b23.tv/example",
            ])

    def test_interactive_choice_two_selects_audio(self):
        with patch("builtins.input", return_value="2"):
            media_type = cli_main.choose_media_type()

        self.assertEqual(media_type, downloader.AUDIO)

    def test_interactive_audio_format_defaults_to_mp3(self):
        with patch("builtins.input", return_value=""):
            self.assertEqual(cli_main.choose_audio_format(), downloader.MP3)

    def test_interactive_audio_format_accepts_flac(self):
        with patch("builtins.input", return_value="2"):
            self.assertEqual(cli_main.choose_audio_format(), downloader.FLAC)

    def test_interactive_speed_mode_defaults_to_standard(self):
        with patch("builtins.input", return_value=""):
            self.assertEqual(cli_main.choose_speed_mode(), downloader.STANDARD)

    def test_main_forwards_audio_mode_and_prints_audio_summary(self):
        url = "https://youtu.be/example"
        result = {
            "platform": "YouTube",
            "title": "Example",
            "filepath": "/tmp/Example.mp3",
            "format": "MP3",
            "acodec": "mp3",
            "audio_format_requested": downloader.MP3,
            "audio_format_used": downloader.MP3,
            "audio_format_fallback": False,
            "source_acodec": "AAC",
            "source_abr_kbps": 246,
            "filesize": "1.00 MB",
            "media_type": downloader.AUDIO,
        }

        with (
            patch.object(sys, "argv", ["main.py", "--audio", url]),
            patch("main.check_ffmpeg", return_value=True),
            patch(
                "main.download_tasks",
                return_value=[((downloader.YOUTUBE, url), result)],
            ) as download_tasks,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            exit_code = cli_main.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(download_tasks.call_args.kwargs["media_type"], downloader.AUDIO)
        self.assertEqual(
            download_tasks.call_args.kwargs["audio_format"],
            downloader.MP3,
        )
        self.assertIn("MP3", output.getvalue())
        self.assertNotIn("分辨率", output.getvalue())

    def test_main_forwards_flac_and_prints_audio_fallback(self):
        url = "https://b23.tv/example"
        result = {
            "platform": "Bilibili",
            "title": "Example",
            "filepath": "/tmp/Example [MP3 V0 · 源AAC 246kbps].mp3",
            "format": "MP3 V0",
            "acodec": "mp3",
            "filesize": "1.00 MB",
            "media_type": downloader.AUDIO,
            "audio_format_requested": downloader.FLAC,
            "audio_format_used": downloader.MP3,
            "audio_format_fallback": True,
            "source_acodec": "AAC",
            "source_abr_kbps": 246,
        }

        with (
            patch.object(sys, "argv", ["main.py", "--audio", "--flac", url]),
            patch("main.check_ffmpeg", return_value=True),
            patch(
                "main.download_tasks",
                return_value=[((downloader.BILIBILI, url), result)],
            ) as download_tasks,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            exit_code = cli_main.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            download_tasks.call_args.kwargs["audio_format"],
            downloader.FLAC,
        )
        self.assertIn(
            "源站未提供 FLAC，已自动回退至 MP3 V0",
            output.getvalue(),
        )

    def test_main_forwards_turbo_and_warns_when_aria2_is_missing(self):
        url = "https://b23.tv/example"
        result = {
            "platform": "Bilibili",
            "title": "Example",
            "filepath": "/tmp/Example.mp4",
            "resolution": "1920x1080",
            "fps": 30,
            "vcodec": "h264",
            "acodec": "aac",
            "filesize": "10.00 MB",
            "media_type": downloader.VIDEO,
            "speed_mode_requested": downloader.TURBO,
            "speed_mode_used": downloader.STANDARD,
            "turbo_fallback": False,
        }
        with (
            patch.object(sys, "argv", ["main.py", "--turbo", url]),
            patch("main.check_ffmpeg", return_value=True),
            patch("main.aria2c_path", return_value=None),
            patch(
                "main.download_tasks",
                return_value=[((downloader.BILIBILI, url), result)],
            ) as tasks,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            exit_code = cli_main.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(tasks.call_args.kwargs["speed_mode"], downloader.TURBO)
        self.assertIn("未检测到 aria2c", output.getvalue())
        self.assertIn("标准模式", output.getvalue())


if __name__ == "__main__":
    unittest.main()
