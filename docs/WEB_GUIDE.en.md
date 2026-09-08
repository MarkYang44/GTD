# Web user guide

This guide covers common operations, download formats, task statuses, and troubleshooting in the GTD — Generalized Transmedia Downloader web interface.

Use Python 3.10 or later and install the pinned direct dependency baseline in the [README](../README.en.md). To obtain upstream yt-dlp extractor fixes, follow its opt-in update instructions.

## Getting started

Once the project web server is running, visit [http://127.0.0.1:8233](http://127.0.0.1:8233) in your browser. You can submit video and audio tasks separately.

Use the **ZH / EN** switch at the top right to change languages. Your choice applies across all project pages and is remembered in this browser.

Use the **Dark / Light** slider in the upper-right corner to switch themes. Dark is the default; light uses clean white and soft gray surfaces. Both keep Petronas green accents. Your theme preference is independent of language, remembered in this browser, and shared across pages and tabs.

> The web interface and system folder picker are intended for the local desktop session running this project. The browser does not read or upload arbitrary local folder contents.

## LMU content tools

Use the character icon in the upper-right corner to open the Circuit Guide. Search by circuit name, Chinese alias, or location, and combine class, car, and favorites filters. Star a circuit or car to save it in this browser; favorites synchronize across same-origin tabs.

Expand the recommendations, select 2–3 entries, and use **Compare** at the bottom right to view each circuit's recommendation reasons and caveats side by side. Filtering preserves favorites and comparison selections; reloading clears comparison selections. If browser storage is disabled, favorites last only for the current page.

## Download workflow

1. To download video, paste links or platform share text into **Best-quality video**; for audio only, use **Best-quality audio**. Put each link on its own line.
2. Audio options are **MP3 V0**, **Source FLAC**, **Original audio**, and **WAV PCM**. WAV files are larger and do not improve source quality. Source FLAC automatically falls back to MP3 V0 when the platform does not provide FLAC.
3. Under **Download location**, enter a path or click **Choose folder** to open the Windows/macOS system picker. Leave it blank to use the default `downloads/` shown on the page.
4. The dropdown beside the download location keeps the last 3 folders successfully used in this browser. Duplicate paths are removed, with the most recently used path first.
5. Single items are submitted directly. Playlists, collections, and multipart videos first open a preview panel. You can select up to 100 items at a time.
6. After submitting, the task area shows the queue, speed, estimated time remaining, progress, processing stage, output specifications, and save path.

## Video, audio, and output files

- Video downloads select the highest-quality video and audio streams available from the platform, then use FFmpeg to merge them into MP4.
- MP3 V0 selects the highest-quality source audio and uses FFmpeg to convert it at the highest VBR quality.
- Source FLAC produces FLAC only when the platform actually provides it. It does not disguise AAC or Opus as lossless audio.
- Original audio preserves the source codec and corresponding file extension. WAV is decoded PCM: it takes more space without improving source quality.
- MP3, FLAC, and some containers that support cover art attempt to embed the video thumbnail. WebM and WAV are output normally without embedded cover art.
- Repeated downloads do not overwrite existing files. New files receive incrementing suffixes such as `(2)` and `(3)`.

## Download locations and history

- Blank field: save to the project's default `downloads/` folder.
- Manual entry: enter a Windows or macOS folder path that can be created and written to.
- System picker: click **Choose folder** to select a folder on the computer running the web server.
- Recent locations: a path is recorded only after a download request is successfully submitted. Canceled selections, invalid paths, and failed submissions do not update history.
- Recent download locations are stored only in this browser's local storage and is never uploaded. Clearing site data also clears the history.
- Retrying or downloading again keeps the original task's download location; it does not automatically revert to the default folder.

## Task queue and actions

- All web batches share up to 3 worker slots, with at most 2 Bilibili tasks running simultaneously.
- **Cancel**: queued tasks are canceled immediately; standard downloads stop at the next safe checkpoint.
- **Retry**: failed or canceled tasks rejoin the same queue, keeping a record of every attempt.
- **Retry all failed tasks**: resubmit only failed tasks that can be retried.
- **Redownload**: create a new task for a completed download, preserving the original file.
- Task history is saved locally in `state/tasks.sqlite3` (override with the `GTD_HISTORY_PATH` environment variable), including source URLs, output paths, and task results, but excluding cookie files and downloader internals. Up to 100 batches are retained by pruning the oldest finished batches; active batches are never pruned. Refreshing the page restores the current batch, and Task history lets you select older batches. After a server restart, unfinished tasks become retryable `INTERRUPTED` failures and require a manual retry; no downloads start automatically, and downloaded files are kept.

## Bilibili turbo mode

- Turbo mode requires `aria2c` on the system or in the project. The switch is disabled automatically when it is unavailable.
- This mode applies only to Bilibili. YouTube and Instagram do not use aria2c.
- Selected streams larger than 50 MiB may be tested with small sample downloads across up to 4 HTTPS CDN hosts returned by Bilibili.
- Once a task becomes non-interruptible, the cancel button is unavailable. Wait for the task to finish.
- If aria2c fails or a CDN returns `HTTP 403` / `HTTP 412`, the project automatically falls back to standard mode or the original CDN.
- Acceleration does not bypass platform permissions, anti-abuse controls, or rate limits. Actual speed still depends on region, network routing, and CDN load.

## Supported links

| Platform | Common supported pages |
|---|---|
| YouTube | Standard videos, short links, Shorts, live streams/replays, embedded videos, YouTube Music, playlists |
| Instagram | Reels, video posts, IGTV, unexpired Stories accessible to the current account |
| Bilibili | BV, av, mobile video pages, specific parts, multipart videos, list, medialist, creator collections, b23.tv short links |

Whether playlists, collections, or multipart videos can be expanded depends on public availability, yt-dlp support, and current cookie permissions. The tool does not bypass DRM, additional service APIs, or account access restrictions.

## Login-protected content and cookies

Public content usually does not require cookies. For private content, age-restricted content, or content that explicitly requires login, your account must already have access. Place a Netscape-format cookie file in the project root:

| Platform | Filename |
|---|---|
| YouTube | `youtube_cookies.txt` |
| Instagram | `instagram_cookies.txt` |
| Bilibili | `bilibili_cookies.txt` |

The open-source extension **Get cookies.txt LOCALLY** is recommended. Install it only from an official page:

- [Chrome / Edge installation page](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
- [Firefox installation page](https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt-locally/)
- [Source code and privacy information](https://github.com/kairi003/Get-cookies.txt-LOCALLY)

Export only the current platform's domain, select Netscape format, and confirm that the first line contains `# Netscape HTTP Cookie File`. Save the file in the project root using the filename above, then restart the web server and refresh the page.

> Cookie files are login credentials. Do not upload, share, screenshot, commit them to Git, or paste them into chats, issues, or logs.

## Troubleshooting

| Problem | What to do |
|---|---|
| Page will not open | Confirm the web server is running, then visit `http://127.0.0.1:8233` |
| FFmpeg not detected | Install FFmpeg, add it to the system PATH, reopen your terminal, and restart the web server |
| aria2c not detected | Standard mode still works; restart the web server after installing aria2c |
| HTTP 403 or login required | Confirm your browser account can play the content, then update the platform's cookies |
| HTTP 429 | Requests are too frequent; pause and try again later |
| Bilibili HTTP 412 | Reduce request frequency and retry later; also update Bilibili cookies for login-protected content |
| Network timeout | Check your local network, proxy, or VPN settings, then retry |
| Download has no audio or cannot be merged | Confirm FFmpeg is installed and can be found by the project |
| Folder is not writable | Choose a folder writable by your user account; avoid protected Windows system folders |
| Garbled progress text or outdated styling | Restart the web server and hard-refresh the page with `Ctrl+F5` |

## Authorized use

This tool is only for downloading video or audio you own, are authorized to use, or the platform permits you to download. Follow the terms of service of YouTube, Instagram, and Bilibili, and applicable local laws. Do not use it to bypass DRM or access controls, or to download content you have no right to use.

## Extract audio from a local video

Choose **Extract audio from a local video** on the homepage, or open `/extract-audio`. Drop or select one local video (up to 2 GiB), choose **Original audio** or **MP3 V0**, and start extraction. Original audio copies the stream without re-encoding, using the default audio track or the first track when no default is set. AAC normally produces M4A; other extensions depend on the codec. Extraction cannot improve the source quality.

Upload and processing progress are shown separately. Extraction shares the existing queue, cancellation/retry, and task history. Results are saved to the default `downloads` folder and can also be saved with **Download audio**. Upload copies are staged in `state/audio_uploads` for 24 hours; expired inactive copies are cleaned on startup, upload, or extraction-history refresh. Re-upload after expiration to retry. Staging is limited to 8 GiB / 256 files. Source videos are unchanged and completed outputs are not automatically removed.
