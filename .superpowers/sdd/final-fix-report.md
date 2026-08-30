# LMU circuit guide final-fix report

## Review findings resolved

1. `/kozekilmu/tracks` now contains the same sticky topbar, scroll progress,
   mascot status, and `返回下载` link as the victory archive. It uses the
   existing shared motion runtime for the scrolled state.
2. Guide image fallback is server-rendered. Empty circuit/car image paths are
   valid optional metadata; configured paths render only when they resolve to a
   file below Flask's static root. Missing and empty paths render the existing
   accessible placeholder without inline JavaScript.

## Safety and performance

- The helper rejects absolute, backslash, and parent-directory paths before a
  filesystem lookup, then verifies the resolved candidate remains below the
  static root.
- Existing-file checks are cached by relative path. The route builds one small
  availability set from the 16 circuits and referenced cars, not one lookup per
  rendered recommendation.
- No download, extraction, conversion, queue, or API behavior changed.

## TDD and verification evidence

- New blank/missing circuit and car contracts failed before the implementation,
  then passed after it. The focused data/route run passed 10 tests.
- LMU, victory-page, and shared-motion regression run: 41 tests passed.
- Full suite: 366 tests passed; 2 existing Windows-only tests skipped.
- `venv/bin/python -m compileall -q app.py lmu_guide_data.py tests`,
  `node --check static/js/motion.js`, and `git diff --check` exited 0.
- A repository scan found no `onerror=` attributes under `templates/` or
  `static/`.
