# LMU Circuit Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a spacious, source-attributed LMU circuit guide at `/kozekilmu/tracks`, covering all 16 official circuits with three LMGT3 and three Hypercar recommendations per circuit.

**Architecture:** Store immutable guide content in a focused Python module, render it through one read-only Flask route and Jinja template, and keep presentation in a dedicated CSS file. A developer-only standard-library script downloads official LMU media and converts it to committed local WebP assets through FFmpeg; the page performs no live third-party requests.

**Tech Stack:** Python 3.11+, Flask/Jinja, HTML5 `<details>`, CSS Grid, existing `static/js/motion.js`, `unittest`, FFmpeg for one-time WebP conversion.

## Global Constraints

- Preserve `/kozekilmu` as the existing victory archive; change only its new guide navigation.
- Cover exactly the 16 circuits listed by LMU on 2026-08-30, including DLC.
- Render exactly three LMGT3 and three Hypercar recommendations for every circuit.
- Recommendations target ordinary players and prioritize stability, braking confidence, tyre management, traffic handling, and circuit suitability; never claim an objectively fastest car.
- Use official LMU images first, commit optimized local WebP files, and record every source URL.
- Use a themed placeholder when an official image cannot be obtained; never silently substitute an unverified third-party image.
- Reuse the dark navy, Petronas-green, Cormorant/Palatino, and shared motion language without adding frontend dependencies.
- Respect keyboard access and `prefers-reduced-motion`; essential content must not depend on hover or JavaScript.
- Do not modify downloader, extraction, conversion, task, API, port, or service logic.

## File Structure

- Create `lmu_guide_data.py`: immutable circuit, car, recommendation, DLC, and source metadata.
- Create `scripts/sync_lmu_guide_assets.py`: optional developer command for downloading official images and converting them to WebP.
- Create `templates/kozekilmu_tracks.html`: semantic guide markup and data loops only.
- Create `static/css/kozekilmu_tracks.css`: guide layout, responsive behavior, details styling, and fallbacks.
- Create `static/kozekilmu/guide/tracks/*.webp`: 16 circuit images.
- Create `static/kozekilmu/guide/cars/*.webp`: the 16 recommended car images reused across circuits.
- Modify `app.py`: add one read-only `/kozekilmu/tracks` route.
- Modify `templates/kozekilmu.html`: add the two-link easter-egg navigation.
- Create `tests/test_lmu_guide.py`: data, route, local-asset, semantic, responsive, and accessibility contracts.
- Modify `tests/test_kozekilmu.py`: preserve the victory page while asserting its new navigation.

---

### Task 1: Build the Immutable Guide Dataset

**Files:**
- Create: `lmu_guide_data.py`
- Create: `tests/test_lmu_guide.py`

**Interfaces:**
- Produces: `Car`, `Recommendation`, and `Circuit` frozen dataclasses.
- Produces: `CARS: dict[str, Car]`, `CIRCUITS: tuple[Circuit, ...]`, `GUIDE_UPDATED = "2026-08-30"`.
- Produces: `validate_guide_data() -> None`, called at module import and directly by tests.
- Consumes: no downloader or Flask code.

- [ ] **Step 1: Write failing data-contract tests**

Create `tests/test_lmu_guide.py` with these exact checks:

```python
import unittest

import lmu_guide_data as guide


EXPECTED_SLUGS = (
    "bahrain", "barcelona", "le-mans", "paul-ricard", "cota", "daytona",
    "fuji", "imola", "interlagos", "lusail", "monza", "portimao",
    "sebring", "silverstone-international", "spa", "laguna-seca",
)
EXPECTED_DLC = {
    "barcelona", "paul-ricard", "cota", "daytona", "imola",
    "interlagos", "lusail", "silverstone-international", "laguna-seca",
}


class LmuGuideDataTests(unittest.TestCase):
    def test_current_official_circuit_snapshot_is_complete_and_ordered(self):
        self.assertEqual(tuple(item.slug for item in guide.CIRCUITS), EXPECTED_SLUGS)
        self.assertEqual(
            {item.slug for item in guide.CIRCUITS if item.is_dlc},
            EXPECTED_DLC,
        )

    def test_each_circuit_has_three_unique_recommendations_per_requested_class(self):
        for circuit in guide.CIRCUITS:
            with self.subTest(circuit=circuit.slug):
                self.assertEqual(len(circuit.lmgt3), 3)
                self.assertEqual(len(circuit.hypercar), 3)
                self.assertEqual(len({item.car_slug for item in circuit.lmgt3}), 3)
                self.assertEqual(len({item.car_slug for item in circuit.hypercar}), 3)
                self.assertTrue(all(guide.CARS[item.car_slug].car_class == "LMGT3" for item in circuit.lmgt3))
                self.assertTrue(all(guide.CARS[item.car_slug].car_class == "Hypercar" for item in circuit.hypercar))

    def test_copy_and_sources_are_complete_without_fastest_claims(self):
        guide.validate_guide_data()
        forbidden = ("绝对最快", "必胜", "guaranteed fastest")
        for circuit in guide.CIRCUITS:
            copy = " ".join((circuit.character, circuit.challenge, circuit.advice))
            self.assertTrue(circuit.source_url.startswith("https://lemansultimate.com/"))
            self.assertFalse(any(token in copy.lower() for token in forbidden))
            for recommendation in (*circuit.lmgt3, *circuit.hypercar):
                self.assertGreaterEqual(len(recommendation.fit), 12)
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_lmu_guide.LmuGuideDataTests -v
```

Expected: import failure because `lmu_guide_data.py` does not exist.

- [ ] **Step 3: Implement the typed data module**

Create the following public shape in `lmu_guide_data.py`:

```python
from dataclasses import dataclass

GUIDE_UPDATED = "2026-08-30"


@dataclass(frozen=True, slots=True)
class Car:
    slug: str
    name: str
    car_class: str
    image: str
    source_url: str
    image_source_url: str
    strength: str
    caution: str


@dataclass(frozen=True, slots=True)
class Recommendation:
    car_slug: str
    fit: str


@dataclass(frozen=True, slots=True)
class Circuit:
    slug: str
    name: str
    location: str
    length_km: str
    is_dlc: bool
    image: str
    source_url: str
    image_source_url: str
    character: str
    challenge: str
    advice: str
    lmgt3: tuple[Recommendation, Recommendation, Recommendation]
    hypercar: tuple[Recommendation, Recommendation, Recommendation]
```

Define `CARS` for these exact recommended cars:

| Slug | Official display name | Class | Primary ordinary-player trait | Caution |
|---|---|---|---|---|
| `aston-martin-vantage-lmgt3` | Aston Martin Vantage AMR LMGT3 | LMGT3 | compliant platform and calm braking | can lean into safe understeer |
| `bmw-m4-lmgt3` | BMW M4 LMGT3 | LMGT3 | stable, kerb-friendly front-engine balance | front tyres punish overdriving |
| `corvette-z06-lmgt3-r` | Corvette Z06 LMGT3.R | LMGT3 | confident braking and predictable traction | throttle rotation needs patience |
| `ferrari-296-lmgt3` | Ferrari 296 LMGT3 | LMGT3 | agile direction changes and balanced aero | rough kerbs can unsettle it |
| `ford-mustang-lmgt3` | Ford Mustang LMGT3 | LMGT3 | straight-line speed and accessible torque | mass and front-tyre load show in tight sectors |
| `lamborghini-huracan-lmgt3-evo2` | Lamborghini Huracan LMGT3 Evo2 | LMGT3 | fast response in flowing corners | rear movement requires smooth inputs |
| `lexus-rc-f-lmgt3` | Lexus RC F LMGT3 | LMGT3 | reassuring stability and usable V8 delivery | slower rotation in very tight changes |
| `mclaren-720s-lmgt3-evo` | McLaren 720S LMGT3 Evo | LMGT3 | aero efficiency and high-speed confidence | low-speed traction and tall kerbs need care |
| `porsche-911-gt3-r` | Porsche 911 GT3 R LMGT3 | LMGT3 | traction and rotation from the rear-engine layout | trail braking can provoke the rear |
| `alpine-a424` | Alpine A424 | Hypercar | compact, nimble response | braking stability is setup-sensitive |
| `bmw-m-hybrid-v8` | BMW M Hybrid V8 | Hypercar | stable platform and kerb confidence | needs patience to rotate in slow corners |
| `cadillac-v-series-r` | Cadillac V-Series.R | Hypercar | strong braking and mechanical traction | torque can stress the rear tyres |
| `ferrari-499p` | Ferrari 499P | Hypercar | aero performance and decisive rotation | rewards precise inputs more than corrections |
| `peugeot-9x8-2024` | Peugeot 9X8 2024 | Hypercar | agile modern aero package | balance is sensitive to setup and kerb use |
| `porsche-963` | Porsche 963 | Hypercar | broad, approachable operating window | tyre temperature still needs monitoring |
| `toyota-gr010-hybrid` | Toyota GR010-Hybrid | Hypercar | stability, traction, and endurance-friendly behaviour | slower rotation can cost time in tight sectors |

Use official car page URLs and image paths of the form
`kozekilmu/guide/cars/<slug>.webp`.

Use these exact official LMU image URLs for the 16 car assets:

| Car slug | Official image URL |
|---|---|
| `alpine-a424` | `https://lemansultimate.com/wp-content/uploads/2024/09/Alpine-Solo-LM-19-1024x576.png` |
| `aston-martin-vantage-lmgt3` | `https://lemansultimate.com/wp-content/uploads/2025/02/Aston-3-1024x576.png` |
| `bmw-m4-lmgt3` | `https://lemansultimate.com/wp-content/uploads/2024/12/Le-Mans-Ultimate-Screenshot-2026.06.03-09.42.22.99-1024x576.png` |
| `bmw-m-hybrid-v8` | `https://lemansultimate.com/wp-content/uploads/2024/02/Le-Mans-Ultimate-Screenshot-2026.06.03-10.47.35.97-1024x576.png` |
| `cadillac-v-series-r` | `https://lemansultimate.com/wp-content/uploads/2024/02/le-mans-ultimate.exe-Screenshot-2025.07.15-14.16.55.62-1024x576.png` |
| `corvette-z06-lmgt3-r` | `https://lemansultimate.com/wp-content/uploads/2024/12/Le-Mans-Ultimate-Screenshot-2026.06.03-10.06.06.28-1024x576.png` |
| `ferrari-296-lmgt3` | `https://lemansultimate.com/wp-content/uploads/2024/11/Ferrari-54-1-1024x576.png` |
| `ferrari-499p` | `https://lemansultimate.com/wp-content/uploads/2024/02/Le-Mans-Ultimate-Screenshot-2026.06.03-10.55.45.94-1024x576.png` |
| `ford-mustang-lmgt3` | `https://lemansultimate.com/wp-content/uploads/2025/02/Le-Mans-Ultimate-Screenshot-2026.06.03-09.53.29.53-1024x576.png` |
| `lamborghini-huracan-lmgt3-evo2` | `https://lemansultimate.com/wp-content/uploads/2025/06/le-mans-ultimate.exe-Screenshot-2025.05.22-17.33.23.00-1024x576.png` |
| `lexus-rc-f-lmgt3` | `https://lemansultimate.com/wp-content/uploads/2025/06/le-mans-ultimate.exe-Screenshot-2025.05.20-12.33.09.16-1024x576.png` |
| `mclaren-720s-lmgt3-evo` | `https://lemansultimate.com/wp-content/uploads/2024/11/McLaren-70-3-1024x576.png` |
| `peugeot-9x8-2024` | `https://lemansultimate.com/wp-content/uploads/2024/02/Le-Mans-Ultimate-Screenshot-2026.06.03-10.20.35.91-1024x576.png` |
| `porsche-911-gt3-r` | `https://lemansultimate.com/wp-content/uploads/2025/02/Lm100-Screenshot-2025.02.13-13.57.39.75-1024x576.png` |
| `porsche-963` | `https://lemansultimate.com/wp-content/uploads/2024/02/Porsche-963-2-1024x576.png` |
| `toyota-gr010-hybrid` | `https://lemansultimate.com/wp-content/uploads/2024/02/Le-Mans-Ultimate-Screenshot-2026.06.03-12.31.24.88-1024x576.png` |

Define all circuits with the following verified lengths, DLC flags, and exact
recommendation mapping. Each `fit` sentence must connect the listed car trait to
the circuit characteristic stated in the same row.

| Circuit | km | DLC | Circuit character | LMGT3 picks | Hypercar picks |
|---|---:|:---:|---|---|---|
| Bahrain | 5.412 | No | heavy stops, low-speed traction, rear-tyre management | BMW, Corvette, Lexus | Toyota, Cadillac, Porsche |
| Barcelona | 4.657 | Yes | long loaded corners plus a mixed technical final sector | Ferrari, McLaren, Porsche | Ferrari, Peugeot 2024, Porsche |
| Le Mans | 13.626 | No | low drag, extreme braking zones, long full-throttle runs | Mustang, McLaren, Ferrari | Cadillac, Porsche, Ferrari |
| Paul Ricard | 5.842 | Yes | Mistral straight, Signes commitment, technical final sector | McLaren, Ferrari, Porsche | Peugeot 2024, Ferrari, Alpine |
| COTA | 5.513 | Yes | uphill braking, fast esses, slow traction zones | BMW, Corvette, Ferrari | Porsche, Cadillac, Ferrari |
| Daytona | 5.729 | Yes | banking efficiency, infield traction, Bus Stop stability | Mustang, BMW, McLaren | Cadillac, Porsche, BMW |
| Fuji | 4.563 | No | very long straight followed by a slow technical third sector | BMW, Porsche, Corvette | Toyota, Porsche, Cadillac |
| Imola | 4.909 | Yes | narrow rhythm, tall kerbs, repeated braking and traction | Porsche, BMW, Aston Martin | Porsche, BMW, Toyota |
| Interlagos | 4.309 | Yes | elevation, short lap, mixed-speed corners and traction exits | Ferrari, Porsche, Corvette | Ferrari, Porsche, Cadillac |
| Lusail | 5.419 | Yes | sustained medium/high-speed load and tyre temperature | McLaren, Ferrari, Lamborghini | Ferrari, Peugeot 2024, Alpine |
| Monza | 5.793 | No | maximum speed, heavy chicane braking, aggressive kerbs | Mustang, McLaren, Ferrari | Cadillac, Porsche, Ferrari |
| Portimão | 4.653 | No | blind crests, compression, rotation and traction | Porsche, Ferrari, McLaren | Ferrari, Alpine, Peugeot 2024 |
| Sebring | 6.019 | No | bumps, rough braking surfaces and traction over concrete seams | BMW, Aston Martin, Corvette | Cadillac, Porsche, BMW |
| Silverstone International | 2.979 | Yes | compact lap, frequent traffic and repeated direction changes | McLaren, Ferrari, BMW | Ferrari, Porsche, Peugeot 2024 |
| Spa | 7.004 | No | high-speed aero, elevation, long lap and variable weather | McLaren, Ferrari, BMW | Ferrari, Porsche, Cadillac |
| Laguna Seca | 3.602 | Yes | low-speed traction, elevation and the Corkscrew sequence | Porsche, Corvette, BMW | Porsche, Cadillac, BMW |

Use these exact official LMU image URLs for the circuit assets, in the same
order as the circuit records:

```text
bahrain = https://lemansultimate.com/wp-content/uploads/2024/02/Bahrain-20-1-1024x576.png
barcelona = https://lemansultimate.com/wp-content/uploads/2026/07/Barca-11-1024x576.png
le-mans = https://lemansultimate.com/wp-content/uploads/2024/02/Desktop-Screenshot-2024.01.30-13.22.32.90-1024x576.png
paul-ricard = https://lemansultimate.com/wp-content/uploads/2025/12/PaulRicard_1-1024x576.jpg
cota = https://lemansultimate.com/wp-content/uploads/2024/09/Desktop-Screenshot-2024.08.29-10.14.03.02-1-1024x576.png
daytona = https://lemansultimate.com/wp-content/uploads/2026/07/Daytona-11-1024x576.png
fuji = https://lemansultimate.com/wp-content/uploads/2024/02/Fuji-8-1-1024x576.png
imola = https://lemansultimate.com/wp-content/uploads/2024/07/Imola-Statics-1-1-1024x576.png
interlagos = https://lemansultimate.com/wp-content/uploads/2024/11/Interlagos-1-1024x576.png
lusail = https://lemansultimate.com/wp-content/uploads/2025/05/Qatar2-1024x576.jpg
monza = https://lemansultimate.com/wp-content/uploads/2024/02/Monza-21-1024x576.png
portimao = https://lemansultimate.com/wp-content/uploads/2024/02/Portimao-7-1-1024x576.png
sebring = https://lemansultimate.com/wp-content/uploads/2024/02/Sebring-13-1-1024x576.png
silverstone-international = https://lemansultimate.com/wp-content/uploads/2025/09/le-mans-ultimate.exe-Screenshot-2025.09.24-11.03.48.85-1024x576.png
spa = https://lemansultimate.com/wp-content/uploads/2024/02/Spa-11-1024x576.png
laguna-seca = https://lemansultimate.com/wp-content/uploads/2026/07/1920x1080LAG_3-1024x576.jpg
```

For display names and URLs, use the exact LMU circuit index entries. Implement
`validate_guide_data()` so duplicate slugs, wrong recommendation counts, missing
cars, class mismatches, blank copy, non-LMU source URLs, and non-local image paths
raise `ValueError`. Call it once after defining `CIRCUITS`.

- [ ] **Step 4: Run the focused tests to verify GREEN**

Run:

```bash
venv/bin/python -m unittest tests.test_lmu_guide.LmuGuideDataTests -v
```

Expected: all data tests pass.

- [ ] **Step 5: Commit the data model**

```bash
git add lmu_guide_data.py tests/test_lmu_guide.py
git commit -m "feat: add LMU circuit guide data"
```

---

### Task 2: Acquire and Verify Official Local WebP Assets

**Files:**
- Create: `scripts/sync_lmu_guide_assets.py`
- Create: `static/kozekilmu/guide/tracks/*.webp`
- Create: `static/kozekilmu/guide/cars/*.webp`
- Modify: `tests/test_lmu_guide.py`

**Interfaces:**
- Consumes: `CIRCUITS` and `CARS` from Task 1.
- Produces: `sync_assets(destination: Path, opener=urlopen, ffmpeg="ffmpeg") -> tuple[Path, ...]`.
- Produces: one 1024×576-or-smaller WebP per circuit and recommended car.

- [ ] **Step 1: Add failing local-asset tests**

Append a `LmuGuideAssetTests` class that iterates over every unique circuit/car
image path and asserts:

```python
path = Path("static") / relative_path
self.assertTrue(path.is_file(), relative_path)
self.assertEqual(path.read_bytes()[:4], b"RIFF")
self.assertEqual(path.read_bytes()[8:12], b"WEBP")
self.assertLess(path.stat().st_size, 450_000)
```

Also assert every image path is unique within its own resource type and every
source URL starts with `https://lemansultimate.com/` or
`https://lemansultimate.com/wp-content/uploads/`.

- [ ] **Step 2: Run the asset tests to verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_lmu_guide.LmuGuideAssetTests -v
```

Expected: failures naming the missing `static/kozekilmu/guide/...` files.

- [ ] **Step 3: Implement the developer-only asset sync script**

Use only the standard library plus the existing system FFmpeg. For each source:

```python
request = Request(source_url, headers={"User-Agent": "GTD LMU guide asset sync"})
with opener(request, timeout=30) as response:
    source_path.write_bytes(response.read())
subprocess.run(
    [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source_path),
        "-vf", "scale=1024:576:force_original_aspect_ratio=decrease",
        "-frames:v", "1", "-c:v", "libwebp", "-quality", "82",
        "-compression_level", "6", str(output_path),
    ],
    check=True,
)
```

Download into `TemporaryDirectory`, write only the final WebP into the project,
create parent directories, reject empty responses, and continue to the next
asset after printing one clear failure. Exit non-zero if any requested asset
failed so missing files cannot be mistaken for success.

- [ ] **Step 4: Run the sync script and verify every official asset**

Run:

```bash
venv/bin/python scripts/sync_lmu_guide_assets.py
venv/bin/python -m unittest tests.test_lmu_guide.LmuGuideAssetTests -v
```

Expected: 32 local WebP files (16 tracks + 16 unique recommended cars) and all
asset tests pass. If an LMU URL is unavailable, deliberately omit that local
path in data so the template fallback is used; do not use another website.

- [ ] **Step 5: Commit assets and provenance code**

```bash
git add scripts/sync_lmu_guide_assets.py static/kozekilmu/guide lmu_guide_data.py tests/test_lmu_guide.py
git commit -m "feat: add official LMU guide imagery"
```

---

### Task 3: Add the Read-Only Guide Route and Two-Page Navigation

**Files:**
- Modify: `app.py:14-90`
- Modify: `templates/kozekilmu.html:350-370`
- Create: `templates/kozekilmu_tracks.html`
- Modify: `tests/test_kozekilmu.py`
- Modify: `tests/test_lmu_guide.py`

**Interfaces:**
- Consumes: `CIRCUITS` and `GUIDE_UPDATED` from Task 1.
- Produces: Flask endpoint `kozekilmu_tracks()` at `/kozekilmu/tracks`.
- Produces: `.easter-nav` with active-page `aria-current="page"` on both pages.

- [ ] **Step 1: Write failing route and navigation tests**

Add tests that assert:

```python
response = self.client.get("/kozekilmu/tracks")
self.assertEqual(response.status_code, 200)
html = response.get_data(as_text=True)
self.assertIn("<title>LMU 赛道指南 - GTD</title>", html)
self.assertIn('href="/kozekilmu"', html)
self.assertIn('href="/kozekilmu/tracks"', html)
self.assertIn('aria-current="page"', html)
self.assertEqual(html.count('class="circuit-card"'), 16)
self.assertEqual(html.count("<details"), 16)
self.assertEqual(html.count('data-class="LMGT3"'), 48)
self.assertEqual(html.count('data-class="Hypercar"'), 48)
```

Extend the existing victory-page test to require both navigation links and
`aria-current="page"` on the victory archive link while retaining every current
title, Bilibili, image, motion, and return-link assertion.

- [ ] **Step 2: Run route tests to verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_lmu_guide tests.test_kozekilmu -v
```

Expected: `/kozekilmu/tracks` returns 404 and victory navigation assertions fail.

- [ ] **Step 3: Add the Flask route**

Import only the public data constants and add:

```python
from lmu_guide_data import CARS, CIRCUITS, GUIDE_UPDATED


@app.route("/kozekilmu/tracks")
def kozekilmu_tracks():
    """Render the read-only LMU circuit and car recommendation guide."""
    return render_template(
        "kozekilmu_tracks.html",
        cars=CARS,
        circuits=CIRCUITS,
        guide_updated=GUIDE_UPDATED,
    )
```

- [ ] **Step 4: Add semantic navigation and template loops**

Place this navigation before the hero on both pages, changing only which link
has `aria-current="page"`:

```html
<nav class="easter-nav" aria-label="LMU 彩蛋分页">
  <a class="easter-nav-link is-active" href="{{ url_for('kozekilmu') }}" aria-current="page">VICTORY ARCHIVE <span>/ 冠军档案</span></a>
  <a class="easter-nav-link" href="{{ url_for('kozekilmu_tracks') }}">CIRCUIT GUIDE <span>/ 赛道指南</span></a>
</nav>
```

In the new template, loop over `circuits`; render one `<article
class="circuit-card" id="{{ circuit.slug }}">`, one lazy circuit image or
`.media-placeholder`, metadata, concise copy, and one native `<details>`. Inside
the details, render two recommendation groups. Resolve each recommendation with
the public `cars` mapping passed by the route with
`{% set car = cars[recommendation.car_slug] %}`. Do not perform dictionary
lookups through private Jinja globals.

Every external source link must use:

```html
target="_blank" rel="noopener noreferrer"
```

Load only `/static/css/kozekilmu_tracks.css`, `/static/css/motion.css`, and the
existing deferred `/static/js/motion.js`.

- [ ] **Step 5: Run route and victory regressions to verify GREEN**

Run:

```bash
venv/bin/python -m unittest tests.test_lmu_guide tests.test_kozekilmu tests.test_motion_system -v
```

Expected: all route, original easter egg, and shared-motion tests pass.

- [ ] **Step 6: Commit the route and semantic markup**

```bash
git add app.py templates/kozekilmu.html templates/kozekilmu_tracks.html tests/test_kozekilmu.py tests/test_lmu_guide.py
git commit -m "feat: add LMU circuit guide page"
```

---

### Task 4: Apply Spacious Responsive Styling and Safe Motion

**Files:**
- Create: `static/css/kozekilmu_tracks.css`
- Modify: `templates/kozekilmu.html`
- Modify: `templates/kozekilmu_tracks.html`
- Modify: `tests/test_lmu_guide.py`

**Interfaces:**
- Consumes: existing CSS tokens and `static/css/motion.css` behavior.
- Produces: two-column desktop grid, single-column mobile grid, accessible
  details controls, local-image fallback, and stable reduced-motion layout.

- [ ] **Step 1: Add failing presentation-contract tests**

Read the CSS and rendered HTML, then assert these contracts:

```python
self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", css)
self.assertRegex(css, r"@media\s*\(max-width:\s*820px\)")
self.assertRegex(css, r"(?s)\.circuit-grid\s*\{[^}]*grid-template-columns:\s*1fr")
self.assertIn("prefers-reduced-motion: reduce", css)
self.assertIn("details[open]", css)
self.assertIn(":focus-visible", css)
self.assertIn(".media-placeholder", css)
self.assertNotIn("display: none", reduced_motion_block)
self.assertIn('loading="lazy"', html)
self.assertIn('width="1024" height="576"', html)
self.assertEqual(html.count('data-motion-surface'), 16)
self.assertEqual(html.count('data-motion-sheen aria-hidden="true"'), 16)
```

Also assert the page includes the visible BoP/version caveat and official LMU
attribution links.

- [ ] **Step 2: Run presentation tests to verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_lmu_guide -v
```

Expected: failures for missing responsive, focus, details, placeholder, and
motion contracts.

- [ ] **Step 3: Implement the dedicated guide stylesheet**

Use the existing tokens exactly (`#0f172a`, `#0b1222`, `#009b95`, `#00a19b`,
`#f8fafc`, `#94a3b8`). Set the content width to `min(1240px, calc(100% - 40px))`,
use `clamp(28px, 4vw, 56px)` grid gaps, and keep card padding at least `28px`.

The circuit image is `aspect-ratio: 16 / 9; object-fit: cover`. Recommendation
cards use a 96–120px thumbnail beside text on desktop and stack naturally below
560px. Style the native summary with a visible disclosure marker, a minimum
44px target, and `cursor: pointer`. Do not animate `height: auto`; rely on shared
reveal/sheen motion and a color/border transition for `details[open]`.

Keep the page readable in reduced motion:

```css
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after { transition-duration: .01ms !important; }
}
```

Add compact `.easter-nav` styles to the original page’s existing inline CSS so
the navigation looks identical without extracting or reformatting unrelated CSS.

- [ ] **Step 4: Run focused HTML/CSS tests to verify GREEN**

Run:

```bash
venv/bin/python -m unittest tests.test_lmu_guide tests.test_kozekilmu tests.test_motion_system -v
```

Expected: all guide, original easter egg, and shared-motion tests pass.

- [ ] **Step 5: Commit presentation work**

```bash
git add static/css/kozekilmu_tracks.css templates/kozekilmu.html templates/kozekilmu_tracks.html tests/test_lmu_guide.py
git commit -m "style: polish LMU circuit guide"
```

---

### Task 5: Full Verification, Visual QA, and Research Cleanup

**Files:**
- Modify only files required by verified defects found in this task.
- Remove local untracked `.firecrawl/` research output after the committed data
  and source URLs have been independently checked; never add it to Git.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: verified desktop/mobile page with the original victory archive and
  downloader behavior intact.

- [ ] **Step 1: Verify official content completeness**

Compare the 16 circuit names, DLC flags, official URLs, and all car source URLs
against the 2026-08-30 LMU circuit/car index snapshot. Confirm every local image
origin is official and every recommendation references an available LMU car.

- [ ] **Step 2: Run the complete automated suite and static checks**

```bash
venv/bin/python -m unittest discover -s tests -v
venv/bin/python -m compileall -q app.py lmu_guide_data.py tests
node --check static/js/motion.js
git diff --check
```

Expected: all platform-independent tests pass, only the existing Windows-only
tests skip, and compile/Node/diff checks exit 0.

- [ ] **Step 3: Start the local service for visual QA**

```bash
venv/bin/python app.py
```

Confirm the process reports port `8233`. Check process ownership before stopping
anything already using that port.

- [ ] **Step 4: Perform desktop, mobile, keyboard, and reduced-motion QA**

At `/kozekilmu` and `/kozekilmu/tracks`, verify:

- navigation active state and back-to-download link;
- 16 roomy cards, correct image crops, DLC badges, and source links;
- every details section opens with keyboard and contains 3+3 recommendations;
- 1440px desktop uses two columns and 390px mobile uses one column without
  horizontal overflow;
- missing-image fallback remains legible by temporarily testing one invalid path
  without committing that change;
- reduced motion keeps all content visible and disables disruptive movement;
- no console errors or failed local static requests.

- [ ] **Step 5: Stop only the QA service and clean temporary research output**

Send Ctrl+C to the exact process started in Step 3. Confirm:

```bash
lsof -nP -iTCP:8233 -sTCP:LISTEN
```

returns no GTD process. Remove `.firecrawl/`, then run `git status --short` and
confirm only intentional implementation files remain.

- [ ] **Step 6: Commit any QA-only corrections**

If visual QA required scoped corrections:

```bash
git add <only the corrected guide files>
git commit -m "fix: refine LMU circuit guide QA"
```

If no corrections were required, do not create an empty commit.
