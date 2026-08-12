import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app as web_app
import downloader
import output_files
import folder_picker
import main as cli_main
from task_control import CancellationToken, TaskManager, TaskSeed


class DownloadDirectoryTests(unittest.TestCase):
    def test_output_files_directory_helpers_match_downloader_behavior(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "output"
            self.assertEqual(
                output_files.ensure_downloads_dir(
                    "output", project_dir=root, downloads_dir=root / "downloads"
                ),
                downloader.ensure_downloads_dir(str(target)),
            )

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

    def test_batch_reuses_one_validated_download_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            probe_count = 0
            original_open = Path.open

            def count_probes(path, *args, **kwargs):
                nonlocal probe_count
                if path.name.startswith(".__mvd_write_test_"):
                    probe_count += 1
                return original_open(path, *args, **kwargs)

            with (
                patch.object(Path, "open", new=count_probes),
                patch("downloader._download_bilibili", return_value={}),
            ):
                downloader.download_tasks(
                    [
                        (downloader.BILIBILI, "https://b23.tv/one"),
                        (downloader.BILIBILI, "https://b23.tv/two"),
                    ],
                    output_dir=directory,
                )

            self.assertEqual(probe_count, 1)

    def test_direct_download_still_validates_download_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            probe_count = 0
            original_open = Path.open

            def count_probes(path, *args, **kwargs):
                nonlocal probe_count
                if path.name.startswith(".__mvd_write_test_"):
                    probe_count += 1
                return original_open(path, *args, **kwargs)

            with (
                patch.object(Path, "open", new=count_probes),
                patch("downloader._download_bilibili", return_value={}),
            ):
                downloader.download_video(
                    "https://b23.tv/example",
                    platform=downloader.BILIBILI,
                    output_dir=directory,
                )

            self.assertEqual(probe_count, 1)

    def test_prepared_output_directory_rejects_raw_relative_path_and_none(self):
        for path in (".", None):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "已验证下载目录"):
                    downloader._prepared_output_dir(path)

    def test_public_download_video_has_no_validation_bypass_parameter(self):
        self.assertNotIn(
            "output_dir_validated",
            inspect.signature(downloader.download_video).parameters,
        )
        with self.assertRaises(TypeError):
            downloader.download_video(
                "https://b23.tv/example",
                output_dir_validated=True,
            )

    def test_direct_download_validates_input_before_directory_io(self):
        token = CancellationToken()
        token.cancel()
        cases = (
            ("unsupported URL", {"url": "not-a-url"}, None),
            ("invalid media type", {"url": "https://youtu.be/x", "media_type": "text"}, ValueError),
            ("cancelled", {"url": "https://youtu.be/x", "cancel_token": token}, Exception),
        )

        for name, kwargs, expected_error in cases:
            with self.subTest(name=name), patch(
                "downloader.ensure_downloads_dir",
            ) as ensure:
                if expected_error is None:
                    self.assertIsNone(downloader.download_video(**kwargs))
                else:
                    with self.assertRaises(expected_error):
                        downloader.download_video(**kwargs)
                ensure.assert_not_called()

    def test_batch_and_runner_keep_selected_directory(self):
        calls = []

        def runner(url, **kwargs):
            calls.append(kwargs)
            return {
                "title": "ok",
                "filepath": str(Path(kwargs["output_dir"]) / "ok.mp4"),
            }

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "media"
            manager = TaskManager(runner, max_workers=1)
            batch = manager.create_batch(
                [TaskSeed("youtube", "https://youtu.be/x", "X", 1)],
                "video",
                "mp3",
                "standard",
                str(target),
            )
            self.assertTrue(manager.wait_for_idle())
            snapshot = manager.snapshot(batch["id"])
            manager.shutdown()

        resolved = str(target.resolve())
        self.assertEqual(snapshot["download_dir"], resolved)
        self.assertEqual(snapshot["tasks"][0]["download_dir"], resolved)
        self.assertEqual(calls[0]["output_dir"], resolved)
        self.assertNotIn("output_dir_validated", calls[0])


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
            probe_count = 0
            original_open = Path.open

            def count_probes(path, *args, **kwargs):
                nonlocal probe_count
                if path.name.startswith(".__mvd_write_test_"):
                    probe_count += 1
                return original_open(path, *args, **kwargs)

            with patch.object(web_app.task_manager, "create_batch") as create:
                resolved = str(target.resolve())
                create.return_value = {
                    "id": "batch",
                    "total": 1,
                    "download_dir": resolved,
                }
                with patch.object(Path, "open", new=count_probes):
                    response = self.client.post(
                        "/api/download",
                        json={
                            "urls": ["https://youtu.be/example"],
                            "download_dir": str(target),
                        },
                    )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(create.call_args.args[4]), resolved)
        self.assertEqual(response.get_json()["download_dir"], resolved)
        self.assertEqual(probe_count, 1)

    def test_web_invalid_directory_precedes_unsupported_url(self):
        with tempfile.TemporaryDirectory() as temporary:
            invalid = Path(temporary) / "not-a-directory"
            invalid.write_text("data", encoding="utf-8")
            with patch.object(web_app.task_manager, "create_batch") as create:
                response = self.client.post(
                    "/api/download",
                    json={
                        "urls": ["https://example.com/unsupported"],
                        "download_dir": str(invalid),
                    },
                )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error_code"], "INVALID_DOWNLOAD_DIR")
        create.assert_not_called()

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
        html = "\n".join(
            (
                self.client.get("/").get_data(as_text=True),
                Path("static/css/index.css").read_text(encoding="utf-8"),
                Path("static/js/index.js").read_text(encoding="utf-8"),
            )
        )

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
