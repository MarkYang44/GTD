# Advanced LMU Strategy Implementation Plan

Goal: Extend the existing browser-local calculator with two fuel plans and capacity-aware refueling.
Architecture: Keep pure arithmetic in static/js/lmu_strategy.js and reuse the Jinja shell, language/theme runtime and CSS. No new dependencies or game-specific claims.
Approved scope: User selected the strategy extension proposed in conversation. Implement inline and commit locally after verification.

## Rules
- Preserve ceil(duration/lap)+1 planned laps; do not subtract pit loss from fuel planning.
- Inputs: existing minutes/lap/fuel; tank (default 100 L, range 0.1–1000), formation fuel (3 L, 0–1000), refueling rate (2 L/s, 0.01–100), fixed pit loss (25 s, 0–3600). All defaults are generic, not verified car specifications.
- Regular reserve=max(base*5%, one lap); conservative=max(base*10%, one lap). Total ceil((base+reserve+formation)*10)/10.
- Distribute race fuel plus reserve/rounding evenly over planned laps for stint planning. Start with min(tank,total); debit formation once. Pit before a lap whose budget cannot fit in remaining fuel; refill min(tank-remaining, outstanding budget-remaining). No finish-line fuel-only stop. Mark infeasible if formation+one budgeted lap exceeds capacity.
- Pit loss per stop=fixed loss+added fuel/rate. Fixed loss excludes refueling; no tire/service overlap, mandatory stops, driver limits or weather simulation. Display at most first 20 stops with truncation note, but totals include all stops.
- Summary remains conservative; side-by-side regular/conservative cards include budgets, start fuel, stop counts, losses, expandable schedules. Advanced fields native collapsed details. Invalid advanced input opens details before focusing on submit.

## Tasks
- [x] Extend tests/js/lmu_strategy_harness.js: changed defaults, exact capacity, one/many stops, zero formation/loss, infeasibility, rounding, fuel conservation and capacity invariants. Run node harness red, implement pure calculator, rerun green.
- [x] Extend templates/kozekilmu_strategy.html and static/js/lmu_strategy.js rendering; add scoped styles in static/css/lmu_tools.css. Preserve language switching, local-only operation and reduced-motion preferences.
- [x] Extend tests/browser/test_lmu_extensions.py for new outputs, advanced validation, keyboard/reset, bilingual/theme/mobile behavior; update README.md, README.en.md, docs/WEB_GUIDE.md and docs/WEB_GUIDE.en.md.
- [x] Run venv/bin/python -m unittest discover -s tests -p 'test_*.py'; run browser extensions; inspect desktop/mobile screenshots; git diff --check; commit scoped changes locally.

## Verification and review
- 2026-09-09: 437 unit/Node tests passed, 2 platform skips; 3 focused real Chromium tests passed. Desktop/mobile light-theme screenshots inspected, dark-to-light and English-to-Chinese interactions covered. git diff --check clean.
- Reviewer identified that fuel additions based on contingency consumption must not be treated as nominal consumption instructions. Added planning fuel per lap and exit fuel targets, with actual addition=max(0,target-current onboard fuel). Added nominal-consumption replay regression for 60 min / 30 L tank. Reviewer approved after rerun.
- Browser tests run using /tmp/gtd-reliability-venv/bin/python and PLAYWRIGHT_BROWSERS_PATH=/tmp/gtd-playwright; the project venv lacks Playwright. Temporary test servers/browser contexts clean themselves up; existing app service unchanged.
