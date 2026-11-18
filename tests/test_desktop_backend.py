"""Desktop API contracts without an external network or native window."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from desktop_backend import create_desktop_app
from media_sources import cookie_input
from web_runtime import get_runtime
from yt_dlp import YoutubeDL


class DesktopBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.data = self.root / "GTD 桌面 data"
        self.downloads = self.root / "My Downloads 下载" / "GTD"
        self.app = create_desktop_app(self.data, self.downloads, "secret")
        self.client = self.app.test_client()
        self.auth = {"Host": "127.0.0.1:51234", "Authorization": "Bearer secret"}
        self.addCleanup(get_runtime(self.app).task_manager.shutdown)

    def test_backend_auth_and_allowed_routes(self):
        self.assertEqual(self.client.get("/api/batches").status_code, 403)
        self.assertEqual(self.client.get("/api/batches", headers={
            **self.auth, "Origin": "https://example.org",
        }).status_code, 403)
        self.assertEqual(self.client.get("/api/batches", headers={
            **self.auth, "Host": "example.org",
        }).status_code, 403)
        self.assertEqual(self.client.get("/api/batches", headers=self.auth).json, {"batches": []})
        self.assertEqual(self.client.get("/", headers=self.auth).status_code, 404)
        self.assertEqual(self.client.post("/api/select-directory", headers=self.auth).status_code, 404)

    def test_settings_save_atomically_and_validate_directory(self):
        path = "/api/desktop/settings"
        response = self.client.get(path, headers=self.auth)
        self.assertEqual(response.json["default_download_dir"], str(self.downloads))
        invalid = self.root / "file"
        invalid.touch()
        response = self.client.post(path, headers=self.auth, json={
            "theme": "light", "download_dir": str(invalid),
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get(path, headers=self.auth).json["theme"], "system")
        target = self.root / "Custom 下载"
        response = self.client.post(path, headers=self.auth, json={
            "theme": "light", "language": "zh", "download_dir": str(target),
        })
        self.assertEqual(response.status_code, 200)
        recreated = create_desktop_app(self.data, self.downloads, "secret")
        self.assertEqual(recreated.test_client().get(path, headers=self.auth).json["download_dir"], str(target))
        self.assertEqual(response.json["theme"], "light")

    def test_cookie_import_validates_and_keeps_private_copy(self):
        path = "/api/desktop/cookies"
        cookie = self.root / "导出 cookies.txt"
        cookie.write_text("test", encoding="utf-8")
        self.assertEqual(self.client.post(path, headers=self.auth, json={
            "platform": "youtube", "path": str(cookie),
        }).status_code, 400)
        cookie.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tname\tvalue\n",
                          encoding="utf-8")
        imported = self.client.post(path, headers=self.auth, json={"platform": "youtube", "path": str(cookie)})
        self.assertTrue(imported.json["cookies"]["youtube"])
        self.assertNotIn("value", imported.get_data(as_text=True))
        copy = self.data / "cookies" / "youtube_cookies.txt"
        self.assertEqual(copy.read_bytes(), cookie.read_bytes())
        if os.name != "nt":
            self.assertEqual(copy.stat().st_mode & 0o077, 0)
        with patch.dict(os.environ, {"GTD_COOKIE_DIR": str(copy.parent)}):
            snapshot = cookie_input(copy)
            with YoutubeDL({"cookiefile": snapshot, "quiet": True}) as downloader:
                self.assertEqual(downloader.cookiejar.get_cookie_header("https://www.youtube.com"), "name=value")
                removed = self.client.post(path, headers=self.auth, json={"platform": "youtube", "path": None})
                self.assertFalse(removed.json["cookies"]["youtube"])
        self.assertFalse(copy.exists())
        self.assertTrue(cookie.exists())

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires FFmpeg tools")
    def test_native_file_extraction_and_restart_history(self):
        source = self.root / "本地 clip.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=64x64:r=10",
                        "-f", "lavfi", "-i", "sine=frequency=440", "-t", "0.5",
                        "-c:v", "mpeg4", "-c:a", "aac", str(source)], check=True)
        result = self.client.post("/api/desktop/extract", headers=self.auth, json={
            "path": str(source), "audio_format": "mp3",
        })
        self.assertEqual(result.status_code, 202, result.get_data(as_text=True))
        batch_id = result.json["batch_id"]
        self.assertTrue(get_runtime(self.app).task_manager.wait_for_idle(20))
        path = f"/api/batch/{batch_id}"
        batch = self.client.get(path, headers=self.auth).json
        task = batch["tasks"][0]
        self.assertEqual(task["status"], "completed", task)
        output = Path(task["result"]["filepath"])
        self.assertEqual(output.parent, self.downloads)
        self.assertEqual(output.suffix, ".mp3")
        self.assertTrue(output.is_file())
        self.assertTrue(source.is_file())
        recreated = create_desktop_app(self.data, self.downloads, "secret")
        self.addCleanup(get_runtime(recreated).task_manager.shutdown)
        self.assertTrue(recreated.test_client().get(path, headers=self.auth).json["tasks"][0]["result"]["local_extraction"])

    def test_bulk_conflicts_are_reported_individually(self):
        result = self.client.post("/api/desktop/batch-action", headers=self.auth, json={
            "action": "cancel", "tasks": [{"batch_id": "missing", "task_id": "task"}],
        })
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["succeeded"], 0)
        self.assertEqual(result.json["errors"][0]["task_id"], "task")

    def test_sidecar_exits_when_parent_closes_stdin(self):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", 0))
            except PermissionError:
                self.skipTest("environment does not allow loopback listeners")
        script = Path(__file__).resolve().parent.parent / "desktop_backend.py"
        with subprocess.Popen([sys.executable, str(script), "--data-dir", str(self.data),
                               "--download-dir", str(self.downloads)],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE) as child:
            try:
                # The token and EOF use the same pipe even during startup.
                stdout, stderr = child.communicate(b"test-token\n", timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                stdout, stderr = child.communicate()
                self.fail(f"Sidecar did not exit after EOF. stdout={stdout!r} stderr={stderr!r}")
            self.assertEqual(child.returncode, 0, stderr.decode("utf-8", errors="replace"))
            self.assertRegex(stdout, rb"^GTD_READY [0-9]+\r?\n$")
