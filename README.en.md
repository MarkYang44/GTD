<p align="center">
  <img src="static/icons/android-chrome-192x192.png" width="88" alt="GTD icon">
</p>

<h1 align="center">GTD</h1>

<p align="center"><strong>Generalized Transmedia Downloader</strong><br>Multi-platform media downloads, local audio extraction, and LMU race tools.</p>

<p align="center"><a href="README.md">简体中文</a> · <strong>English</strong></p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Interface-Web%20%2B%20CLI-008C88" alt="Web and CLI">
  <img src="https://img.shields.io/badge/Language-中文%20%7C%20English-59636E" alt="Chinese and English">
</p>

Built on [yt-dlp](https://github.com/yt-dlp/yt-dlp), Flask, and FFmpeg, GTD brings YouTube, Instagram, and Bilibili downloads into one workflow. Manage batches in your browser or download directly from the command line. Extract audio from local video files, and use the included Le Mans Ultimate section for circuit guides, a car catalog, race strategy, and a manually maintained weekly calendar.

**Run the Web interface or CLI from source on macOS and Windows.** Install the Python dependencies and media tools to get started.

[Full usage reference](docs/REFERENCE.en.md) · [Web user guide](docs/WEB_GUIDE.en.md) · [Calendar maintenance](docs/LMU_CALENDAR_MAINTENANCE.md) · [LMU content maintenance](docs/LMU_CONTENT_MAINTENANCE.md) · [Report an issue](https://github.com/MarkYang44/GTD/issues)

## Features

| Module | Capabilities |
| --- | --- |
| Multi-platform downloads | Mix YouTube, Instagram, and Bilibili URLs or share text; preview and select playlist, collection, and multipart entries |
| Video and audio | Select the highest available video and audio quality; MP4 video and MP3 V0, source FLAC, original audio, or WAV PCM; cover embedding with fallback artwork |
| Subtitles and danmaku | Optionally package manual subtitles, automatic captions, and Bilibili comments as selectable MKV tracks |
| Task management | Progress, speed, time remaining, structured errors, cancellation, retries, redownloads, and persistent history |
| Local audio extraction | Upload or drop a video, extract the original audio or convert to MP3 V0, and download the result |
| LMU tools | Circuit guides, car catalog, favorites and comparisons, practice notes, fuel and pit estimates, content revisions, weekly calendar, and victory archive |
| Interface and output | Shared Chinese/English and dark/light preferences; custom output folders with native macOS/Windows folder pickers |

All Web batches share up to **3 worker slots**, including local audio extraction, with at most **2 Bilibili** downloads and **1 Instagram** download running at once. Each CLI batch uses the same concurrency limits. Select up to 100 items per batch; collection previews list up to the first 1,000 entries and report truncation.

## Quick start

### 1. Prepare your environment

| Dependency | Purpose |
| --- | --- |
| Python 3.10+ and pip | Run the Web service and CLI |
| FFmpeg and ffprobe | Merge streams, inspect media, convert and extract audio |
| aria2c (optional) | Bilibili turbo mode; standard downloads work without it |
| Node.js 22 (development checks) | Run JavaScript regression harnesses |

On macOS, use an existing Homebrew installation to install media tools:

```bash
brew install ffmpeg
# Optional
brew install aria2
```

On Windows, install Python from [python.org](https://www.python.org/downloads/windows/). Follow the Windows links on the [FFmpeg download page](https://ffmpeg.org/download.html) to install a distribution containing `ffmpeg.exe` and `ffprobe.exe`, and add its `bin` directory to `PATH`. Open a new terminal and verify both commands:

```bash
ffmpeg -version
ffprobe -version
```

### 2. Get the source and install dependencies

```bash
git clone https://github.com/MarkYang44/GTD.git
cd GTD
```

macOS:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -3 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

On Windows, no activation or PowerShell execution-policy changes are needed. In the commands below, replace `python` with `.\venv\Scripts\python.exe` when the environment is not activated; the macOS equivalent is `venv/bin/python`.

[requirements.txt](requirements.txt) defines the direct dependency baseline. Pip resolves transitive dependencies for your OS and Python version. Install the complete file to include cover-art handling and Windows timezone data.

### 3. Start the Web interface

```bash
python app.py
```

Open **[http://127.0.0.1:8233](http://127.0.0.1:8233)** and paste one link per line into the video or audio panel. Collections open a selection panel before submission. Track progress after submitting. Output defaults to the project's `downloads/` folder, or select another directory in the interface. Press `Ctrl+C` in the terminal to stop the service.

> The service listens on `0.0.0.0:8233` by default and has no login protection. Devices that can reach the port on your local network can submit tasks and access results. Use a trusted network and do not expose the port to the internet. When accessed remotely, the folder picker operates on the computer running the service.

## Command-line usage

Start interactive mode to choose video or audio, an output folder, and download URLs:

```bash
python main.py
```

Or supply arguments directly. Replace the placeholder URLs below with your targets:

```bash
# Download video; append more URLs to submit a mixed batch
python main.py "https://www.youtube.com/watch?v=VIDEO_ID"

# Audio formats: mp3 / flac / source / wav
python main.py --audio --audio-format mp3 "https://www.youtube.com/watch?v=VIDEO_ID"

# Explicit selection is required for playlists and multipart collections
python main.py --items 1-5 "https://www.youtube.com/playlist?list=PLAYLIST_ID"

# Video subtitles, automatic captions, and Bilibili danmaku
python main.py --subtitles --auto-subtitles --danmaku "https://www.bilibili.com/video/BV_ID"

# Optional Bilibili turbo mode, requiring aria2c
python main.py --turbo "https://www.bilibili.com/video/BV_ID"
```

Set an output directory with `--output-dir "path"`; `--download-dir` is an alias. Relative paths are resolved from the project root, and missing folders are created when possible. Quote URLs and paths containing spaces. `--items all` selects an entire collection within the 100-item batch limit. Argument mode starts downloading immediately.

CLI exit codes: `0` when all tasks succeed, `1` for any failure or no valid URLs, and `130` when the user interrupts interactive input.

## Output and availability

- **Video:** MP4 by default; enabling subtitles or danmaku switches to MKV with separate subtitle/ASS tracks. Only source-provided tracks accessible to your account can be downloaded. Burned-in text cannot be extracted.
- **Audio:** MP3 uses V0. `source` keeps the selected source codec, and `wav` decodes to PCM. `flac` uses actual source FLAC when available and otherwise falls back to MP3 V0. Conversion does not improve lossy source quality.
- **Local extraction:** Original audio or MP3 V0, with a 2 GiB per-file upload limit. See the [Web guide](docs/WEB_GUIDE.en.md#extract-audio-from-a-local-video) for supported containers, staging quotas, and cleanup rules.
- **File preservation:** Repeated downloads receive suffixes such as `(2)` and `(3)`. After a service restart, unfinished tasks become `INTERRUPTED` and require a manual retry.
- **Platform limits:** Availability depends on the source, account permissions, and yt-dlp support. Bilibili can select alternative CDNs supplied by the platform, and turbo failures can fall back to standard mode. Actual speed depends on network conditions and CDN routing.

## LMU tools

| Page | Route |
| --- | --- |
| Circuit guide | `/kozekilmu/tracks` |
| Car catalog | `/kozekilmu/cars` |
| Race strategy | `/kozekilmu/strategy` |
| Weekly calendar | `/kozekilmu/calendar` |
| Content updates | `/kozekilmu/updates` |
| Victory archive | `/kozekilmu` |

The calendar uses **manual review, JSON validation, and manual publication**, with no automatic fetching or scheduled updates. Times use `Europe/London` with GMT/BST handling. Expired calendars carry a historical warning, and unknown official fields remain “Not Published.” Car recommendations are editorial advice; fuel and pit results are estimates.

```bash
python scripts/update_lmu_calendar.py /path/to/candidate.json --check
python scripts/update_lmu_calendar.py /path/to/candidate.json
```

Failed validation preserves valid data. Successful week transitions archive the previous week. Refresh the page after publication. See [calendar maintenance](docs/LMU_CALENDAR_MAINTENANCE.md) for the schema, examples, and limitations, and [content maintenance](docs/LMU_CONTENT_MAINTENANCE.md) for source review and revision procedures.

## Data and privacy

| Location | Contents |
| --- | --- |
| `downloads/` or a custom folder | Downloaded media and extracted audio |
| `state/tasks.sqlite3` | Task history, source URLs, output paths, and results; override with `GTD_HISTORY_PATH` |
| `state/audio_uploads/` | Staged local video copies for audio extraction |
| `logs/downloader.jsonl` | Redacted event logs, rotating at 10 MiB with up to 5 backups |
| `data/lmu/calendar/` | Current calendar, backup, week archives, and publication status |
| Browser local storage | Language, theme, recent folders, LMU favorites, and practice notes |

For login-required content, place a Netscape-format `youtube_cookies.txt`, `instagram_cookies.txt`, or `bilibili_cookies.txt` in the project root. Platform-specific files take priority over the general `cookies.txt`. Follow the [cookie setup guide](docs/WEB_GUIDE.en.md#login-protected-content-and-cookies), then restart the service after replacing cookies.

Cookies are login credentials: do not upload or commit them. Task history and media can also contain personal information. Include only the necessary redacted log excerpt in an issue.

Downloads, collection previews, subtitles/danmaku, and turbo mode use **direct connections**. GTD clears proxy environment variables and sets `NO_PROXY=*` only within its own process. It does not change system, VPN, or shell settings; your network still needs access to the source.

## Troubleshooting

| Problem | Suggested action |
| --- | --- |
| Web page does not open | Confirm `python app.py` is running; inspect terminal errors and port 8233 conflicts |
| FFmpeg / ffprobe not found | Verify both tools are on `PATH`, open a new terminal, and restart GTD |
| Login required or `HTTP 403` | Check playback permissions in your browser, then refresh the platform's cookies |
| `HTTP 429` / Bilibili `HTTP 412` | Reduce request frequency and retry later; avoid repeated submissions |
| CDN disconnect / `NETWORK_CONNECTION_RESET` | If automatic fallback also fails, check direct connectivity and retry manually later |
| Extraction reports `NO_AUDIO` / `INPUT_EXPIRED` | Verify the video contains audio; upload again if the staged input expired |
| Upstream page changes break extraction | Consider the update channel below, then restart and retry |

The optional upstream update channel installs the moving yt-dlp main branch and may behave differently from the fixed baseline:

```bash
python -m pip install --upgrade --force-reinstall --no-cache-dir -r requirements-update.txt
# Restore the direct dependency baseline
python -m pip install --force-reinstall -r requirements.txt
```

## Development and verification

GTD uses Python, Flask/Jinja, and plain HTML/CSS/JavaScript, with no frontend build step. Web and CLI share the download core.

| Entry point / directory | Responsibility |
| --- | --- |
| `app.py` / `main.py` | Web / CLI entry points |
| `downloader.py` / `task_control.py` | Download core and task scheduling |
| `local_audio.py` / `audio_extract_routes.py` | Local media extraction and endpoints |
| `templates/` / `static/` | Page templates, styles, scripts, and assets |
| `lmu_*.py` / `data/lmu/` | LMU content, strategy data, and calendar |
| `tests/` / `.github/workflows/tests.yml` | Python, JavaScript, and browser regressions |

Run from the project root. JavaScript harnesses require Node.js 22; real audio tests require FFmpeg/ffprobe:

```bash
python -m unittest discover -s tests -p "test_*.py"

# Optional: full browser regression suite
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m unittest discover -s tests/browser -p "test_*.py"
```

The CI configuration covers macOS/Windows and Python 3.10/3.13. Platform download tests mock responses and do not verify live source connectivity or speed. Some media tests skip when FFmpeg/ffprobe are unavailable. Browser tests use a separate test service and temporary state directories.

## Responsible use and acknowledgments

Download only content you own, are authorized to use, or are permitted by the platform to download. Follow source terms and applicable laws. GTD does not bypass DRM, account permissions, or membership restrictions. The LMU tools are independent community features and are not affiliated with Le Mans Ultimate.

Thanks to [yt-dlp](https://github.com/yt-dlp/yt-dlp), [Flask](https://github.com/pallets/flask), [FFmpeg](https://ffmpeg.org/), [Mutagen](https://github.com/quodlibet/mutagen), and [aria2](https://github.com/aria2/aria2). Documentation structure inspired by [LMU Stintrix](https://github.com/MarkYang44/LMU-Stintrix).

<p align="center">Designed by Mark Yang</p>
