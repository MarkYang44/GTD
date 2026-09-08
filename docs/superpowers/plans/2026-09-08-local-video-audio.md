# Local video audio extraction implementation plan

> Use subagent-driven-development for independent frontend work and local backend implementation, then integrate and verify.

**Goal:** Upload local videos on a dedicated bilingual themed page and extract original audio or MP3 through the existing queue.
**Architecture:** `local_audio.py` owns staging and FFmpeg runner; `audio_extract_routes.py` provides Flask blueprint; app runner dispatches local inputs into shared TaskManager. Frontend reuses shared styles/language/theme and existing batch/action APIs.

- [x] Backend: tests for staging limits, media validation, stream selection, source copy, MP3, cancellation/cleanup, download result allowlisting; implement focused modules and app dispatch.
- [x] Frontend: independent template/CSS/JS, upload/drop, format selection, upload progress, polling/actions/history/download; shared header and homepage entry.
- [x] Integration: real FFmpeg fixtures and Flask API flow; browser workflow plus existing suite; check layout/theme/language and update bilingual docs.
- [x] Review, resolve findings, local commit. No push.

Validation: 428 unit/Node tests passed (2 platform skips); 14 Chromium browser tests passed. Real FFmpeg fixtures verified default track selection, source AAC packet hashes, MP3 codec, output download and retained history. Cancellation tests verified process termination and partial-output cleanup. Native Chrome visual checks covered desktop and 375px light layout. Code review found shared homepage history needed local filenames/output links; corrected. No dependency changes; source uploads and completed outputs remain Git-ignored.
