# Bilibili Adaptive CDN and aria2 Turbo Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Bilibili-only adaptive CDN/chunk selection for files over 50 MiB and an opt-in aria2c turbo mode for Web video, Web audio, and CLI downloads, with safe automatic fallback.

**Architecture:** Put Bilibili response adaptation, selected-stream inspection, range probing, and the 30-minute single-flight cache in a focused `bilibili_acceleration.py` module. Keep orchestration in `downloader.py`: Bilibili uses one metadata extraction followed by yt-dlp processing, while YouTube and Instagram retain their existing one-step path. Propagate a strict `speed_mode` enum through CLI and Flask, and expose aria2c availability to two independent front-end switches.

**Tech Stack:** Python 3.14, yt-dlp 2026.06.09, Flask, `unittest`, vanilla HTML/CSS/JavaScript, FFmpeg/FFprobe, aria2c/Homebrew

## Global Constraints

- Create the execution branch in an isolated worktree with the `using-git-worktrees` skill before changing production code.
- Use TDD for every behavior change: write the focused failing test, observe the expected failure, implement the smallest production change, and rerun focused tests.
- Keep `MAX_PARALLEL_DOWNLOADS = 3` and `MAX_PARALLEL_BILIBILI_DOWNLOADS = 2` unchanged.
- Keep `standard` as the default speed mode and preserve every existing call that omits `speed_mode`.
- Apply CDN probing and aria2c only to Bilibili; YouTube and Instagram options and live progress remain unchanged.
- Treat a task as large only when every selected stream has a positive known size and the video-plus-audio or audio-only sum is greater than 50 MiB.
- Small or unknown-size tasks use the current 10 MiB `http_chunk_size` without probing.
- Probe at most 4 Bilibili-provided HTTPS CDN hosts with at most 512 KiB per host; compare 4 MiB and 10 MiB chunk samples only on the chosen host.
- Cache the chosen host and chunk size in memory for 30 minutes, keyed by the sorted candidate-host tuple, with single-flight concurrency.
- Never synthesize CDN hostnames and never log signed URLs, cookies, or sensitive headers.
- aria2c turbo mode uses at most 4 connections per task and automatically falls back to standard mode on aria2-specific failure.
- Web turbo progress displays `高速下载中`; standard mode retains speed, percentage, and ETA.
- Update Web, CLI, README, regression tests, and run instructions together.
- Do not read, print, stage, or commit `bilibili_cookies.txt`.

## File Map

- Create `bilibili_acceleration.py`: Bilibili extractor adapter, selected-stream helpers, probe/cache policy, speed-mode constants, and aria2 capability/configuration helpers.
- Create `tests/test_bilibili_acceleration.py`: isolated unit tests for adapter, threshold, probing, cache, URL selection, and aria2 configuration.
- Modify `downloader.py`: speed-mode validation, two-stage Bilibili orchestration, progress mode events, fallback attempts, and non-sensitive result metadata.
- Modify `app.py`: speed-mode API validation/propagation, capability endpoint, and task mode state.
- Modify `templates/index.html`: two independent turbo switches, capability loading, simplified turbo status, and fallback display.
- Modify `main.py`: `--turbo`, interactive turbo choice, unavailable warning, and mode summary.
- Modify `tests/test_bilibili_support.py`, `tests/test_parallel_downloads.py`, `tests/test_web_progress.py`, and `tests/test_cli_audio.py`: surface and regression coverage.
- Modify `README.md`: aria2 installation, 50 MiB policy, Web/CLI usage, cache, fallback, and performance caveats.

---

### Task 1: Preserve Bilibili Main and Backup CDN URLs Per Format

**Files:**
- Create: `bilibili_acceleration.py`
- Create: `tests/test_bilibili_acceleration.py`

**Interfaces:**
- Consumes: yt-dlp `BilibiliIE.extract_formats(play_info: dict) -> list[dict]` and `YoutubeDL.add_info_extractor()`.
- Produces: `CDN_CANDIDATES_FIELD`, `BilibiliIE`, `enrich_bilibili_formats(play_info, formats) -> list[dict]`, and `register_bilibili_extractor(ydl) -> None`.

- [ ] **Step 1: Write failing adapter tests**

Create `tests/test_bilibili_acceleration.py` with:

```python
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
        self.assertIsInstance(extractor, acceleration.BilibiliIE)
```

- [ ] **Step 2: Run the adapter tests and verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_bilibili_acceleration.BilibiliExtractorAdapterTests -v
```

Expected: import fails with `ModuleNotFoundError: No module named 'bilibili_acceleration'`.

- [ ] **Step 3: Implement the instance-scoped extractor adapter**

Create `bilibili_acceleration.py` with these definitions:

```python
from urllib.parse import urlparse

from yt_dlp.extractor.bilibili import BilibiliIE as YtdlpBilibiliIE

CDN_CANDIDATES_FIELD = "_bilibili_cdn_candidates"


def _https_candidates(stream: dict) -> tuple[str, ...]:
    values = []
    for key in ("baseUrl", "base_url", "url"):
        value = stream.get(key)
        if isinstance(value, str):
            values.append(value)
            break
    for key in ("backupUrl", "backup_url", "backup_urls"):
        backups = stream.get(key)
        if isinstance(backups, str):
            values.append(backups)
        elif isinstance(backups, list):
            values.extend(value for value in backups if isinstance(value, str))

    result = []
    for value in values:
        try:
            is_https = urlparse(value).scheme.lower() == "https"
        except ValueError:
            is_https = False
        if is_https and value not in result:
            result.append(value)
    return tuple(result)


def _dash_streams(play_info: dict) -> list[dict]:
    dash = play_info.get("dash")
    if not isinstance(dash, dict):
        raise TypeError("Bilibili dash data is not a mapping")

    streams = []
    for key in ("video", "audio"):
        values = dash.get(key) or []
        if isinstance(values, list):
            streams.extend(value for value in values if isinstance(value, dict))

    dolby = dash.get("dolby")
    if isinstance(dolby, dict):
        values = dolby.get("audio") or []
        if isinstance(values, list):
            streams.extend(value for value in values if isinstance(value, dict))

    flac = dash.get("flac")
    if isinstance(flac, dict) and isinstance(flac.get("audio"), dict):
        streams.append(flac["audio"])
    return streams


def enrich_bilibili_formats(play_info: dict, formats: list[dict]) -> list[dict]:
    try:
        by_primary_url = {}
        for stream in _dash_streams(play_info):
            candidates = _https_candidates(stream)
            if candidates:
                by_primary_url[candidates[0]] = candidates
    except (AttributeError, TypeError, ValueError):
        return formats

    for fmt in formats:
        candidates = by_primary_url.get(fmt.get("url"))
        if candidates:
            fmt[CDN_CANDIDATES_FIELD] = candidates
    return formats


class BilibiliIE(YtdlpBilibiliIE):
    def extract_formats(self, play_info):
        formats = super().extract_formats(play_info)
        return enrich_bilibili_formats(play_info, formats)


def register_bilibili_extractor(ydl) -> None:
    ydl.add_info_extractor(BilibiliIE())
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
venv/bin/python -m unittest tests.test_bilibili_acceleration.BilibiliExtractorAdapterTests -v
```

Expected: all three tests pass.

- [ ] **Step 5: Commit the adapter**

```bash
git add bilibili_acceleration.py tests/test_bilibili_acceleration.py
git commit -m "feat: preserve Bilibili CDN candidates"
```

---

### Task 2: Inspect Selected Streams and Apply a Chosen CDN Safely

**Files:**
- Modify: `bilibili_acceleration.py`
- Modify: `tests/test_bilibili_acceleration.py`

**Interfaces:**
- Consumes: processed yt-dlp info dictionaries containing either `requested_formats` or one selected format.
- Produces: `selected_formats(info) -> list[dict]`, `selected_size(info) -> int | None`, `candidate_hosts(info) -> dict[str, str]`, `primary_host(info) -> str | None`, and `apply_cdn_host(info, host) -> bool`.

- [ ] **Step 1: Write failing selected-stream tests**

Append:

```python
class SelectedStreamTests(unittest.TestCase):
    def test_video_size_is_sum_and_audio_size_is_single_stream(self):
        video_info = {"requested_formats": [
            {"url": "https://a.example/v", "filesize": 40 * 1024 * 1024},
            {"url": "https://a.example/a", "filesize_approx": 12 * 1024 * 1024},
        ]}
        audio_info = {"url": "https://a.example/a", "filesize": 8 * 1024 * 1024}

        self.assertEqual(acceleration.selected_size(video_info), 52 * 1024 * 1024)
        self.assertEqual(acceleration.selected_size(audio_info), 8 * 1024 * 1024)

    def test_unknown_or_non_positive_size_returns_none(self):
        self.assertIsNone(acceleration.selected_size({"url": "https://a.example/a"}))
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
            "primary.example", "b.example", "c.example", "d.example",
        ])

    def test_applies_host_to_each_stream_only_when_candidate_exists(self):
        info = {"requested_formats": [
            {
                "url": "https://primary.example/v",
                acceleration.CDN_CANDIDATES_FIELD: (
                    "https://primary.example/v", "https://fast.example/v",
                ),
            },
            {
                "url": "https://primary.example/a",
                acceleration.CDN_CANDIDATES_FIELD: (
                    "https://primary.example/a", "https://fast.example/a",
                ),
            },
        ]}

        changed = acceleration.apply_cdn_host(info, "fast.example")

        self.assertTrue(changed)
        self.assertEqual(
            [fmt["url"] for fmt in info["requested_formats"]],
            ["https://fast.example/v", "https://fast.example/a"],
        )
```

- [ ] **Step 2: Run the selected-stream tests and verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_bilibili_acceleration.SelectedStreamTests -v
```

Expected: fails because `selected_size`, `candidate_hosts`, and `apply_cdn_host` are absent.

- [ ] **Step 3: Implement selected-stream helpers**

Append to `bilibili_acceleration.py`:

```python
MAX_CDN_HOSTS = 4


def selected_formats(info: dict) -> list[dict]:
    requested = info.get("requested_formats")
    if isinstance(requested, list) and requested:
        return [fmt for fmt in requested if isinstance(fmt, dict)]
    return [info]


def selected_size(info: dict) -> int | None:
    total = 0
    for fmt in selected_formats(info):
        value = fmt.get("filesize") or fmt.get("filesize_approx")
        if not isinstance(value, (int, float)) or value <= 0:
            return None
        total += int(value)
    return total or None


def _host(url: object) -> str | None:
    if not isinstance(url, str):
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    return parsed.hostname.lower() if parsed.scheme == "https" and parsed.hostname else None


def _format_candidates(fmt: dict) -> tuple[str, ...]:
    stored = fmt.get(CDN_CANDIDATES_FIELD)
    values = stored if isinstance(stored, (list, tuple)) else (fmt.get("url"),)
    return tuple(value for value in values if _host(value))


def candidate_hosts(info: dict) -> dict[str, str]:
    result = {}
    for fmt in selected_formats(info):
        primary = fmt.get("url")
        if (host := _host(primary)) and host not in result:
            result[host] = primary
    for fmt in selected_formats(info):
        for url in _format_candidates(fmt):
            host = _host(url)
            if host and host not in result:
                result[host] = url
            if len(result) == MAX_CDN_HOSTS:
                return result
    return result


def primary_host(info: dict) -> str | None:
    formats = selected_formats(info)
    return _host(formats[0].get("url")) if formats else None


def apply_cdn_host(info: dict, host: str | None) -> bool:
    if not host:
        return False
    changed = False
    for fmt in selected_formats(info):
        selected = next(
            (url for url in _format_candidates(fmt) if _host(url) == host),
            None,
        )
        if selected and fmt.get("url") != selected:
            fmt["url"] = selected
            changed = True
    if "requested_formats" not in info and selected_formats(info):
        info["url"] = selected_formats(info)[0]["url"]
    return changed
```

- [ ] **Step 4: Run Tasks 1–2 tests and verify GREEN**

Run:

```bash
venv/bin/python -m unittest tests.test_bilibili_acceleration -v
```

Expected: all adapter and selected-stream tests pass.

- [ ] **Step 5: Commit selected-stream helpers**

```bash
git add bilibili_acceleration.py tests/test_bilibili_acceleration.py
git commit -m "feat: inspect selected Bilibili streams"
```

---

### Task 3: Add Range Probing and the 30-Minute Single-Flight Cache

**Files:**
- Modify: `bilibili_acceleration.py`
- Modify: `tests/test_bilibili_acceleration.py`

**Interfaces:**
- Consumes: `YoutubeDL.urlopen(Request)`, `selected_size()`, and `candidate_hosts()`.
- Produces: immutable `AccelerationPlan`, `CdnProbeCache.get_or_probe(key, probe)`, `measure_range()`, `build_acceleration_plan(ydl, info) -> AccelerationPlan`, and module singleton `CDN_PROBE_CACHE`.

- [ ] **Step 1: Write failing threshold, probe, and cache tests**

Add `import threading`, `import time`, `from urllib.parse import urlparse`, and change the mock import to `from unittest.mock import Mock, patch`, then append:

```python
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
            {"url": "https://a.example/a", "filesize": 50 * 1024 * 1024},
            {"url": "https://a.example/a"},
        ):
            with self.subTest(info=info), patch.object(
                acceleration, "measure_range"
            ) as measure:
                plan = acceleration.build_acceleration_plan(Mock(), info)
                self.assertFalse(plan.adaptive)
                self.assertEqual(plan.http_chunk_size, 10 * 1024 * 1024)
                measure.assert_not_called()

    def test_large_task_chooses_fastest_host_and_chunk(self):
        info = {
            "url": "https://slow.example/a",
            "filesize": 51 * 1024 * 1024,
            acceleration.CDN_CANDIDATES_FIELD: (
                "https://slow.example/a", "https://fast.example/a",
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
        with patch.object(acceleration, "measure_range", side_effect=fake_measure):
            plan = acceleration.build_acceleration_plan(Mock(), info, cache=cache)

        self.assertTrue(plan.adaptive)
        self.assertEqual(plan.cdn_host, "fast.example")
        self.assertEqual(plan.http_chunk_size, 4 * 1024 * 1024)

    def test_all_probe_failures_keep_primary_host_and_ten_mib_chunk(self):
        info = {
            "url": "https://primary.example/a",
            "filesize": 60 * 1024 * 1024,
            acceleration.CDN_CANDIDATES_FIELD: (
                "https://primary.example/a", "https://backup.example/a",
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
        factory = lambda: calls.append("probe") or acceleration.CdnChoice(
            "fast.example", 4 * 1024 * 1024,
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
            return acceleration.CdnChoice("fast.example", 10 * 1024 * 1024)

        def worker():
            barrier.wait()
            results.append(cache.get_or_probe(("fast.example",), factory))

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

        self.assertIsNone(acceleration.measure_range(ydl, "https://a.example/v", 10))
```

- [ ] **Step 2: Run the adaptive policy tests and verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_bilibili_acceleration.AdaptivePolicyTests -v
```

Expected: fails because `CdnProbeCache`, `CdnChoice`, `measure_range`, and `build_acceleration_plan` are absent.

- [ ] **Step 3: Implement immutable plans, range measurement, cache, and policy**

Add imports and definitions to `bilibili_acceleration.py`:

```python
import threading
import time
from dataclasses import dataclass
from typing import Callable

from yt_dlp.networking.common import Request

BILIBILI_HTTP_CHUNK_SIZE = 10 * 1024 * 1024
BILIBILI_SMALL_CHUNK_SIZE = 4 * 1024 * 1024
BILIBILI_LARGE_FILE_THRESHOLD = 50 * 1024 * 1024
CDN_PROBE_BYTES = 512 * 1024
CDN_CACHE_TTL_SECONDS = 30 * 60
CDN_PROBE_TIMEOUT_SECONDS = 3


@dataclass(frozen=True)
class CdnChoice:
    host: str | None
    http_chunk_size: int


@dataclass(frozen=True)
class AccelerationPlan:
    adaptive: bool
    cdn_host: str | None
    http_chunk_size: int


class CdnProbeCache:
    def __init__(self, ttl_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._lock = threading.Lock()
        self._entries = {}
        self._in_flight = {}

    def get_or_probe(self, hosts: tuple[str, ...], probe: Callable[[], CdnChoice]) -> CdnChoice:
        key = tuple(sorted(set(hosts)))
        while True:
            with self._lock:
                entry = self._entries.get(key)
                if entry and entry[0] > self.clock():
                    return entry[1]
                event = self._in_flight.get(key)
                if event is None:
                    event = self._in_flight[key] = threading.Event()
                    owner = True
                else:
                    owner = False
            if owner:
                break
            event.wait()

        try:
            choice = probe()
            with self._lock:
                self._entries[key] = (self.clock() + self.ttl_seconds, choice)
            return choice
        finally:
            with self._lock:
                self._in_flight.pop(key).set()


CDN_PROBE_CACHE = CdnProbeCache(CDN_CACHE_TTL_SECONDS)


def measure_range(ydl, url: str, size: int, start: int = 0, headers: dict | None = None) -> float | None:
    request_headers = dict(headers or {})
    request_headers["Range"] = f"bytes={start}-{start + size - 1}"
    request = Request(
        url,
        headers=request_headers,
        extensions={"timeout": CDN_PROBE_TIMEOUT_SECONDS},
    )
    started = time.monotonic()
    try:
        with ydl.urlopen(request) as response:
            if getattr(response, "status", None) != 206:
                return None
            if not str(getattr(response, "headers", {}).get("Content-Range", "")).startswith("bytes "):
                return None
            payload = response.read(size)
    except Exception:
        return None
    elapsed = time.monotonic() - started
    if not payload or elapsed <= 0:
        return None
    return len(payload) / elapsed


def _probe_choice(ydl, info: dict, hosts: dict[str, str]) -> CdnChoice:
    headers = info.get("http_headers")
    headers = headers if isinstance(headers, dict) else None
    successful = {}
    for host, url in hosts.items():
        speed = measure_range(ydl, url, CDN_PROBE_BYTES, headers=headers)
        if speed is not None:
            successful[host] = speed
    if not successful:
        return CdnChoice(primary_host(info), BILIBILI_HTTP_CHUNK_SIZE)

    fastest = max(successful, key=successful.get)
    url = hosts[fastest]
    small_speed = measure_range(
        ydl, url, BILIBILI_SMALL_CHUNK_SIZE, CDN_PROBE_BYTES, headers=headers,
    )
    normal_speed = measure_range(
        ydl,
        url,
        BILIBILI_HTTP_CHUNK_SIZE,
        CDN_PROBE_BYTES + BILIBILI_SMALL_CHUNK_SIZE,
        headers=headers,
    )
    chunk_size = (
        BILIBILI_SMALL_CHUNK_SIZE
        if small_speed is not None and normal_speed is not None and small_speed > normal_speed
        else BILIBILI_HTTP_CHUNK_SIZE
    )
    return CdnChoice(fastest, chunk_size)


def build_acceleration_plan(
    ydl,
    info: dict,
    cache: CdnProbeCache = CDN_PROBE_CACHE,
) -> AccelerationPlan:
    size = selected_size(info)
    original_host = primary_host(info)
    if size is None or size <= BILIBILI_LARGE_FILE_THRESHOLD:
        return AccelerationPlan(False, original_host, BILIBILI_HTTP_CHUNK_SIZE)

    hosts = candidate_hosts(info)
    if not hosts:
        return AccelerationPlan(False, original_host, BILIBILI_HTTP_CHUNK_SIZE)
    choice = cache.get_or_probe(
        tuple(hosts),
        lambda: _probe_choice(ydl, info, hosts),
    )
    return AccelerationPlan(True, choice.host, choice.http_chunk_size)
```

- [ ] **Step 4: Run the full acceleration unit module and verify GREEN**

Run:

```bash
venv/bin/python -m unittest tests.test_bilibili_acceleration -v
```

Expected: all tests pass, including one-probe single-flight behavior.

- [ ] **Step 5: Commit adaptive probing and cache**

```bash
git add bilibili_acceleration.py tests/test_bilibili_acceleration.py
git commit -m "feat: choose Bilibili CDN and chunk size"
```

---

### Task 4: Define Speed Modes and aria2c Configuration

**Files:**
- Modify: `bilibili_acceleration.py`
- Modify: `tests/test_bilibili_acceleration.py`

**Interfaces:**
- Consumes: `shutil.which("aria2c")` and yt-dlp option dictionaries.
- Produces: `STANDARD`, `TURBO`, `SPEED_MODES`, `aria2c_path() -> str | None`, `effective_speed_mode(platform, requested, executable) -> str`, and `configure_aria2(options, executable) -> None`.

- [ ] **Step 1: Write failing speed-mode and aria2 tests**

Append:

```python
class Aria2ModeTests(unittest.TestCase):
    def test_detects_aria2c_path(self):
        with patch("bilibili_acceleration.shutil.which", return_value="/opt/homebrew/bin/aria2c"):
            self.assertEqual(acceleration.aria2c_path(), "/opt/homebrew/bin/aria2c")

    def test_turbo_only_becomes_effective_for_bilibili_with_aria2(self):
        self.assertEqual(
            acceleration.effective_speed_mode("bilibili", "turbo", "/bin/aria2c"),
            acceleration.TURBO,
        )
        self.assertEqual(
            acceleration.effective_speed_mode("youtube", "turbo", "/bin/aria2c"),
            acceleration.STANDARD,
        )
        self.assertEqual(
            acceleration.effective_speed_mode("bilibili", "turbo", None),
            acceleration.STANDARD,
        )

    def test_configure_aria2_uses_four_connections(self):
        options = {}

        acceleration.configure_aria2(options, "/opt/homebrew/bin/aria2c")

        self.assertEqual(options["external_downloader"], {
            "http": "/opt/homebrew/bin/aria2c",
        })
        self.assertEqual(options["external_downloader_args"]["aria2c"], [
            "--max-connection-per-server=4",
            "--split=4",
            "--max-concurrent-downloads=4",
            "--min-split-size=1M",
        ])
```

- [ ] **Step 2: Run the mode tests and verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_bilibili_acceleration.Aria2ModeTests -v
```

Expected: fails because the speed-mode constants and helpers are absent.

- [ ] **Step 3: Implement strict modes and conservative aria2 options**

Add `import shutil` and:

```python
STANDARD = "standard"
TURBO = "turbo"
SPEED_MODES = {STANDARD, TURBO}


def aria2c_path() -> str | None:
    return shutil.which("aria2c")


def effective_speed_mode(platform: str, requested: str, executable: str | None) -> str:
    if requested not in SPEED_MODES:
        raise ValueError(f"不支持的速度模式: {requested}")
    return TURBO if platform == "bilibili" and requested == TURBO and executable else STANDARD


def configure_aria2(options: dict, executable: str) -> None:
    options["external_downloader"] = {"http": executable}
    options["external_downloader_args"] = {
        "aria2c": [
            "--max-connection-per-server=4",
            "--split=4",
            "--max-concurrent-downloads=4",
            "--min-split-size=1M",
        ],
    }
```

- [ ] **Step 4: Run all acceleration tests and verify GREEN**

Run:

```bash
venv/bin/python -m unittest tests.test_bilibili_acceleration -v
```

Expected: every test passes and standard mode has no external downloader side effect.

- [ ] **Step 5: Commit speed modes and aria2 options**

```bash
git add bilibili_acceleration.py tests/test_bilibili_acceleration.py
git commit -m "feat: configure optional aria2 turbo mode"
```

---

### Task 5: Integrate Two-Stage Bilibili Downloading and Safe Fallbacks

**Files:**
- Modify: `downloader.py:9-18,274-382,497-566`
- Modify: `tests/test_bilibili_support.py:108-184`
- Modify: `tests/test_downloader_errors.py`

**Interfaces:**
- Consumes: `register_bilibili_extractor()`, `build_acceleration_plan()`, `apply_cdn_host()`, `configure_aria2()`, `effective_speed_mode()`, and existing `_resolve_output_path()`.
- Produces: `_build_ydl_options(..., speed_mode=STANDARD, aria2_executable=None) -> dict`, `_download_bilibili(...) -> DownloadResult | None`, mode progress events, and result fields `speed_mode_requested`, `speed_mode_used`, `turbo_fallback`, `cdn_host`, and `http_chunk_size`.

- [ ] **Step 1: Write failing Bilibili option and fallback tests**

Add imports `copy` and `Mock`, then add these focused tests. The fake `YoutubeDL` sequence models metadata extraction, a failing aria2 attempt, and a successful native fallback without using the network:

```python
class BilibiliTurboDownloadTests(unittest.TestCase):
    def test_turbo_options_only_apply_to_bilibili(self):
        output_dir = Path("/tmp/downloads")
        bili = downloader._build_ydl_options(
            downloader.BILIBILI,
            output_dir,
            1,
            1,
            speed_mode=downloader.TURBO,
            aria2_executable="/bin/aria2c",
        )
        youtube = downloader._build_ydl_options(
            downloader.YOUTUBE,
            output_dir,
            1,
            1,
            speed_mode=downloader.TURBO,
            aria2_executable="/bin/aria2c",
        )

        self.assertEqual(bili["external_downloader"]["http"], "/bin/aria2c")
        self.assertNotIn("external_downloader", youtube)

    def test_unknown_speed_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "速度模式"):
            downloader._build_ydl_options(
                downloader.BILIBILI,
                Path("/tmp/downloads"),
                1,
                1,
                speed_mode="warp",
            )

    def test_aria2_failure_retries_once_with_standard_mode(self):
        info = {
            "id": "BV1TEST",
            "title": "Example",
            "url": "https://primary.example/audio.m4s?token=secret",
            "filesize": 60 * 1024 * 1024,
            "ext": "m4a",
        }
        events = []
        attempts = []

        def fake_attempt(prepared_info, options, output_dir):
            attempts.append(options.get("external_downloader"))
            if len(attempts) == 1:
                raise downloader.yt_dlp.utils.DownloadError("aria2c exited with code 1")
            return prepared_info, output_dir / "Example [BV1TEST].mp3"

        with (
            patch("downloader.aria2c_path", return_value="/bin/aria2c"),
            patch("downloader._extract_bilibili_info", return_value=(Mock(), info)),
            patch("downloader.build_acceleration_plan", return_value=Mock(
                adaptive=True,
                cdn_host="primary.example",
                http_chunk_size=4 * 1024 * 1024,
            )),
            patch("downloader._process_bilibili_attempt", side_effect=fake_attempt),
            patch("downloader._format_filesize", return_value="60.00 MB"),
        ):
            result = downloader.download_video(
                "https://b23.tv/example",
                platform=downloader.BILIBILI,
                media_type=downloader.AUDIO,
                speed_mode=downloader.TURBO,
                progress_callback=lambda event, data: events.append((event, data)),
            )

        self.assertEqual(attempts, [{"http": "/bin/aria2c"}, None])
        self.assertEqual(result["speed_mode_used"], downloader.STANDARD)
        self.assertTrue(result["turbo_fallback"])
        self.assertNotIn("token=", repr(result))
        self.assertIn(("mode", {
            "speed_mode": downloader.STANDARD,
            "turbo_fallback": True,
        }), events)

    def test_non_aria2_download_error_does_not_retry_as_standard(self):
        info = {"id": "BV1TEST", "title": "Example", "url": "https://a/v", "filesize": 60}
        with (
            patch("downloader.aria2c_path", return_value="/bin/aria2c"),
            patch("downloader._extract_bilibili_info", return_value=(Mock(), info)),
            patch("downloader.build_acceleration_plan", return_value=Mock(
                adaptive=False, cdn_host="a", http_chunk_size=10 * 1024 * 1024,
            )),
            patch(
                "downloader._process_bilibili_attempt",
                side_effect=downloader.yt_dlp.utils.DownloadError("ffmpeg merge failed"),
            ) as process,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = downloader.download_video(
                "https://b23.tv/example",
                platform=downloader.BILIBILI,
                speed_mode=downloader.TURBO,
            )

        self.assertIsNone(result)
        self.assertEqual(process.call_count, 1)

    def test_selected_cdn_403_retries_original_url_and_ten_mib_chunk(self):
        info = {
            "id": "BV1TEST",
            "title": "Example",
            "url": "https://primary.example/audio.m4s",
            "filesize": 60 * 1024 * 1024,
            "ext": "m4a",
            "_bilibili_cdn_candidates": (
                "https://primary.example/audio.m4s",
                "https://fast.example/audio.m4s",
            ),
        }
        seen = []

        def fake_attempt(prepared_info, options, output_dir):
            seen.append((prepared_info["url"], options["http_chunk_size"]))
            if len(seen) == 1:
                raise downloader.yt_dlp.utils.DownloadError("HTTP Error 403")
            return prepared_info, output_dir / "Example [BV1TEST].mp3"

        with (
            patch("downloader._extract_bilibili_info", return_value=(Mock(), info)),
            patch("downloader.build_acceleration_plan", return_value=Mock(
                adaptive=True,
                cdn_host="fast.example",
                http_chunk_size=4 * 1024 * 1024,
            )),
            patch("downloader._process_bilibili_attempt", side_effect=fake_attempt),
            patch("downloader._format_filesize", return_value="60.00 MB"),
        ):
            result = downloader.download_video(
                "https://b23.tv/example",
                platform=downloader.BILIBILI,
                media_type=downloader.AUDIO,
            )

        self.assertEqual(seen, [
            ("https://fast.example/audio.m4s", 4 * 1024 * 1024),
            ("https://primary.example/audio.m4s", 10 * 1024 * 1024),
        ])
        self.assertEqual(result["cdn_host"], "primary.example")

    def test_failed_attempt_cleanup_only_removes_new_temporary_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            existing = output_dir / "existing.part"
            existing.write_bytes(b"keep")
            before = downloader._temporary_snapshot(output_dir)
            new_part = output_dir / "Example.mp4.part"
            new_format = output_dir / "Example.f137.mp4"
            final_file = output_dir / "Example.mp4"
            new_part.write_bytes(b"partial")
            new_format.write_bytes(b"partial")
            final_file.write_bytes(b"final")

            downloader._cleanup_new_attempt_files(output_dir, before)

            self.assertTrue(existing.exists())
            self.assertFalse(new_part.exists())
            self.assertFalse(new_format.exists())
            self.assertTrue(final_file.exists())
```

- [ ] **Step 2: Run focused downloader tests and verify RED**

Run:

```bash
venv/bin/python -m unittest \
  tests.test_bilibili_support.BilibiliTurboDownloadTests \
  tests.test_bilibili_support.BilibiliDownloadOptionsTests -v
```

Expected: fails because downloader functions do not accept `speed_mode` and the helper functions do not exist.

- [ ] **Step 3: Add imports, aliases, and option validation**

At the top of `downloader.py`, add `import copy`, `from dataclasses import dataclass`, and:

```python
from bilibili_acceleration import (
    BILIBILI_HTTP_CHUNK_SIZE,
    SPEED_MODES,
    STANDARD,
    TURBO,
    AccelerationPlan,
    apply_cdn_host,
    aria2c_path,
    build_acceleration_plan,
    configure_aria2,
    effective_speed_mode,
    primary_host,
    register_bilibili_extractor,
)
```

Remove the duplicate local `BILIBILI_HTTP_CHUNK_SIZE`. Extend `_build_ydl_options()`:

```python
def _build_ydl_options(
    platform: str,
    output_dir: Path,
    index: int,
    total: int,
    progress_callback: YtdlpProgressCallback = None,
    media_type: str = VIDEO,
    speed_mode: str = STANDARD,
    aria2_executable: str | None = None,
) -> dict:
    if media_type not in MEDIA_TYPES:
        raise ValueError(f"不支持的下载类型: {media_type}")
    if speed_mode not in SPEED_MODES:
        raise ValueError(f"不支持的速度模式: {speed_mode}")
    options = {
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "progress_hooks": [_make_progress_hook(index, total, progress_callback)],
        "writesubtitles": False,
        "writeautomaticsub": False,
        "embedmetadata": True,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "logger": _QuietYtdlpLogger(),
        "retries": 10,
        "fragment_retries": 10,
        "extractor_retries": 5,
        "socket_timeout": 30,
    }
```

Retain the current YouTube, Instagram, Bilibili, video/audio format, postprocessor, output template, and cookie branches byte-for-byte after this common dictionary. Immediately before the single existing `return options`, add:

```python
    if platform == BILIBILI and speed_mode == TURBO and aria2_executable:
        configure_aria2(options, aria2_executable)
    return options
```

- [ ] **Step 4: Implement isolated extraction, attempts, cleanup, and result assembly**

Add these complete helpers above `download_video()`:

```python
def _extract_bilibili_info(url: str, options: dict):
    ydl = yt_dlp.YoutubeDL(options)
    register_bilibili_extractor(ydl)
    try:
        info = ydl.extract_info(url, download=False)
        return ydl, info
    except Exception:
        ydl.close()
        raise


def _temporary_snapshot(output_dir: Path) -> set[Path]:
    return {path.resolve() for path in output_dir.iterdir()} if output_dir.is_dir() else set()


def _cleanup_new_attempt_files(output_dir: Path, before: set[Path]) -> None:
    if not output_dir.is_dir():
        return
    for path in output_dir.iterdir():
        resolved = path.resolve()
        name = path.name
        is_attempt_file = (
            name.endswith((".part", ".aria2", ".ytdl"))
            or ".part." in name
            or re.search(r"\.f[^.]+\.[^.]+$", name) is not None
        )
        if resolved not in before and path.is_file() and is_attempt_file:
            path.unlink(missing_ok=True)


def _process_bilibili_attempt(
    prepared_info: dict,
    options: dict,
    output_dir: Path,
) -> tuple[dict, Path]:
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.process_info(prepared_info)
        filepath = _resolve_output_path(ydl, prepared_info, output_dir, prepared_info["_media_type"])
    return prepared_info, filepath


def _is_aria2_failure(error: Exception) -> bool:
    message = str(error).lower()
    return "aria2c" in message and ("exited" in message or "external downloader" in message)


def _is_cdn_access_failure(error: Exception) -> bool:
    message = str(error).lower()
    return "http error 403" in message or "http error 412" in message


def _build_download_result(
    info: dict,
    filepath: Path,
    platform_name: str,
    media_type: str,
    requested_mode: str,
    used_mode: str,
    turbo_fallback: bool,
    plan: AccelerationPlan,
) -> DownloadResult:
    resolution = info.get("resolution") or (
        f"{info.get('width')}x{info.get('height')}"
        if info.get("width") and info.get("height") else "未知"
    )
    result = {
        "platform": platform_name,
        "title": info.get("title", "未知标题"),
        "filepath": str(filepath),
        "filesize": _format_filesize(filepath, info),
        "media_type": media_type,
        "speed_mode_requested": requested_mode,
        "speed_mode_used": used_mode,
        "turbo_fallback": turbo_fallback,
        "cdn_host": plan.cdn_host or "未知",
        "http_chunk_size": plan.http_chunk_size,
    }
    if media_type == AUDIO:
        result.update({"format": "MP3", "acodec": "mp3"})
    else:
        result.update({
            "resolution": resolution,
            "fps": info.get("fps") or "未知",
            "vcodec": info.get("vcodec") or "未知",
            "acodec": info.get("acodec") or "未知",
        })
    return result
```

Implement `_download_bilibili()` as the only Bilibili two-stage path:

```python
def _download_bilibili(
    url: str,
    index: int,
    total: int,
    output_dir: Path,
    progress_callback: YtdlpProgressCallback,
    media_type: str,
    speed_mode: str,
) -> DownloadResult:
    executable = aria2c_path()
    used_mode = effective_speed_mode(BILIBILI, speed_mode, executable)
    metadata_options = _build_ydl_options(
        BILIBILI, output_dir, index, total,
        progress_callback=progress_callback,
        media_type=media_type,
        speed_mode=STANDARD,
    )
    metadata_ydl, extracted = _extract_bilibili_info(url, metadata_options)
    try:
        if not extracted:
            raise yt_dlp.utils.DownloadError("下载器未返回视频信息")
        plan = build_acceleration_plan(metadata_ydl, extracted)
    finally:
        metadata_ydl.close()

    original_info = copy.deepcopy(extracted)
    optimized_info = copy.deepcopy(extracted)
    apply_cdn_host(optimized_info, plan.cdn_host)
    for prepared in (original_info, optimized_info):
        prepared["_media_type"] = media_type

    attempts = [(used_mode, optimized_info, plan, False)]
    if used_mode == TURBO:
        attempts.append((STANDARD, copy.deepcopy(optimized_info), plan, True))
    original_plan = AccelerationPlan(False, primary_host(original_info), BILIBILI_HTTP_CHUNK_SIZE)
    if plan.cdn_host and plan.cdn_host != primary_host(original_info):
        attempts.append((STANDARD, original_info, original_plan, used_mode == TURBO))

    last_error = None
    for attempt_index, (attempt_mode, prepared_info, attempt_plan, fallback) in enumerate(attempts):
        options = _build_ydl_options(
            BILIBILI, output_dir, index, total,
            progress_callback=progress_callback,
            media_type=media_type,
            speed_mode=attempt_mode,
            aria2_executable=executable,
        )
        options["http_chunk_size"] = attempt_plan.http_chunk_size
        if progress_callback:
            progress_callback("mode", {
                "speed_mode": attempt_mode,
                "turbo_fallback": fallback,
            })
        before = _temporary_snapshot(output_dir)
        try:
            final_info, filepath = _process_bilibili_attempt(prepared_info, options, output_dir)
            return _build_download_result(
                final_info, filepath, PLATFORM_NAMES[BILIBILI], media_type,
                speed_mode, attempt_mode, fallback, attempt_plan,
            )
        except yt_dlp.utils.DownloadError as error:
            _cleanup_new_attempt_files(output_dir, before)
            last_error = error
            next_is_standard = attempt_index + 1 < len(attempts) and attempts[attempt_index + 1][0] == STANDARD
            can_retry_aria2 = attempt_mode == TURBO and _is_aria2_failure(error) and next_is_standard
            can_retry_cdn = _is_cdn_access_failure(error) and attempt_plan.cdn_host != primary_host(original_info)
            if not can_retry_aria2 and not can_retry_cdn:
                raise
    raise last_error or yt_dlp.utils.DownloadError("Bilibili 下载失败")
```

- [ ] **Step 5: Route Bilibili through the new helper and preserve other platforms**

Extend `download_video()` with `speed_mode: str = STANDARD`, validate it, and immediately after building the output directory use:

```python
    if speed_mode not in SPEED_MODES:
        raise ValueError(f"不支持的速度模式: {speed_mode}")
    if platform == BILIBILI:
        try:
            return _download_bilibili(
                url, index, total, output_dir,
                progress_callback, media_type, speed_mode,
            )
        except yt_dlp.utils.DownloadError as error:
            _handle_download_error(str(error), platform, media_type)
            return None
```

Leave the current `extract_info(url, download=True)` block for YouTube and Instagram unchanged. In the existing non-Bilibili `result = {...}` dictionary add exactly:

```python
                "speed_mode_requested": speed_mode,
                "speed_mode_used": STANDARD,
                "turbo_fallback": False,
                "cdn_host": "未知",
                "http_chunk_size": 0,
```

Do not route YouTube or Instagram through `_build_download_result()` or the Bilibili preflight.

- [ ] **Step 6: Run focused download/error tests and verify GREEN**

Run:

```bash
venv/bin/python -m unittest \
  tests.test_bilibili_support.BilibiliTurboDownloadTests \
  tests.test_bilibili_support.BilibiliDownloadOptionsTests \
  tests.test_downloader_errors -v
```

Expected: all pass; aria2-specific failure retries once, while FFmpeg/general errors do not repeat the download.

- [ ] **Step 7: Commit the Bilibili orchestration**

```bash
git add downloader.py tests/test_bilibili_support.py tests/test_downloader_errors.py
git commit -m "feat: add adaptive Bilibili download fallback"
```

---

### Task 6: Propagate Speed Mode Through the Shared Parallel Queue

**Files:**
- Modify: `downloader.py:575-650`
- Modify: `tests/test_parallel_downloads.py:204-223`

**Interfaces:**
- Consumes: `download_video(..., speed_mode=STANDARD)`.
- Produces: `download_tasks(tasks, progress_callback=None, media_type=VIDEO, speed_mode=STANDARD)` while retaining ordered results and existing concurrency limits.

- [ ] **Step 1: Write failing queue propagation tests**

Append to `ParallelDownloadTests`:

```python
    def test_speed_mode_is_forwarded_to_every_task(self):
        tasks = [
            (downloader.BILIBILI, "https://b23.tv/first"),
            (downloader.YOUTUBE, "https://youtu.be/second"),
        ]

        with patch(
            "downloader.download_video",
            side_effect=lambda url, **kwargs: {
                "title": url,
                "speed_mode_requested": kwargs["speed_mode"],
            },
        ) as mocked:
            results = downloader.download_tasks(tasks, speed_mode=downloader.TURBO)

        self.assertEqual(mocked.call_count, 2)
        self.assertTrue(all(
            call.kwargs["speed_mode"] == downloader.TURBO
            for call in mocked.call_args_list
        ))
        self.assertTrue(all(
            result["speed_mode_requested"] == downloader.TURBO
            for _, result in results
        ))

    def test_unknown_batch_speed_mode_fails_before_workers_start(self):
        with patch("downloader.ThreadPoolExecutor") as executor:
            with self.assertRaisesRegex(ValueError, "速度模式"):
                downloader.download_tasks(
                    [(downloader.BILIBILI, "https://b23.tv/example")],
                    speed_mode="warp",
                )
        executor.assert_not_called()
```

- [ ] **Step 2: Run the new parallel tests and verify RED**

Run:

```bash
venv/bin/python -m unittest \
  tests.test_parallel_downloads.ParallelDownloadTests.test_speed_mode_is_forwarded_to_every_task \
  tests.test_parallel_downloads.ParallelDownloadTests.test_unknown_batch_speed_mode_fails_before_workers_start -v
```

Expected: fails because `download_tasks()` has no `speed_mode` parameter.

- [ ] **Step 3: Extend the shared queue without changing semaphore placement**

Change the signature and initial validation:

```python
def download_tasks(
    tasks: list[VideoTask],
    progress_callback: ProgressCallback = None,
    media_type: str = VIDEO,
    speed_mode: str = STANDARD,
) -> list[tuple[VideoTask, Optional[DownloadResult]]]:
    if speed_mode not in SPEED_MODES:
        raise ValueError(f"不支持的速度模式: {speed_mode}")
```

Inside `_download_current_task()`, pass the new keyword without moving the existing `started` event or Bilibili semaphore:

```python
            return download_video(
                url,
                index=task_index + 1,
                total=total,
                platform=platform,
                progress_callback=_relay_progress if progress_callback else None,
                media_type=media_type,
                speed_mode=speed_mode,
            )
```

Document the new parameter in the function docstring. Leave `worker_count`, `executor.map()`, result ordering, and the two-slot Bilibili semaphore unchanged.

- [ ] **Step 4: Run all parallel tests and verify GREEN**

Run:

```bash
venv/bin/python -m unittest tests.test_parallel_downloads -v
```

Expected: all tests pass, including maximum 3 total tasks, maximum 2 Bilibili tasks, waiting-event timing, ordering, media type, and speed mode.

- [ ] **Step 5: Commit queue propagation**

```bash
git add downloader.py tests/test_parallel_downloads.py
git commit -m "feat: propagate download speed mode"
```

---

### Task 7: Add Flask Capability, Validation, and Mode State

**Files:**
- Modify: `app.py:12-19,32-113,125-170`
- Modify: `tests/test_web_progress.py:11-308`
- Modify: `tests/test_bilibili_support.py:222-272`

**Interfaces:**
- Consumes: `SPEED_MODES`, `STANDARD`, `TURBO`, `aria2c_path()`, and `download_tasks(..., speed_mode=...)`.
- Produces: `GET /api/capabilities`, strict `speed_mode` handling in `POST /api/download`, and batch/task mode fields.

- [ ] **Step 1: Write failing API and state tests**

Add:

```python
class WebTurboApiTests(unittest.TestCase):
    def setUp(self):
        web_app._batches.clear()
        self.client = web_app.app.test_client()

    def test_capabilities_reports_aria2_boolean(self):
        with patch("app.aria2c_path", return_value="/opt/homebrew/bin/aria2c"):
            response = self.client.get("/api/capabilities")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"aria2c_available": True})

    def test_download_defaults_to_standard_speed_mode(self):
        with patch("app.threading.Thread"):
            response = self.client.post(
                "/api/download",
                json={"urls": ["https://b23.tv/example"]},
            )

        batch = web_app._batches[response.get_json()["batch_id"]]
        self.assertEqual(batch["speed_mode"], downloader.STANDARD)
        self.assertEqual(batch["tasks"][0]["speed_mode_used"], downloader.STANDARD)

    def test_download_forwards_turbo_to_background_thread(self):
        with patch("app.threading.Thread") as thread_class:
            response = self.client.post(
                "/api/download",
                json={
                    "urls": ["https://b23.tv/example"],
                    "media_type": downloader.AUDIO,
                    "speed_mode": downloader.TURBO,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(thread_class.call_args.kwargs["args"][3], downloader.TURBO)

    def test_download_rejects_non_string_and_unknown_speed_modes(self):
        for value in (["turbo"], "warp"):
            with self.subTest(value=value), patch("app.threading.Thread") as thread_class:
                response = self.client.post(
                    "/api/download",
                    json={"urls": ["https://b23.tv/example"], "speed_mode": value},
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("速度模式", response.get_json()["error"])
                thread_class.assert_not_called()

    def test_mode_event_updates_task_without_creating_terminal_state(self):
        batch = web_app._create_batch(
            [(downloader.BILIBILI, "https://b23.tv/example")],
            speed_mode=downloader.TURBO,
        )

        web_app._apply_progress_event(batch, 0, "mode", {
            "speed_mode": downloader.STANDARD,
            "turbo_fallback": True,
        })

        task = batch["tasks"][0]
        self.assertEqual(task["speed_mode_used"], downloader.STANDARD)
        self.assertTrue(task["turbo_fallback"])
        self.assertEqual(batch["completed"], 0)
        self.assertEqual(batch["failed"], 0)
```

- [ ] **Step 2: Run the Web turbo API tests and verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_web_progress.WebTurboApiTests -v
```

Expected: fails with missing capability route, missing batch fields, and unsupported `_create_batch(speed_mode=...)`.

- [ ] **Step 3: Add capability and batch state**

Extend imports from `downloader` with `SPEED_MODES`, `STANDARD`, `TURBO`, and `aria2c_path`. Change `_create_batch()` to:

```python
def _create_batch(
    tasks: list,
    media_type: str = VIDEO,
    speed_mode: str = STANDARD,
) -> dict:
    batch_id = uuid.uuid4().hex[:8]
    batch = {
        "id": batch_id,
        "media_type": media_type,
        "speed_mode": speed_mode,
        "tasks": [
            {
                "index": i,
                "url": url,
                "platform": platform,
                "platform_name": PLATFORM_NAMES.get(platform, "未知"),
                "status": "pending",
                "title": None,
                "result": None,
                "error": None,
                "progress": None,
                "speed_mode_used": STANDARD,
                "turbo_fallback": False,
            }
            for i, (platform, url) in enumerate(tasks)
        ],
        "total": len(tasks),
        "completed": 0,
        "failed": 0,
        "all_done": False,
    }
    with _lock:
        _batches[batch_id] = batch
    return batch
```

Add the non-terminal event before the existing `completed` branch:

```python
    elif event == "mode" and isinstance(data, dict):
        task["status"] = "downloading"
        task["speed_mode_used"] = (
            data.get("speed_mode")
            if data.get("speed_mode") in SPEED_MODES
            else STANDARD
        )
        task["turbo_fallback"] = bool(data.get("turbo_fallback"))
        if task["speed_mode_used"] == TURBO:
            task["progress"] = None
```

When processing `completed`, copy the result mode fields back to the task before incrementing:

```python
        task["speed_mode_used"] = str(data.get("speed_mode_used", STANDARD))
        task["turbo_fallback"] = bool(data.get("turbo_fallback", False))
```

- [ ] **Step 4: Validate and propagate mode through Flask**

Change `_run_downloads()` and its call:

```python
def _run_downloads(
    batch_id: str,
    tasks: list,
    media_type: str = VIDEO,
    speed_mode: str = STANDARD,
) -> None:
    def _on_progress(task_index: int, event: str, data: object) -> None:
        with _lock:
            batch = _batches.get(batch_id)
            if not batch:
                return
            _apply_progress_event(batch, task_index, event, data)

    download_tasks(
        tasks,
        progress_callback=_on_progress,
        media_type=media_type,
        speed_mode=speed_mode,
    )

    with _lock:
        batch = _batches.get(batch_id)
        if batch:
            batch["all_done"] = True
```

Add the capability route:

```python
@app.route("/api/capabilities")
def api_capabilities():
    return jsonify({"aria2c_available": aria2c_path() is not None})
```

In `api_download()` read and validate:

```python
    speed_mode = body.get("speed_mode", STANDARD)
    if not isinstance(speed_mode, str) or speed_mode not in SPEED_MODES:
        return jsonify({"error": "不支持的速度模式"}), 400
```

Create and launch with:

```python
    batch = _create_batch(tasks, media_type=media_type, speed_mode=speed_mode)
    thread = threading.Thread(
        target=_run_downloads,
        args=(batch["id"], tasks, media_type, speed_mode),
        daemon=True,
    )
```

- [ ] **Step 5: Run all Web backend tests and verify GREEN**

Run:

```bash
venv/bin/python -m unittest \
  tests.test_web_progress.WebTurboApiTests \
  tests.test_web_progress.WebDownloadApiTests \
  tests.test_web_progress.WebProgressStateTests \
  tests.test_bilibili_support.BilibiliSurfaceIntegrationTests -v
```

Expected: all pass, including old requests that omit `speed_mode`.

- [ ] **Step 6: Commit Flask capability and state**

```bash
git add app.py tests/test_web_progress.py tests/test_bilibili_support.py
git commit -m "feat: expose turbo mode through Web API"
```

---

### Task 8: Add Independent Web Turbo Switches and Turbo Status Rendering

**Files:**
- Modify: `templates/index.html:333-399,609-645,661-801,818-879,951-956`
- Modify: `tests/test_web_progress.py:78-112`

**Interfaces:**
- Consumes: `GET /api/capabilities`, batch/task `speed_mode_used`, `turbo_fallback`, and `POST /api/download` field `speed_mode`.
- Produces: `videoTurboToggle`, `audioTurboToggle`, `loadCapabilities()`, per-section mode submission, `高速下载中`, and fallback messaging.

- [ ] **Step 1: Write failing front-end source tests**

Append to `WebProgressStateTests`:

```python
    def test_frontend_has_independent_video_and_audio_turbo_switches(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn('id="videoTurboToggle"', html)
        self.assertIn('id="audioTurboToggle"', html)
        self.assertEqual(html.count('<span class="turbo-title">极速模式</span>'), 2)
        self.assertIn('fetch("/api/capabilities")', html)
        self.assertIn("aria2c_available", html)

    def test_frontend_submits_section_speed_mode(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn(
            'const speedMode = control.turboToggle.checked ? "turbo" : "standard";',
            html,
        )
        self.assertIn("JSON.stringify({ urls, media_type: mediaType, speed_mode: speedMode })", html)

    def test_frontend_renders_turbo_and_fallback_states(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("高速下载中", html)
        self.assertIn("极速模式不可用，已切换标准模式", html)
        self.assertIn('t.speed_mode_used === "turbo"', html)
        self.assertIn("!t.turbo_fallback", html)
```

- [ ] **Step 2: Run the new front-end tests and verify RED**

Run:

```bash
venv/bin/python -m unittest \
  tests.test_web_progress.WebProgressStateTests.test_frontend_has_independent_video_and_audio_turbo_switches \
  tests.test_web_progress.WebProgressStateTests.test_frontend_submits_section_speed_mode \
  tests.test_web_progress.WebProgressStateTests.test_frontend_renders_turbo_and_fallback_states -v
```

Expected: all three fail because the switches and mode rendering are absent.

- [ ] **Step 3: Add switch styling consistent with the existing dark PETRONAS theme**

Add after `.url-input:disabled`:

```css
  .turbo-control {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-top: 14px;
    padding: 11px 13px;
    border: 1px solid var(--border);
    background: rgba(0, 155, 149, .045);
  }
  .turbo-copy { display: grid; gap: 3px; min-width: 0; }
  .turbo-title { color: var(--foreground); font-size: 12px; }
  .turbo-hint { color: var(--muted); font-size: 10px; line-height: 1.45; }
  .turbo-switch { position: relative; width: 38px; height: 21px; flex: 0 0 auto; }
  .turbo-switch input { position: absolute; opacity: 0; pointer-events: none; }
  .turbo-slider {
    position: absolute;
    inset: 0;
    border: 1px solid var(--border-strong);
    background: rgba(100, 116, 139, .2);
    cursor: pointer;
    transition: background .2s ease, border-color .2s ease;
  }
  .turbo-slider::after {
    content: "";
    position: absolute;
    top: 3px;
    left: 3px;
    width: 13px;
    height: 13px;
    background: var(--muted);
    transition: transform .2s ease, background .2s ease;
  }
  .turbo-switch input:checked + .turbo-slider {
    border-color: var(--accent);
    background: rgba(0, 161, 155, .2);
  }
  .turbo-switch input:checked + .turbo-slider::after {
    transform: translateX(17px);
    background: var(--accent);
  }
  .turbo-switch input:focus-visible + .turbo-slider { outline: 2px solid var(--accent); outline-offset: 2px; }
  .turbo-switch input:disabled + .turbo-slider { opacity: .42; cursor: not-allowed; }
```

- [ ] **Step 4: Add one switch to each existing card**

Immediately after `videoUrls` add:

```html
        <div class="turbo-control">
          <span class="turbo-copy"><span class="turbo-title">极速模式</span><span class="turbo-hint" id="videoTurboHint">正在检测 aria2c…</span></span>
          <label class="turbo-switch" aria-label="视频极速模式">
            <input type="checkbox" id="videoTurboToggle" disabled>
            <span class="turbo-slider" aria-hidden="true"></span>
          </label>
        </div>
```

Immediately after `audioUrls` add the same structure with IDs `audioTurboHint`, `audioTurboToggle`, and label `音频极速模式`. Do not move or merge either textarea.

- [ ] **Step 5: Load capabilities and submit the active card's mode**

Add `turboToggle` and `turboHint` to each `downloadControls` entry. Add module state and loader:

```javascript
  let aria2Available = false;

  async function loadCapabilities() {
    try {
      const response = await fetch("/api/capabilities");
      if (!response.ok) throw new Error("capability request failed");
      const capabilities = await response.json();
      aria2Available = capabilities.aria2c_available === true;
    } catch (_) {
      aria2Available = false;
    }
    Object.values(downloadControls).forEach(control => {
      control.turboToggle.disabled = !aria2Available || isDownloading;
      control.turboHint.textContent = aria2Available
        ? "Bilibili 大文件可使用 aria2c 多连接下载"
        : "未安装 aria2c，当前使用标准模式";
      if (!aria2Available) control.turboToggle.checked = false;
    });
  }
```

Change `setControlsDisabled()` so each switch remains disabled when aria2 is unavailable:

```javascript
      control.turboToggle.disabled = disabled || !aria2Available;
```

Inside `startDownload()`, before `fetch`, add:

```javascript
    const speedMode = control.turboToggle.checked ? "turbo" : "standard";
```

Change the JSON body to:

```javascript
        body: JSON.stringify({ urls, media_type: mediaType, speed_mode: speedMode }),
```

Call `loadCapabilities();` after the existing `initializeExperience()` try/catch, so a capability failure never blocks page initialization.

- [ ] **Step 6: Render turbo and fallback progress without fake metrics**

Replace the `downloading` branch in `renderTasks()` with:

```javascript
      } else if (t.status === "downloading") {
        if (t.speed_mode_used === "turbo" && !t.turbo_fallback) {
          html += `<div class="task-meta"><span class="spinner"></span> 高速下载中</div>`;
        } else {
          if (t.turbo_fallback) {
            html += `<div class="task-meta">极速模式不可用，已切换标准模式</div>`;
          }
          html += `<div class="task-meta"><span class="spinner"></span> 正在下载，请稍候…</div>`;
          html += renderDownloadProgress(t.progress);
        }
```

Do not change completed audio/video metadata, failed state, operational metrics, scrolling animations, or reduced-motion CSS.

- [ ] **Step 7: Run front-end regression and syntax tests**

Run:

```bash
venv/bin/python -m unittest tests.test_web_progress -v
sed -n '/<script>/,/<\/script>/p' templates/index.html | sed '1d;$d' | node --check
```

Expected: all Web tests pass and Node exits 0 without syntax errors.

- [ ] **Step 8: Commit the Web switches**

```bash
git add templates/index.html tests/test_web_progress.py
git commit -m "feat: add Web turbo mode controls"
```

---

### Task 9: Add CLI Turbo Selection and Mode Reporting

**Files:**
- Modify: `main.py:12-29,34-68,207-249`
- Modify: `tests/test_cli_audio.py`

**Interfaces:**
- Consumes: `STANDARD`, `TURBO`, `aria2c_path()`, and `download_tasks(..., speed_mode=...)`.
- Produces: `parse_command_line(args) -> tuple[str, str, list[str]]`, `choose_speed_mode() -> str`, combined `--audio --turbo`, and actual-mode summary text.

- [ ] **Step 1: Write failing CLI parsing and forwarding tests**

Update the two existing parse assertions to unpack three values, then append:

```python
    def test_parse_command_line_combines_audio_and_turbo(self):
        url = "https://b23.tv/example"

        media_type, speed_mode, urls = cli_main.parse_command_line([
            "--audio", url, "--turbo",
        ])

        self.assertEqual(media_type, downloader.AUDIO)
        self.assertEqual(speed_mode, downloader.TURBO)
        self.assertEqual(urls, [url])

    def test_interactive_speed_mode_defaults_to_standard(self):
        with patch("builtins.input", return_value=""):
            self.assertEqual(cli_main.choose_speed_mode(), downloader.STANDARD)

    def test_main_forwards_turbo_and_warns_when_aria2_is_missing(self):
        url = "https://b23.tv/example"
        result = {
            "platform": "Bilibili",
            "title": "Example",
            "filepath": "/tmp/Example.mp4",
            "resolution": "1920x1080",
            "acodec": "aac",
            "filesize": "10.00 MB",
            "media_type": downloader.VIDEO,
            "speed_mode_requested": downloader.TURBO,
            "speed_mode_used": downloader.STANDARD,
            "turbo_fallback": False,
        }
        with (
            patch.object(sys, "argv", ["main.py", "--turbo", url]),
            patch("main.check_ffmpeg", return_value=True),
            patch("main.aria2c_path", return_value=None),
            patch("main.download_tasks", return_value=[((downloader.BILIBILI, url), result)]) as tasks,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            exit_code = cli_main.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(tasks.call_args.kwargs["speed_mode"], downloader.TURBO)
        self.assertIn("未检测到 aria2c", output.getvalue())
        self.assertIn("标准模式", output.getvalue())
```

- [ ] **Step 2: Run CLI tests and verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_cli_audio -v
```

Expected: parse tuple size and missing `choose_speed_mode()` failures.

- [ ] **Step 3: Implement CLI parsing and interactive selection**

Import `STANDARD`, `TURBO`, and `aria2c_path`. Replace `parse_command_line()` and add:

```python
def parse_command_line(args: list[str]) -> tuple[str, str, list[str]]:
    media_type = AUDIO if "--audio" in args else VIDEO
    speed_mode = TURBO if "--turbo" in args else STANDARD
    urls = [value for value in args if value not in {"--audio", "--turbo"}]
    return media_type, speed_mode, urls


def choose_speed_mode() -> str:
    print("是否启用 Bilibili 极速模式？")
    print("  y. 启用 aria2c 多连接下载")
    print("  n. 标准模式（默认）")
    while True:
        choice = input("启用极速模式？(y/N): ").strip().lower()
        if choice in {"", "n", "no"}:
            return STANDARD
        if choice in {"y", "yes"}:
            return TURBO
        print("⚠️  请输入 y 或 n。")
```

In `main()` use:

```python
    if command_line_mode:
        media_type, speed_mode, url_args = parse_command_line(sys.argv[1:])
        tasks = get_tasks_from_args(url_args)
        if not tasks:
            print("❌ 错误：未提供合法的 YouTube、Instagram 或 Bilibili 视频链接。")
            print("   用法: python main.py [--audio] [--turbo] <URL1> [URL2] [URL3] ...")
            return 1
    else:
        try:
            media_type = choose_media_type()
            speed_mode = choose_speed_mode()
            tasks = get_tasks_from_user(media_type=media_type)
        except (EOFError, KeyboardInterrupt):
            print("\n已取消。")
            return 130

    if speed_mode == TURBO and aria2c_path() is None:
        print("⚠️  未检测到 aria2c；Bilibili 任务将自动使用标准模式。")
```

Pass `speed_mode=speed_mode` to `download_tasks()`.

- [ ] **Step 4: Report actual mode without exposing CDN URLs**

At the end of `print_single_result()` and within each successful item in `print_summary()`, derive:

```python
        used_mode = result.get("speed_mode_used", STANDARD)
        mode_name = "极速模式" if used_mode == TURBO else "标准模式"
        if result.get("turbo_fallback"):
            mode_name += "（极速模式已降级）"
```

Print `下载模式: {mode_name}`. Do not print `cdn_host` in the default summary; it remains available in the result dictionary for diagnostics.

- [ ] **Step 5: Run CLI tests and verify GREEN**

Run:

```bash
venv/bin/python -m unittest tests.test_cli_audio -v
```

Expected: default video/standard parsing, audio, turbo, combined flags, interactive choices, forwarding, and unavailable warning all pass.

- [ ] **Step 6: Commit CLI support**

```bash
git add main.py tests/test_cli_audio.py
git commit -m "feat: add CLI turbo mode"
```

---

### Task 10: Document Installation, Policy, and User Workflow

**Files:**
- Modify: `README.md:5-49,119-144,148-228,232-283,313-318`
- Modify: `tests/test_bilibili_support.py:278-315`

**Interfaces:**
- Consumes: finalized Web and CLI behavior.
- Produces: user-facing aria2 installation and mode instructions, without making aria2 mandatory.

- [ ] **Step 1: Extend the failing documentation expectations**

Add the following entries to `BilibiliDocumentationTests.test_readme_documents_bilibili_workflow_and_boundaries()`:

```python
            "bilibili_acceleration.py",
            "brew install aria2",
            "aria2c --version",
            "--turbo",
            "--audio --turbo",
            "50 MiB",
            "30 分钟",
            "高速下载中",
            "自动切换回标准模式",
            "最多测试 4 个",
            "不修改或猜测 CDN 域名",
```

- [ ] **Step 2: Run the documentation test and verify RED**

Run:

```bash
venv/bin/python -m unittest \
  tests.test_bilibili_support.BilibiliDocumentationTests.test_readme_documents_bilibili_workflow_and_boundaries -v
```

Expected: fails on the first new required string.

- [ ] **Step 3: Update dependencies and directory structure**

In README's feature list, state that Bilibili files over 50 MiB can select among at most 4 server-provided CDN hosts and that aria2 is optional. Add `bilibili_acceleration.py` to the directory tree with the description `Bilibili CDN 测速、缓存与极速模式策略`. Keep Python, yt-dlp, Flask, and FFmpeg setup unchanged.

After the FFmpeg section, add:

````markdown
### 可选：安装 aria2c 极速模式

标准模式不需要 aria2c。macOS 用户如需启用 Bilibili“极速模式”，可安装：

```bash
brew install aria2
aria2c --version
```

未安装或 aria2c 运行失败时，程序会自动切换回标准模式；YouTube 和 Instagram 不使用该加速器。
````

- [ ] **Step 4: Document CLI and Web behavior precisely**

Add these CLI examples beside the existing `--audio` examples:

```bash
python main.py --turbo "https://www.bilibili.com/video/BV1xRuu6fEeA"
python main.py --audio --turbo "https://www.bilibili.com/video/BV1xRuu6fEeA"
```

In the Web workflow, document that the video and audio cards have independent “极速模式” switches, disabled with an explicit hint when aria2c is unavailable. State that turbo tasks display `高速下载中`, while standard tasks retain precise speed, ETA, and percentage.

Add a Bilibili performance subsection containing all of these exact rules:

- `<= 50 MiB` or unknown selected size: current 10 MiB native chunk, no probe.
- `> 50 MiB`: at most 4 Bilibili-provided HTTPS CDN hosts, 512 KiB sample per host, then 4 MiB versus 10 MiB chunk comparison.
- Results are cached in memory for 30 minutes and reset on service restart.
- The program does not modify or guess CDN domains.
- Speed varies by region, route, account, and current CDN load; no fixed improvement is guaranteed.

- [ ] **Step 5: Run the documentation test and verify GREEN**

Run:

```bash
venv/bin/python -m unittest tests.test_bilibili_support.BilibiliDocumentationTests -v
```

Expected: README contains every required workflow and boundary string.

- [ ] **Step 6: Commit documentation**

```bash
git add README.md tests/test_bilibili_support.py
git commit -m "docs: explain Bilibili turbo mode"
```

---

### Task 11: Install aria2c, Run Full Verification, Benchmark, and Restart the Service

**Files:**
- Verify only: all tracked source, tests, README, and templates
- Runtime dependency: `/opt/homebrew/bin/aria2c`

**Interfaces:**
- Consumes: completed feature branch and current local network.
- Produces: verified tests, validated binaries/media, controlled benchmark evidence, browser QA, and a restarted service on port 8233.

- [ ] **Step 1: Install aria2c only after resolving its current state**

Run:

```bash
command -v aria2c
```

Expected before installation: no path. If absent, request the required host permission and run exactly:

```bash
/opt/homebrew/bin/brew install aria2
```

Then verify:

```bash
command -v aria2c
aria2c --version
```

Expected: an executable path, normally `/opt/homebrew/bin/aria2c`, and a successful version banner. If Homebrew installation fails, retain the implemented disabled-switch/standard-fallback behavior, record the installation error, and continue all non-turbo automated tests; do not modify application startup to install it automatically.

- [ ] **Step 2: Run the complete automated verification suite**

Run:

```bash
venv/bin/python -m unittest discover -s tests -v
venv/bin/python -m compileall -q downloader.py bilibili_acceleration.py app.py main.py tests
sed -n '/<script>/,/<\/script>/p' templates/index.html | sed '1d;$d' | node --check
git diff --check
git status --short
```

Expected: all unit tests pass; compileall, Node syntax, and diff checks exit 0; status contains only intentional feature changes or is clean after commits; `bilibili_cookies.txt` is absent from status.

- [ ] **Step 3: Resolve one small and one qualifying large Bilibili sample without logging signed media URLs**

Use the previously verified small sample `https://b23.tv/hkl7PC7`. For the user-provided candidate `https://www.bilibili.com/video/BV1xRuu6fEeA`, run metadata-only extraction through the new adapter and print only title, selected total MiB, and candidate hostnames. Confirm its selected sum is greater than 50 MiB before treating it as the large sample. If the candidate is not greater than 50 MiB at the currently available quality, use another publicly accessible long-form Bilibili video and repeat the same metadata-only size check; do not run the large benchmark until the printed selected sum exceeds 50 MiB.

Expected: the small sample takes the no-probe 10 MiB path; the qualifying sample reports a selected total greater than 50 MiB and no signed query string appears in terminal output.

- [ ] **Step 4: Run three isolated standard and turbo downloads per qualifying large sample**

For each run, point `downloader.DOWNLOADS_DIR` at a fresh `tempfile.TemporaryDirectory()`, call `download_tasks([make_task(url)], speed_mode=STANDARD)` or `TURBO`, and record:

- elapsed media/download time;
- result `cdn_host` only, never the full URL;
- result `http_chunk_size`;
- requested/used mode and fallback flag;
- final file size.

Run standard three times and turbo three times. Calculate median elapsed time and median throughput for each mode. Do not include FFmpeg merge/MP3 conversion time in the network throughput calculation; use yt-dlp progress timing or media bytes divided by the media transfer interval.

Expected: every run produces a valid file; adaptive standard chooses the fastest successful probe result; repeated candidate sets hit the 30-minute cache; turbo either uses aria2c successfully or records a safe standard fallback. Report measured values without promising a permanent percentage improvement.

- [ ] **Step 5: Validate MP4 and MP3 integrity**

Run one large video and one large audio task with `DOWNLOADS_DIR` set to the `video` and `audio` children of one task-specific temporary directory. Resolve exactly one output of each type and inspect it:

```bash
integrity_root="$(mktemp -d /private/tmp/gtd-bili-integrity.XXXXXX)"
mkdir "$integrity_root/video" "$integrity_root/audio"
export YTB_BILI_INTEGRITY_ROOT="$integrity_root"
venv/bin/python -c 'import os; from pathlib import Path; import downloader; downloader.DOWNLOADS_DIR = Path(os.environ["YTB_BILI_INTEGRITY_ROOT"]) / "video"; task = downloader.make_task("https://www.bilibili.com/video/BV1xRuu6fEeA"); result = downloader.download_tasks([task], speed_mode=downloader.TURBO); assert result[0][1] is not None'
venv/bin/python -c 'import os; from pathlib import Path; import downloader; downloader.DOWNLOADS_DIR = Path(os.environ["YTB_BILI_INTEGRITY_ROOT"]) / "audio"; task = downloader.make_task("https://www.bilibili.com/video/BV1xRuu6fEeA"); result = downloader.download_tasks([task], media_type=downloader.AUDIO, speed_mode=downloader.TURBO); assert result[0][1] is not None'
video_output="$(find "$integrity_root/video" -type f -name '*.mp4' -print -quit)"
audio_output="$(find "$integrity_root/audio" -type f -name '*.mp3' -print -quit)"
test -n "$video_output" -a -n "$audio_output"
ffprobe -v error -show_entries format=duration,size -show_entries stream=codec_type,codec_name,width,height -of json "$video_output"
ffprobe -v error -show_entries format=duration,size -show_entries stream=codec_type,codec_name -of json "$audio_output"
```

If Step 3 selected a different qualifying large URL, replace only the two literal user-candidate URLs above with that already validated literal URL. Expected: MP4 has playable video and audio streams with positive duration/size; MP3 has one audio stream, positive duration/size, and MP3 codec output. Never target the project downloads directory for cleanup or integrity testing.

- [ ] **Step 6: Restart only this project's port-8233 service**

Resolve the listener and ownership before stopping anything:

```bash
lsof -nP -iTCP:8233 -sTCP:LISTEN
```

Resolve the single listener PID into a task-scoped variable and validate that it is numeric:

```bash
project_service_pid="$(lsof -tiTCP:8233 -sTCP:LISTEN)"
case "$project_service_pid" in ''|*[!0-9]*) exit 1;; esac
ps -p "$project_service_pid" -o pid=,command=
lsof -a -p "$project_service_pid" -d cwd -Fn
```

Proceed only if the command is this project's Python/Flask process and cwd is exactly `/Users/markyang/Projects/GTD` or the active feature worktree. Stop that explicit validated PID with `kill "$project_service_pid"`, then start the completed checkout with:

```bash
venv/bin/python app.py
```

Expected: `http://127.0.0.1:8233` responds, while macOS `ControlCenter` and port 5000 are untouched.

- [ ] **Step 7: Perform desktop and mobile browser QA**

Use the browser-control skill against `http://127.0.0.1:8233` and verify:

- desktop width around 1440 px and mobile width around 390 px;
- both existing independent URL inputs remain present;
- each card has exactly one turbo switch and its own state;
- installed aria2c enables both switches; simulated unavailable capability disables both with the explicit hint in Flask tests;
- a standard Bilibili task shows speed/ETA/percentage;
- a turbo Bilibili task shows `高速下载中` without fake metrics;
- a forced aria2 unit/integration failure shows `极速模式不可用，已切换标准模式` and then standard progress;
- Active, Queue, Limit metrics and reduced-motion/mobile layout do not regress.

Capture screenshots or browser observations for desktop, mobile, standard, and turbo states in the implementation handoff.

- [ ] **Step 8: Review final branch diff and request code review**

Run:

```bash
git status --short --branch
git log --oneline --decorate -12
git diff main...HEAD --stat
git diff main...HEAD -- . ':!bilibili_cookies.txt'
```

Expected: only the planned module, download orchestration, Web/CLI surfaces, tests, README, design, and plan are present. Use the `requesting-code-review` skill, address any correctness issue, rerun the relevant focused tests, and then rerun the full suite before claiming completion.

## Completion Handoff

The final report must include:

- aria2c installation/version result;
- total automated test count and command output status;
- controlled standard versus turbo median measurements;
- selected CDN hostnames and chunk sizes only;
- MP4/MP3 FFprobe results;
- desktop/mobile Web QA result;
- service URL `http://127.0.0.1:8233` and verified process ownership;
- commit list and whether the branch is ahead of `origin/main`;
- explicit confirmation that `bilibili_cookies.txt` was not read, staged, or committed.
