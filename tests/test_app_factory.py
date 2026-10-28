"""Application lifecycle and real request isolation without external downloads."""

import os
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

import app as web_app
from collection_resolver import CollectionPreview
from task_control import TaskManager
from flask import has_app_context
from web_runtime import get_runtime


class AppFactoryTests(unittest.TestCase):
    def test_import_does_not_open_history_or_construct_execution_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            history = Path(temporary) / "state" / "tasks.sqlite3"
            program = """
import os
from pathlib import Path
import app
assert not Path(os.environ['GTD_HISTORY_PATH']).exists(), 'import opened task history'
assert 'gtd.runtime' not in app.app.extensions, 'import constructed execution resources'
"""
            environment = dict(os.environ, GTD_HISTORY_PATH=str(history),
                               GTD_UPLOAD_ROOT=str(Path(temporary) / "uploads"))
            result = subprocess.run([sys.executable, "-c", program], env=environment,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def factory(self, *args, **kwargs):
        factory = getattr(web_app, "create_app", None)
        self.assertTrue(callable(factory), "Web module must expose create_app")
        return factory(*args, **kwargs)

    def test_two_applications_have_separate_history_and_preview_stores(self):
        with tempfile.TemporaryDirectory() as temporary:
            applications = [self.factory({
                "TESTING": True,
                "GTD_HISTORY_PATH": str(Path(temporary) / name / "tasks.sqlite3"),
                "GTD_UPLOAD_ROOT": str(Path(temporary) / name / "uploads"),
            }) for name in ("first", "second")]
            for application in applications:
                self.assertNotIn("gtd.runtime", application.extensions)
                self.assertEqual(application.test_client().get("/api/batches").json,
                                 {"batches": []})
                self.addCleanup(application.extensions["gtd.runtime"].task_manager.shutdown)
            first, second = [application.extensions["gtd.runtime"] for application in applications]
            self.assertIsNot(first.task_manager, second.task_manager)
            preview = CollectionPreview("isolated-preview", "Sample", "youtube", (), False)
            first.preview_store.put(preview)
            self.assertIsNone(second.preview_store.get(preview.id))
            self.assertTrue(all(Path(application.config["GTD_HISTORY_PATH"]).is_file()
                                for application in applications))

    def test_factory_request_uses_its_injected_manager_and_preserves_endpoints(self):
        calls = []
        def runner(url, **kwargs):
            calls.append((url, kwargs["media_type"]))
            return {"title": "sample", "filepath": "/tmp/sample.mp4"}

        manager = TaskManager(runner, max_workers=1)
        self.addCleanup(manager.shutdown)
        with tempfile.TemporaryDirectory() as temporary:
            application = self.factory({"TESTING": True,
                "GTD_HISTORY_PATH": str(Path(temporary) / "unused.sqlite3"),
                "GTD_UPLOAD_ROOT": str(Path(temporary) / "uploads")}, manager=manager)
            response = application.test_client().post("/api/download", json={
                "urls": ["https://youtu.be/example"], "download_dir": temporary})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(manager.wait_for_idle())
            self.assertEqual(calls, [("https://youtu.be/example", "video")])
            snapshot = application.test_client().get("/api/batch/" + response.json["batch_id"])
            self.assertEqual(snapshot.json["tasks"][0]["status"], "completed")
            self.assertFalse(Path(application.config["GTD_HISTORY_PATH"]).exists())
            self.assertEqual(application.url_map.bind("").build("index"), "/")
            self.assertEqual(application.url_map.bind("").build("audio_extract.page"), "/extract-audio")

    def test_concurrent_first_use_returns_one_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            application = self.factory({"GTD_HISTORY_PATH": str(Path(temporary) / "tasks.sqlite3"),
                "GTD_UPLOAD_ROOT": str(Path(temporary) / "uploads")})
            with ThreadPoolExecutor(max_workers=6) as pool:
                runtimes = list(pool.map(lambda _: get_runtime(application), range(12)))
            self.addCleanup(runtimes[0].task_manager.shutdown)
            self.assertTrue(all(runtime is runtimes[0] for runtime in runtimes))

    def test_extraction_worker_captures_its_application_store_without_flask_context(self):
        calls = []
        def extract(key, *, store, **kwargs):
            calls.append((store.root, has_app_context(), store.resolve(key)[1]))
            return {"title": "Sample", "filepath": "/tmp/sample.mp3"}

        with tempfile.TemporaryDirectory() as temporary:
            applications = [self.factory({"TESTING": True,
                "GTD_HISTORY_PATH": str(Path(temporary) / name / "tasks.sqlite3"),
                "GTD_UPLOAD_ROOT": str(Path(temporary) / name / "uploads")}) for name in ("one", "two")]
            with patch("web_runtime.extract_audio", side_effect=extract):
                for number, application in enumerate(applications):
                    response = application.test_client().post("/api/extract-audio", data={
                        "video": (io.BytesIO(b"local fixture"), f"clip-{number}.mp4")})
                    self.assertEqual(response.status_code, 202)
                    runtime = get_runtime(application)
                    self.addCleanup(runtime.task_manager.shutdown)
                    self.assertTrue(runtime.task_manager.wait_for_idle())
            self.assertEqual(calls, [(Path(application.config["GTD_UPLOAD_ROOT"]), False, f"clip-{number}.mp4")
                                    for number, application in enumerate(applications)])

