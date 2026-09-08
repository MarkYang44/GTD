"""Real upload -> queue -> FFmpeg -> browser download, using isolated storage."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

from flask import Flask, jsonify
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from test_reliability import QuietHandler, ROOT
from audio_extract_routes import extraction_blueprint, with_download_links
from local_audio import UploadStore, extract_audio
from task_control import TaskManager


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class ExtractionBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        cls.video = root / 'sample.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=s=32x32:d=0.4','-f','lavfi','-i','sine=duration=0.4','-c:v','mpeg4','-c:a','aac','-shortest',str(cls.video)],check=True)
        store = UploadStore(root / 'inputs')
        manager = TaskManager(lambda key, **kwargs: extract_audio(key, store=store, **kwargs), capability_aware_runner=True)
        cls.addClassCleanup(manager.shutdown)
        app = Flask(__name__, template_folder=str(ROOT / 'templates'), static_folder=str(ROOT / 'static'))
        app.register_blueprint(extraction_blueprint(manager, store, str(root / 'out')))
        app.add_url_rule('/kozekilmu/tracks', 'kozekilmu_tracks', lambda: 'guide')
        app.add_url_rule('/api/batch/<batch_id>', 'status', lambda batch_id: jsonify(with_download_links(manager.snapshot(batch_id))))
        cls.server = make_server('127.0.0.1', 0, app, request_handler=QuietHandler)
        thread = threading.Thread(target=cls.server.serve_forever, daemon=True); thread.start()
        def stop():
            cls.server.shutdown(); thread.join(5); cls.server.server_close()
        cls.addClassCleanup(stop)
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        pw = sync_playwright().start(); cls.addClassCleanup(pw.stop)
        cls.browser = pw.chromium.launch(); cls.addClassCleanup(cls.browser.close)

    def test_upload_source_and_mp3_download_with_theme_and_language(self):
        for mode, width, theme in [('source', 375, 'light'), ('mp3', 1280, 'dark')]:
            with self.subTest(mode=mode):
                context = self.browser.new_context(viewport={'width':width,'height':800})
                self.addCleanup(context.close)
                context.add_init_script(f"localStorage.setItem('gtd_language_v1','en');localStorage.setItem('gtd_theme_v1','{theme}')")
                page = context.new_page()
                page.route('https://**/*', lambda route: route.abort())
                errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(self.url + '/extract-audio')
                expect(page.locator('html')).to_have_attribute('data-theme', theme)
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                page.locator('#video-file').set_input_files(str(self.video))
                page.locator('.format-option').filter(has=page.locator(f'input[value="{mode}"]')).click()
                expect(page.locator(f'input[name="audio_format"][value="{mode}"]')).to_be_checked()
                page.locator('#extract-submit').click()
                expect(page.locator('.status-completed')).to_be_visible(timeout=15000)
                expect(page.locator('#upload-label')).to_contain_text('Upload complete')
                with page.expect_download() as download:
                    page.get_by_role('link', name='Download audio').click()
                downloaded = download.value
                self.assertTrue(downloaded.suggested_filename.endswith('.m4a' if mode=='source' else '.mp3'))
                self.assertGreater(Path(downloaded.path()).stat().st_size, 0)
                page.reload()
                expect(page.locator('.status-completed')).to_be_visible()
                page.locator('label[for="guide-language-toggle"]').click()
                expect(page.get_by_role('link', name='下载音频')).to_be_visible()
                self.assertEqual(errors, [])

    def test_invalid_file_fails_without_output_link(self):
        context = self.browser.new_context(); self.addCleanup(context.close)
        page = context.new_page()
        page.route('https://**/*', lambda route: route.abort())
        page.goto(self.url + '/extract-audio')
        page.locator('#video-file').set_input_files({'name':'broken.mp4','mimeType':'video/mp4','buffer':b'not a video'})
        page.locator('#extract-submit').click()
        expect(page.locator('.status-failed')).to_be_visible(timeout=15000)
        expect(page.locator('.task-actions a')).to_have_count(0)
