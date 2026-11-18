import { errorParts, localValue, progressStage } from "./strings.js";
import {
  button, callout, element, fadeIn, flip, formatDateTime, formatDuration, icon, iconButton,
  reconcile, reducedMotion, setHidden, setIcon, setText,
} from "./ui.js";

export const isActive = task => task.status === "running" || task.status === "running_uninterruptible";
export const taskKey = task => `${task.batch_id}/${task.id}`;
const startedAt = task => task.attempts?.at(-1)?.started_at || 0;
const finishedAt = task => task.attempts?.at(-1)?.finished_at || startedAt(task);
const FILTERS = ["all", "active", "queued", "failed", "cancelled", "completed"];
const ERROR_FIXES = {
  AUTH_REQUIRED: "cookies", MEMBERSHIP_REQUIRED: "cookies", COLLECTION_EXTRACT_FAILED: "cookies",
  METADATA_FAILED: "cookies", INVALID_DOWNLOAD_DIR: "folder", STORAGE_ERROR: "folder",
};

export function taskName(task, ctx) {
  const title = task.result?.title || task.title;
  if (title) return localValue(title, ctx.language);
  return task.platform === "local" ? ctx.t("local") : task.url || ctx.t("unknown");
}

export function platformName(platform, t) {
  return { youtube: "YouTube", instagram: "Instagram", bilibili: "Bilibili", local: t("local") }[platform] || platform;
}

export function percentOf(task) {
  const value = Number.parseFloat(task.progress?.percent_text);
  return Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : null;
}

export function statusInfo(task, t) {
  if (isActive(task)) {
    const working = task.postprocessing || task.platform === "local";
    return {
      tone: "active",
      icon: working ? "spinner" : "arrow-down-circle",
      text: t(task.platform === "local" ? "extracting" : task.postprocessing ? "processing" : task.status),
    };
  }
  const known = {
    queued: ["queued", "clock"], completed: ["done", "check-circle"], failed: ["failed", "alert"], cancelled: ["cancelled", "slash"],
  }[task.status];
  return { tone: known?.[0] || "queued", icon: known?.[1] || "clock", text: t(task.status || "unknown") };
}

export function statusText(task, t) {
  return statusInfo(task, t).text;
}

function matches(task, filter) {
  return filter === "all" || (filter === "active" ? isActive(task) : task.status === filter);
}

export function countTasks(tasks) {
  const counts = Object.fromEntries(FILTERS.map(filter => [filter, 0]));
  for (const task of tasks) {
    counts.all += 1;
    if (isActive(task)) counts.active += 1;
    else if (task.status in counts) counts[task.status] += 1;
  }
  return counts;
}

function telemetry(task, ctx) {
  const progress = task.progress || {};
  const speed = localValue(progress.speed_text, ctx.language);
  const eta = localValue(progress.eta_text, ctx.language);
  return [speed && speed !== "…" ? speed : "", eta && eta !== "…" ? ctx.t("etaLeft", { eta }) : ""].filter(Boolean);
}

function rowDetail(task, ctx) {
  if (isActive(task)) {
    if (task.postprocessing || task.platform === "local") return progressStage(task, ctx.language);
    return telemetry(task, ctx).join(" · ");
  }
  if (task.status === "failed" && task.error) return errorParts(task.error, ctx.language).message;
  if (task.status === "completed") {
    const result = task.result || {};
    return [result.filesize, result.format].filter(Boolean).map(value => localValue(String(value), ctx.language)).join(" · ");
  }
  return "";
}

function quickAction(task, ctx) {
  const name = taskName(task, ctx);
  if (task.can_cancel) return { action: "cancel", icon: "close", label: ctx.t("cancelTask", { name }) };
  if (task.can_retry) return { action: "retry", icon: "retry", label: ctx.t("retryTask", { name }) };
  if (task.status === "completed" && task.result?.filepath) return { action: "reveal", icon: "folder", label: ctx.t("revealTask", { name }) };
  return null;
}

function sortGroups(tasks, grouped) {
  if (!grouped) return [{ id: "all", tasks }];
  const byStart = (a, b) => startedAt(a) - startedAt(b);
  const byQueue = (a, b) => (a.batch_created || 0) - (b.batch_created || 0) || (a.position || 0) - (b.position || 0);
  const byFinish = (a, b) => finishedAt(b) - finishedAt(a);
  return [
    { id: "active", tasks: tasks.filter(isActive).sort(byStart) },
    { id: "queued", tasks: tasks.filter(task => task.status === "queued").sort(byQueue) },
    { id: "failed", tasks: tasks.filter(task => task.status === "failed").sort(byFinish) },
    { id: "done", tasks: tasks.filter(task => task.status === "completed" || task.status === "cancelled").sort(byFinish) },
  ].filter(group => group.tasks.length);
}

// Running first, then waiting tasks in the order the scheduler will start them.
export function queueOrder(tasks) {
  return sortGroups(tasks, true).flatMap(group => group.tasks);
}

function factList(pairs, t) {
  const facts = element("dl", "facts");
  for (const [label, value] of pairs) {
    if (value == null || value === "") continue;
    const item = element("div", "fact");
    item.append(element("dt", "", t(label)), element("dd", "", String(value)));
    facts.append(item);
  }
  return facts.childElementCount ? facts : null;
}

function pathRow(label, value, actions) {
  const row = element("div", "path-row");
  const text = element("div", "path-copy");
  text.append(element("span", "path-label", label));
  const path = element("code", "path", value);
  path.title = value;
  text.append(path);
  const tools = element("div", "path-actions");
  tools.append(...actions);
  row.append(text, tools);
  return row;
}

class Row {
  constructor(key, owner) {
    this.key = key;
    this.owner = owner;
    this.node = element("li", "task-row");
    this.node.dataset.key = key;
    const line = element("div", "task-line");
    this.check = element("input", "task-check");
    this.check.type = "checkbox";
    this.check.addEventListener("click", event => owner.toggle(this, event.shiftKey));
    this.main = element("button", "task-main");
    this.main.type = "button";
    this.main.addEventListener("click", () => owner.handlers.onExpand(this.key));
    this.mark = icon("clock", "icon task-mark");
    const copy = element("span", "task-copy");
    this.title = element("span", "task-title");
    this.meta = element("span", "task-meta");
    this.metaStatus = element("span", "meta-status");
    this.metaDetail = element("span", "meta-detail");
    this.metaOrigin = element("span", "meta-origin");
    this.meta.append(this.metaStatus, this.metaDetail, this.metaOrigin);
    this.meter = element("span", "meter");
    this.meterFill = element("span", "meter-fill");
    this.meter.append(this.meterFill);
    copy.append(this.title, this.meta, this.meter);
    this.main.append(this.mark, copy);
    this.quick = iconButton("close", "", () => this.runQuick(), "task-quick");
    line.append(this.check, this.main, this.quick);
    this.details = element("div", "task-details");
    this.details.id = `details-${key.replace(/[^\w-]/g, "-")}`;
    this.details.hidden = true;
    this.main.setAttribute("aria-controls", this.details.id);
    this.node.append(line, this.details);
    this.percent = null;
    this.detailKey = "";
  }

  runQuick() {
    const { action, task } = this.quickState || {};
    if (!action) return;
    if (action === "reveal") this.owner.handlers.onReveal(task.result.filepath);
    else this.owner.handlers.onAction(action, [task]);
  }

  update(task, state) {
    const { ctx, selected, expanded, busy } = state;
    const { t } = ctx;
    this.task = task;
    // Most rows are idle between polls; skip their DOM work entirely.
    const signature = JSON.stringify([ctx.language, selected.has(this.key), expanded === this.key, busy, task]);
    if (signature === this.signature) return;
    this.signature = signature;
    const name = taskName(task, ctx);
    const status = statusInfo(task, t);
    const percent = isActive(task) && !task.postprocessing ? percentOf(task) : null;
    this.node.dataset.tone = status.tone;
    this.node.dataset.selected = String(selected.has(this.key));
    this.node.dataset.expanded = String(expanded === this.key);
    this.check.checked = selected.has(this.key);
    this.check.setAttribute("aria-label", t("selectTask", { name }));
    setIcon(this.mark, status.icon);
    this.mark.classList.toggle("spinning", status.icon === "spinner");
    setText(this.title, name);
    this.title.title = name;
    setText(this.metaStatus, percent == null ? status.text : `${status.text} ${task.progress.percent_text.trim()}`);
    const detail = rowDetail(task, ctx);
    setText(this.metaDetail, detail);
    setHidden(this.metaDetail, !detail);
    setText(this.metaOrigin, [platformName(task.platform, t), t(task.media_type)].filter(Boolean).join(" · "));
    setHidden(this.meter, percent == null);
    if (percent != null) {
      // Retries restart at zero; jump back instead of animating backwards.
      this.meterFill.dataset.instant = String(this.percent == null || percent < this.percent);
      this.meterFill.style.transform = `scaleX(${percent / 100})`;
    }
    this.percent = percent;
    this.main.setAttribute("aria-expanded", String(expanded === this.key));
    this.main.setAttribute("aria-label", [name, status.text, detail].filter(Boolean).join(", "));

    const quick = quickAction(task, ctx);
    this.quickState = quick && { ...quick, task };
    this.quick.hidden = !quick;
    if (quick) {
      setIcon(this.quick.firstElementChild, quick.icon);
      this.quick.setAttribute("aria-label", quick.label);
      this.quick.title = quick.label;
      this.quick.disabled = busy && quick.action !== "reveal";
      this.quick.dataset.action = quick.action;
    }
    this.renderDetails(task, state, expanded === this.key);
  }

  renderDetails(task, state, open) {
    if (!open) {
      if (!this.details.hidden) {
        this.details.hidden = true;
        this.details.replaceChildren();
        this.detailKey = "";
      }
      return;
    }
    const { ctx, busy } = state;
    // The manager mirrors live progress at the top level too; leave all of it to updateLive().
    const {
      progress, postprocessing, percent_text, speed_mbps, speed_text, eta_text,
      total_size_bytes, total_size_text, total_size_is_estimate, ...stable
    } = task;
    const key = JSON.stringify([ctx.language, busy, stable, Boolean(postprocessing)]);
    const opening = this.details.hidden;
    if (key !== this.detailKey) {
      const focused = this.details.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
      this.details.replaceChildren(this.buildDetails(task, ctx, busy));
      this.detailKey = key;
      if (focused) this.details.querySelector(`[data-focus-key="${focused}"]`)?.focus({ preventScroll: true });
    }
    this.updateLive(task, ctx);
    if (opening) {
      this.details.hidden = false;
      fadeIn(this.details);
    }
  }

  updateLive(task, ctx) {
    if (!this.live) return;
    const { t, language } = ctx;
    const stage = progressStage(task, language);
    setText(this.live.stage, stage || (task.status === "queued" ? t("waitSlot") : ""));
    setHidden(this.live.stage, !this.live.stage.textContent);
    const progress = task.progress || {};
    const values = {
      progress: progress.percent_text?.trim(), speed: localValue(progress.speed_text, language),
      eta: localValue(progress.eta_text, language), size: localValue(progress.total_size_text, language),
    };
    for (const [name, node] of Object.entries(this.live.facts)) {
      setText(node.lastElementChild, values[name] || "—");
    }
  }

  buildDetails(task, ctx, busy) {
    const { t, language } = ctx;
    const { handlers } = this.owner;
    const result = task.result || {};
    const fragment = document.createDocumentFragment();
    this.live = null;

    const actions = element("div", "detail-actions");
    for (const action of ["cancel", "retry", "redownload"]) {
      if (!task[`can_${action}`]) continue;
      const label = action === "redownload" && task.platform === "local" ? "reextract" : action;
      const control = button(t(label), () => handlers.onAction(action, [task]),
        action === "retry" ? "primary compact" : "secondary compact", action === "cancel" ? "close" : "retry");
      control.disabled = busy;
      control.dataset.focusKey = action;
      actions.append(control);
    }
    if (result.filepath) {
      const reveal = button(t("showOutput"), () => handlers.onReveal(result.filepath), "secondary compact", "folder");
      reveal.dataset.focusKey = "reveal";
      actions.append(reveal);
    }
    if (actions.childElementCount) fragment.append(actions);

    if (isActive(task) || task.status === "queued") {
      const live = element("div", "detail-live");
      const stage = element("p", "detail-stage");
      const facts = element("dl", "facts live-facts");
      const refs = {};
      for (const name of isActive(task) && task.platform !== "local" ? ["progress", "speed", "eta", "size"] : []) {
        const item = element("div", "fact");
        item.append(element("dt", "", t(name)), element("dd", "", "—"));
        facts.append(item);
        refs[name] = item;
      }
      live.append(stage);
      if (facts.childElementCount) live.append(facts);
      fragment.append(live);
      this.live = { stage, facts: refs };
      if (task.turbo_fallback) fragment.append(element("p", "detail-note", t("turboFallback")));
      if (task.status === "running_uninterruptible") fragment.append(element("p", "detail-note", t("turboBusy")));
    }

    if (task.error && task.status === "failed") {
      const parts = errorParts(task.error, language);
      const fix = ["youtube", "instagram", "bilibili"].includes(task.platform) || ERROR_FIXES[parts.code] === "folder"
        ? ERROR_FIXES[parts.code] : null;
      const fixButton = fix && button(t(fix === "cookies" ? "fixCookies" : "fixFolder", { platform: platformName(task.platform, t) }),
        () => handlers.onFix(fix, task), "secondary compact", fix === "cookies" ? "key" : "folder");
      if (fixButton) fixButton.dataset.focusKey = "fix";
      fragment.append(callout({ tone: "error", ...parts, actions: fixButton ? [fixButton] : [], codeLabel: t("errorCode") }));
    }

    const notes = [];
    if (result.audio_format_fallback) notes.push(t("formatFallback"));
    const trackStatus = { embedded: "embedded", partial: "partial", unavailable: "unavailableTracks" }[result.subtitle_status];
    if (trackStatus) notes.push(t(trackStatus));
    for (const warning of result.subtitle_warnings || []) {
      const track = {
        manual: "subtitles", automatic: "automatic", danmaku: "danmaku", subtitle_metadata: "subtitles",
        subtitle_embedding: "subtitles", mkv_remux: "format",
      }[String(warning).split(":")[0]];
      notes.push(track ? t("trackWarning", { track: t(track) }) : String(warning));
    }
    for (const note of notes) fragment.append(element("p", "detail-note", note));

    const paths = element("div", "detail-paths");
    if (result.filepath) {
      const copy = iconButton("copy", t("copyPath"), () => handlers.onCopy(result.filepath, "path"));
      copy.dataset.focusKey = "copy-path";
      paths.append(pathRow(t("output"), result.filepath, [copy]));
    }
    if (task.platform !== "local" && task.url) {
      const open = iconButton("external", t("openLink"), () => handlers.onOpenLink(task.url));
      open.dataset.focusKey = "open-link";
      const copy = iconButton("copy", t("copyLink"), () => handlers.onCopy(task.url, "link"));
      copy.dataset.focusKey = "copy-link";
      paths.append(pathRow(t("sourceLink"), task.url, [open, copy]));
    }
    if (paths.childElementCount) fragment.append(paths);

    const value = item => (item == null || item === "" ? "" : localValue(String(item), language));
    const sourceRate = Number.isFinite(Number(result.source_abr_kbps)) ? `${result.source_abr_kbps} kbps` : "";
    const media = factList([
      ["format", value(result.format)],
      ["resolution", value(result.resolution)],
      ["fps", Number.isFinite(Number(result.fps)) ? `${result.fps} fps` : value(result.fps)],
      ["videoCodec", value(result.vcodec)],
      ["audioCodec", value(result.acodec)],
      ["sourceCodec", [value(result.source_acodec), sourceRate].filter(Boolean).join(" · ")],
      ["size", value(result.filesize)],
      ["version", result.output_version_actual > 1 ? result.output_version_actual : ""],
    ], t);
    if (media) fragment.append(media);

    if (task.attempts?.length > 1 || (task.attempts?.length && isActive(task) === false && task.status !== "completed")) {
      const section = element("div", "detail-attempts");
      section.append(element("h4", "", t("attempts")));
      const list = element("ol", "attempt-list");
      for (const attempt of task.attempts) {
        const item = element("li", "attempt");
        item.dataset.status = attempt.status;
        const head = element("div", "attempt-head");
        head.append(element("strong", "", t("attemptTitle", { number: attempt.number })), element("span", "attempt-status", t(attempt.status)));
        const when = [formatDateTime(attempt.started_at, language)];
        if (attempt.finished_at && attempt.started_at) when.push(formatDuration(attempt.finished_at - attempt.started_at, language));
        else if (!attempt.finished_at) when.push(t("stillRunning"));
        if (attempt.output_version > 1) when.push(`${t("version")} ${attempt.output_version}`);
        item.append(head, element("span", "attempt-time", when.join(" · ")));
        if (attempt.error && attempt.number < task.attempt_count) {
          const parts = errorParts(attempt.error, language);
          item.append(element("span", "attempt-error", [parts.message, parts.code && `[${parts.code}]`].filter(Boolean).join(" ")));
        }
        list.append(item);
      }
      section.append(list);
      fragment.append(section);
    }
    return fragment;
  }
}

// A keyed, in-place task list: rows are reused across polls so hover, focus and progress transitions survive.
export class TaskList {
  constructor(root, handlers) {
    this.root = root;
    this.handlers = handlers;
    this.toolbar = element("div", "list-toolbar");
    this.body = element("div", "list-body");
    root.replaceChildren(this.toolbar, this.body);
    this.rows = new Map();
    this.groups = new Map();
    this.order = "";
    this.toolbarKey = "";
    this.lastToggled = "";
    this.visible = [];
    this.expanded = "";
    this.body.addEventListener("keydown", event => this.navigate(event));
  }

  toggle(row, range) {
    const checked = row.check.checked;
    if (range && this.lastToggled) {
      const keys = this.visible.map(taskKey);
      const from = keys.indexOf(this.lastToggled);
      const to = keys.indexOf(row.key);
      if (from >= 0 && to >= 0) {
        const [start, end] = from < to ? [from, to] : [to, from];
        this.handlers.onSelect(this.visible.slice(start, end + 1), checked);
        this.lastToggled = row.key;
        return;
      }
    }
    this.lastToggled = row.key;
    this.handlers.onSelect([row.task], checked);
  }

  navigate(event) {
    if (!event.target.classList?.contains("task-main") || event.altKey || event.ctrlKey || event.metaKey) return;
    const mains = [...this.body.querySelectorAll(".task-main")];
    const index = mains.indexOf(event.target);
    const next = { ArrowDown: index + 1, ArrowUp: index - 1, Home: 0, End: mains.length - 1 }[event.key];
    if (next == null || !mains[next]) return;
    event.preventDefault();
    mains[next].focus();
    mains[next].scrollIntoView({ block: "nearest" });
  }

  group(id, t) {
    let group = this.groups.get(id);
    if (!group) {
      const section = element("section", "task-group");
      section.dataset.group = id;
      const heading = element("h3", "group-heading");
      const label = element("span", "group-label");
      const count = element("span", "group-count");
      heading.append(label, count);
      const list = element("ul", "task-list");
      section.append(heading, list);
      group = { section, heading, label, count, list };
      this.groups.set(id, group);
    }
    setText(group.label, id === "all" ? "" : t(`section_${id}`));
    group.heading.hidden = id === "all";
    group.list.setAttribute("aria-label", id === "all" ? t("taskList") : t(`section_${id}`));
    return group;
  }

  renderToolbar(state, counts, visible) {
    const { ctx, selected, filter, busy, clearable } = state;
    const { t } = ctx;
    const chosen = visible.filter(task => selected.has(taskKey(task)));
    const key = JSON.stringify([ctx.language, counts, filter, busy, clearable, chosen.map(taskKey),
      chosen.map(task => [task.can_cancel, task.can_retry, task.can_redownload]), visible.length]);
    if (key === this.toolbarKey) return;
    this.toolbarKey = key;
    const focused = this.toolbar.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
    const nodes = [];
    const all = element("input", "task-check");
    all.type = "checkbox";
    all.dataset.focusKey = "select-all";
    all.setAttribute("aria-label", t("selectAllTasks"));
    all.checked = visible.length > 0 && chosen.length === visible.length;
    all.indeterminate = chosen.length > 0 && chosen.length < visible.length;
    all.disabled = !visible.length;
    all.addEventListener("change", () => this.handlers.onSelect(visible, all.checked));
    nodes.push(all);
    this.toolbar.dataset.mode = chosen.length ? "selection" : "filter";
    if (chosen.length) {
      nodes.push(element("span", "selection-count", t("selectedTasks", { count: chosen.length })));
      for (const [action, label, tone] of [["cancel", "cancelSelected", "secondary"], ["retry", "retrySelected", "primary"], ["redownload", "redownloadSelected", "secondary"]]) {
        const eligible = chosen.filter(task => task[`can_${action}`]);
        if (!eligible.length) continue;
        const control = button(`${t(label)} (${eligible.length})`, () => this.handlers.onAction(action, eligible), `${tone} compact`);
        control.disabled = busy;
        control.dataset.focusKey = action;
        nodes.push(control);
      }
      const clear = button(t("clearSelection"), () => this.handlers.onSelect(chosen, false), "ghost compact toolbar-end");
      clear.dataset.focusKey = "clear-selection";
      nodes.push(clear);
    } else {
      const chips = element("div", "chips");
      chips.setAttribute("role", "group");
      chips.setAttribute("aria-label", t("filterTasks"));
      for (const name of FILTERS) {
        if (name !== "all" && name !== filter && !counts[name]) continue;
        const chip = element("button", "chip");
        chip.type = "button";
        chip.dataset.focusKey = `filter-${name}`;
        chip.dataset.filter = name;
        chip.setAttribute("aria-pressed", String(filter === name));
        // The text node keeps the accessible name readable ("Failed 1"); flex gap handles spacing.
        chip.append(element("span", "", t(`filter_${name}`)), " ", element("span", "chip-count", String(counts[name])));
        chip.addEventListener("click", () => this.handlers.onFilter(name));
        chips.append(chip);
      }
      nodes.push(chips);
      if (clearable) {
        const clear = button(t("clearFinished"), () => this.handlers.onClearFinished(), "ghost compact toolbar-end");
        clear.title = t("clearFinishedHint");
        clear.dataset.focusKey = "clear-finished";
        nodes.push(clear);
      }
    }
    this.toolbar.replaceChildren(...nodes);
    if (focused) this.toolbar.querySelector(`[data-focus-key="${focused}"]`)?.focus({ preventScroll: true });
  }

  render(state) {
    const { tasks, ctx, filter, grouped, expanded, empty } = state;
    const counts = countTasks(tasks);
    const visibleTasks = tasks.filter(task => matches(task, filter));
    const groups = sortGroups(visibleTasks, grouped && filter === "all");
    this.visible = groups.flatMap(group => group.tasks);
    this.toolbar.hidden = !tasks.length;
    if (tasks.length) this.renderToolbar(state, counts, this.visible);

    if (!tasks.length || !this.visible.length) {
      this.order = "";
      const node = !tasks.length ? empty() : this.filteredEmpty(ctx);
      reconcile(this.body, [node]);
      for (const row of this.rows.values()) row.node.remove();
      this.rows.clear();
      return;
    }

    const live = new Set(this.visible.map(taskKey));
    for (const [key, row] of this.rows) if (!live.has(key)) this.rows.delete(key);
    const sections = [];
    const placements = [];
    for (const { id, tasks: members } of groups) {
      const group = this.group(id, ctx.t);
      setText(group.count, String(members.length));
      sections.push(group.section);
      const nodes = members.map(task => {
        const key = taskKey(task);
        let row = this.rows.get(key);
        if (!row) {
          row = new Row(key, this);
          this.rows.set(key, row);
        }
        row.update(task, state);
        return row.node;
      });
      placements.push([group.list, nodes]);
    }
    const order = JSON.stringify([filter, groups.map(group => [group.id, group.tasks.map(taskKey)])]);
    const moved = this.order && order !== this.order && state.animate !== false;
    const apply = () => {
      reconcile(this.body, sections);
      for (const [list, nodes] of placements) reconcile(list, nodes);
    };
    if (moved) flip([...this.body.querySelectorAll(".task-row")], apply);
    else apply();
    for (const id of [...this.groups.keys()]) if (!sections.includes(this.groups.get(id).section)) this.groups.delete(id);
    this.order = order;

    if (expanded && expanded !== this.expanded) {
      const row = this.rows.get(expanded);
      row?.node.scrollIntoView({ block: "nearest", behavior: reducedMotion() ? "auto" : "smooth" });
    }
    this.expanded = expanded;
  }

  filteredEmpty(ctx) {
    if (!this.filterEmpty) {
      this.filterEmpty = element("div", "empty-state compact");
      this.filterEmptyText = element("p", "");
      this.filterEmptyAction = button("", () => this.handlers.onFilter("all"), "ghost compact");
      this.filterEmpty.append(this.filterEmptyText, this.filterEmptyAction);
    }
    setText(this.filterEmptyText, ctx.t("noMatches"));
    setText(this.filterEmptyAction.lastElementChild, ctx.t("showAll"));
    return this.filterEmpty;
  }
}

export function emptyState({ iconName, title, hint, actions = [] }) {
  const node = element("div", "empty-state");
  const mark = element("span", "empty-mark");
  mark.append(icon(iconName));
  node.append(mark, element("p", "empty-title", title));
  if (hint) node.append(element("p", "empty-hint", hint));
  if (actions.length) {
    const row = element("div", "empty-actions");
    row.append(...actions);
    node.append(row);
  }
  return node;
}
