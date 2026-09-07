import subprocess
import unittest
from unittest.mock import Mock, patch

import app as web_app


class HistoryApiTests(unittest.TestCase):
    def test_history_endpoint_returns_summaries(self):
        manager = Mock()
        manager.list_batches.return_value = [{'id': 'saved', 'total': 2}]
        with patch.object(web_app, 'task_manager', manager):
            response = web_app.app.test_client().get('/api/batches')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'batches': [{'id': 'saved', 'total': 2}]})

    def test_bulk_retry_directory_error_returns_structured_conflict(self):
        manager = Mock()
        manager.retry_failed.side_effect = ValueError('directory unavailable')
        with patch.object(web_app, 'task_manager', manager):
            response = web_app.app.test_client().post('/api/batch/saved/retry-failed')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json['error_code'], 'TASK_STATE_CONFLICT')

    def test_homepage_exposes_history_controls(self):
        html = web_app.app.test_client().get('/').get_data(as_text=True)
        self.assertIn('id="batchHistory"', html)
        self.assertIn('id="historyFeedback"', html)

    def test_polling_recovery_harness(self):
        result = subprocess.run(['node', 'tests/js/polling_recovery_harness.js'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Polling recovery harness passed', result.stdout)
