# Task 4 Report: Kozeki Ui Hidden-Page Motion

## Result

The hidden page now uses the shared motion system for staged reveals, scroll depth, and six approved pointer surfaces: one video card and five gallery shots. The page contains no private pointer, animation-frame, intersection, or scroll runtime.

The review fix adds an explicit `data-motion-sheen` child to each media surface. The shared runtime uses that opt-in layer without changing the background-based sheen used by ordinary homepage surfaces. Each sheen is non-interactive, sits below the video overlay and shot captions, and becomes static on leave, destroy, fail-open, reduced motion, or non-fine pointers.

The video and gallery media wrappers have 14px overscan on every edge. Their parallax transform remains separate from the images' hover transform, while the original clipping, desktop and mobile aspect ratios, image dimensions, five lazy gallery images, captions, play affordance, Bilibili link, and responsive grid remain intact.

## TDD Evidence

- RED: the tightened hidden-page and shared-runtime tests failed on the missing sheen children, missing 14px overscan, and missing layered-sheen opt-in path.
- GREEN: 18 focused hidden-page/shared-motion tests pass.
- The layered-sheen runtime test verifies pointer activation and leave/destroy cleanup while confirming ordinary surfaces still receive and restore their background-gradient fallback.
- Structural tests require exactly six approved surfaces, stable media order, the seven approved parallax targets, exactly five lazy gallery images, no duplicate runtime tokens, and preserved link/caption/play/responsive and reduced-motion contracts.

## Verification

- `node --check static/js/motion.js`: passed.
- Full Python suite: 321 tests passed, 2 skipped.
- `git diff --check`: passed.

The linked worktree uses the repository root virtual environment because it does not contain its own `venv`. Port `8233` and service configuration were not changed. The exact fix commit is recorded in Git history to avoid embedding a stale commit identifier in this report.
