# User Guide Tilt Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the User Guide pointer tilt to 40% of the existing strength while preserving every other page's current motion.

**Architecture:** Extend the shared surface runtime with one optional `data-motion-tilt-strength` multiplier that defaults to `1`. Opt only the User Guide table of contents and document panel into `0.4`, leaving shared selectors, CSS, transitions, sheen, and reduced-motion handling unchanged.

**Tech Stack:** Vanilla JavaScript, Jinja HTML, Python `unittest`, Node.js runtime assertions

## Global Constraints

- User Guide motion surfaces use exactly `0.4` of the current tilt strength.
- The existing `MAX_TILT = 0.6` default remains unchanged for every surface without the attribute.
- Download-page motion, layout, page content, sheen, transitions, and reduced-motion behavior remain unchanged.
- No dependency or business-logic changes.

---

### Task 1: Add opt-in per-surface tilt strength

**Files:**
- Modify: `tests/test_motion_system.py`
- Modify: `tests/test_web_guide.py`
- Modify: `static/js/motion.js`
- Modify: `templates/guide.html`

**Interfaces:**
- Consumes: Existing `[data-motion-surface]` pointer tracking and `MAX_TILT = 0.6`.
- Produces: Optional HTML attribute `data-motion-tilt-strength` containing a numeric multiplier clamped from `0` to `1`; absent or invalid values preserve multiplier `1`.

- [ ] **Step 1: Write the failing runtime and template tests**

In `tests/test_motion_system.py`, extend `test_runtime_handles_numbers_lifecycle_and_surface_cleanup` with a second surface:

```javascript
const softSurface = new Element({
  "data-motion-surface": "",
  "data-motion-tilt-strength": "0.4",
});
```

Return both surfaces from the mock root, trigger the soft surface at the top-right corner, and assert:

```javascript
assert.strictEqual(surface.style.values["--motion-rx"], "0.6deg");
assert.strictEqual(surface.style.values["--motion-ry"], "0.6deg");
softSurface.listeners.pointerenter[0]({ clientX: 100, clientY: 0 });
for (const callback of [...queuedFrames.values()]) callback(650);
assert.strictEqual(softSurface.style.values["--motion-rx"], "0.24deg");
assert.strictEqual(softSurface.style.values["--motion-ry"], "0.24deg");
```

In `tests/test_web_guide.py`, require both Guide surfaces to opt in:

```python
self.assertEqual(html.count('data-motion-tilt-strength="0.4"'), 2)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
venv/bin/python -m unittest \
  tests.test_motion_system.MotionSystemTests.test_runtime_handles_numbers_lifecycle_and_surface_cleanup \
  tests.test_web_guide.WebGuideTests.test_guide_loads_shared_motion_assets_and_declares_reading_safe_motion -v
```

Expected: FAIL because the runtime still emits `0.6deg` for the soft surface and the Guide template has no strength attributes.

- [ ] **Step 3: Implement the minimal runtime behavior**

In `static/js/motion.js`, derive a per-surface strength inside `updateSurface`:

```javascript
const configuredStrength = Number.parseFloat(surface.getAttribute("data-motion-tilt-strength"));
const tiltStrength = Number.isFinite(configuredStrength) ? clamp(configuredStrength, 0, 1) : 1;
const maxTilt = MAX_TILT * tiltStrength;
const rotateX = clamp((0.5 - y) * 2 * maxTilt, -maxTilt, maxTilt);
const rotateY = clamp((x - 0.5) * 2 * maxTilt, -maxTilt, maxTilt);
const tiltPrecision = tiltStrength === 1 ? 1 : 2;
```

Write the rotation properties using `tiltPrecision` so the Guide retains the exact `0.24deg` maximum while default surfaces keep their existing `0.6deg` representation.

In `templates/guide.html`, add the attribute to exactly these two existing surfaces:

```html
<div class="guide-toc-inner" data-motion-surface data-motion-tilt-strength="0.4">
<section class="guide-document" data-motion-surface data-motion-tilt-strength="0.4" aria-label="网页使用说明正文">
```

- [ ] **Step 4: Run focused and complete verification**

Run:

```bash
venv/bin/python -m unittest tests.test_motion_system tests.test_web_guide -q
venv/bin/python -m unittest discover -s tests -q
node --check static/js/motion.js
git diff --check
```

Expected: all tests pass, JavaScript syntax is valid, and Git reports no whitespace errors.

- [ ] **Step 5: Commit the implementation**

```bash
git add static/js/motion.js templates/guide.html tests/test_motion_system.py tests/test_web_guide.py
git commit -m "feat: soften user guide tilt"
```
