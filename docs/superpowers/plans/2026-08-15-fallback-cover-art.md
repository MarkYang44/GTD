# 下载文件封面兜底机制实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为支持封面的音频容器和 MP4 视频增加“源封面优先、缺失时每次随机使用内置图片”的最终封面保障。

**Architecture:** 新增独立 `media_cover.py`，在媒体完成下载、后处理和最终命名后检查真实容器标签；已有封面保持不变，没有封面时用 Mutagen 写入随机内置图片。下载器继续用 yt-dlp 获取源封面，并通过共享 finalizer 将实际封面状态写入 Web/CLI 共用结果。

**Tech Stack:** Python 3.14, yt-dlp, Mutagen, FFmpeg/ffprobe, unittest.

## Global Constraints

- 源站封面优先，绝不被兜底图片覆盖。
- 每次下载、重试或重新下载独立调用 `secrets.choice()`；不做内容 ID 稳定映射。
- 仅支持 MP3、FLAC、M4A/MP4、OGG、Opus 和项目输出的 MP4 视频；WAV、WebM 不为封面转码或转封装。
- MP4 封面写入 `covr` 元数据，不重编码音视频流、不生成 sidecar 图片。
- 封面失败记录警告但不改变成功下载任务的状态。
- 六张用户原图只移动和重命名，SHA-256 必须保持不变。
- 不修改既有 `downloads/` 文件，不增加依赖，不启动或停止 8233 服务。

---

### Task 1: Add the Fallback Cover Asset Library and Container Writer

**Files:**
- Create: `assets/fallback_covers/cover-01.png`
- Create: `assets/fallback_covers/cover-02.jpg`
- Create: `assets/fallback_covers/cover-03.jpg`
- Create: `assets/fallback_covers/cover-04.png`
- Create: `assets/fallback_covers/cover-05.png`
- Create: `assets/fallback_covers/cover-06.jpg`
- Create: `media_cover.py`
- Create: `tests/test_media_cover.py`

**Interfaces:**
- Produces immutable `CoverOutcome(embedded: bool, source: Literal["source", "fallback", "none"], fallback_name: str | None)`.
- Produces `fallback_cover_paths() -> tuple[Path, ...]` in stable filename order.
- Produces `ensure_media_cover(filepath: Path, *, source_cover: Path | None = None, chooser: Callable | None = None) -> CoverOutcome`; `chooser=None` resolves to `secrets.choice` at call time.

- [ ] **Step 1: Write failing resource and behavior tests**

Create `tests/test_media_cover.py` with tests that require:

```python
EXPECTED_ASSETS = {
    "cover-01.png": "4dff6c05585511a21a0827cb6ef5f5950f33e6d1930b43798f93beb178a6c46c",
    "cover-02.jpg": "1726f1cb05ac075b09b85a4ef12c6ea2f425bbb59b118fedf3f462f7b237dccf",
    "cover-03.jpg": "7f08ab1bdfba35e34aa8254c9080784e5835f115af78a75ed128615bd1c68e4d",
    "cover-04.png": "d2449e6c0fd759462e108a3cf4edbe8e79a35b88cbc52f878921361a94952ddf",
    "cover-05.png": "3077461dc3474b4544eb9b4bf3272298bb9a7b845fd1ce5c98a52a8d6aeabfb7",
    "cover-06.jpg": "e33fe437c47cec137aba8ed929b3d2328376ebb18baa50d030a65bba7935d465",
}
```

Tests must verify exact count/name/hash, PNG/JPEG signatures, unsupported `.wav`/`.webm` bypass without calling the chooser, missing/corrupt media returns `none` with a warning, and a supplied chooser is called exactly once for a supported file without a cover.

- [ ] **Step 2: Run Task 1 tests and verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_media_cover -v
```

Expected: import/resource failures because `media_cover.py` and `assets/fallback_covers/` do not exist.

- [ ] **Step 3: Move the six original images without changing bytes**

Create `assets/fallback_covers/`, then move these explicit source files from the main checkout `/Users/markyang/Projects/Multiple_Video_Downloader/` into the active feature worktree at the planned names:

```text
10319268-6284-4932-B124-441356EBC322.PNG -> cover-01.png
80FE2ECE-7AF4-4A1A-A1A4-603804CA2159.jpg -> cover-02.jpg
9CFB3921-A973-440F-B6F7-A087A14D36B1.jpg -> cover-03.jpg
B5CCBC21-C283-4890-A1C8-74B4B299BC5C.PNG -> cover-04.png
F6FC1CB9-493C-48F0-A794-320A471277E7.PNG -> cover-05.png
IMG_9655.jpg -> cover-06.jpg
```

Re-run SHA-256 checks and require exact equality with `EXPECTED_ASSETS`.

- [ ] **Step 4: Implement `media_cover.py` minimally**

Use Mutagen container APIs and signature-based image MIME detection without Pillow:

```python
SUPPORTED_COVER_EXTENSIONS = {".mp3", ".flac", ".m4a", ".mp4", ".m4v", ".mov", ".ogg", ".opus"}

def ensure_media_cover(filepath, *, source_cover=None, chooser=None):
    if filepath.suffix.lower() not in SUPPORTED_COVER_EXTENSIONS:
        return CoverOutcome(False, "none")
    if _has_cover(filepath):
        return CoverOutcome(True, "source")
    if source_cover is not None:
        try:
            _embed_cover(filepath, source_cover)
            return CoverOutcome(True, "source")
        except Exception:
            pass  # warn locally, then continue to fallback
    cover = (chooser or secrets.choice)(fallback_cover_paths())
    _embed_cover(filepath, cover)
    if not _has_cover(filepath):
        raise ValueError("cover verification failed")
    return CoverOutcome(True, "fallback", cover.name)
```

Catch resource/media/write exceptions at the public boundary, log one warning containing the media path and cause, and return `CoverOutcome(False, "none")`. Implement MP3 `APIC`, FLAC `Picture`, MP4/M4A `covr`, and OGG/Opus `METADATA_BLOCK_PICTURE`.

- [ ] **Step 5: Add real-container RED/GREEN integration tests**

Using `tempfile`, `shutil.which("ffmpeg")`, and subprocess argument lists (no shell), create 0.2-second MP3, FLAC, M4A, and MP4 fixtures. Verify:

- fallback insertion is detected on a second read;
- the chosen asset name is returned;
- an existing source cover is byte-identical after another call and the chooser is not invoked;
- two separate uncovered fixtures with an injected sequential chooser receive different covers;
- MP4 的非封面音视频流 codec 与数量在写入前后保持不变；`covr` 可由 ffprobe 呈现为一个 `attached_pic` 封面流。

Skip only the real-container tests when FFmpeg/ffprobe is unavailable; resource and unit contracts must still run.

- [ ] **Step 6: Verify and commit Task 1**

Run:

```bash
venv/bin/python -m unittest tests.test_media_cover -v
venv/bin/python -m compileall -q media_cover.py tests/test_media_cover.py
git diff --check
```

Commit:

```bash
git add assets/fallback_covers media_cover.py tests/test_media_cover.py
git commit -m "feat: add fallback cover library"
```

---

### Task 2: Integrate Source Covers and Final Cover Outcomes

**Files:**
- Modify: `downloader.py`
- Modify: `tests/test_downloader_errors.py`
- Modify: `tests/test_parallel_downloads.py`
- Modify: `tests/test_task_control.py`

**Interfaces:**
- Consumes `ensure_media_cover()` and `CoverOutcome` from Task 1.
- Mutates the final `info` dictionary with private `_cover_embedded`, `_cover_source`, and `_fallback_cover` fields inside `_finalize_download_output()` without changing its return signature.
- Produces public result keys `cover_embedded: bool`, `cover_source: str`, and `fallback_cover: str | None` for both video and audio results.

- [ ] **Step 1: Write failing yt-dlp option tests**

Add tests requiring video options for YouTube, Instagram, and Bilibili to set `writethumbnail=True` without adding `EmbedThumbnail` to yt-dlp's fatal main postprocessor chain. For Instagram, assert `FFmpegVideoRemuxer` remains configured. Supported audio containers also download source thumbnails for the shared non-fatal finalizer; WAV/WebM do not request thumbnails.

- [ ] **Step 2: Write failing finalizer/result tests**

Patch `downloader._ensure_media_cover` with deterministic `CoverOutcome` values and require:

```python
{
    "cover_embedded": True,
    "cover_source": "fallback",
    "fallback_cover": "cover-03.jpg",
}
```

for both audio and video results. Verify `source` returns no fallback name, `none` reports false, and finalization calls the cover helper after audio/video final naming. Extend ordinary/Bilibili parity assertions with all three fields.

- [ ] **Step 3: Run Task 2 tests and verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_downloader_errors tests.test_parallel_downloads -v
```

Expected: failures because video options do not request thumbnails and final results still expose format capability rather than actual cover state.

- [ ] **Step 4: Enable source-cover embedding for MP4 video**

In `_build_ydl_options()`:

- YouTube/Bilibili video: retain format and merge settings and add `writethumbnail=True` without a thumbnail embedding postprocessor.
- Instagram video: retain the remuxer and set `writethumbnail=True` without a thumbnail embedding postprocessor.
- Resolve the moved task-private thumbnail in the shared finalizer, embed it locally with non-fatal error handling, then remove only that owned sidecar.

Do not add thumbnail handling to WAV or WebM audio output.

- [ ] **Step 5: Run the final cover guard in the shared finalizer**

Resolve the task-owned source sidecar before final naming, then call `_ensure_media_cover(filepath, source_cover=source_cover)` exactly once after audio/video renaming and store the outcome on `info`. Keep `_finalize_download_output()`'s existing tuple return signature so all platform and retry paths retain compatibility.

In `_build_download_result()`, add the three public cover fields to the common result dictionary and remove the old audio-only `audio_profile.cover_embedded` report. Validate the stored source against `{"source", "fallback", "none"}` and fail closed to `none` for malformed internal values.

- [ ] **Step 6: Verify normal, Bilibili, retry, and redownload paths**

Use existing mocked downloader/task-manager tests to prove every successful path goes through the shared finalizer once, while failed/cancelled attempts do not report a successful cover. Ensure redownload creates a new output and invokes the helper again rather than reusing the old outcome.

- [ ] **Step 7: Verify and commit Task 2**

Run:

```bash
venv/bin/python -m unittest tests.test_downloader_errors tests.test_parallel_downloads tests.test_task_control -q
venv/bin/python -m compileall -q downloader.py tests
git diff --check
```

Commit:

```bash
git add downloader.py tests/test_downloader_errors.py tests/test_parallel_downloads.py tests/test_task_control.py
git commit -m "feat: apply fallback covers to downloads"
```

---

### Task 3: Document and Fully Verify the Cover Guarantee

**Files:**
- Modify: `README.md`
- Modify: `tests/test_downloader_errors.py`
- Modify: `tests/test_media_cover.py`

**Interfaces:**
- Documents the exact supported formats, random-per-download behavior, source precedence, MP4 metadata behavior, and non-fatal failure policy.
- Produces final automated, media-integrity, and download-directory evidence.

- [ ] **Step 1: Add a failing README contract**

Require README text to state:

- source covers are never replaced;
- MP3/FLAC/M4A/OGG/Opus and MP4 use a random built-in fallback when needed;
- each retry/redownload may choose a different image;
- WAV/WebM remain unsupported and are not transcoded for covers;
- cover failure does not invalidate a completed media download.

- [ ] **Step 2: Update README and run focused tests**

Replace the old sentence saying source content without a cover simply completes without one. Run the README contract plus `tests.test_media_cover` and downloader option tests.

- [ ] **Step 3: Commit the documentation contract**

Run focused tests, then commit:

```bash
git add README.md tests/test_downloader_errors.py
git commit -m "docs: explain fallback cover behavior"
```

- [ ] **Step 4: Capture download-directory integrity before full QA**

Run:

```bash
find /Users/markyang/Projects/Multiple_Video_Downloader/downloads -type f -exec shasum -a 256 {} \; | LC_ALL=C sort > /tmp/mvd-cover-downloads-before.sha256
```

- [ ] **Step 5: Run complete automated verification**

Run:

```bash
venv/bin/python -m unittest discover -s tests -v
venv/bin/python -m compileall -q *.py tests
node --check static/js/motion.js
node --check static/js/index.js
git diff --check
```

Expected: all tests pass with only the existing Windows-only skips on macOS.

- [ ] **Step 6: Verify real media without touching user downloads**

In a temporary directory, generate MP3, FLAC, M4A, and MP4 fixtures, run `ensure_media_cover()` with each of the six assets, and reopen every output with Mutagen. Use ffprobe to confirm MP4 media codec names, duration tolerance, and non-attached media stream counts are unchanged.

- [ ] **Step 7: Recheck downloads and request independent review**

Run:

```bash
find /Users/markyang/Projects/Multiple_Video_Downloader/downloads -type f -exec shasum -a 256 {} \; | LC_ALL=C sort > /tmp/mvd-cover-downloads-after.sha256
cmp -s /tmp/mvd-cover-downloads-before.sha256 /tmp/mvd-cover-downloads-after.sha256
```

Give the reviewer the design, plan, pre-feature base SHA, branch HEAD, full diff, test output, real-media evidence, six asset hashes, and download comparison. Fix every Critical/Important finding with a new failing regression before implementation changes.

- [ ] **Step 8: Commit review fixes only when required**

If review requires changes, add a new failing regression first, make the smallest fix, and commit the bounded review surface with:

```bash
git add media_cover.py downloader.py tests/test_media_cover.py tests/test_downloader_errors.py tests/test_parallel_downloads.py tests/test_task_control.py
git commit -m "fix: address fallback cover review findings"
```

Require `git status --short` to be empty before handoff.
