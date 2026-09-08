import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
import threading
import time
from unittest.mock import patch
import unittest

from werkzeug.datastructures import FileStorage
from task_control import CancellationToken
from output_files import prepare_output_dir
from download_errors import DownloadFailure
from local_audio import UploadStore, extract_audio, run_process


class LocalAudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = UploadStore(self.root / 'uploads', max_file_bytes=1024, max_total_bytes=2048)

    def test_upload_limit_and_untrusted_name(self):
        with self.assertRaises(DownloadFailure):
            self.store.save(FileStorage(stream=io.BytesIO(b'x' * 1025), filename='../../bad.mp4'))
        self.assertEqual(list(self.store.root.glob('*')), [])
        key = self.store.save(FileStorage(stream=io.BytesIO(b'ok'), filename='../../clip.mp4'))
        path, name = self.store.resolve(key)
        self.assertEqual(name, 'clip.mp4')
        self.assertEqual(path.parent, self.store.root)
        with self.assertRaises(DownloadFailure):
            self.store.resolve('../../secret')

    def test_capacity_and_expiry_preserve_active_inputs(self):
        key = self.store.save(FileStorage(stream=io.BytesIO(b'x' * 1024), filename='a.mp4'))
        key2 = self.store.save(FileStorage(stream=io.BytesIO(b'x' * 1024), filename='b.mp4'))
        with self.assertRaises(DownloadFailure):
            self.store.save(FileStorage(stream=io.BytesIO(b'x'), filename='c.mp4'))
        self.store.cleanup({key}, now=10**12)
        self.assertTrue(self.store.resolve(key)[0].exists())
        with self.assertRaises(DownloadFailure):
            self.store.resolve(key2)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
    def test_real_source_copy_and_mp3(self):
        video = self.root / 'sample.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=32x32:d=0.4', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.4', '-f', 'lavfi', '-i', 'sine=frequency=880:duration=0.4', '-map', '0:v', '-map', '1:a', '-map', '2:a', '-disposition:a:0', '0', '-disposition:a:1', 'default', '-c:v', 'mpeg4', '-c:a', 'aac', '-shortest', str(video)], check=True)
        self.store = UploadStore(self.root / 'media')
        with video.open('rb') as source:
            key = self.store.save(FileStorage(stream=source, filename='sample.mp4'))
        outputs = []
        for mode, codec in [('source', 'aac'), ('mp3', 'mp3')]:
            result = extract_audio(key, store=self.store, audio_format=mode, output_dir=prepare_output_dir(self.root / 'out'), cancel_token=CancellationToken())
            outputs.append(result['filepath'])
            self.assertEqual(result['audio_stream_index'], 2)
            probe = subprocess.run(['ffprobe','-v','error','-show_streams','-of','json',result['filepath']],capture_output=True,text=True,check=True)
            streams = json.loads(probe.stdout)['streams']
            self.assertEqual([s['codec_type'] for s in streams], ['audio'])
            self.assertEqual(streams[0]['codec_name'], codec)
        def packets(path, selector='a:0'):
            p = subprocess.run(['ffprobe','-v','error','-select_streams',selector,'-show_packets','-show_data_hash','sha256','-show_entries','packet=data_hash','-of','json',str(path)],capture_output=True,text=True,check=True)
            return [v['data_hash'] for v in json.loads(p.stdout)['packets']]
        self.assertEqual(packets(video, 'a:1'), packets(outputs[0]))
        token = CancellationToken(); token.cancel()
        with self.assertRaises(DownloadFailure):
            extract_audio(key, store=self.store, audio_format='mp3', output_dir=prepare_output_dir(self.root / 'out'), cancel_token=token)
        self.assertEqual(len(list((self.root / 'out').iterdir())), 2)

    def test_cancellation_terminates_running_process(self):
        token = CancellationToken()
        timer = threading.Timer(.15, token.cancel)
        timer.start(); self.addCleanup(timer.cancel)
        started = time.monotonic()
        with self.assertRaises(DownloadFailure):
            run_process([sys.executable, '-c', 'import time; time.sleep(30)'], token)
        self.assertLess(time.monotonic() - started, 4)

    def test_cancelled_conversion_cleans_partial_output(self):
        key = self.store.save(FileStorage(stream=io.BytesIO(b'video'), filename='video.mp4'))
        token = CancellationToken()
        output = prepare_output_dir(self.root / 'out')
        def fake_process(command, *args, **kwargs):
            if command[0] == 'ffprobe':
                return json.dumps({'streams':[{'index':0,'codec_type':'video'}, {'index':1,'codec_type':'audio','codec_name':'aac'}]}).encode()
            Path(command[-1]).write_bytes(b'partial')
            token.cancel(); token.raise_if_cancelled()
        with patch('local_audio.shutil.which', return_value='/ffmpeg'), patch('local_audio.run_process', side_effect=fake_process):
            with self.assertRaises(DownloadFailure):
                extract_audio(key, store=self.store, audio_format='mp3', output_dir=output, cancel_token=token)
        self.assertEqual(list((self.root / 'out').iterdir()), [])
