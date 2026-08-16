# GTD Brand Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Present the project publicly as GTD — Generalized Transmedia Downloader and prepare the verified Git repository for the GitHub repository name `GTD` without changing downloader behavior.

**Architecture:** Update only user-facing brand strings, safe documentation paths, and their regression contracts. Preserve runtime compatibility identifiers and use the existing Flask/static/CLI structure without introducing a brand abstraction or dependency.

**Tech Stack:** Python 3, Flask, unittest, HTML, JavaScript, JSON, Git.

## Global Constraints

- Use `GTD` on compact surfaces and `GTD — Generalized Transmedia Downloader` where the full identity fits.
- Keep downloader, parser, queue, conversion, media-cover, aria2c, API, and CLI invocation behavior unchanged.
- Preserve the logger namespace, browser download-history storage key, and existing aria2c environment variable.
- Do not add or upgrade dependencies, force push, rewrite history, or create a replacement GitHub repository.
- Produce one commit with message `chore: rename project to GTD`.

---

### Task 1: Lock Public Brand Contracts

**Files:**
- Modify: `tests/test_web_progress.py`
- Modify: `tests/test_web_guide.py`
- Modify: `tests/test_cli_audio.py`

**Interfaces:**
- Consumes the existing source files directly through `Path.read_text()` and the Flask test client.
- Produces test contracts for README heading/subtitle, Web/PWA names, guide identity, Web startup banner, and CLI public identity.

- [ ] **Step 1: Update tests to require the new identity**

Require these exact public values:

```text
# GTD
**Generalized Transmedia Downloader**
GTD stands for Generalized Transmedia Downloader.
<title>GTD — Generalized Transmedia Downloader</title>
🎬 GTD — Generalized Transmedia Downloader — Web 模式
```

Require `static/site.webmanifest` to expose full `name` and `short_name: GTD`; require the guide title and accessible service label to use GTD; require CLI source banners to include GTD.

- [ ] **Step 2: Verify RED**

Run:

```bash
../../venv/bin/python -m unittest tests.test_web_progress tests.test_web_guide tests.test_cli_audio -v
```

Expected: brand-contract failures against the legacy public identity while unrelated behavior tests continue passing.

---

### Task 2: Rename Current User-Facing Surfaces

**Files:**
- Modify: `README.md`
- Modify: `app.py`
- Modify: `main.py`
- Modify: `templates/index.html`
- Modify: `templates/guide.html`
- Modify: `static/site.webmanifest`
- Modify: `docs/WEB_GUIDE.md`

**Interfaces:**
- Keeps Flask routes, API payloads, HTML structure, CLI arguments, and Python imports unchanged.
- Produces the exact brand strings required by Task 1.

- [ ] **Step 1: Update README and current documentation**

Use this opening while retaining the existing functional description:

```markdown
# GTD

**Generalized Transmedia Downloader**

GTD stands for Generalized Transmedia Downloader.
```

Change project tree roots and sample `cd`/startup paths to `GTD`. Do not rewrite feature instructions.

- [ ] **Step 2: Update Web, PWA, and CLI display strings**

Set the main browser title to `GTD — Generalized Transmedia Downloader`; use `使用说明 - GTD` on the guide; use the full Web startup banner; use `GTD` in compact CLI input banners. Change only text and metadata attributes.

- [ ] **Step 3: Verify GREEN**

Run the Task 1 command and require all focused tests to pass.

---

### Task 3: Update Safe Historical References and Audit Compatibility

**Files:**
- Modify only tracked Markdown files containing safe legacy repository paths or user-facing proposed brand text.

**Interfaces:**
- Converts repository path examples to `/Users/markyang/Projects/GTD` and temporary test filenames to `/tmp/gtd-*`.
- Leaves the documented compatibility identifiers unchanged.

- [ ] **Step 1: Update safe references**

Change historical repository path examples and proposed extension labels to GTD. Do not alter third-party GitHub URLs.

- [ ] **Step 2: Run the six-variant residual search**

Use `rg` across tracked text. Expected retained matches are limited to the logger namespace, browser local-storage key, and any migration audit explanation that does not expose a legacy public brand.

---

### Task 4: Full Validation and Single Commit

**Files:**
- Verify all modified files.

**Interfaces:**
- Produces one verified Git commit and no runtime artifacts.

- [ ] **Step 1: Run static and automated validation**

```bash
../../venv/bin/python -m unittest discover -s tests -q
../../venv/bin/python -m compileall -q .
node --check static/js/index.js
node --check static/js/motion.js
../../venv/bin/python -m json.tool static/site.webmanifest
git diff --check
```

- [ ] **Step 2: Run Flask smoke validation**

Start the worktree's `app` on `127.0.0.1` with a temporary non-production port, request the home page, guide, capabilities API, and manifest, verify HTTP 200 and GTD identity, then stop the exact process.

- [ ] **Step 3: Review and commit**

Inspect `git status`, `git diff --stat`, and full `git diff`. Stage only rename-related tracked files and create:

```bash
git commit -m "chore: rename project to GTD"
```

---

### Task 5: Integrate, Push, and Rename the Local Root

**Files:**
- No source-file edits.

**Interfaces:**
- Fast-forwards `main` to the verified rename commit.
- Pushes normally to the existing origin.
- Renames the local project root to `GTD` after removing the linked worktree and repairs the ignored virtual environment's absolute paths.

- [ ] **Step 1: Integrate and push safely**

Fast-forward `main`, verify the remote remains the existing accessible repository, then run a normal `git push origin main`. Do not force push.

- [ ] **Step 2: Rename the local root**

Remove the clean linked worktree and rename the local root directory from its legacy basename to `GTD`. Repair the moved virtual environment without upgrading dependencies:

```bash
/opt/homebrew/bin/python3 -m venv --upgrade /Users/markyang/Projects/GTD/venv
```

Verify the activation scripts and executable shebangs contain the new root, then rerun Python, pip, yt-dlp, the complete test suite, `git status`, branch, commit, and `origin` from the new path.

- [ ] **Step 3: Report the GitHub manual action**

Because GitHub CLI is unavailable, instruct the user to rename the repository in GitHub Settings and then run:

```bash
git remote set-url origin https://github.com/MarkYang44/GTD.git
git fetch origin
```
