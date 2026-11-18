"""Exercise the desktop UI against the same invoke contract as the native host."""

from mimetypes import guess_type
import json
import os
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


UI = Path(__file__).resolve().parents[2] / "desktop" / "ui"
CSP = json.loads((UI.parent / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))["app"]["security"]["csp"]
# Keep transport boundaries observable without depending on private Rust state.
BRIDGE = r"""
(() => {
  const settings = {
    download_dir: '', default_download_dir: '/media/GTD', data_dir: '/data/GTD',
    theme: 'dark', language: 'en', cookies: {youtube: false},
  };
  let created = false;
  let extracted = false;
  let failed = false;
  window.calls = [];
  window.__TAURI__ = {app: {getVersion: async () => '9.8.7'}, core: {invoke: async (command, args) => {
    window.calls.push({command, args});
    if (command === 'renderer_ready') return null;
    if (command === 'pick_path') {
      return {folder: '/media/新的目录', video: '/Users/GTD/input 片.mp4', cookie: window.nextCookie || '/Users/GTD/cookies.txt'}[args.kind];
    }
    if (command === 'reveal_path' || command === 'open_link') return null;
    switch (args.path) {
      case '/api/desktop/settings':
        Object.assign(settings, args.body);
        return structuredClone(settings);
      case '/api/desktop/cookies':
        if (String(args.body.path).includes('broken')) {
          throw JSON.stringify({error_code: 'INVALID_COOKIES', message: '需要 Netscape 格式 / Choose a Netscape cookies file.'});
        }
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
        return {id: 'downloads', all_done: failed, tasks: [{
          id: 'task1', title: 'Sample video', url: 'https://example.test/testing', platform: 'youtube', media_type: 'video',
          status: failed ? 'cancelled' : 'running', can_cancel: !failed, can_retry: failed,
          progress: {percent_text: '36%', speed_text: '9 MiB/s', eta_text: '00:14'},
          attempts: [{number: 1, status: 'running', started_at: 1800000000, output_version: 1}],
        }]};
      case '/api/batch/extract':
        return {id: 'extract', all_done: true, tasks: [{
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

# A running batch with every task state plus an older finished batch, for queue and history views.
RICH_BRIDGE = r"""
(() => {
  const now = Math.floor(Date.now() / 1000);
  const auth = {error_code: 'AUTH_REQUIRED', message: '需要登录', suggestion: '请导入 Cookie', retryable: true};
  const live = {id: 'live', created_at: now - 600, media_type: 'video', download_dir: '/media/GTD', tasks: [
    {id: 'run', title: 'Running clip', platform: 'youtube', url: 'https://youtube.test/run', media_type: 'video', position: 1,
     status: 'running', can_cancel: true, progress: {percent_text: '42.0%', speed_text: '5.00 MB/s', eta_text: '00:20'},
     attempts: [{number: 1, status: 'running', started_at: now - 60}]},
    {id: 'wait', title: 'Waiting clip', platform: 'bilibili', url: 'https://bilibili.test/wait', media_type: 'video', position: 2,
     status: 'queued', can_cancel: true, attempts: []},
    {id: 'lock', title: 'Locked clip', platform: 'youtube', url: 'https://youtube.test/lock', media_type: 'video', position: 3,
     status: 'failed', can_retry: true, error: auth,
     attempts: [{number: 1, status: 'failed', started_at: now - 300, finished_at: now - 290, error: auth}]},
    {id: 'done', title: 'Finished clip', platform: 'youtube', url: 'https://youtube.test/done', media_type: 'video', position: 4,
     status: 'completed', can_redownload: true, result: {filepath: '/media/GTD/Finished clip.mp4', format: 'MP4', filesize: '10 MB', vcodec: '未知', fps: 30},
     attempts: [{number: 1, status: 'completed', started_at: now - 500, finished_at: now - 380}]},
  ]};
  const rate = {error_code: 'RATE_LIMITED', message: '请求过多', suggestion: '稍后重试', retryable: true};
  const old = {id: 'old', created_at: now - 86400 * 3, media_type: 'audio', audio_format: 'flac', download_dir: '/media/Music', tasks: [
    {id: 'kyoto', title: 'Kyoto walk', platform: 'youtube', url: 'https://youtube.test/kyoto', media_type: 'audio', position: 1,
     status: 'completed', can_redownload: true, result: {filepath: '/media/Music/Kyoto walk.flac', format: 'FLAC'}, attempts: []},
    {id: 'busy', title: 'Rate limited song', platform: 'youtube', url: 'https://youtube.test/busy', media_type: 'audio', position: 2,
     status: 'failed', can_retry: true, error: rate, attempts: [{number: 1, status: 'failed', started_at: now - 86400 * 3, finished_at: now - 86400 * 3 + 5}]},
  ]};
  const batches = [live, old];
  const summary = batch => {
    const count = status => batch.tasks.filter(task => status.includes(task.status)).length;
    const {tasks, ...rest} = batch;
    return {...rest, total: tasks.length, active: count(['running']), queued: count(['queued']), completed: count(['completed']),
      failed: count(['failed']), cancelled: count(['cancelled']), all_done: !count(['running', 'queued'])};
  };
  window.calls = [];
  window.__TAURI__ = {core: {invoke: async (command, args) => {
    window.calls.push({command, args});
    if (command !== 'api') return null;
    if (args.path === '/api/desktop/settings') {
      return {download_dir: '', default_download_dir: '/media/GTD', theme: 'dark', language: 'en', cookies: {youtube: true}};
    }
    if (args.path === '/api/capabilities') return {aria2c_available: false, default_download_dir: '/media/GTD'};
    if (args.path === '/api/batches') return {batches: batches.map(summary)};
    if (args.path.startsWith('/api/batch/')) {
      const batch = batches.find(item => item.id === args.path.split('/')[3]);
      return {...summary(batch), tasks: structuredClone(batch.tasks)};
    }
    if (args.path === '/api/desktop/batch-action') {
      for (const ref of args.body.tasks) {
        const task = batches.find(item => item.id === ref.batch_id).tasks.find(item => item.id === ref.task_id);
        Object.assign(task, {status: 'queued', error: null, can_retry: false, can_cancel: true});
      }
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
        self.page = self.open(BRIDGE)

    def open(self, bridge, viewport=None):
        page = self.browser.new_page(viewport=viewport or {"width": 1160, "height": 760})
        self.addCleanup(page.close)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        self.addCleanup(lambda: self.assertEqual(errors, []))
        page.route("https://gtd.test/**", self.serve_asset)
        page.add_init_script(bridge)
        page.goto("https://gtd.test")
        return page

    @staticmethod
    def serve_asset(route):
        name = urlsplit(route.request.url).path.rsplit("/", 1)[-1] or "index.html"
        asset = UI / name
        if name == ".." or not asset.is_file():
            route.fulfill(status=404)
            return
        mime = "text/javascript" if asset.suffix == ".js" else guess_type(name)[0]
        route.fulfill(body=asset.read_bytes(), content_type=mime, headers={"Content-Security-Policy": CSP})

    def call_body(self, path, page=None):
        return (page or self.page).evaluate("(path) => window.calls.findLast(call => call.args.path === path).args.body", path)

    def test_collection_submission_and_bulk_cancellation(self):
        page = self.page
        page.get_by_role("textbox", name="Links or share text").fill("https://youtube.com/playlist?list=demo")
        page.get_by_role("checkbox", name="Download subtitles").check()
        page.get_by_role("checkbox", name="Automatic captions").check()
        page.get_by_role("button", name="Preview links").click()
        dialog = page.get_by_role("dialog", name="Select collection items")
        expect(dialog.get_by_text('<img src="evil"> First item', exact=True)).to_be_visible()
        expect(dialog.get_by_role("checkbox", name="Private item")).to_be_disabled()
        expect(dialog.get_by_text("Video · Automatic captions · /media/GTD")).to_be_visible()
        dialog.get_by_role("checkbox", name="Second item").uncheck()
        dialog.get_by_role("button", name="Add 1 item to queue").click()
        expect(page.get_by_text("Sample video")).to_be_visible()
        expect(page.get_by_text("Added 1 task to the queue.")).to_be_visible()
        body = self.call_body("/api/download")
        self.assertEqual(body["selected_entry_ids"], ["one"])
        self.assertEqual(body["subtitle_options"], {"subtitles": True, "automatic": True, "danmaku": False})
        expect(page.get_by_text("9 MiB/s · 00:14 left")).to_be_visible()
        page.get_by_role("button", name=re.compile("^Sample video")).click()
        page.get_by_role("button", name="Open in browser").click()
        self.assertEqual(page.evaluate("window.calls.findLast(call => call.command === 'open_link').args"),
                         {"url": "https://example.test/testing"})
        page.get_by_role("checkbox", name="Select Sample video").check()
        page.get_by_role("button", name="Cancel selected (1)").click()
        expect(page.get_by_role("list", name="Finished").get_by_text("Cancelled", exact=True)).to_be_visible()
        self.assertEqual(self.call_body("/api/desktop/batch-action"), {
            "action": "cancel", "tasks": [{"batch_id": "downloads", "task_id": "task1"}],
        })
        page.get_by_role("button", name="History", exact=True).click()
        page.get_by_role("checkbox", name="Select Sample video").check()
        page.get_by_role("button", name="Retry selected (1)").click()
        expect(page.locator("#history-list .task-row")).to_have_attribute("data-tone", "active")
        self.assertEqual(self.call_body("/api/desktop/batch-action")["action"], "retry")

    def test_native_paths_settings_extraction_and_result_details(self):
        page = self.page
        page.get_by_role("button", name="Settings", exact=True).click()
        page.get_by_role("button", name="Choose folder").click()
        expect(page.get_by_label("Default output folder")).to_have_value("/media/新的目录")
        expect(page.get_by_text("Default folder updated.")).to_be_visible()
        self.assertEqual(self.call_body("/api/desktop/settings"), {"download_dir": "/media/新的目录"})
        expect(page.get_by_role("button", name="Use default")).to_be_visible()
        expect(page.get_by_text("Version 9.8.7")).to_be_visible()
        expect(page.get_by_text("/data/GTD", exact=True)).to_be_visible()
        page.get_by_role("button", name="Download", exact=True).click()
        expect(page.get_by_role("textbox", name="Output folder", exact=True)).to_have_value("/media/新的目录")
        page.get_by_role("button", name="Settings", exact=True).click()
        page.get_by_role("button", name="Import YouTube cookies").click()
        expect(page.get_by_role("button", name="Remove YouTube cookies")).to_be_visible()
        page.get_by_role("radio", name="Light").check(force=True)
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        page.get_by_role("radio", name="简体中文").check(force=True)
        expect(page.get_by_role("heading", name="设置", exact=True)).to_be_visible()
        page.get_by_role("radio", name="English").check(force=True)
        expect(page.get_by_role("heading", name="Settings", exact=True)).to_be_visible()
        page.get_by_role("button", name="Extract audio", exact=True).first.click()
        page.get_by_role("button", name="Choose a video").click()
        expect(page.get_by_text("input 片.mp4", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Change")).to_be_visible()
        page.get_by_role("radio", name="MP3 V0").check(force=True)
        expect(page.get_by_text("Converts the audio track to MP3 V0.", exact=False)).to_be_visible()
        page.locator("#extract-button").click()
        page.get_by_role("button", name=re.compile("^Local sample")).click()
        expect(page.get_by_text("/media/GTD/extracted.mp3", exact=True)).to_be_visible()
        page.get_by_role("button", name="Show in folder", exact=True).click()
        self.assertEqual(self.call_body("/api/desktop/extract"), {
            "path": "/Users/GTD/input 片.mp4", "audio_format": "mp3", "download_dir": "/media/新的目录",
        })
        self.assertTrue(page.evaluate("window.calls.some(call => call.command === 'reveal_path')"))
        page.get_by_role("button", name="Extract again").click()
        expect(page.get_by_text("Updated 1 task.", exact=True)).to_be_visible()
        self.assertEqual(self.call_body("/api/desktop/batch-action")["action"], "redownload")

    def test_cookie_removal_confirms_and_errors_stay_in_their_row(self):
        page = self.page
        page.get_by_role("button", name="Settings", exact=True).click()
        page.get_by_role("button", name="Import YouTube cookies").click()
        expect(page.get_by_text("YouTube cookies imported.")).to_be_visible()
        page.get_by_role("button", name="Remove YouTube cookies").click()
        self.assertEqual(self.call_body("/api/desktop/cookies")["path"], "/Users/GTD/cookies.txt")
        page.get_by_role("button", name="Confirm removing YouTube cookies").click()
        expect(page.get_by_role("button", name="Import YouTube cookies")).to_be_visible()
        self.assertEqual(self.call_body("/api/desktop/cookies"), {"platform": "youtube", "path": None})
        page.evaluate("window.nextCookie = '/Users/GTD/broken.txt'")
        page.get_by_role("button", name="Import Instagram cookies").click()
        row = page.locator('.cookie-row[data-platform="instagram"]')
        expect(row.get_by_text("This is not a valid Netscape cookies.txt file.")).to_be_visible()
        expect(page.locator("#settings-notice")).to_be_hidden()

    def test_queue_groups_by_state_and_links_errors_to_fixes(self):
        page = self.open(RICH_BRIDGE)
        page.get_by_role("button", name="Queue", exact=True).click()
        expect(page.locator("#queue-list .task-title")).to_have_text(["Running clip", "Waiting clip", "Locked clip", "Finished clip"])
        expect(page.locator("#queue-list .group-label")).to_have_text(["In progress", "Queued", "Needs attention", "Finished"])
        expect(page.get_by_role("button", name="Failed 1")).to_be_visible()
        page.locator("#queue-list .task-main").first.focus()
        page.keyboard.press("ArrowDown")
        expect(page.locator("#queue-list .task-main").nth(1)).to_be_focused()
        page.get_by_role("button", name=re.compile("^Finished clip")).click()
        expect(page.get_by_text("Unknown", exact=True)).to_be_visible()
        expect(page.get_by_text("30 fps", exact=True)).to_be_visible()
        page.get_by_role("button", name=re.compile("^Locked clip")).click()
        expect(page.get_by_text("AUTH_REQUIRED", exact=True)).to_be_visible()
        page.get_by_role("button", name="Update YouTube cookies").click()
        expect(page.get_by_role("heading", name="Settings", exact=True)).to_be_visible()
        expect(page.locator('.cookie-row[data-platform="youtube"] button').first).to_be_focused()
        page.get_by_role("button", name="Queue", exact=True).click()
        page.get_by_role("button", name="Clear finished").click()
        expect(page.get_by_text("Cleared 1 finished task.")).to_be_visible()
        expect(page.locator("#queue-list .task-title")).to_have_text(["Running clip", "Waiting clip", "Locked clip"])

    def test_history_lists_batches_searches_titles_and_retries_failures(self):
        page = self.open(RICH_BRIDGE)
        page.get_by_role("button", name="History", exact=True).click()
        expect(page.locator(".batch-name")).to_have_text(["Running clip and 3 more", "Kyoto walk and 1 more"])
        page.get_by_role("searchbox", name="Search history").fill("rate limited")
        expect(page.locator(".batch-name")).to_have_text(["Kyoto walk and 1 more"])
        page.locator(".batch-item").first.click()
        expect(page.get_by_role("heading", name="Kyoto walk and 1 more")).to_be_visible()
        expect(page.get_by_text("Audio · Source FLAC")).to_be_visible()
        page.get_by_role("button", name="Retry failed (1)").click()
        self.assertEqual(self.call_body("/api/desktop/batch-action", page), {
            "action": "retry", "tasks": [{"batch_id": "old", "task_id": "busy"}],
        })
        expect(page.get_by_text("Updated 1 task.")).to_be_visible()
        page.get_by_role("searchbox", name="Search history").fill("nothing like this")
        expect(page.get_by_text("No batches match “nothing like this”.")).to_be_visible()

    def test_collection_caps_selection_supports_ranges_and_filter_escape(self):
        page = self.open(BRIDGE.replace("""return {preview_id: 'preview', requires_selection: true, entries: [""", """return {preview_id: 'preview', requires_selection: true, truncated: true, entries: [
          ...Array.from({length: 120}, (_, index) => ({id: `e${index + 1}`, title: `Track ${index + 1}`, platform: 'youtube', position: index + 1, selectable: index !== 4})),"""))
        page.get_by_role("textbox", name="Links or share text").fill("https://youtube.com/playlist?list=long")
        page.get_by_role("button", name="Preview links").click()
        dialog = page.get_by_role("dialog", name="Select collection items")
        search = dialog.get_by_role("searchbox", name="Filter by title")
        expect(search).to_be_focused()
        search.press("Escape")
        expect(dialog).to_be_hidden()
        expect(page.get_by_role("textbox", name="Links or share text")).to_be_focused()
        page.get_by_role("button", name="Preview links").click()
        expect(dialog.get_by_text("YouTube + Bilibili · 123 items · 2 unavailable")).to_be_visible()
        expect(dialog.get_by_text("The preview reached the 1,000-item display limit.")).to_be_visible()
        expect(dialog.get_by_role("button", name="Add 100 items to queue")).to_be_enabled()
        select_all = dialog.get_by_role("checkbox", name="Select first 100")
        select_all.uncheck()
        expect(dialog.get_by_role("button", name="Add to queue")).to_be_disabled()
        dialog.get_by_role("checkbox", name="Track 3", exact=True).check()
        dialog.get_by_role("checkbox", name="Track 8", exact=True).click(modifiers=["Shift"])
        expect(dialog.get_by_role("button", name="Add 5 items to queue")).to_be_visible()
        search.fill("Track 11")
        expect(dialog.locator(".collection-entry")).to_have_count(11)
        search.press("Escape")
        expect(search).to_have_value("")
        expect(dialog).to_be_visible()
        dialog.get_by_role("button", name="Add 5 items to queue").click()
        self.assertEqual(self.call_body("/api/download", page)["selected_entry_ids"], ["e3", "e4", "e6", "e7", "e8"])

    def test_unavailable_service_offers_reconnect(self):
        page = self.open("""
          window.allowConnect = false;
          window.__TAURI__ = {core: {invoke: async (command, args) => {
            if (!window.allowConnect) throw 'Could not reach GTD: connection refused';
            if (command !== 'api') return null;
            if (args.path === '/api/desktop/settings') return {download_dir: '', default_download_dir: '/media/GTD', theme: 'dark', language: 'en', cookies: {}};
            if (args.path === '/api/capabilities') return {aria2c_available: false};
            if (args.path === '/api/batches') return {batches: []};
            throw new Error(args.path);
          }}};
        """)
        banner = page.get_by_role("alert")
        expect(banner.get_by_text("GTD can't reach its download service")).to_be_visible()
        expect(page.get_by_text("Available once the service is running")).to_be_visible()
        expect(page.get_by_role("button", name="Preview links")).to_be_disabled()
        page.evaluate("window.allowConnect = true")
        banner.get_by_role("button", name="Reconnect").click()
        expect(banner).to_be_hidden()
        expect(page.get_by_text("Service ready")).to_be_visible()

    def test_compact_window_does_not_overflow(self):
        for width, height in ((680, 550), (610, 520)):
            self.page.set_viewport_size({"width": width, "height": height})
            for name in ("Download", "Queue", "History", "Extract audio", "Settings"):
                self.page.get_by_role("button", name=name, exact=True).first.click()
                self.assertEqual(self.page.evaluate("document.documentElement.scrollWidth"), width, name)
        self.page.get_by_role("button", name="Download", exact=True).click()
        expect(self.page.get_by_role("button", name="Preview links")).to_be_enabled()
        self.assertTrue(self.page.evaluate("window.calls.some(call => call.command === 'renderer_ready')"))


if __name__ == "__main__":
    unittest.main()
