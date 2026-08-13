import unittest
from pathlib import Path
from html.parser import HTMLParser

import app as web_app


class _VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


class _StructureNode:
    def __init__(self, tag, attrs, parent=None):
        self.tag = tag
        self.attrs = dict(attrs)
        self.parent = parent
        self.children = []

    @property
    def classes(self):
        return set(self.attrs.get("class", "").split())


class _StructureParser(HTMLParser):
    VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self):
        super().__init__()
        self.nodes = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        parent = self.stack[-1] if self.stack else None
        node = _StructureNode(tag, attrs, parent)
        self.nodes.append(node)
        if parent:
            parent.children.append(node)
        if tag not in self.VOID_ELEMENTS:
            self.stack.append(node)

    def handle_endtag(self, tag):
        while self.stack:
            node = self.stack.pop()
            if node.tag == tag:
                return


def _parse_structure(html):
    parser = _StructureParser()
    parser.feed(html)
    return parser


class KozekiLmuEasterEggTests(unittest.TestCase):
    def setUp(self):
        self.client = web_app.app.test_client()

    def test_task_mascot_links_to_hidden_route_accessibly(self):
        response = self.client.get("/")
        html = "\n".join(
            (
                response.get_data(as_text=True),
                Path("static/css/index.css").read_text(encoding="utf-8"),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('class="icon" href="/kozekilmu"', html)
        self.assertIn('aria-label="打开隐藏的 LMU 富士 GT3 冠军页面"', html)
        self.assertIn('.empty-state .icon:focus-visible', html)

    def test_hidden_route_renders_title_video_and_return_link(self):
        response = self.client.get("/kozekilmu")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "<title>你怎么知道我在2026年7月12号的 LMU 富士赛道 GT3 铜赛拿了冠军 😋</title>",
            html,
        )
        parser = _VisibleTextParser()
        parser.feed(html)
        visible_text = "".join(parser.parts)
        self.assertIn(
            "你怎么知道我在2026年7月12号的 LMU 富士赛道 GT3 铜赛拿了冠军 😋",
            visible_text,
        )
        self.assertIn('href="https://b23.tv/F3xhGEK"', html)
        self.assertIn('target="_blank" rel="noopener noreferrer"', html)
        self.assertIn("模拟赛车萌新拿下 LMU 第一胜", html)
        self.assertIn('href="/#task-card"', html)

    def test_all_supplied_images_are_project_local_and_rendered(self):
        html = self.client.get("/kozekilmu").get_data(as_text=True)
        expected_assets = {
            "lmu-first-win.png": (1448, 1086),
            "race-summary.png": (2304, 1215),
            "classification.png": (2239, 1233),
            "career-stats.png": (897, 415),
            "fuji-result.png": (747, 422),
            "achievements.png": (533, 226),
        }

        for filename, dimensions in expected_assets.items():
            path = Path("static/kozekilmu") / filename
            self.assertTrue(path.is_file(), filename)
            self.assertIn(f"/static/kozekilmu/{filename}", html)
            self.assertIn(f'width="{dimensions[0]}" height="{dimensions[1]}"', html)

    def test_easter_egg_keeps_main_theme_and_responsive_layout(self):
        html = self.client.get("/kozekilmu").get_data(as_text=True)

        self.assertIn("--background: #0f172a", html)
        self.assertIn("--accent: #00a19b", html)
        self.assertIn("Designed by Mark Yang", html)
        self.assertIn('font-family: "Cormorant Garamond"', html)
        self.assertIn("@media (max-width: 820px)", html)
        self.assertIn("@media (max-width: 560px)", html)
        self.assertIn("prefers-reduced-motion", html)
        self.assertIn('class="hero-date">2026年7月12号</span>', html)
        self.assertIn("font-variant-numeric: tabular-nums lining-nums", html)
        self.assertIn("column-gap: clamp(24px, 2vw, 32px)", html)
        self.assertIn("row-gap: clamp(28px, 2.4vw, 38px)", html)
        self.assertIn("column-gap: 20px; row-gap: 20px", html)

    def test_hidden_page_motion_structure_is_bounded_and_ordered(self):
        html = self.client.get("/kozekilmu").get_data(as_text=True)
        structure = _parse_structure(html)

        self.assertIn('href="/static/css/motion.css"', html)
        self.assertIn('<script defer src="/static/js/motion.js"></script>', html)
        surfaces = [node for node in structure.nodes if "data-motion-surface" in node.attrs]
        video_surfaces = [node for node in surfaces if node.tag == "a" and "video-card" in node.classes]
        shot_surfaces = [node for node in surfaces if node.tag == "figure" and "shot" in node.classes]
        self.assertEqual(len(surfaces), 6)
        self.assertEqual(len(video_surfaces), 1)
        self.assertEqual(len(shot_surfaces), 5)

        assets = [
            Path(node.attrs["src"]).name
            for node in structure.nodes
            if node.tag == "img" and "/static/kozekilmu/" in node.attrs.get("src", "")
        ]
        self.assertEqual(
            assets,
            [
                "lmu-first-win.png",
                "race-summary.png",
                "fuji-result.png",
                "classification.png",
                "career-stats.png",
                "achievements.png",
            ],
        )

        parallax = [node for node in structure.nodes if "data-motion-parallax" in node.attrs]
        self.assertEqual(
            [(node.attrs.get("class"), node.attrs["data-motion-parallax"]) for node in parallax],
            [
                ("hero-stamp", "0.55"),
                ("video-media", "0.45"),
                ("shot-media", "0.40"),
                ("shot-media", "0.46"),
                ("shot-media", "0.52"),
                ("shot-media", "0.44"),
                ("shot-media", "0.48"),
            ],
        )

        for token in ("requestAnimationFrame", "new IntersectionObserver", "pointermove", "pointerenter"):
            self.assertNotIn(token, html)

    def test_media_surfaces_have_noninteractive_sheen_below_controls(self):
        html = self.client.get("/kozekilmu").get_data(as_text=True)
        structure = _parse_structure(html)
        motion_css = Path("static/css/motion.css").read_text(encoding="utf-8")

        surfaces = [node for node in structure.nodes if "data-motion-surface" in node.attrs]
        for surface in surfaces:
            sheens = [child for child in surface.children if "data-motion-sheen" in child.attrs]
            self.assertEqual(len(sheens), 1)
            self.assertEqual(sheens[0].attrs.get("aria-hidden"), "true")
            self.assertEqual(sheens[0].tag, "span")

        self.assertRegex(motion_css, r"\[data-motion-sheen\]\s*\{[^}]*pointer-events:\s*none")
        self.assertRegex(motion_css, r"\[data-motion-sheen\]\s*\{[^}]*z-index:\s*1")
        self.assertNotIn("[data-motion-surface]::before", motion_css)
        self.assertNotIn("[data-motion-surface]::after", motion_css)
        self.assertRegex(html, r"\.video-overlay\s*\{[^}]*z-index:\s*3")
        self.assertRegex(html, r"\.shot-caption\s*\{[^}]*z-index:\s*2")

    def test_media_parallax_has_overscan_and_preserves_access(self):
        html = self.client.get("/kozekilmu").get_data(as_text=True)
        structure = _parse_structure(html)

        self.assertRegex(html, r"\.video-media,\s*\.shot-media\s*\{[^}]*inset:\s*-14px")
        lazy_images = [node for node in structure.nodes if node.tag == "img" and node.attrs.get("loading") == "lazy"]
        self.assertEqual(len(lazy_images), 5)
        self.assertEqual(len([node for node in structure.nodes if node.tag == "figcaption" and "shot-caption" in node.classes]), 5)
        play = [node for node in structure.nodes if "video-play" in node.classes]
        self.assertEqual(len(play), 1)

        video = next(node for node in structure.nodes if node.tag == "a" and "video-card" in node.classes)
        self.assertEqual(video.attrs.get("href"), "https://b23.tv/F3xhGEK")
        self.assertEqual(video.attrs.get("target"), "_blank")
        self.assertEqual(video.attrs.get("rel"), "noopener noreferrer")
        self.assertIn("@media (max-width: 820px)", html)
        self.assertIn("@media (max-width: 560px)", html)
        reduced_block = html.split("@media (prefers-reduced-motion: reduce)", 1)[1].split("}", 2)[0]
        for selector in ("video-card", "video-media", "video-play", "shot-media"):
            self.assertNotIn(selector, reduced_block)


if __name__ == "__main__":
    unittest.main()
