import re
from html.parser import HTMLParser
from pathlib import Path
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

    def test_dynamic_language_preserves_tasks_and_selection(self):
        result = subprocess.run(['node', 'tests/js/download_language_harness.js'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_english_static_copy_and_attributes_have_no_untranslated_chinese(self):
        from tests.test_lmu_guide import _EnglishVisibleCopyParser

        class AttributeParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.missing = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                for name in ('alt', 'aria-label', 'title', 'placeholder'):
                    if re.search(r'[\u3400-\u9fff]', attrs.get(name, '')):
                        translated = attrs.get(f'data-i18n-{name}-en', '')
                        if not translated or re.search(r'[\u3400-\u9fff]', translated):
                            self.missing.append((tag, name, attrs[name]))

        for route in ('/', '/guide', '/kozekilmu', '/kozekilmu/tracks'):
            with self.subTest(route=route):
                html = web_app.app.test_client().get(route).get_data(as_text=True)
                parser = _EnglishVisibleCopyParser()
                parser.feed(html)
                self.assertEqual(parser.han_text, [])
                metadata = AttributeParser()
                metadata.feed(html)
                self.assertEqual(metadata.missing, [])

    def test_readme_language_links_and_section_coverage(self):
        zh = Path('README.md').read_text()
        en = Path('README.en.md').read_text()
        self.assertIn('[English](README.en.md)', zh)
        self.assertIn('[中文](README.md)', en)
        for level in ('## ', '### ', '#### '):
            self.assertEqual(sum(line.startswith(level) for line in zh.splitlines()),
                             sum(line.startswith(level) for line in en.splitlines()))
