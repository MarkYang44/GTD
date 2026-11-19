// Everything that talks to the native host or the Python service: boot, polling, the background history
// loader and task actions. Views only read `state`; they never fetch on their own.
import { formatError } from "./strings.js";
import { save } from "./prefs.js";
import { state, update } from "./store.js";

const COUNT_KEYS = ["total", "active", "queued", "completed", "failed", "cancelled"];
const ACTION_CHUNK = 100;

export function invoke(command, args) {
  if (!window.__TAURI__?.core?.invoke) {
    return Promise.reject(new Error("Open this workspace in GTD Desktop."));
  }
  return window.__TAURI__.core.invoke(command, args);
}

export function api(path, body) {
  return invoke("api", body === undefined ? { path } : { path, body });
}

function applySettings(s, settings) {
  s.settings = settings;
  s.language = settings.language === "zh" ? "zh" : "en";
}

let poll = null;
let pollTimer = null;
let loader = null;

export async function boot() {
  clearTimeout(pollTimer);
  update(s => {
    s.booting = true;
    if (s.connection !== "unavailable") s.connection = "starting";
  });
  try {
    const [settings, capabilities] = await Promise.all([api("/api/desktop/settings"), api("/api/capabilities")]);
    update(s => {
      s.capabilities = capabilities;
      s.connection = "ready";
      s.connectionError = "";
      s.booting = false;
      applySettings(s, settings);
    });
    void invoke("renderer_ready", {}).catch(() => {});
    await refresh();
  } catch (error) {
    update(s => {
      s.booting = false;
      s.connection = "unavailable";
      s.connectionError = formatError(error, s.language);
    });
  }
}

const busyBatch = batch => Boolean(batch.active || batch.queued);

export function refresh() {
  if (state.connection !== "ready") return Promise.resolve();
  if (poll) return poll;
  clearTimeout(pollTimer);
  poll = pollOnce()
    .then(() => {
      if (state.pollError) update(s => { s.pollError = false; });
    })
    .catch(() => {
      if (!state.pollError) update(s => { s.pollError = true; });
    })
    .finally(() => {
      poll = null;
      pollTimer = setTimeout(refresh, state.batches.some(busyBatch) ? 1000 : 4000);
    });
  return poll;
}

// A finished snapshot stays valid until its summary moves (a retry or redownload changes the counts).
function isStale(summary) {
  const saved = state.snapshots.get(summary.id);
  if (!saved || state.stale.has(summary.id)) return true;
  if (!summary.all_done || !saved.all_done) return true;
  return COUNT_KEYS.some(key => key in saved && (saved[key] || 0) !== (summary[key] || 0));
}

async function pollOnce() {
  const { batches } = await api("/api/batches");
  const present = new Set(batches.map(batch => batch.id));
  update(s => {
    s.batches = batches;
    let pruned = false;
    for (const id of [...s.snapshots.keys()]) {
      if (!present.has(id)) {
        s.snapshots.delete(id);
        pruned = true;
      }
    }
    for (const id of [...s.stale]) if (!present.has(id)) s.stale.delete(id);
    if (pruned) s.revision += 1;
    if (s.batchView.current && !present.has(s.batchView.current)) {
      s.batchView.current = "";
      s.batchView.selected.clear();
      s.batchView.expanded = "";
    }
    const kept = [...s.dismissed].filter(key => present.has(key.split("/")[0]));
    if (kept.length !== s.dismissed.size) {
      s.dismissed = new Set(kept);
      save("dismissed", kept);
    }
  });
  // Live batches refresh on every poll; finished ones load once through the background loader.
  const due = batches.filter(summary => (state.snapshots.has(summary.id) ? isStale(summary) : busyBatch(summary) || !summary.all_done));
  await Promise.all(due.map(summary => fetchBatch(summary.id)));
  loadHistory();
}

async function fetchBatch(id) {
  try {
    const snapshot = await api(`/api/batch/${encodeURIComponent(id)}`);
    if (!state.batches.some(batch => batch.id === id)) return;
    update(s => {
      s.snapshots.set(id, snapshot);
      s.stale.delete(id);
      s.revision += 1;
    });
  } catch {
    // A pruned batch leaves with the next summary poll; anything else is retried then.
  }
}

// Fetch every stored batch once: live work first, then batches with failures, then newest first.
function loadHistory() {
  if (loader || state.connection !== "ready") return;
  const missing = state.batches.filter(batch => !state.snapshots.has(batch.id));
  if (!missing.length) {
    if (!state.historyReady) update(s => { s.historyReady = true; });
    return;
  }
  const rank = batch => (busyBatch(batch) ? 0 : batch.failed ? 1 : 2);
  const queue = missing.map((batch, index) => ({ batch, index }))
    .sort((a, b) => rank(a.batch) - rank(b.batch) || a.index - b.index)
    .map(item => item.batch.id);
  loader = Promise.all(Array.from({ length: Math.min(4, queue.length) }, async () => {
    while (queue.length) await fetchBatch(queue.shift());
  })).finally(() => {
    loader = null;
    if (!state.historyReady) update(s => { s.historyReady = true; });
  });
}

let derived = { batches: null, revision: -1, tasks: [] };

// Every loaded task, newest batch first, tagged with its batch for actions and grouping.
export function allTasks() {
  if (derived.batches === state.batches && derived.revision === state.revision) return derived.tasks;
  const tasks = [];
  for (const batch of state.batches) {
    const snapshot = state.snapshots.get(batch.id);
    for (const task of snapshot?.tasks || []) {
      tasks.push({ ...task, batch_id: batch.id, batch_created: batch.created_at || 0 });
    }
  }
  derived = { batches: state.batches, revision: state.revision, tasks };
  return tasks;
}

export async function runAction(action, tasks) {
  await poll;
  update(s => { s.busy = true; });
  let succeeded = 0;
  const errors = [];
  try {
    // Bounded requests let a large selection report partial completion.
    for (let start = 0; start < tasks.length; start += ACTION_CHUNK) {
      const refs = tasks.slice(start, start + ACTION_CHUNK).map(task => ({ batch_id: task.batch_id, task_id: task.id }));
      const response = await api("/api/desktop/batch-action", { action, tasks: refs });
      succeeded += response.succeeded;
      errors.push(...response.errors);
    }
    return { succeeded, errors };
  } finally {
    await poll;
    update(s => {
      s.busy = false;
      for (const task of tasks) s.stale.add(task.batch_id);
    });
    await refresh();
  }
}

export function setDismissed(keys, dismissed) {
  update(s => {
    for (const key of keys) {
      if (dismissed) s.dismissed.add(key);
      else s.dismissed.delete(key);
    }
  });
  save("dismissed", [...state.dismissed]);
}

export async function saveSettings(patch) {
  const settings = await api("/api/desktop/settings", patch);
  update(s => applySettings(s, settings));
  return settings;
}

export async function setCookies(platform, path) {
  await api("/api/desktop/cookies", { platform, path });
  const settings = await api("/api/desktop/settings");
  update(s => applySettings(s, settings));
}

export const previewLinks = inputs => api("/api/preview", { inputs });

async function adopt(response) {
  await poll;
  update(s => { s.fresh = response.batch_id; });
  await refresh();
}

export async function startDownload(options, previewId, entryIds) {
  const response = await api("/api/download", { ...options, preview_id: previewId, selected_entry_ids: entryIds });
  await adopt(response);
  return response;
}

export async function startExtraction(body) {
  const response = await api("/api/desktop/extract", body);
  await adopt(response);
  return response;
}

export const pickPath = (kind, initialDir) => invoke("pick_path", initialDir ? { kind, initialDir } : { kind });
export const reveal = path => invoke("reveal_path", { path });
export const openLink = url => invoke("open_link", { url });

// The folder new work saves to unless the composer overrides it.
export function defaultFolder() {
  return state.settings?.download_dir || state.settings?.default_download_dir || state.capabilities?.default_download_dir || "";
}
