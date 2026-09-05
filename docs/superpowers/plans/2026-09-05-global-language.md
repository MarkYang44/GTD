# Global language implementation plan

Goal: apply the approved bilingual design to all four pages and both README editions.
Architecture: extend the existing early language bootstrap with shared preferences, translation helpers and language-change events; extract the toggle and CSS. Page translations consume this shared runtime.
Tech stack: Flask/Jinja, plain JavaScript, Markdown, unittest and Node.

Constraints: keep existing routes, branding, input/task state and navigation order; no commits.

- [ ] Shared runtime and homepage: add tests for all-page bootstrap, old preference migration, cross-tab events, attributes and placeholders. Run `venv/bin/python -m unittest tests.test_global_language` and Node harness to confirm failure. Extend `static/js/lmu_guide_language.js`, extract `templates/_language_toggle.html` and `static/css/language.css`, translate `templates/index.html`, connect tracks. Run the same tests to green.
- [ ] Dynamic homepage: localize `static/js/index.js` using `GtdLanguage.t(zh, en, params)` and a `gtd:languagechange` listener. Preserve preview selection, asynchronous operation state and completed batch data. Use a Node harness to verify rerendering without new requests and source-value preservation.
- [ ] Guide and archive: translate `templates/guide.html`, `templates/kozekilmu.html`, add `docs/WEB_GUIDE.en.md`, and pass rendered English guide through `app.py`. Test translated content and language-aware TOC.
- [ ] README: create complete `README.en.md`, add reciprocal language links and language-switch documentation to both editions. Compare section and command coverage.
- [ ] Integration: run all unittest tests, JS harnesses, syntax checks and `git diff --check`. Inspect four pages in a temporary local instance, desktop/mobile, both languages, persistence and simulated task/preview state. Resolve failures, record actual results and leave all changes uncommitted.
