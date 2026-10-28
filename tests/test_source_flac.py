"""Real source-mode FLAC extraction from Bilibili-style M4A containers."""

import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import downloader
import yt_dlp


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class SourceFlacContainerTests(unittest.TestCase):
    def _audio_hash(self, path):
        return subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0",
             "-c:a", "copy", "-f", "hash", "-hash", "sha256", "-"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    def test_source_flac_in_m4a_preserves_audio_and_finishes_metadata_and_cover(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.m4a"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                 "sine=frequency=440:duration=0.25", "-ar", "48000", "-ac", "2",
                 "-sample_fmt", "s32", "-c:a", "flac", "-bits_per_raw_sample", "24",
                 "-strict", "-2",
                 "-f", "mp4", str(source)],
                check=True, capture_output=True,
            )
            source_hash = self._audio_hash(source)
            info = {
                "id": "BV1TEST", "title": "Source FLAC regression",
                "uploader": "Test artist", "ext": "m4a", "acodec": "flac",
                "vcodec": "none", "abr": 1649.142,
            }
            profile = downloader._audio_output_profile(info, downloader.SOURCE)
            options = downloader._build_ydl_options(
                downloader.BILIBILI, root, 1, 1,
                media_type=downloader.AUDIO, audio_format=downloader.SOURCE,
                selected_audio=info,
            )
            # This local postprocessing test must not load developer credentials.
            options.pop("cookiefile", None)
            with contextlib.redirect_stdout(io.StringIO()):
                with yt_dlp.YoutubeDL(options) as ydl:
                    processed = ydl.post_process(str(source), info)
                final, profile, version = downloader._finalize_download_output(
                    processed, Path(processed["filepath"]), downloader.AUDIO, profile, 1,
                )

            self.assertEqual(final.suffix, ".flac")
            self.assertIn("Source FLAC", final.name)
            self.assertEqual(profile.requested, downloader.SOURCE)
            self.assertEqual(profile.used, downloader.SOURCE)
            self.assertFalse(profile.fallback)
            self.assertEqual(version, 1)
            self.assertTrue(processed["_cover_embedded"])
            self.assertEqual(self._audio_hash(final), source_hash)
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_streams", "-show_format",
                 "-of", "json", str(final)],
                check=True, capture_output=True, text=True,
            )
            output = json.loads(probe.stdout)
            audio = next(s for s in output["streams"] if s["codec_type"] == "audio")
            self.assertEqual(audio["codec_name"], "flac")
            self.assertEqual(audio["sample_rate"], "48000")
            self.assertEqual(audio["bits_per_raw_sample"], "24")
            tags = {key.lower(): value for key, value in output["format"]["tags"].items()}
            self.assertEqual(tags["title"], info["title"])
            self.assertEqual(tags["artist"], info["uploader"])


if __name__ == "__main__":
    unittest.main()
