# Task 4 Report: Kozeki Ui Hidden-Page Motion

## Commit

`560ad15d2208b387122f5da75b3d5de53982266e` — `feat: apply shared motion to hidden page`

## Delivered

- Loaded the shared motion stylesheet after the hidden page's inline styles and the deferred shared runtime before `</body>`.
- Added staged reveals for the hero, race data, video heading/card, gallery heading, and gallery shots.
- Applied the six approved motion surfaces: the main video card and five gallery shots.
- Added low-strength parallax to the hero stamp and new video/gallery media wrappers, keeping existing image hover transforms on the images themselves.
- Removed the full inline pointer/scroll runtime and its page-specific pointer light; the shared runtime now owns progress, topbar state, pointer surfaces, lifecycle, and scheduling.
- Preserved clipping, dimensions, gallery lazy loading, captions, the Bilibili link and play affordance, and the responsive grid. Reduced-motion rules do not hide media or the play affordance.

## TDD and Verification

- RED: the added hidden-page/shared-delivery tests failed because `/kozekilmu` did not yet include the shared CSS or JavaScript.
- GREEN: `node --check static/js/motion.js` completed successfully.
- GREEN: `../../venv/bin/python -m unittest tests.test_kozekilmu tests.test_motion_system tests.test_web_guide -q` completed with `Ran 22 tests` and `OK`.
- Structural verification confirmed exactly six `data-motion-surface` markers, wrapper-only image parallax, no hidden-page scheduling IIFE, and retained lazy-loading markers.

## Environment Note

The linked worktree has no local `venv/bin/python`; verification used the project's existing root virtual environment. No service configuration or port `8233` files were changed.
