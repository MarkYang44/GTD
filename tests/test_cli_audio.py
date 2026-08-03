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

        media_type, urls = cli_main.parse_command_line(["--audio", url])

        self.assertEqual(media_type, downloader.AUDIO)
        self.assertEqual(urls, [url])

    def test_parse_command_line_defaults_to_video(self):
        url = "https://youtu.be/example"

        media_type, urls = cli_main.parse_command_line([url])

        self.assertEqual(media_type, downloader.VIDEO)
        self.assertEqual(urls, [url])

    def test_interactive_choice_two_selects_audio(self):
        with patch("builtins.input", return_value="2"):
            media_type = cli_main.choose_media_type()

        self.assertEqual(media_type, downloader.AUDIO)

    def test_main_forwards_audio_mode_and_prints_audio_summary(self):
        url = "https://youtu.be/example"
        result = {
            "platform": "YouTube",
            "title": "Example",
            "filepath": "/tmp/Example.mp3",
            "format": "MP3",
            "acodec": "mp3",
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
        self.assertIn("MP3", output.getvalue())
        self.assertNotIn("分辨率", output.getvalue())


if __name__ == "__main__":
    unittest.main()
