# GTD reliability implementation plan

User-approved scope: audit sequence 1 → 2 → 3 → 4 → 6. Local commits authorized; no push.

Architecture: retain Flask and plain JS. Add bounded/recoverable polling, structured generated-title metadata, Python startup validation, optional SQLite TaskHistoryStore integrated into TaskManager, a recent-batch selector and browser-local current batch reference. Restarted active work becomes retryable INTERRUPTED, never silently restarts. SQLite state is local and Git-ignored. No byte-level download resume promise.

- [ ] Polling: Node tests for 404 releasing controls, network errors retaining batch with backoff, timeout abort and successful recovery. Implement in static/js/index.js.
- [ ] Preview localization: tests and collection_resolver.py metadata distinguish generated and source titles; frontend derives local strings only for generated values.
- [ ] Compatibility: runtime_requirements.py rejects Python <3.10 before imports; update both entrypoints and both README editions.
- [ ] Backend history: task_history.py SQLite storage, TaskManager optional store/list/restore, temporary-database tests for completed and interrupted work, pruning and retry. app.py adds GET /api/batches and configured local state path.
- [ ] Browser recovery: save current batch id safely, restore polling on load, add bilingual recent-history selector and refresh button; preserve existing inputs and controls. No automatic downloads upon selecting history.
- [ ] Reproducibility: immutable tested dependency baseline and explicit opt-in updates, macOS/Windows CI plus browser smoke tests using mocked APIs. Record that hosted CI is unexecuted locally.
- [ ] Final: full unittest, all JS harnesses, real browser checks where possible, diff review, local checkpoint/final commits.

Success: no permanent disabled UI on missing batches; no generated Chinese in English previews; documented minimum matches code; completed history survives manager restart; interrupted history can be explicitly retried; startup and CI checks catch regressions. Existing routes, download formats, maximum concurrent work and protected output-file behavior stay intact.
