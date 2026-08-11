import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app as web_app
import downloader
import folder_picker
import main as cli_main
from task_control import TaskManager, TaskSeed


class DownloadDirectoryTests(unittest.TestCase):
    def test_blank_value_keeps_default_downloads_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            default = Path(temporary) / "downloads"
            with patch.object(downloader, "DOWNLOADS_DIR", default):
                resolved = downloader.ensure_downloads_dir("")

            self.assertEqual(resolved, default.resolve())
            self.assertTrue(resolved.is_dir())
            self.assertEqual(list(resolved.glob(".__mvd_write_test_*.tmp")), [])

    def test_custom_absolute_and_relative_directories_are_created(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(downloader, "PROJECT_DIR", root):
                relative = downloader.ensure_downloads_dir("nested/output")
            absolute = downloader.ensure_downloads_dir(root / "absolute")

            self.assertEqual(relative, (root / "nested/output").resolve())
            self.assertEqual(absolute, (root / "absolute").resolve())
            self.assertTrue(relative.is_dir())
            self.assertTrue(absolute.is_dir())

    def test_existing_file_is_rejected_as_download_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "not-a-folder"
            target.write_text("data", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "无法创建下载目录|不是文件夹"):
                downloader.ensure_downloads_dir(target)

    def test_batch_and_runner_keep_selected_directory(self):
        calls = []

        def runner(url, **kwargs):
            calls.append(kwargs)
            return {
                "title": "ok",
                "filepath": str(Path(kwargs["output_dir"]) / "ok.mp4"),
            }

        manager = TaskManager(runner, max_workers=1)
        batch = manager.create_batch(
            [TaskSeed("youtube", "https://youtu.be/x", "X", 1)],
            "video",
            "mp3",
            "standard",
            "D:/Media",
        )
        self.assertTrue(manager.wait_for_idle())
        snapshot = manager.snapshot(batch["id"])
        manager.shutdown()

        self.assertEqual(snapshot["download_dir"], "D:/Media")
        self.assertEqual(snapshot["tasks"][0]["download_dir"], "D:/Media")
        self.assertEqual(calls[0]["output_dir"], "D:/Media")


class FolderPickerTests(unittest.TestCase):
    def test_windows_picker_uses_precompiled_native_helper(self):
        with (
            patch.object(folder_picker.sys, "platform", "win32"),
            patch(
                "folder_picker._choose_windows",
                return_value="D:\\Media",
            ) as choose,
        ):
            selected = folder_picker.choose_folder(".")

        choose.assert_called_once()
        self.assertEqual(selected, "D:\\Media")

    @unittest.skipUnless(sys.platform == "win32", "Windows-only COM smoke test")
    def test_windows_modern_picker_helper_is_available(self):
        self.assertTrue(folder_picker.validate_windows_picker())

    @unittest.skipUnless(sys.platform == "win32", "Windows-only launch behavior")
    def test_windows_picker_is_explicitly_shown_from_hidden_web_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "picked"

            def complete_picker(command, **kwargs):
                Path(command[2]).write_text(str(target), encoding="utf-8")
                self.assertEqual(kwargs["startupinfo"].wShowWindow, 1)
                self.assertTrue(
                    kwargs["startupinfo"].dwFlags
                    & folder_picker.subprocess.STARTF_USESHOWWINDOW
                )
                self.assertNotIn("creationflags", kwargs)
                return SimpleNamespace(returncode=0)

            with (
                patch(
                    "folder_picker.prepare_windows_picker",
                    return_value=Path(temporary) / "folder-picker.exe",
                ),
                patch("folder_picker.subprocess.run", side_effect=complete_picker),
            ):
                selected = folder_picker._choose_windows(Path(temporary))

        self.assertEqual(selected, str(target))

    def test_macos_picker_uses_osascript_and_cancel_returns_none(self):
        result = SimpleNamespace(returncode=0, stdout="\n", stderr="")
        with (
            patch.object(folder_picker.sys, "platform", "darwin"),
            patch("folder_picker._run_picker", return_value=result) as run,
        ):
            selected = folder_picker.choose_folder(".")

        self.assertEqual(run.call_args.args[0][0], "osascript")
        self.assertIsNone(selected)

    def test_unsupported_platform_explains_manual_fallback(self):
        with patch.object(folder_picker.sys, "platform", "linux"):
            with self.assertRaisesRegex(
                folder_picker.FolderPickerUnavailable,
                "手动输入路径",
            ):
                folder_picker.choose_folder(".")


class DownloadLocationSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.client = web_app.app.test_client()

    def test_web_download_resolves_and_forwards_custom_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "web-output"
            with patch.object(web_app.task_manager, "create_batch") as create:
                create.return_value = {"id": "batch", "total": 1}
                response = self.client.post(
                    "/api/download",
                    json={
                        "urls": ["https://youtu.be/example"],
                        "download_dir": str(target),
                    },
                )

        self.assertEqual(response.status_code, 200)
        resolved = str(target.resolve())
        self.assertEqual(create.call_args.args[4], resolved)
        self.assertEqual(response.get_json()["download_dir"], resolved)

    def test_web_picker_endpoint_returns_verified_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "picked"
            with patch("app.choose_folder", return_value=str(target)):
                response = self.client.post("/api/select-directory", json={})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.get_json()["download_dir"],
                str(target.resolve()),
            )
            self.assertTrue(target.is_dir())

    def test_web_page_exposes_manual_and_native_folder_controls(self):
        html = self.client.get("/").get_data(as_text=True)

        self.assertIn('id="videoDownloadDir"', html)
        self.assertIn('id="audioDownloadDir"', html)
        self.assertIn("chooseDownloadDirectory('video')", html)
        self.assertIn(
            "download_dir: pendingDownloadSettings.downloadDir || null",
            html,
        )


class CliDownloadLocationTests(unittest.TestCase):
    def test_interactive_default_keeps_downloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            default = Path(temporary) / "downloads"
            with (
                patch.object(cli_main, "DOWNLOADS_DIR", default),
                patch.object(downloader, "DOWNLOADS_DIR", default),
                patch("builtins.input", return_value=""),
            ):
                selected = cli_main.choose_download_location()

        self.assertEqual(selected, default.resolve())

    def test_interactive_native_picker_is_validated(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "chosen"
            with (
                patch("builtins.input", return_value="3"),
                patch("main.choose_folder", return_value=str(target)),
            ):
                selected = cli_main.choose_download_location()

        self.assertEqual(selected, target.resolve())


if __name__ == "__main__":
    unittest.main()
