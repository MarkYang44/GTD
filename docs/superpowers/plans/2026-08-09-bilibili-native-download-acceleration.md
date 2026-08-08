# Bilibili Native Download Acceleration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve Bilibili direct-HTTPS download throughput without changing YouTube or Instagram behavior and without losing the Web UI's live speed, percentage, and ETA updates.

**Architecture:** Add Bilibili-only native yt-dlp HTTP chunk and throttling parameters in `_build_ydl_options()`. Keep the global three-worker executor, but wrap Bilibili downloads in a batch-local two-slot semaphore so mixed-platform work can still use all three workers.

**Tech Stack:** Python 3, yt-dlp, Flask, `unittest`, FFmpeg

## Global Constraints

- Apply acceleration parameters only when `platform == BILIBILI`.
- Use `http_chunk_size = 10 * 1024 * 1024` and initially test `throttled_rate = 256 * 1024`.
- Preserve the global `MAX_PARALLEL_DOWNLOADS = 3` boundary.
- Permit at most `MAX_PARALLEL_BILIBILI_DOWNLOADS = 2` Bilibili downloads at once.
- Preserve input-order results, task-index progress events, worker exception isolation, cookies, formats, filenames, retries, and post-processing.
- Keep yt-dlp's native downloader so Web speed, percentage, and ETA callbacks continue during downloads.
- Do not install or enable aria2c in this phase.
- Retain a speed parameter only if controlled testing improves average throughput by at least 10% without new HTTP 403, HTTP 412, repeated re-extraction, or progress regression.

---

### Task 1: Add Bilibili-Only Native Acceleration Options

**Files:**
- Modify: `downloader.py:24-40,283-326`
- Test: `tests/test_bilibili_support.py:82-160`

**Interfaces:**
- Consumes: `_build_ydl_options(platform: str, output_dir: Path, index: int, total: int, progress_callback=None, media_type: str = VIDEO) -> dict`.
- Produces: `BILIBILI_HTTP_CHUNK_SIZE`, `BILIBILI_THROTTLED_RATE`, and Bilibili yt-dlp option dictionaries containing those values.

- [ ] **Step 1: Write failing platform-specific option tests**

Add these methods to `BilibiliDownloadOptionsTests`:

```python
    def test_native_acceleration_applies_to_bilibili_video_and_audio(self):
        output_dir = Path("/tmp/downloads")

        for media_type in (downloader.VIDEO, downloader.AUDIO):
            with self.subTest(media_type=media_type):
                options = downloader._build_ydl_options(
                    downloader.BILIBILI,
                    output_dir,
                    1,
                    1,
                    media_type=media_type,
                )
                self.assertEqual(
                    options["http_chunk_size"],
                    10 * 1024 * 1024,
                )
                self.assertEqual(
                    options["throttled_rate"],
                    256 * 1024,
                )

    def test_native_acceleration_does_not_change_other_platforms(self):
        output_dir = Path("/tmp/downloads")

        for platform in (downloader.YOUTUBE, downloader.INSTAGRAM):
            with self.subTest(platform=platform):
                options = downloader._build_ydl_options(
                    platform,
                    output_dir,
                    1,
                    1,
                )
                self.assertNotIn("http_chunk_size", options)
                self.assertNotIn("throttled_rate", options)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
../../venv/bin/python -m unittest \
  tests.test_bilibili_support.BilibiliDownloadOptionsTests.test_native_acceleration_applies_to_bilibili_video_and_audio \
  tests.test_bilibili_support.BilibiliDownloadOptionsTests.test_native_acceleration_does_not_change_other_platforms -v
```

Expected: the Bilibili test fails with missing `http_chunk_size`; the other-platform test passes.

- [ ] **Step 3: Implement the minimal Bilibili-only options**

Add near `MAX_PARALLEL_DOWNLOADS`:

```python
BILIBILI_HTTP_CHUNK_SIZE = 10 * 1024 * 1024
BILIBILI_THROTTLED_RATE = 256 * 1024
```

Replace the Bilibili output-template branch with:

```python
    elif platform == BILIBILI:
        options.update(
            {
                "outtmpl": str(output_dir / "%(title)s [%(id)s].%(ext)s"),
                "http_chunk_size": BILIBILI_HTTP_CHUNK_SIZE,
                "throttled_rate": BILIBILI_THROTTLED_RATE,
            }
        )
```

- [ ] **Step 4: Run focused and option regression tests**

Run:

```bash
../../venv/bin/python -m unittest tests.test_bilibili_support.BilibiliDownloadOptionsTests tests.test_downloader_errors -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the option change**

```bash
git add downloader.py tests/test_bilibili_support.py
git commit -m "perf: add Bilibili native download tuning"
```

---

### Task 2: Enforce the Two-Task Bilibili Concurrency Boundary

**Files:**
- Modify: `downloader.py:9-16,35-40,567-624`
- Test: `tests/test_parallel_downloads.py`

**Interfaces:**
- Consumes: `download_tasks(tasks, progress_callback=None, media_type=VIDEO)` and `download_video(url, index, total, platform, progress_callback, media_type)`.
- Produces: `MAX_PARALLEL_BILIBILI_DOWNLOADS = 2` and a batch-local `threading.BoundedSemaphore` that gates only Bilibili calls.

- [ ] **Step 1: Write failing Bilibili concurrency tests**

Add these methods to `ParallelDownloadTests`:

```python
    def test_bilibili_runs_at_most_two_tasks_concurrently(self):
        tasks = [
            (downloader.BILIBILI, f"https://b23.tv/video-{index}")
            for index in range(5)
        ]
        lock = threading.Lock()
        active = 0
        maximum_active = 0

        def fake_download(url, **kwargs):
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return {"title": url}

        with patch("downloader.download_video", side_effect=fake_download):
            results = downloader.download_tasks(tasks)

        self.assertEqual(maximum_active, 2)
        self.assertEqual(
            [result["title"] for _, result in results],
            [url for _, url in tasks],
        )

    def test_mixed_batch_keeps_three_global_workers_and_two_bilibili_slots(self):
        tasks = [
            (downloader.BILIBILI, "https://b23.tv/first"),
            (downloader.BILIBILI, "https://b23.tv/second"),
            (downloader.YOUTUBE, "https://youtu.be/third"),
        ]
        barrier = threading.Barrier(3)
        lock = threading.Lock()
        active = 0
        active_bilibili = 0
        maximum_active = 0
        maximum_bilibili = 0

        def fake_download(url, platform=None, **kwargs):
            nonlocal active, active_bilibili, maximum_active, maximum_bilibili
            with lock:
                active += 1
                if platform == downloader.BILIBILI:
                    active_bilibili += 1
                maximum_active = max(maximum_active, active)
                maximum_bilibili = max(maximum_bilibili, active_bilibili)
            barrier.wait(timeout=1)
            with lock:
                active -= 1
                if platform == downloader.BILIBILI:
                    active_bilibili -= 1
            return {"title": url}

        with patch("downloader.download_video", side_effect=fake_download):
            downloader.download_tasks(tasks)

        self.assertEqual(maximum_active, 3)
        self.assertEqual(maximum_bilibili, 2)
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
../../venv/bin/python -m unittest \
  tests.test_parallel_downloads.ParallelDownloadTests.test_bilibili_runs_at_most_two_tasks_concurrently \
  tests.test_parallel_downloads.ParallelDownloadTests.test_mixed_batch_keeps_three_global_workers_and_two_bilibili_slots -v
```

Expected: the first test fails because the current maximum is 3.

- [ ] **Step 3: Implement the Bilibili semaphore**

Add `import threading`, then add:

```python
MAX_PARALLEL_BILIBILI_DOWNLOADS = 2
```

Inside `download_tasks()`, before `_run_task`, create:

```python
    bilibili_slots = threading.BoundedSemaphore(
        MAX_PARALLEL_BILIBILI_DOWNLOADS
    )
```

Inside `_run_task`, wrap the existing `download_video()` call with one local helper:

```python
        def _download_current_task():
            return download_video(
                url,
                index=task_index + 1,
                total=total,
                platform=platform,
                progress_callback=(
                    _relay_progress if progress_callback else None
                ),
                media_type=media_type,
            )

        try:
            if platform == BILIBILI:
                with bilibili_slots:
                    result = _download_current_task()
            else:
                result = _download_current_task()
```

Keep the existing `except` block and all progress events unchanged.

- [ ] **Step 4: Run all concurrency and progress tests**

Run:

```bash
../../venv/bin/python -m unittest tests.test_parallel_downloads tests.test_web_progress -v
```

Expected: all tests pass, including the existing global maximum of 3 and progress index checks.

- [ ] **Step 5: Commit the concurrency boundary**

```bash
git add downloader.py tests/test_parallel_downloads.py
git commit -m "perf: limit concurrent Bilibili tasks"
```

---

### Task 3: Document the Performance Behavior

**Files:**
- Modify: `README.md:335-350`
- Test: `tests/test_bilibili_support.py:250-290`

**Interfaces:**
- Consumes: the Bilibili native chunk and concurrency behavior from Tasks 1 and 2.
- Produces: user-facing guidance that explains the CDN dependency and conservative acceleration limits.

- [ ] **Step 1: Write a failing documentation test**

Append to the `required` list in `BilibiliDocumentationTests`:

```python
            "10 MB HTTP 分块",
            "最多同时运行 2 个 Bilibili 下载任务",
            "实际速度仍取决于 Bilibili 分配的 CDN 和网络路由",
```

- [ ] **Step 2: Run the documentation test and verify RED**

Run:

```bash
../../venv/bin/python -m unittest tests.test_bilibili_support.BilibiliDocumentationTests -v
```

Expected: fail because the README does not contain the performance guidance.

- [ ] **Step 3: Add the README performance row**

Add this FAQ row after the existing Bilibili HTTP 412 row:

```markdown
| Bilibili 下载速度较慢 | 项目使用 10 MB HTTP 分块，并且最多同时运行 2 个 Bilibili 下载任务；实际速度仍取决于 Bilibili 分配的 CDN 和网络路由，客户端优化不保证绕过平台侧限速 |
```

- [ ] **Step 4: Run the documentation and Bilibili regression tests**

Run:

```bash
../../venv/bin/python -m unittest tests.test_bilibili_support -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the documentation**

```bash
git add README.md tests/test_bilibili_support.py
git commit -m "docs: explain Bilibili download acceleration"
```

---

### Task 4: Run Controlled Baseline and Optimized Downloads

**Files:**
- Modify only if measurement triggers the rollback rules: `downloader.py`, `tests/test_bilibili_support.py`, `README.md`
- Temporary outputs: `/private/tmp/bili-speed-baseline.*`, `/private/tmp/bili-speed-optimized.*`, and optionally `/private/tmp/bili-speed-chunk-only.*`

**Interfaces:**
- Consumes: `https://b23.tv/hkl7PC7`, `bilibili_cookies.txt`, yt-dlp's native downloader, and the exact highest video-only format selected by `bestvideo`.
- Produces: wall-clock time, final byte size, average bytes per second, error observations, and a retain-or-rollback decision.

- [ ] **Step 1: Record the selected format and CDN without downloading**

Run from the worktree:

```bash
../../venv/bin/python -m yt_dlp \
  --cookies ../../bilibili_cookies.txt \
  --skip-download \
  --dump-single-json \
  -f bestvideo \
  "https://b23.tv/hkl7PC7" \
  | jq -r '[.format_id, .protocol, (.url | capture("^https?://(?<host>[^/]+)").host)] | @tsv'
```

Expected: one direct HTTPS video format is selected; record the format ID.

- [ ] **Step 2: Download the baseline video stream**

Run:

```bash
/usr/bin/time -p ../../venv/bin/python -m yt_dlp \
  --cookies ../../bilibili_cookies.txt \
  --no-playlist \
  --newline \
  -f bestvideo \
  -o "/private/tmp/bili-speed-baseline.%(ext)s" \
  "https://b23.tv/hkl7PC7"
```

Record `real` seconds, final file size from `stat -f %z /private/tmp/bili-speed-baseline.*`, average bytes per second as size divided by `real`, and any 403, 412, or retry output.

- [ ] **Step 3: Download with both proposed native parameters**

Run:

```bash
/usr/bin/time -p ../../venv/bin/python -m yt_dlp \
  --cookies ../../bilibili_cookies.txt \
  --no-playlist \
  --newline \
  --http-chunk-size 10M \
  --throttled-rate 256K \
  -f bestvideo \
  -o "/private/tmp/bili-speed-optimized.%(ext)s" \
  "https://b23.tv/hkl7PC7"
```

Record the same fields as the baseline. Confirm both files have identical byte sizes.

- [ ] **Step 4: Apply the retention rule**

If optimized average throughput is at least 10% higher and no new 403, 412, repeated re-extraction, or progress regression occurred, retain both parameters.

If the combined profile fails that rule, run a third download with `--http-chunk-size 10M` and no `--throttled-rate`, writing `/private/tmp/bili-speed-chunk-only.%(ext)s`. Retain only `http_chunk_size` if this run is at least 10% faster than baseline without new errors; remove `BILIBILI_THROTTLED_RATE`, remove the production `throttled_rate` option, and change the option test to assert that `throttled_rate` is absent.

If chunk-only also fails, remove both speed constants and both production options, change the option test to assert that `http_chunk_size` and `throttled_rate` are absent, remove `"10 MB HTTP 分块"` from the documentation test, and replace the README row with:

```markdown
| Bilibili 下载速度较慢 | 项目最多同时运行 2 个 Bilibili 下载任务；实际速度仍取决于 Bilibili 分配的 CDN 和网络路由，客户端并发控制不保证绕过平台侧限速 |
```

In every outcome, keep the Bilibili concurrency limit.

- [ ] **Step 5: Verify any measurement-driven rollback**

Run after the retention decision:

```bash
../../venv/bin/python -m unittest \
  tests.test_bilibili_support.BilibiliDownloadOptionsTests \
  tests.test_parallel_downloads -v
```

Expected: all tests pass and assert only the parameters retained by measurement.

- [ ] **Step 6: Commit a rollback only if measurement required one**

If files changed in Step 4:

```bash
git add downloader.py tests/test_bilibili_support.py README.md
git commit -m "perf: keep measured Bilibili tuning"
```

If no files changed, do not create an empty commit.

---

### Task 5: Complete Verification and Runtime Inspection

**Files:**
- Verify: `downloader.py`, `app.py`, `main.py`, `templates/index.html`, `tests`, `README.md`

**Interfaces:**
- Consumes: the final measured configuration.
- Produces: clean test, compile, JavaScript, Git, API/UI, and 8233 service evidence.

- [ ] **Step 1: Run complete automated verification**

Run:

```bash
../../venv/bin/python -m unittest discover -s tests -v
../../venv/bin/python -m compileall -q app.py downloader.py main.py tests
zsh -c "sed -n '/^<script>$/,/^<\\/script>$/p' templates/index.html | sed '1d;\$d' | node --check"
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 2: Verify and restart the 8233 service safely**

Resolve and inspect the listener with:

```bash
BILI_SERVICE_PID=$(lsof -t -iTCP:8233 -sTCP:LISTEN | head -1)
test -n "$BILI_SERVICE_PID"
lsof -a -p "$BILI_SERVICE_PID" -d cwd -Fn
```

Stop it only if the reported cwd belongs to this project. Start `../../venv/bin/python app.py` from the feature worktree.

- [ ] **Step 3: Inspect the served page and one patched API batch**

Request `http://127.0.0.1:8233/` and confirm the established title, Bilibili copy, separate video/audio inputs, and progress markup remain present. Run the Flask API regression tests to confirm a Bilibili task retains its normalized URL and platform.

- [ ] **Step 4: Review the complete branch diff**

Run:

```bash
git status --short --branch
git diff main...HEAD -- downloader.py tests/test_bilibili_support.py tests/test_parallel_downloads.py README.md
```

Confirm that YouTube/Instagram options, filenames, media formats, progress events, and page layout are unchanged.
