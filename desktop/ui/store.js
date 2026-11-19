// One state object for the whole workspace. Mutations go through update(); every view re-renders once
// per microtask batch and skips its own unchanged work, so callers never decide what to repaint.
import { translate } from "./strings.js";
import { load } from "./prefs.js";

export const PAGE_SIZE = 80;
export const SCOPES = ["all", "active", "queued", "attention", "completed", "cancelled"];

export const state = {
  connection: "starting",
  connectionError: "",
  pollError: false,
  booting: false,
  language: "en",
  settings: null,
  capabilities: null,
  version: "",
  batches: [],
  snapshots: new Map(),
  stale: new Set(),
  revision: 0,
  historyReady: false,
  fresh: "",
  view: "downloads",
  busy: false,
  downloads: { scope: "all", query: "", selected: new Set(), expanded: "", limit: PAGE_SIZE },
  batchView: { current: "", query: "", filter: "all", selected: new Set(), expanded: "", limit: PAGE_SIZE },
  dismissed: new Set(load("dismissed", [])),
};

const renderers = [];
let queued = false;

export function onRender(renderer) {
  renderers.push(renderer);
}

export function changed() {
  if (queued) return;
  queued = true;
  queueMicrotask(flush);
}

// Run pending renders now, e.g. before focusing an element a state change is about to reveal.
export function flush() {
  if (!queued) return;
  queued = false;
  for (const renderer of renderers) {
    try {
      renderer(state);
    } catch (error) {
      // One broken view must not freeze the others; surface the error asynchronously.
      setTimeout(() => { throw error; });
    }
  }
}

export function update(mutate) {
  mutate(state);
  changed();
}

export const t = (key, values) => translate(key, state.language, values);
export const ctx = { t, get language() { return state.language; } };
