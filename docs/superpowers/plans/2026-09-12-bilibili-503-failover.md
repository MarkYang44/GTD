# Bilibili HTTP 503 Failover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover from Bilibili CDN HTTP 503 responses and download the five incomplete videos from the latest batch.

**Architecture:** Extend the existing CDN transport-failure predicate by one observed status code, allowing the existing lazy backup-host state machine to run. Keep operational recovery sequential to reduce load on Bilibili.

**Tech Stack:** Python 3, unittest, yt-dlp, aria2c, FFmpeg/ffprobe

## Global Constraints

- Preserve the completed video and all existing partial files.
- Do not read, print, or commit Cookie contents.
- Do not change public APIs, global concurrency, or unrelated behavior.
- Do not stage, commit, or push changes.

---

### Task 1: Recognize HTTP 503 as a recoverable CDN transfer failure

**Files:**
- Modify: `tests/test_bilibili_support.py`
- Modify: `downloader.py`

**Interfaces:**
- Consumes: `_download_bilibili(...)` and `_is_cdn_transport_failure(error)`
- Produces: Existing automatic standard-mode retry on a different CDN host for HTTP 503

- [ ] Add a test where the selected CDN raises `DownloadError("HTTP Error 503: Service Unavailable")` and the backup host succeeds.
- [ ] Run the focused test and confirm it fails because only one attempt occurs.
- [ ] Add `"http error 503"` to `_is_cdn_transport_failure`.
- [ ] Re-run the focused test and Bilibili test modules.
- [ ] Run the full Python test suite and `git diff --check`.

### Task 2: Recover the incomplete batch

**Files:**
- Preserve: `downloads/*`
- Read/update through normal runtime behavior: `logs/downloader.jsonl`

**Interfaces:**
- Consumes: The five incomplete Bilibili URLs stored in batch `faca2947a77749a2b84ee3188c91dfa6`
- Produces: Five finalized MP4 files in `downloads/`

- [ ] Download each incomplete URL separately with turbo mode and fresh metadata.
- [ ] After each item, confirm the process exits successfully before starting the next.
- [ ] Run `ffprobe` on all five outputs and require readable video/audio streams.
- [ ] Confirm the original completed file remains present and inspect final Git status.
