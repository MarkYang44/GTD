# Architecture and safe refactoring

**English** · [简体中文](ARCHITECTURE.zh-CN.md) · [README](../README.md)

GTD keeps its Flask/Jinja and plain JavaScript interface. The Web interface and CLI use the same yt-dlp and FFmpeg download core; the boundaries below separate decisions from execution without adding a framework or runtime dependency.

| Boundary | Responsibility |
| --- | --- |
| `app.py` | Flask application factory, HTTP responses, and route coordination |
| `download_requests.py` | Validate a submission, select explicit preview entries, normalize direct links, and retain rejected input indexes |
| `web_runtime.py` | Own the per-application task manager, preview store, and upload store |
| `download_options.py` | Build yt-dlp options from immutable preferences and an explicit bundle of current helper functions |
| `bilibili_recovery.py` | Decide attempt order and admit backup hosts lazily after recoverable failures |
| `downloader.py` | Coordinate network I/O, cancellation, owned workspaces, subtitles, and final output processing |
| `task_models.py` | Describe task, attempt, progress, result, and batch data with Python 3.10-compatible static types |
| `task_control.py` / `task_history.py` | Schedule work and guard state transitions / persist allowlisted history fields |
| `static/js/task_api.js` | Share JSON request timeouts and capped exponential retry delays |

## Web application lifecycle

`create_app(config=None, *, manager=None, uploads=None)` creates a Flask application with its own routes and lifecycle metadata. Construction and `import app` do not open task history, construct task execution resources, or expire uploads. The first operation using a runtime resource initializes one instance under a per-application lock. `python app.py` explicitly initializes its runtime before starting the server, so saved tasks are restored at startup.

The default `app.app` WSGI object and existing Flask endpoint names remain available. Compatibility proxies (`task_manager`, `preview_store`, and `upload_store`) resolve the current Flask application during a request and the default application outside a context. Worker functions capture the originating application's upload store and do not depend on Flask request context.

For isolated tests or embedding:

```python
from app import create_app
from web_runtime import get_runtime

application = create_app({
    "TESTING": True,
    "GTD_HISTORY_PATH": "/tmp/gtd-example/tasks.sqlite3",
    "GTD_UPLOAD_ROOT": "/tmp/gtd-example/uploads",
})
runtime = get_runtime(application)
try:
    response = application.test_client().get("/api/batches")
    assert response.status_code == 200
finally:
    runtime.task_manager.shutdown()
```

The caller owns shutdown after initialization. Do not shut down the manager at the end of an individual HTTP request. An injected manager remains owned by its caller, including when runtime initialization fails. The path settings can be supplied through the factory configuration or environment; their defaults remain `state/tasks.sqlite3` and `state/audio_uploads/`.

Each initialized application owns a process-local queue. The standard single-app service retains three global worker slots, two Bilibili slots, and one Instagram slot. Multiple applications or server processes do not share a scheduler.

## Compatibility and ownership

- HTTP parsing retains validation order, structured errors, status codes, selected-entry order, and direct-link rejection indexes. The HTTP adapter handles serialization; the parser does not use Flask request state.
- `_build_ydl_options(...)` retains its existing signature. It captures current helper functions into `OptionsHooks` on every call, keeping existing testing and discovery seams. `DownloadPreferences` groups media, audio-format, and speed choices; the existing audio output profile remains authoritative for codec/container behavior.
- Bilibili recovery changes metadata and planning only. The downloader still checks cancellation, creates and cleans its attempt workspace, performs network operations, packages subtitles, and finalizes results. Recovery retains Turbo-to-Standard fallback, original-CDN fallback, backup order, and copy/identity behavior.
- Task types document contracts; they are not runtime validators or a database migration. The SQLite allowlists still exclude execution capabilities and private diagnostics. State mutation stays inside the existing locks and generation guards.
- Browser pages share transport and retry-delay calculation. Each page retains its own selection guards, polling stop/resume rules, rendering, and language handling. Uploads still use XHR for progress and cancellation. The JSON timeout covers body consumption; callers choose whether an HTTP error body needs parsing.

## Verification strategy

Start with focused regressions around the changed boundary, then run the full Python/JavaScript and browser suites listed in the README. Assert behavior at the caller above an extracted helper, rather than only asserting the helper's structure.

Key contracts include mixed-platform options, ordered CDN recovery, cancellation and workspace ownership, output collision handling, restart recovery, stale browser responses, and timeouts while reading response bodies. Media integration checks use generated local fixtures and real FFmpeg; source FLAC checks compare encoded-audio hashes as well as codec and metadata. Platform download tests simulate upstream responses, so passing them does not establish live connectivity or download speed.
