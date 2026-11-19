// The add bar at the top of Downloads: links (or one local video) plus the options that apply to them.
// Options persist between launches; a one-off folder choice lasts until the app restarts.
import { errorParts } from "./strings.js";
import { $, fillCallout, isMac, setText, toast } from "./ui.js";
import { toggleMenu } from "./menu.js";
import { load, save } from "./prefs.js";
import { MAX_SELECTED, openCollection } from "./collection.js";
import { defaultFolder, pickPath, previewLinks, reveal, startDownload, startExtraction } from "./service.js";
import { flush, state, t, update } from "./store.js";

export const MAX_LINKS = 20;
const AUDIO_FORMATS = ["mp3", "flac", "source", "wav"];
const EXTRACT_FORMATS = ["source", "mp3"];
const saved = load("composer", {});
const options = {
  media: saved.media === "audio" ? "audio" : "video",
  audioFormat: AUDIO_FORMATS.includes(saved.audioFormat) ? saved.audioFormat : "mp3",
  extractFormat: EXTRACT_FORMATS.includes(saved.extractFormat) ? saved.extractFormat : "source",
  subtitles: saved.subtitles === true,
  automatic: saved.subtitles === true && saved.automatic === true,
  danmaku: saved.danmaku === true,
  turbo: saved.turbo === true,
};
const local = { file: "", folder: "", busy: false, error: null };
const field = $("composer-links");

function setOption(name, value) {
  options[name] = value;
  if (name === "subtitles" && !value) options.automatic = false;
  save("composer", options);
  render();
}

const readLinks = () => field.value.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
const turboReady = () => Boolean(state.capabilities?.aria2c_available) && state.connection === "ready";
const folder = () => local.folder || defaultFolder();
const basename = path => path.split(/[\\/]/).filter(Boolean).pop() || path;

function showError(parts) {
  local.error = typeof parts === "string" ? { message: parts } : parts;
  render();
}

function clearError() {
  if (!local.error) return;
  local.error = null;
  render();
}

function autogrow() {
  field.style.height = "auto";
  field.style.height = `${Math.min(field.scrollHeight, 168)}px`;
}

function collectOptions() {
  const request = {
    media_type: options.media,
    audio_format: options.media === "audio" ? options.audioFormat : "mp3",
    speed_mode: turboReady() && options.turbo ? "turbo" : "standard",
    download_dir: local.folder || state.settings?.download_dir || "",
  };
  if (options.media === "video") {
    request.subtitle_options = { subtitles: options.subtitles, automatic: options.subtitles && options.automatic, danmaku: options.danmaku };
  }
  return request;
}

// New tasks should be visible right away: leave scopes that would filter them out.
function afterAdd(response, source) {
  if (source != null && field.value === source) {
    field.value = "";
    autogrow();
  }
  update(s => {
    if (!["all", "active", "queued"].includes(s.downloads.scope)) s.downloads.scope = "all";
  });
  toast(t("added", { count: response.task_count }), { dismissLabel: t("dismiss") });
  render();
}

async function submit() {
  if (local.busy || state.connection !== "ready") return;
  if (local.file) {
    await extractFile();
    return;
  }
  const inputs = readLinks();
  if (!inputs.length) {
    field.focus();
    return;
  }
  if (inputs.length > MAX_LINKS) {
    showError(t("linkLimit"));
    field.focus();
    return;
  }
  local.error = null;
  local.busy = true;
  render();
  const source = field.value;
  const request = collectOptions();
  try {
    const result = await previewLinks(inputs);
    const selectable = result.entries.filter(entry => entry.selectable).slice(0, MAX_SELECTED).map(entry => entry.id);
    if (result.requires_selection) {
      openCollection({ result, options: request, returnFocus: field, onAdded: response => afterAdd(response, source) });
    } else if (selectable.length) {
      afterAdd(await startDownload(request, result.preview_id, selectable), source);
    } else {
      local.error = { message: t("noEntries") };
    }
  } catch (error) {
    local.error = errorParts(error, state.language);
  } finally {
    local.busy = false;
    render();
  }
}

async function extractFile() {
  local.error = null;
  local.busy = true;
  render();
  try {
    const response = await startExtraction({
      path: local.file, audio_format: options.extractFormat, download_dir: local.folder || state.settings?.download_dir || "",
    });
    local.file = "";
    afterAdd(response, null);
    flush();
    field.focus();
  } catch (error) {
    local.error = errorParts(error, state.language);
  } finally {
    local.busy = false;
    render();
  }
}

export async function pickFile() {
  if (local.busy) return;
  try {
    const path = await pickPath("video");
    if (!path) return;
    local.file = path;
    local.error = null;
    render();
    $("composer-submit").focus();
  } catch (error) {
    showError(errorParts(error, state.language));
  }
}

async function chooseFolder() {
  try {
    const location = await pickPath("folder", folder() || undefined);
    if (!location) return;
    local.folder = location === defaultFolder() ? "" : location;
    render();
  } catch (error) {
    showError(errorParts(error, state.language));
  }
}

export function focus() {
  const target = local.file ? $("composer-submit") : field;
  target.focus({ preventScroll: false });
  if (target === field) field.setSelectionRange(field.value.length, field.value.length);
}

// Pasting outside a text field lands in the link box, on a line of its own.
export function prepareForPaste() {
  if (local.file) {
    local.file = "";
    render();
  }
  if (field.value && !field.value.endsWith("\n")) field.value += "\n";
  field.focus();
  field.setSelectionRange(field.value.length, field.value.length);
}

export function insertText(text) {
  const lines = String(text).split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  if (!lines.length) return;
  local.file = "";
  const current = field.value.replace(/\s+$/, "");
  field.value = current ? `${current}\n${lines.join("\n")}` : lines.join("\n");
  local.error = null;
  autogrow();
  render();
  focus();
}

function formatMenu() {
  const extracting = Boolean(local.file);
  const formats = extracting ? EXTRACT_FORMATS : AUDIO_FORMATS;
  const key = extracting ? "extractFormat" : "audioFormat";
  return {
    label: t("audioFormat"),
    items: formats.map(format => ({
      type: "radio",
      label: t(`formatLabel_${format}`),
      hint: t(`${extracting ? "extractHint" : "formatHint"}_${format}`),
      checked: () => options[key] === format,
      run: () => setOption(key, format),
    })),
  };
}

function tracksMenu() {
  return {
    label: t("textTracks"),
    items: [
      { type: "checkbox", label: t("subtitles"), checked: () => options.subtitles, run: value => setOption("subtitles", value) },
      {
        type: "checkbox", label: t("automatic"), hint: t("automaticHint"),
        checked: () => options.automatic, disabled: () => !options.subtitles, run: value => setOption("automatic", value),
      },
      { type: "checkbox", label: t("danmaku"), hint: t("danmakuHint"), checked: () => options.danmaku, run: value => setOption("danmaku", value) },
      { type: "note", label: t("subtitlesHint") },
    ],
  };
}

function folderMenu() {
  const current = folder();
  return {
    label: t("outputFolder"),
    items: [
      { type: "heading", label: current, mono: true, title: current },
      { label: t("chooseFolderEllipsis"), icon: "folder", run: chooseFolder },
      local.folder ? { label: t("useDefaultFolder"), hint: defaultFolder(), icon: "undo", run: () => { local.folder = ""; render(); } } : null,
      { label: t("openFolder"), icon: "external", disabled: !current, run: () => reveal(current).catch(error => showError(errorParts(error, state.language))) },
    ],
  };
}

function trackSummary() {
  const parts = [];
  if (options.subtitles) parts.push(t(options.automatic ? "shortAutomatic" : "shortSubtitles"));
  if (options.danmaku) parts.push(t("shortDanmaku"));
  return parts.length ? parts.join(t("listSeparator")) : t("tracksOff");
}

export function render() {
  const ready = state.connection === "ready";
  const extracting = Boolean(local.file);
  const composer = $("composer");
  composer.dataset.mode = extracting ? "file" : "links";
  composer.dataset.busy = String(local.busy);
  field.hidden = extracting;
  $("composer-file").hidden = !extracting;
  if (extracting) {
    setText($("composer-file-name"), basename(local.file));
    setText($("composer-file-path"), local.file);
    $("composer-file-path").title = local.file;
  }
  field.readOnly = local.busy;
  const count = readLinks().length;
  const counter = $("composer-count");
  counter.hidden = extracting || count === 0;
  setText(counter, count > MAX_LINKS ? t("linkCountOver", { count, max: MAX_LINKS }) : t("linkCount", { count }));
  counter.dataset.invalid = String(count > MAX_LINKS);

  for (const input of document.querySelectorAll('input[name="composer-media"]')) {
    input.checked = input.value === options.media;
    input.disabled = local.busy;
  }
  $("composer-media").hidden = extracting;
  const format = $("composer-format");
  format.hidden = !extracting && options.media !== "audio";
  const formatValue = t(`formatLabel_${extracting ? options.extractFormat : options.audioFormat}`);
  setText(format.querySelector(".property-value"), formatValue);
  format.setAttribute("aria-label", `${t("audioFormat")}: ${formatValue}`);
  format.disabled = local.busy;
  const tracks = $("composer-tracks");
  tracks.hidden = extracting || options.media !== "video";
  const trackValue = trackSummary();
  setText(tracks.querySelector(".property-value"), trackValue);
  tracks.setAttribute("aria-label", `${t("textTracks")}: ${trackValue}`);
  tracks.dataset.on = String(options.subtitles || options.danmaku);
  tracks.disabled = local.busy;
  const turbo = $("composer-turbo");
  turbo.hidden = extracting;
  turbo.disabled = local.busy || !turboReady();
  turbo.setAttribute("aria-pressed", String(turboReady() && options.turbo));
  turbo.title = t(state.connection === "unavailable" ? "turboOffline" : !state.capabilities ? "turboChecking"
    : state.capabilities.aria2c_available ? "turboReady" : "turboMissing");
  const place = $("composer-folder");
  const current = folder();
  setText(place.querySelector(".property-value"), current ? basename(current) : t("outputFolder"));
  place.title = current;
  place.setAttribute("aria-label", `${t("outputFolder")}: ${current}`);
  place.dataset.custom = String(Boolean(local.folder));
  place.disabled = local.busy;
  $("composer-from-file").hidden = extracting;
  $("composer-from-file").disabled = local.busy;
  $("composer-file-clear").disabled = local.busy;

  const submitButton = $("composer-submit");
  submitButton.disabled = local.busy || !ready || (!extracting && (count === 0 || count > MAX_LINKS));
  setText(submitButton.querySelector(".button-label"), t(local.busy ? (extracting ? "preparing" : "previewBusy") : extracting ? "startExtract" : "downloadAction"));
  submitButton.dataset.busy = String(local.busy);

  const hint = !ready ? t(state.connection === "unavailable" ? "turboOffline" : "starting")
    : extracting ? t(`extractHint_${options.extractFormat}`)
      : options.media === "audio" ? t(`formatHint_${options.audioFormat}`)
        : t("composerKeys", { enter: isMac ? "↩" : "Enter", newline: isMac ? "⇧↩" : "Shift+Enter" });
  setText($("composer-hint"), hint);

  const notice = $("composer-notice");
  notice.hidden = !local.error;
  if (local.error) fillCallout(notice, { tone: "error", codeLabel: t("errorCode"), ...local.error });
}

function onMenu(anchor, build) {
  if (!anchor.disabled) toggleMenu(anchor, build);
}

$("composer").addEventListener("submit", event => {
  event.preventDefault();
  submit();
});
field.addEventListener("input", () => {
  autogrow();
  if (local.error && readLinks().length <= MAX_LINKS) local.error = null;
  if (readLinks().length > MAX_LINKS) local.error = { message: t("linkLimit") };
  render();
});
field.addEventListener("keydown", event => {
  if (event.key !== "Enter" || event.isComposing || event.keyCode === 229) return;
  const modifier = event.metaKey || event.ctrlKey;
  if (event.shiftKey && !modifier) return;
  event.preventDefault();
  if (!$("composer-submit").disabled) submit();
});
for (const input of document.querySelectorAll('input[name="composer-media"]')) {
  input.addEventListener("change", () => setOption("media", input.value));
}
$("composer-format").addEventListener("click", event => onMenu(event.currentTarget, formatMenu));
$("composer-tracks").addEventListener("click", event => onMenu(event.currentTarget, tracksMenu));
$("composer-folder").addEventListener("click", event => onMenu(event.currentTarget, folderMenu));
$("composer-turbo").addEventListener("click", () => setOption("turbo", !(turboReady() && options.turbo)));
$("composer-from-file").addEventListener("click", pickFile);
$("composer-file-clear").addEventListener("click", () => {
  local.file = "";
  local.error = null;
  render();
  field.focus();
});
