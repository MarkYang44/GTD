# LMU Circuit Guide Bilingual Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a complete Chinese/English language slider to `/kozekilmu/tracks`, defaulting to Chinese and restoring the user's last choice without reloading the page.

**Architecture:** Preserve the existing English data fields and add explicit Chinese companion fields to the immutable LMU guide data. Render both language variants server-side, hide only the inactive variant with CSS, and use one dedicated dependency-free script to synchronize the root language, translated attributes, browser title, accessible slider state, and guarded `localStorage` persistence.

**Tech Stack:** Python 3 dataclasses and `unittest`, Flask/Jinja, semantic HTML, CSS, vanilla JavaScript, Node.js behavior harness.

## Global Constraints

- Only `/kozekilmu/tracks` becomes bilingual; `/kozekilmu`, the downloader, user guide, queue, extraction, conversion, and network logic remain unchanged.
- First visit defaults to Chinese; later visits restore only a valid stored `zh` or `en` value.
- Switching language must not reload, navigate, change scroll position, or close an open `<details>` element.
- Official circuit names, car names, `LMGT3`, `Hypercar`, `DLC`, `LMU`, and `BoP` remain unchanged.
- Chinese locations retain the English location in parentheses; ambiguous motorsport terminology includes a concise English term in parentheses where useful.
- Do not add packages, a translation framework, an external translation service, inline JavaScript, or inline event handlers.
- Keep `static/js/motion.js` unchanged; the language behavior belongs only in `static/js/lmu_guide_language.js`.
- With JavaScript disabled or failed, Chinese content remains readable.
- The slider is keyboard operable, visibly focusable, screen-reader understandable, and at least 44px on its interactive axis.
- Preserve all current image fallback, source attribution, recommendation-count, responsive layout, and reduced-motion behavior.

---

### Task 1: Add Complete Bilingual Guide Data

**Files:**
- Modify: `lmu_guide_data.py:26-219`
- Modify: `tests/test_lmu_guide.py:36-81`

**Interfaces:**
- Consumes: existing `Car`, `Recommendation`, `Circuit`, `_car()`, `_recommend()`, `_circuit()`, `CARS`, and `CIRCUITS` interfaces.
- Produces: `Car.strength_zh: str`, `Car.caution_zh: str`, `Recommendation.fit_zh: str`, `Circuit.location_zh: str`, `Circuit.character_zh: str`, `Circuit.challenge_zh: str`, and `Circuit.advice_zh: str` for the template in Task 2.

- [ ] **Step 1: Add failing bilingual-data tests**

Add these tests to `LmuGuideDataTests`:

```python
def test_every_guide_entry_has_complete_chinese_copy(self):
    for car in guide.CARS.values():
        with self.subTest(car=car.slug):
            self.assertTrue(car.strength_zh.strip())
            self.assertTrue(car.caution_zh.strip())

    for circuit in guide.CIRCUITS:
        with self.subTest(circuit=circuit.slug):
            self.assertTrue(circuit.location_zh.strip())
            self.assertIn(f"（{circuit.location}）", circuit.location_zh)
            self.assertTrue(circuit.character_zh.strip())
            self.assertTrue(circuit.challenge_zh.strip())
            self.assertTrue(circuit.advice_zh.strip())
            for recommendation in (*circuit.lmgt3, *circuit.hypercar):
                self.assertTrue(recommendation.fit_zh.strip())

def test_data_validation_rejects_blank_chinese_copy(self):
    invalid = replace(guide.CIRCUITS[0], advice_zh="")
    with patch.object(guide, "CIRCUITS", (invalid, *guide.CIRCUITS[1:])):
        with self.assertRaisesRegex(ValueError, "blank circuit copy"):
            guide.validate_guide_data()

def test_chinese_copy_keeps_selected_technical_terms_bilingual(self):
    copy = " ".join(
        (
            *(car.strength_zh + " " + car.caution_zh for car in guide.CARS.values()),
            *(circuit.character_zh + " " + circuit.challenge_zh + " " + circuit.advice_zh for circuit in guide.CIRCUITS),
        )
    )
    for term in ("制动稳定性（braking stability）", "轮胎负荷（tyre load）"):
        self.assertIn(term, copy)
```

- [ ] **Step 2: Run the data tests to verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_lmu_guide.LmuGuideDataTests -v
```

Expected: the new tests fail with missing `*_zh` attributes.

- [ ] **Step 3: Extend the immutable data interfaces**

Add the Chinese fields without renaming or changing any existing English field:

```python
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
    strength_zh: str
    caution_zh: str


@dataclass(frozen=True, slots=True)
class Recommendation:
    car_slug: str
    fit: str
    fit_zh: str


@dataclass(frozen=True, slots=True)
class Circuit:
    slug: str
    name: str
    location: str
    location_zh: str
    length_km: str
    is_dlc: bool
    image: str
    source_url: str
    image_source_url: str
    character: str
    character_zh: str
    challenge: str
    challenge_zh: str
    advice: str
    advice_zh: str
    lmgt3: tuple[Recommendation, Recommendation, Recommendation]
    hypercar: tuple[Recommendation, Recommendation, Recommendation]
```

Update `_car()`, `_recommend()`, and `_circuit()` signatures and constructor calls in the same field order. Do not introduce a generic translation dictionary or dynamic attribute lookup.

- [ ] **Step 4: Add the complete Chinese copy**

Translate every current English `strength`, `caution`, `fit`, `character`, `challenge`, and `advice` string directly beside its English source. Use natural Chinese driving language, preserve meaning, and avoid fastest-lap promises.

Use these exact location values:

```python
LOCATION_ZH = {
    "bahrain": "萨基尔，巴林（Sakhir, Bahrain）",
    "barcelona": "蒙特梅洛，西班牙（Montmeló, Spain）",
    "le-mans": "勒芒，法国（Le Mans, France）",
    "paul-ricard": "勒卡斯泰莱，法国（Le Castellet, France）",
    "cota": "奥斯汀，美国（Austin, United States）",
    "daytona": "代托纳比奇，美国（Daytona Beach, United States）",
    "fuji": "小山町，日本（Oyama, Japan）",
    "imola": "伊莫拉，意大利（Imola, Italy）",
    "interlagos": "圣保罗，巴西（São Paulo, Brazil）",
    "lusail": "卢赛尔，卡塔尔（Lusail, Qatar）",
    "monza": "蒙扎，意大利（Monza, Italy）",
    "portimao": "波尔蒂芒，葡萄牙（Portimão, Portugal）",
    "sebring": "赛百灵，美国（Sebring, United States）",
    "silverstone-international": "银石，英国（Silverstone, United Kingdom）",
    "spa": "斯塔沃洛，比利时（Stavelot, Belgium）",
    "laguna-seca": "蒙特雷，美国（Monterey, United States）",
}
```

Pass each literal value into `_circuit()`; do not retain `LOCATION_ZH` as a runtime lookup unless it materially improves readability. Include these exact term forms where they naturally belong:

- `制动稳定性（braking stability）`
- `轮胎负荷（tyre load）`
- `牵引力（traction）`
- `空气动力学效率（aero efficiency）`
- `操作窗口（operating window）`
- `循迹刹车（trail braking）`
- `路肩（kerb）`
- `调校（setup）`

- [ ] **Step 5: Extend validation and verify GREEN**

Update the existing non-blank checks:

```python
if not all((
    car.name.strip(),
    car.strength.strip(),
    car.caution.strip(),
    car.strength_zh.strip(),
    car.caution_zh.strip(),
)):
    raise ValueError(f"blank car copy: {car.slug}")

if not all((
    circuit.name.strip(),
    circuit.location.strip(),
    circuit.location_zh.strip(),
    circuit.length_km.strip(),
    circuit.character.strip(),
    circuit.character_zh.strip(),
    circuit.challenge.strip(),
    circuit.challenge_zh.strip(),
    circuit.advice.strip(),
    circuit.advice_zh.strip(),
)):
    raise ValueError(f"blank circuit copy: {circuit.slug}")

if not recommendation.fit.strip() or not recommendation.fit_zh.strip():
    raise ValueError(f"blank recommendation copy: {circuit.slug}")
```

Run:

```bash
venv/bin/python -m unittest tests.test_lmu_guide.LmuGuideDataTests -v
venv/bin/python -m unittest tests.test_lmu_guide -v
```

Expected: all LMU data and asset tests pass.

- [ ] **Step 6: Commit bilingual data**

```bash
git add lmu_guide_data.py tests/test_lmu_guide.py
git commit -m "feat: add bilingual LMU guide copy"
```

---

### Task 2: Render the Accessible Language Slider and Both Copy Variants

**Files:**
- Modify: `templates/kozekilmu_tracks.html:1-105`
- Modify: `static/css/kozekilmu_tracks.css:9-562`
- Modify: `tests/test_lmu_guide.py:83-205`

**Interfaces:**
- Consumes: Task 1's `*_zh` fields and existing `available_images` set.
- Produces: root `data-guide-language`, `[data-guide-copy]` variants, `#guide-language-toggle`, translated-attribute metadata, and CSS contracts consumed by Task 3.

- [ ] **Step 1: Add failing route and presentation tests**

Add or update tests to assert:

```python
def test_guide_server_renders_chinese_default_and_complete_language_control(self):
    html = self.client.get("/kozekilmu/tracks").get_data(as_text=True)
    self.assertIn('<html lang="zh-CN" data-guide-language="zh"', html)
    self.assertIn('id="guide-language-toggle"', html)
    self.assertIn('type="checkbox"', html)
    self.assertIn('data-guide-copy="zh"', html)
    self.assertIn('data-guide-copy="en"', html)
    self.assertIn("LMU 赛道指南", html)
    self.assertIn("LMU Circuit Guide", html)
    self.assertIn(guide.CIRCUITS[0].character_zh, html)
    self.assertIn(guide.CIRCUITS[0].character, html)
    self.assertIn(guide.CIRCUITS[0].lmgt3[0].fit_zh, html)
    self.assertIn(guide.CIRCUITS[0].lmgt3[0].fit, html)

def test_language_metadata_covers_dynamic_accessible_attributes(self):
    html = self.client.get("/kozekilmu/tracks").get_data(as_text=True)
    self.assertIn('data-title-zh="LMU 赛道指南 - GTD"', html)
    self.assertIn('data-title-en="LMU Circuit Guide - GTD"', html)
    self.assertIn('data-i18n-alt-zh="Bahrain 赛道"', html)
    self.assertIn('data-i18n-alt-en="Bahrain circuit"', html)
    self.assertIn('data-i18n-aria-label-zh=', html)
    self.assertIn('data-i18n-aria-label-en=', html)

def test_language_slider_css_is_responsive_accessible_and_fail_open(self):
    css = CSS_PATH.read_text(encoding="utf-8")
    self.assertIn('html[data-guide-language="zh"] [data-guide-copy="zh"]', css)
    self.assertIn('html[data-guide-language="en"] [data-guide-copy="en"]', css)
    self.assertRegex(css, r"\.language-toggle[^}]*min-height:\s*44px")
    self.assertIn(".language-toggle input:focus-visible", css)
    self.assertRegex(css, r"@media\s*\(max-width:\s*560px\)")
    self.assertNotIn("display: none", css[css.find("@media (prefers-reduced-motion: reduce)"):])
```

Also update old assertions that expect only Chinese title/link text so they accept the default Chinese variant without forbidding English copy.

- [ ] **Step 2: Run route/presentation tests to verify RED**

Run:

```bash
venv/bin/python -m unittest \
  tests.test_lmu_guide.LmuGuideRouteTests \
  tests.test_lmu_guide.LmuGuidePresentationTests -v
```

Expected: failures for missing language control, English variants, metadata, and slider CSS.

- [ ] **Step 3: Add a small Jinja copy macro and Chinese-default root state**

At the beginning of the template, define:

```jinja2
{% macro guide_copy(zh, en) -%}
<span data-guide-copy="zh">{{ zh }}</span><span data-guide-copy="en">{{ en }}</span>
{%- endmacro %}
```

Change the root element to:

```jinja2
<html lang="zh-CN"
      data-guide-language="zh"
      data-title-zh="LMU 赛道指南 - GTD"
      data-title-en="LMU Circuit Guide - GTD">
```

Keep `<title>LMU 赛道指南 - GTD</title>` as the no-JavaScript default.

- [ ] **Step 4: Add the native checkbox slider to the topbar**

Insert it before the return link:

```jinja2
<label class="language-toggle" for="guide-language-toggle">
  <span lang="zh-CN">中文</span>
  <input id="guide-language-toggle"
         type="checkbox"
         data-i18n-aria-label-zh="切换为英文"
         data-i18n-aria-label-en="Switch to Chinese"
         aria-label="切换为英文">
  <span class="language-toggle-track" aria-hidden="true">
    <span class="language-toggle-thumb"></span>
  </span>
  <span lang="en">EN</span>
</label>
```

The checkbox remains unchecked for Chinese and checked for English.

- [ ] **Step 5: Render both variants for every visible string**

Use `guide_copy()` for page chrome and textual copy. Required static pairs include:

```text
返回下载 | Back to downloads
冠军档案 | Victory archive
赛道指南 | Circuit guide
LE MANS ULTIMATE / 只读指南 | LE MANS ULTIMATE / READ-ONLY GUIDE
LMU 赛道指南 | LMU Circuit Guide
以赛道特性为起点，整理 LMGT3 与 Hypercar 的三台可尝试车型。 | Start with each circuit's character and compare three approachable LMGT3 and Hypercar choices.
资料更新： | Updated:
查看车型建议 | View car recommendations
LMU 官方赛道资料 | Official LMU circuit page
LMU 官方车型资料 | Official LMU car page
官方赛道图片暂缺 | Official circuit image unavailable
官方车型图片暂缺 | Official car image unavailable
```

Render data pairs exactly as follows:

```jinja2
<p class="circuit-meta">
  {{ guide_copy(circuit.location_zh, circuit.location) }} · {{ circuit.length_km }} km{% if circuit.is_dlc %} · DLC{% endif %}
</p>
<p>{{ guide_copy(circuit.character_zh, circuit.character) }}</p>
<p>{{ guide_copy(circuit.challenge_zh, circuit.challenge) }}</p>
<p>{{ guide_copy(circuit.advice_zh, circuit.advice) }}</p>
```

For recommendations:

```jinja2
<p>{{ guide_copy(recommendation.fit_zh, recommendation.fit) }}</p>
<p>
  <span data-guide-copy="zh">{{ car.strength_zh }}；注意：{{ car.caution_zh }}。</span>
  <span data-guide-copy="en">{{ car.strength }}; caution: {{ car.caution }}.</span>
</p>
```

Give images, placeholders, navigation, the circuit-list section, and the language input both `data-i18n-*-zh` and `data-i18n-*-en` values while leaving the real `alt`/`aria-label` value Chinese by default. Translate the complete footer, including official index link labels and the BoP/version disclaimer.

- [ ] **Step 6: Add fail-open language and slider CSS**

Add near the base element rules:

```css
[data-guide-copy] {
  display: none;
}

html[data-guide-language="zh"] [data-guide-copy="zh"],
html[data-guide-language="en"] [data-guide-copy="en"] {
  display: revert;
}
```

Add the slider styles without changing theme tokens:

```css
.language-toggle {
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  gap: 7px;
  color: var(--muted-strong);
  font-size: 11px;
  letter-spacing: .04em;
  cursor: pointer;
  user-select: none;
}

.language-toggle input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}

.language-toggle-track {
  position: relative;
  width: 42px;
  height: 22px;
  border: 1px solid var(--border-strong);
  border-radius: 999px;
  background: rgba(15, 23, 42, .72);
  transition: border-color .18s ease, background-color .18s ease;
}

.language-toggle-thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 12px rgba(0, 161, 155, .38);
  transition: transform .18s ease;
}

.language-toggle input:checked + .language-toggle-track .language-toggle-thumb {
  transform: translateX(18px);
}

.language-toggle input:focus-visible + .language-toggle-track {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}
```

Under 560px, reduce the visual gaps and track width only; keep the label's `min-height: 44px`. Under reduced motion, the existing transition-duration override applies and content remains visible.

- [ ] **Step 7: Verify rendered bilingual contracts and commit**

Run:

```bash
venv/bin/python -m unittest tests.test_lmu_guide tests.test_kozekilmu tests.test_motion_system -v
git diff --check
```

Expected: all focused tests pass; no downloader behavior changes.

Commit:

```bash
git add templates/kozekilmu_tracks.html static/css/kozekilmu_tracks.css tests/test_lmu_guide.py
git commit -m "feat: render LMU language switch"
```

---

### Task 3: Implement Guarded Language Persistence and Live Attribute Updates

**Files:**
- Create: `static/js/lmu_guide_language.js`
- Create: `tests/test_lmu_guide_language.py`
- Create: `tests/js/lmu_guide_language_harness.js`
- Modify: `templates/kozekilmu_tracks.html:1-110`
- Modify: `tests/test_lmu_guide.py:100-205`

**Interfaces:**
- Consumes: `#guide-language-toggle`, root `data-title-*`, `[data-i18n-alt-*]`, `[data-i18n-aria-label-*]`, and CSS `data-guide-language` selectors from Task 2.
- Produces: `window.LmuGuideLanguage.init(): void` and `window.LmuGuideLanguage.apply(language: "zh" | "en", persist?: boolean): "zh" | "en"` for deterministic behavior tests and safe reinitialization.

- [ ] **Step 1: Add failing JavaScript asset and behavior tests**

Create `tests/test_lmu_guide_language.py` with:

```python
import subprocess
import unittest
from pathlib import Path

import app as web_app


JS_PATH = Path("static/js/lmu_guide_language.js")
HARNESS_PATH = Path("tests/js/lmu_guide_language_harness.js")


class LmuGuideLanguageTests(unittest.TestCase):
    def test_page_serves_only_the_dedicated_language_runtime_after_motion(self):
        client = web_app.app.test_client()
        html = client.get("/kozekilmu/tracks").get_data(as_text=True)
        self.assertIn('<script defer src="/static/js/motion.js"></script>', html)
        self.assertIn('<script defer src="/static/js/lmu_guide_language.js"></script>', html)
        self.assertLess(html.index("motion.js"), html.index("lmu_guide_language.js"))
        self.assertNotIn("onchange=", html)
        self.assertNotIn("onclick=", html)

    def test_language_runtime_defaults_persists_updates_and_deduplicates(self):
        result = subprocess.run(
            ["node", str(HARNESS_PATH)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_language_script_has_valid_javascript(self):
        result = subprocess.run(
            ["node", "--check", str(JS_PATH)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
```

Create `tests/js/lmu_guide_language_harness.js` with the complete behavior harness:

```javascript
"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync("static/js/lmu_guide_language.js", "utf8");

class Element {
  constructor(attributes = {}) {
    this.attributes = { ...attributes };
    this.dataset = {};
    this.listeners = {};
    this.checked = false;
    this.lang = "";
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  addEventListener(name, listener) {
    (this.listeners[name] ||= []).push(listener);
  }
}

function boot({ stored = null, throwGet = false, throwSet = false } = {}) {
  const root = new Element({
    "data-title-zh": "LMU 赛道指南 - GTD",
    "data-title-en": "LMU Circuit Guide - GTD",
  });
  const image = new Element({
    "data-i18n-alt-zh": "Bahrain 赛道",
    "data-i18n-alt-en": "Bahrain circuit",
  });
  const navigation = new Element({
    "data-i18n-aria-label-zh": "LMU 彩蛋分页",
    "data-i18n-aria-label-en": "LMU easter egg pages",
  });
  const toggle = new Element({
    "data-i18n-aria-label-zh": "切换为英文",
    "data-i18n-aria-label-en": "Switch to Chinese",
  });
  const values = new Map();
  if (stored !== null) values.set("gtd_lmu_guide_language_v1", stored);

  const localStorage = {
    getItem(key) {
      if (throwGet) throw new Error("blocked read");
      return values.get(key) ?? null;
    },
    setItem(key, value) {
      if (throwSet) throw new Error("blocked write");
      values.set(key, value);
    },
  };

  const document = {
    documentElement: root,
    readyState: "complete",
    title: "",
    querySelector(selector) {
      return selector === "#guide-language-toggle" ? toggle : null;
    },
    querySelectorAll(selector) {
      if (selector.startsWith("[data-i18n-alt-")) return [image];
      if (selector.startsWith("[data-i18n-aria-label-")) return [navigation, toggle];
      return [];
    },
    addEventListener() {},
  };
  const window = { localStorage };
  vm.runInNewContext(source, { document, window, console });
  return { root, image, navigation, toggle, values, document, api: window.LmuGuideLanguage };
}

const initial = boot();
assert.strictEqual(initial.root.dataset.guideLanguage, "zh");
assert.strictEqual(initial.root.lang, "zh-CN");
assert.strictEqual(initial.document.title, "LMU 赛道指南 - GTD");
assert.strictEqual(initial.image.getAttribute("alt"), "Bahrain 赛道");
assert.strictEqual(initial.navigation.getAttribute("aria-label"), "LMU 彩蛋分页");
assert.strictEqual(initial.toggle.checked, false);

initial.toggle.checked = true;
initial.toggle.listeners.change[0]();
assert.strictEqual(initial.root.dataset.guideLanguage, "en");
assert.strictEqual(initial.root.lang, "en");
assert.strictEqual(initial.document.title, "LMU Circuit Guide - GTD");
assert.strictEqual(initial.image.getAttribute("alt"), "Bahrain circuit");
assert.strictEqual(initial.navigation.getAttribute("aria-label"), "LMU easter egg pages");
assert.strictEqual(initial.values.get("gtd_lmu_guide_language_v1"), "en");

initial.api.init();
initial.api.init();
assert.strictEqual(initial.toggle.listeners.change.length, 1);

const restored = boot({ stored: "en" });
assert.strictEqual(restored.root.dataset.guideLanguage, "en");
assert.strictEqual(restored.toggle.checked, true);

for (const setup of [{ stored: "invalid" }, { throwGet: true }]) {
  const fallback = boot(setup);
  assert.strictEqual(fallback.root.dataset.guideLanguage, "zh");
  assert.strictEqual(fallback.toggle.checked, false);
}

const blockedWrite = boot({ throwSet: true });
blockedWrite.toggle.checked = true;
blockedWrite.toggle.listeners.change[0]();
assert.strictEqual(blockedWrite.root.dataset.guideLanguage, "en");
```


- [ ] **Step 2: Run language tests to verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_lmu_guide_language -v
```

Expected: failures because the script and template reference do not exist.

- [ ] **Step 3: Implement the dependency-free language runtime**

Create `static/js/lmu_guide_language.js` using this exact behavior:

```javascript
(() => {
  "use strict";

  const STORAGE_KEY = "gtd_lmu_guide_language_v1";
  const VALID_LANGUAGES = new Set(["zh", "en"]);
  const ATTRIBUTE_NAMES = ["alt", "aria-label"];
  const root = document.documentElement;

  function normalize(language) {
    return VALID_LANGUAGES.has(language) ? language : "zh";
  }

  function readStoredLanguage() {
    try {
      return normalize(window.localStorage.getItem(STORAGE_KEY));
    } catch (_error) {
      return "zh";
    }
  }

  function storeLanguage(language) {
    try {
      window.localStorage.setItem(STORAGE_KEY, language);
    } catch (_error) {
      // Storage is optional; the visible language has already changed.
    }
  }

  function applyTranslatedAttributes(language) {
    for (const attribute of ATTRIBUTE_NAMES) {
      const selector = `[data-i18n-${attribute}-${language}]`;
      for (const element of document.querySelectorAll(selector)) {
        element.setAttribute(
          attribute,
          element.getAttribute(`data-i18n-${attribute}-${language}`),
        );
      }
    }
  }

  function apply(language, persist = false) {
    const selected = normalize(language);
    root.dataset.guideLanguage = selected;
    root.lang = selected === "zh" ? "zh-CN" : "en";
    document.title = root.getAttribute(`data-title-${selected}`);
    applyTranslatedAttributes(selected);

    const toggle = document.querySelector("#guide-language-toggle");
    if (toggle) {
      toggle.checked = selected === "en";
    }
    if (persist) {
      storeLanguage(selected);
    }
    return selected;
  }

  function init() {
    const toggle = document.querySelector("#guide-language-toggle");
    apply(readStoredLanguage());
    if (!toggle || toggle.dataset.languageBound === "true") {
      return;
    }
    toggle.dataset.languageBound = "true";
    toggle.addEventListener("change", () => {
      apply(toggle.checked ? "en" : "zh", true);
    });
  }

  window.LmuGuideLanguage = { apply, init };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
```

Do not add timers, fetches, mutation observers, animation loops, or dependencies.

- [ ] **Step 4: Load the runtime after shared motion**

At the template end, keep motion first:

```jinja2
<script defer src="/static/js/motion.js"></script>
<script defer src="/static/js/lmu_guide_language.js"></script>
```

- [ ] **Step 5: Run behavior and regression tests to verify GREEN**

Run:

```bash
venv/bin/python -m unittest tests.test_lmu_guide_language -v
venv/bin/python -m unittest tests.test_lmu_guide tests.test_kozekilmu tests.test_motion_system -v
node --check static/js/lmu_guide_language.js
git diff --check
```

Expected: language behavior and all existing LMU/motion contracts pass.

- [ ] **Step 6: Commit the language runtime**

```bash
git add static/js/lmu_guide_language.js templates/kozekilmu_tracks.html tests/test_lmu_guide_language.py tests/js/lmu_guide_language_harness.js tests/test_lmu_guide.py
git commit -m "feat: persist LMU guide language"
```

---

### Task 4: Full Regression and Responsive Language QA

**Files:**
- Modify if a verified defect requires it: `lmu_guide_data.py`
- Modify if a verified defect requires it: `templates/kozekilmu_tracks.html`
- Modify if a verified defect requires it: `static/css/kozekilmu_tracks.css`
- Modify if a verified defect requires it: `static/js/lmu_guide_language.js`
- Modify if a verified defect requires it: `tests/test_lmu_guide.py`
- Modify if a verified defect requires it: `tests/test_lmu_guide_language.py`
- Modify if a verified defect requires it: `tests/js/lmu_guide_language_harness.js`

**Interfaces:**
- Consumes: all bilingual data, rendering, slider, and persistence behavior from Tasks 1-3.
- Produces: a verified Chinese-default and remembered-English LMU circuit guide with downloader behavior unchanged.

- [ ] **Step 1: Run the complete automated suite and static checks**

Run:

```bash
venv/bin/python -m unittest discover -s tests -v
venv/bin/python -m compileall -q app.py lmu_guide_data.py tests
node --check static/js/motion.js
node --check static/js/lmu_guide_language.js
git diff --check
rg -n 'on(?:click|change|error|load)=' templates/kozekilmu_tracks.html static/js/lmu_guide_language.js
```

Expected: all platform-independent tests pass, only the two existing Windows-only tests skip, compilation/syntax/diff checks exit 0, and the inline-handler scan returns no matches.

- [ ] **Step 2: Start only this project's QA service**

First run:

```bash
lsof -nP -iTCP:8233 -sTCP:LISTEN
```

If another process owns the port, identify its command and working directory; do not stop it. Otherwise start:

```bash
venv/bin/python app.py
```

Record the PID created by this command.

- [ ] **Step 3: Verify desktop, mobile, keyboard, storage, and failure behavior**

At `/kozekilmu/tracks`, verify:

- first visit with the storage key removed shows Chinese, Chinese browser title, unchecked slider, and Chinese accessible attributes;
- the slider sits before the return link and avatar, is keyboard operable, and has a visible focus ring;
- switching to English updates every visible region, title, `lang`, `alt`, and `aria-label` without changing `scrollY` or closing an open recommendation `<details>`;
- reload restores English; switching back restores and persists Chinese;
- a malformed key and blocked storage fall back to Chinese without console errors;
- 1440px retains two columns; 390px uses one column and the topbar has no horizontal overflow;
- Chinese terminology includes useful English parentheticals without turning each sentence into duplicated prose;
- reduced motion keeps both switch functionality and all active-language content visible;
- all 16 circuit images, recommendation images, CSS, and both JS files return 200 with expected MIME types.

Use an available browser controller or existing browser dependency if present. Do not install a new dependency solely for QA. If no browser control exists, document that limitation and verify served HTML, CSS media contracts, JS behavior harness, HTTP resources, and storage logic instead of claiming screenshot or physical-keyboard evidence.

- [ ] **Step 4: Stop only the QA process and verify cleanup**

Send Ctrl+C to the exact PID started in Step 2, then run:

```bash
lsof -nP -iTCP:8233 -sTCP:LISTEN
git status --short
```

Expected: no GTD listener remains on 8233 and only intentional implementation changes exist. Do not modify or remove files under `downloads/`.

- [ ] **Step 5: Commit only verified QA corrections**

If QA exposes a defect, add a failing regression test, verify RED, apply the smallest fix, verify GREEN, and commit only those files:

```bash
git add lmu_guide_data.py templates/kozekilmu_tracks.html static/css/kozekilmu_tracks.css static/js/lmu_guide_language.js tests/test_lmu_guide.py tests/test_lmu_guide_language.py tests/js/lmu_guide_language_harness.js
git commit -m "fix: refine LMU language toggle QA"
```

If QA finds no defect, do not create an empty commit.

