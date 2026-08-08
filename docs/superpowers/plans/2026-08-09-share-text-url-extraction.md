# Share Text URL Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Web, CLI, and API users paste platform share text containing a video URL while storing only the clean, validated URL in the download queue.

**Architecture:** Extend `downloader.py::normalize_url()` with one shared HTTP(S) URL extractor and trailing-punctuation cleaner. Keep `detect_platform()` as the validation boundary, so all entrypoints gain the behavior without frontend-only or Bilibili-only parsing.

**Tech Stack:** Python 3, Flask, vanilla HTML/JavaScript, `unittest`

## Global Constraints

- Extract only the first explicit `http://` or `https://` URL from each input line.
- Preserve query parameters such as `vd_source` and `p`.
- Strip only trailing common Chinese/English wrappers and sentence punctuation.
- Preserve existing pure URL and protocol-less pure-domain behavior.
- Do not split multiple URLs in one line into multiple tasks.
- Extracted URLs must still pass existing platform and video-path validation.
- Do not change formats, cookies, filenames, concurrency, progress events, or page layout.

---

### Task 1: Extract and Validate URLs from Share Text in the Shared Core

**Files:**
- Modify: `tests/test_bilibili_support.py`
- Modify: `downloader.py:20-180`

**Interfaces:**
- Consumes: `normalize_url(url: str) -> str`, `detect_platform(url: str) -> Optional[str]`, and `make_task(url: str) -> Optional[VideoTask]`.
- Produces: `SHARE_URL_RE`, `TRAILING_URL_PUNCTUATION`, and a `normalize_url()` implementation that returns a clean URL candidate.

- [ ] **Step 1: Write failing shared URL extraction tests**

Add to `tests/test_bilibili_support.py`:

```python
class ShareTextUrlExtractionTests(unittest.TestCase):
    def test_extracts_user_provided_bilibili_share_text(self):
        share_text = (
            "【【梗百科】不X你们X什么是啥梗？！】"
            "https://www.bilibili.com/video/BV1xRuu6fEeA"
            "?vd_source=c29bf1bb20fc12664dae270045332759"
        )
        expected = (
            "https://www.bilibili.com/video/BV1xRuu6fEeA"
            "?vd_source=c29bf1bb20fc12664dae270045332759"
        )

        self.assertEqual(downloader.normalize_url(share_text), expected)
        self.assertEqual(
            downloader.make_task(share_text),
            (downloader.BILIBILI, expected),
        )

    def test_removes_trailing_share_punctuation_but_keeps_query(self):
        share_text = (
            "推荐：https://www.bilibili.com/video/BV1xRuu6fEeA?p=2】。"
        )

        self.assertEqual(
            downloader.normalize_url(share_text),
            "https://www.bilibili.com/video/BV1xRuu6fEeA?p=2",
        )

    def test_shared_parser_also_handles_youtube_and_instagram_text(self):
        cases = [
            (
                "观看 (https://www.youtube.com/watch?v=abc123).",
                downloader.YOUTUBE,
                "https://www.youtube.com/watch?v=abc123",
            ),
            (
                "Reel：https://www.instagram.com/reel/ABC123/！",
                downloader.INSTAGRAM,
                "https://www.instagram.com/reel/ABC123/",
            ),
        ]

        for share_text, platform, expected in cases:
            with self.subTest(share_text=share_text):
                self.assertEqual(
                    downloader.make_task(share_text),
                    (platform, expected),
                )

    def test_rejects_text_without_url_and_non_video_url(self):
        self.assertIsNone(downloader.make_task("只有标题，没有链接"))
        self.assertIsNone(
            downloader.make_task("主页 https://space.bilibili.com/2。")
        )
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_bilibili_support.ShareTextUrlExtractionTests -v`

Expected: FAIL because the current normalizer prefixes the whole share text with `https://` instead of extracting the embedded URL.

- [ ] **Step 3: Implement minimal shared URL extraction**

Add constants near `ANSI_ESCAPE_RE` in `downloader.py`:

```python
SHARE_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
TRAILING_URL_PUNCTUATION = "】）》」』〕〉)]}>\"',.!?;:，。！？；："
```

Replace `normalize_url()` with:

```python
def normalize_url(url: str) -> str:
    """提取输入中的首个 HTTP(S) URL，清理末尾标点并补全协议。"""
    value = url.strip()
    match = SHARE_URL_RE.search(value)
    normalized = match.group(0) if match else value
    normalized = normalized.rstrip(TRAILING_URL_PUNCTUATION)
    if normalized and not re.match(r"^https?://", normalized, re.IGNORECASE):
        normalized = f"https://{normalized}"
    return normalized
```

- [ ] **Step 4: Run focused and platform regression tests**

Run: `venv/bin/python -m unittest tests.test_bilibili_support.ShareTextUrlExtractionTests tests.test_bilibili_support.BilibiliUrlDetectionTests tests.test_parallel_downloads -v`

Expected: all tests PASS; clean URLs and concurrency behavior remain unchanged.

- [ ] **Step 5: Commit the shared parser**

```bash
git add downloader.py tests/test_bilibili_support.py
git commit -m "feat: extract URLs from platform share text"
```

---

### Task 2: Verify API Normalization and Document the Input Behavior

**Files:**
- Modify: `tests/test_bilibili_support.py`
- Modify: `templates/index.html:615-645`
- Modify: `README.md:150-320`

**Interfaces:**
- Consumes: `make_task()` normalization in `/api/download` and the existing `videoUrls`/`audioUrls` inputs.
- Produces: Web batches containing only the clean URL plus clear page and README instructions.

- [ ] **Step 1: Write failing API, template, and documentation tests**

Add to `tests/test_bilibili_support.py`:

```python
class ShareTextSurfaceTests(unittest.TestCase):
    def setUp(self):
        web_app._batches.clear()
        self.client = web_app.app.test_client()

    def test_web_api_stores_only_clean_url_from_share_text(self):
        share_text = (
            "【视频】https://www.bilibili.com/video/BV1xRuu6fEeA"
            "?vd_source=source123"
        )
        expected = (
            "https://www.bilibili.com/video/BV1xRuu6fEeA"
            "?vd_source=source123"
        )

        with patch("app.threading.Thread"):
            response = self.client.post(
                "/api/download",
                json={"urls": [share_text], "media_type": downloader.VIDEO},
            )

        self.assertEqual(response.status_code, 200)
        batch = web_app._batches[response.get_json()["batch_id"]]
        self.assertEqual(batch["tasks"][0]["url"], expected)

    def test_page_and_readme_explain_share_text_input(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertGreaterEqual(html.count("链接或平台分享文案"), 2)
        self.assertIn("可以直接粘贴平台生成的分享文案", readme)
        self.assertIn("自动忽略标题并提取其中的第一个 HTTP(S) 链接", readme)
        self.assertIn("【【梗百科】", readme)
```

- [ ] **Step 2: Run the surface tests and verify RED**

Run: `venv/bin/python -m unittest tests.test_bilibili_support.ShareTextSurfaceTests -v`

Expected: the API normalization test passes after Task 1, while template and README assertions fail.

- [ ] **Step 3: Update both existing input placeholders**

Use these placeholders without adding controls:

```html
placeholder="粘贴 YouTube / Instagram / Bilibili 链接或平台分享文案，一行一个"
placeholder="粘贴音频链接或平台分享文案，一行一个"
```

- [ ] **Step 4: Add README instructions and the exact Bilibili example**

Add this paragraph near the CLI/Web input instructions:

````markdown
可以直接粘贴平台生成的分享文案，每行仍表示一个任务。程序会自动忽略标题并提取其中的第一个 HTTP(S) 链接，例如：

```text
【【梗百科】不X你们X什么是啥梗？！】https://www.bilibili.com/video/BV1xRuu6fEeA?vd_source=c29bf1bb20fc12664dae270045332759
```
````

- [ ] **Step 5: Run focused surface and existing Web tests**

Run: `venv/bin/python -m unittest tests.test_bilibili_support.ShareTextSurfaceTests tests.test_web_progress -v`

Expected: all tests PASS and exactly one video input plus one audio input remain.

- [ ] **Step 6: Run complete verification**

Run: `venv/bin/python -m unittest discover -s tests -v`

Expected: all tests PASS.

Run: `venv/bin/python -m compileall -q app.py downloader.py main.py tests`

Expected: exit code 0.

Run: `zsh -c "sed -n '/^<script>$/,/^<\\/script>$/p' templates/index.html | sed '1d;\$d' | node --check"`

Expected: exit code 0.

Run: `git diff --check`

Expected: exit code 0.

- [ ] **Step 7: Restart and inspect the 8233 service**

Verify the listener PID and cwd before stopping it. Start `venv/bin/python app.py` from the implementation branch, request `http://127.0.0.1:8233/`, and confirm the served HTML contains `链接或平台分享文案` twice.

- [ ] **Step 8: Commit the user-facing documentation**

```bash
git add README.md templates/index.html tests/test_bilibili_support.py
git commit -m "docs: explain platform share text input"
```
