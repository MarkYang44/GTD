# Audio Cover, Quality Labels, and Source FLAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Embed video thumbnails into downloaded audio, append truthful source-quality labels to filenames, and let Web and CLI users request source FLAC with an explicit MP3 V0 fallback.

**Architecture:** Keep `media_type` limited to `video` and `audio`, then thread a separate `audio_format` value (`mp3` or `flac`) through the existing CLI/Web → batch → single-download path. Build one immutable audio profile from yt-dlp's selected source format, use it to choose lossless FLAC extraction or MP3 fallback, run metadata/thumbnail postprocessors, rename the completed file with a truthful quality label, and expose the same result fields to both surfaces.

**Tech Stack:** Python 3.14, yt-dlp, FFmpeg/FFprobe 8.1, mutagen 1.47+, Flask, vanilla HTML/CSS/JavaScript, `unittest`.

## Global Constraints

- `mp3` remains the default and continues to mean FFmpeg/LAME V0 (`preferredquality="0"`).
- Source FLAC mode outputs FLAC only when the selected source codec is actually FLAC; AAC, Opus, and other lossy sources fall back to MP3 V0.
- MP3 filenames distinguish the lossy result from the selected source, for example `[MP3 V0 · 源FLAC 1521kbps]`.
- FLAC filenames use `[FLAC Lossless · 1521kbps]`; missing metadata is omitted instead of rendered as `NA`, `None`, or a guessed value.
- YouTube keeps title-only base naming; Instagram and Bilibili keep `[内容ID]` before the quality label.
- Missing thumbnails do not fail the audio task; successful embedding leaves no standalone thumbnail file.
- Web and CLI both expose MP3/FLAC selection, while existing video behavior and the maximum of three global/two Bilibili concurrent tasks remain unchanged.
- The exact Bilibili sample `BV1fsTM6CE9P` must select format `30251`, codec FLAC, at approximately 1521 kbps during live metadata verification.
- Do not download the complete approximately 783 MB sample album during automated verification.

---

## File Structure

- Modify `downloader.py`: audio-format constants, selected-source profiling, filename labels, cover/postprocessor options, FLAC fallback, result fields, and shared parameter propagation.
- Modify `main.py`: `--flac`, interactive format selection, validation, forwarding, and summary copy.
- Modify `app.py`: API validation, batch persistence, background forwarding, and completed-task audio fallback state.
- Modify `templates/index.html`: format selector, styling, request payload, disabled-state handling, task titles, and audio result/fallback rendering.
- Modify `requirements.txt`: install `mutagen>=1.47.0` for FLAC cover embedding.
- Modify `README.md`: document output formats, examples, fallback semantics, embedded covers, and CLI/Web usage.
- Modify `tests/test_downloader_errors.py`: core audio option, profile, naming, output path, and thumbnail behavior.
- Modify `tests/test_bilibili_support.py`: selected FLAC and Bilibili fallback/download-result behavior.
- Modify `tests/test_parallel_downloads.py`: batch propagation of `audio_format` without altering concurrency.
- Modify `tests/test_cli_audio.py`: command-line and interactive FLAC selection plus summary output.
- Modify `tests/test_web_progress.py`: API state/validation and static page behavior.

---

### Task 1: Model truthful audio output profiles and filenames

**Files:**
- Modify: `downloader.py:9-63, 407-430`
- Test: `tests/test_downloader_errors.py:108-170`

**Interfaces:**
- Produces: `MP3 = "mp3"`, `FLAC = "flac"`, `AUDIO_FORMATS = {MP3, FLAC}`.
- Produces: immutable `AudioOutputProfile(requested, used, fallback, source_acodec, source_abr_kbps)`.
- Produces: `_audio_output_profile(info: dict, requested: str) -> AudioOutputProfile`.
- Produces: `_audio_quality_label(profile: AudioOutputProfile) -> str`.
- Produces: `_rename_audio_output(filepath: Path, profile: AudioOutputProfile) -> Path`.
- Changes: `_resolve_output_path(..., audio_format: str = MP3) -> Path` resolves `.mp3` or `.flac`.

- [ ] **Step 1: Write failing profile and filename tests**

Add imports for the new dataclass-facing behavior only through `downloader`, then add these cases to `DownloadAudioOptionsTests`:

```python
    def test_flac_source_builds_mp3_profile_and_quality_filename(self):
        info = {"vcodec": "none", "acodec": "flac", "abr": 1521.267}

        profile = downloader._audio_output_profile(info, downloader.MP3)

        self.assertEqual(profile.used, downloader.MP3)
        self.assertFalse(profile.fallback)
        self.assertEqual(profile.source_acodec, "FLAC")
        self.assertEqual(profile.source_abr_kbps, 1521)
        self.assertEqual(
            downloader._audio_quality_label(profile),
            "MP3 V0 · 源FLAC 1521kbps",
        )

    def test_requested_flac_uses_real_flac_and_falls_back_for_aac(self):
        lossless = downloader._audio_output_profile(
            {"vcodec": "none", "acodec": "flac", "tbr": 1521.267},
            downloader.FLAC,
        )
        fallback = downloader._audio_output_profile(
            {"vcodec": "none", "acodec": "mp4a.40.2", "abr": 245.75},
            downloader.FLAC,
        )

        self.assertEqual(lossless.used, downloader.FLAC)
        self.assertFalse(lossless.fallback)
        self.assertEqual(
            downloader._audio_quality_label(lossless),
            "FLAC Lossless · 1521kbps",
        )
        self.assertEqual(fallback.used, downloader.MP3)
        self.assertTrue(fallback.fallback)
        self.assertEqual(fallback.source_acodec, "AAC")

    def test_unknown_source_fields_do_not_leak_placeholders(self):
        profile = downloader._audio_output_profile({}, downloader.MP3)

        label = downloader._audio_quality_label(profile)

        self.assertEqual(label, "MP3 V0")
        self.assertNotIn("NA", label)
        self.assertNotIn("None", label)

    def test_audio_output_is_renamed_after_platform_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "Example [BV123].mp3"
            source.touch()
            profile = downloader._audio_output_profile(
                {"acodec": "flac", "abr": 1521.267},
                downloader.MP3,
            )

            actual = downloader._rename_audio_output(source, profile)

            self.assertEqual(
                actual.name,
                "Example [BV123] [MP3 V0 · 源FLAC 1521kbps].mp3",
            )
            self.assertTrue(actual.is_file())
            self.assertFalse(source.exists())
```

Extend `test_audio_output_path_resolves_postprocessed_mp3` with a FLAC subtest whose existing file is `Example.flac` and which calls `_resolve_output_path(..., media_type=AUDIO, audio_format=FLAC)`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
venv/bin/python -m unittest tests.test_downloader_errors.DownloadAudioOptionsTests -v
```

Expected: failures because `MP3`, `FLAC`, `AudioOutputProfile`, profile helpers, and the new `_resolve_output_path` argument do not exist.

- [ ] **Step 3: Add constants, profile extraction, labels, and rename logic**

Import `dataclass`, add constants next to `AUDIO`, and add the immutable profile:

```python
from dataclasses import dataclass

MP3 = "mp3"
FLAC = "flac"
AUDIO_FORMATS = {MP3, FLAC}


@dataclass(frozen=True)
class AudioOutputProfile:
    requested: str
    used: str
    fallback: bool
    source_acodec: str | None
    source_abr_kbps: int | None
```

Add focused helpers before the file-path section:

```python
def _selected_audio_info(info: dict) -> dict:
    requested = info.get("requested_formats")
    if isinstance(requested, list):
        for candidate in requested:
            if isinstance(candidate, dict) and candidate.get("acodec") not in {None, "none"}:
                return candidate
    return info


def _display_audio_codec(value: object) -> str | None:
    codec = str(value or "").lower()
    if codec.startswith("flac"):
        return "FLAC"
    if codec.startswith(("aac", "mp4a")):
        return "AAC"
    if "opus" in codec:
        return "Opus"
    if codec.startswith("mp3"):
        return "MP3"
    return codec.upper() or None


def _audio_output_profile(info: dict, requested: str) -> AudioOutputProfile:
    if requested not in AUDIO_FORMATS:
        raise ValueError(f"不支持的音频格式: {requested}")
    selected = _selected_audio_info(info)
    source_acodec = _display_audio_codec(selected.get("acodec"))
    raw_bitrate = selected.get("abr") or selected.get("tbr")
    source_abr_kbps = (
        round(raw_bitrate)
        if isinstance(raw_bitrate, (int, float)) and raw_bitrate > 0
        else None
    )
    used = FLAC if requested == FLAC and source_acodec == "FLAC" else MP3
    return AudioOutputProfile(
        requested=requested,
        used=used,
        fallback=requested == FLAC and used == MP3,
        source_acodec=source_acodec,
        source_abr_kbps=source_abr_kbps,
    )


def _audio_quality_label(profile: AudioOutputProfile) -> str:
    parts = ["FLAC Lossless" if profile.used == FLAC else "MP3 V0"]
    if profile.used == FLAC:
        if profile.source_abr_kbps:
            parts.append(f"{profile.source_abr_kbps}kbps")
    elif profile.source_acodec:
        source = f"源{profile.source_acodec}"
        if profile.source_abr_kbps:
            source += f" {profile.source_abr_kbps}kbps"
        parts.append(source)
    return " · ".join(parts)


def _rename_audio_output(filepath: Path, profile: AudioOutputProfile) -> Path:
    target = filepath.with_name(
        f"{filepath.stem} [{_audio_quality_label(profile)}]{filepath.suffix}"
    )
    filepath.replace(target)
    return target
```

Add `audio_format: str = MP3` to `_resolve_output_path`, validate it for audio, and select `f".{audio_format}"` instead of the current unconditional `.mp3` suffix.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the same `DownloadAudioOptionsTests` command. Expected: all tests in that class pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add downloader.py tests/test_downloader_errors.py
git commit -m "feat: model audio quality outputs"
```

---

### Task 2: Embed covers and execute MP3/FLAC selection with fallback

**Files:**
- Modify: `downloader.py:289-404, 519-790, 870-950`
- Modify: `requirements.txt`
- Test: `tests/test_downloader_errors.py:108-170`
- Test: `tests/test_bilibili_support.py:109-190, 240-445`
- Test: `tests/test_parallel_downloads.py:190-230`

**Interfaces:**
- Consumes: Task 1 `AudioOutputProfile`, `_audio_output_profile`, `_rename_audio_output`, `MP3`, `FLAC`, `AUDIO_FORMATS`.
- Changes: `_build_ydl_options(..., audio_format: str = MP3) -> dict`.
- Changes: `_resolve_output_path(..., audio_format: str = MP3) -> Path`.
- Changes: `_download_bilibili(..., audio_format: str) -> DownloadResult`.
- Changes: `download_video(..., audio_format: str = MP3) -> Optional[DownloadResult]`.
- Changes: `download_tasks(..., audio_format: str = MP3) -> list[...]`.
- Produces result fields: `audio_format_requested`, `audio_format_used`, `audio_format_fallback`, `source_acodec`, `source_abr_kbps`.

- [ ] **Step 1: Write failing postprocessor and fallback tests**

Update the existing MP3 option assertion and add FLAC assertions:

```python
    def test_audio_options_download_thumbnail_and_embed_it_after_conversion(self):
        options = downloader._build_ydl_options(
            downloader.YOUTUBE,
            Path("/tmp/downloads"),
            1,
            1,
            media_type=downloader.AUDIO,
            audio_format=downloader.MP3,
        )

        self.assertTrue(options["writethumbnail"])
        self.assertEqual(
            [processor["key"] for processor in options["postprocessors"]],
            ["FFmpegExtractAudio", "FFmpegMetadata", "EmbedThumbnail"],
        )
        self.assertFalse(options["postprocessors"][-1]["already_have_thumbnail"])

    def test_flac_options_select_flac_first_and_copy_to_flac(self):
        options = downloader._build_ydl_options(
            downloader.BILIBILI,
            Path("/tmp/downloads"),
            1,
            1,
            media_type=downloader.AUDIO,
            audio_format=downloader.FLAC,
        )

        self.assertEqual(
            options["format"],
            "bestaudio[acodec^=flac]/bestaudio/best",
        )
        self.assertEqual(
            options["postprocessors"][0],
            {"key": "FFmpegExtractAudio", "preferredcodec": "flac"},
        )
```

In `tests/test_bilibili_support.py`, mock extracted information with `acodec="flac"`, `format_id="30251"`, and `abr=1521.267`; assert the final processing options use FLAC and the result records `audio_format_used="flac"`. Add a second case with `acodec="mp4a.40.2"`, `abr=245.75`; assert processing uses MP3 and result field `audio_format_fallback` is true.

In `tests/test_parallel_downloads.py`, extend the audio forwarding test:

```python
        downloader.download_tasks(
            tasks,
            media_type=downloader.AUDIO,
            audio_format=downloader.FLAC,
        )

        self.assertTrue(calls)
        self.assertTrue(all(call["audio_format"] == downloader.FLAC for call in calls))
```

- [ ] **Step 2: Run the focused tests and verify RED**

```bash
venv/bin/python -m unittest \
  tests.test_downloader_errors.DownloadAudioOptionsTests \
  tests.test_bilibili_support.BilibiliDownloadOptionsTests \
  tests.test_bilibili_support.BilibiliTurboDownloadTests \
  tests.test_parallel_downloads.ParallelDownloadTests -v
```

Expected: failures because cover processors and `audio_format` propagation are absent.

- [ ] **Step 3: Add the FLAC cover dependency**

Append exactly this requirement:

```text
mutagen>=1.47.0
```

Install the declared dependencies into the project virtual environment:

```bash
venv/bin/python -m pip install -r requirements.txt
```

Expected: `mutagen` installs successfully. Verify with:

```bash
venv/bin/python -c "import mutagen; print(mutagen.version_string)"
```

- [ ] **Step 4: Build MP3 and FLAC postprocessor chains**

Add `audio_format: str = MP3` to `_build_ydl_options`, validate membership in `AUDIO_FORMATS`, and replace the audio branch with:

```python
        extractor = {
            "key": "FFmpegExtractAudio",
            "preferredcodec": audio_format,
        }
        if audio_format == MP3:
            extractor["preferredquality"] = "0"
        options.update(
            {
                "format": (
                    "bestaudio[acodec^=flac]/bestaudio/best"
                    if audio_format == FLAC
                    else "bestaudio/best"
                ),
                "writethumbnail": True,
                "postprocessors": [
                    extractor,
                    {
                        "key": "FFmpegMetadata",
                        "add_metadata": True,
                        "add_chapters": False,
                        "add_infojson": False,
                    },
                    {
                        "key": "EmbedThumbnail",
                        "already_have_thumbnail": False,
                    },
                ],
            }
        )
```

The built-in `EmbedThumbnail` postprocessor returns successfully when the information dictionary has no thumbnails. With `already_have_thumbnail=False`, it removes the downloaded sidecar after embedding.

- [ ] **Step 5: Resolve actual format before processing and publish result fields**

For Bilibili, pass the requested format into metadata options, create the profile immediately after extraction, and build every transfer attempt with `audio_format=profile.used`. Pass the used format to `_resolve_output_path`, then run `_rename_audio_output` after successful postprocessing.

For non-Bilibili audio, split the current audio-only path into one metadata extraction and one `process_info` call:

```python
metadata_options = _build_ydl_options(
    platform,
    output_dir,
    index,
    total,
    progress_callback=progress_callback,
    media_type=AUDIO,
    audio_format=audio_format,
)
with yt_dlp.YoutubeDL(metadata_options) as metadata_ydl:
    info = metadata_ydl.extract_info(url, download=False)
profile = _audio_output_profile(info, audio_format)
download_options = _build_ydl_options(
    platform,
    output_dir,
    index,
    total,
    progress_callback=progress_callback,
    media_type=AUDIO,
    audio_format=profile.used,
)
with yt_dlp.YoutubeDL(download_options) as ydl:
    ydl.process_info(info)
    filepath = _resolve_output_path(
        ydl,
        info,
        output_dir,
        media_type=AUDIO,
        audio_format=profile.used,
    )
filepath = _rename_audio_output(filepath, profile)
```

Keep the current single-call `extract_info(..., download=True)` path unchanged for video. Add a small result-update helper or equivalent exact update in both result builders:

```python
result.update(
    {
        "format": "FLAC" if profile.used == FLAC else "MP3 V0",
        "acodec": profile.used,
        "audio_format_requested": profile.requested,
        "audio_format_used": profile.used,
        "audio_format_fallback": profile.fallback,
        "source_acodec": profile.source_acodec or "未知",
        "source_abr_kbps": profile.source_abr_kbps or "未知",
    }
)
```

Validate `audio_format` at the public `download_video` and `download_tasks` boundaries before starting workers, and pass it through every call. Update the function docstrings with the exact accepted values and fallback behavior.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run the focused command from Step 2. Expected: all selected test classes pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add downloader.py requirements.txt tests/test_downloader_errors.py tests/test_bilibili_support.py tests/test_parallel_downloads.py
git commit -m "feat: embed audio covers and support source flac"
```

---

### Task 3: Expose source FLAC in the CLI

**Files:**
- Modify: `main.py:15-84, 180-290`
- Test: `tests/test_cli_audio.py`

**Interfaces:**
- Consumes: Task 2 `MP3`, `FLAC`, and `download_tasks(..., audio_format=...)`.
- Produces: `choose_audio_format() -> str`.
- Changes: `parse_command_line(args) -> tuple[media_type, audio_format, speed_mode, urls]`.

- [ ] **Step 1: Write failing CLI tests**

Update existing unpacking from three to four values and add:

```python
    def test_parse_command_line_selects_source_flac(self):
        media_type, audio_format, speed_mode, urls = cli_main.parse_command_line([
            "--audio", "--flac", "https://b23.tv/example",
        ])

        self.assertEqual(media_type, downloader.AUDIO)
        self.assertEqual(audio_format, downloader.FLAC)
        self.assertEqual(speed_mode, downloader.STANDARD)
        self.assertEqual(urls, ["https://b23.tv/example"])

    def test_flac_flag_requires_audio_mode(self):
        with self.assertRaisesRegex(ValueError, "--flac 只能与 --audio 一起使用"):
            cli_main.parse_command_line(["--flac", "https://b23.tv/example"])

    def test_interactive_audio_format_defaults_to_mp3(self):
        with patch("builtins.input", return_value=""):
            self.assertEqual(cli_main.choose_audio_format(), downloader.MP3)

    def test_interactive_audio_format_accepts_flac(self):
        with patch("builtins.input", return_value="2"):
            self.assertEqual(cli_main.choose_audio_format(), downloader.FLAC)
```

Extend the mocked `download_tasks` assertion to require `audio_format=downloader.FLAC`, and make the result fixture include the five Task 2 result fields. Assert the summary contains `源站未提供 FLAC，已自动回退至 MP3 V0` when the fallback field is true.

- [ ] **Step 2: Run CLI tests and verify RED**

```bash
venv/bin/python -m unittest tests.test_cli_audio -v
```

Expected: failures from the old three-value parser and missing interactive selector.

- [ ] **Step 3: Implement CLI parsing, selection, forwarding, and summary**

Import `MP3` and `FLAC`. Implement:

```python
def choose_audio_format() -> str:
    print("请选择音频输出格式：")
    print("  1. MP3 V0（默认，兼容性最佳）")
    print("  2. 源 FLAC（无 FLAC 时自动回退 MP3 V0）")
    while True:
        choice = input("选择 1 或 2（直接回车选择 MP3）: ").strip().lower()
        if choice in {"", "1", "mp3"}:
            return MP3
        if choice in {"2", "flac"}:
            return FLAC
        print("⚠️  请输入 1 或 2。")
```

Change `parse_command_line` to remove `--flac`, reject it without `--audio`, and return `(media_type, audio_format, speed_mode, urls)`. In `main()`, set `audio_format=MP3` for video, call `choose_audio_format()` only after interactive users choose audio, and pass it to `download_tasks`.

Update usage to:

```text
python main.py [--audio [--flac]] [--turbo] <URL1> [URL2] [URL3] ...
```

For audio summaries, print actual format, source codec/rate, and this exact fallback copy when applicable:

```text
源站未提供 FLAC，已自动回退至 MP3 V0
```

- [ ] **Step 4: Run CLI tests and verify GREEN**

Run the Step 2 command. Expected: all CLI audio tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add main.py tests/test_cli_audio.py
git commit -m "feat: expose source flac in cli"
```

---

### Task 4: Expose source FLAC in the Web API and page

**Files:**
- Modify: `app.py:12-206`
- Modify: `templates/index.html:377-422, 686-709, 726-990`
- Test: `tests/test_web_progress.py:87-143, 282-340`

**Interfaces:**
- Consumes: Task 2 `AUDIO_FORMATS`, `MP3`, and `download_tasks(..., audio_format=...)`.
- Changes: `_create_batch(..., audio_format: str = MP3)` stores the requested format.
- Changes: `_run_downloads(..., audio_format: str = MP3)` forwards it.
- API: request body accepts `audio_format: "mp3" | "flac"`.

- [ ] **Step 1: Write failing API and page tests**

Add API tests:

```python
    def test_download_api_creates_flac_audio_batch(self):
        with patch("app.threading.Thread") as thread_class:
            response = self.client.post(
                "/api/download",
                json={
                    "urls": ["https://b23.tv/example"],
                    "media_type": downloader.AUDIO,
                    "audio_format": downloader.FLAC,
                },
            )

        self.assertEqual(response.status_code, 200)
        batch = web_app._batches[response.get_json()["batch_id"]]
        self.assertEqual(batch["audio_format"], downloader.FLAC)
        self.assertEqual(thread_class.call_args.kwargs["args"][4], downloader.FLAC)

    def test_download_api_rejects_unknown_and_non_string_audio_format(self):
        for value in ("wav", [downloader.FLAC]):
            with self.subTest(value=value), patch("app.threading.Thread") as thread_class:
                response = self.client.post(
                    "/api/download",
                    json={
                        "urls": ["https://youtu.be/example"],
                        "media_type": downloader.AUDIO,
                        "audio_format": value,
                    },
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("音频格式", response.get_json()["error"])
                thread_class.assert_not_called()
```

Add static page assertions for IDs `audioFormatMp3` and `audioFormatFlac`, an initially checked MP3 input, `audio_format: audioFormat`, the exact fallback message, and task-card fields `source_acodec` and `source_abr_kbps`.

- [ ] **Step 2: Run Web tests and verify RED**

```bash
venv/bin/python -m unittest tests.test_web_progress -v
```

Expected: failures for missing batch/API field and page controls.

- [ ] **Step 3: Implement Web API state and forwarding**

Import `AUDIO_FORMATS` and `MP3`. Add `audio_format=MP3` to `_create_batch` and `_run_downloads`, store it in the batch, and forward it to `download_tasks`.

In `api_download`, read and validate before URL processing:

```python
audio_format = body.get("audio_format", MP3)
if not isinstance(audio_format, str) or audio_format not in AUDIO_FORMATS:
    return jsonify({"error": "不支持的音频格式"}), 400
```

Pass `audio_format` into `_create_batch` and append it to the background thread argument tuple. On a completed event, preserve a task-level boolean for reliable JavaScript checks:

```python
task["audio_format_fallback"] = bool(
    data.get("audio_format_fallback", False)
)
```

- [ ] **Step 4: Add the Web format selector and result rendering**

Place this segmented control between the audio textarea and turbo control:

```html
<fieldset class="format-control" id="audioFormatControl">
  <legend>音频输出格式</legend>
  <label><input type="radio" name="audioFormat" id="audioFormatMp3" value="mp3" checked><span>MP3 V0</span></label>
  <label><input type="radio" name="audioFormat" id="audioFormatFlac" value="flac"><span>源 FLAC</span></label>
</fieldset>
```

Style it with the existing dark surface, border, Petronas green checked state, keyboard focus ring, and responsive two-column layout. Add the two radio inputs to `downloadControls.audio.formatInputs`; use an empty array for video and disable every format input in `setControlsDisabled`.

In `startDownload`, compute:

```javascript
const audioFormat = mediaType === "audio"
  ? document.querySelector('input[name="audioFormat"]:checked').value
  : "mp3";
```

Include `audio_format: audioFormat` in the JSON body. Use the requested format in pending and polled task titles. In completed audio cards show actual format, source codec and optional numeric kbps. If `t.audio_format_fallback` is true, render the exact sentence `源站未提供 FLAC，已自动回退至 MP3 V0` before the saved path.

- [ ] **Step 5: Run Web tests and verify GREEN**

Run the Step 2 command. Expected: all Web tests pass.

- [ ] **Step 6: Commit Task 4**

```bash
git add app.py templates/index.html tests/test_web_progress.py
git commit -m "feat: expose source flac in web ui"
```

---

### Task 5: Document and verify real MP3/FLAC outputs

**Files:**
- Modify: `README.md`
- Modify: `tests/test_bilibili_support.py:487-555`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: user-facing install, Web, CLI, filename, fallback, and cover instructions.

- [ ] **Step 1: Write a failing documentation regression test**

Add a documentation test requiring all of these exact strings in `README.md`:

```python
required = [
    "MP3 V0 / 源 FLAC",
    "python main.py --audio --flac",
    "源站未提供 FLAC，已自动回退至 MP3 V0",
    "[MP3 V0 · 源FLAC 1521kbps].mp3",
    "[FLAC Lossless · 1521kbps].flac",
    "自动嵌入视频封面",
    "没有封面时仍正常输出音频",
    "mutagen",
    "MP3 成品仍是有损音频",
]
```

- [ ] **Step 2: Run the documentation test and verify RED**

```bash
venv/bin/python -m unittest tests.test_bilibili_support.BilibiliDocumentationTests -v
```

Expected: failures for the new audio format and cover instructions.

- [ ] **Step 3: Update README usage and behavior**

Update installation to mention that `requirements.txt` installs `mutagen` for FLAC cover metadata. Update Web and CLI audio sections with the selector/flag, exact filenames, truthful MP3-versus-FLAC explanation, automatic MP3 fallback, embedded cover behavior, and the missing-cover success behavior. Keep port `8233`, cookie guidance, concurrency limits, and Bilibili acceleration documentation unchanged.

- [ ] **Step 4: Run documentation and full automated verification**

```bash
venv/bin/python -m unittest tests.test_bilibili_support.BilibiliDocumentationTests -v
venv/bin/python -m unittest discover -s tests -v
venv/bin/python -m compileall -q downloader.py bilibili_acceleration.py app.py main.py tests
git diff --check
```

Expected: documentation test passes, the complete suite reports zero failures, compileall exits 0, and `git diff --check` prints nothing.

- [ ] **Step 5: Re-run live metadata verification on the exact sample**

Use the project Bilibili extractor with `download=False` and print only safe format fields. Do not print URLs, cookies, or CDN tokens:

```bash
venv/bin/python - <<'PY'
from pathlib import Path
import downloader

url = "https://www.bilibili.com/video/BV1fsTM6CE9P?vd_source=c29bf1bb20fc12664dae270045332759"
options = downloader._build_ydl_options(
    downloader.BILIBILI,
    Path("/tmp/gtd-audio-probe"),
    1,
    1,
    media_type=downloader.AUDIO,
    audio_format=downloader.FLAC,
)
ydl, info = downloader._extract_bilibili_info(url, options)
try:
    selected = downloader._selected_audio_info(info)
    profile = downloader._audio_output_profile(info, downloader.FLAC)
    print({
        "format_id": selected.get("format_id"),
        "acodec": selected.get("acodec"),
        "abr": selected.get("abr"),
        "profile": profile,
        "thumbnail": bool(info.get("thumbnail") or info.get("thumbnails")),
    })
finally:
    ydl.close()
PY
```

Expected: format ID `30251`, codec `flac`, profile used format `flac`, bitrate near `1521`, and thumbnail true.

- [ ] **Step 6: Validate short real media outputs without downloading the album**

Create an explicit temporary directory and use yt-dlp's range downloader with the same source selector and postprocessor behavior to produce separate 8-second FLAC and MP3 V0 samples:

```bash
mkdir -p /tmp/gtd-audio-qa
venv/bin/python -m yt_dlp \
  --cookies bilibili_cookies.txt \
  --format "bestaudio[acodec^=flac]" \
  --download-sections "*0-8" \
  --force-keyframes-at-cuts \
  --extract-audio \
  --audio-format flac \
  --embed-thumbnail \
  --add-metadata \
  --output "/tmp/gtd-audio-qa/sample-flac.%(ext)s" \
  "https://www.bilibili.com/video/BV1fsTM6CE9P?vd_source=c29bf1bb20fc12664dae270045332759"
venv/bin/python -m yt_dlp \
  --cookies bilibili_cookies.txt \
  --format "bestaudio[acodec^=flac]" \
  --download-sections "*0-8" \
  --force-keyframes-at-cuts \
  --extract-audio \
  --audio-format mp3 \
  --audio-quality 0 \
  --embed-thumbnail \
  --add-metadata \
  --output "/tmp/gtd-audio-qa/sample-mp3.%(ext)s" \
  "https://www.bilibili.com/video/BV1fsTM6CE9P?vd_source=c29bf1bb20fc12664dae270045332759"
```

Inspect both files:

```bash
ffprobe -v error -show_entries stream=index,codec_name,codec_type,disposition:format_tags -of json /tmp/gtd-audio-qa/sample-flac.flac
ffprobe -v error -show_entries stream=index,codec_name,codec_type,disposition:format_tags -of json /tmp/gtd-audio-qa/sample-mp3.mp3
find /tmp/gtd-audio-qa -maxdepth 1 -type f -exec basename {} \; | sort
```

Expected: FLAC file has a FLAC audio stream and embedded picture metadata; MP3 has an MP3 audio stream and an attached-picture stream. The file listing contains only `sample-flac.flac` and `sample-mp3.mp3`, with no standalone thumbnail. After recording the results, remove only the explicit QA directory:

```bash
rm -rf /tmp/gtd-audio-qa
```

- [ ] **Step 7: Perform local Web API/UI validation**

Use Flask's test client to submit MP3 and FLAC audio batches and verify stored `audio_format` values. Restart only this project's non-debug Flask process if it is already serving port 8233, load `http://127.0.0.1:8233`, and confirm the format selector is keyboard-operable, disabled during a task, and leaves the video input independent. Do not stop macOS `ControlCenter` or any process not identified by command and project cwd.

- [ ] **Step 8: Commit Task 5**

```bash
git add README.md tests/test_bilibili_support.py
git commit -m "docs: explain mp3 and source flac outputs"
```

- [ ] **Step 9: Final branch verification**

```bash
venv/bin/python -m unittest discover -s tests -v
venv/bin/python -m compileall -q downloader.py bilibili_acceleration.py app.py main.py tests
git diff --check
git status --short --branch
```

Expected: all tests pass, compileall and diff checks exit 0, and only intentional commits are present.
