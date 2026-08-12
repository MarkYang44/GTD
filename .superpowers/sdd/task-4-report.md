# Task 4 Report: Extract Homepage CSS and JavaScript

## RED

- Added an asset-boundary regression test before moving code. It requires external CSS and deferred JS assets, rejects inline style/script blocks, and verifies every inline event handler is exported with `Object.assign(window, ...)`.
- The requested `venv/bin/python` is absent in this linked worktree. The shared project interpreter is `../../venv/bin/python`.
- RED with that interpreter: the new stylesheet assertion failed because `static/css/index.css` did not exist. Existing JavaScript-source checks also reported the expected missing `static/js/index.js` file.

## GREEN

- Moved the homepage stylesheet to `static/css/index.css` without changing its rules.
- Moved the homepage script to `static/js/index.js`, loaded with `defer`, and explicitly exported all handlers used by static or rendered inline event attributes.
- The script had no Jinja-only values, so no data attribute bridge was required.
- Updated frontend test helpers to aggregate template, CSS, and JavaScript sources. Two other web-surface tests now read the relevant static asset instead of assuming CSS and JavaScript remain embedded in the HTTP response.

## Verification

- `node --check static/js/index.js`
- `../../venv/bin/python -m unittest tests.test_web_progress tests.test_bilibili_support -q` — 93 tests passed.
- `../../venv/bin/python -m unittest discover -s tests -q` — 264 tests passed, 2 Windows-only tests skipped.
- `../../venv/bin/python -m compileall -q app.py downloader.py main.py tests`
- `git diff --check`
- Compared the extracted stylesheet against the original template byte-for-byte; compared the script after removing only the required `Object.assign(window, ...)` block.

## Self-review

- No service was started or modified, and no download content was touched.
- Serial visibility-aware polling, task render signatures, requests, and adaptive/turbo behavior were mechanically preserved.
- The template contains only external asset tags for the former large CSS and JavaScript blocks.

## Review Follow-up

- Added a Flask-client delivery test that parses the rendered homepage, requires exactly `/static/css/index.css` and `/static/js/index.js`, then fetches both URLs and verifies HTTP 200 with `text/css` and `text/javascript` MIME types.
- Strengthened the inline-handler test to scan both the template and `static/js/index.js` generated HTML. It now checks the dynamic `updateCollectionSelection` and `operateTask` handlers and compares the full handler union against the parsed `Object.assign(window, {...})` export set.
- This was a characterization-test follow-up: the correct production behavior already existed, so the tests passed without a production change.
- Follow-up verification: focused Web/Bilibili suite passed 94 tests; full discovery passed 265 tests with 2 Windows-only skips; Node syntax, compileall, and diff checks passed.
