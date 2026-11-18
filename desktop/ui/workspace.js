import { errorParts, formatError, translate } from "./strings.js";
import {
  $, button, closeDialog, copyText, dayKey, dayLabel, element, fillCallout, flash, formatClock,
  formatDateTime, icon, isMac, openDialog, reconcile, setHidden, setText, shortcutLabel, toast,
} from "./ui.js";
import {
  TaskList, emptyState, isActive, percentOf, platformName, queueOrder, statusInfo, taskKey, taskName,
} from "./tasks.js";

const select = selector => document.querySelectorAll(selector);
const platforms = ["youtube", "instagram", "bilibili"];
const platformMarks = { youtube: "YT", instagram: "IG", bilibili: "BL" };
const maxLinks = 20;
const maxSelected = 100;
const pages = ["download", "queue", "history", "extract", "settings"];
const state = {
  page: "download",
  connection: "starting",
  connectionError: "",
  language: "en",
  settings: null,
  capabilities: null,
  version: "",
  batches: [],
  snapshots: new Map(),
  index: new Map(),
  session: new Set(),
  dismissed: new Set(),
  currentBatch: "",
  historyQuery: "",
  localPath: "",
  cookieErrors: {},
  confirmRemove: "",
  queue: { selected: new Set(), filter: "all", expanded: "" },
  history: { selected: new Set(), filter: "all", expanded: "" },
};
let preview = null;
let downloadBusy = false;
let extractBusy = false;
let settingsBusy = false;
let queueBusy = false;
let booting = false;
let poll = null;
let pollTimer = null;
let indexing = null;
let confirmTimer = null;

const t = (key, values) => translate(key, state.language, values);
const ctx = { t, get language() { return state.language; } };

function invoke(command, args) {
  if (!window.__TAURI__?.core?.invoke) {
    return Promise.reject(new Error("Open this workspace in GTD Desktop."));
  }
  return window.__TAURI__.core.invoke(command, args);
}

function api(path, body) {
  return invoke("api", body === undefined ? { path } : { path, body });
}

// Inline messages: success copy uses a toast, persistent problems stay next to their source.
function notice(id, message, tone = "error") {
  const target = $(`${id}-notice`);
  if (!message) {
    target.hidden = true;
    target.replaceChildren();
    return;
  }
  const parts = typeof message === "string" ? { message } : message;
  fillCallout(target, { tone, codeLabel: t("errorCode"), ...parts });
  target.hidden = false;
}

function showError(id, error) {
  notice(id, errorParts(error, state.language));
}

function localize() {
  const root = document.documentElement;
  root.lang = state.language === "zh" ? "zh-CN" : "en";
  root.dataset.theme = state.settings?.theme || "system";
  for (const node of select("[data-copy]")) node.textContent = t(node.dataset.copy);
  for (const node of select("[data-label]")) node.setAttribute("aria-label", t(node.dataset.label));
  for (const node of select("[data-placeholder]")) node.placeholder = t(node.dataset.placeholder);
  for (const [index, control] of [...select("nav [data-page]")].entries()) {
    const label = t(control.dataset.page);
    control.setAttribute("aria-label", label);
    control.title = t("shortcut", { label, keys: shortcutLabel(index + 1) });
  }
  $("submit-hint").textContent = t("submitShortcut", { keys: isMac ? "⌘↩" : "Ctrl+Enter" });
  $("app-heading").textContent = t(state.page);
  renderConnection();
  renderCompose();
  renderLocal();
  renderSettings();
  updateSummaries();
  renderActivity();
  if (preview) renderCollection();
  renderResults();
}

function openPage(page, { focus = true, expand = "" } = {}) {
  if (!pages.includes(page)) return;
  state.page = page;
  for (const key of pages) $(`view-${key}`).hidden = key !== page;
  for (const control of select("nav [data-page]")) {
    if (control.dataset.page === page) control.setAttribute("aria-current", "page");
    else control.removeAttribute("aria-current");
  }
  $("app-heading").textContent = t(page);
  if (expand && page === "queue") {
    state.queue.filter = "all";
    state.queue.expanded = expand;
  }
  if (focus) {
    window.scrollTo(0, 0);
    $("app-heading").focus({ preventScroll: true });
  }
  if (page === "download") renderActivity();
  if (page === "settings") renderSettings();
  renderResults();
  if (page === "history") {
    refreshQueue();
    buildIndex();
    loadBatch(state.currentBatch);
  }
}

function renderConnection() {
  const busy = booting && state.connection !== "ready";
  $("connection-text").textContent = t(state.connection);
  $("connection-dot").dataset.connection = state.connection;
  $("service-banner").hidden = state.connection !== "unavailable";
  $("service-error").textContent = state.connectionError;
  $("reconnect").disabled = busy;
  $("reconnect").textContent = t(busy ? "reconnecting" : "reconnect");
}

function applySettings(settings) {
  const previous = state.settings?.download_dir || state.settings?.default_download_dir || "";
  state.settings = settings;
  state.language = settings.language === "zh" ? "zh" : "en";
  const folder = settings.download_dir || settings.default_download_dir || "";
  for (const id of ["download-folder", "extract-folder"]) {
    const input = $(id);
    input.placeholder = folder;
    if (!input.value || input.value === previous) input.value = folder;
  }
  localize();
}

async function boot() {
  clearTimeout(pollTimer);
  booting = true;
  if (state.connection !== "unavailable") state.connection = "starting";
  renderConnection();
  renderCompose();
  renderLocal();
  try {
    const [settings, capabilities] = await Promise.all([
      api("/api/desktop/settings"),
      api("/api/capabilities"),
    ]);
    state.capabilities = capabilities;
    state.connection = "ready";
    state.connectionError = "";
    booting = false;
    applySettings(settings);
    void invoke("renderer_ready", {}).catch(() => {});
    await refreshQueue();
  } catch (error) {
    booting = false;
    state.connection = "unavailable";
    state.connectionError = formatError(error, state.language);
    renderConnection();
    renderCompose();
    renderLocal();
    renderSettings();
  }
}

/* Download */

function readLinks() {
  return $("download-links").value.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
}

const checkedValue = name => document.querySelector(`input[name="${name}"]:checked`)?.value;

function renderCompose() {
  const media = checkedValue("media");
  $("video-options").hidden = media !== "video";
  $("audio-options").hidden = media !== "audio";
  $("automatic").disabled = !$("subtitles").checked;
  if ($("automatic").disabled) $("automatic").checked = false;
  $("download-format-hint").textContent = t(`formatHint_${checkedValue("download-format")}`);
  const count = readLinks().length;
  $("link-count").textContent = `${count} / ${maxLinks}`;
  $("link-count").dataset.invalid = count > maxLinks;
  $("turbo").disabled = !state.capabilities?.aria2c_available;
  $("turbo-hint").textContent = t(state.connection === "unavailable" ? "turboOffline" : !state.capabilities ? "turboChecking"
    : state.capabilities.aria2c_available ? "turboReady" : "turboMissing");
  $("preview-button").disabled = downloadBusy || state.connection !== "ready" || count > maxLinks;
  $("preview-button").textContent = t(downloadBusy ? "previewBusy" : "previewLinks");
}

function collectDownloadOptions() {
  const media = checkedValue("media");
  const options = {
    media_type: media,
    audio_format: media === "audio" ? checkedValue("download-format") : "mp3",
    speed_mode: !$("turbo").disabled && $("turbo").checked ? "turbo" : "standard",
    download_dir: $("download-folder").value.trim() || state.settings.download_dir || "",
  };
  if (media === "video") {
    options.subtitle_options = {
      subtitles: $("subtitles").checked,
      automatic: $("subtitles").checked && $("automatic").checked,
      danmaku: $("danmaku").checked,
    };
  }
  return options;
}

async function startPreview(event) {
  event.preventDefault();
  if (downloadBusy || state.connection !== "ready") return;
  const inputs = readLinks();
  if (!inputs.length || inputs.length > maxLinks) {
    notice("download", t(inputs.length ? "linkLimit" : "linksPlaceholder"));
    $("download-links").focus();
    return;
  }
  notice("download", "");
  const source = $("download-links").value;
  const options = collectDownloadOptions();
  downloadBusy = true;
  renderCompose();
  try {
    const result = await api("/api/preview", { inputs });
    const selected = new Set(result.entries.filter(entry => entry.selectable).slice(0, maxSelected).map(entry => entry.id));
    if (result.requires_selection) {
      preview = { result, options, selected, source, busy: false, query: "", last: "", rows: new Map() };
      renderCollection();
      openDialog($("collection"));
      (result.entries.length > 8 ? $("collection-search") : $("submit-collection")).focus();
    } else if (selected.size) {
      await submitPreview({ result, options, selected, source });
    } else {
      notice("download", t("noEntries"));
    }
  } catch (error) {
    showError("download", error);
  } finally {
    downloadBusy = false;
    renderCompose();
  }
}

async function submitPreview(selection) {
  const selectedIds = selection.result.entries
    .filter(entry => selection.selected.has(entry.id)).map(entry => entry.id);
  const response = await api("/api/download", {
    ...selection.options,
    preview_id: selection.result.preview_id,
    selected_entry_ids: selectedIds,
  });
  if (preview) {
    preview = null;
    closeDialog($("collection"));
  }
  if ($("download-links").value === selection.source) $("download-links").value = "";
  notice("download", "");
  await showNewBatch(response);
}

/* Collection dialog */

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
    const next = fromBox ? checkbox.checked : !checkbox.checked;
    toggleEntries(entry, next, event.shiftKey);
  });
  return { row, checkbox, title, meta, entry };
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
    else if (preview.selected.size < maxSelected) preview.selected.add(item.id);
  }
  preview.last = entry.id;
  refreshCollectionControls();
}

function renderCollection() {
  const { result } = preview;
  const title = !result.title_is_generated && result.title || "";
  $("collection-title").textContent = title;
  $("collection-title").hidden = !title;
  const unavailable = result.entries.filter(entry => !entry.selectable).length;
  const platformsSeen = [...new Set(result.entries.map(entry => platformName(entry.platform, t)))];
  const number = value => value.toLocaleString(state.language === "zh" ? "zh-CN" : "en-US");
  $("collection-meta").textContent = [
    t("collectionMeta", { platform: platformsSeen.join(" + "), count: number(result.entries.length) }),
    unavailable ? t("collectionUnavailable", { count: number(unavailable) }) : "",
  ].filter(Boolean).join(" · ");
  if (result.truncated) fillCallout($("collection-truncated"), { tone: "info", message: t("truncated") });
  $("collection-truncated").hidden = !result.truncated;
  $("collection-search").value = preview.query;
  $("collection-search").closest(".search-field").hidden = result.entries.length < 8;
  const options = preview.options;
  const summary = [t(options.media_type === "audio" ? "audio" : "video")];
  if (options.media_type === "audio") summary.push(t(`formatLabel_${options.audio_format}`));
  if (options.subtitle_options?.subtitles) summary.push(t(options.subtitle_options.automatic ? "summaryAutomatic" : "summarySubtitles"));
  if (options.subtitle_options?.danmaku) summary.push(t("summaryDanmaku"));
  if (options.speed_mode === "turbo") summary.push(t("summaryTurbo"));
  const folder = options.download_dir || state.settings?.default_download_dir || "";
  $("collection-summary").textContent = [...summary, folder].filter(Boolean).join(" · ");
  $("collection-summary").title = $("collection-summary").textContent;
  for (const entry of result.entries) {
    if (!preview.rows.has(entry.id)) preview.rows.set(entry.id, collectionRow(entry));
  }
  refreshCollectionControls();
}

function refreshCollectionControls() {
  const visible = visibleEntries();
  const visibleIds = new Set(visible.map(entry => entry.id));
  const available = visible.filter(entry => entry.selectable);
  const capped = available.slice(0, Math.max(maxSelected, 0));
  const size = preview.selected.size;
  const chosenVisible = available.filter(entry => preview.selected.has(entry.id)).length;
  const query = preview.query.trim();
  const allAvailable = preview.result.entries.filter(entry => entry.selectable).length;
  $("collection-select-label").textContent = query ? t("selectMatches")
    : allAvailable > maxSelected ? t("selectFirst", { count: maxSelected }) : t("selectAll");
  const all = $("collection-select-all");
  all.checked = capped.length > 0 && capped.every(entry => preview.selected.has(entry.id));
  all.indeterminate = !all.checked && chosenVisible > 0;
  all.disabled = preview.busy || !available.length;
  $("collection-count").textContent = t("collectionCount", { count: size });
  $("collection-count").dataset.full = String(size >= maxSelected);
  $("collection-count").title = t("rangeHint");
  const submit = $("submit-collection");
  submit.disabled = preview.busy || !size;
  submit.textContent = preview.busy ? t("adding") : size ? t("submitSelected", { count: size }) : t("submitNone");
  $("close-collection").disabled = preview.busy;
  $("back-collection").disabled = preview.busy;
  const nodes = [];
  for (const entry of preview.result.entries) {
    const view = preview.rows.get(entry.id);
    if (!visibleIds.has(entry.id)) continue;
    const name = entryName(entry);
    const checked = preview.selected.has(entry.id);
    view.checkbox.checked = checked;
    view.checkbox.disabled = preview.busy || !entry.selectable || (!checked && size >= maxSelected);
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

function closePreview() {
  if (!preview || preview.busy) return;
  preview = null;
  closeDialog($("collection"), { returnFocus: $("download-links") });
  notice("collection", "");
}

async function addSelected() {
  if (!preview || preview.busy) return;
  preview.busy = true;
  refreshCollectionControls();
  notice("collection", "");
  try {
    await submitPreview(preview);
  } catch (error) {
    showError("collection", error);
  } finally {
    if (preview) {
      preview.busy = false;
      refreshCollectionControls();
    }
    renderCompose();
  }
}

/* Native paths */

async function pickFolder(id) {
  const input = $(id);
  const view = { "default-folder": "folder", "download-folder": "download", "extract-folder": "extract" }[id];
  try {
    const location = await invoke("pick_path", { kind: "folder", initialDir: input.value.trim() || undefined });
    if (!location) return;
    input.value = location;
    if (id === "default-folder") await saveFolder(location);
  } catch (error) {
    showError(view, error);
  }
}

async function pickVideo() {
  notice("extract", "");
  try {
    const path = await invoke("pick_path", { kind: "video" });
    if (path) {
      state.localPath = path;
      renderLocal();
      $("change-video").focus();
    }
  } catch (error) {
    showError("extract", error);
  }
}

function renderLocal() {
  const chosen = Boolean(state.localPath);
  $("pick-video").hidden = chosen;
  $("file-card").hidden = !chosen;
  $("file-name").textContent = state.localPath.split(/[\\/]/).pop() || t("noVideo");
  $("file-path").textContent = state.localPath;
  $("file-path").title = state.localPath;
  $("extract-format-hint").textContent = t(`extractHint_${checkedValue("extract-format")}`);
  $("extract-button").disabled = !chosen || extractBusy || state.connection !== "ready";
  $("extract-button").textContent = t(extractBusy ? "preparing" : "startExtract");
}

async function extractAudio(event) {
  event.preventDefault();
  if (extractBusy || !state.localPath || state.connection !== "ready") return;
  extractBusy = true;
  notice("extract", "");
  renderLocal();
  try {
    const response = await api("/api/desktop/extract", {
      path: state.localPath,
      audio_format: checkedValue("extract-format"),
      download_dir: $("extract-folder").value.trim() || state.settings.download_dir || "",
    });
    await showNewBatch(response);
  } catch (error) {
    showError("extract", error);
  } finally {
    extractBusy = false;
    renderLocal();
  }
}

/* Settings */

async function changeSettings(update, { target = "settings", success } = {}) {
  if (settingsBusy || state.connection !== "ready") return false;
  settingsBusy = true;
  renderSettings();
  notice(target, "");
  try {
    applySettings(await update());
    if (success) toast(success, { dismissLabel: t("dismiss") });
    return true;
  } catch (error) {
    showError(target, error);
    return false;
  } finally {
    settingsBusy = false;
    renderSettings();
  }
}

function saveFolder(value) {
  const next = value.trim();
  if (next === (state.settings?.download_dir || "") || (!state.settings?.download_dir && next === state.settings?.default_download_dir)) {
    renderSettings();
    return Promise.resolve(true);
  }
  return changeSettings(() => api("/api/desktop/settings", { download_dir: next }), { target: "folder", success: t("folderSaved") });
}

function renderSettings() {
  const ready = state.connection === "ready" && !settingsBusy;
  const settings = state.settings;
  for (const input of select('input[name="language"], input[name="theme"]')) {
    input.disabled = !ready;
    // Keep the user's pending choice visible while it saves; resync once the response lands.
    if (!settingsBusy) input.checked = input.value === (input.name === "language" ? state.language : settings?.theme || "system");
  }
  const folder = settings ? settings.download_dir || settings.default_download_dir || "" : "";
  const input = $("default-folder");
  if (document.activeElement !== input || !ready) input.value = folder;
  input.disabled = !ready;
  for (const control of select("#folder-form button")) control.disabled = !ready;
  $("folder-default-tag").hidden = !settings || Boolean(settings.download_dir);
  $("reset-folder").hidden = !settings?.download_dir;
  $("app-version").textContent = state.version ? t("versionLabel", { version: state.version }) : "Generalized Transmedia Downloader";
  $("data-folder-row").hidden = !settings?.data_dir;
  $("data-folder").textContent = settings?.data_dir || "";
  $("open-data-folder").disabled = !settings?.data_dir;
  renderCookies();
}

function renderCookies() {
  const ready = state.connection === "ready" && !settingsBusy;
  const rows = platforms.map(id => {
    const platform = platformName(id, t);
    const installed = Boolean(state.settings?.cookies?.[id]);
    const row = element("li", "cookie-row");
    row.dataset.platform = id;
    row.dataset.installed = String(installed);
    const mark = element("span", "cookie-mark", platformMarks[id]);
    mark.setAttribute("aria-hidden", "true");
    const copy = element("div", "cookie-copy");
    const status = element("span", "cookie-status");
    status.append(icon(installed ? "check-circle" : "key"), element("span", "", t(installed ? "cookieImported" : "cookieMissing")));
    copy.append(element("strong", "", platform), status);
    const actions = element("div", "cookie-actions");
    const importButton = button(t(installed ? "replace" : "import"), async () => {
      try {
        const path = await invoke("pick_path", { kind: "cookie" });
        if (path) await updateCookie(id, path);
      } catch (error) {
        state.cookieErrors[id] = error;
        renderCookies();
      }
    }, "secondary compact");
    importButton.setAttribute("aria-label", t(installed ? "replaceCookies" : "importCookies", { platform }));
    importButton.disabled = !ready;
    actions.append(importButton);
    if (installed) {
      const confirming = state.confirmRemove === id;
      const remove = button(t(confirming ? "confirmRemove" : "remove"), () => {
        if (state.confirmRemove !== id) {
          state.confirmRemove = id;
          clearTimeout(confirmTimer);
          confirmTimer = setTimeout(() => {
            state.confirmRemove = "";
            renderCookies();
          }, 4000);
          renderCookies();
          document.querySelector(`.cookie-row[data-platform="${id}"] .cookie-actions .confirm`)?.focus();
          return;
        }
        state.confirmRemove = "";
        clearTimeout(confirmTimer);
        updateCookie(id, null);
      }, `${confirming ? "secondary confirm" : "ghost"} compact`);
      remove.setAttribute("aria-label", t(confirming ? "confirmRemoveCookies" : "removeCookies", { platform }));
      remove.disabled = !ready;
      actions.append(remove);
    }
    row.append(mark, copy, actions);
    if (state.cookieErrors[id]) {
      row.append(element("div", "callout"));
      fillCallout(row.lastElementChild, { tone: "error", codeLabel: t("errorCode"), ...errorParts(state.cookieErrors[id], state.language) });
    }
    return row;
  });
  const focused = $("cookie-list").contains(document.activeElement)
    ? [document.activeElement.closest(".cookie-row")?.dataset.platform, document.activeElement.getAttribute("aria-label")] : null;
  $("cookie-list").replaceChildren(...rows);
  if (focused) {
    const [platform, label] = focused;
    const row = $("cookie-list").querySelector(`.cookie-row[data-platform="${platform}"]`);
    ([...row?.querySelectorAll("button") || []].find(node => node.getAttribute("aria-label") === label)
      || row?.querySelector("button"))?.focus({ preventScroll: true });
  }
}

async function updateCookie(platform, path) {
  delete state.cookieErrors[platform];
  state.confirmRemove = "";
  clearTimeout(confirmTimer);
  const name = platformName(platform, t);
  let failure = null;
  const saved = await changeSettings(async () => {
    try {
      await api("/api/desktop/cookies", { platform, path });
      return await api("/api/desktop/settings");
    } catch (error) {
      failure = error;
      throw error;
    }
  }, { target: "settings", success: t(path ? "cookiesImported" : "cookiesRemoved", { platform: name }) });
  if (!saved && failure) {
    notice("settings", "");
    state.cookieErrors[platform] = failure;
    renderCookies();
  }
}

/* Queue and history */

function combinedTasks(batchIds) {
  const created = new Map(state.batches.map(batch => [batch.id, batch.created_at]));
  return batchIds.flatMap(batchId => (state.snapshots.get(batchId)?.tasks || [])
    .map(task => ({ ...task, batch_id: batchId, batch_created: created.get(batchId) || 0 })));
}

function queueIds() {
  const ids = new Set(state.session);
  for (const batch of state.batches) {
    if (batch.active || batch.queued) ids.add(batch.id);
  }
  const ordered = state.batches.filter(batch => ids.has(batch.id)).map(batch => batch.id);
  return [...new Set([...ordered, ...ids])];
}

function queueTasks() {
  return combinedTasks(queueIds()).filter(task => {
    const key = taskKey(task);
    if (!state.dismissed.has(key)) return true;
    if (isActive(task) || task.status === "queued") {
      state.dismissed.delete(key);
      return true;
    }
    return false;
  });
}

function updateSummaries() {
  const batches = state.batches.filter(batch => state.session.has(batch.id) || batch.active || batch.queued);
  const active = batches.reduce((sum, batch) => sum + (batch.active || 0), 0);
  const queued = batches.reduce((sum, batch) => sum + (batch.queued || 0), 0);
  $("activity-count").textContent = t("activitySummary", { active, queued });
  $("nav-count").textContent = active + queued;
  $("nav-count").hidden = !active && !queued;
}

const activityRows = new Map();

function renderActivity() {
  const tasks = queueOrder(queueTasks().filter(task => isActive(task) || task.status === "queued")).slice(0, 6);
  const nodes = [];
  const keys = new Set();
  for (const task of tasks) {
    const key = taskKey(task);
    keys.add(key);
    let view = activityRows.get(key);
    if (!view) {
      const row = element("li", "activity-row");
      const control = element("button", "activity-button");
      control.type = "button";
      const mark = icon("clock");
      const title = element("span", "activity-title");
      const meta = element("span", "activity-meta");
      const meter = element("span", "meter");
      const fill = element("span", "meter-fill");
      meter.append(fill);
      control.append(mark, title, meta, meter);
      control.addEventListener("click", () => openPage("queue", { expand: key }));
      row.append(control);
      view = { row, mark, title, meta, meter, fill, percent: null };
      activityRows.set(key, view);
    }
    const status = statusInfo(task, t);
    const percent = isActive(task) && !task.postprocessing ? percentOf(task) : null;
    view.row.dataset.tone = status.tone;
    view.mark.firstElementChild.setAttribute("href", `#i-${status.icon}`);
    view.mark.classList.toggle("spinning", status.icon === "spinner");
    setText(view.title, taskName(task, ctx));
    setText(view.meta, percent == null ? status.text : `${status.text} ${task.progress.percent_text.trim()}`);
    setHidden(view.meter, percent == null);
    if (percent != null) {
      view.fill.dataset.instant = String(view.percent == null || percent < view.percent);
      view.fill.style.transform = `scaleX(${percent / 100})`;
    }
    view.percent = percent;
    nodes.push(view.row);
  }
  for (const key of [...activityRows.keys()]) if (!keys.has(key)) activityRows.delete(key);
  if (!nodes.length) {
    if (renderActivity.emptyLanguage !== state.language || !renderActivity.empty) {
      renderActivity.empty = element("li", "activity-empty");
      renderActivity.empty.append(emptyState({ iconName: "queue", title: t("queueEmpty"), hint: t("activityEmptyHint") }));
      renderActivity.emptyLanguage = state.language;
    }
    nodes.push(renderActivity.empty);
  }
  reconcile($("activity-list"), nodes);
}

function viewHandlers(view) {
  const display = state[view];
  return {
    onSelect: (tasks, checked) => {
      for (const task of tasks) {
        if (checked) display.selected.add(taskKey(task));
        else display.selected.delete(taskKey(task));
      }
      renderResults();
    },
    onFilter: filter => {
      display.filter = filter;
      display.selected.clear();
      renderResults({ animate: false });
    },
    onExpand: key => {
      display.expanded = display.expanded === key ? "" : key;
      renderResults();
    },
    onAction: (action, tasks) => operate(action, tasks, view),
    onReveal: path => reveal(path, view),
    onOpenLink: url => openLink(url, view),
    onCopy: (text, kind) => copy(text, kind),
    onFix: (kind, task) => fix(kind, task),
    onClearFinished: () => clearFinished(),
  };
}

const queueList = new TaskList($("queue-list"), viewHandlers("queue"));
const historyList = new TaskList($("history-list"), viewHandlers("history"));
const emptyNodes = new Map();

function cachedEmpty(name, build) {
  const key = `${name}:${state.language}`;
  if (!emptyNodes.has(key)) emptyNodes.set(key, build());
  return emptyNodes.get(key);
}

function queueEmpty() {
  return cachedEmpty("queue", () => emptyState({
    iconName: "queue", title: t("queueEmpty"), hint: t("queueEmptyHint"),
    actions: [
      button(t("newDownload"), () => openPage("download"), "primary compact", "download"),
      button(t("extract"), () => openPage("extract"), "secondary compact", "extract"),
    ],
  }));
}

function renderResults({ animate = true } = {}) {
  if (state.page === "queue") {
    const tasks = queueTasks();
    const finished = tasks.filter(task => task.status === "completed" || task.status === "cancelled").length;
    queueList.render({
      tasks, ctx, view: "queue", filter: state.queue.filter, selected: state.queue.selected,
      expanded: state.queue.expanded, busy: queueBusy, grouped: true, clearable: finished, animate, empty: queueEmpty,
    });
  } else if (state.page === "history") {
    renderHistory(animate);
  }
}

function clearFinished() {
  let count = 0;
  for (const task of queueTasks()) {
    if (task.status === "completed" || task.status === "cancelled") {
      state.dismissed.add(taskKey(task));
      state.queue.selected.delete(taskKey(task));
      count += 1;
    }
  }
  if (state.queue.expanded && state.dismissed.has(state.queue.expanded)) state.queue.expanded = "";
  state.queue.filter = "all";
  renderResults();
  toast(t("finishedCleared", { count }), { dismissLabel: t("dismiss") });
}

function batchKind(batch) {
  if (state.index.get(batch.id)?.local) return "local";
  return batch.media_type === "audio" ? "audio" : "video";
}

function batchName(batch) {
  const entry = state.index.get(batch.id);
  const title = entry?.titles[0];
  if (!title) return [t(`batchKind_${batchKind(batch)}`), t("batchItems", { count: batch.total })].join(" · ");
  return batch.total > 1 ? t("batchMore", { title, count: batch.total - 1, total: batch.total }) : title;
}

function batchFormat(batch) {
  const kind = t(`batchKind_${batchKind(batch)}`);
  return batch.media_type === "audio" && batch.audio_format ? `${kind} · ${t(`formatLabel_${batch.audio_format}`)}` : kind;
}

function statusBar(batch) {
  const bar = element("span", "status-bar");
  for (const part of ["completed", "active", "failed", "cancelled"]) {
    const value = batch[part] || 0;
    if (!value || !batch.total) continue;
    const segment = element("span");
    segment.dataset.part = part;
    segment.style.width = `${(value / batch.total) * 100}%`;
    bar.append(segment);
  }
  return bar;
}

const batchViews = new Map();
const dayViews = new Map();

function renderBatchList() {
  const query = state.historyQuery.trim().toLocaleLowerCase();
  const matches = state.batches.filter(batch => {
    if (!query) return true;
    const entry = state.index.get(batch.id);
    const haystack = [entry?.search || "", batchFormat(batch), formatDateTime(batch.created_at, state.language)].join(" ").toLocaleLowerCase();
    return haystack.includes(query);
  });
  const nodes = [];
  let day = "";
  for (const batch of matches) {
    const key = dayKey(batch.created_at);
    if (key !== day) {
      day = key;
      let header = dayViews.get(key);
      if (!header) {
        header = element("p", "batch-day");
        dayViews.set(key, header);
      }
      setText(header, dayLabel(batch.created_at, state.language, t));
      nodes.push(header);
    }
    let view = batchViews.get(batch.id);
    if (!view) {
      const item = element("button", "batch-item");
      item.type = "button";
      item.addEventListener("click", () => selectBatch(batch.id));
      const kind = element("span", "batch-kind");
      kind.append(icon("video"));
      const name = element("span", "batch-name");
      const sub = element("span", "batch-sub");
      view = { item, kind, name, sub, key: "" };
      item.append(kind, name, sub);
      batchViews.set(batch.id, view);
    }
    const renderKey = JSON.stringify([state.language, batch, state.index.get(batch.id)?.titles?.[0], state.currentBatch === batch.id]);
    if (renderKey !== view.key) {
      view.key = renderKey;
      const kind = batchKind(batch);
      view.kind.firstElementChild.firstElementChild.setAttribute("href", `#i-${{ local: "extract", audio: "audio", video: "video" }[kind]}`);
      const name = batchName(batch);
      setText(view.name, name);
      view.item.title = name;
      const sub = [formatClock(batch.created_at, state.language), t("batchItems", { count: batch.total })];
      view.sub.replaceChildren(element("span", "", sub.join(" · ")));
      if (batch.failed) view.sub.append(element("span", "batch-failed", ` · ${t("batchFailed", { count: batch.failed })}`));
      else if (batch.active || batch.queued) view.sub.append(element("span", "", ` · ${t("batchActive", { count: (batch.active || 0) + (batch.queued || 0) })}`));
      view.sub.dataset.failed = String(Boolean(batch.failed));
      view.item.querySelector(".status-bar")?.remove();
      view.item.append(statusBar(batch));
      view.item.setAttribute("aria-current", String(state.currentBatch === batch.id));
    }
    nodes.push(view.item);
  }
  for (const id of [...batchViews.keys()]) if (!state.batches.some(batch => batch.id === id)) batchViews.delete(id);
  if (!nodes.length) {
    renderBatchList.empty ||= element("p", "batch-empty");
    renderBatchList.empty.textContent = t("noHistoryMatches", { query: state.historyQuery.trim() });
    nodes.push(renderBatchList.empty);
  }
  reconcile($("batch-list"), nodes);
}

function renderBatchHeader(batch) {
  const header = $("batch-header");
  const snapshot = state.snapshots.get(batch.id);
  const retryable = (snapshot?.tasks || []).filter(task => task.status === "failed" && task.can_retry)
    .map(task => ({ ...task, batch_id: batch.id }));
  const key = JSON.stringify([state.language, batch, state.index.get(batch.id)?.titles?.[0], retryable.length, queueBusy]);
  if (header.dataset.key === key) return;
  header.dataset.key = key;
  const focused = header.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
  const heading = element("div", "batch-heading");
  const title = element("h2", "", batchName(batch));
  title.id = "batch-title";
  const facts = element("p", "batch-facts");
  facts.append(
    element("span", "", formatDateTime(batch.created_at, state.language)),
    element("span", "", batchFormat(batch)),
    element("span", "", t("batchProgress", { completed: batch.completed || 0, total: batch.total })),
  );
  if (batch.failed) facts.append(element("span", "failed", t("batchFailed", { count: batch.failed })));
  if (batch.active || batch.queued) facts.append(element("span", "", t("batchActive", { count: (batch.active || 0) + (batch.queued || 0) })));
  heading.append(title, facts);
  const toolbar = element("div", "batch-toolbar");
  if (batch.download_dir) {
    const folder = element("p", "batch-folder");
    const path = element("code", "path", batch.download_dir);
    path.title = batch.download_dir;
    folder.append(icon("folder"), element("span", "", t("savedTo")), path);
    toolbar.append(folder);
  }
  const actions = element("div", "batch-actions");
  if (batch.download_dir) {
    const show = button(t("showFolder"), () => reveal(batch.download_dir, "history"), "secondary compact", "folder");
    show.dataset.focusKey = "show-folder";
    actions.append(show);
  }
  if (retryable.length) {
    const retry = button(t("retryFailed", { count: retryable.length }), () => operate("retry", retryable, "history"), "primary compact", "retry");
    retry.disabled = queueBusy;
    retry.dataset.focusKey = "retry-failed";
    actions.append(retry);
  }
  if (actions.childElementCount) toolbar.append(actions);
  header.replaceChildren(heading, ...(toolbar.childElementCount ? [toolbar] : []));
  if (focused) header.querySelector(`[data-focus-key="${focused}"]`)?.focus({ preventScroll: true });
}

function renderHistory(animate = true) {
  const hasBatches = state.batches.length > 0;
  $("history-layout").hidden = !hasBatches;
  $("history-empty").hidden = hasBatches;
  if (!hasBatches) {
    const node = cachedEmpty("history", () => emptyState({
      iconName: "history", title: t("historyEmpty"), hint: t("historyEmptyHint"),
      actions: [button(t("newDownload"), () => openPage("download"), "primary compact", "download")],
    }));
    if ($("history-empty").firstElementChild !== node) $("history-empty").replaceChildren(node);
    return;
  }
  renderBatchList();
  const batch = state.batches.find(item => item.id === state.currentBatch);
  if (!batch) return;
  renderBatchHeader(batch);
  const loading = !state.snapshots.has(batch.id);
  historyList.render({
    tasks: combinedTasks([batch.id]), ctx, view: "history", filter: state.history.filter, selected: state.history.selected,
    expanded: state.history.expanded, busy: queueBusy, grouped: false, clearable: 0, animate,
    empty: () => cachedEmpty(loading ? "loading" : "no-tasks", () => {
      const node = element("div", "empty-state compact");
      node.append(element("p", "", t(loading ? "batchLoading" : "noBatches")));
      return node;
    }),
  });
}

function selectBatch(id) {
  if (state.currentBatch === id) return;
  state.currentBatch = id;
  state.history.selected.clear();
  state.history.expanded = "";
  state.history.filter = "all";
  renderResults({ animate: false });
  loadBatch(id);
}

// Fetch a batch right away instead of waiting for the next poll tick.
async function loadBatch(id) {
  if (!id || state.snapshots.has(id) || state.connection !== "ready") return;
  try {
    const snapshot = await api(`/api/batch/${encodeURIComponent(id)}`);
    if (state.batches.some(batch => batch.id === id)) state.snapshots.set(id, snapshot);
  } catch (error) {
    showError("history", error);
  }
  renderResults();
}

// Batch titles make history searchable; finished batches never change, so fetch each once.
async function buildIndex() {
  if (indexing || state.connection !== "ready") return indexing;
  const pending = state.batches.filter(batch => {
    const entry = state.index.get(batch.id);
    return !entry || (!entry.done && batch.all_done);
  });
  if (!pending.length) return null;
  indexing = (async () => {
    const queue = [...pending];
    await Promise.all(Array.from({ length: Math.min(4, queue.length) }, async () => {
      while (queue.length) {
        const batch = queue.shift();
        try {
          const snapshot = state.snapshots.get(batch.id)?.all_done ? state.snapshots.get(batch.id) : await api(`/api/batch/${encodeURIComponent(batch.id)}`);
          const titles = snapshot.tasks.map(task => task.result?.title || task.title || task.url || "").filter(Boolean);
          state.index.set(batch.id, {
            titles, search: titles.join("\n"), done: Boolean(snapshot.all_done),
            local: snapshot.tasks.some(task => task.platform === "local"),
          });
        } catch {
          // A pruned batch disappears from the next list poll.
        }
      }
    }));
  })().finally(() => {
    indexing = null;
    if (state.page === "history") renderResults();
  });
  return indexing;
}

async function pollQueue() {
  const payload = await api("/api/batches");
  state.batches = payload.batches;
  const present = new Set(state.batches.map(batch => batch.id));
  for (const id of state.snapshots.keys()) if (!present.has(id)) state.snapshots.delete(id);
  for (const id of state.index.keys()) if (!present.has(id)) state.index.delete(id);
  for (const id of state.session) if (!present.has(id)) state.session.delete(id);
  if (!present.has(state.currentBatch)) {
    state.currentBatch = state.batches[0]?.id || "";
    state.history.selected.clear();
    state.history.expanded = "";
  }
  const wanted = new Set(queueIds());
  if (state.page === "history" && state.currentBatch) wanted.add(state.currentBatch);
  const summaries = new Map(state.batches.map(batch => [batch.id, batch]));
  await Promise.all([...wanted].map(async id => {
    const summary = summaries.get(id);
    const saved = state.snapshots.get(id);
    if (summary?.all_done && saved?.all_done) return;
    const batch = await api(`/api/batch/${encodeURIComponent(id)}`);
    state.snapshots.set(id, batch);
  }));
  updateSummaries();
  if (state.page === "download") renderActivity();
  if (state.page === "history") buildIndex();
  renderResults();
}

function refreshQueue() {
  if (state.connection !== "ready") return Promise.resolve();
  if (poll) return poll;
  clearTimeout(pollTimer);
  poll = pollQueue().then(() => {
    notice("workspace", "");
  }).catch(() => {
    notice("workspace", { message: t("connectionLost") }, "warning");
  }).finally(() => {
    poll = null;
    pollTimer = setTimeout(refreshQueue, state.batches.some(batch => batch.active || batch.queued) ? 1000 : 4000);
  });
  return poll;
}

async function showNewBatch(response) {
  // Let in-flight reads settle before invalidating the list after a mutation.
  await poll;
  state.session.add(response.batch_id);
  state.queue.filter = "all";
  openPage("queue");
  toast(t("added", { count: response.task_count }), { dismissLabel: t("dismiss") });
  await refreshQueue();
}

async function operate(action, items, view) {
  if (queueBusy || !items.length) return;
  queueBusy = true;
  renderResults();
  notice(view, "");
  let succeeded = 0;
  const errors = [];
  try {
    // Bound each request so a large selection can report partial completion.
    for (let start = 0; start < items.length; start += maxSelected) {
      const tasks = items.slice(start, start + maxSelected).map(task => ({ batch_id: task.batch_id, task_id: task.id }));
      const response = await api("/api/desktop/batch-action", { action, tasks });
      succeeded += response.succeeded;
      errors.push(...response.errors);
      for (const task of tasks) {
        if (!response.errors.some(error => error.task_id === task.task_id && error.batch_id === task.batch_id)) {
          state[view].selected.delete(`${task.batch_id}/${task.task_id}`);
          state.session.add(task.batch_id);
        }
      }
    }
    if (errors.length) {
      notice(view, {
        message: t("operationPartial", { count: succeeded, failed: errors.length }),
        suggestion: errors.slice(0, 3).map(error => formatError(error, state.language)).join("\n"),
      });
    } else {
      toast(t("operationFinished", { count: succeeded }), { dismissLabel: t("dismiss") });
    }
  } catch (error) {
    showError(view, error);
  } finally {
    await poll;
    for (const task of items) state.snapshots.delete(task.batch_id);
    queueBusy = false;
    await refreshQueue();
  }
}

async function reveal(path, view) {
  if (!path) return;
  try {
    await invoke("reveal_path", { path });
  } catch (error) {
    if (view === "toast") toast(formatError(error, state.language), { tone: "error", dismissLabel: t("dismiss") });
    else showError(view, error);
  }
}

async function openLink(url, view) {
  try {
    await invoke("open_link", { url });
  } catch (error) {
    showError(view, error);
  }
}

async function copy(text, kind) {
  const copied = await copyText(text);
  toast(t(copied ? (kind === "path" ? "pathCopied" : "linkCopied") : "copyFailed"), {
    tone: copied ? "ok" : "error", duration: 2600, dismissLabel: t("dismiss"),
  });
}

function fix(kind, task) {
  openPage("settings");
  const target = kind === "cookies"
    ? document.querySelector(`.cookie-row[data-platform="${task.platform}"]`)
    : $("folder-form");
  if (!target) return;
  target.scrollIntoView({ block: "center" });
  flash(target);
  (kind === "cookies" ? target.querySelector("button") : $("default-folder"))?.focus({ preventScroll: true });
}

/* Wiring */

for (const control of select("[data-page]")) control.addEventListener("click", () => openPage(control.dataset.page));
for (const control of select("[data-pick-folder]")) control.addEventListener("click", () => pickFolder(control.dataset.pickFolder));
$("download-form").addEventListener("submit", startPreview);
$("download-form").addEventListener("change", renderCompose);
$("download-links").addEventListener("input", () => {
  renderCompose();
  notice("download", readLinks().length > maxLinks ? t("linkLimit") : "");
});
$("download-links").addEventListener("keydown", event => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    if (!$("preview-button").disabled) $("download-form").requestSubmit();
  }
});
$("clear-links").addEventListener("click", () => {
  $("download-links").value = "";
  notice("download", "");
  renderCompose();
  $("download-links").focus();
});
$("collection-select-all").addEventListener("change", event => {
  if (!preview || preview.busy) return;
  const available = visibleEntries().filter(entry => entry.selectable);
  if (event.target.checked) {
    for (const entry of available) {
      if (preview.selected.size >= maxSelected) break;
      preview.selected.add(entry.id);
    }
  } else {
    for (const entry of available) preview.selected.delete(entry.id);
  }
  refreshCollectionControls();
});
$("collection-search").addEventListener("input", event => {
  if (!preview) return;
  preview.query = event.target.value;
  preview.last = "";
  refreshCollectionControls();
});
$("collection-search").addEventListener("keydown", event => {
  // First Escape clears the filter; the next one closes the dialog. Search fields consume
  // Escape themselves (even when empty), so the dialog would never see it otherwise.
  if (event.key !== "Escape" || !preview) return;
  event.preventDefault();
  event.stopPropagation();
  if (!event.target.value) {
    closePreview();
    return;
  }
  event.target.value = "";
  preview.query = "";
  refreshCollectionControls();
});
$("collection").addEventListener("cancel", event => {
  event.preventDefault();
  if (event.target === $("collection")) closePreview();
});
$("collection").addEventListener("keydown", event => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !$("submit-collection").disabled) {
    event.preventDefault();
    addSelected();
  }
});
$("close-collection").addEventListener("click", closePreview);
$("back-collection").addEventListener("click", closePreview);
$("submit-collection").addEventListener("click", addSelected);
$("pick-video").addEventListener("click", pickVideo);
$("change-video").addEventListener("click", pickVideo);
$("clear-video").addEventListener("click", () => {
  state.localPath = "";
  renderLocal();
  $("pick-video").focus();
});
$("extract-form").addEventListener("change", renderLocal);
$("extract-form").addEventListener("submit", extractAudio);
for (const input of select('input[name="language"]')) {
  input.addEventListener("change", () => changeSettings(() => api("/api/desktop/settings", { language: input.value })));
}
for (const input of select('input[name="theme"]')) {
  input.addEventListener("change", () => changeSettings(() => api("/api/desktop/settings", { theme: input.value })));
}
$("folder-form").addEventListener("submit", event => {
  event.preventDefault();
  saveFolder($("default-folder").value);
});
$("default-folder").addEventListener("change", () => saveFolder($("default-folder").value));
$("reset-folder").addEventListener("click", () => {
  changeSettings(() => api("/api/desktop/settings", { download_dir: "" }), { target: "folder", success: t("folderSaved") });
});
$("open-default-folder").addEventListener("click", () => reveal($("default-folder").value.trim(), "folder"));
$("open-data-folder").addEventListener("click", () => reveal(state.settings?.data_dir, "settings"));
$("history-search").addEventListener("input", event => {
  state.historyQuery = event.target.value;
  renderBatchList();
});
$("reconnect").addEventListener("click", boot);
// Keep the WebView's browser menu (Reload, Save as…) out of the app; text fields and
// selected text still get the native Cut/Copy/Paste menu.
document.addEventListener("contextmenu", event => {
  if (event.target.closest?.("input, textarea") || String(window.getSelection())) return;
  event.preventDefault();
});
document.addEventListener("keydown", event => {
  const modifier = isMac ? event.metaKey : event.ctrlKey;
  if (!modifier || event.shiftKey || event.altKey || !/^[1-5]$/.test(event.key) || $("collection").open) return;
  event.preventDefault();
  openPage(pages[Number(event.key) - 1]);
});

document.documentElement.dataset.platform = /Windows/.test(navigator.userAgent) ? "windows" : isMac ? "mac" : "other";
void window.__TAURI__?.app?.getVersion?.().then(version => {
  state.version = version;
  renderSettings();
}).catch(() => {});
localize();
boot();
