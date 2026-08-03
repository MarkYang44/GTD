# Portfolio-Inspired Dark UI Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** 将下载器首页升级为 Portfolio 风格的马石油绿深色工具界面，并增加 A1 运行指标带与渐进式滚动动效，同时保持现有视频、MP3 下载行为完全不变。

**Architecture:** 所有正式 UI、样式与无依赖交互增强集中在 `templates/index.html`。现有 Flask API、DOM 功能 ID、下载提交、轮询和任务渲染函数继续作为稳定边界；新增指标只消费轮询返回的 `batch.tasks`，动效初始化封装为可失败的独立增强层。

**Tech Stack:** Flask/Jinja HTML、原生 CSS、原生 JavaScript、Python `unittest`

---

## Success criteria

- 深色画布、石墨卡片与马石油绿设计变量出现在正式页面。
- 视频与音频输入保持独立，桌面双栏、390px 移动端单栏。
- ACTIVE、QUEUE、LIMIT 初始显示 `00 / 00 / 03`，轮询时从任务状态实时更新。
- 页面具备滚动进度、一次性 Reveal、精细指针柔光、卡片/按钮微交互和 reduced-motion 降级。
- 现有 DOM ID、API 请求格式、轮询、任务详情与长路径换行能力保持不变。
- 全量测试与 Python 编译检查通过，8233 端口桌面/移动端浏览器 QA 无控制台错误和横向溢出。

### Task 1: Lock the new frontend contract with failing tests

**Files:**
- Modify: `tests/test_web_progress.py`

**Step 1: Add focused static-contract tests**

Add separate tests for:

- Theme variables `--background: #0f172a`, `--surface: #111827`, `--primary: #009b95`, and `--accent: #00a19b`.
- Metric elements `metric-active`, `metric-queue`, `metric-limit` and initial `00`, `00`, `03` values.
- `updateOperationalMetrics(batch)` counting `downloading` and `pending` tasks and padding values to two digits.
- Enhancement hooks `scroll-progress`, `pointer-light`, `data-reveal`, `IntersectionObserver`, `requestAnimationFrame`, and `prefers-reduced-motion: reduce`.
- Stable structural hooks for the top bar, hero, two-column download grid, and task panel.

Keep every test focused on one user-visible contract and retain all existing tests.

**Step 2: Run the focused frontend tests and confirm RED**

Run:

```bash
venv/bin/python -m unittest tests.test_web_progress.WebProgressStateTests -v
```

Expected: the newly added tests fail because the dark theme, metrics band, and motion hooks are not yet present; pre-existing frontend tests continue to pass.

### Task 2: Exclude visual companion artifacts

**Files:**
- Modify: `.gitignore`

**Step 1: Add the preview directory rule**

Append `.superpowers/` without changing existing ignore rules.

**Step 2: Verify Git no longer reports preview artifacts**

Run:

```bash
git status --short
```

Expected: `.superpowers/` is absent; only intentional plan, test, template, and ignore-file changes are shown.

### Task 3: Implement the dark Portfolio-inspired page shell

**Files:**
- Modify: `templates/index.html`

**Step 1: Replace visual tokens and global layout**

Define the approved palette and typography using CSS custom properties. Add the dark canvas, subtle grid/noise layers, ambient PETRONAS glow, visible keyboard focus, responsive container sizing, and opaque fallback surfaces.

**Step 2: Build the approved page hierarchy**

Create:

- A sticky top bar containing `YD / DOWNLOADER` and `READY`, with no service/port label.
- A hero with the approved kicker, `Capture. Convert. Keep.` title, Chinese product description, and decorative orbit.
- A three-cell A1 metrics band with initial values `00 / 00 / 03`.
- A `.download-grid` containing the existing video and audio forms as distinct cards.
- A technical task panel containing the existing task title, summary, and task container.

Preserve these functional IDs exactly: `videoUrls`, `audioUrls`, `videoDownloadButton`, `audioDownloadButton`, `videoClearButton`, `audioClearButton`, `task-title`, `task-summary`, and `task-container`.

**Step 3: Restyle all functional states**

Provide dark input, button, task card, progress, completed, failed, metadata, and empty-state styles. Retain `.task-meta { overflow-wrap: anywhere; }` and ensure the desktop grid collapses to one column without horizontal overflow.

**Step 4: Run focused tests**

Run:

```bash
venv/bin/python -m unittest tests.test_web_progress.WebProgressStateTests -v
```

Expected: theme and structural tests pass; metrics/motion tests may remain RED until Task 4.

### Task 4: Add operational metrics and progressive motion

**Files:**
- Modify: `templates/index.html`

**Step 1: Add metrics computation**

Implement `setOperationalMetrics(active, queue)` and `updateOperationalMetrics(batch)`:

- ACTIVE counts `task.status === "downloading"`.
- QUEUE counts `task.status === "pending"`.
- Values use `String(value).padStart(2, "0")`.
- Changed values receive a short-lived flash class.
- Submission immediately reflects the pending URL count; every poll recomputes from the returned task array.
- LIMIT remains static at `03`.

**Step 2: Add isolated enhancement initialization**

Implement a guarded `initializeExperience()` that cannot interfere with download logic. It should:

- Update the 2px scroll-progress scale and top-bar scrolled state through `requestAnimationFrame`.
- Reveal `[data-reveal]` elements once with `IntersectionObserver`, or show them immediately when unsupported.
- Track pointer position through `requestAnimationFrame` only when `(pointer: fine)` matches and reduced motion does not.
- Leave all content visible by default if JavaScript or initialization fails.

**Step 3: Add reduced-motion and interaction CSS**

Disable translations, smooth behavior, pointer light, flashing, and looping decoration under `prefers-reduced-motion: reduce`. Add restrained card lift, border glow, button-arrow movement, press feedback, and new-task reveal elsewhere.

**Step 4: Run focused tests and confirm GREEN**

Run:

```bash
venv/bin/python -m unittest tests.test_web_progress.WebProgressStateTests -v
```

Expected: all frontend contract tests pass.

### Task 5: Run regression and compilation verification

**Files:**
- Verify only

**Step 1: Run the full unit suite**

Run:

```bash
venv/bin/python -m unittest discover -s tests -v
```

Expected: every test passes with zero failures or errors.

**Step 2: Compile project Python sources**

Run:

```bash
venv/bin/python -m compileall app.py downloader.py main.py tests
```

Expected: exit code 0.

**Step 3: Inspect the scoped diff**

Run:

```bash
git diff --check
git diff -- .gitignore templates/index.html tests/test_web_progress.py docs/superpowers/plans/2026-08-03-portfolio-inspired-dark-ui.md
```

Expected: no whitespace errors; every changed line traces to the approved frontend redesign.

### Task 6: Validate the live UI on port 8233

**Files:**
- Verify only

**Step 1: Start the project service**

Run `venv/bin/python app.py`, confirm it owns `127.0.0.1:8233`, and verify an HTTP 200 response before browser inspection. Do not stop unrelated processes.

**Step 2: Perform desktop browser QA**

At desktop width, verify:

- Header, hero, metrics, dual download cards, and task panel match the approved hierarchy.
- No `LOCAL SERVICE · 8233` text appears.
- Initial metrics are `00 / 00 / 03`.
- Scroll progress, reveal, sticky-header transition, focus ring, pointer light, hover, and button feedback work.
- Existing video/audio inputs and buttons remain operable.
- Console contains no errors.

**Step 3: Perform 390px mobile QA**

Verify:

- Metrics remain one compact three-column row.
- Video and audio cards stack vertically.
- Task metadata and paths wrap.
- There is no horizontal overflow.
- Touch layout does not depend on hover or pointer light.

**Step 4: Stop only the verified project process**

Terminate the exact process started for this check and verify port 8233 is no longer owned by it.

### Task 7: Final verification and handoff

**Files:**
- Verify all intentional changes

**Step 1: Re-run fresh final checks**

Run the full unit suite, compile check, and `git diff --check` again after browser QA.

**Step 2: Review repository status**

Confirm no preview artifacts, generated files, or unrelated edits are included. Do not stage, commit, or push unless the user requests it.

**Step 3: Report outcomes**

Summarize the implemented visual hierarchy, live metric behavior, responsive/motion accessibility behavior, test counts, browser QA, and the local URL `http://127.0.0.1:8233`.
