# Global language delivery status

Implementation complete. User approved the design and subsequently authorized local commits to protect progress from usage interruptions. Initial checkpoint: `8cfed67`. Do not push without a request.

Delivered: shared toggle and language runtime on all four pages; old preference compatibility, persistence, cross-tab updates and back/forward cache restoration; static and dynamic homepage localization; full English guide and archive; reciprocal Chinese/English README links and complete English documentation.

Verified:

- `venv/bin/python -m unittest discover -s tests`: 397 tests, OK, 2 existing Windows-only skips.
- Node syntax checks and global, download, existing LMU, and guide TOC language harnesses passed.
- English static text and translated accessibility attributes checked on all four rendered routes.
- Dynamic harness covers completed/running/queued/failed/cancelled tasks, postprocessing, unknown error fallback, input and pending-control preservation, selection retention, and no extra requests on language changes.
- README: 34 fenced blocks in each edition; executable commands and source URLs match; heading counts match at each level.
- Safari: four-page language switching, cross-page preference, refresh, input preservation, guide TOC anchors, and desktop screenshots inspected.
- Chrome iPhone SE emulation (375 x 667): all four page headers and English layouts inspected. No actual device test or external media download was performed.
- `git diff --check` passed.

Temporary verification used 127.0.0.1:8234. Its test tabs were closed. On 2026-09-07 the remaining temporary process was verified by command and working directory, then stopped. No service was listening on 8233 at final verification; run `venv/bin/python app.py` to view the updated site.

Final recheck on 2026-09-07: the full 397-test suite passed (2 Windows-only skips), all four JavaScript language harnesses and syntax checks passed, and the working tree was clean before this verification-record update. Feature implementation is saved in local commit `c318c64`; no changes were pushed.
