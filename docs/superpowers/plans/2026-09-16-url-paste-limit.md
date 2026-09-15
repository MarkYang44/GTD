# URL Paste Limit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Warn users at 20 pasted URL lines and reject any paste that would make either download input exceed 20 non-empty lines.

**Architecture:** Add one shared paste guard in `static/js/index.js` and attach it to both existing textareas during startup. Test browser-event behavior through a focused Node VM harness invoked by the Python regression suite.

**Tech Stack:** Vanilla JavaScript, Node.js `vm` and `assert`, Python `unittest`

## Global Constraints

- Count trimmed, non-empty lines in the value that would exist after selection replacement.
- Allow a paste resulting in exactly 20 lines, then show the localized limit message.
- Reject the entire paste if it would exceed 20 lines; do not truncate it.
- Apply identical behavior to video and audio inputs.
- Do not change typing, backend limits, public APIs, HTML, or CSS.
- Do not stage, commit, or push changes.

---

### Task 1: Add the paste-limit regression harness

**Files:**
- Create: `tests/js/url_paste_limit_harness.js`
- Modify: `tests/test_web_progress.py`

**Interfaces:**
- Consumes: paste listeners registered on `#videoUrls` and `#audioUrls`
- Produces: a Node process that exits nonzero unless normal, exact-limit, overflow, selection-replacement, bilingual, and dual-input behavior match the specification

- [ ] **Step 1: Write the failing Node harness**

Create a DOM stub whose textarea elements retain `paste` listeners. Dispatch simulated clipboard events and assert that 18 existing lines plus two new lines is allowed with a warning, 18 plus three is entirely rejected, a selected range is replaced before counting, and the same guard exists on both inputs. Switch `GtdLanguage.language` to English and assert the alert is English.

- [ ] **Step 2: Register the harness in Python**

Add this method to `WebConfigurationTests`:

```python
def test_url_paste_limit_harness(self):
    result = subprocess.run(
        ["node", "tests/js/url_paste_limit_harness.js"],
        capture_output=True,
        text=True,
        check=False,
    )
    self.assertEqual(result.returncode, 0, result.stderr)
```

- [ ] **Step 3: Verify RED**

Run: `node tests/js/url_paste_limit_harness.js`

Expected: FAIL because neither textarea has a registered `paste` listener.

### Task 2: Implement the shared paste guard

**Files:**
- Modify: `static/js/index.js`

**Interfaces:**
- Consumes: `ClipboardEvent.clipboardData`, textarea `value`, `selectionStart`, and `selectionEnd`
- Produces: `initializeUrlPasteLimits()` startup registration and paste-time enforcement with `URL_PASTE_LINE_LIMIT = 20`

- [ ] **Step 1: Add minimal implementation**

Add a helper that constructs the prospective value as:

```javascript
const start = textarea.selectionStart ?? textarea.value.length;
const end = textarea.selectionEnd ?? start;
const nextValue = textarea.value.slice(0, start) + pastedText + textarea.value.slice(end);
```

Count `nextValue.split("\n").map(line => line.trim()).filter(Boolean)`. If the count is 20, allow the event and alert in the current language. If above 20, call `event.preventDefault()` and show the same alert. Register the handler for both values in `downloadControls` during startup.

- [ ] **Step 2: Verify GREEN**

Run: `node tests/js/url_paste_limit_harness.js`

Expected: `URL paste limit harness passed`.

- [ ] **Step 3: Run focused frontend checks**

Run:

```bash
venv/bin/python -m unittest tests.test_web_progress.WebConfigurationTests.test_url_paste_limit_harness
node tests/js/download_language_harness.js
node --check static/js/index.js
```

Expected: all commands exit 0.

### Task 3: Verify the complete change

**Files:**
- Verify: `static/js/index.js`
- Verify: `tests/js/url_paste_limit_harness.js`
- Verify: `tests/test_web_progress.py`

**Interfaces:**
- Consumes: completed Tasks 1 and 2
- Produces: repository-wide regression evidence and a reviewable unstaged diff

- [ ] **Step 1: Run the full regression suite**

Run: `venv/bin/python -m unittest discover -s tests -p 'test_*.py'`

Expected: exit 0 with only the existing platform-specific skips.

- [ ] **Step 2: Run static and diff checks**

Run:

```bash
node --check static/js/index.js
git diff --check
git status -sb
```

Expected: syntax and whitespace checks exit 0; status lists only this task's unstaged files.
