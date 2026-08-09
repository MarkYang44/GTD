import contextlib
import io
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import downloader
import download_errors
import task_control
import yt_dlp


class DownloadErrorMessageTests(unittest.TestCase):
    def test_attempt_workspace_is_forwarded_to_ytdlp_temp_paths(self):
        workspace = Path("/tmp/private-attempt")

        options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            Path("/tmp/output"),
            1,
            1,
            attempt_workspace=workspace,
        )

        self.assertEqual(options["paths"]["temp"], str(workspace))

    def test_ydl_options_use_quiet_logger_for_handled_errors(self):
        options = downloader._build_ydl_options(
            downloader.INSTAGRAM,
            downloader.DOWNLOADS_DIR,
            1,
            1,
        )

        logger = options.get("logger")
        self.assertIsNotNone(logger)
        self.assertTrue(callable(getattr(logger, "error", None)))
        self.assertIsNone(logger.error("suppressed by downloader"))

    def test_youtube_options_enable_js_challenge_solver(self):
        options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            downloader.DOWNLOADS_DIR,
            1,
            1,
        )

        self.assertIn("node", options.get("js_runtimes", {}))
        self.assertIn("ejs:github", options.get("remote_components", []))

    def test_instagram_empty_media_response_points_to_cookie_file(self):
        buffer = io.StringIO()

        with contextlib.redirect_stdout(buffer):
            downloader._handle_download_error(
                "ERROR: [Instagram] abc: Instagram sent an empty media response.",
                downloader.INSTAGRAM,
            )

        output = buffer.getvalue()
        self.assertIn("Instagram 返回了空媒体数据", output)
        self.assertIn("instagram_cookies.txt", output)
        self.assertIn(str(downloader.PROJECT_DIR / "instagram_cookies.txt"), output)

    def test_instagram_http_400_explains_api_rejection(self):
        buffer = io.StringIO()

        with contextlib.redirect_stdout(buffer):
            downloader._handle_download_error(
                "ERROR: [Instagram] abc: Video info extraction failed: HTTP Error 400: Bad Request",
                downloader.INSTAGRAM,
            )

        output = buffer.getvalue()
        self.assertIn("Instagram API 拒绝了该请求", output)
        self.assertIn("重新导出完整 Cookie", output)
        self.assertIn("浏览器中确认该链接能正常播放", output)


class DownloadOutputTemplateTests(unittest.TestCase):
    def test_real_attempt_uses_private_unique_working_filename(self):
        workspace = Path("/tmp/output/.attempts/0123456789abcdef0123456789abcdef")

        options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            Path("/tmp/output"),
            1,
            1,
            attempt_workspace=workspace,
        )

        self.assertIn(".__mvd_0123456789abcdef0123456789abcdef", options["outtmpl"])
        self.assertNotEqual(
            options["outtmpl"],
            str(Path("/tmp/output") / "%(title)s.%(ext)s"),
        )

    def test_concurrent_same_title_video_outputs_are_atomically_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            first = output_dir / "Same [.__mvd_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa].mp4"
            second = output_dir / "Same [.__mvd_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb].mp4"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            barrier = threading.Barrier(2)
            claimed = []

            def finalize(path):
                barrier.wait()
                claimed.append(downloader._finalize_video_output(path, 1))

            threads = [
                threading.Thread(target=finalize, args=(first,)),
                threading.Thread(target=finalize, args=(second,)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(
                {path.name for path in claimed},
                {"Same.mp4", "Same (2).mp4"},
            )
            self.assertEqual(
                {path.read_bytes() for path in claimed},
                {b"first", b"second"},
            )
    def test_instagram_same_title_different_ids_prepare_distinct_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            options = downloader._build_ydl_options(
                downloader.INSTAGRAM,
                output_dir,
                1,
                2,
            )
            with yt_dlp.YoutubeDL(options) as ydl:
                first_path = Path(ydl.prepare_filename({
                    "id": "AAA111",
                    "title": "Video by same.author",
                    "ext": "mp4",
                }))
                second_path = Path(ydl.prepare_filename({
                    "id": "BBB222",
                    "title": "Video by same.author",
                    "ext": "mp4",
                }))

        self.assertNotEqual(first_path, second_path)
        self.assertEqual(first_path.name, "Video by same.author [AAA111].mp4")
        self.assertEqual(second_path.name, "Video by same.author [BBB222].mp4")

    def test_youtube_output_template_keeps_existing_filename(self):
        output_dir = Path("/tmp/downloads")

        options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            output_dir,
            1,
            1,
        )

        self.assertEqual(
            options["outtmpl"],
            str(output_dir / "%(title)s.%(ext)s"),
        )

    def test_video_output_template_includes_redownload_suffix(self):
        options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            Path("/tmp/output"),
            1,
            1,
            output_version=2,
        )

        self.assertIn(" (2).%(ext)s", options["outtmpl"])

    def test_attempt_workspace_cleanup_is_scoped_to_owned_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            first = downloader._new_attempt_workspace(output_dir)
            second = downloader._new_attempt_workspace(output_dir)
            (first / "first.mp4.part").write_bytes(b"first")
            second_part = second / "second.mp4.part"
            second_part.write_bytes(b"second")

            downloader._cleanup_attempt_workspace(first)

            self.assertFalse(first.exists())
            self.assertEqual(second_part.read_bytes(), b"second")


class DownloadAudioOptionsTests(unittest.TestCase):
    def test_completed_audio_wins_if_cancel_arrives_after_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            token = task_control.CancellationToken()
            info = {
                "title": "Song",
                "ext": "m4a",
                "acodec": "aac",
                "abr": 128,
            }

            class FakeYdl:
                def __init__(self, _options):
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

                def extract_info(self, _url, download=False):
                    self.assert_metadata = not download
                    return info

                def process_info(self, _info):
                    (output_dir / "Song.mp3").write_bytes(b"complete")
                    token.cancel()

                def prepare_filename(self, _info):
                    return str(output_dir / "Song.m4a")

            with (
                patch("downloader.ensure_downloads_dir", return_value=output_dir),
                patch("downloader.yt_dlp.YoutubeDL", FakeYdl),
            ):
                result = downloader.download_video(
                    "https://youtu.be/example",
                    platform=downloader.YOUTUBE,
                    media_type=downloader.AUDIO,
                    cancel_token=token,
                    raise_errors=True,
                )

            self.assertIsNotNone(result)
            self.assertEqual(result["media_type"], downloader.AUDIO)
            self.assertTrue(Path(result["filepath"]).is_file())

    def test_unknown_source_codec_is_rejected_instead_of_transcoded(self):
        profile = downloader._audio_output_profile(
            {"acodec": "mystery-codec", "ext": "webm"},
            downloader.SOURCE,
        )

        with self.assertRaises(download_errors.DownloadFailure) as caught:
            downloader._ensure_source_copy_supported(
                {"acodec": "mystery-codec", "ext": "webm"},
                profile,
            )

        self.assertEqual(caught.exception.info.error_code, "FORMAT_UNAVAILABLE")
    def test_audio_rename_never_overwrites_existing_quality_target(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Song.mp3"
            source.write_bytes(b"new")
            profile = downloader.AudioOutputProfile(
                downloader.MP3,
                downloader.MP3,
                False,
                "AAC",
                128,
                "mp3",
                True,
            )
            occupied = Path(directory) / "Song [MP3 V0 · 源AAC 128kbps].mp3"
            occupied.write_bytes(b"original")

            target = downloader._rename_audio_output(source, profile)

            self.assertEqual(occupied.read_bytes(), b"original")
            self.assertEqual(target.read_bytes(), b"new")
            self.assertEqual(target.name, "Song [MP3 V0 · 源AAC 128kbps] (2).mp3")

    def test_source_profile_uses_actual_output_extension(self):
        profile = downloader.AudioOutputProfile(
            downloader.SOURCE,
            downloader.SOURCE,
            False,
            "Opus",
            128,
            "webm",
            False,
        )

        actual = downloader._profile_for_output_path(profile, Path("Song.opus"))

        self.assertEqual(actual.output_ext, "opus")
        self.assertEqual(downloader._audio_format_name(actual), "SOURCE OPUS")
    def test_audio_quality_label_precedes_redownload_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Song (2).mp3"
            path.touch()
            profile = downloader.AudioOutputProfile(
                downloader.MP3,
                downloader.MP3,
                False,
                "AAC",
                128,
                "mp3",
                True,
            )

            target = downloader._rename_audio_output(
                path,
                profile,
                output_version=2,
            )

            self.assertEqual(
                target.name,
                "Song [MP3 V0 · 源AAC 128kbps] (2).mp3",
            )
    def test_source_audio_preserves_selected_codec_without_quality_setting(self):
        info = {"acodec": "opus", "ext": "webm", "abr": 160}

        profile = downloader._audio_output_profile(info, downloader.SOURCE)
        options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            Path("/tmp/output"),
            1,
            1,
            media_type=downloader.AUDIO,
            audio_format=downloader.SOURCE,
            selected_audio=info,
        )
        extractor = options["postprocessors"][0]

        self.assertEqual(profile.used, downloader.SOURCE)
        self.assertEqual(profile.output_ext, "webm")
        self.assertEqual(extractor["preferredcodec"], "best")
        self.assertNotIn("preferredquality", extractor)
        self.assertEqual(
            downloader._audio_quality_label(profile),
            "Source Opus · 160kbps",
        )

    def test_wav_decodes_best_audio_without_claiming_lossless_source(self):
        info = {"acodec": "mp4a.40.2", "ext": "m4a", "abr": 128}

        profile = downloader._audio_output_profile(info, downloader.WAV)
        options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            Path("/tmp/output"),
            1,
            1,
            media_type=downloader.AUDIO,
            audio_format=downloader.WAV,
            selected_audio=info,
        )

        self.assertEqual(profile.used, downloader.WAV)
        self.assertEqual(profile.output_ext, "wav")
        self.assertEqual(
            options["postprocessors"][0]["preferredcodec"],
            "wav",
        )
        self.assertEqual(
            downloader._audio_quality_label(profile),
            "WAV PCM · 源AAC 128kbps",
        )

    def test_source_webm_and_wav_skip_unsupported_thumbnail_embedding(self):
        source_options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            Path("/tmp/output"),
            1,
            1,
            media_type=downloader.AUDIO,
            audio_format=downloader.SOURCE,
            selected_audio={"acodec": "opus", "ext": "webm"},
        )
        wav_options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            Path("/tmp/output"),
            1,
            1,
            media_type=downloader.AUDIO,
            audio_format=downloader.WAV,
            selected_audio={"acodec": "aac", "ext": "m4a"},
        )

        self.assertNotIn(
            "EmbedThumbnail",
            [processor["key"] for processor in source_options["postprocessors"]],
        )
        self.assertNotIn(
            "EmbedThumbnail",
            [processor["key"] for processor in wav_options["postprocessors"]],
        )
        self.assertFalse(source_options["writethumbnail"])
        self.assertFalse(wav_options["writethumbnail"])

    def test_source_m4a_keeps_supported_thumbnail_embedding(self):
        options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            Path("/tmp/output"),
            1,
            1,
            media_type=downloader.AUDIO,
            audio_format=downloader.SOURCE,
            selected_audio={"acodec": "aac", "ext": "m4a"},
        )

        self.assertIn(
            "EmbedThumbnail",
            [processor["key"] for processor in options["postprocessors"]],
        )
        self.assertTrue(options["writethumbnail"])

    def test_flac_source_builds_mp3_profile_and_quality_filename(self):
        info = {"vcodec": "none", "acodec": "flac", "abr": 1521.267}

        profile = downloader._audio_output_profile(info, downloader.MP3)

        self.assertEqual(profile.used, downloader.MP3)
        self.assertFalse(profile.fallback)
        self.assertEqual(profile.source_acodec, "FLAC")
        self.assertEqual(profile.source_abr_kbps, 1521)
        self.assertEqual(
            downloader._audio_quality_label(profile),
            "MP3 V0 · 源FLAC 1521kbps",
        )

    def test_requested_flac_uses_real_flac_and_falls_back_for_aac(self):
        lossless = downloader._audio_output_profile(
            {"vcodec": "none", "acodec": "flac", "tbr": 1521.267},
            downloader.FLAC,
        )
        fallback = downloader._audio_output_profile(
            {"vcodec": "none", "acodec": "mp4a.40.2", "abr": 245.75},
            downloader.FLAC,
        )

        self.assertEqual(lossless.used, downloader.FLAC)
        self.assertFalse(lossless.fallback)
        self.assertEqual(
            downloader._audio_quality_label(lossless),
            "FLAC Lossless · 1521kbps",
        )
        self.assertEqual(fallback.used, downloader.MP3)
        self.assertTrue(fallback.fallback)
        self.assertEqual(fallback.source_acodec, "AAC")

    def test_unknown_source_fields_do_not_leak_placeholders(self):
        profile = downloader._audio_output_profile({}, downloader.MP3)

        label = downloader._audio_quality_label(profile)

        self.assertEqual(label, "MP3 V0")
        self.assertNotIn("NA", label)
        self.assertNotIn("None", label)

    def test_audio_output_is_renamed_after_platform_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "Example [BV123].mp3"
            source.touch()
            profile = downloader._audio_output_profile(
                {"acodec": "flac", "abr": 1521.267},
                downloader.MP3,
            )

            actual = downloader._rename_audio_output(source, profile)

            self.assertEqual(
                actual.name,
                "Example [BV123] [MP3 V0 · 源FLAC 1521kbps].mp3",
            )
            self.assertTrue(actual.is_file())
            self.assertFalse(source.exists())

    def test_audio_options_select_best_audio_and_extract_highest_quality_mp3(self):
        output_dir = Path("/tmp/downloads")

        options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            output_dir,
            1,
            1,
            media_type=downloader.AUDIO,
        )

        self.assertEqual(options["format"], "bestaudio/best")
        self.assertEqual(
            options["postprocessors"],
            [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "0",
                },
                {
                    "key": "FFmpegMetadata",
                    "add_metadata": True,
                    "add_chapters": False,
                    "add_infojson": False,
                },
                {
                    "key": "EmbedThumbnail",
                    "already_have_thumbnail": False,
                },
            ],
        )
        self.assertTrue(options["writethumbnail"])
        self.assertEqual(
            options["outtmpl"],
            str(output_dir / "%(title)s.%(ext)s"),
        )

    def test_flac_options_select_flac_first_and_copy_to_flac(self):
        options = downloader._build_ydl_options(
            downloader.BILIBILI,
            Path("/tmp/downloads"),
            1,
            1,
            media_type=downloader.AUDIO,
            audio_format=downloader.FLAC,
        )

        self.assertEqual(
            options["format"],
            "bestaudio[acodec^=flac]/bestaudio/best",
        )
        self.assertEqual(
            options["postprocessors"][0],
            {"key": "FFmpegExtractAudio", "preferredcodec": "flac"},
        )
        self.assertTrue(options["writethumbnail"])

    def test_instagram_audio_keeps_id_suffix_in_output_template(self):
        output_dir = Path("/tmp/downloads")

        options = downloader._build_ydl_options(
            downloader.INSTAGRAM,
            output_dir,
            1,
            1,
            media_type=downloader.AUDIO,
        )

        self.assertEqual(
            options["outtmpl"],
            str(output_dir / "%(title)s [%(id)s].%(ext)s"),
        )

    def test_audio_output_path_resolves_postprocessed_mp3(self):
        class FakeYdl:
            def prepare_filename(self, info):
                return str(output_dir / "Example.webm")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            expected = output_dir / "Example.mp3"
            expected.touch()

            actual = downloader._resolve_output_path(
                FakeYdl(),
                {"title": "Example", "ext": "webm"},
                output_dir,
                media_type=downloader.AUDIO,
            )

        self.assertEqual(actual, expected)

    def test_audio_output_path_resolves_postprocessed_flac(self):
        class FakeYdl:
            def prepare_filename(self, info):
                return str(output_dir / "Example.m4a")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            expected = output_dir / "Example.flac"
            expected.touch()

            actual = downloader._resolve_output_path(
                FakeYdl(),
                {"title": "Example", "ext": "m4a"},
                output_dir,
                media_type=downloader.AUDIO,
                audio_format=downloader.FLAC,
            )

        self.assertEqual(actual, expected)

    def test_audio_output_path_resolves_source_extension_from_profile(self):
        class FakeYdl:
            def prepare_filename(self, info):
                return str(output_dir / "Example.webm")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            expected = output_dir / "Example.webm"
            expected.touch()
            profile = downloader._audio_output_profile(
                {"acodec": "opus", "ext": "webm"},
                downloader.SOURCE,
            )

            actual = downloader._resolve_output_path(
                FakeYdl(),
                {"title": "Example", "ext": "webm"},
                output_dir,
                media_type=downloader.AUDIO,
                audio_format=downloader.SOURCE,
                audio_profile=profile,
            )

        self.assertEqual(actual, expected)


class DownloadProgressHookTests(unittest.TestCase):
    def test_finished_postprocessor_hook_preserves_atomic_final_output(self):
        token = task_control.CancellationToken()
        hook = downloader._make_cancel_hook(token)
        token.cancel()

        hook({"status": "finished"})

        with self.assertRaises(download_errors.DownloadCancelled):
            hook({"status": "started"})

    def test_progress_hook_raises_dedicated_cancel_exception(self):
        token = task_control.CancellationToken()
        hook = downloader._make_progress_hook(1, 1, cancel_token=token)
        token.cancel()

        with self.assertRaises(download_errors.DownloadCancelled):
            hook(
                {
                    "status": "downloading",
                    "downloaded_bytes": 1,
                    "total_bytes": 2,
                }
            )
    def test_progress_hook_emits_complete_line_for_parallel_cli_output(self):
        hook = downloader._make_progress_hook(2, 3)
        buffer = io.StringIO()

        with contextlib.redirect_stdout(buffer):
            hook({
                "status": "downloading",
                "_percent_str": "25.0%",
                "speed": 1024 * 1024,
                "eta": 10,
            })

        output = buffer.getvalue()
        self.assertTrue(output.endswith("\n"))
        self.assertNotIn("\r", output)
        self.assertIn("[2/3]", output)

    def test_progress_snapshot_removes_ansi_color_codes_from_percent(self):
        snapshot = downloader._extract_progress_snapshot({
            "_percent_str": "\x1b[0;94m100.0%\x1b[0m",
            "speed": 1024 * 1024,
            "eta": 0,
        })

        self.assertEqual(snapshot["percent_text"], "100.0%")
        self.assertNotIn("\x1b", snapshot["percent_text"])

    def test_ydl_options_emit_speed_and_eta_progress_for_web_callback(self):
        events = []

        options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            downloader.DOWNLOADS_DIR,
            1,
            1,
            progress_callback=lambda event, data: events.append((event, data)),
        )

        hook = options["progress_hooks"][0]
        with contextlib.redirect_stdout(io.StringIO()):
            hook({
                "status": "downloading",
                "_percent_str": " 12.3%",
                "speed": 2.5 * 1024 * 1024,
                "eta": 65,
            })

        self.assertEqual(len(events), 1)
        event, data = events[0]
        self.assertEqual(event, "progress")
        self.assertEqual(data["percent_text"], "12.3%")
        self.assertEqual(data["speed_mbps"], 2.5)
        self.assertEqual(data["speed_text"], "2.50 MB/s")
        self.assertEqual(data["eta_text"], "01:05")

    def test_ydl_options_progress_uses_unknown_text_when_speed_or_eta_missing(self):
        events = []

        options = downloader._build_ydl_options(
            downloader.INSTAGRAM,
            downloader.DOWNLOADS_DIR,
            1,
            1,
            progress_callback=lambda event, data: events.append((event, data)),
        )

        hook = options["progress_hooks"][0]
        with contextlib.redirect_stdout(io.StringIO()):
            hook({"status": "downloading"})

        self.assertEqual(events[0][0], "progress")
        self.assertEqual(events[0][1]["speed_text"], "计算中")
        self.assertEqual(events[0][1]["eta_text"], "计算中")


if __name__ == "__main__":
    unittest.main()
