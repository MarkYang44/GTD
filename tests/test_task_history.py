"""Restart and retention behavior of local task history."""
import importlib.util
import json
import tempfile
import sqlite3
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

from output_files import prepare_output_dir, prepared_output_dir
from task_control import TaskManager, TaskSeed


class TaskHistoryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('task_history'),
                             'durable task history module is missing')
        from task_history import TaskHistoryStore
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.store = TaskHistoryStore(self.root / 'state' / 'tasks.sqlite3')

    def manager(self, runner=None, **kwargs):
        manager = TaskManager(runner or (lambda url, **kw: {'filepath': str(self.root / 'out.mp4')}),
                              history_store=self.store, **kwargs)
        self.addCleanup(manager.shutdown)
        return manager

    def create(self, manager, url='https://example.com/video'):
        return manager.create_batch([TaskSeed('youtube', url)], 'video', 'mp3', 'normal', str(self.root / 'media'))

    def test_completed_history_restores_outputs_and_redownload_versions(self):
        first = self.manager()
        batch = self.create(first)
        self.assertTrue(first.wait_for_idle())
        first.shutdown()
        preparer = Mock(side_effect=prepare_output_dir)
        received = []
        def runner(url, **kw):
            received.append((prepared_output_dir(kw['output_dir']), kw['output_version']))
            return {'filepath': str(self.root / 'out (2).mp4')}
        restored = self.manager(runner, capability_aware_runner=True, directory_preparer=preparer)
        preparer.assert_not_called()
        snapshot = restored.snapshot(batch['id'])
        self.assertEqual(snapshot['completed'], 1)
        self.assertEqual(snapshot['tasks'][0]['result']['filepath'], str(self.root / 'out.mp4'))
        restored.redownload(batch['id'], batch['tasks'][0]['id'])
        self.assertTrue(restored.wait_for_idle())
        self.assertEqual(received, [(self.root / 'media', 2)])
        preparer.assert_called_once()

    def test_interrupted_tasks_restore_retryable_without_auto_start(self):
        entered, release = threading.Event(), threading.Event()
        def blocked(url, **kw):
            entered.set()
            release.wait(5)
            return {'filepath': str(self.root / 'out.mp4')}
        first = self.manager(blocked, max_workers=1)
        self.addCleanup(release.set)
        batch = first.create_batch([TaskSeed('youtube', 'one'), TaskSeed('youtube', 'two')],
                                   'video', 'mp3', 'normal', str(self.root / 'media'))
        self.assertTrue(entered.wait(2))
        # Copy a committed database snapshot while the old process has unfinished work.
        from task_history import TaskHistoryStore
        copied = TaskHistoryStore(self.root / 'restart.sqlite3')
        for saved in self.store.load_batches():
            copied.save_batch(saved)
        runner = Mock(return_value={'filepath': str(self.root / 'retry.mp4')})
        restored = TaskManager(runner, history_store=copied)
        self.addCleanup(restored.shutdown)
        snapshot = restored.snapshot(batch['id'])
        runner.assert_not_called()
        self.assertEqual(snapshot['failed'], 2)
        for task in snapshot['tasks']:
            self.assertEqual(task['error']['error_code'], 'INTERRUPTED')
            self.assertTrue(task['can_retry'])
        restored.retry(batch['id'], snapshot['tasks'][0]['id'])
        self.assertTrue(restored.wait_for_idle())
        runner.assert_called_once()
        release.set()

    def test_loading_does_not_recreate_missing_output_directory(self):
        first = self.manager()
        batch = self.create(first)
        self.assertTrue(first.wait_for_idle())
        first.shutdown()
        (self.root / 'media').rmdir()
        restored = self.manager()
        self.assertFalse((self.root / 'media').exists())
        restored.redownload(batch['id'], batch['tasks'][0]['id'])
        self.assertTrue(restored.wait_for_idle())
        self.assertTrue((self.root / 'media').is_dir())

    def test_retention_removes_old_terminal_batches_from_disk(self):
        first = self.manager(max_batches=2)
        ids = []
        for number in range(3):
            ids.append(self.create(first, str(number))['id'])
            self.assertTrue(first.wait_for_idle())
        first.shutdown()
        restored = self.manager(max_batches=2)
        summaries = restored.list_batches()
        self.assertEqual([item['id'] for item in summaries], list(reversed(ids[1:])))
        self.assertNotIn('tasks', summaries[0])
        self.assertIn('created_at', summaries[0])
        with self.assertRaises(KeyError):
            restored.snapshot(ids[0])

    def test_history_write_failure_does_not_strand_downloads(self):
        self.store.save_batch = Mock(side_effect=sqlite3.OperationalError('disk full'))
        manager = self.manager()
        with self.assertLogs(manager._logger, level='WARNING'):
            batch = self.create(manager)
            self.assertTrue(manager.wait_for_idle())
        self.assertEqual(manager.snapshot(batch['id'])['completed'], 1)

    def test_progress_ticks_do_not_write_history_and_cancellation_is_saved(self):
        entered, release = threading.Event(), threading.Event()
        def runner(url, **kw):
            for number in range(50):
                kw['progress_callback']('progress', {'percent_text': str(number)})
            entered.set()
            release.wait(5)
            return {'filepath': str(self.root / 'out.mp4')}
        self.store.save_batch = Mock(wraps=self.store.save_batch)
        manager = self.manager(runner, max_workers=1)
        self.addCleanup(release.set)
        batch = manager.create_batch([TaskSeed('youtube', 'one'), TaskSeed('youtube', 'two')],
                                     'video', 'mp3', 'normal', str(self.root / 'media'))
        self.assertTrue(entered.wait(2))
        self.assertEqual(self.store.save_batch.call_count, 2)
        manager.cancel(batch['id'], batch['tasks'][1]['id'])
        self.assertEqual(self.store.load_batches()[0]['tasks'][1]['status'], 'cancelled')
        release.set()

    def test_failed_directory_revalidation_preserves_restored_task(self):
        first = self.manager()
        batch = self.create(first)
        self.assertTrue(first.wait_for_idle())
        first.shutdown()
        restored = self.manager(directory_preparer=Mock(side_effect=ValueError('directory unavailable')))
        with self.assertRaisesRegex(ValueError, 'directory unavailable'):
            restored.redownload(batch['id'], batch['tasks'][0]['id'])
        self.assertEqual(restored.snapshot(batch['id'])['total'], 1)
        self.assertEqual(restored.snapshot(batch['id'])['completed'], 1)

    def test_store_omits_credentials_private_diagnostics_and_capabilities(self):
        first = self.manager(lambda url, **kw: {'filepath': str(self.root / 'out.mp4'),
                                             'cookies': 'SECRET_COOKIE', 'technical_detail': 'SECRET_DIAG'})
        batch = self.create(first)
        self.assertTrue(first.wait_for_idle())
        saved = self.store.load_batches()[0]
        encoded = json.dumps(saved)
        self.assertNotIn('SECRET_COOKIE', encoded)
        self.assertNotIn('SECRET_DIAG', encoded)
        self.assertNotIn('_prepared_output_dir', encoded)
        self.assertEqual(saved['id'], batch['id'])


if __name__ == '__main__':
    unittest.main()
