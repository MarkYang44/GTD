# LMU V1.4.2 Tracks, Cars, and Sleeper Picks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update GTD's LMU guide to the V1.4.2 content baseline with 18 circuits, the complete 24-car Hypercar/LMGT3 catalog, and one independently rendered Sleeper Pick per class per circuit.

**Architecture:** Extend the immutable `Circuit` model with first-class Sleeper fields while leaving each ordinary recommendation tuple at exactly three entries. Reuse existing rendering, filtering, comparison, review, and snapshot systems, but give Sleeper entries unique DOM and snapshot identities so an allowed overlap with the ordinary top three cannot overwrite data. Keep release facts separate from editorial driving recommendations and exact-version validation.

**Tech Stack:** Python 3 dataclasses, Flask/Jinja, vanilla JavaScript, CSS, unittest, Node harnesses, Playwright, FFmpeg/WebP, JSON content snapshots.

## Global Constraints

- Preserve `/kozekilmu/tracks`, `/kozekilmu/cars`, navigation order, favorites, comparison, bilingual switching, dark/light themes, reduced motion, and no-JavaScript readability.
- Preserve the Petronas-green visual language; Sleeper styling uses a badge and border, not a new palette.
- Keep three ordinary recommendations per class and add exactly one separate Sleeper Pick per class per circuit.
- Sleeper overlap with the same class's ordinary top three is valid.
- Do not claim fastest laps, optimal setup, or V1.4.2 driving validation without exact-version evidence.
- Do not change LMP2, LMP3, GTE, downloader, strategy, account, route, or persistence behavior.
- Do not overwrite existing snapshots; publish `2026.09.22.1` through the existing script.
- Do not commit or expose cookies, credentials, logs, download media, or temporary source files.

---

### Task 1: Complete the 24-car Hypercar and LMGT3 catalog

**Files:**
- Modify: `tests/test_lmu_guide.py:78-220`
- Modify: `tests/test_lmu_content.py:15-35`
- Modify: `lmu_guide_data.py:6-117`
- Modify: `lmu_practice_data.py:32-75`
- Modify: `scripts/sync_lmu_guide_assets.py:24-35`
- Create: `static/kozekilmu/guide/cars/aston-martin-valkyrie.webp`
- Create: `static/kozekilmu/guide/cars/genesis-gmr-001.webp`
- Create: `static/kozekilmu/guide/cars/glickenhaus-scg-007.webp`
- Create: `static/kozekilmu/guide/cars/isotta-fraschini-tipo-6.webp`
- Create: `static/kozekilmu/guide/cars/lamborghini-sc63.webp`
- Create: `static/kozekilmu/guide/cars/peugeot-9x8.webp`
- Create: `static/kozekilmu/guide/cars/vanwall-vandervell-680.webp`
- Create: `static/kozekilmu/guide/cars/mercedes-amg-lmgt3.webp`

**Interfaces:**
- Produces: `CARS: dict[str, Car]` with 14 `Hypercar` and 10 `LMGT3` entries; `CAR_NOTES` with identical keys; `_asset_sources()` covering every catalog car.
- Consumes: existing `_car(...) -> Car` and official source/image URL conventions.

- [ ] **Step 1: Write failing catalog and asset-coverage tests**

Add assertions equivalent to:

```python
EXPECTED_NEW_CARS = {
    "aston-martin-valkyrie", "genesis-gmr-001", "glickenhaus-scg-007",
    "isotta-fraschini-tipo-6", "lamborghini-sc63", "peugeot-9x8",
    "vanwall-vandervell-680", "mercedes-amg-lmgt3",
}

def test_v142_hypercar_and_lmgt3_catalog_is_complete(self):
    self.assertEqual(len(guide.CARS), 24)
    self.assertEqual(sum(car.car_class == "Hypercar" for car in guide.CARS.values()), 14)
    self.assertEqual(sum(car.car_class == "LMGT3" for car in guide.CARS.values()), 10)
    self.assertTrue(EXPECTED_NEW_CARS <= guide.CARS.keys())

def test_asset_sync_includes_every_catalog_car(self):
    sources = dict(asset_sync._asset_sources())
    for car in guide.CARS.values():
        self.assertEqual(sources[car.image], car.image_source_url)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_lmu_guide.LmuGuideDataTests tests.test_lmu_content.ContentTests`

Expected: FAIL because the eight cars and their notes/assets are absent and `_asset_sources()` only includes recommended cars.

- [ ] **Step 3: Add the eight cars with exact source images and bounded handling copy**

Use these slugs and official source images:

```python
NEW_CAR_IMAGES = {
    "aston-martin-valkyrie": "https://lemansultimate.com/wp-content/uploads/2025/06/1920x1080Valk-1.jpg",
    "genesis-gmr-001": "https://lemansultimate.com/wp-content/uploads/2026/08/1920x1080Genesis-12.jpg",
    "glickenhaus-scg-007": "https://lemansultimate.com/wp-content/uploads/2024/02/Glick-7.png",
    "isotta-fraschini-tipo-6": "https://lemansultimate.com/wp-content/uploads/2024/09/Desktop-Screenshot-2024.09.10-11.27.29.51.png",
    "lamborghini-sc63": "https://lemansultimate.com/wp-content/uploads/2024/07/Desktop-Screenshot-2024.07.16-10.52.17.50.png",
    "peugeot-9x8": "https://lemansultimate.com/wp-content/uploads/2024/02/Peugeot-9X8-4.png",
    "vanwall-vandervell-680": "https://lemansultimate.com/wp-content/uploads/2024/02/Vanwall-7.png",
    "mercedes-amg-lmgt3": "https://lemansultimate.com/wp-content/uploads/2025/07/1920x1080Merc-1.jpg",
}
```

Use bilingual strengths/cautions that make the evidence boundary explicit: Aston neutral/no-hybrid simplicity vs earlier braking and bump sensitivity; Genesis braking/rotation vs sensitive front end; Glickenhaus simple non-hybrid delivery vs different braking; Isotta simple controls vs limited current performance evidence; Lamborghini traction/rotation vs twitchy rear and bump sensitivity; wingless Peugeot approachable top-speed potential vs front-hybrid management; Vanwall simple non-hybrid delivery vs limited current performance evidence; Mercedes stable braking/traction/aero vs tight-direction-change understeer.

- [ ] **Step 4: Add sourced practice notes for all eight cars**

Use Coach Dave's current aggregate guides as the handling source:

```python
HYPERCAR_GUIDE = "which-hypercars-are-best-in-le-mans-ultimate"
GT3_GUIDE = "best-gt3-cars-in-le-mans-ultimate"
```

For Glickenhaus, Isotta, and Vanwall, limit the source observation to their non-hybrid control model and write the exercise as a comparison of braking/throttle references; do not invent a current pace ranking. Set per-record `checked_on="2026-09-22"` in `NOTE_REVIEWS` for only the eight new cars.

- [ ] **Step 5: Make asset synchronization include every car and fetch the new files**

Replace the recommended-slug set with deterministic iteration over all `CARS`:

```python
cars = tuple((car.image, car.image_source_url) for _, car in sorted(CARS.items()))
```

Run: `venv/bin/python scripts/sync_lmu_guide_assets.py`

Expected: `Synced 42 official LMU guide assets.` after Task 2 adds 18 tracks; if run now, expect 40. Confirm each new WebP is non-empty and decodes with `ffprobe`.

- [ ] **Step 6: Run focused tests and commit**

Run: `venv/bin/python -m unittest tests.test_lmu_guide.LmuGuideDataTests tests.test_lmu_content.ContentTests`

Expected: catalog/note tests PASS; snapshot-current test may remain RED until Task 5 publishes the release.

```bash
git add lmu_guide_data.py lmu_practice_data.py scripts/sync_lmu_guide_assets.py tests/test_lmu_guide.py tests/test_lmu_content.py static/kozekilmu/guide/cars
git commit -m "feat: complete LMU Hypercar and LMGT3 catalog"
```

### Task 2: Add Road Atlanta and Long Beach

**Files:**
- Modify: `tests/test_lmu_guide.py:78-265`
- Modify: `lmu_guide_data.py:11-180`
- Modify: `lmu_practice_data.py:11-31`
- Modify: `templates/kozekilmu_tracks.html:94`
- Create: `static/kozekilmu/guide/tracks/road-atlanta.webp`
- Create: `static/kozekilmu/guide/tracks/long-beach.webp`

**Interfaces:**
- Produces: `CIRCUITS` with 18 ordered entries and `TRACK_NOTES` with matching keys.
- Consumes: complete `CARS` from Task 1.

- [ ] **Step 1: Write failing track-count, slug, alias, and copy tests**

Extend `EXPECTED_SLUGS` and `EXPECTED_DLC` with `road-atlanta` and `long-beach`; assert 18 rendered cards, official announcement URLs, `4.088` and `3.167` lengths, and the Chinese aliases `亚特兰大之路`, `罗德亚特兰大`, `长滩`, `长滩街道赛道`.

- [ ] **Step 2: Run the track tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_lmu_guide.LmuGuideDataTests tests.test_lmu_guide.LmuGuideRouteTests`

Expected: FAIL with missing slugs and `16 != 18`.

- [ ] **Step 3: Add source URL overrides and both circuit records**

Use:

```python
_CIRCUIT_SOURCE_URLS = {
    "road-atlanta": "https://lemansultimate.com/le-mans-ultimate-adds-second-us-track-pack-dlc-alongside-elms-2026-season-liveries/",
    "long-beach": "https://lemansultimate.com/le-mans-ultimate-adds-second-us-track-pack-dlc-alongside-elms-2026-season-liveries/",
}
```

Road Atlanta: `Braselton, United States`, `布拉塞尔顿，美国（Braselton, United States）`, `4.088`, DLC, flowing elevation/blind crests/camber changes. Ordinary LMGT3 picks: Mercedes-AMG, BMW M4, Ferrari 296. Ordinary Hypercar picks: Porsche 963, BMW M Hybrid V8, Peugeot 9X8 2024.

Long Beach: `Long Beach, United States`, `长滩，美国（Long Beach, United States）`, `3.167`, DLC, concrete walls/blind entries/limited margin. Ordinary LMGT3 picks: BMW M4, Corvette Z06, Mercedes-AMG. Ordinary Hypercar picks: Cadillac V-Series.R, Porsche 963, Peugeot 9X8 2024.

Use these official announcement images:

```python
"road-atlanta": "https://mcusercontent.com/d64b6e298cfffd4e86ce086a4/images/1aeeeff8-e212-029d-6e0a-b80036dec94f.jpg"
"long-beach": "https://mcusercontent.com/d64b6e298cfffd4e86ce086a4/images/75e22a61-9950-a555-cecb-5d7ae3dc189b.jpg"
```

- [ ] **Step 4: Add bilingual practice rows and aliases**

Use source observations limited to official claims and separate editorial exercises:

```python
"road-atlanta": (
    "官方强调连续起伏弯、盲坡顶和不断变化的弯道倾角。",
    "The official overview highlights flowing elevation, blind crests, and changing camber.",
    "先用保守速度固定盲坡顶后的参照，再以连续干净圈比较起伏路段的一致性。",
    "Fix references beyond blind crests at conservative speed, then compare consistency over consecutive clean laps.",
)
"long-beach": (
    "这是 LMU 首条真正街道赛道，混凝土墙、盲入口和极小容错构成主要挑战。",
    "LMU's first true street circuit is defined by concrete walls, blind entries, and minimal margin.",
    "先建立可重复的制动与贴墙位置，再逐步缩小安全余量，不以偶然一圈替代稳定性。",
    "Establish repeatable braking and wall placement before reducing margin; do not trade consistency for one lucky lap.",
)
```

- [ ] **Step 5: Sync assets, run tests, and commit**

Run: `venv/bin/python scripts/sync_lmu_guide_assets.py`

Run: `venv/bin/python -m unittest tests.test_lmu_guide.LmuGuideDataTests tests.test_lmu_guide.LmuGuideRouteTests`

Expected: 18 circuits and both local track images PASS; snapshot test is deferred to Task 5.

```bash
git add lmu_guide_data.py lmu_practice_data.py templates/kozekilmu_tracks.html tests/test_lmu_guide.py static/kozekilmu/guide/tracks
git commit -m "feat: add Road Atlanta and Long Beach guides"
```

### Task 3: Add the 36 first-class Sleeper Picks

**Files:**
- Modify: `tests/test_lmu_guide.py:89-220`
- Modify: `lmu_guide_data.py:45-190`

**Interfaces:**
- Produces: `Circuit.lmgt3_sleeper: Recommendation` and `Circuit.hypercar_sleeper: Recommendation` for every circuit.
- Consumes: `_recommend(car_slug, fit, fit_zh)` and the complete car/circuit catalogs.

- [ ] **Step 1: Write failing model and validation tests**

```python
def test_every_circuit_has_one_valid_sleeper_per_class(self):
    for circuit in guide.CIRCUITS:
        self.assertEqual(guide.CARS[circuit.lmgt3_sleeper.car_slug].car_class, "LMGT3")
        self.assertEqual(guide.CARS[circuit.hypercar_sleeper.car_slug].car_class, "Hypercar")
        self.assertTrue(circuit.lmgt3_sleeper.fit.strip())
        self.assertTrue(circuit.lmgt3_sleeper.fit_zh.strip())
        self.assertTrue(circuit.hypercar_sleeper.fit.strip())
        self.assertTrue(circuit.hypercar_sleeper.fit_zh.strip())

def test_sleeper_overlap_with_ordinary_recommendations_is_valid(self):
    overlap = replace(guide.CIRCUITS[0], lmgt3_sleeper=guide.CIRCUITS[0].lmgt3[0])
    with patch.object(guide, "CIRCUITS", (overlap, *guide.CIRCUITS[1:])):
        guide.validate_guide_data()
```

- [ ] **Step 2: Run tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_lmu_guide.LmuGuideDataTests`

Expected: ERROR because the Sleeper fields do not exist.

- [ ] **Step 3: Extend `Circuit`, `_circuit`, and validation**

Add the two non-optional `Recommendation` fields after the ordinary tuples. Validate their car existence, class, English/Chinese fit copy, and forbidden fastest claims. Do not enforce non-overlap.

- [ ] **Step 4: Populate the exact Sleeper roster**

Use this reviewed roster; each entry gets a circuit-specific English and Chinese reason centered on stability plus layout-matched pace:

| Circuit | LMGT3 Sleeper | Hypercar Sleeper |
|---|---|---|
| Bahrain | Mercedes-AMG LMGT3 | Peugeot 9X8 2024 |
| Barcelona | Mercedes-AMG LMGT3 | Porsche 963 |
| Le Mans | Mercedes-AMG LMGT3 | Peugeot 9X8 (wingless) |
| Paul Ricard | Mercedes-AMG LMGT3 | Peugeot 9X8 (wingless) |
| COTA | BMW M4 LMGT3 | Porsche 963 |
| Daytona | Mercedes-AMG LMGT3 | Peugeot 9X8 (wingless) |
| Fuji | Lexus RC F LMGT3 | Peugeot 9X8 (wingless) |
| Imola | Mercedes-AMG LMGT3 | BMW M Hybrid V8 |
| Interlagos | Lexus RC F LMGT3 | Porsche 963 |
| Lusail | Mercedes-AMG LMGT3 | Peugeot 9X8 2024 |
| Monza | BMW M4 LMGT3 | Peugeot 9X8 (wingless) |
| Portimão | Mercedes-AMG LMGT3 | BMW M Hybrid V8 |
| Sebring | Mercedes-AMG LMGT3 | Cadillac V-Series.R |
| Silverstone International | Mercedes-AMG LMGT3 | Porsche 963 |
| Spa | Mercedes-AMG LMGT3 | Peugeot 9X8 2024 |
| Laguna Seca | Lexus RC F LMGT3 | Porsche 963 |
| Road Atlanta | Mercedes-AMG LMGT3 | Porsche 963 |
| Long Beach | BMW M4 LMGT3 | Porsche 963 |

The reason template must name the relevant trait and circuit demand, for example:

```python
_recommend(
    "mercedes-amg-lmgt3",
    "Sleeper Pick: stable braking and strong traction make Long Beach's walls and slow exits easier to approach without giving away useful pace.",
    "Sleeper之选：稳定制动和强牵引力让长滩的贴墙重刹与低速出弯更容易掌控，同时保留实用速度。",
)
```

Do not copy an ordinary fit sentence when the car overlaps the top three.

- [ ] **Step 5: Run validation tests and commit**

Run: `venv/bin/python -m unittest tests.test_lmu_guide.LmuGuideDataTests`

Expected: PASS, including the explicit overlap case.

```bash
git add lmu_guide_data.py tests/test_lmu_guide.py
git commit -m "feat: add LMU sleeper recommendations"
```

### Task 4: Render and integrate Sleeper Picks without identity collisions

**Files:**
- Modify: `tests/test_lmu_guide.py:223-330`
- Modify: `tests/test_lmu_extensions.py:10-25`
- Modify: `tests/browser/test_lmu_tools.py:8-105`
- Modify: `tests/browser/test_lmu_extensions.py:6-37`
- Modify: `app.py:150-164`
- Modify: `templates/kozekilmu_tracks.html:47-180`
- Modify: `templates/_lmu_catalog_cards.html:18-25`
- Modify: `static/css/kozekilmu_tracks.css`

**Interfaces:**
- Produces: 144 recommendation `<li>` nodes, 36 with `data-sleeper="true"`; unique compare keys; reverse catalog entries carrying `is_sleeper`.
- Consumes: Sleeper fields from Task 3 and existing `lmu_tools.js` generic recommendation discovery.

- [ ] **Step 1: Write failing render and integration tests**

Assert 18 circuit cards, 72 LMGT3 entries, 72 Hypercar entries, 36 `.sleeper-pick` entries, bilingual badge text, and unique `data-key` values. Update browser expectations from three to four visible recommendations per filtered class and from 16 to 18 circuits.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_lmu_guide.LmuGuideRouteTests tests.test_lmu_extensions.LmuExtensionsTests`

Expected: FAIL because only ordinary recommendations render and reverse catalog counts remain six per circuit.

- [ ] **Step 3: Render the fourth card with a unique key**

For each class, append the appropriate Sleeper in the Jinja loop and set:

```jinja2
data-key="{{ circuit.slug }}:{{ car.slug }}{{ ':sleeper' if is_sleeper else '' }}"
data-sleeper="{{ 'true' if is_sleeper else 'false' }}"
```

Render `Sleeper之选 / Sleeper Pick` in a `.sleeper-badge`, keep the independent reason, review block, practice block, favorite action, and compare action. Update hero copy to “三台常规推荐与一台 Sleeper 之选 / three regular choices plus one Sleeper Pick.”

- [ ] **Step 4: Include Sleeper entries in reverse recommendations**

Build catalog rows as `(circuit, recommendation, is_sleeper)` and append both Sleeper entries after ordinary entries. In `_lmu_catalog_cards.html`, show the bilingual Sleeper badge when `is_sleeper` is true. Duplicate circuit links are allowed when one car has both roles because the reasons differ.

- [ ] **Step 5: Add restrained styling and verify JS needs no special branch**

Style `.sleeper-pick` with the existing green tokens, a slightly stronger border, and `.sleeper-badge`; add light-theme and narrow-screen rules beside existing recommendation rules. Do not change `lmu_tools.js`: it already filters and compares every unique `li.recommendation[data-key]`.

- [ ] **Step 6: Run Python and browser-focused tests, then commit**

Run: `venv/bin/python -m unittest tests.test_lmu_guide tests.test_lmu_extensions`

Run: `venv/bin/python -m unittest tests.browser.test_lmu_tools tests.browser.test_lmu_extensions`

Expected: PASS with 18 circuits, four per class, unique Sleeper comparisons, search/filter inclusion, and no horizontal overflow.

```bash
git add app.py templates/kozekilmu_tracks.html templates/_lmu_catalog_cards.html static/css/kozekilmu_tracks.css tests/test_lmu_guide.py tests/test_lmu_extensions.py tests/browser/test_lmu_tools.py tests/browser/test_lmu_extensions.py
git commit -m "feat: integrate sleeper picks into LMU guide"
```

### Task 5: Version Sleeper records and publish the V1.4.2 content release

**Files:**
- Modify: `tests/test_lmu_content.py:15-76`
- Modify: `lmu_practice_data.py:5-90`
- Modify: `lmu_content.py:5-61`
- Modify: `docs/LMU_CONTENT_MAINTENANCE.md:7-25`
- Modify: `data/lmu/releases.json`
- Create: `data/lmu/2026.09.22.1.json`

**Interfaces:**
- Produces: `GAME_REFERENCE="V1.4.2"`, `GAME_CHECKED_ON="2026-09-22"`, 36 independent `sleeper:` snapshot records, and a current published snapshot.
- Consumes: all completed guide data from Tasks 1-4.

- [ ] **Step 1: Write failing version and snapshot tests**

Assert the latest release is `2026.09.22.1`, game reference is V1.4.2, all 36 keys beginning `sleeper:` exist, total recommendation review count is 144, and ordinary plus Sleeper overlap creates two distinct records.

- [ ] **Step 2: Run tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_lmu_content.ContentTests`

Expected: FAIL with V1.4.1.4, no Sleeper records, and unpublished differences.

- [ ] **Step 3: Separate game-review date from legacy note-review date**

Keep `CHECKED_ON = "2026-09-09"` for existing notes. Add:

```python
GAME_REFERENCE = "V1.4.2"
GAME_CHECKED_ON = "2026-09-22"
GAME_SOURCE = "https://motorsportgames.com/le-mans-ultimate-releases-version-1-2-update-introducing-paul-ricard-racing-circuit-ginetta-lmp3-race-car-alongside-physics-overhaul-online-competition-refinement-and-team-online-championships-dup/"
```

Use `GAME_CHECKED_ON` only for `reference:game` and template context. Keep new entity note dates explicit through `NOTE_REVIEWS`.

- [ ] **Step 4: Add independent Sleeper snapshot records**

Keep ordinary keys as `recommendation:{circuit}:{car}`. Add:

```python
records[f"sleeper:{circuit.slug}:lmgt3"] = ...
records[f"sleeper:{circuit.slug}:hypercar"] = ...
```

Each record stores the selected car name, bilingual fit, unverified applicable version, 2026-09-22 review date, circuit/car sources, and “No driving-test evidence.” Add `sleeper` bilingual labels to `FIELD_LABELS`/updates grouping where needed.

- [ ] **Step 5: Update maintenance documentation and publish**

Run:

```bash
venv/bin/python scripts/publish_lmu_content.py \
  --version 2026.09.22.1 --date 2026-09-22 \
  --summary-zh '新增亚特兰大之路与长滩，补齐 24 辆 HY/LMGT3 车型，并为 18 条赛道各添加 HY、GT3 Sleeper 之选。' \
  --summary-en 'Add Road Atlanta and Long Beach, complete the 24-car Hypercar/LMGT3 catalog, and add one Hypercar and LMGT3 Sleeper Pick for all 18 circuits.'
```

Expected: creates `data/lmu/2026.09.22.1.json` and appends one manifest entry without modifying older snapshots.

- [ ] **Step 6: Verify snapshot consistency and commit**

Run: `venv/bin/python scripts/publish_lmu_content.py --check`

Run: `venv/bin/python -m unittest tests.test_lmu_content.ContentTests`

Expected: PASS; latest release changes are empty against current records, baseline history remains readable, and updates show V1.4.2.

```bash
git add lmu_practice_data.py lmu_content.py docs/LMU_CONTENT_MAINTENANCE.md data/lmu/releases.json data/lmu/2026.09.22.1.json tests/test_lmu_content.py
git commit -m "feat: publish LMU V1.4.2 content release"
```

### Task 6: Update user documentation and run complete QA

**Files:**
- Modify: `README.md:429-457`
- Modify: `README.en.md:437-465`
- Modify: `docs/WEB_GUIDE.md:16-40`
- Modify: `docs/WEB_GUIDE.en.md:17-41`
- Modify: tests only if complete regression exposes a real requirement mismatch

**Interfaces:**
- Produces: user-facing documentation matching the shipped 18-circuit, 24-car, 3+1 recommendation model.
- Consumes: final behavior from Tasks 1-5.

- [ ] **Step 1: Update bilingual documentation**

Document the 18 circuits, 24 cars, separate Sleeper card, overlap allowance, filter/comparison inclusion, editorial/unverified boundary, and V1.4.2 content release. Do not describe the recommendations as measured rankings.

- [ ] **Step 2: Run focused static checks**

```bash
venv/bin/python -m compileall -q app.py lmu_guide_data.py lmu_practice_data.py lmu_content.py scripts tests
node --check static/js/lmu_tools.js
node --check static/js/lmu_guide_language.js
node tests/js/lmu_guide_language_harness.js
venv/bin/python scripts/publish_lmu_content.py --check
git diff --check
```

Expected: every command exits 0.

- [ ] **Step 3: Run the full unit suite**

Run: `venv/bin/python -m unittest discover -s tests -p 'test_*.py'`

Expected: `OK` with only the repository's documented platform skips.

- [ ] **Step 4: Run browser regression**

Run: `venv/bin/python -m unittest discover -s tests/browser -p 'test_lmu_*.py'`

Expected: PASS. Explicitly inspect Road Atlanta and Long Beach, a new Mercedes card, an overlapping Sleeper, vehicle filtering, reverse catalog badges, and comparison cloning.

- [ ] **Step 5: Capture and inspect desktop/mobile theme-language states**

At 1440×1000 and 375×812, inspect both themes and both languages. Confirm no overflow, no Chinese visible in English mode, badges remain readable, locally stored images render, and no console/page errors occur.

- [ ] **Step 6: Confirm immutable history and final Git scope**

Run: `git diff HEAD~5 -- data/lmu/baseline-import.json data/lmu/2026.09.09.1.json`

Expected: no output.

Run: `git status -sb`

Expected: only intentional documentation/QA changes remain before the final commit.

- [ ] **Step 7: Commit documentation and QA updates**

```bash
git add README.md README.en.md docs/WEB_GUIDE.md docs/WEB_GUIDE.en.md
git commit -m "docs: explain LMU sleeper recommendations"
```

