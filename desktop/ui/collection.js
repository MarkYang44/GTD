// The collection picker: shown when a preview needs the user to choose items (playlists, collections).
import { errorParts } from "./strings.js";
import { $, closeDialog, element, fillCallout, openDialog, reconcile, setText } from "./ui.js";
import { platformName } from "./tasks.js";
import { defaultFolder, startDownload } from "./service.js";
import { state, t } from "./store.js";

export const MAX_SELECTED = 100;
let preview = null;

export const collectionOpen = () => Boolean(preview);

export function openCollection({ result, options, onAdded, returnFocus }) {
  const selected = new Set(result.entries.filter(entry => entry.selectable).slice(0, MAX_SELECTED).map(entry => entry.id));
  preview = { result, options, selected, onAdded, returnFocus, busy: false, query: "", last: "", rows: new Map(), empty: null };
  notice("");
  renderCollection();
  openDialog($("collection"));
  (result.entries.length > 8 ? $("collection-search") : $("submit-collection")).focus();
}

function notice(message) {
  const target = $("collection-notice");
  target.hidden = !message;
  if (message) fillCallout(target, { tone: "error", codeLabel: t("errorCode"), ...message });
  else target.replaceChildren();
}

function entryName(entry) {
  return entry.title_is_generated || !entry.title ? t("untitledItem", { position: entry.position }) : entry.title;
}

function entryReason(entry) {
  if (entry.selectable) return "";
  if (state.language === "en") {
    if (entry.unavailable_reason === "内容不可访问") return "Content is inaccessible";
    if (entry.unavailable_reason === "源站未提供可下载链接") return "The source has no downloadable link";
  }
  return entry.unavailable_reason || t("notSelectable");
}

function collectionRow(entry) {
  const row = element("li", "collection-entry");
  row.dataset.available = String(entry.selectable === true);
  const checkbox = element("input");
  checkbox.type = "checkbox";
  checkbox.value = entry.id;
  const position = element("span", "entry-position", String(entry.position));
  const copy = element("span", "entry-copy");
  const title = element("span", "entry-title");
  const meta = element("span", "entry-meta");
  copy.append(title, meta);
  row.append(checkbox, position, copy);
  row.addEventListener("click", event => {
    if (!preview || preview.busy || !entry.selectable) return;
    const fromBox = event.target === checkbox;
    toggleEntries(entry, fromBox ? checkbox.checked : !checkbox.checked, event.shiftKey);
  });
  return { row, checkbox, title, meta };
}

function visibleEntries() {
  const query = preview.query.trim().toLocaleLowerCase();
  return preview.result.entries.filter(entry => !query || entryName(entry).toLocaleLowerCase().includes(query));
}

function toggleEntries(entry, checked, range) {
  let targets = [entry];
  if (range && preview.last) {
    const list = visibleEntries();
    const from = list.findIndex(item => item.id === preview.last);
    const to = list.findIndex(item => item.id === entry.id);
    if (from >= 0 && to >= 0) targets = list.slice(Math.min(from, to), Math.max(from, to) + 1);
  }
  for (const item of targets) {
    if (!item.selectable) continue;
    if (!checked) preview.selected.delete(item.id);
    else if (preview.selected.size < MAX_SELECTED) preview.selected.add(item.id);
  }
  preview.last = entry.id;
  refresh();
}

export function renderCollection() {
  if (!preview) return;
  const { result, options } = preview;
  const title = (!result.title_is_generated && result.title) || "";
  $("collection-title").textContent = title;
  $("collection-title").hidden = !title;
  const unavailable = result.entries.filter(entry => !entry.selectable).length;
  const seen = [...new Set(result.entries.map(entry => platformName(entry.platform, t)))];
  const number = value => value.toLocaleString(state.language === "zh" ? "zh-CN" : "en-US");
  $("collection-meta").textContent = [
    t("collectionMeta", { platform: seen.join(" + "), count: number(result.entries.length) }),
    unavailable ? t("collectionUnavailable", { count: number(unavailable) }) : "",
  ].filter(Boolean).join(" · ");
  if (result.truncated) fillCallout($("collection-truncated"), { tone: "info", message: t("truncated") });
  $("collection-truncated").hidden = !result.truncated;
  $("collection-search").value = preview.query;
  $("collection-search").closest(".search-field").hidden = result.entries.length < 8;
  const summary = [t(options.media_type === "audio" ? "audio" : "video")];
  if (options.media_type === "audio") summary.push(t(`formatLabel_${options.audio_format}`));
  if (options.subtitle_options?.subtitles) summary.push(t(options.subtitle_options.automatic ? "summaryAutomatic" : "summarySubtitles"));
  if (options.subtitle_options?.danmaku) summary.push(t("summaryDanmaku"));
  if (options.speed_mode === "turbo") summary.push(t("summaryTurbo"));
  summary.push(options.download_dir || defaultFolder());
  $("collection-summary").textContent = summary.filter(Boolean).join(" · ");
  $("collection-summary").title = $("collection-summary").textContent;
  for (const entry of result.entries) {
    if (!preview.rows.has(entry.id)) preview.rows.set(entry.id, collectionRow(entry));
  }
  refresh();
}

function refresh() {
  const visible = visibleEntries();
  const visibleIds = new Set(visible.map(entry => entry.id));
  const available = visible.filter(entry => entry.selectable);
  const capped = available.slice(0, MAX_SELECTED);
  const size = preview.selected.size;
  const chosenVisible = available.filter(entry => preview.selected.has(entry.id)).length;
  const query = preview.query.trim();
  const allAvailable = preview.result.entries.filter(entry => entry.selectable).length;
  $("collection-select-label").textContent = query ? t("selectMatches")
    : allAvailable > MAX_SELECTED ? t("selectFirst", { count: MAX_SELECTED }) : t("selectAll");
  const all = $("collection-select-all");
  all.checked = capped.length > 0 && capped.every(entry => preview.selected.has(entry.id));
  all.indeterminate = !all.checked && chosenVisible > 0;
  all.disabled = preview.busy || !available.length;
  $("collection-count").textContent = t("collectionCount", { count: size });
  $("collection-count").dataset.full = String(size >= MAX_SELECTED);
  $("collection-count").title = t("rangeHint");
  const submit = $("submit-collection");
  submit.disabled = preview.busy || !size;
  setText(submit.lastElementChild, preview.busy ? t("adding") : size ? t("submitSelected", { count: size }) : t("submitNone"));
  $("close-collection").disabled = preview.busy;
  $("back-collection").disabled = preview.busy;
  const nodes = [];
  for (const entry of preview.result.entries) {
    if (!visibleIds.has(entry.id)) continue;
    const view = preview.rows.get(entry.id);
    const name = entryName(entry);
    const checked = preview.selected.has(entry.id);
    view.checkbox.checked = checked;
    view.checkbox.disabled = preview.busy || !entry.selectable || (!checked && size >= MAX_SELECTED);
    view.checkbox.setAttribute("aria-label", name);
    view.row.dataset.checked = String(checked);
    setText(view.title, name);
    view.title.title = name;
    const reason = entryReason(entry);
    const metaKey = `${state.language}:${reason}`;
    if (view.meta.dataset.key !== metaKey) {
      view.meta.dataset.key = metaKey;
      view.meta.replaceChildren(element("span", "", platformName(entry.platform, t)));
      if (reason) view.meta.append(element("span", "entry-reason", reason));
    }
    nodes.push(view.row);
  }
  if (!nodes.length) {
    preview.empty ||= element("li", "collection-empty");
    preview.empty.textContent = t("noItemMatches", { query });
    nodes.push(preview.empty);
  }
  reconcile($("collection-list"), nodes);
}

export function closeCollection() {
  if (!preview || preview.busy) return;
  const target = preview.returnFocus;
  preview = null;
  closeDialog($("collection"), { returnFocus: target });
  notice("");
}

async function addSelected() {
  if (!preview || preview.busy) return;
  const current = preview;
  current.busy = true;
  refresh();
  notice("");
  try {
    const ids = current.result.entries.filter(entry => current.selected.has(entry.id)).map(entry => entry.id);
    const response = await startDownload(current.options, current.result.preview_id, ids);
    current.busy = false;
    if (preview === current) closeCollection();
    current.onAdded?.(response);
  } catch (error) {
    current.busy = false;
    if (preview === current) {
      notice(errorParts(error, state.language));
      refresh();
    }
  }
}

$("collection-select-all").addEventListener("change", event => {
  if (!preview || preview.busy) return;
  const available = visibleEntries().filter(entry => entry.selectable);
  if (event.target.checked) {
    for (const entry of available) {
      if (preview.selected.size >= MAX_SELECTED) break;
      preview.selected.add(entry.id);
    }
  } else {
    for (const entry of available) preview.selected.delete(entry.id);
  }
  refresh();
});
$("collection-search").addEventListener("input", event => {
  if (!preview) return;
  preview.query = event.target.value;
  preview.last = "";
  refresh();
});
$("collection-search").addEventListener("keydown", event => {
  // First Escape clears the filter; the next one closes the dialog. Search fields consume Escape
  // themselves (even when empty), so the dialog would never see it otherwise.
  if (event.key !== "Escape" || !preview) return;
  event.preventDefault();
  event.stopPropagation();
  if (!event.target.value) {
    closeCollection();
    return;
  }
  event.target.value = "";
  preview.query = "";
  refresh();
});
$("collection").addEventListener("cancel", event => {
  event.preventDefault();
  if (event.target === $("collection")) closeCollection();
});
$("collection").addEventListener("keydown", event => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !$("submit-collection").disabled) {
    event.preventDefault();
    addSelected();
  }
});
$("close-collection").addEventListener("click", closeCollection);
$("back-collection").addEventListener("click", closeCollection);
$("submit-collection").addEventListener("click", addSelected);
