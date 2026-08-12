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


if __name__ == "__main__":
    unittest.main()
