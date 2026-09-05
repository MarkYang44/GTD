import subprocess
import unittest
import app as web_app


class GlobalLanguageTests(unittest.TestCase):
    def test_all_pages_share_early_bootstrap_and_one_toggle(self):
        client = web_app.app.test_client()
        for path in ('/', '/guide', '/kozekilmu', '/kozekilmu/tracks'):
            with self.subTest(path=path):
                html = client.get(path).get_data(as_text=True)
                self.assertIn('/static/css/language.css', html)
                self.assertEqual(html.count('id="guide-language-toggle"'), 1)
                self.assertLess(html.index('/static/js/lmu_guide_language.js'), html.index('<body>'))

    def test_global_runtime(self):
        result = subprocess.run(['node', 'tests/js/global_language_harness.js'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
