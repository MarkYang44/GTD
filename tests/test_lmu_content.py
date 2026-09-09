"""Audit source coverage, review boundaries and reproducible content history."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import unittest
from app import app
from lmu_guide_data import CARS, CIRCUITS
from lmu_practice_data import CAR_NOTES, TRACK_NOTES
from lmu_content import CONTENT_DIR, current_records, compare_records, history, recommendation_review


class ContentTests(unittest.TestCase):
    def test_every_entity_has_bilingual_sourced_practice(self):
        self.assertEqual(set(CAR_NOTES), set(CARS))
        self.assertEqual(set(TRACK_NOTES), {c.slug for c in CIRCUITS})
        for notes in (CAR_NOTES, TRACK_NOTES):
            for note in notes.values():
                for key in ['observation', 'observation_zh', 'exercise', 'exercise_zh', 'source_name']:
                    self.assertTrue(note[key].strip())
                self.assertTrue(note['source_url'].startswith('https://'))
                self.assertLessEqual(date.fromisoformat(note['checked_on']), date.today())
                if note['applicable_version'] is not None:
                    self.assertTrue(note.get('evidence_url', '').startswith('https://'))

    def test_all_pairings_have_context_sources_without_false_version_claims(self):
        for circuit in CIRCUITS:
            for rec in (*circuit.lmgt3, *circuit.hypercar):
                review = recommendation_review(circuit, CARS[rec.car_slug])
                if review['applicable_version'] is not None:
                    self.assertTrue((review['evidence_url'] or '').startswith('https://'))
                self.assertEqual(review['sources'], [circuit.source_url, CAR_NOTES[rec.car_slug]['source_url']])

    def test_snapshot_is_current_and_baseline_is_truthful(self):
        releases = history()
        initial = next(release for release in releases if release['version'] == '2026.09.09.1')
        self.assertEqual(len(initial['changes']), 129)
        self.assertEqual(releases[-1]['changes'], [])
        snapshot = json.loads((CONTENT_DIR / releases[0]['snapshot']).read_text(encoding='utf-8'))
        self.assertEqual(snapshot, current_records(), 'Review and publish edited LMU content before committing.')
        base = json.loads((CONTENT_DIR / releases[-1]['snapshot']).read_text(encoding='utf-8'))
        self.assertNotIn('checked_on', base['recommendation:bahrain:bmw-m4-lmgt3']['fields'])
        self.assertEqual(compare_records(snapshot, snapshot), [])

    def test_diff_reports_before_after_addition_and_removal(self):
        before = {'car:test': dict(name='Test', href='/test', fields={'strength': {'zh': '旧', 'en': 'Old'}})}
        after = deepcopy(before)
        after['car:test']['fields']['strength']['en'] = 'New'
        change = compare_records(before, after)[0]
        self.assertEqual(change['fields'][0]['before']['en'], 'Old')
        self.assertEqual(change['fields'][0]['after']['en'], 'New')
        self.assertEqual(compare_records({}, after)[0]['status'], 'added')
        self.assertEqual(compare_records(before, {})[0]['status'], 'removed')
        renamed = deepcopy(before)
        renamed['car:test']['name'] = 'Renamed'
        self.assertEqual(compare_records(before, renamed)[0]['fields'][0]['after']['en'], 'Renamed')

    def test_release_checker(self):
        run = subprocess.run([sys.executable, 'scripts/publish_lmu_content.py', '--check'], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_pages_expose_notes_and_change_history(self):
        client = app.test_client()
        tracks = client.get('/kozekilmu/tracks').get_data(as_text=True)
        cars = client.get('/kozekilmu/cars').get_data(as_text=True)
        updates = client.get('/kozekilmu/updates')
        self.assertEqual(tracks.count('data-content-review'), 96)
        self.assertEqual(cars.count('data-practice'), len(CARS))
        self.assertEqual(updates.status_code, 200)
        html = updates.get_data(as_text=True)
        self.assertIn('Before:', html)
        self.assertIn('After:', html)
        self.assertIn('Unverified', html)
        self.assertIn('V1.4.1.4', html)
