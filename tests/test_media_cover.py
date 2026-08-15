import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from media_cover import CoverOutcome, ensure_media_cover, fallback_cover_paths


EXPECTED_ASSETS = {
    "cover-01.png": "4dff6c05585511a21a0827cb6ef5f5950f33e6d1930b43798f93beb178a6c46c",
    "cover-02.jpg": "1726f1cb05ac075b09b85a4ef12c6ea2f425bbb59b118fedf3f462f7b237dccf",
    "cover-03.jpg": "7f08ab1bdfba35e34aa8254c9080784e5835f115af78a75ed128615bd1c68e4d",
    "cover-04.png": "d2449e6c0fd759462e108a3cf4edbe8e79a35b88cbc52f878921361a94952ddf",
    "cover-05.png": "3077461dc3474b4544eb9b4bf3272298bb9a7b845fd1ce5c98a52a8d6aeabfb7",
    "cover-06.jpg": "e33fe437c47cec137aba8ed929b3d2328376ebb18baa50d030a65bba7935d465",
}


class FallbackCoverResourceTests(unittest.TestCase):
    def test_assets_have_exact_names_hashes_and_image_signatures(self):
        assets = fallback_cover_paths()
        self.assertEqual([path.name for path in assets], list(EXPECTED_ASSETS))
        self.assertEqual(len(assets), 6)
        for path in assets:
            data = path.read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), EXPECTED_ASSETS[path.name])
            self.assertTrue(
                data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff")
            )


class CoverGuardUnitTests(unittest.TestCase):
    def test_unsupported_media_bypasses_chooser(self):
        chooser = Mock(side_effect=AssertionError("chooser must not be called"))
        for suffix in (".wav", ".webm"):
            with self.subTest(suffix=suffix):
                outcome = ensure_media_cover(Path(f"missing{suffix}"), chooser=chooser)
                self.assertEqual(outcome, CoverOutcome(False, "none", None))
        chooser.assert_not_called()

    def test_missing_and_corrupt_supported_media_warn_and_fail_open(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            corrupt = Path(tmpdir) / "broken.mp3"
            corrupt.write_bytes(b"not an mp3")
            for path in (Path(tmpdir) / "missing.mp3", corrupt):
                with self.subTest(path=path), self.assertLogs("media_cover", level="WARNING") as logs:
                    outcome = ensure_media_cover(path)
                self.assertEqual(outcome, CoverOutcome(False, "none", None))
                self.assertIn(str(path), "\n".join(logs.output))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class RealContainerCoverTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def _ffmpeg(self, *args):
        subprocess.run(
            [shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", *args],
            check=True,
            capture_output=True,
        )

    def _audio_fixture(self, suffix):
        target = self.root / f"tone{suffix}"
        codec_args = {
            ".mp3": ["-c:a", "libmp3lame"],
            ".flac": ["-c:a", "flac"],
            ".m4a": ["-c:a", "aac"],
        }[suffix]
        self._ffmpeg(
            "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2", *codec_args, str(target)
        )
        return target

    def _mp4_fixture(self, name="clip.mp4"):
        target = self.root / name
        self._ffmpeg(
            "-f", "lavfi", "-i", "color=c=black:s=32x32:d=0.2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2",
            "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(target),
        )
        return target

    def _probe_streams(self, path):
        completed = subprocess.run(
            [shutil.which("ffprobe"), "-v", "error", "-show_streams", "-of", "json", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)["streams"]

    @staticmethod
    def _media_stream_signature(streams):
        return [
            (stream.get("codec_type"), stream.get("codec_name"))
            for stream in streams
            if not stream.get("disposition", {}).get("attached_pic")
        ]

    def test_inserts_and_redetects_fallback_for_real_audio_containers(self):
        chosen = fallback_cover_paths()[2]
        for suffix in (".mp3", ".flac", ".m4a"):
            with self.subTest(suffix=suffix):
                media = self._audio_fixture(suffix)
                first = ensure_media_cover(media, chooser=lambda _paths: chosen)
                self.assertEqual(first, CoverOutcome(True, "fallback", chosen.name))
                chooser = Mock(side_effect=AssertionError("existing cover must win"))
                second = ensure_media_cover(media, chooser=chooser)
                self.assertEqual(second, CoverOutcome(True, "source", None))
                chooser.assert_not_called()

    def test_existing_cover_bytes_are_unchanged(self):
        from mutagen.id3 import ID3

        media = self._audio_fixture(".mp3")
        chosen = fallback_cover_paths()[0]
        ensure_media_cover(media, chooser=lambda _paths: chosen)
        before = ID3(media).getall("APIC")[0].data
        chooser = Mock(side_effect=AssertionError("chooser must not be called"))
        ensure_media_cover(media, chooser=chooser)
        after = ID3(media).getall("APIC")[0].data
        self.assertEqual(after, before)
        chooser.assert_not_called()

    def test_separate_uncovered_files_can_receive_different_covers(self):
        covers = iter(fallback_cover_paths()[:2])
        outcomes = [
            ensure_media_cover(self._audio_fixture(".mp3"), chooser=lambda _paths: next(covers)),
            ensure_media_cover(self._mp4_fixture("second.mp4"), chooser=lambda _paths: next(covers)),
        ]
        self.assertNotEqual(outcomes[0].fallback_name, outcomes[1].fallback_name)

    def test_mp4_cover_does_not_change_media_streams(self):
        media = self._mp4_fixture()
        before = self._probe_streams(media)
        chooser = Mock(return_value=fallback_cover_paths()[1])
        outcome = ensure_media_cover(media, chooser=chooser)
        after = self._probe_streams(media)
        self.assertEqual(outcome.source, "fallback")
        self.assertEqual(
            self._media_stream_signature(after),
            self._media_stream_signature(before),
        )
        attached = [
            stream for stream in after if stream.get("disposition", {}).get("attached_pic")
        ]
        self.assertEqual(len(attached), 1)
        chooser.assert_called_once()
        self.assertEqual(ensure_media_cover(media).source, "source")


if __name__ == "__main__":
    unittest.main()
