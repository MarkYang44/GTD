"""Source and review boundaries for the retained guide and catalog."""
from datetime import date
import unittest
from app import app
from lmu_guide_data import CARS, CIRCUITS
from lmu_practice_data import CAR_NOTES, TRACK_NOTES, CHECKED_ON, GAME_CHECKED_ON, GAME_REFERENCE
from lmu_content import recommendation_review, sleeper_review


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

    def test_us_track_pack_two_notes_capture_the_official_driving_challenges(self):
        self.assertIn('blind crests', TRACK_NOTES['road-atlanta']['observation'])
        self.assertIn('first true street circuit', TRACK_NOTES['long-beach']['observation'])
        self.assertEqual(TRACK_NOTES['road-atlanta']['checked_on'], '2026-09-22')
        self.assertEqual(TRACK_NOTES['long-beach']['checked_on'], '2026-09-22')

    def test_all_pairings_have_context_sources_without_false_version_claims(self):
        for circuit in CIRCUITS:
            for rec in (*circuit.lmgt3, *circuit.hypercar):
                review = recommendation_review(circuit, CARS[rec.car_slug])
                if review['applicable_version'] is not None:
                    self.assertTrue((review['evidence_url'] or '').startswith('https://'))
                self.assertEqual(review['sources'], [circuit.source_url, CAR_NOTES[rec.car_slug]['source_url']])

    def test_v142_build_reference_has_an_independent_review_date(self):
        self.assertEqual(CHECKED_ON, '2026-09-09')
        self.assertEqual(GAME_REFERENCE, 'V1.4.2')
        self.assertEqual(GAME_CHECKED_ON, '2026-09-22')

    def test_sleepers_keep_independent_source_review(self):
        for circuit in CIRCUITS:
            for class_name, rec in (('LMGT3', circuit.sleeper_lmgt3), ('Hypercar', circuit.sleeper_hypercar)):
                review = sleeper_review(circuit, CARS[rec.car_slug], class_name)
                self.assertEqual(review['sources'], [circuit.source_url, CAR_NOTES[rec.car_slug]['source_url']])

    def test_pages_expose_source_notes(self):
        client = app.test_client()
        tracks = client.get('/kozekilmu/tracks').get_data(as_text=True)
        cars = client.get('/kozekilmu/cars').get_data(as_text=True)
        self.assertEqual(tracks.count('data-content-review'), 144)
        self.assertEqual(cars.count('data-practice'), len(CARS))
        self.assertIn('Unverified', tracks)
