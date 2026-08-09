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


class SelectedStreamTests(unittest.TestCase):
    def test_video_size_is_sum_and_audio_size_is_single_stream(self):
        video_info = {"requested_formats": [
            {"url": "https://a.example/v", "filesize": 40 * 1024 * 1024},
            {"url": "https://a.example/a", "filesize_approx": 12 * 1024 * 1024},
        ]}
        audio_info = {
            "url": "https://a.example/a",
            "filesize": 8 * 1024 * 1024,
        }

        self.assertEqual(
            acceleration.selected_size(video_info),
            52 * 1024 * 1024,
        )
        self.assertEqual(
            acceleration.selected_size(audio_info),
            8 * 1024 * 1024,
        )

    def test_unknown_or_non_positive_size_returns_none(self):
        self.assertIsNone(
            acceleration.selected_size({"url": "https://a.example/a"})
        )
        self.assertIsNone(acceleration.selected_size({
            "requested_formats": [
                {"url": "https://a.example/v", "filesize": 10},
                {"url": "https://a.example/a", "filesize": 0},
            ],
        }))

    def test_candidate_hosts_are_unique_capped_and_primary_first(self):
        info = {
            "url": "https://primary.example/v",
            acceleration.CDN_CANDIDATES_FIELD: (
                "https://primary.example/v",
                "https://b.example/v",
                "https://c.example/v",
                "https://d.example/v",
                "https://e.example/v",
            ),
        }

        self.assertEqual(list(acceleration.candidate_hosts(info)), [
            "primary.example",
            "b.example",
            "c.example",
            "d.example",
        ])

    def test_applies_host_to_each_stream_only_when_candidate_exists(self):
        info = {"requested_formats": [
            {
                "url": "https://primary.example/v",
                acceleration.CDN_CANDIDATES_FIELD: (
                    "https://primary.example/v",
                    "https://fast.example/v",
                ),
            },
            {
                "url": "https://primary.example/a",
                acceleration.CDN_CANDIDATES_FIELD: (
                    "https://primary.example/a",
                    "https://fast.example/a",
                ),
            },
        ]}

        changed = acceleration.apply_cdn_host(info, "fast.example")

        self.assertTrue(changed)
        self.assertEqual(
            [fmt["url"] for fmt in info["requested_formats"]],
            ["https://fast.example/v", "https://fast.example/a"],
        )


if __name__ == "__main__":
    unittest.main()
