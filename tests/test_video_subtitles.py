import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


class SubtitleTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('video_subtitles'), 'subtitle engine must exist')
        import video_subtitles
        return video_subtitles

    def test_selection_separates_danmaku_and_limits_auto_translations(self):
        m = self.module()
        info = {'language': 'ja', 'subtitles': {'danmaku': [{'ext':'xml'}], 'zh-CN':[{'ext':'srt'}]}, 'automatic_captions': {k:[{'ext':'vtt'}] for k in ['ja-orig','en','fr','de','zh-Hans']}}
        selected = m.select_tracks(info, {'subtitles': True, 'automatic': True})
        self.assertEqual({x[0] for x in selected}, {'zh-CN', 'ja-orig', 'en', 'zh-Hans'})
        self.assertEqual([x[0] for x in m.select_tracks(info, {'danmaku': True})], ['danmaku'])

    def test_danmaku_escapes_commands_and_handles_supported_modes(self):
        m = self.module()
        xml = '<i><d p="0,1,25,16777215">{\\pos(0,0)}hi</d><d p="1,5,25,1">top</d><d p="2,4,25,1">bottom</d><d p="3,7,25,1">advanced</d><d p="nan,1,25,1">bad</d></i>'
        ass = m.danmaku_ass(xml)
        self.assertEqual(ass.count('Dialogue:'), 3)
        self.assertIn('\\move(', ass)
        self.assertIn('｛＼pos(0,0)｝hi', ass)
        self.assertNotIn('advanced', ass)
        with self.assertRaises(ValueError):
            m.danmaku_ass('<!DOCTYPE i [<!ENTITY x "boom">]><i/>')

    def test_real_mux_preserves_video_and_creates_switchable_ass(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)/'source.mp4'
            ass = Path(d)/'danmaku.ass'
            dst = Path(d)/'output.mkv'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=size=160x90:duration=1','-f','lavfi','-i','sine=duration=1','-c:v','libx264','-c:a','aac','-shortest',str(src)],check=True)
            ass.write_text(m.danmaku_ass('<i><d p="0,1,25,16777215">hello</d></i>'))
            m.mux_tracks(src,dst,[(ass,'zh','Danmaku')])
            result = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(dst)]))
            self.assertEqual([x['codec_type'] for x in result['streams']], ['video','audio','subtitle'])
            self.assertEqual(result['streams'][2]['codec_name'],'ass')
            self.assertEqual(result['streams'][2]['disposition']['default'],1)
            def video_hash(path):
                return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:v:0','-c','copy','-f','hash','-'])
            self.assertEqual(video_hash(src),video_hash(dst))
            def audio_hash(path):
                return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-c','copy','-f','hash','-'])
            self.assertEqual(audio_hash(src),audio_hash(dst))

    def test_package_uses_native_subtitle_data_and_warns_on_missing(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=size=160x90:duration=1','-c:v','libx264',str(src)],check=True)
            info = {'id':'x','title':'fixture','ext':'mp4','url':'https://example.invalid/video.mp4','subtitles':{'en':[{'ext':'srt','data':'1\n00:00:00,000 --> 00:00:00,800\nHello\n'}]}}
            result = m.package_subtitles(info,src,{'subtitles':True,'danmaku':True},{})
            self.assertEqual(result.suffix,'.mkv')
            self.assertEqual(info['_subtitle_tracks'],1)
            self.assertEqual(info['_subtitle_status'],'partial')
            self.assertIn('danmaku:unavailable',info['_subtitle_warnings'])
            streams = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(result)]))['streams']
            self.assertEqual(streams[1]['tags']['title'],'manual:en')

    def test_download_signature_accepts_options(self):
        import inspect
        import downloader
        self.assertIn('subtitle_options',inspect.signature(downloader.download_video).parameters)

    def test_existing_mp4_subtitles_survive_as_mkv_tracks(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as d:
            src, sub = Path(d)/'source.mp4', Path(d)/'text.srt'
            sub.write_text('1\n00:00:00,000 --> 00:00:00,800\nExisting\n')
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=size=160x90:duration=1','-i',str(sub),'-c:v','libx264','-c:s','mov_text',str(src)],check=True)
            info = {'subtitles': {}}
            result = m.package_subtitles(info, src, {'subtitles':True}, {})
            self.assertEqual(result.suffix, '.mkv')
            self.assertEqual(info['_subtitle_tracks'], 1)
            self.assertEqual(info['_subtitle_status'], 'partial')

    def test_bilibili_ai_track_respects_automatic_option(self):
        m = self.module()
        info = {'subtitles': {'ai-zh':[{'ext':'srt'}]}}
        self.assertEqual(m.select_tracks(info, {'subtitles':True}), [])
        selected = m.select_tracks(info, {'subtitles':True,'automatic':True})
        self.assertEqual(selected[0][2], 'automatic')

    def test_cancellation_does_not_consume_original(self):
        from task_control import CancellationToken
        from download_errors import DownloadCancelled
        m = self.module()
        token = CancellationToken(); token.cancel()
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)/'source.mp4'
            src.write_bytes(b'original')
            with self.assertRaises(DownloadCancelled):
                m.package_subtitles({},src,{'subtitles':True},{},token,url='https://example.invalid')
            self.assertEqual(src.read_bytes(), b'original')

    def test_danmaku_is_not_excluded_by_manual_track_limit(self):
        m = self.module()
        info = {'subtitles': {**{f'lang{i}':[{'ext':'srt'}] for i in range(30)}, 'danmaku':[{'ext':'xml'}]}}
        selected = m.select_tracks(info, {'subtitles':True,'danmaku':True})
        self.assertEqual(len(selected),25)
        self.assertEqual(selected[-1][2],'danmaku')

    def test_metadata_probe_explicitly_requests_subtitles(self):
        from unittest.mock import patch, MagicMock
        m = self.module()
        fake = MagicMock()
        fake.__enter__.return_value.extract_info.return_value = {'subtitles': {}}
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'source.mp4'; src.write_bytes(b'original')
            with patch.object(m.yt_dlp, 'YoutubeDL', return_value=fake) as ctor, patch.object(m, 'mux_tracks', side_effect=RuntimeError('fixture')):
                m.package_subtitles({},src,{'danmaku':True},{},url='https://example.invalid/video')
            self.assertTrue(ctor.call_args.args[0]['listsubtitles'])
            self.assertEqual(src.read_bytes(),b'original')
