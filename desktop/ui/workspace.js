import { formatError, translate } from "./strings.js";
import {
  button, element, empty, formatTime, isActive, platformName,
  renderInspector, renderTable, statusText, taskKey, taskName,
} from "./tasks.js";

const $ = id => document.getElementById(id);
const select = selector => document.querySelectorAll(selector);
const platforms = ["youtube", "instagram", "bilibili"];
const maxLinks = 20;
const maxSelected = 100;
const pages = ["download", "queue", "history", "extract", "settings"];
const state = {
  page: "download",
  connection: "starting",
  language: "en",
  settings: null,
  capabilities: null,
  batches: [],
  snapshots: new Map(),
  session: new Set(),
  currentBatch: "",
  localPath: "",
  queue: { selected: new Set(), filter: "all", focused: "" },
  history: { selected: new Set(), filter: "all", focused: "" },
};
const tableRenderKeys = new Map();
let preview = null;
let downloadBusy = false;
let extractBusy = false;
let settingsBusy = false;
let queueBusy = false;
let poll = null;
let pollTimer = null;

const t = (key, values) => translate(key, state.language, values);

function invoke(command, args) {
  if (!window.__TAURI__?.core?.invoke) {
    return Promise.reject(new Error("Open this workspace in GTD Desktop."));
  }
  return window.__TAURI__.core.invoke(command, args);
}

function api(path, body) {
  return invoke("api", body === undefined ? { path } : { path, body });
}

function notice(id, message, tone = "error") {
  const target = $(`${id}-notice`);
  target.textContent = message || "";
  target.hidden = !message;
  target.dataset.tone = tone;
}

function showError(id, error) {
  notice(id, formatError(error, state.language));
}

function localize() {
  document.documentElement.lang = state.language === "zh" ? "zh-CN" : "en";
  document.documentElement.dataset.theme = state.settings?.theme || "system";
  for (const node of select("[data-copy]")) node.textContent = t(node.dataset.copy);
  for (const node of select("[data-label]")) node.setAttribute("aria-label", t(node.dataset.label));
  for (const node of select("[data-placeholder]")) node.placeholder = t(node.dataset.placeholder);
  $("app-heading").textContent = t(state.page);
  renderConnection();
  renderCompose();
  renderLocal();
  renderCookies();
  updateSummaries();
  renderActivity();
  if (preview) renderCollection();
  renderResults(true);
}

function openPage(page, focus = true) {
  if (!pages.includes(page)) return;
  state.page = page;
  for (const key of pages) $(`view-${key}`).hidden = key !== page;
  for (const control of select("nav [data-page]")) {
    if (control.dataset.page === page) control.setAttribute("aria-current", "page");
    else control.removeAttribute("aria-current");
  }
  const heading = $("app-heading");
  heading.textContent = t(page);
  if (focus) {
    window.scrollTo(0, 0);
    heading.focus({ preventScroll: true });
  }
  if (page === "download") renderActivity();
  renderResults();
  if (page === "history") refreshQueue();
}

function renderConnection() {
  $("connection-text").textContent = t(state.connection);
  $("connection-dot").dataset.connection = state.connection;
  $("reconnect").hidden = state.connection !== "unavailable";
}

function applySettings(settings) {
  const previous = state.settings?.download_dir || state.settings?.default_download_dir || "";
  state.settings = settings;
  state.language = settings.language === "zh" ? "zh" : "en";
  $("language").value = state.language;
  $("theme").value = state.settings.theme || "system";
  const folder = state.settings.download_dir || state.settings.default_download_dir || "";
  $("default-folder").value = folder;
  for (const id of ["download-folder", "extract-folder"]) {
    const input = $(id);
    input.placeholder = folder;
    if (!input.value || input.value === previous) input.value = folder;
  }
  localize();
}

async function boot() {
  clearTimeout(pollTimer);
  state.connection = "starting";
  renderConnection();
  renderCompose();
  renderLocal();
  notice("workspace", "");
  try {
    const [settings, capabilities] = await Promise.all([
      api("/api/desktop/settings"),
      api("/api/capabilities"),
    ]);
    state.capabilities = capabilities;
    state.connection = "ready";
    applySettings(settings);
    void invoke("renderer_ready", {}).catch(() => {});
    await refreshQueue();
  } catch (error) {
    state.connection = "unavailable";
    renderConnection();
    renderCompose();
    renderLocal();
    showError("workspace", error);
  }
}

function readLinks() {
  return $("download-links").value.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
}

function renderCompose() {
  const media = new FormData($("download-form")).get("media");
  $("video-options").hidden = media !== "video";
  $("audio-options").hidden = media !== "audio";
  $("automatic").disabled = !$("subtitles").checked;
  if ($("automatic").disabled) $("automatic").checked = false;
  const count = readLinks().length;
  $("link-count").textContent = `${count} / ${maxLinks}`;
  $("link-count").dataset.invalid = count > maxLinks;
  $("turbo").disabled = !state.capabilities?.aria2c_available;
  $("turbo-hint").textContent = t(!state.capabilities ? "turboChecking" :
    state.capabilities.aria2c_available ? "turboReady" : "turboMissing");
  $("preview-button").disabled = downloadBusy || state.connection !== "ready" || count > maxLinks;
  $("preview-button").textContent = t(downloadBusy ? "previewBusy" : "previewLinks");
}

function collectDownloadOptions() {
  const media = new FormData($("download-form")).get("media");
  const options = {
    media_type: media,
    audio_format: media === "audio" ? $("download-format").value : "mp3",
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
      preview = { result, options, selected, source, busy: false };
      renderCollection();
      $("collection").showModal();
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
    $("collection").close();
  }
  if ($("download-links").value === selection.source) $("download-links").value = "";
  notice("download", "");
  await showNewBatch(response);
}

function refreshCollectionControls() {
  const availableCount = Math.min(maxSelected, preview.result.entries.filter(entry => entry.selectable).length);
  const size = preview.selected.size;
  $("collection-count").textContent = t("collectionCount", { count: size });
  $("collection-select-all").checked = availableCount > 0 && size === availableCount;
  $("collection-select-all").indeterminate = size > 0 && size < availableCount;
  $("collection-select-all").disabled = preview.busy || !availableCount;
  $("submit-collection").disabled = preview.busy || !size;
  $("submit-collection").textContent = t(preview.busy ? "adding" : "submitSelected");
  $("close-collection").disabled = preview.busy;
  $("back-collection").disabled = preview.busy;
  for (const checkbox of $("collection-list").querySelectorAll("input")) {
    checkbox.checked = preview.selected.has(checkbox.value);
    checkbox.disabled = preview.busy || checkbox.dataset.available !== "true" ||
      (!checkbox.checked && size >= maxSelected);
  }
}

function renderCollection() {
  $("collection-title").textContent = !preview.result.title_is_generated && preview.result.title || "";
  $("collection-title").hidden = !$("collection-title").textContent;
  $("collection-truncated").hidden = !preview.result.truncated;
  const list = document.createDocumentFragment();
  for (const entry of preview.result.entries) {
    const label = element("label", "collection-entry");
    const checkbox = element("input");
    checkbox.type = "checkbox";
    checkbox.value = entry.id;
    checkbox.dataset.available = String(entry.selectable === true);
    const name = entry.title_is_generated ? `${t("task")} ${entry.position}` : entry.title || t("unknown");
    checkbox.setAttribute("aria-label", name);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) preview.selected.add(entry.id);
      else preview.selected.delete(entry.id);
      refreshCollectionControls();
    });
    const copy = element("span", "entry-copy");
    const reason = entry.selectable ? "" : entry.unavailable_reason === "内容不可访问" && state.language === "en"
      ? "Content is inaccessible" : entry.unavailable_reason === "源站未提供可下载链接" && state.language === "en"
        ? "The source has no downloadable link" : entry.unavailable_reason || t("notSelectable");
    copy.append(element("strong", "", name), element("small", "muted", [
      platformName(entry.platform, t), reason,
    ].filter(Boolean).join(" · ")));
    label.append(checkbox, copy);
    list.append(label);
  }
  $("collection-list").replaceChildren(list);
  refreshCollectionControls();
}

function closePreview() {
  if (!preview || preview.busy) return;
  preview = null;
  $("collection").close();
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

async function pickFolder(id) {
  const input = $(id);
  const view = { "default-folder": "settings", "download-folder": "download", "extract-folder": "extract" }[id];
  try {
    const location = await invoke("pick_path", { kind: "folder", initialDir: input.value.trim() || undefined });
    if (location) input.value = location;
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
    }
  } catch (error) {
    showError("extract", error);
  }
}

function renderLocal() {
  $("file-name").textContent = state.localPath.split(/[\\/]/).pop() || t("noVideo");
  $("file-path").textContent = state.localPath;
  $("file-path").hidden = !state.localPath;
  $("extract-button").disabled = !state.localPath || extractBusy || state.connection !== "ready";
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
      audio_format: $("extract-format").value,
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

async function changeSettings(update) {
  if (settingsBusy || state.connection !== "ready") return;
  settingsBusy = true;
  setSettingsDisabled(true);
  notice("settings", "");
  try {
    applySettings(await update());
    notice("settings", t("saved"), "ok");
  } catch (error) {
    $("language").value = state.language;
    $("theme").value = state.settings.theme;
    showError("settings", error);
  } finally {
    settingsBusy = false;
    setSettingsDisabled(false);
    renderCookies();
  }
}

function setSettingsDisabled(disabled) {
  for (const input of $("view-settings").querySelectorAll("button, input, select")) input.disabled = disabled;
}

function renderCookies() {
  const list = document.createDocumentFragment();
  for (const id of platforms) {
    const platform = platformName(id, t);
    const installed = Boolean(state.settings?.cookies?.[id]);
    const row = element("div", "cookie-row");
    const copy = element("div", "");
    copy.append(element("strong", "", platform), element("p", "muted small", t(installed ? "cookieImported" : "cookieMissing")));
    const actions = element("div", "inline-actions");
    const importButton = button(t(installed ? "replace" : "import"), async () => {
      try {
        const path = await invoke("pick_path", { kind: "cookie" });
        if (path) updateCookie(id, path);
      } catch (error) {
        showError("settings", error);
      }
    });
    importButton.setAttribute("aria-label", t(installed ? "replaceCookies" : "importCookies", { platform }));
    importButton.disabled = settingsBusy || state.connection !== "ready";
    actions.append(importButton);
    if (installed) {
      const remove = button(t("remove"), () => updateCookie(id, null));
      remove.setAttribute("aria-label", t("removeCookies", { platform }));
      remove.disabled = importButton.disabled;
      actions.append(remove);
    }
    row.append(copy, actions);
    list.append(row);
  }
  $("cookie-list").replaceChildren(list);
}

function updateCookie(platform, path) {
  return changeSettings(async () => {
    await api("/api/desktop/cookies", { platform, path });
    return api("/api/desktop/settings");
  });
}

function combinedTasks(batchIds) {
  return batchIds.flatMap(batchId => (state.snapshots.get(batchId)?.tasks || [])
    .map(task => ({ ...task, batch_id: batchId })));
}

function queueIds() {
  const ids = new Set(state.session);
  for (const batch of state.batches) {
    if (batch.active || batch.queued) ids.add(batch.id);
  }
  const ordered = state.batches.filter(batch => ids.has(batch.id)).map(batch => batch.id);
  return [...new Set([...ordered, ...ids])];
}

function updateSummaries() {
  const batches = state.batches.filter(batch => state.session.has(batch.id) || batch.active || batch.queued);
  for (const metric of ["active", "queued", "completed"]) {
    $(`queue-${metric}`).textContent = batches.reduce((sum, batch) => sum + (batch[metric] || 0), 0);
  }
  const active = Number($("queue-active").textContent);
  const queued = Number($("queue-queued").textContent);
  $("activity-count").textContent = t("activities", { active, queued });
  $("nav-count").textContent = active + queued;
  $("nav-count").hidden = !active && !queued;
}

function renderActivity() {
  const tasks = combinedTasks(queueIds()).filter(task => isActive(task) || task.status === "queued").slice(0, 6);
  const key = JSON.stringify([state.language, tasks.map(task => [taskKey(task), taskName(task, t), statusText(task, t)])]);
  if (key === tableRenderKeys.get("activity")) return;
  tableRenderKeys.set("activity", key);
  const fragment = document.createDocumentFragment();
  for (const task of tasks) {
    const row = element("div", "activity-row");
    const control = button(taskName(task, t), () => {
      state.queue.focused = taskKey(task);
      openPage("queue");
    }, "task-name");
    row.append(control, element("p", "muted small", statusText(task, t)));
    fragment.append(row);
  }
  if (!fragment.childElementCount) fragment.append(empty(t("queueEmpty"), t("queueEmptyHint")));
  $("activity-list").replaceChildren(fragment);
}

function renderHistory() {
  const target = $("history-batch");
  const fragment = document.createDocumentFragment();
  for (const batch of state.batches) {
    const label = [formatTime(batch.created_at, state.language), t(batch.media_type || "unknown"),
      t("taskCount", { count: batch.total })].join(" · ");
    const option = element("option", "", label);
    option.value = batch.id;
    fragment.append(option);
  }
  if (!state.batches.length) fragment.append(element("option", "", t("noBatches")));
  target.replaceChildren(fragment);
  target.disabled = !state.batches.length;
  target.value = state.currentBatch;
  const current = state.batches.find(batch => batch.id === state.currentBatch);
  $("history-summary").textContent = current ? t("batchSummary", {
    total: current.total, completed: current.completed || 0, failed: current.failed || 0,
  }) : "";
  $("history-output").hidden = !current?.download_dir;
}

function renderResults(force = false) {
  const page = state.page;
  if (page !== "queue" && page !== "history") return;
  const display = state[page];
  const tasks = combinedTasks(page === "queue" ? queueIds() : state.currentBatch ? [state.currentBatch] : []);
  if (page === "history") {
    const key = JSON.stringify([state.language, state.currentBatch, state.batches]);
    if (force || key !== tableRenderKeys.get("history-options")) {
      tableRenderKeys.set("history-options", key);
      renderHistory();
    }
  }
  const focused = tasks.find(task => taskKey(task) === display.focused);
  const options = {
    t, language: state.language, view: page, busy: queueBusy,
    hasBatch: Boolean(state.currentBatch), selected: display.selected, focused: display.focused, filter: display.filter,
    onReveal: path => reveal(path, page),
    onAction: (action, items) => operate(action, items, page),
    onSelect: (items, checked) => {
      for (const item of items) {
        if (checked) display.selected.add(taskKey(item));
        else display.selected.delete(taskKey(item));
      }
      renderResults();
    },
    onFilter: filter => {
      display.filter = filter;
      display.selected.clear();
      renderResults();
    },
    onFocus: key => {
      display.focused = display.focused === key ? "" : key;
      renderResults();
      if (display.focused && window.matchMedia("(max-width: 1050px)").matches) {
        $(`${page}-inspector`).scrollIntoView({ block: "nearest" });
      }
    },
  };
  const tableKey = JSON.stringify([state.language, tasks, display.focused, display.filter, [...display.selected], queueBusy]);
  const detailKey = JSON.stringify([state.language, focused, queueBusy]);
  if (force || tableKey !== tableRenderKeys.get(page)) {
    tableRenderKeys.set(page, tableKey);
    renderTable($(`${page}-table`), tasks, options);
  }
  if (force || detailKey !== tableRenderKeys.get(`${page}-inspector`)) {
    tableRenderKeys.set(`${page}-inspector`, detailKey);
    renderInspector($(`${page}-inspector`), focused, options);
  }
}

async function pollQueue() {
  const payload = await api("/api/batches");
  state.batches = payload.batches;
  const present = new Set(state.batches.map(batch => batch.id));
  for (const id of state.snapshots.keys()) if (!present.has(id)) state.snapshots.delete(id);
  for (const id of state.session) if (!present.has(id)) state.session.delete(id);
  if (!present.has(state.currentBatch)) {
    state.currentBatch = state.batches[0]?.id || "";
    state.history.selected.clear();
    state.history.focused = "";
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
  renderResults();
}

function refreshQueue() {
  if (state.connection !== "ready") return Promise.resolve();
  if (poll) return poll;
  clearTimeout(pollTimer);
  poll = pollQueue().then(() => {
    if ($("workspace-notice").dataset.tone === "poll-error") notice("workspace", "");
  }).catch(error => {
    notice("workspace", formatError(error, state.language), "poll-error");
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
  openPage("queue");
  notice("queue", t("added", { count: response.task_count }), "ok");
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
    const text = errors.length ? [
      t("operationPartial", { count: succeeded, failed: errors.length }),
      ...errors.slice(0, 3).map(error => formatError(error, state.language)),
    ].join("\n") : t("operationFinished", { count: succeeded });
    notice(view, text, errors.length ? "error" : "ok");
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
    showError(view, error);
  }
}

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
  preview.selected.clear();
  if (event.target.checked) {
    for (const entry of preview.result.entries.filter(item => item.selectable).slice(0, maxSelected)) {
      preview.selected.add(entry.id);
    }
  }
  refreshCollectionControls();
});
$("collection").addEventListener("cancel", event => {
  event.preventDefault();
  closePreview();
});
$("close-collection").addEventListener("click", closePreview);
$("back-collection").addEventListener("click", closePreview);
$("submit-collection").addEventListener("click", addSelected);
$("pick-video").addEventListener("click", pickVideo);
$("extract-form").addEventListener("submit", extractAudio);
$("language").addEventListener("change", event => changeSettings(() => api("/api/desktop/settings", { language: event.target.value })));
$("theme").addEventListener("change", event => changeSettings(() => api("/api/desktop/settings", { theme: event.target.value })));
$("folder-form").addEventListener("submit", event => {
  event.preventDefault();
  changeSettings(() => api("/api/desktop/settings", { download_dir: $("default-folder").value.trim() }));
});
$("reset-folder").addEventListener("click", () => changeSettings(() => api("/api/desktop/settings", { download_dir: "" })));
$("queue-refresh").addEventListener("click", refreshQueue);
$("history-refresh").addEventListener("click", async () => {
  await poll;
  state.snapshots.delete(state.currentBatch);
  await refreshQueue();
});
$("history-batch").addEventListener("change", event => {
  state.currentBatch = event.target.value;
  state.history.selected.clear();
  state.history.focused = "";
  renderResults();
  refreshQueue();
});
$("history-output").addEventListener("click", () => reveal(state.batches.find(batch => batch.id === state.currentBatch)?.download_dir, "history"));
$("reconnect").addEventListener("click", boot);

localize();
boot();
