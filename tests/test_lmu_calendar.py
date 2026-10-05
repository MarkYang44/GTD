"""Calendar contract and lossless manual publication."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


def calendar_fixture():
    return {
        'schemaVersion': 1, 'weekStart': '2026-10-20', 'weekEnd': '2026-10-26',
        'lastUpdated': '2026-10-20T12:30:00Z', 'timezone': 'Europe/London',
        'gameVersion': None, 'sources': ['https://www.racecontrol.gg/'],
        'events': [{
            'id': 'test-only', 'name': 'Test fixture — not an official event',
            'track': 'Fuji', 'trackId': 'fuji', 'layout': None, 'eventType': 'Daily',
            'sessions': ['2026-10-25T00:30:00Z', '2026-10-25T01:30:00Z'],
            'durationMinutes': 30, 'classes': ['LMGT3'], 'eventLevel': 'Beginner',
            'eligibility': {'minimumSR': None, 'badge': None, 'subscription': None},
            'weather': None, 'trackConditions': None, 'allowedCars': {'LMGT3': ['ferrari-296-lmgt3']},
            'recommendedCars': {'LMGT3': [{
                'carId': 'ferrari-296-lmgt3', 'rank': 1,
                'summary': {'zh': '练习建议', 'en': 'Practice suggestion'},
                'drivingCharacteristics': None, 'driverType': None,
                'evidence': {'gameVersion': None, 'trackCharacteristics': None, 'bop': None, 'recentPerformance': None, 'sources': []}
            }]},
            'strategy': [{
                'carId': 'ferrari-296-lmgt3',
                'inputs': {'minutes': 30, 'lap': 120, 'fuel': 3, 'tank': 30, 'formation': 0, 'rate': 2, 'loss': 25},
                'calculationNotes': {'zh': '测试假设，非实测。', 'en': 'Test assumptions, not measurements.'},
                'pitStopRequirement': None, 'pitWindow': None, 'tireStrategy': None, 'tireChangeRecommendation': None,
                'trafficManagement': None, 'fasterClassAdvice': None, 'slowerClassAdvice': None,
                'overtakingAdvice': None, 'beingLappedAdvice': None, 'sources': []
            }], 'sources': ['https://www.racecontrol.gg/']
        }]
    }


class CalendarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if importlib.util.find_spec('lmu_calendar'):
            import lmu_calendar
            cls.api = lmu_calendar

    def setUp(self):
        self.assertTrue(importlib.util.find_spec('lmu_calendar'), 'Calendar data layer is missing')
        self.data = calendar_fixture()

    def test_uk_transition_and_cross_day(self):
        self.assertEqual(self.api.uk_time('2026-10-25T00:30:00Z'), '2026-10-25 01:30 BST')
        self.assertEqual(self.api.uk_time('2026-10-25T01:30:00Z'), '2026-10-25 01:30 GMT')
        self.assertEqual(self.api.uk_time('2026-03-29T01:30:00Z'), '2026-03-29 02:30 BST')
        self.assertEqual(self.api.uk_time('2026-06-01T23:30:00Z'), '2026-06-02 00:30 BST')
        with self.assertRaises(ValueError):
            self.api.uk_time('2026-10-25T01:30:00')

    def test_null_values_and_unsupported_classes(self):
        self.api.validate_calendar(self.data)
        event = self.data['events'][0]
        event['classes'] = ['LMP3']
        event['recommendedCars'] = {}; event['strategy'] = []; event['allowedCars'] = {}
        self.api.validate_calendar(self.data)
        event['sessions'] = []
        self.api.validate_calendar(self.data)

    def test_invalid_candidates(self):
        mutations = [
            lambda d: d.update(timezone='UTC'),
            lambda d: d['events'][0].update(sessions=['2026-10-25T01:30:00+00:99']),
            lambda d: d.update(weekEnd='2026-10-19'),
            lambda d: d['events'][0].update(track=' '),
            lambda d: d['events'][0].update(classes=[]),
            lambda d: d['events'][0].update(sessions=['2026-10-25T01:30:00']),
            lambda d: d['events'][0].update(sessions=['2026-11-01T01:30:00Z']),
            lambda d: d['events'][0]['strategy'][0]['inputs'].update(fuel=-1),
            lambda d: d['events'][0]['strategy'][0]['inputs'].update(fuel=float('nan')),
            lambda d: d['events'][0]['strategy'][0]['inputs'].pop('tank'),
            lambda d: d['events'][0]['strategy'][0].update(calculationNotes=None),
            lambda d: d['events'][0]['recommendedCars']['LMGT3'][0].update(carId='porsche-963'),
            lambda d: d['events'][0].update(sources=['javascript:alert(1)']),
            lambda d: d['events'][0].update(sources=['https://racecontrol.gg.evil.test/']),
            lambda d: d['events'][0]['recommendedCars'].update(LMGT3=d['events'][0]['recommendedCars']['LMGT3'] * 4),
            lambda d: d.update(events=d['events'] * 2),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                candidate = copy.deepcopy(self.data); mutation(candidate)
                with self.assertRaises(ValueError): self.api.validate_calendar(candidate)

    def test_publication_noop_archive_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertTrue(self.api.publish_calendar(self.data, root))
            original = (root / 'current.json').read_bytes()
            self.assertFalse(self.api.publish_calendar(self.data, root))
            invalid = copy.deepcopy(self.data); invalid['events'][0]['track'] = ''
            with self.assertRaises(ValueError): self.api.publish_calendar(invalid, root)
            self.assertEqual((root / 'current.json').read_bytes(), original)
            self.assertEqual(self.api.load_calendar(root)['state'], 'update-failed')
            next_week = copy.deepcopy(self.data)
            next_week.update(weekStart='2026-10-27', weekEnd='2026-11-02', lastUpdated='2026-10-27T12:30:00Z')
            next_week['events'][0]['sessions'] = ['2026-10-28T12:30:00Z']
            self.api.publish_calendar(next_week, root)
            self.assertEqual((root / 'archive' / '2026-10-20.json').read_bytes(), original)
            (root / 'current.json').write_text('broken', encoding='utf-8')
            loaded = self.api.load_calendar(root)
            self.assertEqual(loaded['data']['weekStart'], '2026-10-20')
            self.assertTrue(loaded['fallback'])
            (root / '.update.lock').mkdir()
            with self.assertRaises(ValueError): self.api.publish_calendar(next_week, root)

    def test_reimport_repairs_corrupt_current_and_initial_backup_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.api.publish_calendar(self.data, root)
            (root / 'current.json').write_text('broken')
            self.assertTrue(self.api.load_calendar(root)['fallback'])
            self.assertTrue(self.api.publish_calendar(self.data, root))
            self.assertEqual(self.api.read_calendar(root / 'current.json'), self.data)
            self.assertFalse(self.api.load_calendar(root)['fallback'])

    def test_publication_rejects_oversized_serialization_before_replacing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.api.publish_calendar(self.data, root)
            original = (root / 'current.json').read_bytes()
            oversized = copy.deepcopy(self.data)
            event = oversized['events'][0]
            # Valid text lengths but enough nested copies to exceed the disk bound.
            for key in ('pitStopRequirement', 'tireStrategy', 'tireChangeRecommendation',
                        'trafficManagement', 'fasterClassAdvice', 'slowerClassAdvice',
                        'overtakingAdvice', 'beingLappedAdvice', 'calculationNotes'):
                event['strategy'][0][key] = {'zh': '界' * 4000, 'en': 'a' * 4000}
            oversized['events'] = [copy.deepcopy(event) for _ in range(40)]
            for index, item in enumerate(oversized['events']): item['id'] = f'large-{index}'
            with self.assertRaises(ValueError): self.api.publish_calendar(oversized, root)
            self.assertEqual((root / 'current.json').read_bytes(), original)

    def test_mixed_offset_sessions_render_in_chronological_order(self):
        from app import app
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.data['events'][0]['sessions'] = ['2026-10-25T02:00:00+02:00', '2026-10-25T01:00:00Z']
            self.api.publish_calendar(self.data, root)
            with mock.patch.dict('os.environ', {'GTD_LMU_CALENDAR_DIR': directory}):
                html = app.test_client().get('/kozekilmu/calendar').get_data(as_text=True)
            self.assertLess(html.index('01:00 BST'), html.index('01:00 GMT'))

    def test_failed_file_import_cannot_write_status_during_another_update(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.api.publish_calendar(self.data, root)
            original = (root / 'status.json').read_bytes()
            (root / '.update.lock').mkdir()
            candidate = root / 'invalid.json'; candidate.write_text('{bad json')
            result = subprocess.run([sys.executable, 'scripts/update_lmu_calendar.py',
                                     str(candidate), '--directory', str(root)], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual((root / 'status.json').read_bytes(), original)

    def test_validation_only_does_not_write_failure_status(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / 'invalid.json'; candidate.write_text('{bad json')
            result = subprocess.run([sys.executable, 'scripts/update_lmu_calendar.py',
                                     str(candidate), '--directory', str(root), '--check'], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['invalid.json'])

    def test_unpublished_valid_current_is_empty_not_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'current.json').write_text(json.dumps(self.api.empty_calendar()))
            self.assertEqual(self.api.load_calendar(root)['state'], 'empty')
            (root / 'current.json').write_text('invalid')
            self.assertEqual(self.api.load_calendar(root)['state'], 'update-failed')

    def test_empty_and_bad_repository_render(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self.api.load_calendar(Path(directory))['state'], 'empty')
        from app import app
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict('os.environ', {'GTD_LMU_CALENDAR_DIR': directory}):
            response = app.test_client().get('/kozekilmu/calendar')
            self.assertEqual(response.status_code, 200)
            self.assertIn('No calendar published', response.get_data(as_text=True))

    def test_route_uses_local_times_shared_shell_and_escaped_text(self):
        from app import app
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.data['events'][0]['name'] = '<script>bad()</script>'
            self.api.publish_calendar(self.data, root)
            with patch.dict('os.environ', {'GTD_LMU_CALENDAR_DIR': directory}):
                html = app.test_client().get('/kozekilmu/calendar').get_data(as_text=True)
            self.assertIn('01:30 BST', html); self.assertIn('01:30 GMT', html)
            self.assertIn('href="/kozekilmu/calendar" aria-current="page"', html)
            self.assertIn('id="theme-toggle"', html)
            self.assertIn('&lt;script&gt;', html)
            self.assertNotIn('<script>bad()', html)
