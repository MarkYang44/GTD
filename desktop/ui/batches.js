// Batches: every submission with the settings it used. Browse or search the list, then act on a batch as
// a whole (show its folder, retry its failures) or on its tasks with the same rows as Downloads.
import { localValue } from "./strings.js";
import { $, button, dayKey, dayLabel, element, formatClock, formatDateTime, icon, reconcile, setText } from "./ui.js";
import { SelectionBar, TaskList, emptyState, isActive, taskKey } from "./tasks.js";
import { PAGE_SIZE, ctx, state, t, update } from "./store.js";

const FILTERS = ["all", "active", "queued", "failed", "completed", "cancelled"];
let list;
let bar;
let shared;
const batchViews = new Map();
const dayViews = new Map();
const infoCache = new Map();

function info(batch) {
  const snapshot = state.snapshots.get(batch.id);
  if (!snapshot) return null;
  let entry = infoCache.get(batch.id);
  if (!entry || entry.snapshot !== snapshot) {
    const titles = (snapshot.tasks || []).map(task => task.result?.title || task.title || task.url || "").filter(Boolean);
    entry = {
      snapshot, titles, search: titles.join("\n").toLocaleLowerCase(),
      local: (snapshot.tasks || []).some(task => task.platform === "local"),
    };
    infoCache.set(batch.id, entry);
  }
  return entry;
}

export function batchKind(batch) {
  if (info(batch)?.local) return "local";
  return batch.media_type === "audio" ? "audio" : "video";
}

export function batchName(batch) {
  const raw = info(batch)?.titles[0];
  const title = raw && localValue(raw, state.language);
  if (!title) return [t(`batchKind_${batchKind(batch)}`), t("batchItems", { count: batch.total })].join(" · ");
  return batch.total > 1 ? t("batchMore", { title, count: batch.total - 1, total: batch.total }) : title;
}

export function batchLabel(batchId) {
  const batch = state.batches.find(item => item.id === batchId);
  return batch ? `${batchName(batch)} · ${formatDateTime(batch.created_at, state.language)}` : "";
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

function matchesFilter(task, filter) {
  return filter === "all" || (filter === "active" ? isActive(task) : task.status === filter);
}

export function selectBatch(id, { focus = false } = {}) {
  update(s => {
    s.view = "batches";
    if (s.batchView.current !== id) {
      s.batchView.current = id;
      s.batchView.selected.clear();
      s.batchView.expanded = "";
      s.batchView.filter = "all";
      s.batchView.limit = PAGE_SIZE;
    }
  });
  if (focus) queueMicrotask(() => {
    const item = batchViews.get(id)?.item;
    item?.scrollIntoView({ block: "nearest" });
    item?.focus({ preventScroll: true });
  });
}

function renderBatchList(s) {
  const query = s.batchView.query.trim().toLocaleLowerCase();
  const matches = s.batches.filter(batch => {
    if (!query) return true;
    const haystack = [info(batch)?.search || "", batchFormat(batch), formatDateTime(batch.created_at, s.language)].join(" ").toLocaleLowerCase();
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
      setText(header, dayLabel(batch.created_at, s.language, t));
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
    const renderKey = JSON.stringify([s.language, batch, info(batch)?.titles?.[0], s.batchView.current === batch.id]);
    if (renderKey !== view.key) {
      view.key = renderKey;
      const kind = batchKind(batch);
      view.kind.firstElementChild.firstElementChild.setAttribute("href", `#i-${{ local: "extract", audio: "audio", video: "video" }[kind]}`);
      const name = batchName(batch);
      setText(view.name, name);
      view.item.title = name;
      view.sub.replaceChildren(element("span", "", [formatClock(batch.created_at, s.language), t("batchItems", { count: batch.total })].join(" · ")));
      if (batch.failed) view.sub.append(element("span", "batch-failed", ` · ${t("batchFailed", { count: batch.failed })}`));
      else if (batch.active || batch.queued) view.sub.append(element("span", "batch-pending", ` · ${t("batchActive", { count: (batch.active || 0) + (batch.queued || 0) })}`));
      view.item.querySelector(".status-bar")?.remove();
      view.item.append(statusBar(batch));
      view.item.setAttribute("aria-current", String(s.batchView.current === batch.id));
    }
    nodes.push(view.item);
  }
  for (const id of [...batchViews.keys()]) if (!s.batches.some(batch => batch.id === id)) batchViews.delete(id);
  if (!nodes.length) {
    renderBatchList.empty ||= element("p", "batch-empty");
    renderBatchList.empty.textContent = t("noBatchMatches", { query: s.batchView.query.trim() });
    nodes.push(renderBatchList.empty);
  }
  reconcile($("batch-list"), nodes);
}

function settingChips(batch) {
  const chips = [batchFormat(batch)];
  const subtitles = batch.subtitle_options || {};
  if (subtitles.subtitles) chips.push(t(subtitles.automatic ? "summaryAutomatic" : "summarySubtitles"));
  if (subtitles.danmaku) chips.push(t("summaryDanmaku"));
  if (batch.speed_mode === "turbo") chips.push(t("summaryTurbo"));
  return chips;
}

function renderBatchHeader(s, batch, tasks) {
  const header = $("batch-header");
  const retryable = tasks.filter(task => task.status === "failed" && task.can_retry);
  const counts = Object.fromEntries(FILTERS.map(filter => [filter, tasks.filter(task => matchesFilter(task, filter)).length]));
  const filter = s.batchView.filter || "all";
  const key = JSON.stringify([s.language, batch, info(batch)?.titles?.[0], retryable.length, s.busy, counts, filter]);
  if (header.dataset.key === key) return;
  header.dataset.key = key;
  const focused = header.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
  const heading = element("div", "batch-heading");
  const title = element("h2", "", batchName(batch));
  title.id = "batch-title";
  const facts = element("p", "batch-facts");
  facts.append(
    element("span", "", formatDateTime(batch.created_at, s.language)),
    element("span", "", t("batchProgress", { completed: batch.completed || 0, total: batch.total })),
  );
  if (batch.failed) facts.append(element("span", "failed", t("batchFailed", { count: batch.failed })));
  if (batch.active || batch.queued) facts.append(element("span", "", t("batchActive", { count: (batch.active || 0) + (batch.queued || 0) })));
  const chips = element("p", "batch-settings");
  chips.setAttribute("aria-label", t("batchSettings"));
  for (const label of settingChips(batch)) chips.append(element("span", "tag", label));
  heading.append(title, facts, chips);
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
    const show = button(t("showFolder"), () => shared.onReveal(batch.download_dir, "batches"), "secondary compact", "folder");
    show.dataset.focusKey = "show-folder";
    actions.append(show);
  }
  if (retryable.length) {
    const retry = button(t("retryFailed", { count: retryable.length }), () => shared.onAction("retry", retryable, "batches"), "primary compact", "retry");
    retry.disabled = s.busy;
    retry.dataset.focusKey = "retry-failed";
    actions.append(retry);
  }
  if (actions.childElementCount) toolbar.append(actions);
  const chipsRow = element("div", "chips");
  chipsRow.setAttribute("role", "group");
  chipsRow.setAttribute("aria-label", t("filterTasks"));
  for (const name of FILTERS) {
    if (name !== "all" && name !== filter && !counts[name]) continue;
    const chip = element("button", "chip");
    chip.type = "button";
    chip.dataset.focusKey = `filter-${name}`;
    chip.dataset.filter = name;
    chip.setAttribute("aria-pressed", String(filter === name));
    // The text node keeps the accessible name readable ("Failed 1"); flex gap handles spacing.
    chip.append(element("span", "", t(`filter_${name}`)), " ", element("span", "chip-count", String(counts[name])));
    chip.addEventListener("click", () => update(state => {
      state.batchView.filter = name;
      state.batchView.selected.clear();
      state.batchView.limit = PAGE_SIZE;
    }));
    chipsRow.append(chip);
  }
  header.replaceChildren(heading, ...(toolbar.childElementCount ? [toolbar] : []), ...(tasks.length > 1 ? [chipsRow] : []));
  if (focused) header.querySelector(`[data-focus-key="${focused}"]`)?.focus({ preventScroll: true });
}

const emptyCache = new Map();

export function initBatches(handlers) {
  shared = handlers;
  list = new TaskList($("batch-tasks"), {
    ...handlers.taskHandlers("batches"),
    onGoToBatch: null,
    onSelect: (tasks, checked) => update(s => {
      for (const task of tasks) {
        if (checked) s.batchView.selected.add(taskKey(task));
        else s.batchView.selected.delete(taskKey(task));
      }
    }),
    onExpand: key => update(s => { s.batchView.expanded = s.batchView.expanded === key ? "" : key; }),
    onClearSelection: () => update(s => s.batchView.selected.clear()),
    onMore: () => update(s => { s.batchView.limit += PAGE_SIZE; }),
  });
  bar = new SelectionBar($("batches-selection"), {
    onAction: (action, tasks) => handlers.onAction(action, tasks, "batches"),
    onDismiss: () => {},
    onSelect: tasks => update(s => { for (const task of tasks) s.batchView.selected.add(taskKey(task)); }),
    onClearSelection: () => update(s => s.batchView.selected.clear()),
  });
  $("batches-search").addEventListener("input", event => update(s => { s.batchView.query = event.target.value; }));
  $("batches-search").addEventListener("keydown", event => {
    if (event.key === "Escape" && event.target.value) {
      event.preventDefault();
      event.target.value = "";
      update(s => { s.batchView.query = ""; });
    }
  });
}

export function renderBatches(s) {
  if (s.view !== "batches") {
    bar.hide();
    return;
  }
  setText($("batches-summary"), s.batches.length ? t("batchesSummary", { count: s.batches.length }) : "");
  const hasBatches = s.batches.length > 0;
  $("batches-layout").hidden = !hasBatches;
  $("batches-empty").hidden = hasBatches || s.connection !== "ready";
  if (!hasBatches) {
    const key = `empty:${s.language}`;
    if (!emptyCache.has(key)) {
      emptyCache.set(key, emptyState({
        iconName: "layers", title: t("batchesEmpty"), hint: t("batchesEmptyHint"),
        actions: [button(t("newDownload"), () => shared.newDownload(), "primary compact", "plus")],
      }));
    }
    if ($("batches-empty").firstElementChild !== emptyCache.get(key)) $("batches-empty").replaceChildren(emptyCache.get(key));
    bar.hide();
    return;
  }
  if (!s.batches.some(batch => batch.id === s.batchView.current)) {
    s.batchView.current = s.batches[0].id;
    s.batchView.selected.clear();
    s.batchView.expanded = "";
    s.batchView.filter = "all";
  }
  renderBatchList(s);
  const batch = s.batches.find(item => item.id === s.batchView.current);
  const snapshot = s.snapshots.get(batch.id);
  const tasks = (snapshot?.tasks || [])
    .map(task => ({ ...task, batch_id: batch.id, batch_created: batch.created_at || 0 }))
    .sort((a, b) => (a.position || 0) - (b.position || 0) || (a.index || 0) - (b.index || 0));
  renderBatchHeader(s, batch, tasks);
  const filter = s.batchView.filter || "all";
  const shown = tasks.filter(task => matchesFilter(task, filter));
  const visibleKeys = new Set(shown.map(taskKey));
  for (const key of [...s.batchView.selected]) if (!visibleKeys.has(key)) s.batchView.selected.delete(key);
  list.render({
    groups: [{ id: "batch", tasks: shown }], ctx, selected: s.batchView.selected, expanded: s.batchView.expanded,
    busy: s.busy, limit: s.batchView.limit, pageSize: PAGE_SIZE, fresh: "", animate: true,
    empty: () => {
      const key = `${snapshot ? "none" : "loading"}:${s.language}`;
      if (!emptyCache.has(key)) {
        const node = element("div", "empty-state compact");
        node.append(element("p", "", t(snapshot ? "noMatches" : "batchLoading")));
        emptyCache.set(key, node);
      }
      return emptyCache.get(key);
    },
  });
  bar.render({ ctx, chosen: shown.filter(task => s.batchView.selected.has(taskKey(task))), visible: shown, busy: s.busy });
}
