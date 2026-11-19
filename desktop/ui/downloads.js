// Downloads: one list over every stored batch. The sidebar picks the scope, the header searches it, the
// composer adds to it; finished work is grouped by day instead of living on a separate page.
import { $, button, dayKey, dayLabel, element, icon, setText, shortcutLabel } from "./ui.js";
import { pickFile } from "./composer.js";
import {
  SelectionBar, TaskList, byFinish, byQueue, byStart, emptyState, finishedAt, isActive, platformName, taskKey, taskName,
} from "./tasks.js";
import { allTasks } from "./service.js";
import { PAGE_SIZE, SCOPES, ctx, state, t, update } from "./store.js";

let list;
let bar;
let handlers;
let searchCache = { revision: -1, language: "", texts: new Map() };

export function scopeOf(task, dismissed) {
  if (isActive(task)) return "active";
  if (task.status === "queued") return "queued";
  if (task.status === "failed") return dismissed.has(taskKey(task)) ? "dismissed" : "attention";
  return task.status === "completed" || task.status === "cancelled" ? task.status : "other";
}

// Counts come from batch summaries, so the sidebar is exact before every batch has loaded.
export function scopeCounts(s) {
  const counts = { all: 0, active: 0, queued: 0, attention: 0, completed: 0, cancelled: 0 };
  for (const batch of s.batches) {
    counts.all += batch.total || 0;
    counts.active += batch.active || 0;
    counts.queued += batch.queued || 0;
    counts.attention += batch.failed || 0;
    counts.completed += batch.completed || 0;
    counts.cancelled += batch.cancelled || 0;
  }
  if (s.dismissed.size) {
    for (const task of allTasks()) if (task.status === "failed" && s.dismissed.has(taskKey(task))) counts.attention -= 1;
    counts.attention = Math.max(0, counts.attention);
  }
  return counts;
}

function haystack(task) {
  if (searchCache.revision !== state.revision || searchCache.language !== state.language) {
    searchCache = { revision: state.revision, language: state.language, texts: new Map() };
  }
  const key = taskKey(task);
  let text = searchCache.texts.get(key);
  if (text == null) {
    const file = task.result?.filepath?.split(/[\\/]/).pop();
    text = [taskName(task, ctx), task.title, task.url, file, platformName(task.platform, t), task.result?.format, t(task.media_type)]
      .filter(Boolean).join("\n").toLocaleLowerCase();
    searchCache.texts.set(key, text);
  }
  return text;
}

function byDay(tasks, sentence) {
  const groups = [];
  let current = null;
  for (const task of tasks) {
    const when = finishedAt(task);
    const key = when ? dayKey(when) : "unknown";
    if (!current || current.key !== key) {
      const day = when ? dayLabel(when, state.language, name => t(sentence ? `${name}Lower` : name)) : t("unknown");
      current = { key, id: `day-${key}`, label: sentence ? t("finishedOn", { day }) : day, tasks: [] };
      groups.push(current);
    }
    current.tasks.push(task);
  }
  return groups;
}

function attentionActions(tasks) {
  const retryable = tasks.filter(task => task.can_retry);
  const actions = [];
  if (retryable.length) {
    actions.push({ label: t("retryAll", { count: retryable.length }), icon: "retry", disabled: state.busy, run: () => handlers.onAction("retry", retryable) });
  }
  if (tasks.length) actions.push({ label: t("dismissAll"), icon: "eye-off", run: () => handlers.onDismiss(tasks, true) });
  return actions;
}

function groupsFor(scope, tasks, dismissed) {
  const pick = name => tasks.filter(task => scopeOf(task, dismissed) === name);
  if (scope === "active") return [{ id: "active", tasks: pick("active").sort(byStart) }];
  if (scope === "queued") return [{ id: "queued", tasks: pick("queued").sort(byQueue) }];
  if (scope === "attention") {
    const failed = pick("attention").sort(byFinish);
    return [{ id: "attention", label: failed.length ? t("failedCount", { count: failed.length }) : "", tasks: failed, actions: attentionActions(failed) }];
  }
  if (scope === "completed" || scope === "cancelled") return byDay(pick(scope).sort(byFinish), false);
  const attention = pick("attention").sort(byFinish);
  const finished = tasks.filter(task => ["completed", "cancelled", "dismissed", "other"].includes(scopeOf(task, dismissed))).sort(byFinish);
  return [
    { id: "active", label: t("section_active"), tasks: pick("active").sort(byStart) },
    { id: "queued", label: t("section_queued"), tasks: pick("queued").sort(byQueue) },
    { id: "attention", label: t("section_failed"), tasks: attention, actions: attentionActions(attention) },
    ...byDay(finished, true),
  ].filter(group => group.tasks.length);
}

function speedOf(tasks) {
  let total = 0;
  for (const task of tasks) {
    // speed_mbps is MiB/s; older snapshots only carry the "8.91 MB/s" text.
    const value = Number(task.progress?.speed_mbps ?? task.speed_mbps ?? Number.parseFloat(task.progress?.speed_text));
    if (isActive(task) && Number.isFinite(value)) total += value;
  }
  return total;
}

function summary(scope, counts, shown, query) {
  if (query) return t("searchResults", { count: shown });
  if (scope !== "all") return counts[scope] ? t("scopeCount", { count: counts[scope] }) : "";
  if (counts.active || counts.queued) {
    const parts = [];
    if (counts.active) parts.push(t("summaryDownloading", { count: counts.active }));
    if (counts.queued) parts.push(t("summaryQueued", { count: counts.queued }));
    const speed = speedOf(allTasks());
    if (speed > 0) parts.push(`${speed.toFixed(speed >= 100 ? 0 : 1)} MB/s`);
    return parts.join(" · ");
  }
  if (!counts.all) return "";
  const parts = [t("summaryTotal", { count: counts.all })];
  if (counts.attention) parts.push(t("summaryAttention", { count: counts.attention }));
  return parts.join(" · ");
}

const emptyCache = new Map();
function cached(name, build) {
  const key = `${name}:${state.language}`;
  if (!emptyCache.has(key)) emptyCache.set(key, build());
  return emptyCache.get(key);
}

function heroEmpty() {
  return cached("hero", () => {
    const node = element("div", "hero-empty");
    const art = element("img", "hero-art");
    art.src = "./brand.png";
    art.alt = "";
    art.width = 88;
    art.height = 88;
    const copy = element("div", "hero-copy");
    copy.append(
      element("p", "hero-platforms", "YouTube · Instagram · Bilibili"),
      element("h2", "hero-title", "Capture. Convert. Keep."),
      element("p", "hero-intro", t("featureIntro")),
    );
    const tips = element("ul", "hero-tips");
    for (const [iconName, label, keys] of [
      ["link", t("tipPaste"), shortcutLabel("V")],
      ["download", t("tipDrop"), ""],
    ]) {
      const tip = element("li", "hero-tip");
      const mark = element("span", "hero-tip-mark");
      mark.append(icon(iconName));
      tip.append(mark, element("span", "hero-tip-label", label));
      if (keys) tip.append(element("kbd", "", keys));
      tips.append(tip);
    }
    const actions = element("div", "empty-actions");
    const extract = button(t("fromFileLong"), () => pickFile(), "secondary compact", "file-video");
    extract.append(element("kbd", "", shortcutLabel("O")));
    actions.append(extract);
    node.append(art, copy, tips, actions);
    return node;
  });
}

function scopeEmpty(scope) {
  const spec = {
    all: ["download", "emptyAll", "emptyAllHint"],
    active: ["arrow-down-circle", "emptyActive", "emptyActiveHint"],
    queued: ["clock", "emptyQueued", "emptyQueuedHint"],
    attention: ["check-circle", "emptyAttention", "emptyAttentionHint"],
    completed: ["check-circle", "emptyCompleted", "emptyCompletedHint"],
    cancelled: ["slash", "emptyCancelled", ""],
  }[scope];
  return cached(`scope-${scope}`, () => emptyState({ iconName: spec[0], title: t(spec[1]), hint: spec[2] ? t(spec[2]) : "", className: "compact" }));
}

function searchEmpty(query) {
  const node = cached("search", () => {
    const root = emptyState({ iconName: "search", title: "", hint: "", className: "compact", actions: [button(t("clearSearch"), () => setQuery("", true), "secondary compact")] });
    return root;
  });
  setText(node.querySelector(".empty-title"), t("noSearchResults", { query }));
  return node;
}

function loadingEmpty() {
  return cached("loading", () => {
    const node = element("div", "list-loading");
    for (let index = 0; index < 4; index += 1) node.append(element("div", "skeleton-row"));
    node.setAttribute("aria-label", t("loadingHistory"));
    node.setAttribute("role", "status");
    return node;
  });
}

function emptyFor(s, scope, query) {
  if (query) return () => searchEmpty(query);
  if (s.connection === "unavailable") return () => cached("offline", () => emptyState({ iconName: "alert", title: t("downloadsOffline"), hint: t("serviceDownHint"), className: "compact" }));
  if (s.connection !== "ready" || (!s.historyReady && s.batches.length)) return loadingEmpty;
  if (!s.batches.length && scope === "all") return heroEmpty;
  return () => scopeEmpty(scope);
}

export function setQuery(value, focus = false) {
  const input = $("downloads-search");
  if (input.value !== value) input.value = value;
  update(s => {
    s.downloads.query = value;
    s.downloads.limit = PAGE_SIZE;
  });
  if (focus) input.focus();
}

export function setScope(scope) {
  if (!SCOPES.includes(scope)) return;
  update(s => {
    if (s.downloads.scope !== scope) {
      s.downloads.scope = scope;
      s.downloads.limit = PAGE_SIZE;
      s.downloads.expanded = "";
    }
    s.view = "downloads";
  });
}

export function initDownloads(shared) {
  handlers = shared;
  const selection = state.downloads.selected;
  list = new TaskList($("downloads-list"), {
    ...shared.taskHandlers("downloads"),
    onSelect: (tasks, checked) => update(s => {
      for (const task of tasks) {
        if (checked) s.downloads.selected.add(taskKey(task));
        else s.downloads.selected.delete(taskKey(task));
      }
    }),
    onExpand: key => update(s => { s.downloads.expanded = s.downloads.expanded === key ? "" : key; }),
    onClearSelection: () => update(() => selection.clear()),
    onMore: () => update(s => { s.downloads.limit += PAGE_SIZE; }),
  });
  bar = new SelectionBar($("downloads-selection"), {
    onAction: (action, tasks) => shared.onAction(action, tasks, "downloads"),
    onDismiss: tasks => shared.onDismiss(tasks, true),
    onSelect: tasks => update(s => { for (const task of tasks) s.downloads.selected.add(taskKey(task)); }),
    onClearSelection: () => update(s => s.downloads.selected.clear()),
  });
  $("downloads-search").addEventListener("input", event => setQuery(event.target.value));
  $("search-everywhere").addEventListener("click", () => setScope("all"));
  $("downloads-search").addEventListener("keydown", event => {
    if (event.key === "Escape" && event.target.value) {
      event.preventDefault();
      setQuery("");
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      list.focusFirst();
    }
  });
}

export function renderDownloads(s) {
  const { scope, query, selected, expanded, limit } = s.downloads;
  const counts = scopeCounts(s);
  if (s.view !== "downloads") {
    bar.hide();
    return counts;
  }
  const needle = query.trim().toLocaleLowerCase();
  const tasks = needle ? allTasks().filter(task => haystack(task).includes(needle)) : allTasks();
  const groups = groupsFor(scope, tasks, s.dismissed);
  const shown = groups.reduce((sum, group) => sum + group.tasks.length, 0);
  // A search inside one list still points at matches the other lists hold.
  const elsewhere = needle && scope !== "all" ? tasks.length - shown : 0;
  $("downloads-elsewhere").hidden = elsewhere <= 0;
  if (elsewhere > 0) setText($("search-everywhere"), t("searchElsewhere", { count: elsewhere }));
  setText($("downloads-title"), t(`scope_${scope}`));
  setText($("downloads-summary"), summary(scope, counts, shown, needle));
  // Selection only counts tasks this scope still shows, so a filter change never acts on hidden rows.
  const visibleKeys = new Set(groups.flatMap(group => group.tasks.map(taskKey)));
  for (const key of [...selected]) if (!visibleKeys.has(key)) selected.delete(key);
  if (expanded && !visibleKeys.has(expanded)) s.downloads.expanded = "";
  list.render({
    groups, ctx, selected, expanded: s.downloads.expanded, busy: s.busy, limit, pageSize: PAGE_SIZE,
    empty: emptyFor(s, scope, needle), fresh: s.fresh, animate: true,
  });
  const visible = groups.flatMap(group => group.tasks);
  bar.render({
    ctx, chosen: visible.filter(task => selected.has(taskKey(task))), visible, busy: s.busy,
    dismissable: true, isDismissed: key => s.dismissed.has(key),
  });
  const loading = $("downloads-loading");
  const pending = s.batches.filter(batch => !s.snapshots.has(batch.id)).length;
  loading.hidden = s.historyReady || !pending || !shown;
  setText(loading, t("loadingBatches", { count: pending }));
  return counts;
}
