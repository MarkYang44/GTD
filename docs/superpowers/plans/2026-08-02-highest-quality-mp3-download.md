# Highest-Quality MP3 Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add highest-available-quality MP3 downloads to the shared downloader, Web UI, and CLI without changing existing video defaults.

**Architecture:** Keep `(platform, url)` tasks unchanged and pass a batch-level `media_type` through `main.py` or `app.py` into `download_tasks()`, `download_video()`, and `_build_ydl_options()`. Audio uses `bestaudio/best` plus `FFmpegExtractAudio`; the Web page provides a second independent input card while sharing the existing task list and one-active-batch state.

**Tech Stack:** Python 3, yt-dlp, FFmpeg, Flask, vanilla HTML/CSS/JavaScript, unittest.

## Global Constraints

- `media_type` accepts exactly `video` or `audio`; all existing calls default to `video`.
- MP3 mode selects `bestaudio/best` and uses FFmpeg MP3 quality `0`.
- YouTube keeps title-only filenames; Instagram keeps the `[id]` suffix.
- Each batch uses at most `MAX_PARALLEL_DOWNLOADS = 3` workers and preserves input order.
- The Web UI allows only one active batch across the video and audio sections.
- This checkout is not a Git repository; replace commit steps with file inspection and fresh verification commands.

---

### Task 1: Shared audio download core

**Files:**
- Modify: `downloader.py`
- Modify: `tests/test_downloader_errors.py`
- Modify: `tests/test_parallel_downloads.py`

**Interfaces:**
- Produces: `VIDEO = "video"`, `AUDIO = "audio"`, `MEDIA_TYPES`, and optional `media_type: str = VIDEO` parameters on `_build_ydl_options()`, `download_video()`, and `download_tasks()`.
- Produces: audio results whose `media_type` is `audio`, `format` is `MP3`, and filepath resolves to `.mp3`.

- [ ] **Step 1: Write failing option and output-path tests**

Add tests that assert:

```python
options = downloader._build_ydl_options(
    downloader.YOUTUBE, output_dir, 1, 1, media_type=downloader.AUDIO
)
self.assertEqual(options["format"], "bestaudio/best")
self.assertEqual(options["postprocessors"], [{
    "key": "FFmpegExtractAudio",
    "preferredcodec": "mp3",
    "preferredquality": "0",
}])
self.assertEqual(options["outtmpl"], str(output_dir / "%(title)s.%(ext)s"))
```

Also create a temporary `.mp3` file and assert `_resolve_output_path(..., media_type=AUDIO)` returns it; assert Instagram audio keeps `%(title)s [%(id)s].%(ext)s`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_downloader_errors.DownloadAudioOptionsTests -v
```

Expected: failures because `AUDIO` and `media_type` do not exist.

- [ ] **Step 3: Implement the minimal audio option and result path behavior**

Add constants and branch before platform-specific video settings:

```python
VIDEO = "video"
AUDIO = "audio"
MEDIA_TYPES = {VIDEO, AUDIO}

if media_type == AUDIO:
    options.update({
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "0",
        }],
    })
```

Keep platform-specific JS runtime, headers, cookie and output-template behavior. Resolve `.mp3` before `.mp4` for audio and populate type-appropriate result metadata.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the command from Step 2. Expected: all focused tests pass.

- [ ] **Step 5: Write the failing propagation test**

Patch `download_video`, call `download_tasks(tasks, media_type=downloader.AUDIO)`, and assert every call contains `media_type="audio"` while the existing maximum concurrency and order test remains unchanged.

- [ ] **Step 6: Run propagation test and verify RED**

```bash
venv/bin/python -m unittest tests.test_parallel_downloads.ParallelDownloadTests.test_audio_media_type_is_forwarded_to_every_task -v
```

Expected: failure because `download_tasks()` does not accept `media_type`.

- [ ] **Step 7: Pass media type through the batch core and verify GREEN**

Add the defaulted parameter and forward it:

```python
def download_tasks(tasks, progress_callback=None, media_type=VIDEO):
    ...
    result = download_video(..., media_type=media_type)
```

Run all parallel-download tests. Expected: all pass, including max concurrency 3 and ordered results.

### Task 2: Web API and batch state

**Files:**
- Modify: `app.py`
- Modify: `tests/test_web_progress.py`

**Interfaces:**
- Consumes: `VIDEO`, `AUDIO`, `MEDIA_TYPES`, `download_tasks(..., media_type=...)`.
- Produces: `/api/download` accepts optional JSON `media_type`; batches expose `media_type`.

- [ ] **Step 1: Write failing Flask tests**

Add tests using `app.test_client()` that assert:

```python
response = client.post("/api/download", json={"urls": [valid_url], "media_type": "bogus"})
self.assertEqual(response.status_code, 400)

with patch("app.threading.Thread"):
    response = client.post("/api/download", json={"urls": [valid_url], "media_type": "audio"})
batch = web_app._batches[response.get_json()["batch_id"]]
self.assertEqual(batch["media_type"], "audio")
```

Also assert omitted `media_type` produces a video batch.

- [ ] **Step 2: Run API tests and verify RED**

```bash
venv/bin/python -m unittest tests.test_web_progress.WebDownloadApiTests -v
```

Expected: media type is missing or invalid values are accepted.

- [ ] **Step 3: Implement validated batch-level media type**

Update `_create_batch(tasks, media_type=VIDEO)`, `_run_downloads(batch_id, tasks, media_type=VIDEO)`, and `api_download()`:

```python
media_type = body.get("media_type", VIDEO)
if media_type not in MEDIA_TYPES:
    return jsonify({"error": "不支持的下载类型"}), 400
```

Store the value on the batch and forward it to `download_tasks()` and the worker thread.

- [ ] **Step 4: Run Web tests and verify GREEN**

Run all `tests.test_web_progress` tests. Expected: all pass.

### Task 3: CLI audio mode

**Files:**
- Modify: `main.py`
- Create: `tests/test_cli_audio.py`

**Interfaces:**
- Consumes: `VIDEO`, `AUDIO`, `download_tasks(..., media_type=...)`.
- Produces: `parse_command_line(args) -> tuple[str, list[str]]` and `choose_media_type() -> str`.

- [ ] **Step 1: Write failing CLI parsing tests**

```python
self.assertEqual(main.parse_command_line(["--audio", url]), (downloader.AUDIO, [url]))
self.assertEqual(main.parse_command_line([url]), (downloader.VIDEO, [url]))
```

Patch `download_tasks`, run `main.main()` with `sys.argv = ["main.py", "--audio", url]`, and assert the call uses `media_type=AUDIO`.

- [ ] **Step 2: Run CLI tests and verify RED**

```bash
venv/bin/python -m unittest tests.test_cli_audio -v
```

Expected: `parse_command_line` is missing and audio is treated as an invalid URL.

- [ ] **Step 3: Implement minimal CLI mode selection and type-aware summaries**

Parse only the requested `--audio` flag, defaulting to video. In interactive mode accept empty/`1` for video and `2` for audio. Pass the selected type to `download_tasks()` and make result labels conditional on `result["media_type"]`.

- [ ] **Step 4: Run CLI tests and verify GREEN**

Run the command from Step 2, then run existing tests. Expected: all pass.

### Task 4: Separate Web audio card and user documentation

**Files:**
- Modify: `templates/index.html`
- Modify: `tests/test_web_progress.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `/api/download` with `media_type` and batch `media_type`.
- Produces: `videoUrls` and `audioUrls` textareas, separate submit/clear buttons, and one shared task list.

- [ ] **Step 1: Write failing frontend structure tests**

Assert the HTML contains separate IDs and payload types:

```python
self.assertIn('id="videoUrls"', html)
self.assertIn('id="audioUrls"', html)
self.assertIn('startDownload("video")', html)
self.assertIn('startDownload("audio")', html)
self.assertIn('media_type: mediaType', html)
```

Assert the completion renderer branches on audio and labels MP3 without forcing resolution output.

- [ ] **Step 2: Run frontend tests and verify RED**

```bash
venv/bin/python -m unittest tests.test_web_progress.WebProgressStateTests.test_frontend_has_separate_video_and_audio_download_inputs -v
```

Expected: the audio input and media-type request are absent.

- [ ] **Step 3: Implement the audio card and shared one-batch controller**

Rename the existing input to `videoUrls`, add the audio card, and replace single-element globals with a small media-type lookup. `startDownload(mediaType)` reads only the selected textarea, sends `media_type`, disables both cards while polling, and re-enables both on completion. Render `result.format`, `result.acodec`, and filesize for audio; retain video metadata for video.

- [ ] **Step 4: Update README**

Document the separate Web audio area, `python main.py --audio ...`, interactive mode choice, MP3/FFmpeg quality semantics, filenames, and output fields.

- [ ] **Step 5: Run focused frontend tests and verify GREEN**

Run all Web tests. Expected: all pass.

### Task 5: Full verification and live acceptance

**Files:**
- Verify: `downloader.py`, `app.py`, `main.py`, `templates/index.html`, `README.md`, `tests/`

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: fresh regression, API, browser, and real MP3 evidence.

- [ ] **Step 1: Run the full automated suite**

```bash
venv/bin/python -m unittest discover -s tests -v
venv/bin/python -m compileall -q app.py downloader.py main.py tests
```

Expected: zero failures and both commands exit 0.

- [ ] **Step 2: Simulate an audio batch through Flask**

Use Flask's test client with the background thread patched, verify HTTP 200, `media_type="audio"`, correct task count, and an initial pending state.

- [ ] **Step 3: Perform browser QA**

Start `venv/bin/python app.py`, inspect the page at `http://127.0.0.1:5000`, verify two distinct cards, mobile-width layout, disabled-state behavior, and media-specific result rendering. Stop only the process whose command and cwd match this project.

- [ ] **Step 4: Perform one real MP3 acceptance download**

Use a short public YouTube video with `venv/bin/python main.py --audio <URL>`, then run `ffprobe` on the resulting `.mp3`. Expected: file exists, container/codec is MP3, an audio stream is present, and no video stream is present.
