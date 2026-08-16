import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import downloader
import main as cli_main
from collection_resolver import CollectionEntry, CollectionPreview


class CliAudioModeTests(unittest.TestCase):
    def test_cli_source_uses_gtd_public_identity(self):
        source = Path("main.py").read_text(encoding="utf-8")

        self.assertIn("GTD — Generalized Transmedia Downloader — 命令行入口", source)
        self.assertIn('print(f"🎬 GTD · {media_name}批量下载")', source)

    def test_command_line_download_flow_validates_directory_once(self):
        url = "https://youtu.be/example"
        result = {
            "platform": "YouTube",
            "title": "Example",
            "filepath": "/tmp/Example.mp4",
            "resolution": "1920x1080",
            "fps": 30,
            "vcodec": "h264",
            "acodec": "aac",
            "filesize": "1.00 MB",
            "media_type": downloader.VIDEO,
            "speed_mode_used": downloader.STANDARD,
        }
        probe_count = 0
        original_open = Path.open

        def count_probes(path, *args, **kwargs):
            nonlocal probe_count
            if path.name.startswith(".__mvd_write_test_"):
                probe_count += 1
            return original_open(path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temporary, \
            patch.object(sys, "argv", ["main.py", "--output-dir", temporary, url]), \
            patch("main.check_ffmpeg", return_value=True), \
            patch("main.resolve_cli_tasks", return_value=[(downloader.YOUTUBE, url)]), \
            patch("downloader.download_video", return_value=result), \
            patch.object(Path, "open", new=count_probes), \
            contextlib.redirect_stdout(io.StringIO()):
            exit_code = cli_main.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(probe_count, 1)

    def test_parse_command_line_selects_audio_and_removes_flag(self):
        url = "https://youtu.be/example"

        media_type, audio_format, speed_mode, urls, item_selection, output_dir = cli_main.parse_command_line(
            ["--audio", url]
        )

        self.assertEqual(media_type, downloader.AUDIO)
        self.assertEqual(audio_format, downloader.MP3)
        self.assertEqual(speed_mode, downloader.STANDARD)
        self.assertEqual(urls, [url])
        self.assertIsNone(item_selection)
        self.assertIsNone(output_dir)

    def test_parse_command_line_defaults_to_video(self):
        url = "https://youtu.be/example"

        media_type, audio_format, speed_mode, urls, item_selection, output_dir = cli_main.parse_command_line(
            [url]
        )

        self.assertEqual(media_type, downloader.VIDEO)
        self.assertEqual(audio_format, downloader.MP3)
        self.assertEqual(speed_mode, downloader.STANDARD)
        self.assertEqual(urls, [url])
        self.assertIsNone(item_selection)
        self.assertIsNone(output_dir)

    def test_parse_command_line_combines_audio_and_turbo(self):
        url = "https://b23.tv/example"

        media_type, audio_format, speed_mode, urls, item_selection, output_dir = cli_main.parse_command_line(
            ["--audio", url, "--turbo"]
        )

        self.assertEqual(media_type, downloader.AUDIO)
        self.assertEqual(audio_format, downloader.MP3)
        self.assertEqual(speed_mode, downloader.TURBO)
        self.assertEqual(urls, [url])
        self.assertIsNone(item_selection)
        self.assertIsNone(output_dir)

    def test_parse_command_line_selects_source_flac(self):
        url = "https://b23.tv/example"

        media_type, audio_format, speed_mode, urls, item_selection, output_dir = cli_main.parse_command_line(
            ["--audio", "--flac", url]
        )

        self.assertEqual(media_type, downloader.AUDIO)
        self.assertEqual(audio_format, downloader.FLAC)
        self.assertEqual(speed_mode, downloader.STANDARD)
        self.assertEqual(urls, [url])
        self.assertIsNone(item_selection)
        self.assertIsNone(output_dir)

    def test_parse_command_line_accepts_source_audio_and_wav(self):
        for value in (downloader.SOURCE, downloader.WAV):
            with self.subTest(value=value):
                media, audio_format, speed, urls, item_selection, output_dir = (
                    cli_main.parse_command_line(
                        ["--audio", "--audio-format", value, "https://youtu.be/x"]
                    )
                )

                self.assertEqual(media, downloader.AUDIO)
                self.assertEqual(audio_format, value)
                self.assertEqual(speed, downloader.STANDARD)
                self.assertEqual(urls, ["https://youtu.be/x"])
                self.assertIsNone(item_selection)
                self.assertIsNone(output_dir)

    def test_parse_command_line_accepts_output_directory_without_lowercasing(self):
        parsed = cli_main.parse_command_line(
            ["--output-dir", r"D:\\Media\\My Videos", "https://youtu.be/x"]
        )

        self.assertEqual(parsed[5], r"D:\\Media\\My Videos")

    def test_parse_command_line_accepts_item_selection(self):
        parsed = cli_main.parse_command_line(
            ["--items", "1,3-5", "https://youtube.com/playlist?list=x"]
        )

        self.assertEqual(parsed[4], "1,3-5")

    def test_audio_format_requires_audio_and_rejects_conflicts(self):
        with self.assertRaisesRegex(ValueError, "--audio-format 只能与 --audio"):
            cli_main.parse_command_line(
                ["--audio-format", "wav", "https://youtu.be/x"]
            )
        with self.assertRaisesRegex(ValueError, "不能同时"):
            cli_main.parse_command_line(
                ["--audio", "--flac", "--audio-format", "wav", "https://youtu.be/x"]
            )

    def test_parser_rejects_missing_values_and_unknown_flags(self):
        for args in (["--audio", "--audio-format"], ["--items"]):
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, "需要提供"):
                cli_main.parse_command_line(args)
        with self.assertRaisesRegex(ValueError, "未知参数"):
            cli_main.parse_command_line(["--wat", "https://youtu.be/x"])

    def test_parse_item_selection_supports_all_ranges_and_limit(self):
        available = [str(index) for index in range(1, 102)]

        self.assertEqual(
            cli_main.parse_item_selection("1,3-5", available),
            ["1", "3", "4", "5"],
        )
        self.assertEqual(
            len(cli_main.parse_item_selection("all", available[:100])),
            100,
        )
        with self.assertRaisesRegex(ValueError, "最多选择 100"):
            cli_main.parse_item_selection("all", available)

    def test_parse_item_selection_rejects_unknown_or_duplicate_items(self):
        with self.assertRaisesRegex(ValueError, "不存在"):
            cli_main.parse_item_selection("1,4", ["1", "2", "3"])
        with self.assertRaisesRegex(ValueError, "重复"):
            cli_main.parse_item_selection("1,1", ["1", "2"])

    def test_noninteractive_collection_requires_items(self):
        preview = CollectionPreview(
            id="preview",
            title="List",
            platform=downloader.YOUTUBE,
            entries=(
                CollectionEntry(
                    id="1",
                    title="A",
                    platform=downloader.YOUTUBE,
                    url="https://youtu.be/a",
                    position=1,
                    thumbnail=None,
                    selectable=True,
                    unavailable_reason=None,
                ),
            ),
            is_single=False,
            requires_selection=True,
        )
        with patch("main.resolve_collection", return_value=preview):
            with self.assertRaisesRegex(ValueError, "--items"):
                cli_main.resolve_cli_tasks(
                    ["https://youtube.com/playlist?list=x"],
                    item_selection=None,
                    interactive=False,
                )

    def test_collection_selection_preserves_requested_order(self):
        preview = CollectionPreview(
            id="preview",
            title="List",
            platform=downloader.YOUTUBE,
            entries=tuple(
                CollectionEntry(
                    id=str(index),
                    title=f"Item {index}",
                    platform=downloader.YOUTUBE,
                    url=f"https://youtu.be/{index}",
                    position=index,
                    thumbnail=None,
                    selectable=True,
                    unavailable_reason=None,
                )
                for index in range(1, 4)
            ),
            is_single=False,
            requires_selection=True,
        )
        with patch("main.resolve_collection", return_value=preview):
            tasks = cli_main.resolve_cli_tasks(
                ["https://youtube.com/playlist?list=x"],
                item_selection="3,1",
                interactive=False,
            )

        self.assertEqual(
            tasks,
            [
                (downloader.YOUTUBE, "https://youtu.be/3"),
                (downloader.YOUTUBE, "https://youtu.be/1"),
            ],
        )

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

    def test_interactive_audio_format_accepts_source_and_wav(self):
        with patch("builtins.input", side_effect=["3", EOFError]):
            self.assertEqual(cli_main.choose_audio_format(), downloader.SOURCE)
        with patch("builtins.input", side_effect=["4", EOFError]):
            self.assertEqual(cli_main.choose_audio_format(), downloader.WAV)

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
                "main.resolve_cli_tasks",
                return_value=[(downloader.YOUTUBE, url)],
            ),
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
                "main.resolve_cli_tasks",
                return_value=[(downloader.BILIBILI, url)],
            ),
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
                "main.resolve_cli_tasks",
                return_value=[(downloader.BILIBILI, url)],
            ),
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
