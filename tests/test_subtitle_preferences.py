import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import app as web_app
from task_control import TaskManager, TaskSeed
from task_history import TaskHistoryStore


class SubtitleOptionsTests(unittest.TestCase):
    def test_api_rejects_malformed_or_audio_subtitles(self):
        mocked = patch.object(web_app.task_manager, 'create_batch', return_value={'id': 'batch', 'total': 1, 'download_dir': '/tmp'})
        mocked.start()
        self.addCleanup(mocked.stop)
        client = web_app.app.test_client()
        for options in [True, [], {'subtitles': 'yes'}, {'unknown': True}, {'automatic': True}]:
            with self.subTest(options=options):
                response = client.post('/api/download', json={'urls': ['https://youtu.be/x'], 'subtitle_options': options})
                self.assertEqual(response.status_code, 400)
        response = client.post('/api/download', json={'urls': ['https://youtu.be/x'], 'media_type': 'audio', 'subtitle_options': {'danmaku': True}})
        self.assertEqual(response.status_code, 400)

    def test_api_forwards_valid_options(self):
        with patch.object(web_app.task_manager, 'create_batch', return_value={'id': 'batch', 'total': 1, 'download_dir': '/tmp'}) as create:
            response = web_app.app.test_client().post('/api/download', json={'urls': ['https://youtu.be/x'], 'subtitle_options': {'subtitles': True}})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(create.call_args.kwargs['subtitle_options']['subtitles'])

    def test_options_survive_history_and_redownload(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TaskHistoryStore(Path(tmp) / 'history.sqlite3')
            calls = []
            def run(url, **kw):
                calls.append(kw)
                return {'title': 'fixture', 'filepath': str(Path(tmp) / 'fixture.mkv'), 'subtitle_status': 'embedded', 'subtitle_tracks': 1, 'subtitle_warnings': []}
            manager = TaskManager(run, max_workers=1, history_store=store)
            options = {'subtitles': True, 'automatic': False, 'danmaku': True}
            batch = manager.create_batch([TaskSeed('bilibili', 'https://www.bilibili.com/video/BVfixture')], 'video', 'mp3', 'standard', tmp, subtitle_options=options)
            options['subtitles'] = False
            self.assertTrue(manager.wait_for_idle())
            manager.shutdown()
            manager = TaskManager(run, max_workers=1, history_store=store)
            self.addCleanup(manager.shutdown)
            restored = manager.snapshot(batch['id'])
            task = restored['tasks'][0]
            self.assertTrue(task['subtitle_options']['subtitles'])
            self.assertEqual(task['result']['subtitle_status'], 'embedded')
            manager.redownload(batch['id'], task['id'])
            self.assertTrue(manager.wait_for_idle())
            self.assertEqual(calls[0]['subtitle_options'], calls[1]['subtitle_options'])

class SubtitleCliTests(unittest.TestCase):
    def test_flags_are_optional_and_auto_implies_subtitles(self):
        from main import split_subtitle_flags
        args, options = split_subtitle_flags(['--auto-subtitles', '--danmaku', 'https://youtu.be/x'])
        self.assertEqual(args, ['https://youtu.be/x'])
        self.assertEqual(options, {'subtitles': True, 'automatic': True, 'danmaku': True})
        self.assertEqual(split_subtitle_flags(['https://youtu.be/x'])[1], {})

    def test_batch_downloader_forwards_options(self):
        import downloader
        with tempfile.TemporaryDirectory() as tmp, patch.object(downloader, 'download_video', return_value={'title':'fixture'}) as download:
            downloader.download_tasks([('youtube','https://youtu.be/x')], output_dir=tmp, subtitle_options={'subtitles':True})
            self.assertEqual(download.call_args.kwargs['subtitle_options'], {'subtitles':True})
