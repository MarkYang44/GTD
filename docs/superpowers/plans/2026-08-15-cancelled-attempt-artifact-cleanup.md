# Cancelled Attempt Artifact Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 精准回收取消或失败下载留在目标目录中的任务私有封面、分片和中间文件，同时保留最终媒体与所有无关文件。

**Architecture:** 扩展现有 `output_files.cleanup_attempt_workspace()`，以工作目录名构造完整任务 marker，并在原有 `finally` 清理点统一回收目标目录直属的同任务文件。下载器调用关系保持不变，避免在 Bilibili、YouTube 和 Instagram 路径重复实现清理。

**Tech Stack:** Python 3, pathlib, shutil, unittest, yt-dlp.

## Global Constraints

- 只删除包含当前完整 ` [.__mvd_<id>]` 标记的普通文件或符号链接。
- 不删除最终媒体、无关临时文件、其他任务文件或用户已有文件。
- 不改变下载、重试、文件命名、封面或 aria2c 行为。
- 清理失败不得覆盖下载任务的原始成功、失败或取消结果。
- 不自动处理目标目录中已经存在的历史残留，不启动 8233 服务，不提交或推送代码。

---

### Task 1: Reproduce Target-Directory Leakage

**Files:**
- Modify: `tests/test_downloader_errors.py`

**Interfaces:**
- Consumes: `downloader._new_attempt_workspace(output_dir) -> Path`.
- Consumes: `downloader._cleanup_attempt_workspace(workspace) -> None`.
- Produces: regression contract for exact-marker artifact cleanup.

- [x] **Step 1: Write the failing regression test**

Extend `test_attempt_workspace_cleanup_is_scoped_to_owned_directory` so the target directory contains:

```python
marker = f" [.__mvd_{first.name}]"
owned_thumbnail = output_dir / f"Clip{marker}.jpg"
owned_part = output_dir / f"Clip{marker}.f100026.mp4.part"
final_file = output_dir / "Clip.mp4"
unrelated_part = output_dir / "Clip.f100026.mp4.part"
other_marker_file = output_dir / f"Clip [.__mvd_{second.name}].jpg"
```

After `_cleanup_attempt_workspace(first)`, require both owned artifacts and `first` to be absent while every other path remains byte-identical.

- [x] **Step 2: Verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_downloader_errors.OutputFileHelperTests.test_attempt_workspace_cleanup_is_scoped_to_owned_directory -v
```

Expected: FAIL because the target-directory `.jpg` and `.part` still exist.

---

### Task 2: Clean Only Exact Attempt-Owned Artifacts

**Files:**
- Modify: `output_files.py`
- Test: `tests/test_downloader_errors.py`

**Interfaces:**
- Keeps: `cleanup_attempt_workspace(workspace: Path, *, path_cls=Path, shutil_module=shutil) -> None`.
- Adds no public downloader API and changes no call site.

- [x] **Step 1: Implement the minimum exact-marker sweep**

Inside `cleanup_attempt_workspace()` after validating `.attempts`, validate the workspace name with the existing marker alphabet, construct:

```python
marker = f" [.__mvd_{workspace.name}]"
output_dir = workspace.parent.parent
```

Iterate only `output_dir.iterdir()`. For entries whose name contains the exact marker, call `unlink()` only when `entry.is_file()` or `entry.is_symlink()`. Catch filesystem errors per entry so cleanup remains best-effort. Then retain the existing workspace and empty-parent removal.

- [x] **Step 2: Verify GREEN and safety boundaries**

Run:

```bash
venv/bin/python -m unittest tests.test_downloader_errors.OutputFileHelperTests.test_attempt_workspace_cleanup_is_scoped_to_owned_directory -v
venv/bin/python -m unittest tests.test_downloader_errors tests.test_bilibili_support -q
```

Expected: PASS; exact current-attempt artifacts are removed and unrelated paths remain.

---

### Task 3: Full Regression Verification

**Files:**
- Verify: `output_files.py`
- Verify: `tests/test_downloader_errors.py`

**Interfaces:**
- Produces no additional code unless verification exposes a regression caused by Task 2.

- [x] **Step 1: Run static verification**

```bash
venv/bin/python -m compileall -q output_files.py downloader.py tests
git diff --check
```

Expected: both commands exit 0.

- [x] **Step 2: Run the complete automated suite**

```bash
venv/bin/python -m unittest discover -s tests -v
```

Expected: all supported-platform tests pass; existing platform-specific skips remain skips.

- [x] **Step 3: Review file safety and scope**

Confirm `git diff --stat`, `git diff`, and `git status --short` include only the two design/plan documents, the regression test, and the scoped cleanup implementation. Confirm no command modified `downloads/` or the user's existing Movies files.
