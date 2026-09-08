# Local video to audio

## Scope and experience

Add `/extract-audio`, an independent page linked from the download homepage. Confirmed: input is a local video file. Support selecting or dropping one video per submission, choosing Original audio (default) or MP3 V0, and submitting another file after the first upload completes. Reuse the existing bilingual controls, dark/light theme, editorial typography, and calm motion. Show upload progress separately from processing progress, task status, cancellation/retry, output details, and a download link. Original audio means copying the selected audio stream without re-encoding; it does not restore quality lost in the video. Default to the default audio track, otherwise the first audio track, and disclose that choice.

## Approach

Use the existing Flask service and FFmpeg/ffprobe installation. Add a small local-media runner selected by the shared TaskManager runner dispatcher; ordinary URL downloads continue through download_video. Reuse TaskSeed, concurrency limits, cancellation tokens, existing batch/status/action APIs, TaskHistoryStore, prepared output directories, audio format constants and output collision protection. No separate executor or database. Keep local upload/FFmpeg code in a focused module rather than growing downloader.py.

A separate conversion service would duplicate queue/history. Browser-only FFmpeg would add a large runtime and memory costs. Neither is recommended for this request.

## Data flow and lifecycle

Accept multipart uploads through a dedicated API, never a client-provided server file path. Save under generated identifiers in an ignored staging directory; preserve the display filename separately. Limit each upload to 2 GiB and stream it to disk. Bound retained staging storage to 8 GiB / 256 files and reject exhausted capacity clearly. Validate the actual media using ffprobe in the worker, require a video stream and an audio stream, and reject invalid/no-audio inputs with bilingual errors. Restrict FFmpeg input protocols to local file/pipe so submitted playlist references cannot fetch network resources.

For Original audio use stream copy into a suitable audio container (e.g. AAC to M4A, Opus to Ogg/Opus, or MKA for other supported codecs); never silently transcode when Original was requested. MP3 uses the existing V0 quality policy. Outputs go to the existing default downloads directory with collision-safe names. Use a task-ID based download endpoint that resolves only a completed extraction result, not arbitrary paths supplied in a URL.

Keep staged uploads available for retry for 24 hours, remove expired inactive inputs on startup, upload and history refresh, and never remove queued/running inputs. On missing/expired input, explain that the user must upload again. Clean partial outputs after failure/cancellation and interrupted staging uploads; retain completed output files. Use bounded FFmpeg subprocess output, cooperative termination/kill and accurate duration-based progress where available. Unknown duration is shown as indeterminate.

## Verification

Unit/API checks for upload validation, traversal/size limits, source format selection, process cancellation, staging cleanup, history restoration and authorized output delivery. Generate tiny local test videos and validate source codec preservation and MP3 output with real FFmpeg/ffprobe. Browser checks cover upload, formats, successful output, failure, language/theme preservation and mobile layout. Run existing download regressions and finish with a scoped local commit.
