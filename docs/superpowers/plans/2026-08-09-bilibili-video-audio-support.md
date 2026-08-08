# Bilibili Video and Audio Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Bilibili single-video and short-link downloads to both Web and CLI, including highest-available-quality MP4 and highest-available-audio MP3 output.

**Architecture:** Extend the existing platform discriminator and yt-dlp option builder with one explicit Bilibili branch while preserving the shared `(platform, url)` task contract. Web, CLI, progress events, and the three-worker mixed queue continue to consume the same downloader interfaces; only user-facing supported-platform copy and Bilibili-specific validation, cookies, formats, filenames, and errors change.

**Tech Stack:** Python 3, yt-dlp, FFmpeg, Flask, HTML/CSS/vanilla JavaScript, `unittest`

## Global Constraints

- Support Bilibili `BV`, `av`, mobile video, and `b23.tv` links only.
- A multipart link downloads only the `?p=` part; without `p`, download part 1.
- Do not expand collections, favorites, playlists, bangumi, profiles, or recommendations.
- Do not download danmaku, subtitles, thumbnails, or auxiliary assets.
- Preserve separate Web video/audio inputs and a single mixed-platform queue.
- Preserve `MAX_PARALLEL_DOWNLOADS = 3`, input-order results, and per-task failure isolation.
- Resolve cookies in this order: `bilibili_cookies.txt`, then `cookies.txt`.
- Preserve all existing YouTube and Instagram formats and filename behavior.
- Do not add a new Python dependency.

## File Map

- `downloader.py`: platform constants, URL detection, yt-dlp options, filenames, cookies, and localized errors.
- `main.py`: CLI supported-platform prompts and error copy.
- `app.py`: Web API error copy and startup naming.
- `templates/index.html`: visible supported-platform copy only; no layout or workflow changes.
- `tests/test_bilibili_support.py`: Bilibili URL, options, cookie, error, CLI, API, template, and README regression tests.
- `README.md`: supported URLs, mixed usage, Cookie setup, filename rules, troubleshooting, and compliance.

---

### Task 1: Recognize Only Supported Bilibili Single-Video URLs

**Files:**
- Create: `tests/test_bilibili_support.py`
- Modify: `downloader.py:20-140`

**Interfaces:**
- Consumes: `normalize_url(url: str) -> str` and `make_task(url: str) -> Optional[VideoTask]`.
- Produces: `BILIBILI = "bilibili"`, `is_valid_bilibili_url(url: str) -> bool`, and `detect_platform(url: str) -> Optional[str]` returning `BILIBILI` for approved URLs.

- [ ] **Step 1: Write the failing URL recognition tests**

```python
import unittest

import downloader


class BilibiliUrlDetectionTests(unittest.TestCase):
    def test_accepts_single_video_and_short_link_urls(self):
        accepted = [
            "https://www.bilibili.com/video/BV1GJ411x7h7",
            "https://www.bilibili.com/video/av170001?p=2",
            "https://m.bilibili.com/video/BV1GJ411x7h7",
            "https://bilibili.com/video/av170001",
            "https://b23.tv/BV1GJ411x7h7",
        ]

        for url in accepted:
            with self.subTest(url=url):
                self.assertEqual(downloader.detect_platform(url), downloader.BILIBILI)
                self.assertTrue(downloader.is_valid_bilibili_url(url))
                self.assertEqual(downloader.make_task(url), (downloader.BILIBILI, url))

    def test_rejects_non_video_bilibili_pages(self):
        rejected = [
            "https://space.bilibili.com/2",
            "https://www.bilibili.com/bangumi/play/ep1",
            "https://www.bilibili.com/list/watchlater",
            "https://www.bilibili.com/medialist/play/1",
            "https://www.bilibili.com/video/",
            "https://www.bilibili.com/video/not-a-video-id",
            "https://b23.tv/",
        ]

        for url in rejected:
            with self.subTest(url=url):
                self.assertIsNone(downloader.detect_platform(url))
                self.assertFalse(downloader.is_valid_bilibili_url(url))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_bilibili_support.BilibiliUrlDetectionTests -v`

Expected: ERROR or FAIL because `downloader.BILIBILI` and `is_valid_bilibili_url()` do not exist.

- [ ] **Step 3: Add the Bilibili platform contract and narrow URL detector**

Add the constant and display name:

```python
BILIBILI = "bilibili"

PLATFORM_NAMES = {
    YOUTUBE: "YouTube",
    INSTAGRAM: "Instagram",
    BILIBILI: "Bilibili",
}
```

Add this branch after Instagram detection and before `return None`:

```python
    # -- Bilibili --
    bilibili_hosts = {
        "bilibili.com",
        "www.bilibili.com",
        "m.bilibili.com",
    }
    if (
        host in bilibili_hosts
        and len(path_parts) >= 2
        and path_parts[0] == "video"
        and re.fullmatch(r"(?:BV[0-9A-Za-z]+|av\d+)", path_parts[1], re.IGNORECASE)
    ):
        return BILIBILI

    if host in {"b23.tv", "www.b23.tv"} and path_parts:
        return BILIBILI
```

Add the compatibility helper:

```python
def is_valid_bilibili_url(url: str) -> bool:
    """判断链接是否为支持的 Bilibili 单视频或短链接。"""
    return detect_platform(url) == BILIBILI
```

- [ ] **Step 4: Run focused and existing URL-path tests**

Run: `venv/bin/python -m unittest tests.test_bilibili_support.BilibiliUrlDetectionTests tests.test_parallel_downloads -v`

Expected: PASS; existing mixed queue tests remain green.

- [ ] **Step 5: Commit the platform detector**

```bash
git add downloader.py tests/test_bilibili_support.py
git commit -m "feat: recognize Bilibili video URLs"
```

---

### Task 2: Build Bilibili Video, MP3, Cookie, and Error Options

**Files:**
- Modify: `tests/test_bilibili_support.py`
- Modify: `downloader.py:145-430`

**Interfaces:**
- Consumes: `BILIBILI`, `_find_cookie_file(platform: str) -> Optional[Path]`, and `_build_ydl_options(..., media_type: str) -> dict`.
- Produces: Bilibili yt-dlp options with ID-suffixed output, `noplaylist=True`, MP4 merge or MP3 extraction, and localized access guidance.

- [ ] **Step 1: Write failing Bilibili option, cookie, and error tests**

Append to `tests/test_bilibili_support.py`:

```python
import contextlib
import io
import tempfile
from pathlib import Path
from unittest.mock import patch


class BilibiliDownloadOptionsTests(unittest.TestCase):
    def test_video_uses_best_streams_mp4_merge_and_id_suffix(self):
        output_dir = Path("/tmp/downloads")

        options = downloader._build_ydl_options(
            downloader.BILIBILI, output_dir, 1, 1,
        )

        self.assertEqual(options["format"], "bestvideo+bestaudio/best")
        self.assertEqual(options["merge_output_format"], "mp4")
        self.assertTrue(options["noplaylist"])
        self.assertEqual(
            options["outtmpl"],
            str(output_dir / "%(title)s [%(id)s].%(ext)s"),
        )
        self.assertNotIn("http_headers", options)

    def test_audio_uses_best_audio_mp3_and_id_suffix(self):
        output_dir = Path("/tmp/downloads")

        options = downloader._build_ydl_options(
            downloader.BILIBILI,
            output_dir,
            1,
            1,
            media_type=downloader.AUDIO,
        )

        self.assertEqual(options["format"], "bestaudio/best")
        self.assertEqual(options["postprocessors"][0]["key"], "FFmpegExtractAudio")
        self.assertEqual(options["postprocessors"][0]["preferredquality"], "0")
        self.assertEqual(
            options["outtmpl"],
            str(output_dir / "%(title)s [%(id)s].%(ext)s"),
        )

    def test_platform_cookie_precedes_generic_cookie(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            generic = project_dir / "cookies.txt"
            platform_cookie = project_dir / "bilibili_cookies.txt"
            generic.touch()
            platform_cookie.touch()

            with patch.object(downloader, "PROJECT_DIR", project_dir):
                self.assertEqual(
                    downloader._find_cookie_file(downloader.BILIBILI),
                    platform_cookie,
                )

    def test_membership_error_points_to_bilibili_cookie(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            downloader._handle_download_error(
                "This video is for premium members only",
                downloader.BILIBILI,
            )

        self.assertIn("Bilibili", output.getvalue())
        self.assertIn("bilibili_cookies.txt", output.getvalue())
```

- [ ] **Step 2: Run the option tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_bilibili_support.BilibiliDownloadOptionsTests -v`

Expected: FAIL because Bilibili currently falls into the Instagram-only option branch and lacks membership guidance.

- [ ] **Step 3: Separate platform-common, Instagram-only, and Bilibili options**

Refactor the first platform branch in `_build_ydl_options()`:

```python
    if platform == YOUTUBE:
        node_path = shutil.which("node")
        options["js_runtimes"] = {"node": {"path": node_path} if node_path else {}}
        options["remote_components"] = ["ejs:github"]
    elif platform == INSTAGRAM:
        options.update(
            {
                "outtmpl": str(output_dir / "%(title)s [%(id)s].%(ext)s"),
                "http_headers": {
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;"
                        "q=0.9,*/*;q=0.8"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                },
                "sleep_interval": 1,
                "max_sleep_interval": 3,
                "sleep_interval_requests": 1,
            }
        )
    elif platform == BILIBILI:
        options["outtmpl"] = str(output_dir / "%(title)s [%(id)s].%(ext)s")
```

Use the existing highest-quality YouTube selector for Bilibili video mode:

```python
    elif platform in {YOUTUBE, BILIBILI}:
        options.update(
            {
                "format": "bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
            }
        )
```

Leave the current audio branch before this condition so every platform continues to use the existing MP3 extraction settings.

- [ ] **Step 4: Add localized Bilibili access guidance**

Before the generic login branch in `_handle_download_error()`, add:

```python
    elif platform == BILIBILI and any(
        marker in msg
        for marker in ("premium", "member only", "members only", "login", "sign in")
    ):
        cookie_path = PROJECT_DIR / "bilibili_cookies.txt"
        print("\n❌ 错误：当前账号无权访问该 Bilibili 内容，或该内容需要登录/会员权限。")
        print("   请先确认浏览器中的 Bilibili 账号可以播放该视频。")
        print(f"   然后导出完整 Cookie 并保存为: {cookie_path}")
```

- [ ] **Step 5: Run Bilibili and existing downloader regression tests**

Run: `venv/bin/python -m unittest tests.test_bilibili_support.BilibiliDownloadOptionsTests tests.test_downloader_errors -v`

Expected: PASS, including unchanged YouTube and Instagram option tests.

- [ ] **Step 6: Commit Bilibili download options**

```bash
git add downloader.py tests/test_bilibili_support.py
git commit -m "feat: configure Bilibili video and audio downloads"
```

---

### Task 3: Expose Bilibili Through CLI, Web API, and Page Copy

**Files:**
- Modify: `tests/test_bilibili_support.py`
- Modify: `main.py:1-230`
- Modify: `app.py:1-190`
- Modify: `templates/index.html:580-645`

**Interfaces:**
- Consumes: `make_task()`, `PLATFORM_NAMES`, existing `/api/download`, and existing `startDownload(mediaType)`.
- Produces: user-visible three-platform prompts and API batches whose Bilibili task has `platform_name == "Bilibili"`.

- [ ] **Step 1: Write failing CLI, API, and template integration tests**

Append to `tests/test_bilibili_support.py`:

```python
from pathlib import Path
from unittest.mock import patch

import app as web_app
import main as cli_main


class BilibiliSurfaceIntegrationTests(unittest.TestCase):
    def setUp(self):
        web_app._batches.clear()
        self.client = web_app.app.test_client()

    def test_cli_accepts_bilibili_in_mixed_arguments(self):
        urls = [
            "https://youtu.be/example",
            "https://www.bilibili.com/video/BV1GJ411x7h7?p=2",
        ]

        tasks = cli_main.get_tasks_from_args(urls)

        self.assertEqual(tasks[1][0], downloader.BILIBILI)
        self.assertEqual(tasks[1][1], urls[1])

    def test_web_api_creates_bilibili_audio_task(self):
        url = "https://b23.tv/BV1GJ411x7h7"

        with patch("app.threading.Thread") as thread_class:
            response = self.client.post(
                "/api/download",
                json={"urls": [url], "media_type": downloader.AUDIO},
            )

        self.assertEqual(response.status_code, 200)
        batch = web_app._batches[response.get_json()["batch_id"]]
        self.assertEqual(batch["tasks"][0]["platform"], downloader.BILIBILI)
        self.assertEqual(batch["tasks"][0]["platform_name"], "Bilibili")
        self.assertEqual(thread_class.call_args.kwargs["args"][2], downloader.AUDIO)

    def test_page_names_bilibili_without_adding_new_input(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("YOUTUBE + INSTAGRAM + BILIBILI / ONLINE", html)
        self.assertIn("YouTube / Instagram / Bilibili", html)
        self.assertEqual(html.count('id="videoUrls"'), 1)
        self.assertEqual(html.count('id="audioUrls"'), 1)

    def test_cli_and_api_errors_name_all_supported_platforms(self):
        source = Path("main.py").read_text(encoding="utf-8")
        app_source = Path("app.py").read_text(encoding="utf-8")

        self.assertIn("YouTube、Instagram 或 Bilibili", source)
        self.assertIn("YouTube、Instagram 或 Bilibili", app_source)
```

- [ ] **Step 2: Run integration tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_bilibili_support.BilibiliSurfaceIntegrationTests -v`

Expected: CLI/API task creation passes after Task 1, while platform copy assertions fail.

- [ ] **Step 3: Synchronize CLI copy**

Update the module docstring and these strings in `main.py`:

```python
print(f"🎬 YouTube + Instagram + Bilibili {media_name}批量下载工具")
print("请逐行粘贴 YouTube、Instagram 或 Bilibili 视频链接，每行一个。")
print("三个平台的链接可以任意混合，输入空行后开始下载。")
print("⚠️  Instagram 与 Bilibili 的部分内容需要配置登录 Cookie。\n")
```

Use this invalid-input wording in both interactive and command-line paths:

```python
"受支持的 YouTube、Instagram 或 Bilibili 视频链接"
"未提供合法的 YouTube、Instagram 或 Bilibili 视频链接"
```

- [ ] **Step 4: Synchronize Web service and page copy**

Update `app.py` API error text to:

```python
return jsonify({"error": "未识别到任何受支持的 YouTube、Instagram 或 Bilibili 链接"}), 400
```

Update the startup label to:

```python
print("  🎬 Ytb/Ins/Bili Downloader — Web 模式")
```

Update existing template text without adding controls:

```html
<div class="hero-kicker">YOUTUBE + INSTAGRAM + BILIBILI / ONLINE</div>
<textarea class="url-input" id="videoUrls" aria-label="视频链接" placeholder="粘贴 YouTube / Instagram / Bilibili 视频链接，一行一个"></textarea>
```

- [ ] **Step 5: Run surface and existing Web/CLI regression tests**

Run: `venv/bin/python -m unittest tests.test_bilibili_support.BilibiliSurfaceIntegrationTests tests.test_cli_audio tests.test_web_progress -v`

Expected: PASS; the page still has exactly one video input and one audio input.

- [ ] **Step 6: Commit the user-facing integration**

```bash
git add main.py app.py templates/index.html tests/test_bilibili_support.py
git commit -m "feat: expose Bilibili in Web and CLI"
```

---

### Task 4: Document Bilibili Operation and Complete End-to-End Verification

**Files:**
- Modify: `tests/test_bilibili_support.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: the approved platform, URL, Cookie, output, and queue behavior from Tasks 1-3.
- Produces: a user-facing Bilibili runbook and final verified release state.

- [ ] **Step 1: Write the failing README coverage test**

Append to `tests/test_bilibili_support.py`:

```python
class BilibiliDocumentationTests(unittest.TestCase):
    def test_readme_documents_bilibili_workflow_and_boundaries(self):
        readme = Path("README.md").read_text(encoding="utf-8")

        required = [
            "YouTube + Instagram + Bilibili",
            "bilibili_cookies.txt",
            "https://www.bilibili.com/video/BV",
            "https://www.bilibili.com/video/av",
            "https://b23.tv/",
            "分 P",
            "只下载链接指定的分 P",
            "不自动展开合集、收藏夹或番剧",
            "标题 [内容ID].mp4",
            "标题 [内容ID].mp3",
        ]
        for text in required:
            with self.subTest(text=text):
                self.assertIn(text, readme)
```

- [ ] **Step 2: Run the documentation test and verify RED**

Run: `venv/bin/python -m unittest tests.test_bilibili_support.BilibiliDocumentationTests -v`

Expected: FAIL because the README currently names only YouTube and Instagram.

- [ ] **Step 3: Update every user-facing README surface**

Make these concrete documentation changes:

```markdown
# YouTube + Instagram + Bilibili 视频与 MP3 音频批量下载工具
```

Add `bilibili_cookies.txt` to the project tree and Cookie instructions. Add rows for `BV`, `av`, mobile, multipart, and `b23.tv` links to the supported-link table. State exactly:

```markdown
Bilibili 分 P 视频只下载链接 `?p=` 指定的分 P；未指定时下载第 1 P。程序不自动展开合集、收藏夹或番剧。
```

Document Bilibili filenames:

```markdown
- Bilibili 文件名附加内容 ID：视频为 `标题 [内容ID].mp4`，音频为 `标题 [内容ID].mp3`。
```

Update mixed-input examples, Web steps, troubleshooting, and compliance text to name all three platforms.

- [ ] **Step 4: Run the focused documentation test**

Run: `venv/bin/python -m unittest tests.test_bilibili_support.BilibiliDocumentationTests -v`

Expected: PASS.

- [ ] **Step 5: Run full automated verification**

Run: `venv/bin/python -m unittest discover -s tests -v`

Expected: all tests PASS.

Run: `venv/bin/python -m compileall -q app.py downloader.py main.py tests`

Expected: exit code 0 with no syntax errors.

Run: `zsh -c "sed -n '/^<script>$/,/^<\\/script>$/p' templates/index.html | sed '1d;\$d' | node --check"`

Expected: exit code 0.

Run: `git diff --check`

Expected: exit code 0 with no whitespace errors.

- [ ] **Step 6: Verify Flask API state flow without downloading media**

Run:

```bash
venv/bin/python -m unittest \
  tests.test_bilibili_support.BilibiliSurfaceIntegrationTests.test_web_api_creates_bilibili_audio_task \
  tests.test_web_progress.WebProgressStateTests.test_completion_clears_stale_progress_metrics -v
```

Expected: both tests PASS, confirming Bilibili API classification and unchanged terminal state behavior.

- [ ] **Step 7: Perform optional live metadata smoke checks when network access is available**

Run:

```bash
venv/bin/python -c 'import yt_dlp; urls=["https://www.bilibili.com/video/BV1GJ411x7h7", "https://b23.tv/BV1GJ411x7h7"]; opts={"quiet": True, "skip_download": True, "noplaylist": True}; [(lambda info: print(info.get("extractor_key"), info.get("id"), info.get("title")))(yt_dlp.YoutubeDL(opts).extract_info(url, download=False)) for url in urls]'
```

Expected when the network and Bilibili permit access: two metadata lines with a Bilibili extractor, content ID, and title; no media file is created. If external access is unavailable, record that the network smoke check was not completed and rely on deterministic tests rather than claiming it passed.

- [ ] **Step 8: Restart only the verified project service and inspect served HTML**

Resolve the PID with `lsof -nP -iTCP:8233 -sTCP:LISTEN`, verify its cwd with `lsof -a -p <PID> -d cwd -Fn`, and stop it only when the cwd is `/Users/markyang/Projects/Ytb_Ins_Video_Download`. Start `venv/bin/python app.py`, then request `http://127.0.0.1:8233/` and verify the response contains `BILIBILI`, `videoUrls`, and `audioUrls`.

- [ ] **Step 9: Commit documentation and final verification coverage**

```bash
git add README.md tests/test_bilibili_support.py
git commit -m "docs: explain Bilibili download workflow"
```
