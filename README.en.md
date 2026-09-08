# GTD

[中文](README.md) | **English**

**Generalized Transmedia Downloader**

GTD stands for Generalized Transmedia Downloader.

A multi-platform media downloader designed for downloading and processing media from multiple online platforms.

Batch-download YouTube, Instagram, and Bilibili videos and audio in multiple formats.

Built on [yt-dlp](https://github.com/yt-dlp/yt-dlp), GTD supports both a **command-line interface** and a **web interface**. It automatically recognizes YouTube, Instagram, and Bilibili links within the same batch, previews playlists, collections, and multipart videos, and downloads videos or audio in **MP3 V0 / source FLAC / original audio / WAV PCM** format. Enter a download directory or choose one with the system folder picker; the default remains the project's `downloads/` folder.

## Features

- Enter multiple YouTube, Instagram, and Bilibili links at once
- Process up to 3 links concurrently per batch, with additional tasks queued automatically
- Mix links from all three platforms; the platform is detected automatically
- Preview and select playlist, collection, and multipart entries before submitting; select up to 100 items per batch, with previews capped at the first 1,000 items and an explicit truncation notice
- Automatically select the highest available video and audio quality on YouTube
- Audio mode selects the highest-quality source track available and outputs MP3 V0, genuine source FLAC, original audio, or WAV PCM
- Embed source artwork in audio and MP4 video whenever possible; randomly use a built-in fallback image when the source has no artwork
- Instagram support for Reels, video posts, IGTV, and unexpired Stories
- Bilibili support for `BV`, `av`, mobile video, multipart links, and `b23.tv` short links
- Adaptive speed testing across up to 4 source-provided CDN hosts for Bilibili files larger than 50 MiB; optional aria2c Turbo Mode
- FFmpeg merges video and audio into MP4 and processes MP3 / FLAC / WAV audio
- **Command-line mode**: interactive input and command-line arguments
- **Web mode**: separate video and audio input areas, collection selection, cancellation, retries, and downloading again, with live task status, speed, and estimated time remaining
- **Shared website language switch**: switch between Chinese and English on the download page, user guide, Circuit Guide, and Victory Archive; your browser remembers the choice across pages
- **Custom download directory**: enter a path in the CLI or web interface; Windows uses a precompiled, cached, DPI-aware modern Explorer-style folder dialog, while macOS uses its system folder picker; leave blank to use `downloads/`
- Continue processing other tasks when an individual link fails
- Stable error codes and actionable suggestions; automatically rotated, redacted JSONL logs
- General or platform-specific cookie files
- A completion summary with successes, failures, and file paths

## Directory Structure

```text
GTD/
├── main.py                      # CLI entry point
├── app.py                       # Web server entry point
├── downloader.py                # Shared download core for main.py and app.py
├── media_cover.py               # Final-media artwork detection and random fallback
├── bilibili_acceleration.py     # Bilibili CDN testing, cache, and Turbo Mode policy
├── collection_resolver.py       # Playlist, collection, and multipart preview/selection
├── task_control.py              # Web queue, cancellation, retries, and downloading again
├── download_errors.py           # Structured error codes and user suggestions
├── download_logging.py          # Redacted, rotating JSONL logs
├── folder_picker.py             # Native Windows / macOS folder picker
├── guide_renderer.py            # Safe Markdown renderer for the web user guide
├── assets/fallback_covers/      # 6 built-in fallback artwork images
├── docs/
│   └── WEB_GUIDE.md             # Documentation focused on web usage
├── templates/
│   ├── index.html               # Main web interface
│   └── guide.html               # Web user guide
├── requirements.txt             # Python dependencies
├── README.md                    # Chinese documentation
├── README.en.md                 # English documentation
├── cookies.txt                  # Optional: general cookies
├── youtube_cookies.txt          # Optional: YouTube cookies
├── instagram_cookies.txt        # Optional: Instagram cookies
├── bilibili_cookies.txt         # Optional: Bilibili cookies
├── downloads/                   # Created automatically on the first download
└── logs/                        # Created when the first task event is logged
```

All cookie files are optional; there is no need to create them unless you use cookies. Platform-specific cookies take priority over `cookies.txt`.

## 1. Set Up the Environment

Install:

- Python 3.10 or later
- pip
- FFmpeg

Download or clone this project, then open its root directory in a terminal:

```bash
git clone https://github.com/MarkYang44/GTD.git
cd GTD
```

If the project is already on your computer, replace the example paths below with its actual location.

macOS (Terminal):

```bash
cd /path/to/GTD
```

Windows (PowerShell):

```powershell
cd "C:\path\to\GTD"
```

> Enclose the entire path in quotes if it contains spaces, on both macOS and Windows.

Check your Python version:

macOS:

```bash
python3 --version
python3 -m pip --version
```

Windows (PowerShell):

```powershell
python --version
python -m pip --version
```

Create and activate a virtual environment:

macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If the Windows PowerShell execution policy blocks the activation script, use the virtual environment's Python directly without activating it:

```powershell
.\venv\Scripts\python.exe -m pip --version
```

Install the Python dependencies:

macOS (virtual environment activated):

```bash
python -m pip install -r requirements.txt
```

Windows PowerShell (activation not required):

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` installs both yt-dlp and `mutagen`. The latter detects and writes artwork metadata for MP3, FLAC, M4A/MP4, OGG, and Opus. Install from the dependency file rather than installing only yt-dlp.

The default direct dependency baseline pins yt-dlp `2026.7.4`, Flask `3.1.3`, and Mutagen `1.48.1`. pip still resolves transitive dependencies for your Python version and operating system; this is not a complete cross-platform lock file. Both entrypoints show an upgrade message below Python 3.10. Recreate your virtual environment after upgrading Python.

If platform changes break extraction, you can explicitly opt into yt-dlp's upstream development version:

```bash
python -m pip install --upgrade --force-reinstall --no-cache-dir -r requirements-update.txt
```

This channel changes with upstream and may behave differently from the baseline. Restore the baseline with `python -m pip install --force-reinstall -r requirements.txt`. Restart the web server after updating or restoring dependencies.

The examples below assume the virtual environment is active and use `python`. If it is not active in Windows PowerShell, replace the initial `python` with `.\venv\Scripts\python.exe`; for example, start the website with `.\venv\Scripts\python.exe app.py`.

## 2. Install FFmpeg

FFmpeg merges the highest-quality video and audio streams, packages MP4 files, and handles MP3, FLAC, original audio packaging, WAV, and artwork. Some video and audio outputs cannot be completed without FFmpeg.

macOS:

```bash
brew install ffmpeg
ffmpeg -version
```

Ubuntu / Debian:

```bash
sudo apt update
sudo apt install ffmpeg
ffmpeg -version
```

Windows:

1. Download a Windows build from the [FFmpeg download page](https://ffmpeg.org/download.html).
2. Extract it and add its `bin` directory to your system `PATH`.
3. Reopen PowerShell and run `ffmpeg -version` to verify the installation.

On any operating system, GTD can find FFmpeg if `ffmpeg -version` works in your terminal.

### Optional: Install aria2c for Turbo Mode

Standard Mode does not require aria2c. On macOS, install it to enable Bilibili Turbo Mode:

```bash
brew install aria2
aria2c --version
```

In Windows PowerShell, install the official Windows build in the project directory without changing the system `PATH`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_aria2_windows.ps1
```

The project checks, in order: `MVD_ARIA2C_PATH`, `ARIA2C_PATH`, the project's
`tools\aria2\aria2c.exe`, the system `PATH`, WinGet Links, actual WinGet package directories, and
Scoop shims. Restart the web server after installation so the page can refresh its capability status.

If aria2c is missing or fails, GTD automatically falls back to Standard Mode. YouTube and Instagram do not use this accelerator.

---

## 3. Command-Line Mode

### Option A: Interactive Batch Input

From the project directory, with the virtual environment active, run (macOS and Windows):

```bash
python main.py
```

First choose a download type: press Enter or enter `1` for video, or enter `2` for audio. For audio, choose MP3 V0, source FLAC, original audio, or WAV PCM. Then keep the default `downloads/`, enter a directory, or open the system folder picker on Windows/macOS. Finally, enter links one per line, mixing YouTube, Instagram, and Bilibili as needed.

You can paste a platform's full share text; each line still represents one task. GTD ignores the title and extracts the first HTTP(S) link. For example:

```text
【【梗百科】不X你们X什么是啥梗？！】https://www.bilibili.com/video/BV1xRuu6fEeA?vd_source=c29bf1bb20fc12664dae270045332759
```

The CLI prompts remain in Chinese:

```text
链接 1（空行结束）: https://www.youtube.com/watch?v=xxxx
链接 2（空行结束）: https://www.instagram.com/reel/yyyy/
链接 3（空行结束）: https://www.bilibili.com/video/BV1GJ411x7h7
链接 4（空行结束）:
```

After the final link, press Enter again to submit a blank line. If a playlist, collection, or multipart video is detected, GTD displays ordered entries first. Enter a selection such as `all` or `1,3-5` (up to 100 items), review the tasks, then press Enter or type `y` at `开始下载？(Y/n):` (Start downloading?).

### Option B: Pass Multiple Links as Arguments

Download video (the default):

macOS:

```bash
python main.py \
  "https://www.youtube.com/watch?v=xxxx" \
  "https://www.instagram.com/reel/yyyy/" \
  "https://www.bilibili.com/video/BV1GJ411x7h7?p=2"
```

Windows PowerShell:

```powershell
python main.py `
  "https://www.youtube.com/watch?v=xxxx" `
  "https://www.instagram.com/reel/yyyy/" `
  "https://www.bilibili.com/video/BV1GJ411x7h7?p=2"
```

Download only the highest-quality available audio and convert it to MP3:

macOS:

```bash
python main.py --audio \
  "https://www.youtube.com/watch?v=xxxx" \
  "https://www.instagram.com/reel/yyyy/" \
  "https://b23.tv/BV1GJ411x7h7"
```

Windows PowerShell:

```powershell
python main.py --audio `
  "https://www.youtube.com/watch?v=xxxx" `
  "https://www.instagram.com/reel/yyyy/" `
  "https://b23.tv/BV1GJ411x7h7"
```

Request source FLAC (lossless output is available only when the source actually provides FLAC):

```bash
python main.py --audio --flac "https://www.bilibili.com/video/BV1fsTM6CE9P"
```

If the content has no FLAC track, the task continues with MP3 V0 and a message stating that the source does not provide FLAC and GTD has automatically fallen back to MP3 V0.

Use the unified `--audio-format` option to choose among all four outputs:

```bash
python main.py --audio --audio-format mp3 "https://youtu.be/xxxx"
python main.py --audio --audio-format flac "https://www.bilibili.com/video/BV1fsTM6CE9P"
python main.py --audio --audio-format source "https://youtu.be/xxxx"
python main.py --audio --audio-format wav "https://youtu.be/xxxx"
```

`source` preserves the actual codec and extension of the source track selected by yt-dlp. `wav` decodes to uncompressed PCM, usually producing a much larger file, but cannot restore lossless quality from a lossy source. The older `--audio --flac` syntax remains supported and is equivalent to `--audio --audio-format flac`.

Specify a download directory (created automatically if it does not exist):

macOS:

```bash
python main.py --output-dir "$HOME/Movies/GTD" "https://youtu.be/xxxx"
```

Windows PowerShell:

```powershell
python main.py --output-dir "D:\Media\GTD" "https://youtu.be/xxxx"
```

`--download-dir` is an alias for `--output-dir`. Relative paths are resolved from the project root, and the directory must be creatable and writable. Omitting the option or passing an empty value preserves the default project-local `downloads/` directory.

When downloading playlists, collections, or Bilibili multipart videos through command-line arguments, explicitly select the entries:

```bash
# Download the first 5 items
python main.py --items 1-5 "https://www.youtube.com/playlist?list=xxxx"

# Download all available items; more than 100 is rejected with a request to narrow the selection
python main.py --audio --audio-format source --items all \
  "https://www.bilibili.com/video/BVxxxxxxxxxx"
```

Enable optional Turbo Mode for Bilibili video:

```bash
python main.py --turbo "https://www.bilibili.com/video/BV1xRuu6fEeA"
```

Enable optional Turbo Mode for Bilibili MP3 audio:

```bash
python main.py --audio --turbo "https://www.bilibili.com/video/BV1xRuu6fEeA"
```

Argument mode starts downloading immediately without a second confirmation. For collections without `--items`, it stops with a Chinese message to prevent unintended full-list downloads. `--flac` and `--audio-format` require `--audio`. Place `--audio`, `--audio-format`, `--output-dir`, `--items`, and `--turbo` before the URLs. Without `--turbo`, GTD always uses Standard Mode. Quote links and directories containing spaces to prevent the terminal from interpreting special characters. macOS uses a backslash `\` for line continuation; Windows PowerShell uses a backtick `` ` ``. You can also write the entire command on one line.

### View Download Results

The final video summary shows the platform, title, resolution, file size, and save path. The audio summary shows the actual output format, source codec/bitrate, any FLAC fallback, file size, and save path. Without a custom directory, files are saved under `downloads/` in the project root:

```text
GTD/
└── downloads/
```

If a link fails, GTD continues with the remaining links and lists failures in the final summary.

---

## 4. Web Mode

You can also use GTD through a local browser interface.

### Start the Web Server

From the project directory, with the virtual environment active, run (macOS and Windows):

```bash
python app.py
```

The startup output is in Chinese:

```text
========================================================
  🎬 GTD — Generalized Transmedia Downloader — Web 模式
========================================================
  本机访问:    http://127.0.0.1:8233
  局域网访问:  http://<本机局域网 IP>:8233
  默认下载目录: /项目实际路径/GTD/downloads
  按 Ctrl+C 停止服务
========================================================
```

It lists the local URL, LAN URL, default download directory, and the `Ctrl+C` shortcut to stop the server.

### Open in a Browser

On the Mac running the server, open **http://127.0.0.1:8233**.

Other devices on the same LAN can use **http://<server LAN IP>:8233**. Run `ipconfig getifaddr en0` in the Mac terminal to find its Wi-Fi LAN IP. If the macOS firewall asks whether Python may accept incoming connections, allow it. Guest networks or Wi-Fi with client isolation may prevent devices from reaching each other.

> The web server has no login authentication. Any device on the LAN that can reach this Mac can submit download tasks. Do not forward port 8233 to the public internet.

Use **User Guide** in the upper-right corner of the main page to open `/guide`, a concise guide focused on web usage.

### Extract audio from a local video

Choose **Extract audio from a local video** on the homepage, or open `/extract-audio`. Drop or select one local video (up to 2 GiB), choose **Original audio** or **MP3 V0**, and start extraction. Original audio copies the stream without re-encoding, using the default audio track or the first track when no default is set. AAC normally produces M4A; other extensions depend on the codec. Extraction cannot improve the source quality.

Upload and processing progress are shown separately. Extraction shares the existing queue, cancellation/retry, and task history. Results are saved to the default `downloads` folder and can also be saved with **Download audio**. Upload copies are staged in `state/audio_uploads` for 24 hours; expired inactive copies are cleaned on startup, upload, or extraction-history refresh. Re-upload after expiration to retry. Staging is limited to 8 GiB / 256 files. Source videos are unchanged and completed outputs are not automatically removed.

### Switch the Website Language

The download page (`/`), user guide (`/guide`), Circuit Guide (`/kozekilmu/tracks`), and Victory Archive (`/kozekilmu`) share a **中文 / EN** switch in the upper-right corner. Your browser saves the selected language and applies it when you navigate to another page or refresh. Switching languages preserves entered links and current download tasks. The switch controls website text; source titles, filenames, and original third-party error details remain as provided. The CLI is unchanged.

Use the **Dark / Light** slider in the upper-right corner to switch themes. Dark is the default; light uses clean white and soft gray surfaces. Both keep Petronas green accents. Your theme preference is independent of language, remembered in this browser, and shared across pages and tabs.

This README uses separate Markdown files: follow **中文 | English** at the top to switch between the complete Chinese and English versions.

### Web Workflow

1. Paste links or share text into **Highest Quality Video** for video downloads, or use the separate **Highest Quality Audio** section for audio only.
2. Choose **MP3 V0**, **Source FLAC**, **Original Audio**, or **WAV PCM** for audio. Original audio extensions depend on the source stream. WAV files are larger without improving source quality. If FLAC is unavailable, GTD automatically falls back to MP3 V0.
3. Enter a Windows or macOS directory under **Download Location**, or click **Choose Folder** to open the system picker on the computer running the web server. Leave it blank to use the default `downloads/` shown on the page.
4. Clicking download first resolves the input. Individual content keeps one-click submission; playlists, collections, and multipart videos open a shared preview panel with item selection, select-all, and counts. Submit up to 100 items at once.
5. The video and audio cards each have an independent **Turbo Mode** switch. It is disabled if aria2c is unavailable and applies only to Bilibili.
6. All backend batches share up to 3 worker slots, with at most 2 Bilibili tasks running concurrently. Additional tasks remain queued and start when a slot becomes available.
7. The task list shows queued, downloading, non-interruptible turbo download, completed, failed, and canceled states, along with speed, estimated time remaining, progress, output specifications, and save paths.
8. Failed tasks show a stable `error_code`, an explanation, and suggestions in the selected website language. Expand each attempt to view its status and time.
9. Cancel queued or standard download tasks; retry failed or canceled tasks, or retry all eligible failed tasks in a batch. Download completed tasks again while keeping the original files.
10. Each input area has its own **Clear Input** button. Tasks retain the selected download directory for their batch; retrying or downloading again does not revert to the default directory.

> The web folder picker is invoked by the Mac running Flask and appears only on that Mac. Clicking from a phone or another computer does not open a picker on that remote device. If the system picker is unavailable, enter a folder path on the server Mac manually. The browser does not read or upload arbitrary local directory contents.

### Cancel, Retry, and Download Again

- **Cancel**: queued tasks are canceled immediately. Running standard tasks stop at the downloader's next cooperative checkpoint and clean up temporary files created by that attempt.
- **aria2c turbo tasks**: once a task becomes non-interruptible, no cancel button is available; wait for it to finish. This is the intended Turbo Mode behavior.
- **Retry**: failed or canceled tasks reenter the same queue, preserving attempt records (the latest 20 are restored after a restart). Non-retryable errors do not offer a retry action.
- **Download again**: available only for completed tasks; creates a new task without overwriting the original file. New files use increasing suffixes such as `(2)` and `(3)`.
- **Batch retention**: Task history is saved locally in `state/tasks.sqlite3` (override with the `GTD_HISTORY_PATH` environment variable), including source URLs, output paths, and task results, but excluding cookie files and downloader internals. Up to 100 batches are retained by pruning the oldest finished batches; active batches are never pruned. Refreshing the page restores the current batch, and Task history lets you select older batches. After a server restart, unfinished tasks become retryable `INTERRUPTED` failures and require a manual retry; no downloads start automatically, and downloaded files are kept.

### Test Batch Downloads

Use these public test links to check the web interface:

```text
https://www.youtube.com/watch?v=jNQXAC9IVRw
https://www.youtube.com/watch?v=BaW_jenozKc
```

Paste both links into the video or audio area, one per line, and click its download button. Watch the tasks move from queued to downloading to completed.

### Stop the Web Server

Press `Ctrl+C` in the terminal to stop Flask.

---

## 5. Supported Links

| Platform | Type | Example |
|---|---|---|
| YouTube | Standard video | `https://www.youtube.com/watch?v=xxxx` |
| YouTube | Short link | `https://youtu.be/xxxx` |
| YouTube | Shorts | `https://www.youtube.com/shorts/xxxx` |
| YouTube | Live stream or replay | `https://www.youtube.com/live/xxxx` |
| YouTube | Embedded video | `https://www.youtube.com/embed/xxxx` |
| YouTube Music | Video | `https://music.youtube.com/watch?v=xxxx` |
| YouTube | Playlist | `https://www.youtube.com/playlist?list=xxxx` |
| YouTube | Video with a playlist parameter | `https://www.youtube.com/watch?v=xxxx&list=yyyy` |
| Instagram | Reels | `https://www.instagram.com/reel/xxxx/` |
| Instagram | Video post | `https://www.instagram.com/p/xxxx/` |
| Instagram | IGTV | `https://www.instagram.com/tv/xxxx/` |
| Instagram | Stories | `https://www.instagram.com/stories/username/xxxx/` |
| Bilibili | BV video | `https://www.bilibili.com/video/BV1GJ411x7h7` |
| Bilibili | av video | `https://www.bilibili.com/video/av170001` |
| Bilibili | Mobile video | `https://m.bilibili.com/video/BV1GJ411x7h7` |
| Bilibili | Specific part | `https://www.bilibili.com/video/BV1GJ411x7h7?p=2` |
| Bilibili | Multipart video | `https://www.bilibili.com/video/BVxxxxxxxxxx` |
| Bilibili | Collection / list | `https://www.bilibili.com/list/...`, `/medialist/...` |
| Bilibili | Creator collection | `https://space.bilibili.com/123/lists/...` |
| Bilibili | Short link | `https://b23.tv/BV1GJ411x7h7` |

GTD previews and selects entries from YouTube playlists, Bilibili multipart videos, `list` / `medialist` pages, and creator `lists` pages. Whether entries can be expanded depends on yt-dlp, page visibility, and current cookie permissions. Instagram posts with multiple videos can be previewed based on extractor results; image entries are marked unavailable for download.

Support is not guaranteed for Bilibili series batch pages, Watch Later, private favorites, or pages whose entries are not exposed to yt-dlp and require additional service APIs, DRM handling, or special account permissions. Parsing failures return `COLLECTION_EXTRACT_FAILED` instead of silently downloading the wrong content. Regardless of source size, select up to 100 items at a time. Each preview resolves at most 20 input lines and includes the first 1,000 entries. The web interface explicitly reports truncation; split links into separate previews to continue selecting.

### Output Filenames and Audio Quality

- YouTube video and audio files use content titles. Instagram and Bilibili filenames also include content IDs, such as `Video by author [ABC123].mp3`, `标题 [内容ID].mp4`, and `标题 [内容ID].mp3`, to prevent unrelated content with identical titles from overwriting each other.
- Audio filenames include actual specifications before the extension. For example, converting source FLAC at approximately 1521 kbps to MP3 produces `标题 [内容ID] [MP3 V0 · 源FLAC 1521kbps].mp3`; retaining the source produces `标题 [内容ID] [FLAC Lossless · 1521kbps].flac`.
- MP3 V0 first selects the highest-quality available source track, then converts it with FFmpeg's highest VBR quality setting. Even with Hi-Res FLAC input, the MP3 output remains lossy and cannot preserve genuinely lossless data.
- Source FLAC is output directly only when extraction actually provides a FLAC track. GTD does not transcode lossy AAC or Opus sources and present them as source FLAC. When FLAC is unavailable, it automatically falls back to MP3 V0.
- Source artwork always takes priority and is never replaced by fallback artwork. MP3, FLAC, M4A, OGG, Opus, and MP4 first attempt to embed the video's source artwork. If the final file still has no artwork, GTD randomly selects a built-in fallback and writes it to container metadata without creating extra JPG files in the download directory.
- Random selection runs independently for each download, so retries and repeat downloads may choose different images. WAV and WebM do not support artwork embedding in this workflow; GTD does not transcode or remux them solely to add artwork.
- Missing fallback assets, damaged media tags, or write failures only produce warnings. Artwork failures do not turn successful media downloads into failed tasks or delete or roll back downloaded files.

### Bilibili Download Acceleration

- For selected streams no larger than 50 MiB, or with an unknown size, GTD skips extra speed tests and retains native HTTP downloading with 10 MiB chunks.
- For streams larger than 50 MiB, it tests at most 4 HTTPS CDN hosts provided by Bilibili, reads a 512 KiB sample from each, then compares actual performance with 4 MiB and 10 MiB chunks.
- Speed-test results are cached in memory for 30 minutes. Restarting the web server or CLI process clears the cache.
- GTD does not modify or guess CDN domains or bypass platform permissions, abuse prevention, or rate limits.
- If aria2c is unavailable or fails, or the selected CDN returns `HTTP 403` / `HTTP 412`, GTD automatically falls back to Standard Mode or the original CDN and keeps trying.
- Actual speed depends on region, network routing, account status, and current Bilibili CDN load. No fixed improvement is guaranteed.

### Structured Error Codes and Logs

The website displays stable error codes with explanations and suggestions in the selected language, such as `AUTH_REQUIRED`, `NETWORK_TIMEOUT`, `RATE_LIMITED`, `FORMAT_UNAVAILABLE`, `COLLECTION_EXTRACT_FAILED`, `ARIA2_FAILED`, and `POSTPROCESS_FAILED`. CLI download errors use the same structure, with Chinese descriptions, to distinguish authentication, network, format, collection extraction, and postprocessing problems.

Task events are written to `logs/downloader.jsonl`, one JSON object per line. Logs rotate at 10 MiB and retain up to 5 backups. They record only task phase, platform, media/audio format, speed mode, attempt count, duration, and error fields. URL query parameters, cookies, Authorization, tokens, and passwords are redacted. If the log directory is not writable, GTD displays a single warning without failing download tasks.

Inspect recent events when troubleshooting:

```bash
tail -n 50 logs/downloader.jsonl
```

Do not publicly upload entire logs or cookie files. Even with automatic redaction, share only the minimum excerpt needed to resolve the issue.

## 6. Configure Cookies When Login Is Required

Public content can usually be downloaded directly. Private content, age-restricted content, and content requiring login need valid cookies, and the signed-in account must already have permission to access it. GTD does not bypass access permissions.

### Install a Trusted Cookie Export Extension

This project recommends the open-source **Get cookies.txt LOCALLY** extension. Use the official pages below and verify the extension name and GitHub repository. Do not install the similarly named older **Get cookies.txt** extension or an extension from an unknown source.

- Chrome / Edge: [Chrome Web Store installation page](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
- Firefox: [Mozilla Add-ons installation page](https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt-locally/)
- Source code and privacy information: [kairi003/Get-cookies.txt-LOCALLY](https://github.com/kairi003/Get-cookies.txt-LOCALLY)

#### Chrome / Edge Installation

1. Open the Chrome Web Store page above.
2. In Chrome, click **Add to Chrome**; in Edge, click **Get**. If prompted to allow extensions from other stores, verify that the domain is `chromewebstore.google.com` before allowing it.
3. Pin **Get cookies.txt LOCALLY** in your browser's extensions menu for easy access on platform pages.

#### Firefox Installation

1. Open the Mozilla Add-ons page above.
2. Click **Add to Firefox**, review the permissions, and confirm installation.
3. In the extension manager, allow access to the target platform's pages; otherwise, the extension cannot read and export that site's cookies.

### Export Cookies for Each Platform

Repeat these steps separately for YouTube, Instagram, and Bilibili. Do not mix all three sites' cookies into one platform-specific file:

1. Sign in to the platform in your browser and open a video page. Confirm that the current account can play the target content.
2. Keep that platform page as the active tab and open **Get cookies.txt LOCALLY**.
3. Select **Netscape** format and use the current-site export feature to export only that platform's domain cookies.
4. Open the saved file in a plain-text editor and check that the first line contains `# Netscape HTTP Cookie File`. Do not edit the cookie lines below it.
5. Move the file to the project root, alongside `main.py`, and rename it for the platform:

| Signed-In Platform | Suggested Page | Filename |
|---|---|---|
| YouTube | `https://www.youtube.com/` | `youtube_cookies.txt` |
| Instagram | `https://www.instagram.com/` | `instagram_cookies.txt` |
| Bilibili | `https://www.bilibili.com/` | `bilibili_cookies.txt` |

Platform-specific cookies take priority over general `cookies.txt`. Use the separate filenames above; use `cookies.txt` only when you actually need a general fallback file.

### Apply New Cookies

- CLI: finish the current command, then run `python main.py` again.
- Web: stop the running server and run `python app.py` again to restart the web service on port 8233, then refresh the page and resubmit the task.
- If login prompts, `HTTP 403`, or Bilibili `HTTP 412` persist, confirm that the browser session is still valid, then export that platform's cookies again. Re-export after cookies expire or the account signs out.

### Cookie Security

Cookie files are login credentials. Do not upload, share, screenshot, or commit them to Git, or paste them into chats, issues, or logs. Install the extension only from the official store links above. If cookies are exposed, immediately sign out of other sessions or revoke the platform session, change your password if needed, then delete the old file and export fresh cookies.

## 7. Troubleshooting

| Problem | What to Do |
|---|---|
| FFmpeg not detected | Install FFmpeg as described above, reopen the terminal, and verify `ffmpeg -version` |
| `HTTP 403` or login required | Configure cookies for the platform and confirm that the link opens in your browser |
| `HTTP 429` | Requests are too frequent; wait before retrying |
| Instagram Story cannot be downloaded | Confirm that it has not expired and that the signed-in account has access |
| Bilibili quality restricted, login required, or membership required | Confirm that your account can already play the content, then export complete cookies to `bilibili_cookies.txt` |
| Bilibili abuse prevention or `HTTP 412` | Reduce request frequency, use a network that can access Bilibili normally, and retry later; configure `bilibili_cookies.txt` for login-required content |
| Slow Bilibili downloads | The project uses 10 MB HTTP chunks and runs up to 2 Bilibili downloads concurrently; actual speed depends on the assigned CDN and network route, and client optimization cannot guarantee bypassing platform rate limits |
| Video unavailable or 404 | Check that the link is valid and the content has not been deleted |
| Network timeout | Check your network, proxy, or VPN configuration and retry |
| No sound after download or merging fails | Ensure FFmpeg is installed and available in the system `PATH` |
| MP3 download fails or no audio stream found | Confirm that FFmpeg works, then check in your browser that the source contains playable audio |
| yt-dlp suddenly fails to parse a platform | Opt into `requirements-update.txt` as described in Installation, restart the server, and retry |
| Web page will not open | Confirm that `python app.py` is running without terminal errors, then open `http://127.0.0.1:8233` |
| Web progress contains control codes or garbled text | Restart the web server and force-refresh the page; the current backend strips yt-dlp terminal color codes |
| Web port already in use | Change `WEB_PORT = 8233` in `app.py` and restart the server |

## 8. Exit Status (Command-Line Mode)

- All tasks succeed: exit code `0`
- Any task fails or no valid links are provided: exit code `1`
- The user cancels interactive input with a keyboard shortcut: exit code `130`

## Development checks

With Python 3.10+ and Node.js 22 (required by the JavaScript regression harnesses), run from the project root:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Install the optional development dependencies and Chromium for browser regression tests:

```bash
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m unittest discover -s tests/browser -p "test_*.py"
```

The GitHub Actions configuration covers macOS / Windows and Python 3.10 / 3.13, running unit tests, JavaScript harnesses, and browser tests. Tests mock download responses; they do not validate live platform connectivity or download speed.

## Acceptable Use

This tool is intended for learning and downloading video or audio that you own, are authorized to use, or are permitted by the platform to download. Follow the terms of service of YouTube, Instagram, and Bilibili, as well as applicable local laws and regulations. Do not use it to bypass DRM or access controls or download copyrighted content without permission.
