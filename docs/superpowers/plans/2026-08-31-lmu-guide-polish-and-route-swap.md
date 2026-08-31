# LMU Guide Polish and Route Swap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the circuit guide the default easter-egg page, guarantee English-only English mode, and bound circuit-card reveal delay without changing shared downloader or motion behavior.

**Architecture:** Swap only the two Flask route paths while preserving semantic endpoint names, then update the homepage mascot expectation. Keep one server-rendered bilingual template and strengthen its language boundaries with rendered-DOM and data audits. Fix reveal latency locally by assigning each circuit card a row-local order; do not edit the shared motion runtime.

**Tech Stack:** Python 3, Flask/Jinja2, unittest, HTMLParser, HTML/CSS, existing vanilla JavaScript language runtime.

## Global Constraints

- `/kozekilmu` must render the circuit guide; `/kozekilmu/tracks` must render the victory archive.
- Both existing URLs remain valid; add no redirect or new route.
- English mode contains only English-visible copy; Chinese mode may retain English proper nouns or parenthetical technical terms.
- Circuit-card reveal order is limited to `0` or `1`; retain the existing 680ms animation.
- Do not modify `static/js/motion.js`, downloader logic, queue logic, APIs, assets, or dependencies.
- Use TDD and create one local commit per implementation task.

---

### Task 1: Swap the two easter-egg routes

**Files:**
- Modify: `app.py:107-121`
- Modify: `templates/index.html:203`
- Modify: `tests/test_kozekilmu.py`
- Modify: `tests/test_lmu_guide.py`
- Modify: `tests/test_lmu_guide_language.py`
- Modify: `tests/test_motion_system.py`

**Interfaces:**
- Consumes: existing Flask endpoints `kozekilmu` and `kozekilmu_tracks` used by both page templates.
- Produces: `url_for("kozekilmu_tracks") == "/kozekilmu"` for the guide and `url_for("kozekilmu") == "/kozekilmu/tracks"` for the archive.

- [ ] **Step 1: Write failing route and mascot tests**

Update route assertions so the guide test requests `/kozekilmu` and the victory test requests `/kozekilmu/tracks`. In `tests/test_kozekilmu.py`, require the homepage icon to keep `href="/kozekilmu"` but describe the circuit guide:

```python
def test_task_mascot_opens_circuit_guide_accessibly(self):
    html = self.client.get("/").get_data(as_text=True)
    self.assertIn('class="icon" href="/kozekilmu"', html)
    self.assertIn('aria-label="打开隐藏的 LMU 赛道指南"', html)

def test_swapped_victory_route_renders_archive_and_active_navigation(self):
    html = self.client.get("/kozekilmu/tracks").get_data(as_text=True)
    self.assertIn("LMU 富士赛道 GT3 铜赛拿了冠军", html)
    self.assertIn('href="/kozekilmu/tracks" aria-current="page"', html)
    self.assertIn('href="/kozekilmu"', html)
```

In `tests/test_lmu_guide.py`, require `/kozekilmu` to render the guide and its guide link to be active. Also update `tests/test_lmu_guide_language.py` to request the new guide URL, and update archive-specific `tests/test_motion_system.py` requests to `/kozekilmu/tracks`:

```python
def test_default_easter_route_renders_circuit_guide(self):
    html = self.client.get("/kozekilmu").get_data(as_text=True)
    self.assertIn("LMU 赛道指南", html)
    self.assertIn('href="/kozekilmu" aria-current="page"', html)
    self.assertIn('href="/kozekilmu/tracks"', html)
```

- [ ] **Step 2: Run RED tests**

Run:

```bash
/Users/markyang/Projects/GTD/venv/bin/python -m unittest \
  tests.test_kozekilmu.KozekiLmuEasterEggTests.test_task_mascot_opens_circuit_guide_accessibly \
  tests.test_kozekilmu.KozekiLmuEasterEggTests.test_swapped_victory_route_renders_archive_and_active_navigation \
  tests.test_lmu_guide.LmuGuideRouteTests.test_default_easter_route_renders_circuit_guide -v
```

Expected: FAIL because `/kozekilmu` still renders the archive and the mascot ARIA label still names the champion page.

- [ ] **Step 3: Swap route decorators and update the mascot label**

Keep semantic endpoint names used by `url_for`, changing only route paths:

```python
@app.route("/kozekilmu/tracks")
def kozekilmu():
    """Render the hidden LMU Fuji GT3 victory archive."""
    return render_template("kozekilmu.html")


@app.route("/kozekilmu")
def kozekilmu_tracks():
    """Render the read-only LMU circuit and car recommendation guide."""
    return render_template(
        "kozekilmu_tracks.html",
        cars=CARS,
        circuits=CIRCUITS,
        guide_updated=GUIDE_UPDATED,
        available_images=_available_guide_images(CIRCUITS, CARS.values()),
    )
```

Change the homepage link to the semantic guide endpoint and update its label:

```jinja2
<a class="icon" href="{{ url_for('kozekilmu_tracks') }}" aria-label="打开隐藏的 LMU 赛道指南">
```

The existing navigation templates already use the semantic endpoint names, so their URL and active-state output swaps automatically. Do not manually hardcode URLs.

- [ ] **Step 4: Run route-focused and page tests**

Run:

```bash
/Users/markyang/Projects/GTD/venv/bin/python -m unittest tests.test_kozekilmu tests.test_lmu_guide tests.test_motion_system -v
```

Expected: all tests pass after updating every old route expectation to the new contract.

- [ ] **Step 5: Commit**

```bash
git add app.py templates/index.html tests/test_kozekilmu.py tests/test_lmu_guide.py tests/test_lmu_guide_language.py tests/test_motion_system.py
git commit -m "feat: make LMU circuit guide the default easter page"
```

---

### Task 2: Enforce English-only English mode

**Files:**
- Modify: `templates/kozekilmu_tracks.html:29`
- Modify: `tests/test_lmu_guide.py`

**Interfaces:**
- Consumes: `guide_copy(zh, en)` and the existing `data-guide-copy` CSS/runtime contract.
- Produces: a language-control label that renders `中文` for `zh` and `ZH` for `en`, plus automated English data and visible-body purity checks.

- [ ] **Step 1: Add a rendered-body language audit helper and failing tests**

Add `HTMLParser` import and a parser that ignores `head`, `script`, `style`, and ancestors with `data-guide-copy="zh"`, then captures Han text from every other body text node:

```python
from html.parser import HTMLParser

HAN = re.compile(r"[\u3400-\u9fff]")


class _EnglishVisibleCopyParser(HTMLParser):
    VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.han_text = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID_ELEMENTS:
            self.stack.append((tag, dict(attrs)))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        if not HAN.search(data):
            return
        if any(tag in {"head", "script", "style"} for tag, _ in self.stack):
            return
        if any(attrs.get("data-guide-copy") == "zh" for _, attrs in self.stack):
            return
        self.han_text.append(" ".join(data.split()))
```

Add tests:

```python
def test_english_visible_body_has_no_han_copy(self):
    parser = _EnglishVisibleCopyParser()
    parser.feed(self.client.get("/kozekilmu").get_data(as_text=True))
    self.assertEqual(parser.han_text, [])

def test_all_english_guide_data_is_han_free(self):
    english = []
    for car in guide.CARS.values():
        english.extend((car.name, car.car_class, car.strength, car.caution))
    for circuit in guide.CIRCUITS:
        english.extend((circuit.name, circuit.location, circuit.character, circuit.challenge, circuit.advice))
        english.extend(item.fit for item in (*circuit.lmgt3, *circuit.hypercar))
    self.assertEqual([value for value in english if HAN.search(value)], [])
```

- [ ] **Step 2: Run RED tests**

Run:

```bash
/Users/markyang/Projects/GTD/venv/bin/python -m unittest \
  tests.test_lmu_guide.LmuGuideRouteTests.test_english_visible_body_has_no_han_copy \
  tests.test_lmu_guide.LmuGuideDataTests.test_all_english_guide_data_is_han_free -v
```

Expected: the body audit FAILS with `中文`; the English data audit passes and becomes a regression boundary.

- [ ] **Step 3: Wrap the language label**

Replace the fixed label with bilingual copy:

```jinja2
{{ guide_copy("中文", "ZH") }}
```

Do not modify source links, caution text, footer, alt text, or ARIA metadata unless the new audit exposes a real English-visible Han leak.

- [ ] **Step 4: Run language and page tests**

Run:

```bash
/Users/markyang/Projects/GTD/venv/bin/python -m unittest tests.test_lmu_guide tests.test_lmu_guide_language -v
node tests/js/lmu_guide_language_harness.js
```

Expected: all tests pass and the harness exits 0.

- [ ] **Step 5: Commit**

```bash
git add templates/kozekilmu_tracks.html tests/test_lmu_guide.py
git commit -m "fix: keep LMU English mode English-only"
```

---

### Task 3: Bound circuit reveal delay and perform final verification

**Files:**
- Modify: `templates/kozekilmu_tracks.html:68`
- Modify: `tests/test_lmu_guide.py`

**Interfaces:**
- Consumes: shared `data-motion-group` and `data-motion-order` attributes interpreted by `static/js/motion.js`.
- Produces: 16 circuit cards in group `lmu-circuits`, each with an explicit numeric order of `0` or `1`.

- [ ] **Step 1: Add a failing bounded-order regression test**

Use a rendered-HTML regex scoped to article start tags:

```python
def test_circuit_reveal_stagger_is_bounded_per_grid_row(self):
    html = self.client.get("/kozekilmu").get_data(as_text=True)
    cards = re.findall(r'<article class="circuit-card"[^>]*>', html)
    self.assertEqual(len(cards), 16)
    self.assertTrue(all('data-motion-group="lmu-circuits"' in card for card in cards))
    orders = [re.search(r'data-motion-order="(\d+)"', card).group(1) for card in cards]
    self.assertEqual(orders, [str(index % 2) for index in range(16)])
    self.assertLessEqual(max(map(int, orders)), 1)
```

- [ ] **Step 2: Run RED test**

Run:

```bash
/Users/markyang/Projects/GTD/venv/bin/python -m unittest \
  tests.test_lmu_guide.LmuGuidePresentationTests.test_circuit_reveal_stagger_is_bounded_per_grid_row -v
```

Expected: FAIL because cards currently have neither the LMU group nor explicit orders.

- [ ] **Step 3: Add page-local reveal attributes**

Change only the circuit article start tag:

```jinja2
<article class="circuit-card"
         id="{{ circuit.slug }}"
         data-motion-reveal
         data-motion-group="lmu-circuits"
         data-motion-order="{{ loop.index0 % 2 }}"
         data-motion-surface
         data-motion-tilt-strength="0.18">
```

Do not edit `static/js/motion.js` or `static/css/motion.css`.

- [ ] **Step 4: Run focused verification**

Run:

```bash
/Users/markyang/Projects/GTD/venv/bin/python -m unittest \
  tests.test_lmu_guide tests.test_lmu_guide_language tests.test_kozekilmu tests.test_motion_system -v
node --check static/js/motion.js
node --check static/js/lmu_guide_language.js
node tests/js/lmu_guide_language_harness.js
git diff --check
```

Expected: all tests pass, all Node commands exit 0, and the diff check emits no output.

- [ ] **Step 5: Commit reveal fix**

```bash
git add templates/kozekilmu_tracks.html tests/test_lmu_guide.py
git commit -m "perf: bound LMU circuit reveal delay"
```

- [ ] **Step 6: Run full project verification**

Run:

```bash
/Users/markyang/Projects/GTD/venv/bin/python -m unittest discover -s tests
/Users/markyang/Projects/GTD/venv/bin/python -m compileall -q app.py lmu_guide_data.py tests
git status --short
git diff --check d4f9f70..HEAD
lsof -nP -iTCP:8233 -sTCP:LISTEN
```

Expected: 0 failures; only the two existing Windows-only tests may skip; compile and diff checks exit 0; worktree is clean; no 8233 listener remains.

- [ ] **Step 7: Review the whole branch**

Review `d4f9f70..HEAD` against both LMU bilingual specifications. Fix every Critical or Important finding in one scoped commit, rerun the full verification commands, and request re-review before integration.
