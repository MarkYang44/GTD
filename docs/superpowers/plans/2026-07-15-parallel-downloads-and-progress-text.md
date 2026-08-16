# Parallel Downloads and Progress Text Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run up to three mixed YouTube/Instagram downloads concurrently while preserving input order and removing ANSI control codes from displayed progress percentages.

**Architecture:** Keep scheduling in `downloader.py` so both CLI and Web entrypoints share the behavior. Use a fixed-size `ThreadPoolExecutor`, relay callbacks with each task's original index, store results in input order, and sanitize progress at the yt-dlp data boundary. Keep Web batch mutation behind its existing lock and make terminal state events idempotent.

**Tech Stack:** Python 3.9+, `concurrent.futures`, `threading`, `unittest`, `unittest.mock`, Flask, yt-dlp.

## Global Constraints

- Maximum parallel downloads is exactly 3.
- `download_tasks(tasks, progress_callback=None)` keeps its existing public signature and return order.
- Web and CLI modes both use the shared parallel scheduler.
- Existing URL recognition, platform options, cookies, download directory, output naming, video quality, and failure-continuation behavior remain unchanged.
- No pause, cancellation, retry UI, runtime concurrency control, persistent database, or duplicate-URL coordination is added.
- Production changes must follow a failing-test-first red-green cycle.
- This directory is not a Git repository, so commit steps are documented but skipped unless Git metadata becomes available.

---

## File Map

- Modify `downloader.py`: ANSI sanitization, fixed concurrency constant, thread-pool scheduling, ordered results, and concurrency-safe terminal progress lines.
- Modify `app.py`: ignore duplicate terminal events when updating task state and aggregate counters.
- Modify `tests/test_downloader_errors.py`: regression tests for ANSI progress text and complete-line progress output.
- Create `tests/test_parallel_downloads.py`: bounded concurrency, ordered results, callback-index, and failure-continuation tests.
- Modify `tests/test_web_progress.py`: duplicate terminal-event regression tests.
- Modify `README.md`: document default three-task parallel behavior and updated Web states.

### Task 1: Sanitize yt-dlp progress percentages

**Files:**
- Modify: `tests/test_downloader_errors.py`
- Modify: `downloader.py`

**Interfaces:**
- Consumes: yt-dlp progress dictionary field `_percent_str`.
- Produces: `_strip_ansi(value: object) -> str` and ANSI-free `percent_text` from `_extract_progress_snapshot(data: dict) -> dict[str, object]`.

- [ ] **Step 1: Write the failing ANSI regression test**

Add to `DownloadProgressHookTests`:

```python
def test_progress_snapshot_removes_ansi_color_codes_from_percent(self):
    snapshot = downloader._extract_progress_snapshot({
        "_percent_str": "\x1b[0;94m100.0%\x1b[0m",
        "speed": 1024 * 1024,
        "eta": 0,
    })

    self.assertEqual(snapshot["percent_text"], "100.0%")
    self.assertNotIn("\x1b", snapshot["percent_text"])
```

- [ ] **Step 2: Run the test and verify the observed bug**

Run:

```bash
venv/bin/python -m unittest tests.test_downloader_errors.DownloadProgressHookTests.test_progress_snapshot_removes_ansi_color_codes_from_percent -v
```

Expected: FAIL because `percent_text` still equals `\x1b[0;94m100.0%\x1b[0m`.

- [ ] **Step 3: Add minimal ANSI sanitization**

Add beside the progress helpers in `downloader.py`:

```python
ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _strip_ansi(value: object) -> str:
    """Remove terminal control sequences from a display value."""
    return ANSI_ESCAPE_RE.sub("", str(value or "")).strip()
```

Change `_extract_progress_snapshot()` to:

```python
percent_text = _strip_ansi(data.get("_percent_str")) or "计算中"
```

- [ ] **Step 4: Run the focused and existing progress tests**

Run:

```bash
venv/bin/python -m unittest tests.test_downloader_errors.DownloadProgressHookTests -v
```

Expected: all progress-hook tests PASS.

- [ ] **Step 5: Commit if Git becomes available**

```bash
git add downloader.py tests/test_downloader_errors.py
git commit -m "fix: sanitize download progress text"
```

Expected in the current workspace: skip because `git rev-parse --show-toplevel` reports that this is not a Git repository.

### Task 2: Add a bounded parallel scheduler with ordered results

**Files:**
- Create: `tests/test_parallel_downloads.py`
- Modify: `downloader.py`

**Interfaces:**
- Consumes: `list[VideoTask]`, existing `download_video(...)`, and optional `ProgressCallback`.
- Produces: `MAX_PARALLEL_DOWNLOADS = 3`; unchanged `download_tasks(tasks, progress_callback=None)` returning results in input order.

- [ ] **Step 1: Write failing tests for the concurrency limit and ordered output**

Create `tests/test_parallel_downloads.py` with imports and this test class:

```python
import threading
import time
import unittest
from unittest.mock import patch

import downloader


class ParallelDownloadTests(unittest.TestCase):
    def test_download_tasks_runs_at_most_three_concurrently_and_preserves_order(self):
        tasks = [
            (downloader.YOUTUBE, f"https://youtu.be/video-{index}")
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
            time.sleep(0.02 * (5 - int(url.rsplit("-", 1)[1])))
            with lock:
                active -= 1
            return {"title": url}

        with patch("downloader.download_video", side_effect=fake_download):
            results = downloader.download_tasks(tasks)

        self.assertEqual(maximum_active, 3)
        self.assertEqual(
            [result["title"] for _, result in results],
            [url for _, url in tasks],
        )

    def test_progress_events_keep_each_tasks_original_index(self):
        tasks = [
            (downloader.YOUTUBE, "https://youtu.be/first"),
            (downloader.INSTAGRAM, "https://instagram.com/reel/second"),
        ]
        events = []
        event_lock = threading.Lock()

        def callback(index, event, data):
            with event_lock:
                events.append((index, event, data))

        def fake_download(url, progress_callback=None, **kwargs):
            progress_callback("progress", {"percent_text": url})
            return {"title": url}

        with patch("downloader.download_video", side_effect=fake_download):
            downloader.download_tasks(tasks, progress_callback=callback)

        for index, (_, url) in enumerate(tasks):
            task_events = [
                (event, data)
                for event_index, event, data in events
                if event_index == index
            ]
            self.assertEqual(
                [event for event, _ in task_events],
                ["started", "progress", "completed"],
            )
            self.assertEqual(task_events[1][1]["percent_text"], url)
```

- [ ] **Step 2: Run the bounded-concurrency test and verify it fails**

Run:

```bash
venv/bin/python -m unittest tests.test_parallel_downloads.ParallelDownloadTests.test_download_tasks_runs_at_most_three_concurrently_and_preserves_order -v
```

Expected: FAIL because the serial implementation never sets `three_started`.

- [ ] **Step 3: Implement the fixed-size worker pool**

Replace `import time` with:

```python
from concurrent.futures import ThreadPoolExecutor
```

Add near the constants:

```python
MAX_PARALLEL_DOWNLOADS = 3
```

Replace the serial body of `download_tasks()` with a nested worker and ordered `executor.map()`:

```python
total = len(tasks)
if not tasks:
    return []

def _run_task(index_and_task):
    task_index, task = index_and_task
    platform, url = task

    if progress_callback:
        progress_callback(task_index, "started", {"url": url, "platform": platform})

    def _relay_progress(event: str, data: dict[str, object]) -> None:
        if progress_callback:
            progress_callback(task_index, event, data)

    result = download_video(
        url,
        index=task_index + 1,
        total=total,
        platform=platform,
        progress_callback=_relay_progress if progress_callback else None,
    )

    if progress_callback:
        if result:
            progress_callback(task_index, "completed", result)
        else:
            progress_callback(task_index, "failed", {"error": "下载失败"})
    return task, result

worker_count = min(MAX_PARALLEL_DOWNLOADS, total)
with ThreadPoolExecutor(max_workers=worker_count) as executor:
    return list(executor.map(_run_task, enumerate(tasks)))
```

- [ ] **Step 4: Run the focused scheduler test**

Run:

```bash
venv/bin/python -m unittest tests.test_parallel_downloads.ParallelDownloadTests.test_download_tasks_runs_at_most_three_concurrently_and_preserves_order -v
```

Expected: PASS, with `maximum_active == 3`, ordered results, and correct original callback indices.

- [ ] **Step 5: Commit if Git becomes available**

```bash
git add downloader.py tests/test_parallel_downloads.py
git commit -m "feat: download up to three videos concurrently"
```

Expected in the current workspace: skip because it is not a Git repository.

### Task 3: Continue after an unexpected worker failure

**Files:**
- Modify: `tests/test_parallel_downloads.py`
- Verify: `downloader.py`

**Interfaces:**
- Consumes: scheduler created in Task 2.
- Produces: a result entry and `failed` event for exceptions; continued execution of other tasks.

- [ ] **Step 1: Add the failing worker-exception regression test**

Append to `ParallelDownloadTests`:

```python
def test_worker_exception_marks_only_that_task_failed(self):
    tasks = [
        (downloader.YOUTUBE, "https://youtu.be/good-1"),
        (downloader.YOUTUBE, "https://youtu.be/bad"),
        (downloader.YOUTUBE, "https://youtu.be/good-2"),
    ]
    events = []

    def fake_download(url, **kwargs):
        if url.endswith("bad"):
            raise RuntimeError("boom")
        return {"title": url}

    with patch("downloader.download_video", side_effect=fake_download):
        results = downloader.download_tasks(
            tasks,
            progress_callback=lambda index, event, data: events.append((index, event)),
        )

    self.assertIsNotNone(results[0][1])
    self.assertIsNone(results[1][1])
    self.assertIsNotNone(results[2][1])
    self.assertIn((1, "failed"), events)
    self.assertIn((2, "completed"), events)
```

- [ ] **Step 2: Run the test and verify the worker exception escapes**

```bash
venv/bin/python -m unittest tests.test_parallel_downloads.ParallelDownloadTests.test_worker_exception_marks_only_that_task_failed -v
```

Expected: ERROR with `RuntimeError: boom` when `executor.map()` retrieves the failing task result.

- [ ] **Step 3: Convert an unexpected worker exception into one failed result**

Wrap Task 2's `download_video()` call in `_run_task()` with:

```python
try:
    result = download_video(
        url,
        index=task_index + 1,
        total=total,
        platform=platform,
        progress_callback=_relay_progress if progress_callback else None,
    )
except Exception as error:
    print(f"\n❌ 任务 {task_index + 1} 发生未知错误: {error}")
    result = None
```

- [ ] **Step 4: Run the complete parallel scheduler test module**

Run:

```bash
venv/bin/python -m unittest tests.test_parallel_downloads -v
```

Expected: all three parallel scheduler tests PASS.

- [ ] **Step 5: Commit if Git becomes available**

```bash
git add downloader.py tests/test_parallel_downloads.py
git commit -m "test: cover parallel download event isolation"
```

Expected in the current workspace: skip because it is not a Git repository.

### Task 4: Make Web terminal events idempotent

**Files:**
- Modify: `tests/test_web_progress.py`
- Modify: `app.py`

**Interfaces:**
- Consumes: `_apply_progress_event(batch: dict, task_index: int, event: str, data: object)`.
- Produces: a task reaches one terminal state once; repeated or stale events cannot change counters or regress the task to downloading.

- [ ] **Step 1: Write failing duplicate and stale-event tests**

Add to `WebProgressStateTests`:

```python
def test_duplicate_terminal_event_does_not_increment_count_twice(self):
    batch = web_app._create_batch([(downloader.YOUTUBE, "https://youtu.be/example")])

    web_app._apply_progress_event(batch, 0, "completed", {"title": "done"})
    web_app._apply_progress_event(batch, 0, "completed", {"title": "done"})

    self.assertEqual(batch["completed"], 1)
    self.assertEqual(batch["failed"], 0)

def test_progress_after_terminal_event_does_not_regress_status(self):
    batch = web_app._create_batch([(downloader.YOUTUBE, "https://youtu.be/example")])

    web_app._apply_progress_event(batch, 0, "failed", {"error": "failed"})
    web_app._apply_progress_event(batch, 0, "progress", {"percent_text": "99%"})

    self.assertEqual(batch["tasks"][0]["status"], "failed")
    self.assertEqual(batch["failed"], 1)
```

- [ ] **Step 2: Run and verify both tests fail**

Run:

```bash
venv/bin/python -m unittest \
  tests.test_web_progress.WebProgressStateTests.test_duplicate_terminal_event_does_not_increment_count_twice \
  tests.test_web_progress.WebProgressStateTests.test_progress_after_terminal_event_does_not_regress_status -v
```

Expected: first test reports `2 != 1`; second reports `downloading != failed`.

- [ ] **Step 3: Guard terminal tasks from subsequent events**

In `_apply_progress_event()`, after obtaining `task`, add:

```python
if task["status"] in {"completed", "failed"}:
    return
```

- [ ] **Step 4: Run all Web progress tests**

Run:

```bash
venv/bin/python -m unittest tests.test_web_progress -v
```

Expected: all Web progress state tests PASS.

- [ ] **Step 5: Commit if Git becomes available**

```bash
git add app.py tests/test_web_progress.py
git commit -m "fix: keep web download counters idempotent"
```

Expected in the current workspace: skip because it is not a Git repository.

### Task 5: Prevent concurrent terminal progress lines from overwriting each other

**Files:**
- Modify: `tests/test_downloader_errors.py`
- Modify: `downloader.py`

**Interfaces:**
- Consumes: `_make_progress_hook(index, total, progress_callback=None)`.
- Produces: one newline-terminated progress record per hook invocation, with the existing task number, speed, percent, and ETA fields.

- [ ] **Step 1: Write the failing complete-line output test**

Add to `DownloadProgressHookTests`:

```python
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
```

- [ ] **Step 2: Run and verify the test fails**

Run:

```bash
venv/bin/python -m unittest tests.test_downloader_errors.DownloadProgressHookTests.test_progress_hook_emits_complete_line_for_parallel_cli_output -v
```

Expected: FAIL because current output ends with `\r`.

- [ ] **Step 3: Emit a normal complete line**

In `_make_progress_hook()`, remove `end="\r"` from the downloading `print()` call so it uses the default newline. Do not change the displayed fields or callback behavior.

- [ ] **Step 4: Run all downloader tests**

Run:

```bash
venv/bin/python -m unittest tests.test_downloader_errors -v
```

Expected: all downloader error and progress tests PASS.

- [ ] **Step 5: Commit if Git becomes available**

```bash
git add downloader.py tests/test_downloader_errors.py
git commit -m "fix: isolate concurrent cli progress lines"
```

Expected in the current workspace: skip because it is not a Git repository.

### Task 6: Update documentation and run full verification

**Files:**
- Modify: `README.md`
- Verify: `app.py`, `downloader.py`, `main.py`, `tests/*.py`, `templates/index.html`

**Interfaces:**
- Consumes: completed behavior from Tasks 1-5.
- Produces: user-facing documentation matching the default three-task concurrency and ANSI-free progress display.

- [ ] **Step 1: Update user-facing behavior descriptions**

Make these exact documentation changes:

```markdown
- 一批任务最多同时下载 3 个视频，超过上限的任务自动排队
```

Replace “后端会按顺序下载所有链接” with:

```markdown
后端最多同时下载 3 个链接，超过上限的任务会保持“等待中”，直到有下载位置空闲。
```

Add to Web troubleshooting:

```markdown
| Web 进度出现控制码或乱码 | 重启 Web 服务并强制刷新页面；新版会在后端清除 yt-dlp 的终端颜色控制码 |
```

- [ ] **Step 2: Run the entire automated test suite**

Run:

```bash
venv/bin/python -m unittest discover -s tests -v
```

Expected: all tests PASS with zero failures and zero errors.

- [ ] **Step 3: Compile all Python entrypoints and tests**

Run:

```bash
venv/bin/python -m compileall -q app.py downloader.py main.py tests
```

Expected: exit code 0 and no output.

- [ ] **Step 4: Verify requirements against source text**

Run:

```bash
rg -n "MAX_PARALLEL_DOWNLOADS = 3|ThreadPoolExecutor|ANSI_ESCAPE_RE|task\[\"status\"\] in" downloader.py app.py
rg -n "最多同时下载 3 个|控制码或乱码" README.md
```

Expected: source matches for the scheduler, ANSI cleanup, terminal-state guard, and both documentation updates.

- [ ] **Step 5: Exercise the Flask API without real network downloads**

Run this test-client script. It patches `app.download_tasks`, submits four valid URLs, waits for the background thread, and never calls yt-dlp or accesses the internet:

```bash
venv/bin/python - <<'PY'
import time
from unittest.mock import patch

import app


def fake_download_tasks(tasks, progress_callback=None):
    results = []
    for index, task in enumerate(tasks):
        progress_callback(index, "started", {})
        result = {"title": f"video-{index}"}
        progress_callback(index, "completed", result)
        results.append((task, result))
    return results


urls = [f"https://youtu.be/video-{index}" for index in range(4)]
with patch("app.download_tasks", side_effect=fake_download_tasks):
    with app.app.test_client() as client:
        response = client.post("/api/download", json={"urls": urls})
        assert response.status_code == 200, response.get_data(as_text=True)
        body = response.get_json()
        assert body["task_count"] == 4, body
        batch_id = body["batch_id"]
        for _ in range(100):
            status_response = client.get(f"/api/batch/{batch_id}")
            assert status_response.status_code == 200
            batch = status_response.get_json()
            if batch["all_done"]:
                break
            time.sleep(0.01)
        assert batch["all_done"] is True, batch
        assert batch["completed"] == 4, batch
print("Flask API smoke test passed")
PY
```

Expected: `/api/download` returns HTTP 200 with `task_count == 4`; subsequent batch status returns HTTP 200 and `all_done == true`.

- [ ] **Step 6: Review the final diff manually**

Because this is not a Git repository, inspect the changed files directly and confirm every changed line maps to the approved specification. Confirm no cookie files or downloaded media are included in the work.

- [ ] **Step 7: Restart and browser verification handoff**

Stop any existing `python app.py` process, restart with:

```bash
cd /Users/markyang/Projects/GTD
source venv/bin/activate
python app.py
```

Open `http://127.0.0.1:5000`, submit at least four authorized links, and verify no more than three cards are “下载中” simultaneously and no progress text contains `�[` or `[0;94m`.

- [ ] **Step 8: Commit if Git becomes available**

```bash
git add README.md app.py downloader.py tests/test_downloader_errors.py tests/test_parallel_downloads.py tests/test_web_progress.py
git commit -m "feat: add parallel video downloads"
```

Expected in the current workspace: skip because it is not a Git repository.
