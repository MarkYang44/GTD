import unittest
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

    def test_web_guide_excludes_cli_only_instructions(self):
        source = Path("docs/WEB_GUIDE.md").read_text(encoding="utf-8")

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
