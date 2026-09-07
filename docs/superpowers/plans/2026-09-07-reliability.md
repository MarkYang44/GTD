# GTD reliability implementation plan

User-approved scope: audit sequence 1 → 2 → 3 → 4 → 6. Local commits authorized; no push.

Architecture: retain Flask and plain JS. Add bounded/recoverable polling, structured generated-title metadata, Python startup validation, optional SQLite TaskHistoryStore integrated into TaskManager, a recent-batch selector and browser-local current batch reference. Restarted active work becomes retryable INTERRUPTED, never silently restarts. SQLite state is local and Git-ignored. No byte-level download resume promise.

- [x] Polling: Node tests for 404 releasing controls, network errors retaining batch with backoff, timeout abort and successful recovery. Implement in static/js/index.js.
- [x] Preview localization: tests and collection_resolver.py metadata distinguish generated and source titles; frontend derives local strings only for generated values.
- [x] Compatibility: runtime_requirements.py rejects Python <3.10 before imports; update both entrypoints and both README editions.
- [x] Backend history: task_history.py SQLite storage, TaskManager optional store/list/restore, temporary-database tests for completed and interrupted work, pruning and retry. app.py adds GET /api/batches and configured local state path.
- [x] Browser recovery: save current batch id safely, restore polling on load, add bilingual recent-history selector and refresh button; preserve existing inputs and controls. No automatic downloads upon selecting history.
- [x] Reproducibility: immutable tested dependency baseline and explicit opt-in updates, macOS/Windows CI plus browser smoke tests using mocked APIs. Record that hosted CI is unexecuted locally.
- [x] Final: full unittest, all JS harnesses, real browser checks where possible, diff review, local checkpoint/final commits.

Success: no permanent disabled UI on missing batches; no generated Chinese in English previews; documented minimum matches code; completed history survives manager restart; interrupted history can be explicitly retried; startup and CI checks catch regressions. Existing routes, download formats, maximum concurrent work and protected output-file behavior stay intact.

## Verification and review — 2026-09-07

- Checkpoint: `9ea4ed0` saved the plan and initial regression tests before implementation.
- Installed `requirements.txt` and `requirements-dev.txt` into a clean temporary Python 3.14 environment; `pip check` found no broken requirements.
- Final full suite: 417 tests, OK, 2 existing platform skips. All four Node harnesses and syntax checks for all production JavaScript passed; modified Python modules compiled.
- Real Chromium: 3 tests passed, covering generated/source preview titles and selection across language switches, submission then reload without duplicate POST, history selection without download submission, missing-batch recovery, and a 375px history selector layout.
- Independent review found bulk retry returning HTML 500 when restored directory validation fails. Added a failing API test and structured 409 handling; verified green.
- A stalled JSON body exposed an incomplete timeout boundary. The helper now keeps AbortController active through JSON parsing; the regression confirms abort after headers as well as before headers.
- Backend tests cover completed result restoration, interrupted queued/running tasks with no automatic execution, manual retry, output-directory revalidation, redownload versions, retention pruning, write failure handling, and metadata filtering.
- Hosted macOS/Windows Python 3.10/3.13 CI is configured but has not run. Local tests used macOS Python 3.14 and mocked media APIs; live platform extraction/download speeds were not tested. Dependency pins cover direct dependencies, not a full transitive lock.
- Browser test server and Chromium are automatically closed. Local state remains Git-ignored. No push or deployment.
