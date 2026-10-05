# LMU 每周赛历 / Weekly calendar maintenance

页面：`/kozekilmu/calendar`。使用 Flask/Jinja 与原生 JS，继承 LMU 导航、双语和主题。没有自动抓取、定时更新、GitHub 更新 workflow 或账号 Secret。服务器每次请求都读取有效本地 JSON，成功导入后刷新页面即可，无须重启。

## 手动维护 / Manual publication

1. 人工核对 LMU、RaceControl 或 Studio 397 官方赛历；填写一份 JSON。查看 `docs/examples/lmu-calendar.example.json` 的完整结构。它是**测试示例，不是实际赛历**，请先替换日期、赛事和假设，并填写实际来源。
2. 仅校验（失败也不修改任何文件）：
   ```bash
   venv/bin/python scripts/update_lmu_calendar.py /absolute/path/to/candidate.json --check
   ```
3. 确认后发布：
   ```bash
   venv/bin/python scripts/update_lmu_calendar.py /absolute/path/to/candidate.json
   ```
4. 控制台会列出未发布的字段。补齐并重导入即可；不需要修改模板。不要为新一周沿用旧天气、旧规则、旧 BoP 证据来填补缺项。

Use official LMU/RaceControl/Studio 397 information, prepare a local JSON, validate with `--check`, then import without that flag. The example is synthetic; replace it before publication. Refresh the page after a successful import. No network requests, schedules or secrets are required.

## 文件 / Storage

- `data/lmu/calendar/current.json`: current valid calendar; shipped unpublished and empty.
- `schema.json`: JSON Schema draft 2020-12, for editors and independent tools.
- `previous.json`: valid backup; initial publication also creates a backup.
- `archive/YYYY-MM-DD.json`: last published data from the previous week, keyed by its weekStart. Created on a successful week transition, never overwritten with differing data. Same-week edits use the backup without creating another week archive.
- `status.json`: last manual import failure indicator; successful publication clears it.
- `.update.lock`: writer lock directory, removed on normal exit. If an updater crashed, first confirm no updater is running, then remove this empty lock directory before retrying.

Validation failure never overwrites the last valid current file. The reader tries current, previous, then archives. Missing data shows an empty state; expired data remains visible with a historical warning. Corrupt current can be repaired by importing the same valid backup. A 4 MiB bound applies to both input and published UTF-8 JSON. Updates serialize under a writer lock and use same-directory atomic replacement. `--check` does not publish or record failure status.

`--directory /path/to/calendar` changes the CLI destination. Optional `GTD_LMU_CALENDAR_DIR` points the Flask reader to the same alternative folder (primarily for tests). Neither is needed for normal use. Imported data belongs in the calendar directory, not the downloader’s ignored `downloads/` or the existing LMU guide release index.

## Schema / 数据约定

All keys shown in the example are required. Unknown scalar or bilingual text values use `null`; unknown collections use `[]`/`{}`. Never store `TBA` in numeric/date fields. Unknown layout can mean unpublished or inapplicable; use the event source to clarify rather than fabricate a layout.

- `schemaVersion`: 1. `timezone`: exactly `Europe/London`.
- `weekStart`, `weekEnd`: YYYY-MM-DD, inclusive seven-day range (end = start + six days); represent the actual rotation week, not necessarily Monday–Sunday. Unpublished initial state uses both null, null lastUpdated and no events.
- `lastUpdated`: ISO timestamp with seconds and explicit UTC offset (`Z` is allowed); actual manual review/publication time. Per-game build is `gameVersion`, null if unverified. Updating the calendar does not validate existing driving recommendations against that build.
- `events`: up to 100 unique event slugs. `name`/`track` are official names; `trackId` can link conceptually to a catalog slug; `layout` is nullable. `eventType`: Daily / Weekly / Special / Championship.
- `sessions`: up to 2000 ISO timestamps per event, each with offset and seconds. All UK dates must belong to this week. Duplicate instants are rejected. The view sorts by actual instants, not timestamp spelling. `[]` means schedule not published.
- `durationMinutes`: positive numeric minutes or null. `classes`: nonempty unique names; additional classes such as LMP2/LMP3 can be displayed even without catalog-car recommendations.
- `eventLevel`: official event tier. `eligibility.minimumSR`, `badge`, `subscription`: actual separate eligibility requirements, nullable.
- `weather`, `trackConditions`: bilingual `{ "zh": "...", "en": "..." }` or null. Keep English copy in English.
- `sources`: HTTPS links to LMU/RaceControl/Studio 397 domains. Event sources, recommendation evidence and strategy sources are separate; a homepage does not substantiate a specific race or pace ranking. Blank sources are explicitly reported, not invented.

`lmu_calendar.validate_calendar` validates the shape and cross-field rules beyond JSON Schema: finite numeric inputs, true unique session instants, date bounds, unique ranks/car IDs, class membership, published eligible-car lists, duration consistency and safe official links. Python TypedDicts describe Calendar/Event/Eligibility/RecommendedCar/Evidence/Strategy/StrategyInputs/Copy; runtime validation is mandatory for external JSON.

## 车型 / Recommendations

`recommendedCars` maps class name to **0–3** recommendations. Each uses an existing `carId` from `lmu_guide_data.CARS`, unique rank 1–3, bilingual summary, optional drivingCharacteristics and driverType, and an evidence object. The UI reuses the catalog’s strengths/weaknesses and clearly labels suggestions as editorial, not BoP pace rankings. Populate evidence.trackCharacteristics/gameVersion/bop/recentPerformance/sources only when actually supported. Empty evidence is displayed as Not Published.

`allowedCars` maps each known class to official eligible car IDs. Omit an unknown class list; recommendations/strategies then do not claim verified car eligibility. A published list must contain at least one unique ID; catalog cars must match its class. A recommendation or strategy outside that published list is rejected. Unsupported catalog classes remain readable without made-up cars. Changing existing catalog car strengths is a guide-content edit and follows `LMU_CONTENT_MAINTENANCE.md`; changing weekly recommendation order/summary is just a calendar JSON edit.

## 策略 / Estimates

`strategy` contains per-car estimates. Every entry requires all seven explicit numeric inputs and bilingual `calculationNotes`; the browser never fills missing inputs with defaults:

| Input | Unit | Valid range |
|---|---|---|
| minutes | race minutes | 1–1440 |
| lap | average seconds/lap | 10–1800 |
| fuel | liters/lap | 0.01–100 |
| tank | liters | 0.1–1000 |
| formation | total formation liters | 0–1000 |
| rate | liters/second | 0.01–100 |
| loss | fixed pit seconds, excluding refueling | 0–3600 |

When official duration is known, input minutes must match it. Unknown duration can still use an explicitly displayed estimate duration with its assumptions. Starting fuel, total fuel, reserve and refueling stops are calculated using the existing `lmu_strategy.js` rules: ceil(duration/lap) + one extra lap, 5%/10% reserve with at least one lap fuel, formation fuel once, totals rounded upward to 0.1 L. The plan spreads reserve across laps, does not subtract pit time from planned laps, and is not an optimum-time solution.

All computed results are Estimated. Pit plan displays the completed-lap boundary, exit target and estimated addition. **Actual addition = exit target − dashboard fuel, minimum zero**. Totals include all stops, details display the first 20. The separately reviewed `pitWindow` is a published rule or editorial window, not a calculated optimal window. Official `pitStopRequirement` is distinct from estimated refueling stops. Tires, weather, repairs, driver limits, concurrent services and mandatory stops are not simulated. `tireStrategy`, `tireChangeRecommendation`, `trafficManagement`, `fasterClassAdvice`, `slowerClassAdvice`, `overtakingAdvice`, `beingLappedAdvice` are separately reviewed bilingual advice or null. Explain assumptions and data provenance in calculationNotes; do not present generic defaults as measured car data.

## 时区与页面状态 / Timezone and states

Python `ZoneInfo('Europe/London')` converts explicit-offset instants, preserving GMT/BST and distinguishing repeated autumn hours. Windows installs `tzdata` from requirements. There is no hard-coded UK UTC offset. Do not enter naive local times: resolve nonexistent/repeated local times to a documented offset before import. No automated Tuesday execution exists; publication is only when the command is run.

Server-rendered events and UK times remain readable without JavaScript. Fuel estimates require JavaScript, with explicit input/notes fallback. Because the page is server-rendered, there is no artificial AJAX loading state. Missing fields, empty data, failed import, corrupt-current backup, stale week and browser offline states are separate. Source/API unavailability cannot block local rendering; the updater never calls a source API. Browser offline detection is only a hint, not proof that any specific source is down.

## Tests / 验证

```bash
venv/bin/python -m unittest tests.test_lmu_calendar
node tests/js/lmu_strategy_harness.js
node --check static/js/lmu_calendar.js
venv/bin/python scripts/update_lmu_calendar.py docs/examples/lmu-calendar.example.json --check
venv/bin/python -m unittest discover -s tests -p 'test_*.py'
venv/bin/python -m pip install -r requirements-dev.txt
venv/bin/python -m playwright install chromium
venv/bin/python -m unittest discover -s tests/browser -p 'test_*.py'
git diff --check
```

Tests use temporary storage and explicitly synthetic races; they never publish fixtures into current.json. Existing Python/JS/browser checks replace an npm lint/typecheck/build pipeline, which this project does not have. No new TypeScript toolchain is introduced.
