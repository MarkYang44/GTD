# Apple-Inspired Motion System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one restrained, dependency-free motion system to the homepage, usage guide, and Kozeki Ui hidden page without changing downloader behavior, layout, copy, or service configuration.

**Architecture:** `static/css/motion.css` defines shared motion tokens and opt-in visual states, while `static/js/motion.js` owns one page-level requestAnimationFrame scheduler, reveal observation, desktop pointer surfaces, scroll depth, number interpolation, and visibility cleanup. Pages opt in with data attributes; downloader logic stays in `static/js/index.js`, and the guide consumes a shared scroll-frame event for its table-of-contents state rather than creating a second animation loop.

**Tech Stack:** HTML5, CSS custom properties, vanilla JavaScript, IntersectionObserver, requestAnimationFrame, Flask/Jinja, Python unittest, Node syntax checking.

## Global Constraints

- Do not add GSAP, Three.js, WebGL, new image assets, npm packages, Python dependencies, or network-loaded animation code.
- Preserve the dark theme, Petronas green accent, typography, page layout, copy, download/queue behavior, guide content, hidden-page links, and port `8233`.
- Animate only `transform`, `opacity`, finite entrance `filter`, and CSS custom properties; reveal travel is at most `18px`, blur at most `8px`, tilt at most approximately `0.6deg`, and parallax normally `4-12px`.
- Pointer sheen and tilt run only for `(hover: hover) and (pointer: fine)`, never on touch/coarse pointers, when reduced motion is requested, or while the document is hidden.
- `prefers-reduced-motion: reduce` must render all content immediately and disable reveals, parallax, sheen tracking, tilt, and number interpolation.
- Initialization is fail-open: content is visible before JavaScript adds `motion-ready`, and missing browser APIs must leave the site fully usable.
- Use one shared requestAnimationFrame scheduler per page. Do not add timers or permanent idle animation loops.
- Motion overlays use `pointer-events: none`; form controls, selection, focus order, ARIA live regions, links, and hit target geometry must remain unchanged.
- Existing task-item entrance animation stays in `index.css` and is not enrolled in the shared reveal observer.

---

### Task 1: Build the Shared Motion Engine

**Files:**
- Create: `static/css/motion.css`
- Create: `static/js/motion.js`
- Create: `tests/test_motion_system.py`

**Interfaces:**
- Produces CSS attributes: `[data-motion-reveal]`, `[data-motion-group]`, `[data-motion-order]`, `[data-motion-surface]`, `[data-motion-parallax]`, `[data-motion-number]`.
- Produces root states: `.motion-ready`, `.motion-enabled`, `.motion-fine-pointer`, `.motion-reduced`.
- Produces browser API: `window.MotionSystem.refresh(root = document)`, `window.MotionSystem.setNumber(element, value)`, and `window.MotionSystem.destroy()`.
- Produces event: `motion:scroll-frame` on `document`, with `detail: { scrollY, progress }` after each shared scroll frame.
- Consumes no downloader-specific functions or DOM IDs except optional shared `#scroll-progress` and `#topbar` elements.

- [ ] **Step 1: Write failing shared-asset contract tests**

Create `tests/test_motion_system.py` with fixed contracts rather than comparing aliases:

```python
import re
import unittest
from pathlib import Path


CSS_PATH = Path("static/css/motion.css")
JS_PATH = Path("static/js/motion.js")


class SharedMotionAssetTests(unittest.TestCase):
    def test_shared_assets_define_the_declared_motion_contract(self):
        css = CSS_PATH.read_text(encoding="utf-8")
        script = JS_PATH.read_text(encoding="utf-8")

        for attribute in (
            "data-motion-reveal",
            "data-motion-surface",
            "data-motion-parallax",
            "data-motion-number",
        ):
            self.assertIn(attribute, css + script)
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn("(hover: hover) and (pointer: fine)", css)
        self.assertIn('matchMedia("(prefers-reduced-motion: reduce)")', script)
        self.assertIn('matchMedia("(hover: hover) and (pointer: fine)")', script)

    def test_engine_has_one_scheduler_and_no_idle_animation_loop(self):
        script = JS_PATH.read_text(encoding="utf-8")
        self.assertIn("function scheduleFrame", script)
        self.assertIn("requestAnimationFrame(runFrame)", script)
        self.assertNotIn("setInterval(", script)
        self.assertNotIn("setTimeout(", script)
        self.assertRegex(script, r"document\.hidden")
        self.assertRegex(script, r"cancelAnimationFrame\(")

    def test_engine_is_fail_open_and_exposes_lifecycle_api(self):
        css = CSS_PATH.read_text(encoding="utf-8")
        script = JS_PATH.read_text(encoding="utf-8")
        self.assertRegex(css, r"\[data-motion-reveal\]\s*\{[^}]*opacity:\s*1")
        self.assertIn('root.classList.add("motion-ready")', script)
        self.assertIn('root.classList.remove("motion-ready"', script)
        self.assertIn("refresh,", script)
        self.assertIn("destroy,", script)
        self.assertIn('new CustomEvent("motion:scroll-frame"', script)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the contract tests and verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_motion_system -v
```

Expected: FAIL because `motion.css` and `motion.js` do not exist.

- [ ] **Step 3: Implement shared CSS tokens and fail-open states**

Create `static/css/motion.css` with this structure and keep all numeric limits within the global constraints:

```css
:root {
  --motion-fast: 190ms;
  --motion-enter: 680ms;
  --motion-stagger: 70ms;
  --motion-ease: cubic-bezier(.2, .75, .2, 1);
}

[data-motion-reveal] { opacity: 1; transform: none; filter: none; }
.motion-ready.motion-enabled [data-motion-reveal]:not(.motion-visible) {
  opacity: 0;
  transform: translate3d(0, 16px, 0);
  filter: blur(6px);
}
.motion-ready.motion-enabled [data-motion-reveal].motion-visible {
  opacity: 1;
  transform: translate3d(0, 0, 0);
  filter: blur(0);
  transition: opacity var(--motion-enter) var(--motion-ease),
              transform var(--motion-enter) var(--motion-ease),
              filter var(--motion-enter) var(--motion-ease);
  transition-delay: calc(var(--motion-order, 0) * var(--motion-stagger));
}

[data-motion-surface] { --motion-x: 50%; --motion-y: 50%; --motion-rx: 0deg; --motion-ry: 0deg; }
.motion-fine-pointer [data-motion-surface]::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  opacity: var(--motion-sheen-opacity, 0);
  background: radial-gradient(circle at var(--motion-x) var(--motion-y), rgba(0, 161, 155, .11), transparent 38%);
  transition: opacity var(--motion-fast) ease;
}
.motion-fine-pointer [data-motion-surface].motion-surface-active {
  transform: perspective(1200px) rotateX(var(--motion-rx)) rotateY(var(--motion-ry));
}

[data-motion-parallax] {
  transform: translate3d(0, var(--motion-parallax-offset, 0px), 0);
}

@media (prefers-reduced-motion: reduce) {
  [data-motion-reveal], [data-motion-parallax], [data-motion-surface] {
    opacity: 1 !important;
    transform: none !important;
    filter: none !important;
    transition: none !important;
  }
  [data-motion-surface]::before { display: none !important; }
}
```

Add required stacking-context rules so the sheen stays behind surface content and never covers hit targets. Do not change existing page colors or dimensions.

- [ ] **Step 4: Implement one shared JavaScript scheduler**

Create `static/js/motion.js` as an IIFE. Use one `frameId` and dirty flags for scroll and pointer work:

```javascript
(() => {
  "use strict";
  const root = document.documentElement;
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? true;
  const finePointer = window.matchMedia?.("(hover: hover) and (pointer: fine)").matches ?? false;
  let frameId = null;
  let scrollDirty = true;
  let activeSurface = null;
  let pointerEvent = null;

  function scheduleFrame() {
    if (document.hidden || frameId !== null) return;
    frameId = requestAnimationFrame(runFrame);
  }

  function runFrame() {
    frameId = null;
    if (document.hidden) return;
    if (scrollDirty) updateScrollState();
    if (activeSurface && pointerEvent) updateSurface(activeSurface, pointerEvent);
    scrollDirty = false;
    pointerEvent = null;
  }
```

Complete the engine with:

- one-shot IntersectionObserver reveals and `--motion-order` assignment from `data-motion-order` or group order;
- clamped scroll progress and a per-element `--motion-parallax-offset` pixel value; interpret `data-motion-parallax` as a `0..1` strength multiplied by a `12px` maximum, so `0.55` yields at most `6.6px`; do not rely on unsupported CSS multiplication;
- `motion:scroll-frame` dispatch from `updateScrollState()`;
- per-surface pointer enter/move/leave listeners only when `finePointer && !reduced`;
- clamped tilt calculation `[-0.6, 0.6]` degrees and local sheen percentages;
- `setNumber(element, value)` interpolation for `[data-motion-number]`, using the currently visible integer as the next start, cancelling a prior element animation before replacement, and rendering non-integers immediately;
- `visibilitychange` cancellation and surface reset;
- `refresh(rootNode)` for newly added opt-in markup without enrolling task cards;
- `destroy()` that disconnects observers, cancels the frame, removes listeners, neutralizes surfaces, and removes root motion classes;
- a `try/catch` initializer that removes motion classes and marks reveal elements visible when setup fails.

Do not schedule a new frame from inside `runFrame()` unless new input marked work dirty.

- [ ] **Step 5: Run shared tests and syntax checks**

Run:

```bash
venv/bin/python -m unittest tests.test_motion_system -v
node --check static/js/motion.js
```

Expected: all motion contract tests PASS and Node exits 0.

- [ ] **Step 6: Commit the shared engine**

```bash
git add static/css/motion.css static/js/motion.js tests/test_motion_system.py
git commit -m "feat: add shared motion engine"
```

---

### Task 2: Integrate Motion with the Homepage

**Files:**
- Modify: `templates/index.html`
- Modify: `static/css/index.css`
- Modify: `static/js/index.js`
- Modify: `tests/test_web_progress.py`
- Modify: `tests/test_motion_system.py`

**Interfaces:**
- Consumes `motion.css`, deferred `motion.js`, declarative motion attributes, and `window.MotionSystem.setNumber(element, value)` from Task 1.
- Produces homepage opt-ins for hero hierarchy, metrics, cards, collection preview, task panel, and hero decoration.
- Preserves every existing function exported by `Object.assign(window, {...})` in `index.js`.

- [ ] **Step 1: Add failing homepage integration tests**

Extend the Flask asset-delivery test so the rendered homepage must serve both stylesheet and both deferred script resources in stable order:

```python
self.assertEqual(
    stylesheet_urls,
    ["/static/css/index.css", "/static/css/motion.css"],
)
self.assertEqual(
    script_urls,
    ["/static/js/motion.js", "/static/js/index.js"],
)
```

Add a focused markup contract:

```python
def test_homepage_opts_only_stable_surfaces_into_shared_motion(self):
    template = frontend_template_source()
    self.assertIn('id="hero-title" data-motion-reveal', template)
    self.assertIn('id="metric-active" data-motion-number', template)
    self.assertIn('id="metric-queue" data-motion-number', template)
    self.assertIn('id="metric-limit" data-motion-number', template)
    for surface_id in (
        "video-download-card",
        "audio-download-card",
        "collectionPreview",
        "task-card",
    ):
        self.assertRegex(template, rf'id="{surface_id}"[^>]*data-motion-surface')
    self.assertNotRegex(template, r'class="[^"]*task-item[^"]*"[^>]*data-motion-reveal')
```

Add a source boundary test that rejects the old duplicated experience engine in `index.js`:

```python
self.assertNotIn("function initializeExperience", frontend_script_source())
self.assertNotIn("new IntersectionObserver", frontend_script_source())
self.assertNotIn('matchMedia("(pointer: fine)")', frontend_script_source())
self.assertIn("window.MotionSystem?.setNumber(element, nextValue)", frontend_script_source())
```

- [ ] **Step 2: Run homepage tests and verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_web_progress tests.test_motion_system -v
```

Expected: FAIL because the homepage does not load or opt into the shared engine.

- [ ] **Step 3: Add homepage assets and declarative choreography**

In `templates/index.html`:

- load `motion.css` after `index.css`;
- load deferred `motion.js` before deferred `index.js`;
- replace homepage `data-reveal` attributes with `data-motion-reveal`;
- assign explicit group/order values to hero kicker, title, description, metrics, section heading, and the two cards;
- mark the four approved surfaces with `data-motion-surface`;
- mark the orbit with `data-motion-parallax="0.55"`;
- mark Active, Queue, and Limit values with `data-motion-number`.

Example:

```html
<h1 id="hero-title" data-motion-reveal data-motion-group="hero" data-motion-order="1">Capture. Convert. Keep.</h1>
<strong class="metric-value" id="metric-active" data-motion-number>00</strong>
<section class="card" id="video-download-card" data-motion-reveal data-motion-surface>
```

Do not add motion attributes to dynamically rendered task items or form controls.

- [ ] **Step 4: Remove duplicated homepage motion code**

Delete `initializeExperience()` and its fallback block from `static/js/index.js`. In `setOperationalMetrics()`, call `window.MotionSystem?.setNumber(element, nextValue)` and fall back to direct `textContent` assignment when the API is unavailable. Keep queue polling, scroll-independent download behavior, handler exports, task-item animation, directory history, and capability loading unchanged.

Remove shared reveal/pointer rules from `index.css` only after matching rules exist in `motion.css`. Keep homepage-specific orbit, task-enter, metric-flash, responsive layout, and spinner rules. Update orbit/parallax composition so the shared transform variable does not overwrite its existing drift animation; use a non-animated wrapper or compose both translations on distinct elements rather than applying two transforms to one element.

- [ ] **Step 5: Run homepage regression tests**

Run:

```bash
node --check static/js/motion.js
node --check static/js/index.js
venv/bin/python -m unittest tests.test_web_progress tests.test_motion_system tests.test_download_locations -q
```

Expected: PASS, with all existing inline handler export tests unchanged.

- [ ] **Step 6: Commit homepage integration**

```bash
git add templates/index.html static/css/index.css static/js/index.js tests/test_web_progress.py tests/test_motion_system.py
git commit -m "feat: apply shared motion to homepage"
```

---

### Task 3: Integrate Motion with the Usage Guide

**Files:**
- Modify: `templates/guide.html`
- Modify: `tests/test_web_guide.py`
- Modify: `tests/test_motion_system.py`

**Interfaces:**
- Consumes the shared assets and `motion:scroll-frame` event from Task 1.
- Produces staged guide heading, document-section reveals, approved guide surfaces, and decorative parallax.
- Retains the existing generated table of contents and current-section highlighting.

- [ ] **Step 1: Write failing guide integration tests**

Add tests using the real Flask route:

```python
def test_guide_loads_shared_motion_assets_and_declares_reading_safe_motion(self):
    html = self.client.get("/guide").get_data(as_text=True)
    self.assertIn('href="/static/css/motion.css"', html)
    self.assertIn('<script defer src="/static/js/motion.js"></script>', html)
    self.assertIn('class="guide-heading" data-motion-group="guide-hero"', html)
    self.assertIn('class="guide-document"', html)
    self.assertIn("data-motion-surface", html)
    self.assertIn("motion:scroll-frame", html)
    self.assertNotIn("const pointerLight", html)
    self.assertNotIn("requestAnimationFrame(updateScrollState)", html)
```

Extend `tests/test_motion_system.py` to fetch `/guide`, then GET both shared resource URLs and assert HTTP 200 with CSS/JavaScript MIME types.

- [ ] **Step 2: Run guide tests and verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_web_guide tests.test_motion_system -v
```

Expected: FAIL because the guide still owns duplicate scroll/pointer animation code.

- [ ] **Step 3: Add guide motion markup and shared assets**

In `templates/guide.html`:

- load shared `motion.css` at the end of the page styles;
- load deferred `motion.js` before the small guide-specific script;
- stage `.guide-kicker`, `h1`, and `.guide-intro` with one group and orders `0..2`;
- mark `.guide-toc-inner` and `.guide-document` as restrained motion surfaces;
- add one-time reveal attributes to the document container and top-level rendered `h2` sections after render using the guide script, with groups but no paragraph-level animation;
- add decorative parallax only to existing non-content background layers, creating an `aria-hidden` element if the template lacks a stable decorative layer.

- [ ] **Step 4: Replace duplicate animation loops with the shared event**

Keep TOC construction. Replace the guide's scroll-frame scheduler with a listener that receives the shared frame:

```javascript
document.addEventListener("motion:scroll-frame", () => {
  let currentId = "";
  headings.forEach(heading => {
    if (heading.getBoundingClientRect().top <= 130) currentId = heading.id;
  });
  tocLinks.forEach(link => link.classList.toggle("is-current", link.hash === `#${currentId}`));
});
```

After adding attributes to generated headings/sections, call:

```javascript
window.MotionSystem?.refresh(document.getElementById("guide-markdown"));
```

Delete the guide's own pointer tracking, progress update, topbar update, and requestAnimationFrame state. Do not change Markdown HTML, anchor IDs, external-link safety, or selection behavior.

- [ ] **Step 5: Run guide and shared regressions**

Run:

```bash
node --check static/js/motion.js
venv/bin/python -m unittest tests.test_web_guide tests.test_motion_system tests.test_web_progress -q
```

Expected: PASS.

- [ ] **Step 6: Commit guide integration**

```bash
git add templates/guide.html tests/test_web_guide.py tests/test_motion_system.py
git commit -m "feat: apply shared motion to usage guide"
```

---

### Task 4: Integrate Motion with the Kozeki Ui Hidden Page

**Files:**
- Modify: `templates/kozekilmu.html`
- Modify: `tests/test_kozekilmu.py`
- Modify: `tests/test_motion_system.py`

**Interfaces:**
- Consumes shared motion assets from Task 1.
- Produces staged hero/race/media/gallery entrances, approved media surfaces, and decorative depth.
- Removes all duplicate hidden-page pointer and scroll scheduling code.

- [ ] **Step 1: Write failing hidden-page motion tests**

Add:

```python
def test_hidden_page_uses_shared_motion_without_duplicate_runtime(self):
    html = self.client.get("/kozekilmu").get_data(as_text=True)
    self.assertIn('href="/static/css/motion.css"', html)
    self.assertIn('<script defer src="/static/js/motion.js"></script>', html)
    self.assertIn('class="hero"', html)
    self.assertIn('data-motion-group="kozeki-hero"', html)
    self.assertRegex(html, r'class="video-card"[^>]*data-motion-surface')
    self.assertGreaterEqual(html.count("data-motion-surface"), 6)
    self.assertNotIn("const pointerLight", html)
    self.assertNotIn("requestAnimationFrame(updateScrollState)", html)
```

Extend the shared delivery test for `/kozekilmu` and assert both shared assets return 200 with expected MIME types.

- [ ] **Step 2: Run hidden-page tests and verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_kozekilmu tests.test_motion_system -v
```

Expected: FAIL because the page has not loaded the shared system.

- [ ] **Step 3: Add hidden-page choreography**

In `templates/kozekilmu.html`:

- load `motion.css` after the existing page styles and deferred `motion.js` before closing body;
- stage hero kicker/title/subtitle/stamp, then race data, video heading/card, gallery heading, and gallery shots in reading order;
- mark the main video card and five `.shot` figures with `data-motion-surface`;
- add low-strength parallax only to the hero stamp, video image wrapper, and gallery image wrappers; if necessary, introduce inner wrappers so shared transforms never overwrite existing image hover transforms;
- retain clipping, dimensions, lazy loading, captions, external Bilibili link, and responsive grid.

- [ ] **Step 4: Remove the duplicate hidden-page runtime**

Delete the entire inline pointer/scroll IIFE. Shared motion owns the scroll progress, topbar state, pointer-light state, page visibility, and frame lifecycle. Keep only page content and existing non-runtime styles.

Confirm reduced-motion CSS does not hide images or suppress the essential Bilibili play affordance.

- [ ] **Step 5: Run hidden-page regressions**

Run:

```bash
node --check static/js/motion.js
venv/bin/python -m unittest tests.test_kozekilmu tests.test_motion_system tests.test_web_guide -q
```

Expected: PASS.

- [ ] **Step 6: Commit hidden-page integration**

```bash
git add templates/kozekilmu.html tests/test_kozekilmu.py tests/test_motion_system.py
git commit -m "feat: apply shared motion to hidden page"
```

---

### Task 5: Full Regression, Performance Evidence, and Visual QA

**Files:**
- Modify only if verification exposes a regression.
- Test: all `tests/*.py`

**Interfaces:**
- Consumes all shared and page-specific motion work.
- Produces final automated, lifecycle, performance, accessibility, and visual evidence.

- [ ] **Step 1: Capture the download-file manifest before final QA**

Run without modifying the existing files:

```bash
find /Users/markyang/Projects/GTD/downloads -type f -exec shasum -a 256 {} \; | LC_ALL=C sort > /tmp/gtd-motion-downloads-before.sha256
```

- [ ] **Step 2: Run complete automated verification**

Run:

```bash
venv/bin/python -m unittest discover -s tests -v
venv/bin/python -m compileall -q *.py tests
node --check static/js/motion.js
node --check static/js/index.js
git diff --check
```

Expected: all tests PASS, with only the two existing Windows-only tests skipped on macOS; all syntax and whitespace checks exit 0.

- [ ] **Step 3: Record deterministic motion performance evidence**

Use source contracts or a small browser instrumentation script to verify:

- there is one shared `frameId` scheduler and no interval/timer loop;
- repeated pointer moves before a frame produce one scheduled frame;
- hidden visibility cancels the pending frame and neutralizes the active surface;
- coarse pointer and reduced motion do not attach surface pointer listeners;
- reveal observer unobserves a revealed element;
- number interpolation restarts from its current visible number and bypasses non-numeric content.

Record the results without claiming GPU frame rates unless measured in the browser.

- [ ] **Step 4: Run local browser QA on port 8234**

Start a temporary non-debug Flask process bound only to `127.0.0.1:8234`. Do not stop, replace, or inspect ownership of the existing `8233` service beyond confirming the test uses `8234`.

Check the following at desktop width, mobile width, and with reduced motion emulation on `/`, `/guide`, and `/kozekilmu`:

- first-load hierarchy and one-time scroll reveals;
- topbar blur with no height change;
- desktop-only sheen and tilt remain subtle and do not move controls independently;
- touch/mobile mode has no tilt or pointer sheen tracking;
- Hero decorative parallax stays within the 4-12px range;
- metrics animate forward without stale or backward jumps;
- video/audio inputs, format controls, folder picker state, preview, task polling, retry/cancel/redownload controls, guide anchors, and hidden-page external link remain usable;
- no horizontal overflow, layout shift, clipped focus ring, unreadable text, or browser console error.

Stop only the temporary `8234` process after QA.

- [ ] **Step 5: Recheck download files**

Run:

```bash
find /Users/markyang/Projects/GTD/downloads -type f -exec shasum -a 256 {} \; | LC_ALL=C sort > /tmp/gtd-motion-downloads-after.sha256
cmp -s /tmp/gtd-motion-downloads-before.sha256 /tmp/gtd-motion-downloads-after.sha256
```

Expected: `cmp` exits 0.

- [ ] **Step 6: Request independent code review**

Give the reviewer the design, this plan, the pre-feature base SHA, branch HEAD, full test output, motion performance evidence, browser QA results, and complete diff. Resolve every Critical and Important finding with a new failing regression test before changing implementation.

- [ ] **Step 7: Commit review fixes if required and rerun verification**

If review changes are required:

```bash
git add <only-the-reviewed-files>
git commit -m "fix: address motion system review findings"
```

Then rerun Steps 2 and 5 and require `git status --short` to be empty before handoff.
