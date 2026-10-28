"""Recovery policy tests without network access or unowned output cleanup."""

import contextlib
import copy
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import downloader
from download_errors import DownloadCancelled
from task_control import CancellationToken


def media_info():
    return {
        "id": "BV1TEST", "title": "Example", "ext": "mp4",
        "url": "https://original.example/video.m4s",
        "_bilibili_cdn_candidates": (
            "https://original.example/video.m4s",
            "https://selected.example/video.m4s",
            "https://first.example/video.m4s",
            "https://second.example/video.m4s",
        ),
    }


class BilibiliRecoveryTests(unittest.TestCase):
    def test_plan_keeps_optimized_turbo_standard_original_order(self):
        from bilibili_recovery import BilibiliRecovery

        info = media_info()
        original = copy.deepcopy(info)
        profile = downloader._audio_output_profile({"acodec": "aac", "ext": "m4a"}, "source")
        plan = downloader.AccelerationPlan(True, "selected.example", 4 * 1024 * 1024)
        recovery = BilibiliRecovery(info, plan, "turbo", "audio", profile)
        attempts = recovery.attempts
        self.assertEqual([entry[0] for entry in attempts], ["turbo", "standard", "standard"])
        self.assertEqual([entry[2].cdn_host for entry in attempts], ["selected.example", "selected.example", "original.example"])
        self.assertEqual([entry[3] for entry in attempts], [False, True, True])
        self.assertIs(attempts[2][1], info)
        self.assertIsNot(attempts[0][1], info)
        self.assertIsNot(attempts[1][1], attempts[0][1])
        self.assertEqual(info["url"], original["url"])
        self.assertEqual([entry[1]["_audio_output_ext"] for entry in attempts], ["m4a"] * 3)
        self.assertEqual(recovery.backup_hosts, ["first.example", "second.example"])

    def test_recoverable_errors_admit_one_backup_in_order_and_skip_unusable_host(self):
        from bilibili_recovery import BilibiliRecovery

        info = media_info()
        plan = downloader.AccelerationPlan(False, "original.example", 10 * 1024 * 1024)
        attempted_hosts = []

        def apply(info, host):
            attempted_hosts.append(host)
            return host != "selected.example" and downloader.apply_cdn_host(info, host)

        recovery = BilibiliRecovery(info, plan, "standard", "video", None, apply_cdn_host_fn=apply)
        self.assertEqual(attempted_hosts, [])
        error = downloader.yt_dlp.utils.DownloadError("HTTP Error 503")
        self.assertTrue(recovery.retry_after(0, error, None))
        self.assertEqual(attempted_hosts, ["selected.example", "first.example"])
        self.assertEqual(len(recovery.attempts), 2)
        self.assertEqual(recovery.backup_hosts, ["second.example"])
        self.assertTrue(recovery.retry_after(1, error, None))
        self.assertEqual(attempted_hosts, ["selected.example", "first.example", "second.example"])
        self.assertFalse(recovery.retry_after(2, error, None))
        self.assertEqual(info["url"], "https://original.example/video.m4s")

    def test_non_transfer_failure_does_not_admit_backups_or_retry(self):
        from bilibili_recovery import BilibiliRecovery

        apply = Mock()
        recovery = BilibiliRecovery(media_info(), downloader.AccelerationPlan(False, "original.example", 1), "turbo", "video", None, apply_cdn_host_fn=apply)
        self.assertFalse(recovery.retry_after(0, Exception("ffmpeg merge failed"), None))
        apply.assert_not_called()
        self.assertEqual(len(recovery.attempts), 2)

    def test_unchanged_standard_plan_keeps_info_identity_without_copy(self):
        from bilibili_recovery import BilibiliRecovery

        info = media_info()
        deepcopy = Mock(side_effect=AssertionError("unexpected copy"))
        recovery = BilibiliRecovery(info, downloader.AccelerationPlan(False, "original.example", 1), "standard", "video", None, deepcopy_fn=deepcopy)
        self.assertIs(recovery.attempts[0][1], info)
        self.assertEqual(info["_media_type"], "video")
        deepcopy.assert_not_called()

    def test_retry_classifiers_preserve_aria2_access_and_transport_decisions(self):
        from bilibili_recovery import BilibiliRecovery

        for message in ("aria2c exited with code 1", "HTTP Error 403", "HTTP Error 412", "connection reset", "HTTP Error 503"):
            with self.subTest(error=message):
                recovery = BilibiliRecovery(media_info(), downloader.AccelerationPlan(True, "selected.example", 1), "turbo", "video", None)
                self.assertTrue(recovery.retry_after(0, Exception(message), None))
                if "aria2c" in message:
                    self.assertEqual(len(recovery.attempts), 3)
                else:
                    self.assertEqual(len(recovery.attempts), 4)

    def test_cancellation_cleans_only_current_attempt_and_never_admits_backup(self):
        token = CancellationToken()
        metadata = Mock()
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            unrelated = output_dir / "Example.mp4.part"
            unrelated.write_bytes(b"keep")
            other_workspace = downloader._new_attempt_workspace(output_dir)
            other_part = other_workspace / "Other.mp4.part"
            other_part.write_bytes(b"keep")
            attempts = []

            def cancel_attempt(info, options, directory):
                workspace = Path(options["paths"]["temp"])
                attempts.append(workspace)
                (workspace / "owned.part").write_bytes(b"partial")
                token.cancel()
                token.raise_if_cancelled()

            with (
                patch("downloader._extract_bilibili_info", return_value=(metadata, media_info())),
                patch("downloader.aria2c_path", return_value=None),
                patch("downloader.build_acceleration_plan", return_value=downloader.AccelerationPlan(False, "original.example", 1)),
                patch("downloader._process_bilibili_attempt", side_effect=cancel_attempt),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                with self.assertRaises(DownloadCancelled):
                    downloader._download_bilibili("https://b23.tv/example", 1, 1, output_dir, None, "video", "standard", "mp3", cancel_token=token)
            metadata.close.assert_called_once()
            self.assertEqual(len(attempts), 1)
            self.assertFalse(attempts[0].exists())
            self.assertEqual(unrelated.read_bytes(), b"keep")
            self.assertEqual(other_part.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
