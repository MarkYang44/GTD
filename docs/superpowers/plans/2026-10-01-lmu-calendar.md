# LMU calendar implementation plan

**Goal:** Implement the approved manually maintained weekly calendar.
**Architecture:** Validated local JSON → Flask context → inherited Jinja page; native JS adds shared fuel estimates and an offline hint; Python renders UK times. CLI owns publication and backup files.
**Tech stack:** Python 3.10+, Flask/Jinja, vanilla JavaScript/CSS, unittest/Node/Playwright.

- [x] Data contract: add `tests/test_lmu_calendar.py` covering aware timestamps/DST, nullable published fields, class/car eligibility, negative/nonfinite numeric values and safe source URLs. Verify RED then implement `lmu_calendar.py`, TypedDict definitions and `data/lmu/calendar/schema.json`.
- [x] Manual publication: tests for invalid import preserving bytes, week archive immutability, repeated import, fallback and locking. Implement `scripts/update_lmu_calendar.py` and atomic repository helpers. Empty `current.json` is intentional.
- [x] Rendering: test calendar route, nav, server-rendered UK times and escaped content. Implement inherited template, isolated CSS and JS; expose existing calculator to browser without changing its rules.
- [x] Browser QA: isolated fixture directory, desktop/tablet/mobile, language/theme persistence, partial/stale/offline, calculations, no-JS. Run focused tests then full unit/browser regression, Node syntax and content snapshot checks.
- [x] Documentation: bilingual READMEs/guides and maintenance instructions with complete example and CLI usage. Review scope/security/data semantics before delivery; leave changes uncommitted.
