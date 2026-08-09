import threading
import time
import unittest
from urllib.parse import urlparse
from unittest.mock import Mock, patch

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


class FakeResponse:
    status = 206
    headers = {"Content-Range": "bytes 0-9/100"}

    def __init__(self, payload=b"x" * 10):
        self.payload = payload

    def read(self, amount):
        return self.payload[:amount]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class AdaptivePolicyTests(unittest.TestCase):
    def test_small_and_unknown_tasks_skip_all_probes(self):
        for info in (
            {
                "url": "https://a.example/a",
                "filesize": 50 * 1024 * 1024,
            },
            {"url": "https://a.example/a"},
        ):
            with self.subTest(info=info), patch.object(
                acceleration,
                "measure_range",
            ) as measure:
                plan = acceleration.build_acceleration_plan(Mock(), info)

                self.assertFalse(plan.adaptive)
                self.assertEqual(
                    plan.http_chunk_size,
                    10 * 1024 * 1024,
                )
                measure.assert_not_called()

    def test_large_task_chooses_fastest_host_and_chunk(self):
        info = {
            "url": "https://slow.example/a",
            "filesize": 51 * 1024 * 1024,
            acceleration.CDN_CANDIDATES_FIELD: (
                "https://slow.example/a",
                "https://fast.example/a",
            ),
        }
        speeds = {
            ("slow.example", 512 * 1024): 1.0,
            ("fast.example", 512 * 1024): 5.0,
            ("fast.example", 4 * 1024 * 1024): 6.0,
            ("fast.example", 10 * 1024 * 1024): 4.0,
        }

        def fake_measure(ydl, url, size, start=0, headers=None):
            return speeds[(urlparse(url).hostname, size)]

        cache = acceleration.CdnProbeCache(ttl_seconds=1800)
        with patch.object(
            acceleration,
            "measure_range",
            side_effect=fake_measure,
        ):
            plan = acceleration.build_acceleration_plan(
                Mock(),
                info,
                cache=cache,
            )

        self.assertTrue(plan.adaptive)
        self.assertEqual(plan.cdn_host, "fast.example")
        self.assertEqual(plan.http_chunk_size, 4 * 1024 * 1024)

    def test_all_probe_failures_keep_primary_host_and_ten_mib_chunk(self):
        info = {
            "url": "https://primary.example/a",
            "filesize": 60 * 1024 * 1024,
            acceleration.CDN_CANDIDATES_FIELD: (
                "https://primary.example/a",
                "https://backup.example/a",
            ),
        }

        with patch.object(acceleration, "measure_range", return_value=None):
            plan = acceleration.build_acceleration_plan(
                Mock(),
                info,
                cache=acceleration.CdnProbeCache(ttl_seconds=1800),
            )

        self.assertEqual(plan.cdn_host, "primary.example")
        self.assertEqual(plan.http_chunk_size, 10 * 1024 * 1024)

    def test_cache_reuses_value_and_expires_after_30_minutes(self):
        now = [1000.0]
        cache = acceleration.CdnProbeCache(
            ttl_seconds=1800,
            clock=lambda: now[0],
        )
        calls = []

        def factory():
            calls.append("probe")
            return acceleration.CdnChoice(
                "fast.example",
                4 * 1024 * 1024,
            )

        first = cache.get_or_probe(("a", "b"), factory)
        second = cache.get_or_probe(("b", "a"), factory)
        now[0] += 1801
        third = cache.get_or_probe(("a", "b"), factory)

        self.assertEqual(first, second)
        self.assertEqual(second, third)
        self.assertEqual(calls, ["probe", "probe"])

    def test_concurrent_cache_miss_runs_one_probe(self):
        cache = acceleration.CdnProbeCache(ttl_seconds=1800)
        barrier = threading.Barrier(4)
        calls = []
        results = []

        def factory():
            calls.append("probe")
            time.sleep(0.03)
            return acceleration.CdnChoice(
                "fast.example",
                10 * 1024 * 1024,
            )

        def worker():
            barrier.wait()
            results.append(
                cache.get_or_probe(("fast.example",), factory)
            )

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=1)

        self.assertEqual(calls, ["probe"])
        self.assertEqual(len(results), 4)

    def test_measure_range_rejects_non_partial_response(self):
        response = FakeResponse()
        response.status = 200
        ydl = Mock()
        ydl.urlopen.return_value = response

        self.assertIsNone(
            acceleration.measure_range(
                ydl,
                "https://a.example/v",
                10,
            )
        )


if __name__ == "__main__":
    unittest.main()
