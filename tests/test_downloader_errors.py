import contextlib
import inspect
import io
import tempfile
import threading
import time
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import Mock, patch

import downloader
import audio_output
import download_progress
import output_files
import download_errors
import task_control
import yt_dlp


class DownloadErrorMessageTests(unittest.TestCase):
    def test_audio_output_module_has_fixed_profiles_labels_and_postprocessors(self):
        cases = [
            (
                {"acodec": "flac", "ext": "flac", "abr": 1521.267},
                downloader.MP3,
                audio_output.AudioOutputProfile(
                    downloader.MP3, downloader.MP3, False, "FLAC", 1521, "mp3", True
                ),
                "MP3 V0 · 源FLAC 1521kbps",
                "mp3",
                "0",
                True,
            ),
            (
                {"acodec": "flac", "ext": "flac", "abr": 1521.267},
                downloader.FLAC,
                audio_output.AudioOutputProfile(
                    downloader.FLAC, downloader.FLAC, False, "FLAC", 1521, "flac", True
                ),
                "FLAC Lossless · 1521kbps",
                "flac",
                None,
                True,
            ),
            (
                {"acodec": "mp4a.40.2", "ext": "m4a", "abr": 245.75},
                downloader.FLAC,
                audio_output.AudioOutputProfile(
                    downloader.FLAC, downloader.MP3, True, "AAC", 246, "mp3", True
                ),
                "MP3 V0 · 源AAC 246kbps",
                "mp3",
                "0",
                True,
            ),
            (
                {"acodec": "opus", "ext": "webm", "abr": 160},
                downloader.SOURCE,
                audio_output.AudioOutputProfile(
                    downloader.SOURCE, downloader.SOURCE, False, "Opus", 160, "webm", False
                ),
                "Source Opus · 160kbps",
                "best",
                None,
                False,
            ),
            (
                {"acodec": "mp4a.40.2", "ext": "m4a", "abr": 128},
                downloader.WAV,
                audio_output.AudioOutputProfile(
                    downloader.WAV, downloader.WAV, False, "AAC", 128, "wav", False
                ),
                "WAV PCM · 源AAC 128kbps",
                "wav",
                None,
                False,
            ),
        ]

        for info, requested, expected, label, codec, quality, embeds_cover in cases:
            with self.subTest(requested=requested):
                actual = audio_output.audio_output_profile(info, requested)
                postprocessors = audio_output.audio_postprocessors(actual)
                self.assertEqual(actual, expected)
                self.assertEqual(audio_output.audio_quality_label(actual), label)
                self.assertEqual(postprocessors[0]["preferredcodec"], codec)
                self.assertEqual(postprocessors[1], {
                    "key": "FFmpegMetadata",
                    "add_metadata": True,
                    "add_chapters": False,
                    "add_infojson": False,
                })
                if quality is None:
                    self.assertNotIn("preferredquality", postprocessors[0])
                else:
                    self.assertEqual(postprocessors[0]["preferredquality"], quality)
                self.assertEqual(
                    "EmbedThumbnail" in [item["key"] for item in postprocessors],
                    embeds_cover,
                )

    def test_audio_output_module_source_validation_and_final_path_profile_contract(self):
        source_info = {"acodec": "opus", "ext": "webm", "abr": 160}
        profile = audio_output.audio_output_profile(source_info, downloader.SOURCE)

        self.assertEqual(
            audio_output.selected_audio_info(
                {"requested_formats": [{"acodec": "none"}, source_info]}
            ),
            source_info,
        )
        self.assertIsNone(audio_output.ensure_source_copy_supported(source_info, profile))
        self.assertEqual(
            audio_output.profile_for_output_path(profile, Path("Song.opus")),
            audio_output.AudioOutputProfile(
                downloader.SOURCE, downloader.SOURCE, False, "Opus", 160, "opus", True
            ),
        )

    def test_download_progress_module_has_fixed_ansi_size_eta_and_stage_contracts(self):
        payload = {
            "_percent_str": "\x1b[0;94m12.3%\x1b[0m",
            "speed": 2.5 * 1024 * 1024,
            "eta": 65,
            "total_bytes_estimate": 750 * 1024 * 1024,
        }

        self.assertEqual(
            download_progress.extract_progress_snapshot(payload),
            {
                "percent_text": "12.3%",
                "speed_mbps": 2.5,
                "speed_text": "2.50 MB/s",
                "eta_text": "01:05",
                "total_size_bytes": 750 * 1024 * 1024,
                "total_size_text": "750.00 MiB",
                "total_size_is_estimate": True,
            },
        )
        self.assertEqual(
            download_progress.postprocessing_preparation(downloader.AUDIO, downloader.MP3),
            {
                "stage": "preparing",
                "stage_text": "正在准备将完整音轨转码为 MP3 V0。",
                "detail_text": "随后还会写入元数据与封面；长音频可能需要数十秒至数分钟。",
            },
        )
        expected_stages = [
            ("ExtractAudio", downloader.AUDIO, downloader.MP3, (
                "transcoding_audio", "正在将完整音轨转码为 MP3 V0…", "长音频需要完整解码并重新编码，可能持续数十秒至数分钟。"
            )),
            ("ExtractAudio", downloader.AUDIO, downloader.WAV, (
                "decoding_audio", "正在将完整音轨解码为 WAV…", "长音频需要完整解码，期间没有下载进度属于正常现象。"
            )),
            ("ExtractAudio", downloader.AUDIO, downloader.FLAC, (
                "extracting_audio", "正在提取并整理音轨…", "大文件需要读取并写入完整音轨，请耐心等待。"
            )),
            ("EmbedThumbnail", downloader.AUDIO, downloader.MP3, (
                "embedding_thumbnail", "正在嵌入封面…", "程序正在把封面写入最终媒体文件。"
            )),
            ("Metadata", downloader.AUDIO, downloader.MP3, (
                "writing_metadata", "正在写入媒体信息…", "程序正在保存标题、作者和其他媒体标签。"
            )),
            ("Merger", downloader.VIDEO, downloader.MP3, (
                "merging_streams", "正在合并视频与音频…", "高分辨率或长视频需要读取并写入完整媒体流。"
            )),
            ("Remux", downloader.VIDEO, downloader.MP3, (
                "remuxing_video", "正在整理视频封装…", "程序正在生成兼容性更好的最终视频文件。"
            )),
            ("MoveFiles", downloader.VIDEO, downloader.MP3, (
                "finalizing", "正在整理最终文件…", "处理即将完成，程序正在确认文件名与保存位置。"
            )),
            ("unknown", downloader.VIDEO, downloader.MP3, (
                "postprocessing", "正在处理媒体文件…", "程序仍在正常工作，请保持窗口打开。"
            )),
        ]
        for postprocessor, media_type, audio_format, expected in expected_stages:
            with self.subTest(postprocessor=postprocessor, audio_format=audio_format):
                actual = download_progress.postprocessor_stage(
                    postprocessor, media_type, audio_format
                )
                self.assertEqual(actual, expected)

    def test_download_progress_module_accepts_protocol_only_cancel_token(self):
        class ProtocolOnlyToken:
            def __init__(self):
                self.calls = 0

            def raise_if_cancelled(self):
                self.calls += 1
                raise RuntimeError("cancelled through protocol")

        token = ProtocolOnlyToken()
        hook = download_progress.make_progress_hook(1, 1, cancel_token=token)

        with self.assertRaisesRegex(RuntimeError, "cancelled through protocol"):
            hook({"status": "downloading"})

        self.assertEqual(token.calls, 1)

    def test_audio_output_profile_is_downloader_compatible_and_frozen(self):
        self.assertIs(downloader.AudioOutputProfile, audio_output.AudioOutputProfile)
        profile = audio_output.audio_output_profile({}, downloader.MP3)

        with self.assertRaises(FrozenInstanceError):
            profile.used = downloader.FLAC

    def test_downloader_progress_snapshot_preserves_component_patch_seams(self):
        with (
            patch.object(downloader, "_format_download_speed", return_value=(7.5, "patched speed")) as speed,
            patch.object(downloader, "_strip_ansi", return_value="patched percent") as strip,
            patch.object(downloader, "_progress_total_size", return_value=(9, True)) as size,
            patch.object(downloader, "_format_eta", return_value="patched eta") as eta,
            patch.object(downloader, "_format_size_bytes", return_value="patched size") as format_size,
        ):
            snapshot = downloader._extract_progress_snapshot({"speed": 1, "eta": 2})

        self.assertEqual(snapshot, {
            "percent_text": "patched percent",
            "speed_mbps": 7.5,
            "speed_text": "patched speed",
            "eta_text": "patched eta",
            "total_size_bytes": 9,
            "total_size_text": "patched size",
            "total_size_is_estimate": True,
        })
        for mocked in (speed, strip, size, eta, format_size):
            mocked.assert_called_once()

    def test_downloader_progress_hook_preserves_composite_patch_seams(self):
        snapshot = {
            "percent_text": "patched percent", "speed_mbps": 1.0,
            "speed_text": "patched speed", "eta_text": "patched eta",
            "total_size_bytes": None, "total_size_text": "",
            "total_size_is_estimate": False,
        }
        preparation = {"stage": "patched", "stage_text": "patched stage", "detail_text": "patched detail"}
        events = []
        with (
            patch.object(downloader, "_extract_progress_snapshot", return_value=snapshot) as extract,
            patch.object(downloader, "_postprocessing_preparation", return_value=preparation) as prepare,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            hook = downloader._make_progress_hook(
                1, 1, progress_callback=lambda event, data: events.append((event, data))
            )
            hook({"status": "downloading"})
            hook({"status": "finished"})

        extract.assert_called_once()
        prepare.assert_called_once_with(downloader.VIDEO, downloader.MP3)
        self.assertEqual(events, [("progress", snapshot), ("postprocessing", preparation)])

    def test_downloader_progress_hook_resolves_patched_helpers_after_creation(self):
        events = []
        hook = downloader._make_progress_hook(
            1, 1, progress_callback=lambda event, data: events.append((event, data))
        )
        snapshot = {
            "percent_text": "late percent", "speed_mbps": 3.0,
            "speed_text": "late speed", "eta_text": "late eta",
            "total_size_bytes": None, "total_size_text": "",
            "total_size_is_estimate": False,
        }
        preparation = {"stage": "late", "stage_text": "late stage", "detail_text": "late detail"}

        with (
            patch.object(downloader, "_extract_progress_snapshot", return_value=snapshot) as extract,
            patch.object(downloader, "_postprocessing_preparation", return_value=preparation) as prepare,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            hook({"status": "downloading"})
            hook({"status": "finished"})

        extract.assert_called_once()
        prepare.assert_called_once_with(downloader.VIDEO, downloader.MP3)
        self.assertEqual(events, [("progress", snapshot), ("postprocessing", preparation)])

    def test_downloader_postprocessor_hook_preserves_stage_patch_seam(self):
        stage = ("patched", "patched stage", "patched detail")
        events = []
        with (
            patch.object(downloader, "_postprocessor_stage", return_value=stage) as stage_helper,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            hook = downloader._make_postprocessor_status_hook(
                1, 1, progress_callback=lambda event, data: events.append((event, data))
            )
            hook({"status": "started", "postprocessor": "anything"})

        stage_helper.assert_called_once_with("anything", downloader.VIDEO, downloader.MP3)
        self.assertEqual(events, [("postprocessing", {
            "stage": "patched", "stage_text": "patched stage", "detail_text": "patched detail"
        })])

    def test_downloader_postprocessor_hook_resolves_patched_stage_after_creation(self):
        events = []
        hook = downloader._make_postprocessor_status_hook(
            1, 1, progress_callback=lambda event, data: events.append((event, data))
        )
        stage = ("late", "late stage", "late detail")

        with (
            patch.object(downloader, "_postprocessor_stage", return_value=stage) as stage_helper,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            hook({"status": "started", "postprocessor": "anything"})

        stage_helper.assert_called_once_with("anything", downloader.VIDEO, downloader.MP3)
        self.assertEqual(events, [("postprocessing", {
            "stage": "late", "stage_text": "late stage", "detail_text": "late detail"
        })])

    def test_downloader_cancel_hook_retains_compatibility_metadata(self):
        hook_factory = downloader._make_cancel_hook
        parameter = inspect.signature(hook_factory).parameters["cancel_token"]

        self.assertEqual(tuple(inspect.signature(hook_factory).parameters), ("cancel_token",))
        self.assertIs(parameter.annotation, task_control.CancellationToken)
        self.assertEqual(hook_factory.__name__, "_make_cancel_hook")
        self.assertEqual(hook_factory.__module__, "downloader")

    def test_downloader_audio_profile_and_source_validation_preserve_patch_seams(self):
        selected = {"acodec": "ignored", "ext": "m4a", "abr": 123}
        with (
            patch.object(downloader, "_selected_audio_info", return_value=selected) as selected_helper,
            patch.object(downloader, "_display_audio_codec", return_value="PATCHED") as display,
        ):
            profile = downloader._audio_output_profile({}, downloader.MP3)

        selected_helper.assert_called_once_with({})
        display.assert_called_once_with("ignored")
        self.assertEqual(profile.source_acodec, "PATCHED")

        source_profile = audio_output.AudioOutputProfile(
            downloader.SOURCE, downloader.SOURCE, False, "Opus", 160, "opus", True
        )
        with patch.object(
            downloader, "_selected_audio_info", return_value={"acodec": "opus"}
        ) as source_selected:
            self.assertIsNone(downloader._ensure_source_copy_supported({}, source_profile))

        source_selected.assert_called_once_with({})
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
    def test_downloader_claim_helper_keeps_patchable_version_claim_seam(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "private.mp4"
            expected = Path(directory) / "final.mp4"
            source.write_bytes(b"media")
            with patch.object(
                downloader,
                "_claim_final_output_with_version",
                return_value=(expected, 2),
            ) as claim:
                self.assertEqual(
                    downloader._claim_final_output(source, "final", 2),
                    expected,
                )

            claim.assert_called_once_with(source, "final", 2)

    def test_downloader_version_claim_keeps_patchable_validator_seam(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Clip [.__mvd_token].mp4"
            source.write_bytes(b"media")
            with patch.object(downloader, "_validate_output_version") as validate:
                target, version = downloader._claim_final_output_with_version(
                    source,
                    "Clip",
                    1,
                )

        validate.assert_called_once_with(1)
        self.assertEqual(target.name, "Clip.mp4")
        self.assertEqual(version, 1)

    def test_output_files_cleans_private_source_when_link_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Clip [.__mvd_token].mp4"
            target = Path(directory) / "Clip.mp4"
            source.write_bytes(b"media")

            with patch.object(output_files.os, "link", side_effect=OSError("link failed")):
                with self.assertRaisesRegex(OSError, "link failed"):
                    output_files.claim_final_output_with_version(source, "Clip", 1)

            self.assertFalse(source.exists())
            self.assertFalse(target.exists())

    def test_output_files_rolls_back_new_link_when_private_source_unlink_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Clip [.__mvd_token].mp4"
            target = Path(directory) / "Clip.mp4"
            source.write_bytes(b"media")
            original_unlink = Path.unlink

            def fail_source_unlink(path, *args, **kwargs):
                if path == source:
                    raise OSError("source unlink failed")
                return original_unlink(path, *args, **kwargs)

            with patch.object(Path, "unlink", new=fail_source_unlink):
                with self.assertRaisesRegex(OSError, "source unlink failed"):
                    output_files.claim_final_output_with_version(source, "Clip", 1)

            self.assertTrue(source.exists())
            self.assertFalse(target.exists())

    def test_output_files_rollback_failure_keeps_original_unlink_error_as_top_level(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Clip [.__mvd_token].mp4"
            target = Path(directory) / "Clip.mp4"
            source.write_bytes(b"media")
            original_unlink = Path.unlink
            source_error = OSError("source unlink failed")
            rollback_error = OSError("rollback unlink failed")

            def fail_source_and_target_unlink(path, *args, **kwargs):
                if path == source:
                    raise source_error
                if path == target:
                    raise rollback_error
                return original_unlink(path, *args, **kwargs)

            with patch.object(Path, "unlink", new=fail_source_and_target_unlink):
                with self.assertRaises(OSError) as raised:
                    output_files.claim_final_output_with_version(source, "Clip", 1)

            self.assertIs(raised.exception, source_error)
            self.assertIs(raised.exception.__cause__, rollback_error)
            self.assertTrue(source.exists())
            self.assertTrue(target.exists())

    def test_output_files_keeps_existing_candidate_after_conflict_then_link_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Clip [.__mvd_token].mp4"
            existing = Path(directory) / "Clip.mp4"
            second_candidate = Path(directory) / "Clip (2).mp4"
            source.write_bytes(b"new media")
            existing.write_bytes(b"existing media")

            with patch.object(
                output_files.os,
                "link",
                side_effect=(FileExistsError(), OSError("link failed")),
            ):
                with self.assertRaisesRegex(OSError, "link failed"):
                    output_files.claim_final_output_with_version(source, "Clip", 1)

            self.assertFalse(source.exists())
            self.assertEqual(existing.read_bytes(), b"existing media")
            self.assertFalse(second_candidate.exists())

    def test_output_files_does_not_use_python_311_exception_notes(self):
        source = Path(output_files.__file__).read_text(encoding="utf-8")
        self.assertNotIn(".add_note(", source)

    def test_output_files_templates_match_downloader_exports(self):
        output_dir = Path("/tmp/output")
        workspace = output_dir / ".attempts" / "0123456789abcdef"

        self.assertEqual(
            output_files.output_template(downloader.INSTAGRAM, output_dir, 2),
            downloader._output_template(downloader.INSTAGRAM, output_dir, 2),
        )
        self.assertEqual(
            output_files.attempt_output_template(
                downloader.YOUTUBE, output_dir, workspace
            ),
            downloader._attempt_output_template(
                downloader.YOUTUBE, output_dir, workspace
            ),
        )

    def test_output_files_direct_workspace_resolution_version_and_filesize_contract(self):
        class FakeYdl:
            def prepare_filename(self, _info):
                return str(output_dir / "Clip.webm")

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            workspace = output_files.new_attempt_workspace(output_dir)
            expected = output_dir / "Clip.mp3"
            expected.write_bytes(b"media")
            resolved = output_files.resolve_output_path(
                FakeYdl(),
                {"title": "Clip", "ext": "webm"},
                output_dir,
                media_type=downloader.AUDIO,
            )
            formatted = output_files.format_filesize(expected, {})
            output_files.cleanup_attempt_workspace(workspace)

        self.assertEqual(resolved, expected)
        self.assertEqual(output_files.audio_output_version(Path("Clip [MP3] (3).mp3"), 1), 3)
        self.assertEqual(formatted, "0.00 MB")

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

    def test_shared_finalizer_keeps_audio_metadata_in_platform_parity(self):
        info = {
            "title": "Song",
            "filesize": 1024 * 1024,
        }
        profile = downloader.AudioOutputProfile(
            downloader.SOURCE,
            downloader.SOURCE,
            False,
            "Opus",
            160,
            "webm",
            False,
        )
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            normal_source = output_dir / "Song [.__mvd_normal].opus"
            bilibili_source = output_dir / "Song [BV1TEST] [.__mvd_bili].opus"
            normal_source.write_bytes(b"normal")
            bilibili_source.write_bytes(b"bilibili")

            normal_path, normal_profile, normal_version = (
                downloader._finalize_download_output(
                    info,
                    normal_source,
                    downloader.AUDIO,
                    profile,
                    1,
                )
            )
            bilibili_path, bilibili_profile, bilibili_version = (
                downloader._finalize_download_output(
                    info,
                    bilibili_source,
                    downloader.AUDIO,
                    profile,
                    1,
                )
            )

        normal_result = downloader._build_download_result(
            info,
            normal_path,
            "YouTube",
            downloader.AUDIO,
            downloader.STANDARD,
            downloader.STANDARD,
            False,
            downloader.AccelerationPlan(False, None, 0),
            normal_profile,
            normal_version,
        )
        bilibili_result = downloader._build_download_result(
            info,
            bilibili_path,
            "Bilibili",
            downloader.AUDIO,
            downloader.STANDARD,
            downloader.STANDARD,
            False,
            downloader.AccelerationPlan(False, None, 0),
            bilibili_profile,
            bilibili_version,
        )

        self.assertEqual(normal_result.keys(), bilibili_result.keys())
        for key in (
            "title", "filesize", "media_type", "format", "acodec",
            "audio_format_requested", "audio_format_used",
            "audio_format_fallback", "output_ext", "cover_embedded",
            "source_acodec", "source_abr_kbps", "output_version_actual",
        ):
            with self.subTest(key=key):
                self.assertEqual(normal_result[key], bilibili_result[key])
        self.assertEqual(normal_path.name, "Song [Source Opus · 160kbps].opus")
        self.assertEqual(
            bilibili_path.name,
            "Song [BV1TEST] [Source Opus · 160kbps].opus",
        )
        self.assertEqual(normal_result["format"], "SOURCE OPUS")
        self.assertTrue(normal_result["cover_embedded"])
        self.assertEqual(normal_result["output_ext"], "opus")

    def test_node_discovery_is_cached_until_explicit_refresh(self):
        downloader._reset_node_path_cache()
        self.addCleanup(downloader._reset_node_path_cache)
        with patch("downloader.shutil.which", return_value="/opt/bin/node") as which:
            self.assertEqual(downloader._node_path(refresh=True), "/opt/bin/node")
            self.assertEqual(downloader._node_path(), "/opt/bin/node")
            self.assertEqual(which.call_count, 1)
            self.assertEqual(downloader._node_path(refresh=True), "/opt/bin/node")
            self.assertEqual(which.call_count, 2)

    def test_node_caches_none_and_reset_forces_a_rescan(self):
        downloader._reset_node_path_cache()
        self.addCleanup(downloader._reset_node_path_cache)
        with patch("downloader.shutil.which", return_value=None) as which:
            self.assertIsNone(downloader._node_path())
            self.assertIsNone(downloader._node_path())
            self.assertEqual(which.call_count, 1)
            downloader._reset_node_path_cache()
            self.assertIsNone(downloader._node_path())
            self.assertEqual(which.call_count, 2)

    def test_node_concurrent_cache_miss_scans_once(self):
        downloader._reset_node_path_cache()
        self.addCleanup(downloader._reset_node_path_cache)
        start = threading.Barrier(4)
        results = []

        def slow_which(_name):
            time.sleep(0.02)
            return None

        def worker():
            start.wait()
            results.append(downloader._node_path())

        with patch("downloader.shutil.which", side_effect=slow_which) as which:
            threads = [threading.Thread(target=worker) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=1)

        self.assertEqual(results, [None] * 4)
        self.assertEqual(which.call_count, 1)
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


class DownloadFinalizationOrchestrationTests(unittest.TestCase):
    def _normal_result(self, output_dir, media_type):
        info = {
            "title": "Song",
            "acodec": "opus" if media_type == downloader.AUDIO else "aac",
            "ext": "webm" if media_type == downloader.AUDIO else "mp4",
            "abr": 160,
            "fps": 30,
            "vcodec": "avc1",
            "filesize": 1024 * 1024,
        }
        private_path = output_dir / (
            "Song [.__mvd_normal].opus"
            if media_type == downloader.AUDIO
            else "Song [.__mvd_normal].mp4"
        )
        private_path.write_bytes(b"normal")

        class FakeYdl:
            def __init__(self, _options):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def extract_info(self, _url, download=False):
                return info

            def process_info(self, _info):
                return None

            def prepare_filename(self, _info):
                if media_type == downloader.AUDIO:
                    return str(private_path.with_suffix(".webm"))
                return str(private_path)

        with (
            patch("downloader.yt_dlp.YoutubeDL", FakeYdl),
            patch("downloader._resolve_output_path", return_value=private_path),
            patch(
                "downloader._finalize_download_output",
                wraps=downloader._finalize_download_output,
            ) as finalize,
            patch(
                "downloader._build_download_result",
                wraps=downloader._build_download_result,
            ) as build,
        ):
            result = downloader.download_video(
                "https://youtu.be/example",
                platform=downloader.YOUTUBE,
                media_type=media_type,
                audio_format=downloader.SOURCE,
                speed_mode=downloader.TURBO,
                output_version=2,
                output_dir=output_dir,
                raise_errors=True,
            )

        return result, finalize, build

    def _bilibili_result(self, output_dir, media_type):
        info = {
            "id": "BV1TEST",
            "title": "Song",
            "url": "https://primary.example/media",
            "acodec": "opus" if media_type == downloader.AUDIO else "aac",
            "ext": "webm" if media_type == downloader.AUDIO else "mp4",
            "abr": 160,
            "fps": 30,
            "vcodec": "avc1",
            "filesize": 1024 * 1024,
        }
        private_path = output_dir / (
            "Song [BV1TEST] [.__mvd_bili].opus"
            if media_type == downloader.AUDIO
            else "Song [BV1TEST] [.__mvd_bili].mp4"
        )
        private_path.write_bytes(b"bilibili")
        plan = downloader.AccelerationPlan(True, "fast.example", 4 * 1024 * 1024)
        with (
            patch("downloader.aria2c_path", return_value="/bin/aria2c"),
            patch("downloader._extract_bilibili_info", return_value=(Mock(), info)),
            patch("downloader.build_acceleration_plan", return_value=plan),
            patch(
                "downloader._process_bilibili_attempt",
                return_value=(info, private_path),
            ),
            patch(
                "downloader._finalize_download_output",
                wraps=downloader._finalize_download_output,
            ) as finalize,
            patch(
                "downloader._build_download_result",
                wraps=downloader._build_download_result,
            ) as build,
        ):
            result = downloader.download_video(
                "https://b23.tv/example",
                platform=downloader.BILIBILI,
                media_type=media_type,
                audio_format=downloader.SOURCE,
                speed_mode=downloader.TURBO,
                output_version=2,
                output_dir=output_dir,
                raise_errors=True,
            )

        return result, finalize, build

    def test_real_platform_paths_finalize_and_build_matching_audio_and_video_results(self):
        for media_type in (downloader.AUDIO, downloader.VIDEO):
            with self.subTest(media_type=media_type), tempfile.TemporaryDirectory() as directory:
                output_dir = Path(directory)
                normal, normal_finalize, normal_build = self._normal_result(
                    output_dir,
                    media_type,
                )
                bilibili, bilibili_finalize, bilibili_build = self._bilibili_result(
                    output_dir,
                    media_type,
                )

            expected_profile = (
                downloader.AudioOutputProfile(
                    downloader.SOURCE,
                    downloader.SOURCE,
                    False,
                    "Opus",
                    160,
                    "webm",
                    False,
                )
                if media_type == downloader.AUDIO
                else None
            )
            self.assertEqual(
                normal_finalize.call_args.args[2:],
                (media_type, expected_profile, 2),
            )
            self.assertEqual(
                bilibili_finalize.call_args.args[2:],
                (media_type, expected_profile, 2),
            )
            self.assertEqual(
                normal_build.call_args.args[4:8],
                (
                    downloader.TURBO,
                    downloader.STANDARD,
                    False,
                    downloader.AccelerationPlan(False, None, 0),
                ),
            )
            self.assertEqual(bilibili_build.call_args.args[4:7], (downloader.TURBO, downloader.TURBO, False))
            self.assertEqual(normal["output_version_actual"], 2)
            self.assertEqual(bilibili["output_version_actual"], 2)
            self.assertEqual(normal.keys(), bilibili.keys())
            normal_name = (
                "Song [Source Opus · 160kbps] (2).opus"
                if media_type == downloader.AUDIO
                else "Song (2).mp4"
            )
            bilibili_name = (
                "Song [BV1TEST] [Source Opus · 160kbps] (2).opus"
                if media_type == downloader.AUDIO
                else "Song [BV1TEST] (2).mp4"
            )
            normal_expected = {
                "platform": "YouTube",
                "title": "Song",
                "filepath": str(Path(normal["filepath"]).with_name(normal_name)),
                "filesize": "0.00 MB",
                "media_type": media_type,
                "speed_mode_requested": downloader.TURBO,
                "speed_mode_used": downloader.STANDARD,
                "turbo_fallback": False,
                "cdn_host": "未知",
                "http_chunk_size": 0,
                "output_version_actual": 2,
            }
            bilibili_expected = {
                **normal_expected,
                "platform": "Bilibili",
                "filepath": str(Path(bilibili["filepath"]).with_name(bilibili_name)),
                "speed_mode_used": downloader.TURBO,
                "cdn_host": "fast.example",
                "http_chunk_size": 4 * 1024 * 1024,
            }
            if media_type == downloader.AUDIO:
                audio_fields = {
                    "format": "SOURCE OPUS",
                    "acodec": "Opus",
                    "audio_format_requested": downloader.SOURCE,
                    "audio_format_used": downloader.SOURCE,
                    "audio_format_fallback": False,
                    "output_ext": "opus",
                    "cover_embedded": True,
                    "source_acodec": "Opus",
                    "source_abr_kbps": 160,
                }
                normal_expected.update(audio_fields)
                bilibili_expected.update(audio_fields)
            else:
                video_fields = {
                    "resolution": "未知",
                    "fps": 30,
                    "vcodec": "avc1",
                    "acodec": "aac",
                }
                normal_expected.update(video_fields)
                bilibili_expected.update(video_fields)
            self.assertEqual(normal, normal_expected)
            self.assertEqual(bilibili, bilibili_expected)
            self.assertEqual(
                Path(normal["filepath"]).name,
                Path(bilibili["filepath"]).name.replace(" [BV1TEST]", ""),
            )
            for key in set(normal) - {
                "platform", "filepath", "speed_mode_used", "cdn_host", "http_chunk_size",
            }:
                with self.subTest(media_type=media_type, key=key):
                    self.assertEqual(normal[key], bilibili[key])
            self.assertEqual(normal["speed_mode_requested"], downloader.TURBO)
            self.assertEqual(normal["speed_mode_used"], downloader.STANDARD)
            self.assertEqual(normal["cdn_host"], "未知")
            self.assertEqual(normal["http_chunk_size"], 0)
            self.assertEqual(bilibili["speed_mode_used"], downloader.TURBO)
            self.assertEqual(bilibili["cdn_host"], "fast.example")
            self.assertEqual(bilibili["http_chunk_size"], 4 * 1024 * 1024)


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
    def test_audio_download_completion_explains_long_mp3_postprocessing(self):
        events = []
        hook = downloader._make_progress_hook(
            1,
            1,
            progress_callback=lambda event, data: events.append((event, data)),
            media_type=downloader.AUDIO,
            audio_format=downloader.MP3,
        )
        buffer = io.StringIO()

        with contextlib.redirect_stdout(buffer):
            hook({"status": "finished"})

        self.assertEqual(events[0][0], "postprocessing")
        self.assertIn("MP3 V0", events[0][1]["stage_text"])
        self.assertIn("数十秒至数分钟", events[0][1]["detail_text"])
        self.assertIn("长音频", buffer.getvalue())

    def test_postprocessor_hook_reports_real_processing_stages(self):
        events = []
        hook = downloader._make_postprocessor_status_hook(
            1,
            1,
            progress_callback=lambda event, data: events.append((event, data)),
            media_type=downloader.AUDIO,
            audio_format=downloader.MP3,
        )

        with contextlib.redirect_stdout(io.StringIO()):
            hook({"status": "started", "postprocessor": "ExtractAudio"})
            hook({"status": "started", "postprocessor": "Metadata"})
            hook({"status": "started", "postprocessor": "EmbedThumbnail"})

        self.assertEqual(
            [data["stage"] for _, data in events],
            ["transcoding_audio", "writing_metadata", "embedding_thumbnail"],
        )
        self.assertTrue(all(event == "postprocessing" for event, _ in events))

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

    def test_progress_snapshot_reports_exact_or_estimated_total_size(self):
        exact = downloader._extract_progress_snapshot({
            "total_bytes": 1536 * 1024 * 1024,
        })
        estimated = downloader._extract_progress_snapshot({
            "total_bytes_estimate": 750 * 1024 * 1024,
        })

        self.assertEqual(exact["total_size_text"], "1.50 GiB")
        self.assertFalse(exact["total_size_is_estimate"])
        self.assertEqual(estimated["total_size_text"], "750.00 MiB")
        self.assertTrue(estimated["total_size_is_estimate"])

    def test_progress_snapshot_sums_selected_video_and_audio_streams(self):
        snapshot = downloader._extract_progress_snapshot({
            "total_bytes": 100,
            "info_dict": {
                "requested_formats": [
                    {"filesize": 800 * 1024 * 1024},
                    {"filesize_approx": 200 * 1024 * 1024},
                ],
            },
        })

        self.assertEqual(snapshot["total_size_text"], "1000.00 MiB")
        self.assertTrue(snapshot["total_size_is_estimate"])

    def test_cli_progress_distinguishes_estimated_total_size(self):
        hook = downloader._make_progress_hook(1, 1)
        buffer = io.StringIO()

        with contextlib.redirect_stdout(buffer):
            hook({
                "status": "downloading",
                "_percent_str": "50.0%",
                "total_bytes_estimate": 512 * 1024 * 1024,
            })

        self.assertIn("预计总大小: 512.00 MiB", buffer.getvalue())

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
