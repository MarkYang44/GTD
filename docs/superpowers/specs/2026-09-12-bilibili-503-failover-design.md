# Bilibili HTTP 503 CDN Failover Design

## Problem

The latest six-item Bilibili batch selected turbo mode. Two tasks failed after
the selected CDN returned HTTP 503, two were interrupted after falling back to
standard mode, one completed, and one never started. The downloader currently
switches CDN hosts for access failures and connection resets, but not for HTTP
503, even when metadata contains usable backup hosts.

## Design

Treat HTTP 503 from a Bilibili media transfer as a recoverable CDN transport
failure. Reuse the existing lazy backup-host loop and standard-mode fallback;
do not change concurrency defaults, retry counts, downloader selection, or
public APIs.

Re-download only the five incomplete items, one at a time, with fresh metadata
and turbo mode enabled. Preserve the completed video and existing partial files.

## Verification

Add a regression test proving a 503 on the chosen host retries a different CDN
host and succeeds. Run the focused Bilibili tests, the full Python test suite,
and `git diff --check`. Validate every newly downloaded video with `ffprobe`.
