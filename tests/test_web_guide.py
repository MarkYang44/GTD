import unittest
import subprocess
from pathlib import Path

import app as web_app
from guide_renderer import render_markdown


class WebGuideTests(unittest.TestCase):
    def setUp(self):
        self.client = web_app.app.test_client()

    def test_main_page_links_to_web_guide(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('class="topbar-link" href="/guide"', html)
        self.assertIn("使用说明", html)

    def test_guide_renders_curated_markdown_with_matching_theme(self):
        response = self.client.get("/guide")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("网页使用说明", html)
        self.assertIn("Read. Inspect. Execute.", html)
        self.assertIn("Designed by Mark Yang", html)
        self.assertIn("<title>使用说明 - GTD</title>", html)
        self.assertIn('aria-label="GTD — Generalized Transmedia Downloader"', html)
        self.assertIn('class="topbar-link" href="/"', html)
        self.assertIn('class="guide-markdown"', html)
        self.assertIn('class="guide-toc-list"', html)
        self.assertIn("Rendered from docs/WEB_GUIDE.md", html)
        self.assertIn("--background: #0f172a", html)
        self.assertIn("--accent: #00a19b", html)
        self.assertIn('font-family: "Cormorant Garamond"', html)
        self.assertIn("white-space: nowrap", html)
        self.assertIn("@media (max-width: 1180px)", html)

    def test_guide_loads_shared_motion_assets_and_declares_reading_safe_motion(self):
        html = self.client.get("/guide").get_data(as_text=True)

        self.assertIn('href="/static/css/motion.css"', html)
        self.assertIn('<script defer src="/static/js/motion.js"></script>', html)
        self.assertIn('class="guide-heading" data-motion-group="guide-hero"', html)
        self.assertIn('class="guide-document"', html)
        self.assertIn("data-motion-surface", html)
        self.assertIn("motion:scroll-frame", html)
        self.assertIn("window.MotionSystem?.refresh", html)
        self.assertNotIn("const pointerLight", html)
        self.assertNotIn("requestAnimationFrame(updateScrollState)", html)
        self.assertRegex(
            html,
            r'class="guide-document"(?![^>]*data-motion-reveal)[^>]*data-motion-surface',
        )
        self.assertIn('heading.setAttribute("data-motion-reveal", "")', html)

    def test_guide_initializer_builds_one_toc_and_refreshes_dynamic_headings(self):
        script = r'''
const assert = require("assert");
const fs = require("fs");
const template = fs.readFileSync("templates/guide.html", "utf8");
const match = template.match(/<script>\s*([\s\S]*?)<\/script>/);
assert(match, "guide inline initializer is missing");

class ClassList {
  constructor() { this.values = new Set(); }
  toggle(name, force) { if (force) this.values.add(name); else this.values.delete(name); }
  contains(name) { return this.values.has(name); }
}
class Element {
  constructor({ id = "", textContent = "", top = 200 } = {}) {
    this.id = id;
    this.textContent = textContent;
    this.top = top;
    this.attributes = {};
    this.children = [];
    this.classList = new ClassList();
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name]; }
  set href(value) { this._href = value; this.hash = value.startsWith("#") ? value : ""; }
  get href() { return this._href; }
  appendChild(child) { this.children.push(child); return child; }
  querySelectorAll(selector) {
    if (selector !== "a") return [];
    return this.children.flatMap((item) => item.children.filter((child) => child.tagName === "a"));
  }
  getBoundingClientRect() { return { top: this.top }; }
}

const headings = [
  new Element({ id: "first", textContent: "First", top: 80 }),
  new Element({ id: "second", textContent: "Second", top: 180 }),
];
const tocList = new Element();
const markdown = new Element();
markdown.querySelectorAll = (selector) => selector === "h2" ? headings : [];
const listeners = new Map();
const document = {
  readyState: "loading",
  getElementById(id) { return id === "guide-toc-list" ? tocList : id === "guide-markdown" ? markdown : null; },
  createElement(tagName) { const element = new Element(); element.tagName = tagName; return element; },
  addEventListener(type, listener, options = {}) { (listeners.get(type) || listeners.set(type, []).get(type)).push({ listener, once: options.once }); },
  dispatchEvent(event) {
    const registered = [...(listeners.get(event.type) || [])];
    for (const entry of registered) {
      entry.listener(event);
      if (entry.once) listeners.set(event.type, (listeners.get(event.type) || []).filter((item) => item !== entry));
    }
  },
};
const refreshCalls = [];
global.document = document;
global.window = { MotionSystem: { refresh(root) { refreshCalls.push(root); } } };
global.requestAnimationFrame = () => { throw new Error("guide must not schedule its own frame"); };
new Function(match[1])();

assert.strictEqual((listeners.get("DOMContentLoaded") || []).length, 1);
document.dispatchEvent({ type: "DOMContentLoaded" });
assert.strictEqual(tocList.children.length, 2);
assert.strictEqual((listeners.get("motion:scroll-frame") || []).length, 1);
assert.deepStrictEqual(headings.map((heading) => heading.getAttribute("data-motion-reveal")), ["", ""]);
assert.deepStrictEqual(headings.map((heading) => heading.getAttribute("data-motion-group")), ["guide-sections", "guide-sections"]);
assert.deepStrictEqual(headings.map((heading) => heading.getAttribute("data-motion-order")), ["0", "1"]);
assert.deepStrictEqual(refreshCalls, [markdown]);
let links = tocList.querySelectorAll("a");
assert(links[0].classList.contains("is-current"));
assert(!links[1].classList.contains("is-current"));

headings[0].top = 150;
headings[1].top = 90;
document.dispatchEvent({ type: "motion:scroll-frame" });
links = tocList.querySelectorAll("a");
assert(!links[0].classList.contains("is-current"));
assert(links[1].classList.contains("is-current"));

document.dispatchEvent({ type: "DOMContentLoaded" });
assert.strictEqual(tocList.children.length, 2);
assert.strictEqual((listeners.get("motion:scroll-frame") || []).length, 1);
assert.deepStrictEqual(refreshCalls, [markdown]);
'''
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_web_guide_excludes_cli_only_instructions(self):
        source = Path("docs/WEB_GUIDE.md").read_text(encoding="utf-8")

        self.assertIn("GTD — Generalized Transmedia Downloader", source)
        self.assertNotIn("python main.py", source)
        self.assertNotIn("python app.py", source)
        self.assertNotIn("--audio", source)
        self.assertNotIn("退出状态", source)
        self.assertNotIn("命令行参数", source)
        self.assertIn("下载操作流程", source)
        self.assertIn("下载位置与历史记录", source)

    def test_markdown_renderer_escapes_html_and_blocks_unsafe_links(self):
        rendered = str(
            render_markdown(
                "# 标题\n\n<script>alert(1)</script>\n\n"
                "[危险](javascript:alert(1)) [安全](https://example.com)"
            )
        )

        self.assertIn("&lt;script&gt;", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn('href="javascript:', rendered)
        self.assertIn('href="https://example.com"', rendered)
        self.assertIn('rel="noopener noreferrer"', rendered)

    def test_markdown_renderer_supports_tables_lists_and_code(self):
        rendered = str(
            render_markdown(
                "## 格式\n\n- 视频\n- 音频\n\n"
                "| 类型 | 输出 |\n|---|---|\n| 视频 | MP4 |\n\n`downloads/`"
            )
        )

        self.assertIn('<h2 id="格式">格式</h2>', rendered)
        self.assertIn("<ul>", rendered)
        self.assertIn("<table>", rendered)
        self.assertIn("<code>downloads/</code>", rendered)


if __name__ == "__main__":
    unittest.main()
