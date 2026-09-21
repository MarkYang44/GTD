import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import yt_dlp
from network_settings import configure_direct_network
from downloader import _build_ydl_options
from collection_resolver import _preview_options
from bilibili_acceleration import configure_aria2


class DirectNetworkTests(TestCase):
    def test_process_and_child_environment_disables_stale_proxies(self):
        with patch.dict(os.environ, {'HTTPS_PROXY':'http://127.0.0.1:7897', 'http_proxy':'http://127.0.0.1:7897', 'ALL_PROXY':'socks5://127.0.0.1:7897'}, clear=True):
            configure_direct_network()
            self.assertEqual(dict(os.environ), {'NO_PROXY':'*', 'no_proxy':'*'})

    def test_video_and_preview_explicitly_override_environment_proxy(self):
        with patch.dict(os.environ, {'https_proxy':'http://127.0.0.1:7897'}):
            for platform in ('youtube','instagram','bilibili'):
                for opts in (_preview_options(platform), _build_ydl_options(platform,Path('/tmp'),1,1)):
                    self.assertEqual(opts['proxy'],'')
                    with yt_dlp.YoutubeDL({'proxy':opts['proxy'],'quiet':True}) as ydl:
                        self.assertEqual(ydl.proxies, {'all':'__noproxy__'})

    def test_turbo_has_explicit_direct_arguments(self):
        options={}
        configure_aria2(options,'aria2c')
        args=options['external_downloader_args']['aria2c']
        self.assertIn('--all-proxy=',args)
        self.assertIn('--no-proxy=*',args)
