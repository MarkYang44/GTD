// Entry point: the shell (sidebar, banner, views), global shortcuts, paste and drop, and the shared task
// handlers every list uses. State lives in store.js; I/O lives in service.js.
import { formatError } from "./strings.js";
import { $, copyText, flash, isMac, setText, shortcutLabel, toast } from "./ui.js";
import { closeMenu, isMenuOpen } from "./menu.js";
import { taskKey } from "./tasks.js";
import * as service from "./service.js";
import { SCOPES, flush, onRender, state, t, update } from "./store.js";
import { notice, showError } from "./feedback.js";
import { renderCollection } from "./collection.js";
import * as composer from "./composer.js";
import { initDownloads, renderDownloads, setScope } from "./downloads.js";
import { batchLabel, initBatches, renderBatches, selectBatch } from "./batches.js";
import { initSettings, renderSettings } from "./settings.js";

const VIEWS = ["downloads", "batches", "settings"];
const SHORTCUT_SCOPES = ["all", "active", "queued", "attention", "completed"];
const select = selector => document.querySelectorAll(selector);
const dialogOpen = () => $("collection").open;
// Only text entry keeps Escape and paste for itself; checkboxes and radios do not.
const isEditable = node => Boolean(node?.closest?.("textarea, select, [contenteditable='true'], input:not([type=checkbox], [type=radio], [type=button])"));

function actionToast(action, count) {
  return t({ cancel: "cancelledToast", retry: "retryingToast", redownload: "rerunToast" }[action] || "operationFinished", { count });
}

async function operate(action, tasks, view) {
  if (state.busy || !tasks.length) return;
  notice(view, "");
  try {
    const { succeeded, errors } = await service.runAction(action, tasks);
    const failed = new Set(errors.map(error => `${error.batch_id}/${error.task_id}`));
    update(s => {
      const selection = view === "batches" ? s.batchView.selected : s.downloads.selected;
      for (const task of tasks) if (!failed.has(taskKey(task))) selection.delete(taskKey(task));
    });
    if (errors.length) {
      notice(view, {
        message: t("operationPartial", { count: succeeded, failed: errors.length }),
        suggestion: errors.slice(0, 3).map(error => formatError(error, state.language)).join("\n"),
      });
    } else {
      toast(actionToast(action, succeeded), { dismissLabel: t("dismiss") });
    }
  } catch (error) {
    showError(view, error);
  }
}

async function revealPath(path, view) {
  if (!path) return;
  try {
    await service.reveal(path);
  } catch (error) {
    if (view) showError(view, error);
    else toast(formatError(error, state.language), { tone: "error", dismissLabel: t("dismiss") });
  }
}

async function openSource(url, view) {
  try {
    await service.openLink(url);
  } catch (error) {
    showError(view, error);
  }
}

async function copyValue(text, kind) {
  const copied = await copyText(text);
  toast(t(copied ? (kind === "path" ? "pathCopied" : "linkCopied") : "copyFailed"), {
    tone: copied ? "ok" : "error", duration: 2600, dismissLabel: t("dismiss"),
  });
}

function dismissTasks(tasks, dismissed) {
  const keys = tasks.map(taskKey);
  if (!keys.length) return;
  service.setDismissed(keys, dismissed);
  update(s => { for (const key of keys) s.downloads.selected.delete(key); });
  toast(t(dismissed ? "dismissedToast" : "restoredToast", { count: keys.length }), {
    dismissLabel: t("dismiss"),
    action: dismissed ? { label: t("undo"), run: () => service.setDismissed(keys, false) } : undefined,
  });
}

function openView(view) {
  if (!VIEWS.includes(view)) return;
  update(s => { s.view = view; });
}

// Errors with a known remedy jump to the setting that fixes them.
function fix(kind, task) {
  openView("settings");
  flush();
  const target = kind === "cookies" ? document.querySelector(`.cookie-row[data-platform="${task.platform}"]`) : $("folder-form");
  if (!target) return;
  target.scrollIntoView({ block: "center" });
  flash(target);
  (kind === "cookies" ? target.querySelector("button") : $("default-folder"))?.focus({ preventScroll: true });
}

function newDownload() {
  if (state.view !== "downloads") {
    update(s => { s.view = "downloads"; });
    flush();
  }
  window.scrollTo({ top: 0 });
  composer.focus();
}

const shared = {
  onAction: operate,
  onReveal: revealPath,
  newDownload,
  taskHandlers: view => ({
    onAction: (action, tasks) => operate(action, tasks, view),
    onReveal: path => revealPath(path, view),
    onOpenLink: url => openSource(url, view),
    onCopy: copyValue,
    onFix: fix,
    onDismiss: dismissTasks,
    isDismissed: key => state.dismissed.has(key),
    onGoToBatch: id => {
      selectBatch(id, { focus: true });
    },
    batchLabel: task => batchLabel(task.batch_id),
  }),
};

let localized = "";
function localize() {
  const root = document.documentElement;
  root.lang = state.language === "zh" ? "zh-CN" : "en";
  for (const node of select("[data-copy]")) node.textContent = t(node.dataset.copy);
  for (const node of select("[data-label]")) node.setAttribute("aria-label", t(node.dataset.label));
  for (const node of select("[data-placeholder]")) node.placeholder = t(node.dataset.placeholder);
  for (const node of select("[data-tip]")) node.title = t(node.dataset.tip, { keys: node.dataset.keys ? shortcutLabel(node.dataset.keys) : "" });
  for (const node of select(".button-keys")) node.textContent = shortcutLabel(node.closest("[data-keys]").dataset.keys);
  for (const control of select(".sidebar [data-scope], .sidebar [data-view]")) {
    const label = t(control.dataset.scope ? `scope_${control.dataset.scope}` : control.dataset.view);
    control.title = control.dataset.keys ? t("shortcut", { label, keys: shortcutLabel(control.dataset.keys) }) : label;
  }
  setText($("search-keys"), shortcutLabel("F"));
  setText($("batch-search-keys"), shortcutLabel("F"));
  renderCollection();
}

function renderShell(s, counts) {
  const root = document.documentElement;
  root.dataset.theme = s.settings?.theme || "system";
  for (const view of VIEWS) $(`view-${view}`).hidden = view !== s.view;
  for (const control of select(".sidebar [data-scope], .sidebar [data-view]")) {
    const current = control.dataset.scope ? s.view === "downloads" && s.downloads.scope === control.dataset.scope : s.view === control.dataset.view;
    if (current) control.setAttribute("aria-current", "page");
    else control.removeAttribute("aria-current");
  }
  for (const scope of SCOPES) {
    const value = counts[scope] || 0;
    const badge = $(`count-${scope}`);
    setText(badge, value ? value.toLocaleString(s.language === "zh" ? "zh-CN" : "en-US") : "");
    badge.hidden = !value;
    const control = badge.closest("button");
    control.setAttribute("aria-label", value ? `${t(`scope_${scope}`)}, ${value}` : t(`scope_${scope}`));
  }
  $("nav-cancelled").hidden = !counts.cancelled && !(s.view === "downloads" && s.downloads.scope === "cancelled");
  $("nav-attention").dataset.alert = String(counts.attention > 0);
  const batchesCount = $("count-batches");
  setText(batchesCount, s.batches.length ? String(s.batches.length) : "");
  batchesCount.hidden = !s.batches.length;
  batchesCount.closest("button").setAttribute("aria-label", t("batches"));

  const busy = s.booting && s.connection !== "ready";
  $("status-dot").dataset.connection = s.connection;
  setText($("status-text"), t(s.connection));
  setText($("status-version"), s.version ? `v${s.version}` : "");
  $("service-banner").hidden = s.connection !== "unavailable";
  setText($("service-error"), s.connectionError);
  $("reconnect").disabled = busy;
  setText($("reconnect"), t(busy ? "reconnecting" : "reconnect"));
  if (s.pollError) notice("workspace", { message: t("connectionLost") }, "warning");
  else notice("workspace", "");
}

let lastView = state.view;
function render(s) {
  if (localized !== s.language) {
    localized = s.language;
    localize();
  }
  const counts = renderDownloads(s);
  renderBatches(s);
  renderSettings(s);
  composer.render();
  renderShell(s, counts);
  if (lastView !== s.view) {
    lastView = s.view;
    closeMenu();
    // Focus left behind in a hidden view goes to the new view's heading.
    const active = document.activeElement;
    if (!active || active === document.body || active.closest(".view")?.hidden) $(`${s.view}-title`).focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }
}

/* Paste and drop: links can come in from anywhere in the window. */

let dragDepth = 0;
const dragKind = event => {
  const types = [...(event.dataTransfer?.types || [])];
  if (types.includes("Files")) return "files";
  return types.includes("text/uri-list") || types.includes("text/plain") ? "links" : "";
};

function showDrop(kind) {
  const overlay = $("drop-overlay");
  overlay.dataset.kind = kind;
  setText($("drop-title"), t(kind === "files" ? "dropFilesTitle" : "dropLinks"));
  setText($("drop-hint"), t(kind === "files" ? "dropFilesHint" : "dropLinksHint"));
  overlay.hidden = false;
}

function hideDrop() {
  dragDepth = 0;
  $("drop-overlay").hidden = true;
}

window.addEventListener("dragenter", event => {
  const kind = dragKind(event);
  if (!kind || dialogOpen()) return;
  event.preventDefault();
  dragDepth += 1;
  showDrop(kind);
});
window.addEventListener("dragover", event => {
  const kind = dragKind(event);
  if (!kind || dialogOpen()) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = kind === "files" ? "none" : "copy";
});
window.addEventListener("dragleave", event => {
  if (!dragKind(event)) return;
  dragDepth -= 1;
  if (dragDepth <= 0) hideDrop();
});
window.addEventListener("drop", event => {
  const kind = dragKind(event);
  if (!kind || dialogOpen()) return;
  event.preventDefault();
  hideDrop();
  if (kind === "files") {
    toast(t("dropFilesHint"), { tone: "info", dismissLabel: t("dismiss") });
    return;
  }
  const uris = (event.dataTransfer.getData("text/uri-list") || "").split(/\r?\n/).filter(line => line && !line.startsWith("#"));
  const text = uris.length ? uris.join("\n") : event.dataTransfer.getData("text/plain");
  if (!text?.trim()) return;
  newDownload();
  composer.insertText(text);
});

// Fallback for engines that deliver a paste to a non-editable focus (the keydown below covers the rest).
document.addEventListener("paste", event => {
  if (isEditable(event.target) || dialogOpen()) return;
  const text = event.clipboardData?.getData("text/plain");
  if (!text?.trim()) return;
  event.preventDefault();
  newDownload();
  composer.insertText(text);
});

document.addEventListener("keydown", event => {
  const modifier = isMac ? event.metaKey : event.ctrlKey;
  if (dialogOpen() || isMenuOpen()) return;
  if (event.key === "Escape" && !isEditable(event.target)) {
    if (state.view === "downloads" && state.downloads.selected.size) update(s => s.downloads.selected.clear());
    else if (state.view === "batches" && state.batchView.selected.size) update(s => s.batchView.selected.clear());
    return;
  }
  if (!modifier || event.altKey || event.shiftKey) return;
  const key = event.key.toLowerCase();
  if (key === "v") {
    // Let the native paste land in the link box: focus it before the paste happens.
    if (!isEditable(document.activeElement)) {
      if (state.view !== "downloads") {
        update(s => { s.view = "downloads"; });
        flush();
      }
      composer.prepareForPaste();
    }
    return;
  }
  const actions = {
    n: newDownload,
    o: () => {
      newDownload();
      composer.pickFile();
    },
    f: () => {
      if (state.view === "settings") newDownload();
      const search = $(state.view === "batches" ? "batches-search" : "downloads-search");
      search.focus();
      search.select();
    },
    ",": () => openView("settings"),
    6: () => openView("batches"),
  };
  for (const [index, scope] of SHORTCUT_SCOPES.entries()) actions[String(index + 1)] = () => setScope(scope);
  if (!actions[key]) return;
  event.preventDefault();
  actions[key]();
});

// Keep the WebView's browser menu (Reload, Save as…) out of the app; text fields and selected text
// still get the native Cut/Copy/Paste menu. Task rows open their own menu.
document.addEventListener("contextmenu", event => {
  if (event.defaultPrevented || event.target.closest?.("input, textarea") || String(window.getSelection())) return;
  event.preventDefault();
});

for (const control of select(".sidebar [data-scope]")) control.addEventListener("click", () => setScope(control.dataset.scope));
for (const control of select(".sidebar [data-view]")) control.addEventListener("click", () => openView(control.dataset.view));
$("new-download").addEventListener("click", newDownload);
$("reconnect").addEventListener("click", () => service.boot());

initDownloads(shared);
initBatches(shared);
initSettings();
onRender(render);

document.documentElement.dataset.platform = /Windows/.test(navigator.userAgent) ? "windows" : isMac ? "mac" : "other";
void window.__TAURI__?.app?.getVersion?.().then(version => update(s => { s.version = version; })).catch(() => {});
update(() => {});
flush();
service.boot();
