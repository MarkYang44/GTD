"""Characterization of platform/media options and the extracted builder seam."""

import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import Mock, patch

import audio_output
import downloader
from task_control import CancellationToken


class DownloadOptionsTests(unittest.TestCase):
    def test_platform_media_matrix_keeps_selection_and_postprocessors(self):
        cases = (
            ("video", "mp3", None, None),
            ("audio", "mp3", "bestaudio/best", "mp3"),
            ("audio", "flac", "bestaudio[acodec^=flac]/bestaudio/best", "flac"),
            ("audio", "source", "bestaudio[acodec!=none]/best[acodec!=none]", "m4a"),
            ("audio", "wav", "bestaudio[acodec!=none]/best[acodec!=none]", "wav"),
        )
        for platform in ("youtube", "instagram", "bilibili"):
            for media_type, audio_format, selector, codec in cases:
                with self.subTest(platform=platform, media=media_type, audio=audio_format):
                    selected = {"acodec": "flac", "ext": "flac"} if audio_format == "flac" else {"acodec": "aac", "ext": "m4a"}
                    with (
                        patch("downloader._find_cookie_file", return_value=None),
                        patch("downloader._node_path", return_value=None),
                    ):
                        options = downloader._build_ydl_options(
                            platform, Path("output"), 1, 2,
                            media_type=media_type, audio_format=audio_format,
                            selected_audio=selected, speed_mode="turbo",
                            aria2_executable="aria2c",
                        )
                    self.assertEqual(options["proxy"], "")
                    self.assertFalse(options["overwrites"])
                    self.assertFalse(options["writesubtitles"])
                    self.assertEqual(len(options["progress_hooks"]), 1)
                    self.assertEqual(len(options["postprocessor_hooks"]), 1)
                    self.assertEqual("external_downloader" in options, platform == "bilibili")
                    self.assertEqual("http_chunk_size" in options, platform == "bilibili")
                    if media_type == "audio":
                        self.assertEqual(options["format"], selector)
                        expected = audio_output.audio_postprocessors(audio_output.audio_output_profile(selected, audio_format))
                        self.assertEqual(options["postprocessors"], expected)
                        self.assertNotIn("merge_output_format", options)
                    else:
                        self.assertEqual(options["merge_output_format"], "mp4")
                        self.assertTrue(options["writethumbnail"])
                        if platform == "instagram":
                            self.assertEqual(options["postprocessors"], [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}])
                        else:
                            self.assertEqual(options["format"], "bestvideo+bestaudio/best")

    def test_adapter_groups_preferences_and_patch_points_in_frozen_records(self):
        import download_options

        with (
            patch.object(download_options, "build_ydl_options", return_value={}) as builder,
            patch("downloader._make_progress_hook") as progress_factory,
        ):
            downloader._build_ydl_options(
                "bilibili", Path("output"), 1, 1,
                media_type="audio", audio_format="wav", speed_mode="turbo",
            )
        arguments = builder.call_args.kwargs
        self.assertIn("preferences", arguments)
        self.assertIn("hooks", arguments)
        preferences = arguments["preferences"]
        self.assertEqual(
            (preferences.media_type, preferences.audio_format, preferences.speed_mode),
            ("audio", "wav", "turbo"),
        )
        self.assertIs(arguments["hooks"].make_progress_hook, progress_factory)
        with self.assertRaises(FrozenInstanceError):
            preferences.speed_mode = "standard"
        with self.assertRaises(FrozenInstanceError):
            arguments["hooks"].make_progress_hook = Mock()

    def test_builder_retains_downloader_patch_points_and_hook_order(self):
        import download_options

        progress = Mock()
        cancel_hook = Mock()
        postprocess = Mock()
        token = CancellationToken()
        callback = Mock()
        workspace = Path("output/.attempts/owned")
        with (
            patch("downloader._validate_output_version") as validate,
            patch("downloader._attempt_output_template", return_value="owned-template") as template,
            patch("downloader._make_progress_hook", return_value=progress) as progress_factory,
            patch("downloader._make_cancel_hook", return_value=cancel_hook) as cancel_factory,
            patch("downloader._make_postprocessor_status_hook", return_value=postprocess) as status_factory,
            patch("downloader._find_cookie_file", return_value=Path("cookies.txt")),
            patch.object(download_options, "build_ydl_options", wraps=download_options.build_ydl_options) as builder,
        ):
            options = downloader._build_ydl_options(
                "bilibili", Path("output"), 2, 3, progress_callback=callback,
                cancel_token=token, output_version=4, attempt_workspace=workspace,
            )
        builder.assert_called_once()
        validate.assert_called_once_with(4)
        template.assert_called_once_with("bilibili", Path("output"), workspace)
        progress_factory.assert_called_once_with(2, 3, callback, token, "video", "mp3")
        cancel_factory.assert_called_once_with(token)
        status_factory.assert_called_once_with(2, 3, callback, "video", "mp3")
        self.assertEqual(options["progress_hooks"], [progress])
        self.assertEqual(options["postprocessor_hooks"], [cancel_hook, postprocess])
        self.assertEqual(options["cookiefile"], "cookies.txt")
        self.assertEqual(options["paths"], {"temp": str(workspace)})
        self.assertEqual(options["outtmpl"], "owned-template")


if __name__ == "__main__":
    unittest.main()
