"""Retired pages stay unavailable while the remaining gallery pages work."""
from pathlib import Path
import re
import unittest

from app import app


class RemovedPageTests(unittest.TestCase):
    def test_retired_routes_return_not_found(self):
        client = app.test_client()
        for page in ('strategy', 'calendar', 'updates'):
            with self.subTest(page=page):
                self.assertEqual(client.get('/kozekilmu/' + page).status_code, 404)

    def test_remaining_pages_only_link_to_available_navigation(self):
        client = app.test_client()
        for route in ('/kozekilmu', '/kozekilmu/tracks', '/kozekilmu/cars'):
            with self.subTest(route=route):
                response = client.get(route)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                for page in ('strategy', 'calendar', 'updates'):
                    self.assertNotIn('href="/kozekilmu/' + page + '"', html)

    def test_download_documentation_has_no_racing_content(self):
        for filename in ('README.md', 'README.en.md', 'docs/REFERENCE.md',
                         'docs/REFERENCE.en.md', 'docs/WEB_GUIDE.md', 'docs/WEB_GUIDE.en.md'):
            with self.subTest(filename=filename):
                text = Path(filename).read_text(encoding='utf-8')
                self.assertIsNone(re.search(
                    r'LMU|Le Mans|kozekilmu|赛前策略|每周赛历|内容更新|race strategy|weekly calendar',
                    text, re.I))
