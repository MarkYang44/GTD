# GTD Maintainability Refactoring Plan

**Goal:** Reduce the cost of changing GTD without changing download, extraction, task-history, or browser behavior.

**Approved design:** Apply the four recommendations discussed with the user: separate Web request handling and initialization, separate download configuration/recovery/finalization, make task data contracts explicit, and share the common browser request/polling primitives.

**Architecture:** Keep Flask/Jinja, plain JavaScript, yt-dlp, FFmpeg, and SQLite. Web and CLI continue to share the same downloader. Use small functions, immutable configuration records, and typed dictionaries rather than an inheritance framework. Keep public compatibility entry points while moving their implementations behind focused boundaries.

## Global constraints

- Python 3.10+; no new runtime dependencies.
- Preserve URLs, Flask endpoint names, API status codes and payload fields, CLI arguments/exit codes, output naming, and persisted history JSON.
- Preserve cancellation, generation guards, global/platform concurrency limits, fallback order, and owned-workspace cleanup.
- Keep the existing uncommitted source-FLAC fix and its tests byte-for-byte unchanged.
- No credentials, source media, task history, or personal paths in new artifacts.
- English is the primary documentation language; keep corresponding Chinese documentation links in sync.
- The implementation phase stayed local on `codex/maintainability-refactor`. The user separately authorized committing and GitHub publication on 2026-10-28.

## Baseline

The isolated unit/JavaScript suite ran 468 tests successfully (2 skipped). The baseline runner uses temporary history and suppresses the default upload cleanup only while importing the legacy app, so existing user state is not rewritten.

## Task 1: Web request boundary and application factory

Files: `app.py`, new `download_requests.py`, new `web_runtime.py`, new `tests/test_app_factory.py`, new `tests/test_download_requests.py`.

- [x] Add a subprocess test proving importing the Web module does not create its history database, plus two-app isolation and injected-runner request tests. Observe the failure before implementation.
- [x] Implement `create_app(config=None, *, manager=None, uploads=None)` with a per-app lazy runtime protected by a lock. Default compatibility proxies must resolve the active Flask application inside requests and the default application outside requests. A worker must capture its own upload store rather than depend on Flask context.
- [x] Preserve `app.app`, `app.task_manager`, `app.preview_store`, legacy endpoint names, and existing test substitution seams. Explicitly initialize the default runtime when starting `python app.py`.
- [x] Extract request settings, preview selection, and direct URL conversion into a Flask-independent parser. Carry the existing structured errors through a dedicated exception; preserve validation order and rejected-link indexes.
- [x] Run factory/parser tests and existing Web, folder, subtitle, collection, and history tests.

## Task 2: Download configuration and recovery boundaries

Files: `downloader.py`, new `download_options.py`, new `bilibili_recovery.py`, focused tests.

- [x] Characterize mixed platform/media option output and fallback decisions using existing tests and additional behavior cases for ordered backup hosts, cancellation, and no cleanup outside an attempt workspace.
- [x] Extract yt-dlp option construction into `download_options.py`; preserve `_build_ydl_options(...)` as a compatibility adapter and all monkeypatch seams used by existing callers/tests. Group repeated media/format/speed values in an immutable configuration object if it reduces real repetition.
- [x] Extract Bilibili attempt planning and retry decisions into `bilibili_recovery.py`, preserving order, lazy backup admission, per-attempt ownership, original-info copy behavior, and error classification. Keep I/O coordination in the downloader and reuse existing finalization helpers.
- [x] Run option, Bilibili, source-audio, subtitle, output-directory, cancellation, and parallel-download tests. Do not modify the pre-existing source-FLAC changes.

## Task 3: Explicit task data contracts

Files: new `task_models.py`, `task_control.py`, `task_history.py`.

- [x] Define Python 3.10-compatible `Literal`/`TypedDict` contracts for task status, attempts, results, and batch state, including optional fields and internal execution handles.
- [x] Apply these contracts at task creation, state-transition, snapshot, and persistence boundaries, using the existing regression tests for observable behavior.
- [x] Extract progress/mode field updates from the long execution method without moving lock scopes or generation guards. Keep SQLite history's explicit allowlists as the serialization/privacy boundary.
- [x] Run task-control, history, retry/cancellation, and local-extraction tests.

## Task 4: Shared browser primitives

Files: new `static/js/task_api.js`, `static/js/index.js`, `static/js/extract_audio.js`, both page templates, JavaScript harnesses.

- [x] Add deterministic tests for timeout covering response bodies, timer cleanup, abort propagation, capped exponential delay, and stale batch selection. Observe the new shared API is absent before implementation.
- [x] Share only JSON transport and capped retry-delay calculation. Retain each page's polling stop/resume policy, in-flight/generation guards, upload XHR, language mapping, and rendering.
- [x] Load the helper before page scripts; update standalone VM harnesses to load the same helper in the same order.
- [x] Run all Node harnesses and real browser regressions, including local upload -> FFmpeg -> download and theme/language behavior.

## Task 5: Integration and review

- [x] Document the resulting boundaries and factory lifecycle in an English architecture note, with synchronized links from both READMEs.
- [x] Run the complete unit/JavaScript suite, real browser suite, Python compilation, JavaScript syntax checks, and whitespace checks.
- [x] Review the whole diff independently for compatibility, initialization races, cleanup ownership, and stale browser responses. Resolve material findings and rerun their covering tests.
- [x] Verify the original four uncommitted audio-fix files retain their original SHA-256 hashes. Report actual verification counts and any untested platform limitations.

## Verified result (2026-10-28)

- Full isolated Python/JavaScript suite: 487 tests, OK with 2 skipped (485 passed).
- Final real-browser suite: 28 tests passed using the installed Google Chrome and isolated temporary state, including generated video upload, real FFmpeg extraction, and browser download.
- Python 3.10 syntax compatibility and current-interpreter compilation: 16 changed/new Python files; JavaScript syntax: 7 files. Markdown links, fences, and whitespace verified.
- Independent downloader review and complete-change review approved; nullable progress/result contracts and the local stream index were corrected during final review. No open findings.
- All four pre-existing source-FLAC repair files retain their original SHA-256 hashes.
- Windows was not executed locally; upstream platform responses were simulated. No claim of improved download speed is made.
- Verification left changes uncommitted on `codex/maintainability-refactor` and left no service running. Publication was separately authorized on 2026-10-28.
