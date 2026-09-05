import re
import subprocess
import unittest

import app as web_app


class SecondaryPageLanguageTests(unittest.TestCase):
    def setUp(self):
        self.client = web_app.app.test_client()

    def test_guide_renders_complete_english_article_and_unique_anchors(self):
        html = self.client.get('/guide').get_data(as_text=True)
        self.assertIn('id="guide-markdown-en"', html)
        self.assertIn('Download locations and history', html)
        self.assertIn('Login-protected content and cookies', html)
        self.assertIn('gtd:languagechange', html)
        ids = re.findall(r'<h[1-4] id="([^"]+)"', html)
        self.assertEqual(len(ids), len(set(ids)))

    def test_secondary_pages_share_language_control_and_accessible_translations(self):
        for route in ('/guide', '/kozekilmu'):
            with self.subTest(route=route):
                html = self.client.get(route).get_data(as_text=True)
                self.assertIn('/static/js/lmu_guide_language.js', html)
                self.assertIn('/static/css/language.css', html)
                self.assertIn('data-guide-copy="en"', html)
                self.assertIn('data-i18n-aria-label-en=', html)
        archive = self.client.get('/kozekilmu').get_data(as_text=True)
        self.assertIn('data-i18n-alt-en=', archive)
        self.assertIn('From P8 on the grid to P1 overall', archive)
        self.assertIn('https://b23.tv/F3xhGEK', archive)

    def test_guide_toc_switches_languages_without_duplicate_or_hidden_links(self):
        result = subprocess.run(["node", "tests/guide_language_harness.js"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
