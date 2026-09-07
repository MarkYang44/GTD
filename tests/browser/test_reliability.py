"""Real Chromium regression checks with local assets and mocked media APIs.

Run separately: python -m unittest discover -s tests/browser -p 'test_*.py'
"""
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server, WSGIRequestHandler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
BATCH_ID = 'a' * 32


class QuietHandler(WSGIRequestHandler):
    def log_request(self, *args, **kwargs):
        pass


class BrowserReliabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        previous = os.environ.get('GTD_HISTORY_PATH')
        os.environ['GTD_HISTORY_PATH'] = str(Path(cls.temp.name) / 'tasks.sqlite3')
        try:
            import app
        finally:
            if previous is None:
                os.environ.pop('GTD_HISTORY_PATH', None)
            else:
                os.environ['GTD_HISTORY_PATH'] = previous
        cls.addClassCleanup(app.task_manager.shutdown)
        cls.server = make_server('127.0.0.1', 0, app.app, request_handler=QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        def stop_server():
            cls.server.shutdown()
            cls.thread.join(5)
            cls.server.server_close()
        cls.addClassCleanup(stop_server)
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        cls.browser = cls.playwright.chromium.launch()
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 1280, 'height': 800})
        self.addCleanup(self.context.close)
        self.context.add_init_script("localStorage.setItem('gtd_language_v1','en')")
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.posts = []
        self.batch_status = 200
        self.batch = dict(id=BATCH_ID, created_at=1700000000, media_type='video',
                          total=1, completed=1, failed=0, cancelled=0, all_done=True,
                          tasks=[dict(id='task1', url='https://youtu.be/example', status='completed',
                                      result={'title': 'Saved movie'}, can_redownload=True)])
        self.context.route('**/api/**', self.route_api)
        # Keep browser tests independent of external font/image services.
        self.context.route('https://**/*', lambda route: route.abort())

    def route_api(self, route):
        request = route.request
        path = urlparse(request.url).path
        if request.method == 'POST':
            self.posts.append(path)
        if path == '/api/capabilities':
            route.fulfill(json={'aria2c_available': False, 'folder_picker_available': False})
        elif path == '/api/batches':
            route.fulfill(json={'batches': [{k: v for k, v in self.batch.items() if k != 'tasks'}]})
        elif path == '/api/batch/' + BATCH_ID:
            route.fulfill(status=self.batch_status, json=self.batch if self.batch_status == 200 else {})
        elif path == '/api/preview':
            route.fulfill(json=dict(preview_id='preview', title='下载预览（2 项）', title_is_generated=True,
                                    requires_selection=True, entries=[
                                        dict(id='one', title='第 1 项', title_is_generated=True, position=1, selectable=True),
                                        dict(id='two', title='中文原始标题', title_is_generated=False, position=2, selectable=True)]))
        elif path == '/api/download':
            route.fulfill(json={'batch_id': BATCH_ID, 'task_count': 1, 'download_dir': 'downloads'})
        else:
            route.fulfill(status=404, json={})

    def tearDown(self):
        self.assertEqual(self.errors, [], 'browser JavaScript errors')

    def test_generated_preview_language_and_selection_survive_switch(self):
        self.page.goto(self.url)
        self.page.locator('#videoUrls').fill('https://youtu.be/example')
        self.page.locator('#videoDownloadButton').click()
        expect(self.page.locator('#collectionPreviewTitle')).to_have_text('Download preview (2 items) · Select items')
        titles = self.page.locator('.collection-entry-title')
        expect(titles).to_have_text(['Item 1', '中文原始标题'])
        first = self.page.locator('.collection-entry-checkbox').first
        first.uncheck()
        self.page.locator('label[for="guide-language-toggle"]').click()
        expect(titles).to_have_text(['第 1 项', '中文原始标题'])
        expect(first).not_to_be_checked()
        self.page.locator('label[for="guide-language-toggle"]').click()
        expect(titles).to_have_text(['Item 1', '中文原始标题'])
        expect(first).not_to_be_checked()
        self.page.locator('#collectionSubmitButton').click()
        expect(self.page.locator('#task-container')).to_contain_text('Saved movie')
        self.assertEqual(self.page.evaluate("localStorage.getItem('gtd_current_batch_v1')"), BATCH_ID)
        self.page.reload()
        expect(self.page.locator('#task-container')).to_contain_text('Saved movie')
        self.assertEqual(self.posts.count('/api/download'), 1, 'reload must not submit downloads')

    def test_history_selection_and_mobile_layout(self):
        self.page.set_viewport_size({'width': 375, 'height': 667})
        self.page.goto(self.url)
        expect(self.page.locator('#batchHistory option')).to_have_count(2)
        self.page.locator('#batchHistory').select_option(BATCH_ID)
        expect(self.page.locator('#task-container')).to_contain_text('Saved movie')
        expect(self.page.locator('#videoDownloadButton')).to_be_enabled()
        self.assertEqual(self.posts, [], 'viewing history must not submit downloads')
        box = self.page.locator('#batchHistory').bounding_box()
        self.assertGreaterEqual(box['x'], 0)
        self.assertLessEqual(box['x'] + box['width'], 375)

    def test_missing_saved_batch_releases_controls_and_clears_reference(self):
        self.batch_status = 404
        self.context.add_init_script(f"localStorage.setItem('gtd_current_batch_v1','{BATCH_ID}')")
        self.page.goto(self.url)
        expect(self.page.locator('#task-summary')).to_contain_text('missing or expired')
        expect(self.page.locator('#videoDownloadButton')).to_be_enabled()
        self.assertIsNone(self.page.evaluate("localStorage.getItem('gtd_current_batch_v1')"))
        self.assertEqual(self.posts, [])
