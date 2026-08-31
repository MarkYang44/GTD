# LMU polish final fix report

## Scope

Fixed every finding in `.superpowers/sdd/lmu-polish-whole-branch-review-result.md` with no downloader, API, route, shared-motion, dependency, or unrelated-page changes.

- The existing external language runtime now executes parser-blocking in `<head>` and restores guarded stored language on the root (`data-guide-language`, `lang`) and document title before guide content is parsed.
- `DOMContentLoaded` still owns translated `alt`/`aria-label` values, checkbox synchronization, and the single change listener. The runtime does not touch scroll position or `<details>`, preserving their native state.
- Server-rendered metadata is audited directly for every `data-title-en`, `data-i18n-alt-en`, and `data-i18n-aria-label-en`: all values must be non-empty and Han-free.
- The test parser treats `param` as an HTML void element.
- The Chinese toggle label alone has `lang="zh-CN"`; English-mode `ZH` inherits root `lang="en"`.

## TDD evidence

RED was recorded before implementation:

1. `node tests/js/lmu_guide_language_harness.js` failed at the new loading-document assertion because the baseline left `root.dataset.guideLanguage` undefined instead of restoring stored `en` before `DOMContentLoaded`.
2. After adding the direct parser regression and temporarily omitting `param`, `/Users/markyang/Projects/GTD/venv/bin/python -m unittest tests.test_lmu_guide.LmuGuideParserTests.test_english_copy_parser_treats_param_as_void` failed with `[("param", {})] != []`.

GREEN implementation separated root/title bootstrap from DOM-bound attribute and control work, then restored `param` to the void-element set.

## Covered tests

- `tests/js/lmu_guide_language_harness.js`: stored English is applied to root language and title while `readyState == "loading"`; translated DOM attributes and toggle state are applied after `DOMContentLoaded`; persistence and listener de-duplication remain covered.
- `tests/test_lmu_guide_language.py`: the rendered Flask page loads the non-deferred external bootstrap before `<body>`, retains deferred motion, and has no inline event handlers.
- `tests/test_lmu_guide.py`: rendered Flask metadata audit, `param` void-element behavior, bilingual toggle language declaration, existing English-visible-copy and route contracts.

## Final verification

Executed in `/Users/markyang/Projects/GTD/.worktrees/lmu-guide-language-toggle`:

```text
/Users/markyang/Projects/GTD/venv/bin/python -m unittest tests.test_lmu_guide tests.test_lmu_guide_language
.......................................
Ran 39 tests in 0.203s
OK

node tests/js/lmu_guide_language_harness.js
exit 0

node --check static/js/lmu_guide_language.js
exit 0

git diff --check
exit 0
```

No concerns.
