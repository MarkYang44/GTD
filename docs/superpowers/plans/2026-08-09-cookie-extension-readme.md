# Cookie Extension README Instructions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the Chinese README with safe, official, step-by-step browser extension instructions for exporting YouTube, Instagram, and Bilibili cookies in the format this project consumes.

**Architecture:** Keep this as a documentation-only change. Add a focused documentation regression test that inspects only the README Cookie section, then replace the current five-line overview with verified Chrome/Edge and Firefox installation links, platform-specific export naming, activation steps, and credential-safety warnings.

**Tech Stack:** Markdown, Python `unittest`, existing project documentation tests

## Global Constraints

- Recommend only the open-source **Get cookies.txt LOCALLY** extension.
- Link only to the Chrome Web Store, Mozilla Add-ons, and the author's GitHub repository.
- Export format must be Netscape `cookies.txt`.
- Exact platform filenames are `youtube_cookies.txt`, `instagram_cookies.txt`, and `bilibili_cookies.txt`; `cookies.txt` remains only the generic fallback.
- Do not modify downloader behavior, install an extension, or read any existing Cookie file.
- Warn that Cookie files are login credentials and must never be uploaded, shared, screenshotted, or committed to Git.

---

### Task 1: Add Verified Cookie Extension Installation and Export Instructions

**Files:**
- Modify: `README.md:355-367`
- Modify: `tests/test_bilibili_support.py:487-521`

**Interfaces:**
- Consumes: the existing README section boundaries `## 六、需要登录时配置 Cookie` and `## 七、常见问题`.
- Produces: a self-contained Cookie runbook for Chrome, Edge, and Firefox users, plus a regression test that locks its required links and safety rules.

- [ ] **Step 1: Write the failing documentation test**

Append this test class after `BilibiliDocumentationTests` in `tests/test_bilibili_support.py`:

```python
class CookieExtensionDocumentationTests(unittest.TestCase):
    def test_readme_documents_cookie_extension_install_and_export(self):
        readme = Path("README.md").read_text(encoding="utf-8")
        cookie_section = readme.split(
            "## 六、需要登录时配置 Cookie",
            maxsplit=1,
        )[1].split("## 七、常见问题", maxsplit=1)[0]

        required = [
            "Get cookies.txt LOCALLY",
            "https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc",
            "https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt-locally/",
            "https://github.com/kairi003/Get-cookies.txt-LOCALLY",
            "Chrome / Edge 安装",
            "Firefox 安装",
            "Netscape",
            "# Netscape HTTP Cookie File",
            "仅导出当前平台域名",
            "youtube_cookies.txt",
            "instagram_cookies.txt",
            "bilibili_cookies.txt",
            "重启 8233 Web 服务",
            "不要上传、分享、截图或提交到 Git",
        ]
        for text in required:
            with self.subTest(text=text):
                self.assertIn(text, cookie_section)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
venv/bin/python -m unittest \
  tests.test_bilibili_support.CookieExtensionDocumentationTests -v
```

Expected: FAIL because the README does not yet contain `Get cookies.txt LOCALLY` and the official store links.

- [ ] **Step 3: Replace the README Cookie overview with the complete runbook**

Keep the existing `## 六、需要登录时配置 Cookie` heading and introductory paragraph, then replace its current numbered list and short warning with:

```markdown
### 安装可信的 Cookie 导出扩展

本项目推荐开源扩展 **Get cookies.txt LOCALLY**。请通过下面的官方页面安装，并核对扩展名称及 GitHub 仓库；不要安装名称相似的旧版 **Get cookies.txt** 或来源不明的同名扩展。

- Chrome / Edge：[Chrome Web Store 安装页面](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
- Firefox：[Mozilla Add-ons 安装页面](https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt-locally/)
- 源代码与隐私说明：[kairi003/Get-cookies.txt-LOCALLY](https://github.com/kairi003/Get-cookies.txt-LOCALLY)

#### Chrome / Edge 安装

1. 打开上面的 Chrome Web Store 页面。
2. Chrome 点击 **“添加至 Chrome”**；Edge 点击 **“获取”**，若浏览器提示允许来自其他应用商店的扩展，请先确认页面域名确实是 `chromewebstore.google.com` 再允许。
3. 在浏览器扩展菜单中固定 **Get cookies.txt LOCALLY**，方便在目标平台页面使用。

#### Firefox 安装

1. 打开上面的 Mozilla Add-ons 页面。
2. 点击 **“添加到 Firefox”**，阅读权限说明后确认安装。
3. 在扩展管理器中允许该扩展访问目标平台页面；否则它无法读取并导出当前站点 Cookie。

### 按平台导出 Cookie

YouTube、Instagram 和 Bilibili 分别执行一次以下步骤，不要把三个站点的 Cookie 混在同一个平台专用文件中：

1. 在浏览器中登录目标平台，并打开该平台的视频页面，确认当前账号能够正常播放目标内容。
2. 保持目标平台页面为当前标签页，打开 **Get cookies.txt LOCALLY**。
3. 选择 **Netscape** 格式，使用扩展的当前站点导出功能，仅导出当前平台域名的 Cookie。
4. 保存文件后，用纯文本编辑器打开并检查首行包含 `# Netscape HTTP Cookie File`。不要修改后续 Cookie 行。
5. 将文件移动到本项目根目录，与 `main.py` 同级，并按平台重命名：

| 当前登录平台 | 建议打开的页面 | 保存文件名 |
|---|---|---|
| YouTube | `https://www.youtube.com/` | `youtube_cookies.txt` |
| Instagram | `https://www.instagram.com/` | `instagram_cookies.txt` |
| Bilibili | `https://www.bilibili.com/` | `bilibili_cookies.txt` |

平台专用 Cookie 优先于通用 `cookies.txt`。建议使用上表中的独立文件名；只有确实需要一个通用回退文件时才使用 `cookies.txt`。

### 让新 Cookie 生效

- CLI：结束当前命令后重新运行 `python main.py`。
- Web：停止正在运行的服务，重新执行 `python app.py`，即重启 8233 Web 服务，然后刷新页面并重新提交任务。
- 如果仍然提示登录、`HTTP 403` 或 Bilibili `HTTP 412`，先确认浏览器中的登录状态仍有效，再重新导出对应平台 Cookie。Cookie 过期或账号退出后必须重新导出。

### Cookie 安全

Cookie 文件等同于登录凭证。不要上传、分享、截图或提交到 Git，也不要粘贴到聊天、Issue 或日志中。扩展只应从上述官方商店链接安装。若 Cookie 已泄露，应立即在对应平台退出其他会话或撤销登录状态，必要时修改密码，然后删除旧文件并重新导出。
```

- [ ] **Step 4: Run focused documentation tests and verify GREEN**

Run:

```bash
venv/bin/python -m unittest \
  tests.test_bilibili_support.BilibiliDocumentationTests \
  tests.test_bilibili_support.CookieExtensionDocumentationTests -v
```

Expected: both documentation test classes pass.

- [ ] **Step 5: Run complete verification**

Run:

```bash
venv/bin/python -m unittest discover -s tests -v
venv/bin/python -m compileall -q downloader.py bilibili_acceleration.py app.py main.py tests
git diff --check
git status --short
```

Expected: all tests pass, compileall and diff checks exit 0, and status lists only `README.md`, `tests/test_bilibili_support.py`, and this plan if it has not yet been committed.

- [ ] **Step 6: Commit the documentation update**

```bash
git add README.md tests/test_bilibili_support.py
git commit -m "docs: explain cookie extension setup"
```
