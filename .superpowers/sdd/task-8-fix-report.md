# Task 8 Review-Fix Report

## Scope

Resolved the second final-review findings without extending public download behavior:

- CLI now prepares the output directory once and passes the private capability through `download_tasks()` and `print_summary()` without printing or serializing that capability.
- `task_control` now depends on `output_files` for prepared-directory validation. Web wiring injects the downloader-specific preparer; ordinary custom runners still receive an exact `str` path.
- Restoring a visible active tab immediately calls `pollStatus()` only when no poll is in flight. Hidden polling remains scheduled at three seconds.
- Public task snapshots skip discarded attempts before `deepcopy`, while retaining the full internal history and public `attempt_count`.

## TDD Evidence

The following new regression tests were written before their implementation and initially failed on the review baseline:

- `test_command_line_download_flow_validates_directory_once`: observed three `.__mvd_write_test_` probes; expected one.
- `test_custom_task_manager_never_imports_downloader`: a fresh process showed `downloader` in `sys.modules` after a normal custom batch.
- `test_public_task_does_not_deepcopy_discarded_attempt_history`: a non-deepcopyable sentinel in an old attempt raised from `_public_task`.
- `test_frontend_immediately_polls_when_an_active_page_becomes_visible`: the visibility handler lacked the active visible `pollStatus()` path.

After implementation, the four-test command passed:

```bash
../../venv/bin/python -m unittest \
  tests.test_cli_audio.CliAudioModeTests.test_command_line_download_flow_validates_directory_once \
  tests.test_task_control.TaskManagerTests.test_custom_task_manager_never_imports_downloader \
  tests.test_task_control.TaskManagerTests.test_public_task_does_not_deepcopy_discarded_attempt_history \
  tests.test_web_progress.WebProgressStateTests.test_frontend_immediately_polls_when_an_active_page_becomes_visible -v
```

## Focused Regression

```bash
../../venv/bin/python -m unittest \
  tests.test_cli_audio tests.test_task_control tests.test_web_progress \
  tests.test_download_locations tests.test_parallel_downloads -v
```

Result: 137 passed, 2 pre-existing Windows-only tests skipped.

## Full Verification

```bash
../../venv/bin/python -m unittest discover -s tests -v
../../venv/bin/python -m compileall -q *.py tests
node --check static/js/index.js
git diff --check
```

Results: full discovery ran 302 tests successfully with the two existing Windows-only skips; Python compilation, JavaScript syntax checking, and diff whitespace checking all exited 0. The linked worktree uses the parent checkout's `venv` at `../../venv/bin/python`.
