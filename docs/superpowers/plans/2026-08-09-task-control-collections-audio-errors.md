# Task Control, Collection Downloads, Audio Outputs, and Structured Errors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe task cancellation/retry/redownload, selectable collection downloads, source/WAV audio output, and structured error logging without changing existing quality defaults or deleting downloaded files.

**Architecture:** Keep Flask and yt-dlp as the runtime foundation, but route Web jobs through one in-memory `TaskManager` with a three-worker executor and a two-slot Bilibili semaphore. Add focused modules for error classification, JSONL logging, and collection previews; extend `downloader.py` through explicit parameters so CLI and Web share media behavior.

**Tech Stack:** Python 3.10+, Flask 3, yt-dlp, FFmpeg/FFprobe, mutagen, standard-library `concurrent.futures`, `threading`, `logging.handlers`, `dataclasses`, `unittest`, HTML/CSS/vanilla JavaScript.

## Global Constraints

- Keep Web service at `127.0.0.1:8233`.
- Keep separate video and audio input sections.
- Keep highest-available video quality; do not add quality selectors.
- Keep at most 3 active downloads globally and at most 2 active Bilibili downloads.
- Standard tasks use cooperative cancellation; active aria2c transfers are never cancelled.
- A redownload preserves the original and allocates `(2)`, `(3)`, and later suffixes.
- A collection submission contains at most 100 selected entries.
- Audio choices are exactly `mp3`, `flac`, `source`, and `wav`; MP3 remains the default.
- Never describe WAV transcoding or lossy-source conversion as an audio-quality upgrade.
- JSONL logs rotate at 10 MiB and keep 5 backups; sensitive URLs, cookies, tokens, authorization data, and proxy credentials are redacted.
- Do not delete or overwrite any existing file under `downloads/`; real-download tests use a temporary output directory.
- Preserve compatibility for existing Python calls, `/api/download` requests, `--audio --flac`, standard/turbo behavior, covers, quality labels, and platform filename rules.

---

## File Structure

**Create:**

- `download_errors.py` — stable error codes, public error payloads, cancellation exception, classification, and CLI formatting.
- `download_logging.py` — redaction helpers, JSONL formatter, rotating logger, and safe event writes.
- `collection_resolver.py` — collection URL recognition, flat metadata extraction, preview records, selection validation, and expiring preview storage.
- `task_control.py` — cancellation token, task/batch state, global executor, Bilibili semaphore, retry, redownload, and snapshots.
- `tests/test_structured_errors.py` — error mapping and log-redaction coverage.
- `tests/test_collection_resolver.py` — YouTube/Bilibili/Instagram preview and selection coverage.
- `tests/test_task_control.py` — task-state, concurrency, cancel, retry, and redownload coverage.

**Modify:**

- `downloader.py` — new audio formats, cancellation checkpoints, structured failures, output version suffixes, and richer failed events.
- `app.py` — instantiate `TaskManager`, add preview/task-operation endpoints, validate preview selection, and return structured errors.
- `main.py` — four audio formats, collection selection, structured CLI errors, and compatible flags.
- `templates/index.html` — collection preview, four-format control, task operation buttons, attempt history, and structured errors.
- `tests/test_downloader_errors.py` — source/WAV options, cancellation hooks, and versioned filenames.
- `tests/test_parallel_downloads.py` — compatibility of the existing batch helper.
- `tests/test_web_progress.py` — new APIs and frontend contract.
- `tests/test_cli_audio.py` — new flags, interactive choices, and collection selection.
- `.gitignore` — ignore runtime `logs/`.
- `README.md` — document task controls, collections, audio outputs, logs, limits, and the browser-extension roadmap.

---

### Task 1: Structured Error Model and Redacted JSONL Logging

**Files:**
- Create: `download_errors.py`
- Create: `download_logging.py`
- Create: `tests/test_structured_errors.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `DownloadErrorInfo`, `DownloadFailure`, `DownloadCancelled`, `classify_download_error(error, platform=None, stage="download")`, `public_error(error)`, `format_cli_error(error)`.
- Produces: `sanitize_url(value)`, `redact_value(value)`, `get_download_logger(log_dir=None)`, `log_download_event(logger, event, **fields)`.
- Consumes: platform string constants only; neither module imports Flask or `downloader.py`.

- [ ] **Step 1: Write failing error and logging tests**

```python
# tests/test_structured_errors.py
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from download_errors import (
    DownloadCancelled,
    classify_download_error,
    public_error,
)
from download_logging import get_download_logger, log_download_event, sanitize_url


class StructuredErrorTests(unittest.TestCase):
    def test_network_timeout_is_retryable(self):
        info = classify_download_error(
            RuntimeError("socket timeout while connecting"),
            platform="youtube",
        )
        self.assertEqual(info.error_code, "NETWORK_TIMEOUT")
        self.assertTrue(info.retryable)
        self.assertIn("网络", info.message)

    def test_membership_failure_is_not_retryable(self):
        info = classify_download_error(
            RuntimeError("members only premium content"),
            platform="bilibili",
        )
        self.assertEqual(info.error_code, "MEMBERSHIP_REQUIRED")
        self.assertFalse(info.retryable)

    def test_public_error_excludes_technical_detail(self):
        payload = public_error(classify_download_error(RuntimeError("secret detail")))
        self.assertEqual(
            set(payload),
            {"error_code", "message", "suggestion", "retryable"},
        )

    def test_cancelled_has_dedicated_code(self):
        self.assertEqual(DownloadCancelled().info.error_code, "CANCELLED")


class DownloadLoggingTests(unittest.TestCase):
    def test_sanitize_url_drops_query_and_fragment(self):
        value = sanitize_url(
            "https://www.bilibili.com/video/BV123?token=secret#fragment"
        )
        self.assertEqual(value, "https://www.bilibili.com/video/BV123")

    def test_jsonl_log_redacts_nested_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = get_download_logger(Path(directory))
            log_download_event(
                logger,
                "failed",
                url="https://youtu.be/abc?token=secret",
                headers={"Authorization": "Bearer secret"},
                cookie="session=secret",
                error_code="NETWORK_TIMEOUT",
            )
            for handler in logger.handlers:
                handler.flush()
            line = (Path(directory) / "downloader.jsonl").read_text(
                encoding="utf-8"
            ).strip()
            payload = json.loads(line)
            rendered = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("secret", rendered)
            self.assertEqual(payload["event"], "failed")
            self.assertEqual(payload["url"], "https://youtu.be/abc")

    def test_unwritable_log_directory_does_not_break_download_flow(self):
        with patch("download_logging.Path.mkdir", side_effect=OSError("denied")):
            logger = get_download_logger(Path("/unwritable"))
        self.assertIsNone(logger)
        self.assertFalse(log_download_event(logger, "started", task_id="task"))

    def tearDown(self):
        logging.shutdown()
```

- [ ] **Step 2: Run the new tests and verify the modules are missing**

Run: `venv/bin/python -m unittest tests.test_structured_errors -v`

Expected: FAIL with `ModuleNotFoundError` for `download_errors` or `download_logging`.

- [ ] **Step 3: Implement the error model and classifier**

```python
# download_errors.py
from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadErrorInfo:
    error_code: str
    message: str
    suggestion: str
    retryable: bool
    technical_detail: str = ""


class DownloadFailure(Exception):
    def __init__(self, info: DownloadErrorInfo):
        super().__init__(info.technical_detail or info.message)
        self.info = info


class DownloadCancelled(DownloadFailure):
    def __init__(self):
        super().__init__(DownloadErrorInfo(
            "CANCELLED",
            "任务已取消",
            "可以点击重试重新加入队列",
            True,
        ))


def _info(code, message, suggestion, retryable, detail):
    return DownloadErrorInfo(code, message, suggestion, retryable, detail)


def classify_download_error(error, platform=None, stage="download"):
    if isinstance(error, DownloadFailure):
        return error.info
    detail = str(error)
    message = detail.lower()
    if "timeout" in message or "timed out" in message:
        return _info("NETWORK_TIMEOUT", "连接源站超时", "请检查网络或代理设置后重试", True, detail)
    if "http error 429" in message or "rate limit" in message or "too many request" in message:
        return _info("RATE_LIMITED", "请求过于频繁", "请稍后再重试，并避免同时提交大量链接", True, detail)
    if platform == "bilibili" and any(value in message for value in ("members only", "member only", "premium")):
        return _info("MEMBERSHIP_REQUIRED", "该内容需要会员权限", "请确认当前 Cookie 对应账号拥有访问权限", False, detail)
    if "login" in message or "sign in" in message or "http error 403" in message:
        return _info("AUTH_REQUIRED", "当前凭证无法访问该内容", "请更新对应平台 Cookie 后重试", True, detail)
    if "copyright" in message or "geo" in message or "blocked" in message:
        return _info("GEO_RESTRICTED", "该内容受到版权或地区限制", "请确认当前地区允许访问该内容", False, detail)
    if "requested format" in message or "no audio" in message:
        return _info("FORMAT_UNAVAILABLE", "源站没有可用的目标格式", "请选择其他输出格式或更换链接", False, detail)
    if "aria2" in message:
        return _info("ARIA2_FAILED", "aria2c 极速下载失败", "请重试；程序会按现有规则降级到标准模式", True, detail)
    if "ffmpeg" in message or stage == "postprocess":
        return _info("POSTPROCESS_FAILED", "媒体后处理失败", "请确认 FFmpeg 可用且磁盘空间充足", True, detail)
    if isinstance(error, OSError):
        return _info("STORAGE_ERROR", "无法写入下载文件", "请检查下载目录权限和磁盘空间", True, detail)
    if stage == "collection":
        return _info("COLLECTION_EXTRACT_FAILED", "无法解析播放列表或合集", "请确认链接公开可访问并更新 Cookie 后重试", True, detail)
    if stage == "metadata":
        return _info("METADATA_FAILED", "无法读取媒体信息", "请检查链接、Cookie 和网络后重试", True, detail)
    return _info("DOWNLOAD_FAILED", "下载失败", "请查看错误日志后重试", True, detail)


def public_error(error):
    info = error.info if isinstance(error, DownloadFailure) else error
    return {
        "error_code": info.error_code,
        "message": info.message,
        "suggestion": info.suggestion,
        "retryable": info.retryable,
    }


def format_cli_error(error):
    info = error.info if isinstance(error, DownloadFailure) else error
    return f"[{info.error_code}] {info.message}\n   建议：{info.suggestion}"
```

- [ ] **Step 4: Implement redaction and rotating JSONL logs**

```python
# download_logging.py
import json
import logging
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PROJECT_DIR = Path(__file__).resolve().parent
SENSITIVE_KEYS = {"authorization", "cookie", "cookies", "token", "password", "proxy_password"}
_warning_lock = threading.Lock()
_warning_emitted = False


def _warn_logging_once():
    global _warning_emitted
    with _warning_lock:
        if not _warning_emitted:
            print("⚠️  下载日志暂时无法写入，下载任务将继续执行。")
            _warning_emitted = True


def sanitize_url(value):
    try:
        parts = urlsplit(str(value))
    except ValueError:
        return "[redacted-url]"
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return str(value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def redact_value(value, key=""):
    if key.lower() in SENSITIVE_KEYS:
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return sanitize_url(value)
    return value


class JsonLineFormatter(logging.Formatter):
    def format(self, record):
        payload = redact_value(record.payload)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def get_download_logger(log_dir=None):
    directory = Path(log_dir) if log_dir else PROJECT_DIR / "logs"
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        _warn_logging_once()
        return None
    logger = logging.getLogger(f"multiple_video_downloader.{directory.resolve()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(
            directory / "downloader.jsonl",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(JsonLineFormatter())
        logger.addHandler(handler)
    return logger


def log_download_event(logger, event, **fields):
    if logger is None:
        return False
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    try:
        logger.info("download-event", extra={"payload": payload})
    except (OSError, ValueError):
        _warn_logging_once()
        return False
    return True
```

- [ ] **Step 5: Ignore runtime logs and run tests**

Add this exact line to `.gitignore`:

```gitignore
logs/
```

Run: `venv/bin/python -m unittest tests.test_structured_errors -v`

Expected: all structured-error and logging tests PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add download_errors.py download_logging.py tests/test_structured_errors.py .gitignore
git commit -m "feat: add structured errors and redacted logs"
```

---

### Task 2: Source Audio and WAV Output

**Files:**
- Modify: `downloader.py:45-540`
- Modify: `tests/test_downloader_errors.py:107-282`

**Interfaces:**
- Produces: `SOURCE = "source"`, `WAV = "wav"`, `AUDIO_FORMATS = {MP3, FLAC, SOURCE, WAV}`.
- Produces: `AudioOutputProfile.output_ext`, `_audio_postprocessors(profile)`, and output labels based on real codecs.
- Consumes: existing `_selected_audio_info`, `_resolve_output_path`, `_rename_audio_output`, and mutagen/yt-dlp postprocessors.

- [ ] **Step 1: Add failing tests for source and WAV profiles/options**

```python
# append to DownloadAudioOptionsTests in tests/test_downloader_errors.py
def test_source_audio_preserves_selected_codec_without_lossy_quality_setting(self):
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

def test_wav_decodes_best_audio_and_does_not_claim_lossless_source(self):
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
    self.assertEqual(options["postprocessors"][0]["preferredcodec"], "wav")
    self.assertEqual(downloader._audio_quality_label(profile), "WAV PCM · 源AAC 128kbps")

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
    self.assertNotIn("EmbedThumbnail", [p["key"] for p in source_options["postprocessors"]])
    self.assertNotIn("EmbedThumbnail", [p["key"] for p in wav_options["postprocessors"]])
```

- [ ] **Step 2: Run the focused tests and confirm missing constants/signature**

Run: `venv/bin/python -m unittest tests.test_downloader_errors.DownloadAudioOptionsTests -v`

Expected: FAIL because `SOURCE`, `WAV`, `output_ext`, and `selected_audio` are not implemented.

- [ ] **Step 3: Extend audio constants and profiles**

```python
# downloader.py constants and dataclass
SOURCE = "source"
WAV = "wav"
AUDIO_FORMATS = {MP3, FLAC, SOURCE, WAV}

@dataclass(frozen=True)
class AudioOutputProfile:
    requested: str
    used: str
    fallback: bool
    source_acodec: str | None
    source_abr_kbps: int | None
    output_ext: str


def _audio_output_profile(info, requested):
    if requested not in AUDIO_FORMATS:
        raise ValueError(f"不支持的音频格式: {requested}")
    selected = _selected_audio_info(info)
    codec = _display_audio_codec(selected.get("acodec"))
    bitrate = selected.get("abr") or selected.get("tbr")
    bitrate = round(bitrate) if isinstance(bitrate, (int, float)) and bitrate > 0 else None
    source_ext = str(selected.get("ext") or "").lower()
    if requested == FLAC:
        used = FLAC if codec == "FLAC" else MP3
        output_ext = "flac" if used == FLAC else "mp3"
    elif requested == SOURCE:
        used = SOURCE
        output_ext = source_ext or "mka"
    elif requested == WAV:
        used = WAV
        output_ext = "wav"
    else:
        used = MP3
        output_ext = "mp3"
    return AudioOutputProfile(
        requested=requested,
        used=used,
        fallback=requested == FLAC and used == MP3,
        source_acodec=codec,
        source_abr_kbps=bitrate,
        output_ext=output_ext,
    )
```

- [ ] **Step 4: Build exact postprocessor choices and real labels**

```python
def _audio_postprocessors(profile):
    preferred = {
        MP3: "mp3",
        FLAC: "flac",
        SOURCE: "best",
        WAV: "wav",
    }[profile.used]
    extractor = {"key": "FFmpegExtractAudio", "preferredcodec": preferred}
    if profile.used == MP3:
        extractor["preferredquality"] = "0"
    processors = [
        extractor,
        {
            "key": "FFmpegMetadata",
            "add_metadata": True,
            "add_chapters": False,
            "add_infojson": False,
        },
    ]
    if profile.output_ext in {"mp3", "m4a", "mp4", "flac", "opus", "ogg"}:
        processors.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
    return processors


def _audio_quality_label(profile):
    if profile.used == FLAC:
        parts = ["FLAC Lossless"]
    elif profile.used == SOURCE:
        parts = [f"Source {profile.source_acodec or profile.output_ext.upper()}"]
    elif profile.used == WAV:
        parts = ["WAV PCM"]
    else:
        parts = ["MP3 V0"]
    if profile.used != FLAC and profile.source_acodec and profile.used != SOURCE:
        source = f"源{profile.source_acodec}"
        if profile.source_abr_kbps:
            source += f" {profile.source_abr_kbps}kbps"
        parts.append(source)
    elif profile.source_abr_kbps:
        parts.append(f"{profile.source_abr_kbps}kbps")
    return " · ".join(parts)
```

Pass the selected audio metadata into `_build_ydl_options(..., selected_audio=None)`, construct the profile before postprocessors, set `format` to `bestaudio[acodec!=none]/best[acodec!=none]`, and make `_resolve_output_path()` use `profile.output_ext` rather than assuming the requested enum is a suffix.

Set `writethumbnail` only when the postprocessor list contains `EmbedThumbnail`, so source WebM and WAV do not leave standalone image files. Extend `_build_download_result()` with `audio_format_requested`, `audio_format_used`, `output_ext`, `source_acodec`, `source_abr_kbps`, and `cover_embedded`; its human `format` value must be `MP3 V0`, `FLAC`, `SOURCE <EXT>`, or `WAV PCM` according to the real result.

- [ ] **Step 5: Run focused and regression audio tests**

Run: `venv/bin/python -m unittest tests.test_downloader_errors tests.test_bilibili_support tests.test_cli_audio -v`

Expected: all tests PASS; existing MP3/FLAC behavior remains unchanged.

- [ ] **Step 6: Commit Task 2**

```bash
git add downloader.py tests/test_downloader_errors.py
git commit -m "feat: add source audio and wav outputs"
```

---

### Task 3: Collection Resolver and Expiring Preview Store

**Files:**
- Create: `collection_resolver.py`
- Create: `tests/test_collection_resolver.py`
- Modify: `downloader.py:95-180`

**Interfaces:**
- Produces: `CollectionEntry`, `CollectionPreview`, `CollectionResolveError`, `resolve_collection(text, ydl_factory=yt_dlp.YoutubeDL)`, `resolve_inputs(inputs, ydl_factory=yt_dlp.YoutubeDL)`, `select_preview_entries(preview, entry_ids, limit=100)`.
- Produces: `PreviewStore.put(preview)`, `PreviewStore.get(preview_id)`, `PreviewStore.prune()` with a 30-minute TTL.
- Consumes: `normalize_url`, platform names/constants, and cookie selection from `downloader.py` through small public helpers.

- [ ] **Step 1: Add failing resolver tests with mocked yt-dlp metadata**

```python
# tests/test_collection_resolver.py
import unittest
from unittest.mock import MagicMock, patch

import collection_resolver as resolver


class CollectionResolverTests(unittest.TestCase):
    def _factory(self, info):
        ydl = MagicMock()
        ydl.__enter__.return_value = ydl
        ydl.extract_info.return_value = info
        return lambda options: ydl

    def test_youtube_playlist_preserves_order_and_disabled_entries(self):
        info = {
            "_type": "playlist",
            "title": "Playlist",
            "entries": [
                {"id": "one", "title": "One", "url": "https://youtu.be/one", "thumbnail": "https://img/one.jpg"},
                {"id": "gone", "title": "Deleted video", "url": None, "availability": "private"},
                {"id": "two", "title": "Two", "url": "https://youtu.be/two"},
            ],
        }
        preview = resolver.resolve_collection(
            "https://www.youtube.com/playlist?list=PL123",
            ydl_factory=self._factory(info),
        )
        self.assertEqual([entry.position for entry in preview.entries], [1, 2, 3])
        self.assertTrue(preview.entries[0].selectable)
        self.assertFalse(preview.entries[1].selectable)
        self.assertTrue(preview.requires_selection)

    def test_bilibili_multipart_builds_distinct_p_urls(self):
        info = {
            "_type": "multi_video",
            "id": "BV123",
            "title": "Parts",
            "entries": [
                {"id": "BV123_p1", "title": "P1", "url": "https://www.bilibili.com/video/BV123?p=1"},
                {"id": "BV123_p2", "title": "P2", "url": "https://www.bilibili.com/video/BV123?p=2"},
            ],
        }
        preview = resolver.resolve_collection(
            "https://www.bilibili.com/video/BV123",
            ydl_factory=self._factory(info),
        )
        self.assertNotEqual(preview.entries[0].url, preview.entries[1].url)
        self.assertIn("p=2", preview.entries[1].url)

    def test_instagram_carousel_entries_remain_separate(self):
        info = {
            "_type": "playlist",
            "id": "carousel",
            "title": "Post",
            "entries": [
                {"id": "photo", "title": "Photo", "url": "https://www.instagram.com/p/post/?__a=1"},
                {"id": "video", "title": "Video", "url": "https://www.instagram.com/p/post/?__a=2"},
            ],
        }
        preview = resolver.resolve_collection(
            "https://www.instagram.com/p/post/",
            ydl_factory=self._factory(info),
        )
        self.assertEqual(len(preview.entries), 2)
        self.assertEqual([entry.position for entry in preview.entries], [1, 2])

    def test_selection_rejects_more_than_100_and_unknown_ids(self):
        entries = tuple(
            resolver.CollectionEntry(str(index), str(index), "youtube", f"https://youtu.be/{index}", index, None, True, None)
            for index in range(1, 102)
        )
        preview = resolver.CollectionPreview("p", "title", "youtube", entries, False)
        with self.assertRaisesRegex(ValueError, "最多选择 100"):
            resolver.select_preview_entries(preview, [entry.id for entry in entries])
        with self.assertRaisesRegex(ValueError, "条目不存在"):
            resolver.select_preview_entries(preview, ["missing"])

    def test_mixed_inputs_merge_single_and_collection_entries_in_input_order(self):
        single = resolver.CollectionPreview(
            "single",
            "Single",
            "youtube",
            (resolver.CollectionEntry("1:a", "A", "youtube", "https://youtu.be/a", 1, None, True, None),),
            True,
        )
        collection = resolver.CollectionPreview(
            "collection",
            "Parts",
            "bilibili",
            (
                resolver.CollectionEntry("1:p1", "P1", "bilibili", "https://bilibili.com/video/BV1?p=1", 1, None, True, None),
                resolver.CollectionEntry("2:p2", "P2", "bilibili", "https://bilibili.com/video/BV1?p=2", 2, None, True, None),
            ),
            False,
        )
        with patch(
            "collection_resolver.resolve_collection",
            side_effect=[single, collection],
        ):
            merged = resolver.resolve_inputs([
                "https://youtu.be/a",
                "https://b23.tv/list",
            ])
        self.assertEqual([entry.title for entry in merged.entries], ["A", "P1", "P2"])
        self.assertEqual(merged.platform, "mixed")
        self.assertFalse(merged.is_single)
        self.assertTrue(merged.requires_selection)
```

- [ ] **Step 2: Run the resolver tests and verify failure**

Run: `venv/bin/python -m unittest tests.test_collection_resolver -v`

Expected: FAIL because `collection_resolver.py` does not exist.

- [ ] **Step 3: Implement immutable preview records and selection validation**

```python
# collection_resolver.py
import threading
import time
import uuid
from dataclasses import asdict, dataclass

import yt_dlp

from downloader import BILIBILI, INSTAGRAM, YOUTUBE, normalize_url
from download_errors import DownloadFailure, classify_download_error


class CollectionResolveError(DownloadFailure):
    pass


@dataclass(frozen=True)
class CollectionEntry:
    id: str
    title: str
    platform: str
    url: str | None
    position: int
    thumbnail: str | None
    selectable: bool
    unavailable_reason: str | None


@dataclass(frozen=True)
class CollectionPreview:
    id: str
    title: str
    platform: str
    entries: tuple[CollectionEntry, ...]
    is_single: bool
    requires_selection: bool = False

    def to_dict(self):
        return {
            "preview_id": self.id,
            "title": self.title,
            "platform": self.platform,
            "is_single": self.is_single,
            "requires_selection": self.requires_selection,
            "entries": [asdict(entry) for entry in self.entries],
        }


def select_preview_entries(preview, entry_ids, limit=100):
    if not isinstance(entry_ids, list) or not all(isinstance(value, str) for value in entry_ids):
        raise ValueError("条目选择格式无效")
    if not entry_ids:
        raise ValueError("请至少选择一个条目")
    if len(entry_ids) > limit:
        raise ValueError(f"一次最多选择 {limit} 个条目")
    index = {entry.id: entry for entry in preview.entries}
    if any(entry_id not in index for entry_id in entry_ids):
        raise ValueError("所选条目不存在或预览已变化")
    selected = [index[entry_id] for entry_id in entry_ids]
    if any(not entry.selectable or not entry.url for entry in selected):
        raise ValueError("所选条目中包含不可下载内容")
    return selected
```

- [ ] **Step 4: Implement flat yt-dlp extraction and preview storage**

Use `extract_flat="in_playlist"`, `skip_download=True`, `lazy_playlist=True`, `noplaylist=False`, the existing platform cookie file, and current safe headers. Convert each entry to a stable ID of `<position>:<extractor-id>`. A single item returns `is_single=True` and `requires_selection=False`; playlist/multi-video metadata returns ordered entries with `requires_selection=True`. Bilibili entry URLs must preserve or construct `?p=<position>`. Catch yt-dlp extraction exceptions and raise `CollectionResolveError(classify_download_error(error, platform, stage="collection"))`; do not expose extractor text through the preview API.

`resolve_inputs()` accepts the complete ordered list from one video or audio textarea. Resolve each input independently, prefix entry IDs with the input position to avoid collisions, flatten entries in input order, and return one aggregate `CollectionPreview`. Set `platform="mixed"` when entries span platforms, `is_single=True` only when the aggregate contains exactly one direct item, and `requires_selection=True` when any input expands or any entry is disabled. This preserves the existing mixed-platform queue while allowing a collection and ordinary links in the same submission.

```python
class PreviewStore:
    def __init__(self, ttl_seconds=1800):
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._items = {}

    def put(self, preview):
        with self._lock:
            self._items[preview.id] = (time.monotonic() + self.ttl_seconds, preview)
        return preview.id

    def get(self, preview_id):
        self.prune()
        with self._lock:
            item = self._items.get(preview_id)
            return item[1] if item else None

    def prune(self):
        now = time.monotonic()
        with self._lock:
            expired = [key for key, (deadline, _) in self._items.items() if deadline <= now]
            for key in expired:
                self._items.pop(key, None)
```

- [ ] **Step 5: Expand platform recognition only for supported collection paths**

In `downloader.py`, add a public `detect_collection_platform()` that recognizes YouTube `/playlist` or `list=`, Bilibili `/video/`, `/medialist/play/`, `/list/`, and `space.bilibili.com/<mid>/lists/<sid>`, plus existing Instagram post URLs. Do not treat generic channel/profile URLs as collections.

- [ ] **Step 6: Run resolver and URL regression tests**

Run: `venv/bin/python -m unittest tests.test_collection_resolver tests.test_downloader_errors tests.test_bilibili_support -v`

Expected: all tests PASS and single-video URL behavior is unchanged.

- [ ] **Step 7: Commit Task 3**

```bash
git add collection_resolver.py downloader.py tests/test_collection_resolver.py
git commit -m "feat: preview playlists collections and multipart videos"
```

---

### Task 4: Downloader Cancellation Checkpoints and Versioned Outputs

**Files:**
- Modify: `task_control.py` (create the cancellation primitive first)
- Modify: `downloader.py:280-1165`
- Modify: `tests/test_downloader_errors.py`
- Modify: `tests/test_parallel_downloads.py`

**Interfaces:**
- Produces: `CancellationToken.cancel()`, `CancellationToken.cancelled`, `CancellationToken.raise_if_cancelled()`.
- Extends: `download_video(url, index=1, total=1, platform=None, progress_callback=None, media_type=VIDEO, audio_format=MP3, speed_mode=STANDARD, cancel_token=None, output_version=1, raise_errors=False)`.
- Extends: `_build_ydl_options(platform, output_dir, index, total, progress_callback=None, media_type=VIDEO, audio_format=MP3, speed_mode=STANDARD, aria2_executable=None, selected_audio=None, cancel_token=None, output_version=1)` and `_rename_audio_output(filepath, profile, output_version=1)`.
- Consumes: `DownloadCancelled`, `DownloadFailure`, and `classify_download_error`.

- [ ] **Step 1: Write failing cancellation and filename-version tests**

```python
# tests/test_downloader_errors.py
import download_errors
import task_control

def test_progress_hook_raises_dedicated_cancel_exception(self):
    token = task_control.CancellationToken()
    hook = downloader._make_progress_hook(1, 1, cancel_token=token)
    token.cancel()
    with self.assertRaises(download_errors.DownloadCancelled):
        hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 2})

def test_video_output_template_includes_redownload_suffix(self):
    options = downloader._build_ydl_options(
        downloader.YOUTUBE,
        Path("/tmp/output"),
        1,
        1,
        output_version=2,
    )
    self.assertIn(" (2).%(ext)s", options["outtmpl"])

def test_audio_quality_label_precedes_redownload_suffix(self):
    path = Path(self.temp_dir.name) / "Song (2).mp3"
    path.touch()
    profile = downloader.AudioOutputProfile(
        downloader.MP3,
        downloader.MP3,
        False,
        "AAC",
        128,
        "mp3",
    )
    target = downloader._rename_audio_output(path, profile, output_version=2)
    self.assertEqual(target.name, "Song [MP3 V0 · 源AAC 128kbps] (2).mp3")

def test_cancel_cleanup_preserves_preexisting_and_completed_files(self):
    with tempfile.TemporaryDirectory() as directory:
        output_dir = Path(directory)
        existing = output_dir / "existing.mp4"
        new_part = output_dir / "new.mp4.part"
        completed = output_dir / "new.mp4"
        existing.write_bytes(b"original")
        before = downloader._temporary_snapshot(output_dir)
        new_part.write_bytes(b"partial")
        completed.write_bytes(b"complete")
        downloader._cleanup_new_attempt_files(output_dir, before)
        self.assertEqual(existing.read_bytes(), b"original")
        self.assertFalse(new_part.exists())
        self.assertTrue(completed.exists())
```

- [ ] **Step 2: Run focused tests and verify missing cancellation/version arguments**

Run: `venv/bin/python -m unittest tests.test_downloader_errors -v`

Expected: FAIL with missing `CancellationToken` or unexpected keyword arguments.

- [ ] **Step 3: Add the cancellation primitive without importing downloader**

```python
# initial section of task_control.py
import threading

from download_errors import DownloadCancelled


class CancellationToken:
    def __init__(self):
        self._event = threading.Event()

    @property
    def cancelled(self):
        return self._event.is_set()

    def cancel(self):
        self._event.set()

    def raise_if_cancelled(self):
        if self.cancelled:
            raise DownloadCancelled()
```

- [ ] **Step 4: Add cancellation checks and structured propagation**

Pass `cancel_token` into progress and postprocessor hooks. Check it before metadata extraction, before media processing, after processing, and before final rename. In `_download_bilibili`, emit the existing `mode` event before aria2c starts; callers use that event to close the cancellation window.

In `download_video`, classify caught exceptions. If `raise_errors=True`, raise `DownloadFailure(info)`; otherwise print `format_cli_error(info)` and return `None`. Never convert `DownloadCancelled` to `DOWNLOAD_FAILED`.

```python
def _make_cancel_hook(cancel_token):
    def _hook(_data):
        if cancel_token:
            cancel_token.raise_if_cancelled()
    return _hook
```

- [ ] **Step 5: Add deterministic output versioning**

Use `output_version=1` for normal downloads. For values greater than one, append ` (N)` to each platform output template before `%(ext)s`. `_rename_audio_output()` removes that suffix from the intermediate stem, appends the quality label, then re-appends the suffix so the final form is `Title [quality] (N).ext`.

- [ ] **Step 6: Preserve richer failed events in `download_tasks()`**

Catch `DownloadFailure` per worker and emit `failed` with `public_error(error)` instead of `{"error": "下载失败"}`. Catch `DownloadCancelled` as event `cancelled`. Keep results in original input order and retain the 3/2 concurrency tests.

Create one process logger with `get_download_logger()` and write `started`, `completed`, `failed`, and `cancelled` events for CLI/shared-batch execution. Include only sanitized platform, media type, audio format, speed mode, task index, attempt number, elapsed time, public error fields, and the separately redacted technical detail.

- [ ] **Step 7: Run downloader regressions**

Run: `venv/bin/python -m unittest tests.test_downloader_errors tests.test_parallel_downloads tests.test_bilibili_acceleration tests.test_bilibili_support -v`

Expected: all tests PASS.

- [ ] **Step 8: Commit Task 4**

```bash
git add task_control.py downloader.py tests/test_downloader_errors.py tests/test_parallel_downloads.py
git commit -m "feat: add cooperative cancellation and safe redownload names"
```

---

### Task 5: In-Memory Task Manager, Retry, and Redownload

**Files:**
- Modify: `task_control.py`
- Create: `tests/test_task_control.py`

**Interfaces:**
- Produces: immutable `TaskSeed(platform, url, title=None, position=None)`.
- Produces: `TaskManager.create_batch(entries: list[TaskSeed], media_type, audio_format, speed_mode)`, `snapshot(batch_id)`, `cancel(batch_id, task_id)`, `retry(batch_id, task_id)`, `retry_failed(batch_id)`, `redownload(batch_id, task_id)`, `wait_for_idle(timeout=5)`, and `shutdown(wait=True)`.
- Consumes: an injected runner with the `download_video()` keyword interface from Task 4.
- Consumes: `get_download_logger()` and `log_download_event()` for every state transition and attempt terminal event.
- Produces public task fields: `id`, `index`, `status`, `attempt_count`, `attempts`, `can_cancel`, `can_retry`, `can_redownload`, `error`, `result`, and progress fields.

- [ ] **Step 1: Write failing task-manager state and concurrency tests**

```python
# tests/test_task_control.py
import threading
import time
import unittest

from download_errors import DownloadCancelled, DownloadErrorInfo, DownloadFailure
from task_control import TaskManager, TaskSeed


class TaskManagerTests(unittest.TestCase):
    def test_queued_task_cancels_without_calling_runner(self):
        release = threading.Event()
        calls = []
        def runner(url, **kwargs):
            calls.append(url)
            release.wait(1)
            return {"title": url, "filepath": f"/tmp/{len(calls)}.mp4"}
        manager = TaskManager(runner, max_workers=1)
        batch = manager.create_batch([
            TaskSeed("youtube", "https://youtu.be/one", "One", 1),
            TaskSeed("youtube", "https://youtu.be/two", "Two", 2),
        ], "video", "mp3", "standard")
        second_id = batch["tasks"][1]["id"]
        manager.cancel(batch["id"], second_id)
        release.set()
        manager.shutdown()
        self.assertEqual(manager.snapshot(batch["id"])["tasks"][1]["status"], "cancelled")
        self.assertEqual(calls, ["https://youtu.be/one"])

    def test_retry_reuses_task_and_appends_attempt(self):
        attempts = 0
        def runner(url, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise DownloadFailure(DownloadErrorInfo("NETWORK_TIMEOUT", "超时", "重试", True, "timeout"))
            return {"title": "ok", "filepath": "/tmp/ok.mp4"}
        manager = TaskManager(runner, max_workers=1)
        batch = manager.create_batch([TaskSeed("youtube", "https://youtu.be/x", "X", 1)], "video", "mp3", "standard")
        manager.wait_for_idle()
        task_id = batch["tasks"][0]["id"]
        manager.retry(batch["id"], task_id)
        manager.wait_for_idle()
        task = manager.snapshot(batch["id"])["tasks"][0]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["attempt_count"], 2)
        self.assertEqual(len(task["attempts"]), 2)

    def test_turbo_mode_event_closes_cancel_window(self):
        entered = threading.Event()
        release = threading.Event()
        def runner(url, progress_callback=None, **kwargs):
            progress_callback("mode", {"speed_mode": "turbo", "turbo_fallback": False})
            progress_callback("mode", {"speed_mode": "standard", "turbo_fallback": True})
            entered.set()
            release.wait(1)
            return {"title": "done", "filepath": "/tmp/done.mp4"}
        manager = TaskManager(runner, max_workers=1)
        batch = manager.create_batch([TaskSeed("bilibili", "https://b23.tv/x", "X", 1)], "video", "mp3", "turbo")
        self.assertTrue(entered.wait(1))
        task_id = batch["tasks"][0]["id"]
        with self.assertRaisesRegex(ValueError, "极速任务不可取消"):
            manager.cancel(batch["id"], task_id)
        release.set()
        manager.shutdown()
```

- [ ] **Step 2: Run task-manager tests and verify missing methods**

Run: `venv/bin/python -m unittest tests.test_task_control -v`

Expected: FAIL because `TaskManager` is not implemented.

- [ ] **Step 3: Implement batch/task storage and a single global executor**

Implement `TaskManager` with one `RLock`, one `ThreadPoolExecutor(max_workers=3)`, one Bilibili `BoundedSemaphore(2)`, and a maximum of 100 retained batches. Store `CancellationToken` and Future objects in private dictionaries, not in JSON snapshots.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class TaskSeed:
    platform: str
    url: str
    title: str | None = None
    position: int | None = None
```

The runner receives:

```python
result = self._runner(
    task["url"],
    platform=task["platform"],
    progress_callback=relay,
    media_type=task["media_type"],
    audio_format=task["audio_format"],
    speed_mode=task["speed_mode"],
    cancel_token=token,
    output_version=task["output_version"],
    raise_errors=True,
)
```

Start an attempt immediately before invoking the runner; finish it exactly once with `completed`, `failed`, or `cancelled`. Recompute `active`, `queued`, `completed`, `failed`, `cancelled`, and `all_done` from current task states whenever a snapshot is requested.

Log batch creation, attempt start, mode transition, completion, failure, cancellation, retry, and redownload. Public snapshots contain only `public_error()` fields; `technical_detail` is sent through `redact_value()` to the JSONL logger and never stored in the browser-facing dictionary.

- [ ] **Step 4: Implement operation guards and retries**

```python
def retry(self, batch_id, task_id):
    with self._lock:
        task = self._require_task(batch_id, task_id)
        if task["status"] not in {"failed", "cancelled"}:
            raise ValueError("当前任务状态不可重试")
        if task["status"] == "failed" and not task["error"]["retryable"]:
            raise ValueError("该错误不支持重试")
        task["status"] = "queued"
        task["error"] = None
        task["progress"] = None
        self._submit_locked(batch_id, task)
        return self._public_task(task)
```

`retry_failed()` selects only `failed` tasks whose error payload has `retryable=true`. `cancel()` immediately terminalizes queued tasks; running standard tasks only set the token. Mode event `turbo` changes the state to `running_uninterruptible` and permanently disables cancellation for that attempt.

- [ ] **Step 5: Implement redownload and version reservation**

`redownload()` accepts only completed tasks, creates a new task ID in the same batch, copies its settings, and selects the first unreserved output version greater than one. Use the completed task filepath plus an in-memory reservation set to prevent two concurrent clicks receiving the same version.

- [ ] **Step 6: Add tests for batch counts, retry-all, 3/2 concurrency, cleanup, and redownload versions**

Add explicit tests asserting:

```python
self.assertEqual(snapshot["completed"], 1)
self.assertEqual(snapshot["failed"], 0)
self.assertEqual(snapshot["cancelled"], 1)
self.assertTrue(snapshot["all_done"])
self.assertEqual([task["output_version"] for task in redownloads], [2, 3])
self.assertLessEqual(maximum_active, 3)
self.assertLessEqual(maximum_bilibili, 2)
```

Also create 101 completed batches and assert the oldest completed batch is pruned while an active batch is retained. Capture the fake logger events and assert that a failed attempt logs its code but public snapshots do not contain `technical_detail`.

- [ ] **Step 7: Run task-manager tests**

Run: `venv/bin/python -m unittest tests.test_task_control -v`

Expected: all tests PASS with no leaked executor threads.

- [ ] **Step 8: Commit Task 5**

```bash
git add task_control.py tests/test_task_control.py
git commit -m "feat: manage cancel retry and redownload task states"
```

---

### Task 6: Flask Preview, Submission, and Task Operation APIs

**Files:**
- Modify: `app.py`
- Modify: `tests/test_web_progress.py`

**Interfaces:**
- Consumes: `PreviewStore`, `resolve_inputs`, `select_preview_entries`, `TaskManager`, and public structured errors.
- Produces: `POST /api/preview`, extended `POST /api/download`, four task-operation endpoints, and richer `GET /api/batch/<batch_id>`.

- [ ] **Step 1: Write failing Flask API tests**

```python
# append to tests/test_web_progress.py
class WebTaskOperationApiTests(unittest.TestCase):
    def setUp(self):
        self.client = web_app.app.test_client()

    def test_preview_returns_collection_entries(self):
        preview = {
            "preview_id": "preview-1",
            "title": "List",
            "platform": "youtube",
            "is_single": False,
            "requires_selection": True,
            "entries": [{"id": "1:a", "title": "A", "selectable": True}],
        }
        with patch("app.resolve_inputs") as resolve:
            resolve.return_value.to_dict.return_value = preview
            response = self.client.post(
                "/api/preview",
                json={"inputs": ["https://youtube.com/playlist?list=x"]},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["preview_id"], "preview-1")

    def test_preview_submission_rejects_more_than_100(self):
        response = self.client.post("/api/download", json={
            "preview_id": "preview-1",
            "selected_entry_ids": [str(index) for index in range(101)],
            "media_type": "video",
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error_code"], "INVALID_REQUEST")

    def test_cancel_conflict_returns_409_structured_error(self):
        with patch.object(web_app.task_manager, "cancel", side_effect=ValueError("极速任务不可取消")):
            response = self.client.post("/api/batch/b/task/t/cancel")
        self.assertEqual(response.status_code, 409)
        self.assertIn("error_code", response.get_json())

    def test_audio_api_accepts_source_and_wav(self):
        for value in ("source", "wav"):
            with self.subTest(value=value), patch.object(web_app.task_manager, "create_batch") as create:
                create.return_value = {"id": "b", "total": 1}
                response = self.client.post("/api/download", json={
                    "urls": ["https://youtu.be/example"],
                    "media_type": "audio",
                    "audio_format": value,
                })
                self.assertEqual(response.status_code, 200)
```

- [ ] **Step 2: Run focused Web tests and verify missing endpoints/manager**

Run: `venv/bin/python -m unittest tests.test_web_progress.WebTaskOperationApiTests -v`

Expected: FAIL with 404 or missing `task_manager`.

- [ ] **Step 3: Replace per-batch threads with process-wide stores**

At module initialization:

```python
preview_store = PreviewStore(ttl_seconds=1800)
task_manager = TaskManager(
    download_video,
    max_workers=MAX_PARALLEL_DOWNLOADS,
    max_bilibili=MAX_PARALLEL_BILIBILI_DOWNLOADS,
    max_batches=MAX_STORED_BATCHES,
)
```

Keep compatibility helper functions only where existing tests or imports need them; delegate their state to `task_manager` rather than maintaining a second queue.

Rewrite existing `WebDownloadApiTests`, `WebTurboApiTests`, and batch-pruning tests to patch `app.task_manager.create_batch()` and inspect returned public snapshots instead of asserting that `threading.Thread` was started. Preserve their checks for default video/MP3/standard values, source-FLAC forwarding, turbo forwarding, invalid JSON, invalid URL lists, and 100-batch pruning.

- [ ] **Step 4: Implement preview and dual-mode submission**

`POST /api/preview` accepts only a JSON object containing a non-empty `inputs` list of strings. Resolve all inputs into one ordered preview, store it, and return its public representation. `POST /api/download` accepts either the existing `urls` list or `preview_id + selected_entry_ids`, never both. Validate media/speed/audio enums before resolving tasks.

Convert every accepted input to `TaskSeed`: direct URLs use `make_task()` and a `None` title/position; selected preview entries copy platform, URL, title, and position. Reject malformed requests as `INVALID_REQUEST`, recognized-but-unsupported platform URLs as `UNSUPPORTED_PLATFORM`, and malformed/non-URL input as `INVALID_URL`.

- [ ] **Step 5: Implement operation endpoints with exact status mapping**

```python
@app.post("/api/batch/<batch_id>/task/<task_id>/cancel")
def api_cancel_task(batch_id, task_id):
    return _task_operation(task_manager.cancel, batch_id, task_id)

@app.post("/api/batch/<batch_id>/task/<task_id>/retry")
def api_retry_task(batch_id, task_id):
    return _task_operation(task_manager.retry, batch_id, task_id)

@app.post("/api/batch/<batch_id>/task/<task_id>/redownload")
def api_redownload_task(batch_id, task_id):
    return _task_operation(task_manager.redownload, batch_id, task_id)

@app.post("/api/batch/<batch_id>/retry-failed")
def api_retry_failed(batch_id):
    return jsonify(task_manager.retry_failed(batch_id))
```

Map missing batch/task to 404, validation problems to 400, and valid resources in conflicting states to 409. Every error body uses the public structured-error shape.

- [ ] **Step 6: Run all Web API tests**

Run: `venv/bin/python -m unittest tests.test_web_progress -v`

Expected: all tests PASS; old `/api/download` payloads still work.

- [ ] **Step 7: Commit Task 6**

```bash
git add app.py tests/test_web_progress.py
git commit -m "feat: expose collection and task operation apis"
```

---

### Task 7: Web Collection Preview and Task Controls

**Files:**
- Modify: `templates/index.html`
- Modify: `tests/test_web_progress.py`

**Interfaces:**
- Consumes: Task 6 API payloads and operation URLs.
- Produces: `previewInput(mediaType)`, `renderCollectionPreview(preview, mediaType)`, `submitPreview(mediaType)`, `operateTask(action, taskId)`, and `retryFailedTasks()`.

- [ ] **Step 1: Add failing frontend contract tests**

```python
def test_frontend_has_four_audio_formats_and_collection_preview(self):
    html = Path("templates/index.html").read_text(encoding="utf-8")
    for value in ("mp3", "flac", "source", "wav"):
        self.assertIn(f'value="{value}"', html)
    self.assertIn('id="collectionPreview"', html)
    self.assertIn("renderCollectionPreview", html)
    self.assertIn("selectedEntryIds", html)
    self.assertIn("最多选择 100 项", html)

def test_frontend_has_cancel_retry_redownload_and_retry_failed_actions(self):
    html = Path("templates/index.html").read_text(encoding="utf-8")
    self.assertIn("operateTask('cancel'", html)
    self.assertIn("operateTask('retry'", html)
    self.assertIn("operateTask('redownload'", html)
    self.assertIn("retryFailedTasks", html)
    self.assertIn("极速任务不可取消", html)

def test_frontend_renders_structured_error_and_attempt_history(self):
    html = Path("templates/index.html").read_text(encoding="utf-8")
    self.assertIn("error_code", html)
    self.assertIn("suggestion", html)
    self.assertIn("attempt_count", html)
    self.assertIn("attempts", html)
```

- [ ] **Step 2: Run frontend contract tests and verify failure**

Run: `venv/bin/python -m unittest tests.test_web_progress.WebProgressStateTests -v`

Expected: FAIL because preview and task-operation controls are absent.

- [ ] **Step 3: Add the four-format audio selector and explanatory copy**

Keep MP3 checked by default. Add source-audio copy stating that the extension depends on the source stream, and WAV copy stating that the file is large and does not improve the source quality. Keep the video card spacer so both columns retain matching row height.

- [ ] **Step 4: Implement preview state and selection**

Use one preview panel below the two input cards. The currently submitted section determines inherited settings. Render a checkbox per selectable entry, a select-all checkbox, selected count, and submit button. Disable selection after 100 checks and show a clear counter rather than silently truncating.

```javascript
let currentPreview = null;
let currentPreviewMediaType = null;

function selectedEntryIds() {
  return [...document.querySelectorAll('[data-preview-entry]:checked')]
    .map(input => input.value);
}

async function submitPreview(mediaType) {
  const selected = selectedEntryIds();
  if (!selected.length || selected.length > 100) {
    showError(selected.length ? '一次最多选择 100 项' : '请至少选择一个条目');
    return;
  }
  await submitDownloadRequest({
    preview_id: currentPreview.preview_id,
    selected_entry_ids: selected,
    media_type: mediaType,
    speed_mode: getSpeedMode(mediaType),
    audio_format: getAudioFormat(mediaType),
  });
}
```

`previewInput(mediaType)` sends every non-empty line from the active textarea as the `inputs` array. If `requires_selection` is false, immediately submit all returned entry IDs to preserve the current one-click flow. If it is true, render the selection panel before submission.

- [ ] **Step 5: Render task actions from server capability fields**

Show cancel only for `can_cancel`, retry only for `can_retry`, and redownload only for `can_redownload`. For `running_uninterruptible`, render the aria2c explanation. Operation POSTs reuse the existing polling loop and disable only the clicked button until a response arrives.

- [ ] **Step 6: Render structured errors and attempt history**

Render `error.error_code`, `error.message`, and `error.suggestion` as text content, never HTML. Use `<details>` for `attempts` and show attempt number, start/end time, and terminal status. Update metrics to read server-provided `active`, `queued`, `completed`, `failed`, and `cancelled`.

- [ ] **Step 7: Run template syntax and Web tests**

Run: `venv/bin/python -m unittest tests.test_web_progress -v`

Run:

```bash
venv/bin/python -c "from pathlib import Path; text=Path('templates/index.html').read_text(encoding='utf-8'); Path('/tmp/multiple-video-downloader-index.js').write_text(text.split('<script>',1)[1].split('</script>',1)[0], encoding='utf-8')"
node --check /tmp/multiple-video-downloader-index.js
```

Expected: Python tests PASS and Node reports no syntax errors.

- [ ] **Step 8: Commit Task 7**

```bash
git add templates/index.html tests/test_web_progress.py
git commit -m "feat: add collection preview and task controls to web ui"
```

---

### Task 8: CLI Audio Formats, Collection Selection, and Error Output

**Files:**
- Modify: `main.py`
- Modify: `tests/test_cli_audio.py`

**Interfaces:**
- Consumes: `SOURCE`, `WAV`, `resolve_collection`, `select_preview_entries`, and structured error formatting.
- Produces: `parse_command_line()` support for `--audio-format`, `--items`; `parse_item_selection(value, available_ids)`; `resolve_cli_tasks(inputs, item_selection=None, interactive=False)`.

- [ ] **Step 1: Write failing CLI parsing and selection tests**

```python
# tests/test_cli_audio.py
def test_parse_command_line_accepts_source_audio_and_wav(self):
    for value in (downloader.SOURCE, downloader.WAV):
        media, audio_format, speed, urls, item_selection = cli_main.parse_command_line([
            "--audio", "--audio-format", value, "https://youtu.be/x"
        ])
        self.assertEqual(media, downloader.AUDIO)
        self.assertEqual(audio_format, value)
        self.assertIsNone(item_selection)

def test_flac_alias_remains_compatible(self):
    media, audio_format, speed, urls, item_selection = cli_main.parse_command_line([
        "--audio", "--flac", "https://youtu.be/x"
    ])
    self.assertEqual(audio_format, downloader.FLAC)

def test_parse_item_selection_supports_all_ranges_and_limit(self):
    available = [str(index) for index in range(1, 102)]
    self.assertEqual(cli_main.parse_item_selection("1,3-5", available), ["1", "3", "4", "5"])
    self.assertEqual(len(cli_main.parse_item_selection("all", available[:100])), 100)
    with self.assertRaisesRegex(ValueError, "最多选择 100"):
        cli_main.parse_item_selection("all", available)

def test_noninteractive_collection_requires_items(self):
    with patch("main.resolve_collection") as resolve:
        resolve.return_value = cli_main.CollectionPreview(
            "preview",
            "List",
            "youtube",
            (),
            False,
        )
        with self.assertRaisesRegex(ValueError, "--items"):
            cli_main.resolve_cli_tasks(
                ["https://youtube.com/playlist?list=x"],
                item_selection=None,
                interactive=False,
            )
```

- [ ] **Step 2: Run CLI tests and verify tuple/signature failures**

Run: `venv/bin/python -m unittest tests.test_cli_audio -v`

Expected: FAIL because the new formats and item selection are absent.

- [ ] **Step 3: Replace flag scanning with a small deterministic parser**

Keep the return values explicit: `(media_type, audio_format, speed_mode, urls, item_selection)`. Update every existing parser test and the `main()` caller to unpack all five values. `--audio-format` and `--items` each require a following value. Reject `--audio-format` without `--audio`, conflicting `--flac` plus a non-FLAC format, unknown flags, and invalid formats. Preserve `--audio`, `--flac`, and `--turbo` behavior.

- [ ] **Step 4: Expand interactive audio and collection choices**

Print four numbered audio formats and default to MP3. When a collection is found in interactive mode, print ordered titles and accept `all` or comma/range syntax. In command-line mode, a collection without `--items` exits with a Chinese instruction rather than downloading everything.

- [ ] **Step 5: Print structured errors without secrets**

Use `format_cli_error()` for task failures. Display actual output format and source codec for source/WAV results; retain the FLAC fallback message only when `audio_format_fallback=true`.

- [ ] **Step 6: Run CLI and downloader regressions**

Run: `venv/bin/python -m unittest tests.test_cli_audio tests.test_downloader_errors tests.test_parallel_downloads -v`

Expected: all tests PASS.

- [ ] **Step 7: Commit Task 8**

```bash
git add main.py tests/test_cli_audio.py
git commit -m "feat: extend cli audio and collection selection"
```

---

### Task 9: Documentation, Integration, and End-to-End Verification

**Files:**
- Modify: `README.md`
- Modify: tests only if integration evidence exposes a real uncovered regression

**Interfaces:**
- Consumes: all prior task behavior.
- Produces: complete user instructions and verification evidence; no new runtime interface.

- [ ] **Step 1: Add README assertions before editing documentation**

```python
# add to WebConfigurationTests in tests/test_web_progress.py
def test_readme_documents_new_task_collection_and_audio_features(self):
    readme = Path("README.md").read_text(encoding="utf-8")
    for text in (
        "取消、重试与重新下载",
        "播放列表、合集与分 P",
        "原始音频",
        "WAV",
        "logs/downloader.jsonl",
        "浏览器扩展",
    ):
        self.assertIn(text, readme)
```

- [ ] **Step 2: Run the README test and verify failure**

Run: `venv/bin/python -m unittest tests.test_web_progress.WebConfigurationTests.test_readme_documents_new_task_collection_and_audio_features -v`

Expected: FAIL until README contains the new sections.

- [ ] **Step 3: Update README with exact user workflows**

Document:

- Web preview/select/submit flow and 100-item limit.
- Standard cancellation and aria2c non-cancellable behavior.
- Retry, retry-all, and redownload filename suffixes.
- MP3 V0, real source FLAC with MP3 fallback, source audio extensions, and WAV caveat.
- Error-code display, log path, rotation, and privacy redaction.
- CLI `--audio-format` and `--items` examples while retaining `--audio --flac`.
- Supported and excluded collection types.
- Browser extension work: MV3 popup, service worker, context menu, localhost API, pairing token, minimum permissions, notifications, packaging, Safari/Firefox differences.

- [ ] **Step 4: Run the full automated suite**

Run: `venv/bin/python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 5: Run static and syntax verification**

Run: `venv/bin/python -m compileall app.py downloader.py main.py bilibili_acceleration.py task_control.py collection_resolver.py download_errors.py download_logging.py tests`

Expected: command exits 0.

Run: `venv/bin/python -c "from pathlib import Path; text=Path('templates/index.html').read_text(encoding='utf-8'); Path('/tmp/multiple-video-downloader-index.js').write_text(text.split('<script>',1)[1].split('</script>',1)[0], encoding='utf-8')" && node --check /tmp/multiple-video-downloader-index.js`

Expected: command exits 0.

Run: `git diff --check`

Expected: no output and exit 0.

- [ ] **Step 6: Verify API and task operations with Flask test client**

Run: `venv/bin/python -m unittest tests.test_web_progress.WebTaskOperationApiTests tests.test_task_control.TaskManagerTests -v`

Expected: preview, selected submission, standard cancellation, retry, retry-all, redownload, and aria2c conflict cases all PASS with their asserted HTTP 200/400/404/409 mappings and task counts.

- [ ] **Step 7: Verify real downloads without touching existing files**

First record the existing download manifest with BSD-compatible `stat`:

```bash
find downloads -type f -exec stat -f '%N\t%z\t%m' {} \; | sort > /tmp/mvd-downloads-before.txt
```

Set user-authorized smoke URLs. The public YouTube test clip is the default; Instagram is optional because access depends on the user's current Cookie.

```bash
export MVD_SMOKE_YOUTUBE_URL="https://www.youtube.com/watch?v=jNQXAC9IVRw"
export MVD_SMOKE_BILIBILI_URL="https://www.bilibili.com/video/BV1GJ411x7h7"
export MVD_SMOKE_INSTAGRAM_URL=""
export MVD_SMOKE_DIR="$(mktemp -d)"
```

Run each format in a separate process so `DOWNLOADS_DIR` is patched only in memory:

```bash
MVD_FORMAT=video MVD_URL="$MVD_SMOKE_YOUTUBE_URL" venv/bin/python -c "import os; from pathlib import Path; import downloader; downloader.DOWNLOADS_DIR=Path(os.environ['MVD_SMOKE_DIR']); result=downloader.download_video(os.environ['MVD_URL'], media_type='video', raise_errors=True); print(result['filepath'])"
MVD_FORMAT=mp3 MVD_URL="$MVD_SMOKE_YOUTUBE_URL" venv/bin/python -c "import os; from pathlib import Path; import downloader; downloader.DOWNLOADS_DIR=Path(os.environ['MVD_SMOKE_DIR']); result=downloader.download_video(os.environ['MVD_URL'], media_type='audio', audio_format='mp3', output_version=2, raise_errors=True); print(result['filepath'])"
MVD_FORMAT=source MVD_URL="$MVD_SMOKE_YOUTUBE_URL" venv/bin/python -c "import os; from pathlib import Path; import downloader; downloader.DOWNLOADS_DIR=Path(os.environ['MVD_SMOKE_DIR']); result=downloader.download_video(os.environ['MVD_URL'], media_type='audio', audio_format='source', output_version=3, raise_errors=True); print(result['filepath'])"
MVD_FORMAT=wav MVD_URL="$MVD_SMOKE_YOUTUBE_URL" venv/bin/python -c "import os; from pathlib import Path; import downloader; downloader.DOWNLOADS_DIR=Path(os.environ['MVD_SMOKE_DIR']); result=downloader.download_video(os.environ['MVD_URL'], media_type='audio', audio_format='wav', output_version=4, raise_errors=True); print(result['filepath'])"
MVD_FORMAT=video MVD_URL="$MVD_SMOKE_BILIBILI_URL" venv/bin/python -c "import os; from pathlib import Path; import downloader; downloader.DOWNLOADS_DIR=Path(os.environ['MVD_SMOKE_DIR']); result=downloader.download_video(os.environ['MVD_URL'], media_type='video', speed_mode='standard', raise_errors=True); print(result['filepath'])"
```

If `MVD_SMOKE_INSTAGRAM_URL` is non-empty, run the same temporary-directory video command with that URL. If it returns `AUTH_REQUIRED`, report the current Cookie limitation without copying or modifying Cookie files. Let any manually enabled aria2c sample finish.

Validate every output:

```bash
find "$MVD_SMOKE_DIR" -type f -exec ffprobe -v error -show_entries format=filename,duration,size -show_entries stream=codec_type,codec_name -of json {} \;
```

Expected: each produced media has a nonzero size, positive duration, and the expected video/audio stream. The source output retains its selected codec; WAV reports PCM audio.

- [ ] **Step 8: Verify the existing downloads directory is unchanged**

After Step 7 run:

```bash
find downloads -type f -exec stat -f '%N\t%z\t%m' {} \; | sort > /tmp/mvd-downloads-after.txt
cmp /tmp/mvd-downloads-before.txt /tmp/mvd-downloads-after.txt
```

Expected: `cmp` exits 0 with no output.

- [ ] **Step 9: Perform browser QA on port 8233**

Restart only the Flask process whose command and cwd match this repository. Verify desktop and narrow viewport behavior for separate inputs, four audio formats, collection preview, 100-item counter, cancel/retry/redownload actions, attempt details, structured errors, aria2c non-cancellable copy, and reduced-motion behavior.

- [ ] **Step 10: Commit Task 9**

```bash
git add README.md tests/test_web_progress.py
git commit -m "docs: explain task controls collections and audio outputs"
```

- [ ] **Step 11: Final repository check**

Run: `git status --short`

Expected: no output.

Run: `git log -9 --oneline`

Expected: the task commits appear in dependency order and no unrelated user files are included.
