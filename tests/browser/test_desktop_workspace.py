"""Exercise the desktop UI against the same invoke contract as the native host."""

from mimetypes import guess_type
import json
import os
from pathlib import Path
import unittest
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


UI = Path(__file__).resolve().parents[2] / "desktop" / "ui"
CSP = json.loads((UI.parent / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))["app"]["security"]["csp"]
# Keep transport boundaries observable without depending on private Rust state.
BRIDGE = r"""
(() => {
  const settings = {
    download_dir: '', default_download_dir: '/media/GTD',
    theme: 'dark', language: 'en', cookies: {youtube: false},
  };
  let created = false;
  let extracted = false;
  let failed = false;
  window.calls = [];
  window.__TAURI__ = {core: {invoke: async (command, args) => {
    window.calls.push({command, args});
    if (command === 'renderer_ready') return null;
    if (command === 'pick_path') {
      return {folder: '/media/新的目录', video: '/Users/GTD/input 片.mp4', cookie: '/Users/GTD/cookies.txt'}[args.kind];
    }
    if (command === 'reveal_path') return null;
    switch (args.path) {
      case '/api/desktop/settings':
        Object.assign(settings, args.body);
        return structuredClone(settings);
      case '/api/desktop/cookies':
        settings.cookies[args.body.platform] = !!args.body.path;
        return structuredClone(settings);
      case '/api/capabilities':
        return {aria2c_available: true, default_download_dir: '/media/GTD'};
      case '/api/preview':
        return {preview_id: 'preview', requires_selection: true, entries: [
          {id: 'one', title: '<img src="evil"> First item', platform: 'youtube', position: 1, selectable: true},
          {id: 'two', title: 'Second item', platform: 'bilibili', position: 2, selectable: true},
          {id: 'bad', title: 'Private item', platform: 'youtube', position: 3, selectable: false},
        ]};
      case '/api/download':
        created = true;
        return {batch_id: 'downloads', task_count: 1};
      case '/api/desktop/extract':
        extracted = true;
        return {batch_id: 'extract', task_count: 1};
      case '/api/batches':
        return {batches: [
          ...(extracted ? [{id: 'extract', created_at: 1840000000, total: 1, completed: 1, all_done: true, media_type: 'audio', audio_format: 'mp3'}] : []),
          ...(created ? [{id: 'downloads', created_at: 1800000000, total: 1, active: failed ? 0 : 1, cancelled: failed ? 1 : 0, all_done: failed, media_type: 'video'}] : []),
        ]};
      case '/api/batch/downloads':
        return {id: 'downloads', tasks: [{
          id: 'task1', title: 'Sample video', url: 'https://example.test/testing', platform: 'youtube', media_type: 'video',
          status: failed ? 'cancelled' : 'running', can_cancel: !failed, can_retry: failed,
          progress: {percent_text: '36%', speed_text: '9 MiB/s', eta_text: '00:14'},
          attempts: [{number: 1, status: 'running', started_at: 1800000000, output_version: 1}],
        }]};
      case '/api/batch/extract':
        return {id: 'extract', tasks: [{
          id: 'local1', title: 'Local sample', platform: 'local', media_type: 'audio', status: 'completed',
          result: {filepath: '/media/GTD/extracted.mp3', format: 'MP3', local_extraction: true},
          can_redownload: true,
        }]};
      case '/api/desktop/batch-action':
        failed = args.body.action === 'cancel';
        return {succeeded: args.body.tasks.length, errors: []};
    }
    throw new Error(args.path);
  }}};
})();
"""


class DesktopWorkspaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        playwright = sync_playwright().start()
        cls.addClassCleanup(playwright.stop)
        cls.browser = playwright.chromium.launch(executable_path=os.environ.get("GTD_TEST_CHROMIUM"))
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1160, "height": 760})
        self.addCleanup(self.page.close)
        self.page.route("https://gtd.test/**", self.serve_asset)
        self.page.add_init_script(BRIDGE)
        self.page.goto("https://gtd.test")

    @staticmethod
    def serve_asset(route):
        name = urlsplit(route.request.url).path.rsplit("/", 1)[-1] or "index.html"
        asset = UI / name
        if name == ".." or not asset.is_file():
            route.fulfill(status=404)
            return
        mime = "text/javascript" if asset.suffix == ".js" else guess_type(name)[0]
        route.fulfill(body=asset.read_bytes(), content_type=mime, headers={"Content-Security-Policy": CSP})

    def call_body(self, path):
        return self.page.evaluate("(path) => window.calls.findLast(call => call.args.path === path).args.body", path)

    def test_collection_submission_and_bulk_cancellation(self):
        page = self.page
        page.get_by_role("textbox", name="Links or share text").fill("https://youtube.com/playlist?list=demo")
        page.get_by_role("checkbox", name="Download subtitles").check()
        page.get_by_role("checkbox", name="Automatic captions").check()
        page.get_by_role("button", name="Preview links").click()
        dialog = page.get_by_role("dialog", name="Select collection items")
        expect(dialog.get_by_text('<img src="evil"> First item', exact=True)).to_be_visible()
        expect(dialog.get_by_role("checkbox", name="Private item")).to_be_disabled()
        dialog.get_by_role("checkbox", name="Second item").uncheck()
        dialog.get_by_role("button", name="Add selected to queue").click()
        expect(page.get_by_text("Sample video")).to_be_visible()
        body = self.call_body("/api/download")
        self.assertEqual(body["selected_entry_ids"], ["one"])
        self.assertEqual(body["subtitle_options"], {"subtitles": True, "automatic": True, "danmaku": False})
        expect(page.get_by_text("9 MiB/s")).to_be_visible()
        page.get_by_role("checkbox", name="Select Sample video").check()
        page.get_by_role("button", name="Cancel selected").click()
        expect(page.get_by_role("table").get_by_text("Cancelled", exact=True)).to_be_visible()
        self.assertEqual(self.call_body("/api/desktop/batch-action"), {
            "action": "cancel", "tasks": [{"batch_id": "downloads", "task_id": "task1"}],
        })
        page.get_by_role("button", name="History", exact=True).click()
        page.get_by_role("checkbox", name="Select Sample video").check()
        page.get_by_role("button", name="Retry selected").click()
        expect(page.get_by_role("table").get_by_text("Downloading", exact=True)).to_be_visible()
        self.assertEqual(self.call_body("/api/desktop/batch-action")["action"], "retry")

    def test_native_paths_settings_extraction_and_result_inspector(self):
        page = self.page
        page.get_by_role("button", name="Settings", exact=True).click()
        page.get_by_role("button", name="Choose folder").click()
        expect(page.get_by_label("Default output folder")).to_have_value("/media/新的目录")
        page.get_by_role("textbox", name="Default output folder").press("Enter")
        page.get_by_role("button", name="Download", exact=True).click()
        expect(page.get_by_role("textbox", name="Output folder", exact=True)).to_have_value("/media/新的目录")
        page.get_by_role("button", name="Settings", exact=True).click()
        page.get_by_role("button", name="Import YouTube cookies").click()
        expect(page.get_by_role("button", name="Remove YouTube cookies")).to_be_visible()
        page.get_by_label("Theme").select_option("light")
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        page.get_by_label("Language").select_option("zh")
        expect(page.get_by_role("heading", name="设置", exact=True)).to_be_visible()
        page.get_by_label("语言").select_option("en")
        page.get_by_role("button", name="Extract audio", exact=True).click()
        page.get_by_role("button", name="Choose a video").click()
        expect(page.get_by_text("input 片.mp4", exact=True)).to_be_visible()
        page.get_by_role("combobox", name="Audio format").select_option("mp3")
        page.get_by_role("button", name="Start extraction").click()
        page.get_by_role("button", name="Local sample", exact=True).click()
        expect(page.get_by_text("/media/GTD/extracted.mp3", exact=True)).to_be_visible()
        page.get_by_role("button", name="Show output in folder").click()
        self.assertEqual(self.call_body("/api/desktop/extract"), {
            "path": "/Users/GTD/input 片.mp4", "audio_format": "mp3", "download_dir": "/media/新的目录",
        })
        self.assertTrue(page.evaluate("window.calls.some(call => call.command === 'reveal_path')"))
        page.get_by_role("button", name="Extract again").click()
        expect(page.get_by_text("Updated 1 tasks.", exact=True)).to_be_visible()
        self.assertEqual(self.call_body("/api/desktop/batch-action")["action"], "redownload")

    def test_compact_window_does_not_overflow(self):
        self.page.set_viewport_size({"width": 610, "height": 520})
        self.assertEqual(self.page.evaluate("document.documentElement.scrollWidth"), 610)
        expect(self.page.get_by_role("button", name="Preview links")).to_be_enabled()
        self.assertTrue(self.page.evaluate("window.calls.some(call => call.command === 'renderer_ready')"))


if __name__ == "__main__":
    unittest.main()
