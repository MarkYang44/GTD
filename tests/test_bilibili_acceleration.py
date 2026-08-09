import unittest
from unittest.mock import Mock

import bilibili_acceleration as acceleration


class BilibiliExtractorAdapterTests(unittest.TestCase):
    def test_enriches_matching_format_with_unique_https_candidates(self):
        play_info = {
            "dash": {
                "video": [{
                    "baseUrl": "https://primary.example/video.m4s?token=1",
                    "backupUrl": [
                        "https://backup.example/video.m4s?token=1",
                        "https://backup.example/video.m4s?token=1",
                        "http://insecure.example/video.m4s",
                    ],
                }],
                "audio": [{
                    "base_url": "https://primary.example/audio.m4s?token=2",
                    "backup_url": ["https://backup.example/audio.m4s?token=2"],
                }],
            },
        }
        formats = [
            {"url": "https://primary.example/video.m4s?token=1", "format_id": "80"},
            {"url": "https://primary.example/audio.m4s?token=2", "format_id": "30280"},
        ]

        result = acceleration.enrich_bilibili_formats(play_info, formats)

        self.assertEqual(result[0][acceleration.CDN_CANDIDATES_FIELD], (
            "https://primary.example/video.m4s?token=1",
            "https://backup.example/video.m4s?token=1",
        ))
        self.assertEqual(result[1][acceleration.CDN_CANDIDATES_FIELD], (
            "https://primary.example/audio.m4s?token=2",
            "https://backup.example/audio.m4s?token=2",
        ))

    def test_unknown_play_info_shape_returns_original_formats(self):
        formats = [{"url": "https://primary.example/video.m4s"}]

        result = acceleration.enrich_bilibili_formats(
            {"dash": "unexpected"},
            formats,
        )

        self.assertIs(result, formats)
        self.assertNotIn(acceleration.CDN_CANDIDATES_FIELD, result[0])

    def test_registers_instance_scoped_bilibili_extractor(self):
        ydl = Mock()

        acceleration.register_bilibili_extractor(ydl)

        extractor = ydl.add_info_extractor.call_args.args[0]
        self.assertIsInstance(extractor, acceleration.BiliBiliIE)


if __name__ == "__main__":
    unittest.main()
