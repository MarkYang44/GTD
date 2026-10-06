# GTD Desktop Implementation Plan

> **For agentic workers:** Use subagent-driven-development for isolated packaging and review tasks; execute tightly coupled runtime changes inline. Track completion with checkboxes.

**Goal:** Ship a full-function macOS arm64 app and publish Windows x64 source/build entrypoints for user testing.
**Architecture:** PySide6/QtWebEngine window with original Flask routes, fixed localhost desktop origin, request token injected by Qt interceptor, bundled runtimes and separate writable data paths.
**Tech Stack:** Python 3.13, Flask, PySide6, PyInstaller, FFmpeg/ffprobe, aria2c, Node.

## Global Constraints

Preserve Web/CLI behavior, all LMU routes, manual-only calendar, persistent theme/language/favorites, task cancellation/history, format/subtitle/cover logic. No private state or cookies in artifacts. Windows test evidence stays distinct from macOS. Upload branch only; no public Release required. User approved design and GitHub upload on 2026-10-06.

### Task 1: Runtime resource/data paths
Files: gtd_paths.py; downloader.py; output_files.py; media_sources.py; download_logging.py; app.py; lmu_calendar.py; folder_picker.py; tests/test_desktop_paths.py.
Interface: resource_root()->Path; runtime_root()->Path; downloads_root()->Path; initialize_desktop(root:Path|None)->Path. Preserve source mode defaults unless desktop flag is enabled. Frozen root = sys._MEIPASS. Environment GTD_DATA_DIR overrides writable desktop root for isolated tests.
- [x] Write tests for source defaults, platform paths, no-overwrite calendar seeding and bundled tool PATH.
- [x] Run tests RED: `venv/bin/python -m unittest discover -s tests -p test_desktop_paths.py`.
- [x] Implement runtime/resource separation and minimal module path substitutions.
- [x] Run GREEN plus full existing regression.

### Task 2: Server/session lifecycle
Files: desktop_server.py; tests/test_desktop_server.py.
Interface: DesktopServer(app,token,port=18233) with start()->str, close(); guard accepts header X-GTD-Desktop-Token plus exact Host and same Origin for mutating methods. Bind 127.0.0.1 only; startup bind failure gives actionable duplicate-instance/port error. shutdown cancels running/waiting tasks then stops owned server.
- [x] Test rejected missing token, hostile Host/Origin, authorized original routes and clean shutdown in temporary storage.
- [x] Verify RED then implement and verify GREEN.

### Task 3: Desktop window and full UI
Files: desktop.py; desktop_window.py; static/css/desktop.css; desktop_settings.py; tests/test_desktop_settings.py.
Window uses persistent QWebEngineProfile, localhost-only navigation, external links QDesktopServices, interceptor supplies session token only to local server; downloadRequested prompts save and accepts real transfer. QFileDialog marshaled via queued signals handles folders from Flask thread. Native settings imports bounded Cookie files, validated calendar JSON, selected SQLite history after checking format; favorites imported/exported via bounded JSON and localStorage. All navigation has bilingual labels, state mirrored from webpage language/theme. Active-task close confirmation requests cancellation before shutdown. CLI executable is separate main.py build, preserving argv and console input.
- [x] Define failing tests for safe Cookie/calendar/history import and preferences validation.
- [x] Implement real window/navigation/settings and verify all original routes remain reachable.
- [x] Apply desktop-only CSS after response rendering, preserving Web style unchanged.

### Task 4: Build and Windows upload
Files: scripts/build_desktop.py; scripts/prepare_desktop_tools.py; requirements-desktop.txt; requirements-build.txt; desktop.spec; Desktop.cmd; Build Desktop.cmd; .github/workflows/desktop.yml; docs/DESKTOP.md; tests/test_desktop_build.py.
Interface: tool directory tools/desktop-bin with bin/ and notices/; build script accepts --tools-dir, packages only explicit public resource allowlist; macOS app ZIP and Windows onedir ZIP with console CLI companion. PyInstaller must collect dynamic yt-dlp extractor/EJS/curl_cffi data. macOS tools dependencies copied and rewritten with relocatable install names; Windows source commands provision fixed dependencies and build artifacts locally. SHA256 generated; workflow builds Windows artifacts on push to codex/gtd-desktop and workflow_dispatch.
- [x] Independent agent implements build/resource audit/tools preparation, writes failure-first resource tests.
- [x] Review all allowed resources and executable architecture/licensing dependencies.
- [x] Build macOS app, relocate output and run smoke with system-tool PATH removed.

### Task 5: Verification and handoff
- [x] Run full unit/JS and relevant browser suites, real short media extraction and protected-server routes.
- [x] Native app startup, route changes, persistence, settings, result saving and frozen self-test; save screenshot.
- [x] Document Windows user validation checklist and factual limitations (no Windows native UI claim).
- [x] Review implementation, fix material findings; commit and push codex/gtd-desktop; verify remote commit.
