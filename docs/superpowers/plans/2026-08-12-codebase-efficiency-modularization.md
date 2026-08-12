# Codebase Efficiency and Modularization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce avoidable Web polling, filesystem validation, and retained task-state work while splitting the two largest files into focused, dependency-light modules without changing observable download behavior.

**Architecture:** Keep Flask routes, CLI commands, and `downloader.py` public imports stable. Introduce narrow helpers and compatibility re-exports first, then move implementation behind those interfaces. The Web UI remains framework-free and loads one deferred JavaScript file plus one stylesheet.

**Tech Stack:** Python 3, Flask, yt-dlp, standard-library threading/concurrency, vanilla JavaScript, CSS, `unittest`.

## Global Constraints

- Preserve Web and CLI behavior, structured error codes, filenames, covers, audio labels, and retry/redownload semantics.
- Preserve maximum concurrency of 3 globally and 2 for Bilibili.
- Do not add Python, JavaScript, or build-time dependencies.
- Do not modify or delete existing files under `downloads/`.
- Keep public names currently imported from `downloader.py` available.
- Every behavior change follows a red-green-refactor test cycle.

---

### Task 1: Serialize and Adapt Web Status Polling

**Files:**
- Modify: `templates/index.html:1654-1689`
- Test: `tests/test_web_progress.py`

**Interfaces:**
- Consumes: existing `/api/batch/<batch_id>` JSON response.
- Produces: `scheduleNextPoll(delay)`, `pollStatus()` with at most one in-flight request, visibility-aware interval constants, and a batch render signature.

- [ ] **Step 1: Write failing frontend source tests**

Add tests that load the page script source and assert:

```python
def test_frontend_polling_is_serial_and_visibility_aware(self):
    source = frontend_script_source()
    self.assertNotIn("setInterval(pollStatus", source)
    self.assertIn("pollInFlight", source)
    self.assertIn("document.hidden", source)
    self.assertIn('document.addEventListener("visibilitychange"', source)

def test_frontend_skips_unchanged_task_dom_render(self):
    source = frontend_script_source()
    self.assertIn("lastTaskRenderSignature", source)
    self.assertIn("if (renderSignature !== lastTaskRenderSignature)", source)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_web_progress.WebProgressStateTests.test_frontend_polling_is_serial_and_visibility_aware tests.test_web_progress.WebProgressStateTests.test_frontend_skips_unchanged_task_dom_render`

Expected: FAIL because polling still uses `setInterval` and always calls `renderTasks`.

- [ ] **Step 3: Implement serial adaptive polling**

Replace `setInterval` with one timeout scheduled in `finally`, using `800ms` while visible and `3000ms` while hidden. Guard with `pollInFlight`, capture the requested batch ID, and ignore results if `currentBatchId` changed. Add a stable JSON render signature from task status/progress/result/attempt fields; only call `renderTasks` when it changes.

- [ ] **Step 4: Run focused and Web tests**

Run: `venv/bin/python -m unittest tests.test_web_progress -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add templates/index.html tests/test_web_progress.py
git commit -m "perf: serialize web task polling"
```

---

### Task 2: Validate Download Directories Once per Batch

**Files:**
- Modify: `downloader.py:117-153,1615-1645,1858-1945`
- Modify: `task_control.py:89-149,307-475`
- Test: `tests/test_download_locations.py`
- Test: `tests/test_task_control.py`

**Interfaces:**
- Produces: private `_PreparedOutputDir` capabilities created only after full directory validation.
- Consumes: `download_video()` accepts a valid internal capability through `output_dir`; all raw external paths use full validation after URL, option, and cancellation checks.

- [ ] **Step 1: Write failing tests for probe count and public safety**

Add a probe spy around `Path.open`/the generated write-test path to show:

```python
def test_batch_reuses_one_validated_download_directory(self):
    # validate once, then run multiple tasks with one internal capability
    self.assertEqual(probe_count, 1)

def test_direct_download_still_validates_download_directory(self):
    downloader.download_video(url, output_dir=directory)
    self.assertEqual(probe_count, 1)
```

Add a TaskManager runner test asserting the resolved path is retained while the private capability stays internal.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_download_locations tests.test_task_control -q`

Expected: new assertions fail because every task calls the full directory validator and no prepared capability exists.

- [ ] **Step 3: Add the trusted internal path**

Keep `ensure_downloads_dir()` unchanged for raw external paths. Add a private `_PreparedOutputDir` capability plus preparation and resolution helpers. `download_tasks()` uses its prepared capability directly; TaskManager retains one per batch but passes it only when constructed with explicit `capability_aware_runner=True`, while ordinary custom runners receive a plain resolved `str`. The Web route creates one after request validation and configures its global TaskManager explicitly. Request JSON never supplies a capability.

- [ ] **Step 4: Run focused tests**

Run: `venv/bin/python -m unittest tests.test_download_locations tests.test_task_control tests.test_parallel_downloads -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add downloader.py task_control.py tests/test_download_locations.py tests/test_task_control.py tests/test_parallel_downloads.py
git commit -m "perf: reuse validated download directories"
```

---

### Task 3: Bound Task and Preview Retained State

**Files:**
- Modify: `task_control.py:524-685`
- Modify: `collection_resolver.py:297-326`
- Test: `tests/test_task_control.py`
- Test: `tests/test_collection_resolver.py`

**Interfaces:**
- Produces: `MAX_PUBLIC_ATTEMPTS = 20`; `PreviewStore(ttl_seconds=1800, max_items=100)`.

- [ ] **Step 1: Write failing lifecycle tests**

Add tests asserting terminal tasks are absent from `_tokens` and `_futures`, public attempts contain only the last 20 records while `attempt_count` remains total, and the preview store evicts expired then earliest-deadline entries when capacity is exceeded.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_task_control tests.test_collection_resolver -q`

Expected: FAIL because terminal handles and unbounded public history remain.

- [ ] **Step 3: Implement bounded lifecycle**

In `_finish_attempt`, remove the matching token/future after terminal state is committed. In `_public_task`, slice only the copied `attempts` list. Give `PreviewStore` a positive `max_items`, prune under a single lock, and evict `min(items, key=deadline)` until within capacity.

- [ ] **Step 4: Run focused tests**

Run: `venv/bin/python -m unittest tests.test_task_control tests.test_collection_resolver -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add task_control.py collection_resolver.py tests/test_task_control.py tests/test_collection_resolver.py
git commit -m "perf: bound retained task and preview state"
```

---

### Task 4: Extract Homepage CSS and JavaScript

**Files:**
- Create: `static/css/index.css`
- Create: `static/js/index.js`
- Modify: `templates/index.html`
- Modify: `tests/test_web_progress.py`
- Modify: `tests/test_bilibili_support.py`

**Interfaces:**
- Produces: stylesheet loaded through `url_for('static', filename='css/index.css')`; deferred script loaded through `url_for('static', filename='js/index.js')`.
- Compatibility: functions referenced by inline event attributes remain available on `window`.

- [ ] **Step 1: Write failing asset-boundary tests**

Add helpers to read template plus static assets and assert the template contains no large inline `<style>`/`<script>` blocks, references both assets, and the JavaScript exposes the inline handler names via `Object.assign(window, {...})`.

- [ ] **Step 2: Run Web surface tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_web_progress tests.test_bilibili_support.BilibiliSurfaceIntegrationTests -q`

Expected: FAIL because assets do not yet exist.

- [ ] **Step 3: Move assets without changing behavior**

Mechanically move style and script content. Replace Jinja-only URL values needed by JavaScript with `data-*` attributes or constants in the HTML. Update test helpers so behavioral source assertions read `static/js/index.js` and style assertions read `static/css/index.css`.

- [ ] **Step 4: Run syntax and Web tests**

Run:

```bash
node --check static/js/index.js
venv/bin/python -m unittest tests.test_web_progress tests.test_bilibili_support -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add templates/index.html static/css/index.css static/js/index.js tests/test_web_progress.py tests/test_bilibili_support.py
git commit -m "refactor: extract homepage static assets"
```

---

### Task 5: Extract Media Source and Output File Modules

**Files:**
- Create: `media_sources.py`
- Create: `output_files.py`
- Modify: `downloader.py`
- Modify: `collection_resolver.py`
- Test: `tests/test_bilibili_support.py`
- Test: `tests/test_download_locations.py`
- Test: `tests/test_downloader_errors.py`

**Interfaces:**
- `media_sources.py` produces existing platform constants plus `normalize_url`, `detect_platform`, `detect_collection_platform`, `make_task`, `find_cookie_file`, and `platform_http_headers`.
- `output_files.py` produces directory preparation, output templates, attempt workspace cleanup, output resolution, atomic claim/finalization, version parsing, and filesize formatting.
- `downloader.py` re-exports all previously public names.

- [ ] **Step 1: Write failing module contract tests**

Add import tests that call the new modules and assert identity/behavior matches existing `downloader` exports for representative YouTube, Instagram, Bilibili, share-text, output naming, and directory validation cases.

- [ ] **Step 2: Run contract tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_bilibili_support tests.test_download_locations tests.test_downloader_errors -q`

Expected: FAIL with missing modules.

- [ ] **Step 3: Move source parsing first**

Move only source-related constants and functions to `media_sources.py`. Import and re-export them from `downloader.py`; update `collection_resolver.py` to import directly from `media_sources.py`. Run source tests before proceeding.

- [ ] **Step 4: Move output file helpers**

Move directory, template, workspace, resolution, atomic naming and filesize helpers to `output_files.py`. Pass only primitive configuration or an audio output extension into this module so it does not import `downloader.py` or `audio_output.py`.

- [ ] **Step 5: Run focused tests**

Run: `venv/bin/python -m unittest tests.test_bilibili_support tests.test_download_locations tests.test_downloader_errors -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add media_sources.py output_files.py downloader.py collection_resolver.py tests/test_bilibili_support.py tests/test_download_locations.py tests/test_downloader_errors.py
git commit -m "refactor: split source and output helpers"
```

---

### Task 6: Extract Progress and Audio Output Modules

**Files:**
- Create: `download_progress.py`
- Create: `audio_output.py`
- Modify: `downloader.py`
- Test: `tests/test_downloader_errors.py`
- Test: `tests/test_parallel_downloads.py`

**Interfaces:**
- `download_progress.py` produces current progress formatting and hook factories, accepting cancellation objects through a small protocol (`raise_if_cancelled`).
- `audio_output.py` produces `AudioOutputProfile`, selected-audio inspection, profile selection, quality labels, postprocessor options, source-copy validation, and profile updates based on final paths.
- `downloader.py` keeps compatibility aliases for tested private names during this refactor.

- [ ] **Step 1: Write failing module contract tests**

Test the wished-for imports and compare representative MP3, FLAC, source, WAV, ANSI progress, size, ETA and postprocessor-stage outputs with the established behavior.

- [ ] **Step 2: Run tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_downloader_errors tests.test_parallel_downloads -q`

Expected: FAIL with missing modules.

- [ ] **Step 3: Move progress helpers and preserve aliases**

Move formatting and hooks without changing payload keys. Import aliases into `downloader.py` so existing tests and consumers continue to work.

- [ ] **Step 4: Move audio helpers and preserve aliases**

Move profile and postprocessor decisions. Keep actual file rename/finalization in `output_files.py`; `audio_output.py` supplies the quality label and desired extension.

- [ ] **Step 5: Run focused tests**

Run: `venv/bin/python -m unittest tests.test_downloader_errors tests.test_parallel_downloads tests.test_bilibili_support -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add download_progress.py audio_output.py downloader.py tests/test_downloader_errors.py tests/test_parallel_downloads.py tests/test_bilibili_support.py
git commit -m "refactor: split progress and audio helpers"
```

---

### Task 7: Unify Download Finalization and Cache Environment Discovery

**Files:**
- Modify: `downloader.py:1308-1833`
- Modify: `bilibili_acceleration.py:106-148`
- Modify: `audio_output.py`
- Modify: `output_files.py`
- Test: `tests/test_bilibili_support.py`
- Test: `tests/test_bilibili_acceleration.py`
- Test: `tests/test_downloader_errors.py`

**Interfaces:**
- Produces: one `_finalize_download_output(info, filepath, media_type, profile, output_version)` result used by both Bilibili and other platforms.
- Produces: cached `aria2c_path(refresh: bool = False)` and cached Node discovery helper.

- [ ] **Step 1: Write failing parity and cache tests**

Test that equivalent audio/video metadata produces the same result fields through both platform paths and that repeated aria2/Node discovery calls scan once until `refresh=True`.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_bilibili_support tests.test_bilibili_acceleration tests.test_downloader_errors -q`

Expected: FAIL because result assembly remains duplicated and environment discovery is uncached.

- [ ] **Step 3: Add shared finalization helper**

The helper finalizes the visible filename, determines actual output version, updates source-profile extension, and delegates to the existing result builder. Replace both duplicated blocks while preserving exact result keys.

- [ ] **Step 4: Add explicit environment caches**

Use module-level lock-protected cached values with an unambiguous sentinel, not `functools.cache`, so tests and callers can force refresh. Keep environment-variable precedence unchanged.

- [ ] **Step 5: Run focused tests**

Run: `venv/bin/python -m unittest tests.test_bilibili_support tests.test_bilibili_acceleration tests.test_downloader_errors -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add downloader.py bilibili_acceleration.py audio_output.py output_files.py tests/test_bilibili_support.py tests/test_bilibili_acceleration.py tests/test_downloader_errors.py
git commit -m "refactor: unify download finalization"
```

---

### Task 8: Full Regression, Performance Evidence, and Visual QA

**Files:**
- Modify only if verification exposes a regression.
- Test: all `tests/*.py`

**Interfaces:**
- Consumes all prior task outputs.
- Produces final verification evidence and a clean branch ready for review.

- [ ] **Step 1: Capture downloads manifest**

Run:

```bash
find /Users/markyang/Projects/Multiple_Video_Downloader/downloads -type f -exec shasum -a 256 {} \; | LC_ALL=C sort > /tmp/mvd-optimization-downloads-before.sha256
```

- [ ] **Step 2: Run full automated verification**

Run:

```bash
venv/bin/python -m unittest discover -s tests -v
venv/bin/python -m compileall -q *.py tests
node --check static/js/index.js
git diff --check
```

Expected: 246 or more tests pass; only the two existing Windows-only tests skip on macOS; all commands exit 0.

- [ ] **Step 3: Measure the changed hot paths**

Use deterministic tests/spies to report: maximum one in-flight poll, one full directory probe per batch, terminal handle counts return to zero, preview store never exceeds capacity. Report structural line counts for the former giant files; do not claim network download speed changes.

- [ ] **Step 4: Run local browser QA on a non-conflicting port**

Start Flask on port `8234`, then verify desktop and mobile layouts, video/audio inputs, directory picker state, collection preview, task status polling, retry/cancel/redownload controls, console errors, and absence of horizontal overflow. Do not stop or replace any process on port `8233`.

- [ ] **Step 5: Recheck downloads manifest**

Run the same absolute-path `find ... shasum` command and compare with `/tmp/mvd-optimization-downloads-before.sha256` using `cmp`.

Expected: identical manifest.

- [ ] **Step 6: Request independent code review**

Provide the design, plan, base SHA `942106c`, branch HEAD, test evidence and diff to the reviewer. Resolve all Critical and Important findings with new failing regression tests.

- [ ] **Step 7: Final verification commit**

If review fixes were needed, commit them with:

```bash
git add <reviewed-files>
git commit -m "fix: address optimization review findings"
```

Then rerun Step 2 and confirm `git status --short` is empty.
