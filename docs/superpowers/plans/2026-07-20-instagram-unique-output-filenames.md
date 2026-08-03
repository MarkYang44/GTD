# Instagram Unique Output Filenames Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure different Instagram videos from the same author always use distinct output paths and are all downloaded.

**Architecture:** Keep the existing mixed-platform task pipeline unchanged and specialize only the Instagram yt-dlp output template. Append yt-dlp's stable video `id` to Instagram titles while preserving the current YouTube template and output-path resolution flow.

**Tech Stack:** Python 3, unittest, yt-dlp

## Global Constraints

- Instagram output names must use `%(title)s [%(id)s].%(ext)s`.
- YouTube output names must remain `%(title)s.%(ext)s`.
- Do not change CLI, Web, mixed-batch, concurrency, quality, Cookie, progress, retry, or existing-file migration behavior.
- Do not add dependencies.
- The workspace is not a Git repository, so replace commit steps with explicit file and test verification.

---

### Task 1: Make Instagram output paths unique by video ID

**Files:**
- Modify: `downloader.py:235-305`
- Modify: `tests/test_downloader_errors.py`

**Interfaces:**
- Consumes: `_build_ydl_options(platform: str, output_dir: Path, index: int, total: int, progress_callback=None) -> dict`
- Produces: an Instagram `outtmpl` equal to `<output_dir>/%(title)s [%(id)s].%(ext)s`; the YouTube template remains unchanged.

- [x] **Step 1: Add the failing Instagram filename regression test**

Add `tempfile` and `Path` imports and this test class to `tests/test_downloader_errors.py`:

```python
import tempfile
from pathlib import Path

import yt_dlp


class DownloadOutputTemplateTests(unittest.TestCase):
    def test_instagram_same_title_different_ids_prepare_distinct_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            options = downloader._build_ydl_options(
                downloader.INSTAGRAM,
                output_dir,
                1,
                2,
            )
            with yt_dlp.YoutubeDL(options) as ydl:
                first_path = Path(ydl.prepare_filename({
                    "id": "AAA111",
                    "title": "Video by same.author",
                    "ext": "mp4",
                }))
                second_path = Path(ydl.prepare_filename({
                    "id": "BBB222",
                    "title": "Video by same.author",
                    "ext": "mp4",
                }))

        self.assertNotEqual(first_path, second_path)
        self.assertEqual(first_path.name, "Video by same.author [AAA111].mp4")
        self.assertEqual(second_path.name, "Video by same.author [BBB222].mp4")

    def test_youtube_output_template_keeps_existing_filename(self):
        output_dir = Path("/tmp/downloads")

        options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            output_dir,
            1,
            1,
        )

        self.assertEqual(
            options["outtmpl"],
            str(output_dir / "%(title)s.%(ext)s"),
        )
```

- [x] **Step 2: Run the regression tests and verify the Instagram case fails for the right reason**

Run:

```bash
venv/bin/python -m unittest tests.test_downloader_errors.DownloadOutputTemplateTests -v
```

Expected: the Instagram test fails because both prepared paths are `Video by same.author.mp4`; the YouTube compatibility test passes.

- [x] **Step 3: Apply the minimal platform-specific template change**

Inside the Instagram branch of `_build_ydl_options()`, insert the `outtmpl` entry immediately before the existing `format` entry:

```python
                "outtmpl": str(output_dir / "%(title)s [%(id)s].%(ext)s"),
```

The resulting behavior must be:

```python
youtube_options["outtmpl"] == str(output_dir / "%(title)s.%(ext)s")
instagram_options["outtmpl"] == str(
    output_dir / "%(title)s [%(id)s].%(ext)s"
)
```

- [x] **Step 4: Run the focused regression tests and verify both pass**

Run:

```bash
venv/bin/python -m unittest tests.test_downloader_errors.DownloadOutputTemplateTests -v
```

Expected: 2 tests run and both pass.

- [x] **Step 5: Run the complete verification suite**

Run:

```bash
venv/bin/python -m unittest discover -s tests -v
venv/bin/python -m compileall -q app.py downloader.py main.py tests
```

Expected: all unit tests pass; compileall exits with status 0 and prints no errors.

- [x] **Step 6: Verify the final scope without Git**

Run:

```bash
rg -n 'outtmpl|DownloadOutputTemplateTests|same_title_different_ids|keeps_existing_filename' downloader.py tests/test_downloader_errors.py
```

Expected: production behavior changes only in the Instagram `outtmpl`; tests cover Instagram uniqueness and YouTube compatibility. Report the exact modified files because the workspace has no Git diff or commit history.
