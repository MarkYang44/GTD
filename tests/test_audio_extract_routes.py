import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from flask import Flask
from audio_extract_routes import extraction_blueprint, with_download_links
from local_audio import UploadStore, extract_audio
from task_control import TaskManager
from task_history import TaskHistoryStore


class ExtractionRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = UploadStore(self.root / 'inputs')
        def runner(key, **kwargs):
            return extract_audio(key, store=self.store, **kwargs)
        self.manager = TaskManager(runner, capability_aware_runner=True,
                                   history_store=TaskHistoryStore(self.root / 'history.sqlite3'))
        self.addCleanup(self.manager.shutdown)
        self.app = Flask(__name__)
        self.app.register_blueprint(extraction_blueprint(self.manager, self.store, str(self.root / 'out')))
        self.client = self.app.test_client()

    def upload(self, data, filename='video.mp4', mode='source'):
        return self.client.post('/api/extract-audio', data={'video': (io.BytesIO(data), filename), 'audio_format': mode})

    def finish(self, batch_id):
        end = time.monotonic() + 10
        while time.monotonic() < end:
            batch = self.manager.snapshot(batch_id)
            if batch['all_done']:
                return with_download_links(batch)
            time.sleep(.03)
        self.fail('Extraction did not finish')

    def test_reject_missing_invalid_and_empty_uploads(self):
        self.assertEqual(self.client.post('/api/extract-audio').status_code, 400)
        self.assertEqual(self.upload(b'x', mode='wav').status_code, 400)
        self.assertEqual(self.upload(b'').status_code, 400)
        self.store.max_file_bytes = 3
        self.assertEqual(self.upload(b'1234').status_code, 413)
        self.assertEqual(list(self.store.root.glob('*')), [])
        self.assertEqual(self.client.get('/api/extract-audio/no/no/file').status_code, 404)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_upload_process_download_and_restore_history(self):
        video = self.root / 'sample.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=s=32x32:d=0.3','-f','lavfi','-i','sine=duration=0.3','-c:v','mpeg4','-c:a','aac','-shortest',str(video)],check=True)
        response = self.upload(video.read_bytes(), '../../clip.mp4', 'mp3')
        self.assertEqual(response.status_code, 202)
        batch = self.finish(response.json['batch_id'])
        task = batch['tasks'][0]
        self.assertEqual(task['status'], 'completed', task)
        response = self.client.get(task['result']['download_url'])
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment;', response.headers['Content-Disposition'])
        self.assertEqual(response.data, Path(task['result']['filepath']).read_bytes())
        self.assertEqual(len(self.client.get('/api/extract-audio/batches').json['batches']), 1)
        restored = TaskManager(lambda *a, **k: None, history_store=TaskHistoryStore(self.root / 'history.sqlite3'))
        self.addCleanup(restored.shutdown)
        self.assertEqual(restored.snapshot(batch['id'])['tasks'][0]['result']['filepath'], task['result']['filepath'])
        # A result path cannot redirect the download endpoint outside its output directory.
        task['result']['filepath'] = str(video)
        with patch.object(self.manager, 'snapshot', return_value=batch):
            self.assertEqual(self.client.get(task['result']['download_url']).status_code, 404)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_no_audio_invalid_media_and_expired_retry(self):
        video = self.root / 'silent.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=s=32x32:d=0.2','-c:v','mpeg4',str(video)],check=True)
        batch = self.finish(self.upload(video.read_bytes()).json['batch_id'])
        self.assertEqual(batch['tasks'][0]['error']['error_code'], 'NO_AUDIO')
        invalid = self.finish(self.upload(b'not a video').json['batch_id'])
        self.assertEqual(invalid['tasks'][0]['status'], 'failed')
        self.assertFalse(any((self.root / 'out').glob('.extract-*')))
        # Cancellation keeps a retained input retryable; expired input fails explicitly.
        task = invalid['tasks'][0]
        self.store.remove(task['url'])
        from task_control import CancellationToken
        from output_files import prepare_output_dir
        from download_errors import DownloadFailure
        with self.assertRaises(DownloadFailure) as error:
            extract_audio(task['url'], store=self.store, audio_format='source', output_dir=prepare_output_dir(self.root / 'out'), cancel_token=CancellationToken())
        self.assertEqual(error.exception.info.error_code, 'INPUT_EXPIRED')
