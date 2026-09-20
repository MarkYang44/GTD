# Optional video subtitles and Bilibili danmaku

## Scope
Web video controls and CLI --subtitles / --auto-subtitles / --danmaku. Defaults off; audio excluded. Shared subtitle_options bool mapping persists through queue, retry, redownload and SQLite history. Global language/theme retained.

## Implementation
- subtitle_preferences.py: strict API/queue validation; automatic requires subtitles.
- video_subtitles.py: separate tolerant metadata/subtitle retrieval via yt-dlp native downloader, bounded XML -> ASS, FFmpeg stream-copy MKV packaging. Existing text subtitles converted when required by MKV; original audio/video untouched. First added subtitle default when no existing tracks.
- downloader.py: optional packaging before final output claiming in standard and Bilibili turbo paths; nonfatal subtitle problems exposed in result. Temporary ownership and cancellation retained.
- app.py/task_control.py/task_history.py/main.py: optional preferences and result metadata throughout, compatibility with historical tasks and no-option calls.
- index template/JS and bilingual documentation: separate switches, preview snapshot, localized result status and warnings. MKV and source availability clearly stated; no OCR or baked-in overlays.

## Limits
24 manual / 8 automatic (source and zh/en) / 1 danmaku track. Ordinary scrolling/reverse/fixed top/bottom text; 20,000 XML entries, 16 MiB subtitle limit; no advanced script danmaku. XML DTD/entity declarations rejected and ASS overrides in comment text escaped. Sources may require login; no guarantee of complete historical danmaku. If packaging fails, retain original media and warn.

## Validation
Synthetic FFmpeg fixtures for ASS embedding and existing MP4 mov_text preservation; source metadata retrieval opt-in; caption selection and automatic filtering; cancellation; queue/history/redownload; CLI forwarding; browser preview snapshot and audio exclusion. Run full unittest suite and browser regressions using isolated temp test history and existing Chrome headless profile. No live account/cookie contents are copied into docs or tests.

## Verified results
- Full unit/Node regression: 454 tests, OK with 2 platform skips.
- Full browser regression: 29 tests, OK using installed Chrome with an isolated Playwright context. Temporary browser download failed because configured local proxy was unavailable; no system proxy settings changed.
- Real FFmpeg/ffprobe fixtures verify ASS/default track, original MP4 mov_text retention, stream-copy video/audio hashes, and cancellation/source preservation. No real remote video or IINA UI playback session was used as a test; live availability depends on source/login.
- Reviewer agents exhausted their session quota after initial implementation. Root completed integration, examined extractor gating and Bilibili AI-language handling, fixed both, and ran the final checks.
