"""Catalog data integrity and calculator arithmetic contracts."""
from pathlib import Path
import shutil
import subprocess
import unittest
from app import app
from lmu_guide_data import CARS, CIRCUITS


class LmuExtensionsTests(unittest.TestCase):
    def test_catalog_contains_all_cars_and_reverse_recommendations(self):
        html = app.test_client().get('/kozekilmu/cars').get_data(as_text=True)
        self.assertEqual(html.count('class="circuit-card catalog-card"'), len(CARS))
        for slug, car in CARS.items():
            self.assertIn(f'data-key="{slug}"', html)
            self.assertIn(car.strength, html)
            self.assertIn(car.caution, html)
        for circuit in CIRCUITS:
            expected = len(circuit.lmgt3) + len(circuit.hypercar)
            self.assertEqual(html.count(f'href="/kozekilmu/tracks#{circuit.slug}"'), expected)

    def test_new_routes_have_shared_navigation_and_active_page(self):
        for path in ['/kozekilmu/cars', '/kozekilmu/strategy']:
            response = app.test_client().get(path)
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn(f'href="{path}" aria-current="page"', html)
            self.assertIn('id="guide-language-toggle"', html)
            self.assertIn('id="theme-toggle"', html)

    @unittest.skipUnless(shutil.which('node'), 'Node is required for calculator checks')
    def test_strategy_arithmetic(self):
        completed = subprocess.run(['node', 'tests/js/lmu_strategy_harness.js'], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
