# Source FLAC Container Compatibility Implementation Plan

**Goal:** Make source audio downloads with FLAC inside M4A finish successfully without transcoding.

**Approved design:** For a selected FLAC source, keep requested/used format as `source`, report the output container as `flac`, and explicitly request yt-dlp's FLAC stream-copy extraction before metadata writing. Other source codecs retain their existing behavior.

**Architecture:** Keep the change in `audio_output.py`, shared by Web and CLI downloads. Existing output finalization handles names, covers, and result metadata.

**Tech stack:** Python, unittest, yt-dlp, FFmpeg/ffprobe.

## Constraints

- Preserve lossless encoded audio and source-mode result semantics.
- Do not change video downloads, concurrency, cookies, or network configuration.
- Leave changes uncommitted and do not retry the user's persisted task.

## Task 1: Source FLAC output and regression coverage

Files: `audio_output.py`, `tests/test_downloader_errors.py`, `tests/test_source_flac.py`.

- [x] Add profile cases for source FLAC/M4A and source AAC/M4A. FLAC should produce extension/preferred codec `flac`; AAC should retain `m4a`/`best`.
- [x] Add a real FFmpeg regression: generate FLAC in an MP4 container named `.m4a`, run configured yt-dlp postprocessors and output finalization, verify `.flac`, metadata, source-mode semantics, and matching compressed audio hashes.
- [x] Run `venv/bin/python -m unittest discover -s tests -p 'test_source_flac.py' -v` and observe the original metadata failure.
- [x] In the SOURCE profile branch use `output_ext = FLAC if source_acodec == "FLAC" else source_ext or "mka"`; in postprocessors use `SOURCE: FLAC if profile.source_acodec == "FLAC" else "best"`.
- [x] Re-run focused audio tests and `venv/bin/python -m unittest discover -s tests -p 'test_*.py'`; inspect failures and skips.
- [x] Process the previously fetched real Bilibili sample with the corrected source-mode options; verify FLAC output and unchanged audio hashes.
- [x] Review `git diff` and run `git diff --check` before reporting completion.

## Verification results

- Before the fix, the generated FLAC/M4A fixture reproduced `FFmpegMetadataPP: Conversion failed!`; the source FLAC profile case also failed.
- After the fix, the real-container regression passed, including metadata, cover, 48 kHz/24-bit audio, and identical compressed audio hashes.
- Focused suites: 75 downloader tests and 41 Bilibili tests passed.
- Full unit/JavaScript harness suite: 468 tests, OK with 2 skips.
- Original BV1okbXzvE7j sample (first 2 MiB): source mode produced FLAC, cover embedding passed, compressed audio hashes matched, and the first 3 seconds decoded successfully. This was sample verification, not a full video download.
- Running Web service uses `debug=False`; restarting it is required to load the modified Python module.
