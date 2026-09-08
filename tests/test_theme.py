from html.parser import HTMLParser
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ThemeTests(unittest.TestCase):
    def test_theme_runtime(self):
        result = subprocess.run(
            ['node', str(ROOT / 'tests/js/theme_harness.js')],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_theme_switch_has_native_accessible_bilingual_control(self):
        path = ROOT / 'templates/_theme_toggle.html'
        self.assertTrue(path.exists(), 'Shared theme switch is missing')

        class Elements(HTMLParser):
            def __init__(self):
                super().__init__()
                self.inputs = []

            def handle_starttag(self, tag, attrs):
                if tag == 'input':
                    self.inputs.append(dict(attrs))

        parser = Elements()
        parser.feed(path.read_text())
        self.assertEqual(len(parser.inputs), 1)
        switch = parser.inputs[0]
        self.assertEqual(switch['id'], 'theme-toggle')
        self.assertEqual(switch['type'], 'checkbox')
        self.assertEqual(switch['role'], 'switch')
        self.assertEqual(switch['aria-label'], '浅色主题')
        self.assertEqual(switch['data-i18n-aria-label-zh'], '浅色主题')
        self.assertEqual(switch['data-i18n-aria-label-en'], 'Light theme')
