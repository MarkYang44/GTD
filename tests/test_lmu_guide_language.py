import subprocess
import unittest
from pathlib import Path

import app as web_app


JS_PATH = Path("static/js/lmu_guide_language.js")
HARNESS_PATH = Path("tests/js/lmu_guide_language_harness.js")


class LmuGuideLanguageTests(unittest.TestCase):
    def test_page_serves_only_the_dedicated_language_runtime_after_motion(self):
        client = web_app.app.test_client()
        html = client.get("/kozekilmu").get_data(as_text=True)
        self.assertIn('<script defer src="/static/js/motion.js"></script>', html)
        self.assertIn('<script defer src="/static/js/lmu_guide_language.js"></script>', html)
        self.assertLess(html.index("motion.js"), html.index("lmu_guide_language.js"))
        self.assertNotIn("onchange=", html)
        self.assertNotIn("onclick=", html)

    def test_language_runtime_defaults_persists_updates_and_deduplicates(self):
        result = subprocess.run(
            ["node", str(HARNESS_PATH)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_language_script_has_valid_javascript(self):
        result = subprocess.run(
            ["node", "--check", str(JS_PATH)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
