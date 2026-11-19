// Task rows shared by Downloads and Batches: a keyed list that reuses rows across polls (so hover, focus
// and progress transitions survive), inline details, row menus and the floating selection bar.
import { errorParts, localValue, progressStage } from "./strings.js";
import {
  EASE_OUT, button, callout, element, fadeIn, flip, formatClock, formatDateTime, formatDuration, icon,
  iconButton, isMac, reconcile, reducedMotion, setHidden, setIcon, setText,
} from "./ui.js";
import { openMenu, toggleMenu } from "./menu.js";

export const isActive = task => task.status === "running" || task.status === "running_uninterruptible";
export const isPending = task => isActive(task) || task.status === "queued";
export const taskKey = task => `${task.batch_id}/${task.id}`;
export const startedAt = task => task.attempts?.at(-1)?.started_at || 0;
export const finishedAt = task => task.attempts?.at(-1)?.finished_at || startedAt(task) || task.batch_created || 0;
export const byStart = (a, b) => startedAt(a) - startedAt(b);
export const byQueue = (a, b) => (a.batch_created || 0) - (b.batch_created || 0) || (a.position || 0) - (b.position || 0);
export const byFinish = (a, b) => finishedAt(b) - finishedAt(a);
const PLATFORMS = ["youtube", "instagram", "bilibili"];
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

// Errors with a known remedy link straight to the setting that fixes them.
export function fixFor(task) {
  if (task.status !== "failed" || !task.error) return null;
  const fix = ERROR_FIXES[errorParts(task.error, "en").code];
  return fix === "folder" || (fix === "cookies" && PLATFORMS.includes(task.platform)) ? fix : null;
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

// The same actions back the ⋯ button, right-clicks and the keyboard menu key.
export function taskMenu(task, ctx, handlers, { expanded = false, busy = false } = {}) {
  const { t } = ctx;
  const result = task.result || {};
  const items = [];
  if (result.filepath) {
    items.push(
      { label: t("showOutput"), icon: "folder", run: () => handlers.onReveal(result.filepath) },
      { label: t("copyPath"), icon: "copy", run: () => handlers.onCopy(result.filepath, "path") },
    );
  }
  if (task.platform !== "local" && task.url) {
    items.push(
      { type: "separator" },
      { label: t("openLink"), icon: "external", run: () => handlers.onOpenLink(task.url) },
      { label: t("copyLink"), icon: "link", run: () => handlers.onCopy(task.url, "link") },
    );
  }
  items.push({ type: "separator" });
  if (task.can_retry) items.push({ label: t("retry"), icon: "retry", disabled: busy, run: () => handlers.onAction("retry", [task]) });
  if (task.can_redownload) {
    items.push({ label: t(task.platform === "local" ? "reextract" : "redownload"), icon: "retry", disabled: busy, run: () => handlers.onAction("redownload", [task]) });
  }
  if (task.can_cancel) items.push({ label: t("cancelDownload"), icon: "close", danger: true, disabled: busy, run: () => handlers.onAction("cancel", [task]) });
  if (task.status === "failed" && handlers.onDismiss) {
    const dismissed = handlers.isDismissed(taskKey(task));
    items.push({ label: t(dismissed ? "restoreTask" : "dismissTask"), icon: dismissed ? "undo" : "eye-off", run: () => handlers.onDismiss([task], !dismissed) });
  }
  items.push({ type: "separator" });
  if (handlers.onGoToBatch) items.push({ label: t("goToBatch"), icon: "layers", run: () => handlers.onGoToBatch(task.batch_id) });
  items.push({ label: t(expanded ? "hideDetails" : "showDetails"), icon: "info", run: () => handlers.onExpand(taskKey(task)) });
  return items;
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
    this.check.addEventListener("click", event => owner.toggle(this, event.shiftKey, this.check.checked));
    this.main = element("button", "task-main");
    this.main.type = "button";
    this.main.addEventListener("click", event => {
      // Desktop list conventions: ⌘/Ctrl-click adds to the selection, Shift-click selects a range.
      if (isMac ? event.metaKey : event.ctrlKey) owner.toggle(this, false, !this.selected);
      else if (event.shiftKey && owner.lastToggled) owner.toggle(this, true, true);
      else owner.handlers.onExpand(this.key);
    });
    this.mark = icon("clock", "icon task-mark");
    const copy = element("span", "task-copy");
    this.title = element("span", "task-title");
    this.meta = element("span", "task-meta");
    this.metaStatus = element("span", "meta-status");
    this.metaDetail = element("span", "meta-detail");
    this.metaOrigin = element("span", "meta-origin");
    this.metaTime = element("span", "meta-time");
    this.meta.append(this.metaStatus, this.metaDetail, this.metaOrigin, this.metaTime);
    this.meter = element("span", "meter");
    this.meterFill = element("span", "meter-fill");
    this.meter.append(this.meterFill);
    copy.append(this.title, this.meta, this.meter);
    this.main.append(this.mark, copy);
    this.quick = iconButton("close", "", () => this.runQuick(), "task-quick");
    this.more = iconButton("more", "", () => this.openMenu(), "task-more");
    this.more.setAttribute("aria-haspopup", "menu");
    this.more.setAttribute("aria-expanded", "false");
    line.append(this.check, this.main, this.quick, this.more);
    line.addEventListener("contextmenu", event => {
      if (event.target === this.check) return;
      event.preventDefault();
      this.openMenu({ x: event.clientX, y: event.clientY });
    });
    this.details = element("div", "task-details");
    this.details.id = `details-${key.replace(/[^\w-]/g, "-")}`;
    this.details.hidden = true;
    this.main.setAttribute("aria-controls", this.details.id);
    this.node.append(line, this.details);
    this.percent = null;
    this.detailKey = "";
    this.selected = false;
  }

  runQuick() {
    const { action, task } = this.quickState || {};
    if (!action) return;
    if (action === "reveal") this.owner.handlers.onReveal(task.result.filepath);
    else this.owner.handlers.onAction(action, [task]);
  }

  // Right-clicks open at the pointer; the menu key opens beside the row; both hand focus back to the
  // row itself. The ⋯ button toggles its own menu and keeps focus on the button.
  openMenu(point, fromKeyboard = false) {
    const { ctx, expanded, busy } = this.owner.input;
    const build = () => ({
      items: taskMenu(this.task, ctx, this.owner.handlers, { expanded: expanded === this.key, busy }),
      label: ctx.t("moreFor", { name: taskName(this.task, ctx) }),
      align: "end",
    });
    if (point) openMenu({ point, returnFocus: this.main, ...build() });
    else if (fromKeyboard) openMenu({ anchor: this.more, returnFocus: this.main, ...build() });
    else toggleMenu(this.more, build);
  }

  update(task, input) {
    const { ctx, selected, expanded, busy } = input;
    const { t } = ctx;
    this.task = task;
    this.selected = selected.has(this.key);
    // Most rows are idle between polls; skip their DOM work entirely.
    const signature = JSON.stringify([ctx.language, this.selected, expanded === this.key, busy, task]);
    if (signature === this.signature) return;
    this.signature = signature;
    const name = taskName(task, ctx);
    const status = statusInfo(task, t);
    const percent = isActive(task) && !task.postprocessing ? percentOf(task) : null;
    this.node.dataset.tone = status.tone;
    this.node.dataset.selected = String(this.selected);
    this.node.dataset.expanded = String(expanded === this.key);
    this.check.checked = this.selected;
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
    const time = isPending(task) ? "" : formatClock(finishedAt(task), ctx.language);
    setText(this.metaTime, time);
    setHidden(this.metaTime, !time);
    setHidden(this.meter, percent == null);
    if (percent != null) {
      // Retries restart at zero; jump back instead of animating backwards.
      this.meterFill.dataset.instant = String(this.percent == null || percent < this.percent);
      this.meterFill.style.transform = `scaleX(${percent / 100})`;
    }
    this.percent = percent;
    this.main.setAttribute("aria-expanded", String(expanded === this.key));
    this.main.setAttribute("aria-label", [name, status.text, detail].filter(Boolean).join(", "));
    const moreLabel = t("moreFor", { name });
    this.more.setAttribute("aria-label", moreLabel);
    this.more.title = t("moreActions");

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
    this.renderDetails(task, input, expanded === this.key);
  }

  renderDetails(task, input, open) {
    if (!open) {
      if (!this.details.hidden) {
        this.details.hidden = true;
        this.details.replaceChildren();
        this.detailKey = "";
        this.live = null;
      }
      return;
    }
    const { ctx, busy } = input;
    // The manager mirrors live progress at the top level too; leave all of it to updateLive().
    const {
      progress, postprocessing, percent_text, speed_mbps, speed_text, eta_text,
      total_size_bytes, total_size_text, total_size_is_estimate, ...stable
    } = task;
    const key = JSON.stringify([ctx.language, busy, stable, Boolean(postprocessing), this.owner.handlers.batchLabel?.(task) || ""]);
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
    for (const [name, node] of Object.entries(this.live.facts)) setText(node.lastElementChild, values[name] || "—");
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

    if (isPending(task)) {
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
      const fix = fixFor(task);
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

    const batch = handlers.batchLabel?.(task);
    if (batch && handlers.onGoToBatch) {
      const row = element("div", "detail-batch");
      row.append(icon("layers"), element("span", "detail-batch-label", t("partOfBatch")));
      const link = element("button", "link-button", batch);
      link.type = "button";
      link.dataset.focusKey = "go-to-batch";
      link.addEventListener("click", () => handlers.onGoToBatch(task.batch_id));
      row.append(link);
      fragment.append(row);
    }

    if (task.attempts?.length > 1 || (task.attempts?.length && !isActive(task) && task.status !== "completed")) {
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

export class TaskList {
  constructor(root, handlers) {
    this.root = root;
    this.handlers = handlers;
    this.body = element("div", "list-body");
    this.moreButton = button("", () => handlers.onMore?.(), "secondary compact show-more");
    this.moreButton.dataset.focusKey = "show-more";
    root.replaceChildren(this.body);
    this.rows = new Map();
    this.groups = new Map();
    this.order = "";
    this.lastToggled = "";
    this.visible = [];
    this.expanded = "";
    this.input = null;
    this.rendered = false;
    this.body.addEventListener("keydown", event => this.onKeydown(event));
    // Space selects instead of expanding; buttons fire their click on keyup, so stop that too.
    this.body.addEventListener("keyup", event => {
      if (event.key === " " && event.target.classList?.contains("task-main")) event.preventDefault();
    });
  }

  toggle(row, range, checked) {
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

  onKeydown(event) {
    if (!event.target.classList?.contains("task-main")) return;
    const row = this.rows.get(event.target.closest(".task-row")?.dataset.key);
    const modifier = isMac ? event.metaKey : event.ctrlKey;
    if (modifier && event.key.toLowerCase() === "a") {
      event.preventDefault();
      this.handlers.onSelect(this.visible, true);
      return;
    }
    if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
      event.preventDefault();
      row?.openMenu(null, true);
      return;
    }
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === " " && row) {
      event.preventDefault();
      this.toggle(row, event.shiftKey, !row.selected);
      return;
    }
    if (event.key === "Escape") {
      if (this.expanded) {
        event.preventDefault();
        this.handlers.onExpand(this.expanded);
      } else if (this.input?.selected.size) {
        event.preventDefault();
        this.handlers.onClearSelection?.();
      }
      return;
    }
    const mains = [...this.body.querySelectorAll(".task-main")];
    const index = mains.indexOf(event.target);
    const next = { ArrowDown: index + 1, ArrowUp: index - 1, Home: 0, End: mains.length - 1 }[event.key];
    if (next == null || !mains[next]) return;
    event.preventDefault();
    mains[next].focus();
    mains[next].scrollIntoView({ block: "nearest" });
  }

  group(spec, t) {
    let group = this.groups.get(spec.id);
    if (!group) {
      const section = element("section", "task-group");
      section.dataset.group = spec.id;
      const heading = element("div", "group-heading");
      const check = element("input", "task-check group-check");
      check.type = "checkbox";
      check.addEventListener("change", () => this.handlers.onSelect(group.tasks, check.checked));
      const label = element("h3", "group-label");
      const count = element("span", "group-count");
      const actions = element("div", "group-actions");
      heading.append(check, label, count, actions);
      const list = element("ul", "task-list");
      section.append(heading, list);
      group = { section, heading, check, label, count, actions, list, actionKey: "", tasks: [] };
      this.groups.set(spec.id, group);
    }
    setText(group.label, spec.label || "");
    group.heading.hidden = !spec.label;
    group.list.setAttribute("aria-label", spec.label || t("taskList"));
    group.check.setAttribute("aria-label", t("selectGroup", { group: spec.label || t("taskList") }));
    const actionKey = JSON.stringify([(spec.actions || []).map(action => [action.label, action.disabled])]);
    if (actionKey !== group.actionKey) {
      group.actionKey = actionKey;
      const focused = group.actions.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
      group.actions.replaceChildren(...(spec.actions || []).map((action, index) => {
        const control = button(action.label, action.run, "ghost compact", action.icon);
        control.disabled = Boolean(action.disabled);
        control.dataset.focusKey = `group-action-${index}`;
        return control;
      }));
      if (focused) group.actions.querySelector(`[data-focus-key="${focused}"]`)?.focus({ preventScroll: true });
    }
    return group;
  }

  // groups: [{id, label, tasks, total, actions}]; rows past `limit` are left for "Show more".
  render(input) {
    this.input = input;
    const { groups, ctx, selected, expanded, limit = Infinity, empty } = input;
    const total = groups.reduce((sum, group) => sum + group.tasks.length, 0);
    let budget = limit;
    const shown = [];
    for (const spec of groups) {
      if (budget <= 0) break;
      const tasks = spec.tasks.slice(0, budget);
      budget -= tasks.length;
      if (tasks.length) shown.push({ ...spec, visibleTasks: tasks });
    }
    this.visible = shown.flatMap(group => group.visibleTasks);
    this.root.dataset.selecting = String(selected.size > 0);

    if (!this.visible.length) {
      this.order = "";
      reconcile(this.body, [empty()]);
      for (const row of this.rows.values()) row.node.remove();
      this.rows.clear();
      this.groups.clear();
      this.rendered = true;
      return;
    }

    const live = new Set(this.visible.map(taskKey));
    for (const key of [...this.rows.keys()]) if (!live.has(key)) this.rows.delete(key);
    const sections = [];
    const placements = [];
    const created = [];
    for (const spec of shown) {
      const group = this.group(spec, ctx.t);
      group.tasks = spec.visibleTasks;
      setText(group.count, String(spec.total ?? spec.tasks.length));
      const chosen = spec.visibleTasks.filter(task => selected.has(taskKey(task))).length;
      group.check.checked = chosen > 0 && chosen === spec.visibleTasks.length;
      group.check.indeterminate = chosen > 0 && chosen < spec.visibleTasks.length;
      sections.push(group.section);
      const nodes = spec.visibleTasks.map(task => {
        const key = taskKey(task);
        let row = this.rows.get(key);
        if (!row) {
          row = new Row(key, this);
          this.rows.set(key, row);
          if (this.rendered && input.fresh && task.batch_id === input.fresh) created.push(row);
        }
        row.update(task, input);
        return row.node;
      });
      placements.push([group.list, nodes]);
    }
    const remaining = total - this.visible.length;
    if (remaining > 0) {
      setText(this.moreButton.lastElementChild, ctx.t("showMore", { count: Math.min(remaining, input.pageSize || remaining), total: remaining }));
      sections.push(this.moreButton);
    }
    const order = JSON.stringify(shown.map(group => [group.id, group.visibleTasks.map(taskKey)]));
    const moved = this.order && order !== this.order && input.animate !== false;
    const apply = () => {
      reconcile(this.body, sections);
      for (const [list, nodes] of placements) reconcile(list, nodes);
    };
    if (moved) flip([...this.body.querySelectorAll(".task-row")], apply);
    else apply();
    for (const [id, group] of [...this.groups]) if (!sections.includes(group.section)) this.groups.delete(id);
    this.order = order;
    for (const row of created) fadeIn(row.node, { y: -6, duration: 260 });

    if (expanded && expanded !== this.expanded) {
      this.rows.get(expanded)?.node.scrollIntoView({ block: "nearest", behavior: reducedMotion() ? "auto" : "smooth" });
    }
    this.expanded = expanded;
    this.rendered = true;
  }

  focusFirst() {
    this.body.querySelector(".task-main")?.focus();
  }
}

// Bulk actions float over the list while anything is selected, so the list itself never shifts.
export class SelectionBar {
  constructor(root, handlers) {
    this.root = root;
    this.handlers = handlers;
    this.key = "";
    root.setAttribute("role", "toolbar");
    root.hidden = true;
  }

  render({ ctx, chosen, visible, busy, dismissable = false, isDismissed = () => false }) {
    const { t } = ctx;
    const show = chosen.length > 0;
    if (!show) {
      this.hide();
      return;
    }
    const groups = [
      ["cancel", "cancelSelected", "secondary", chosen.filter(task => task.can_cancel)],
      ["retry", "retrySelected", "primary", chosen.filter(task => task.can_retry)],
      ["redownload", "redownloadSelected", "secondary", chosen.filter(task => task.can_redownload)],
    ];
    const dismiss = dismissable ? chosen.filter(task => task.status === "failed" && !isDismissed(taskKey(task))) : [];
    const key = JSON.stringify([ctx.language, chosen.map(taskKey), groups.map(group => group[3].length), dismiss.length, visible.length, busy]);
    this.root.setAttribute("aria-label", t("selectionActions"));
    if (key !== this.key) {
      this.key = key;
      const focused = this.root.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
      const nodes = [element("span", "selection-count", t("selectedTasks", { count: chosen.length }))];
      const actions = element("div", "selection-actions");
      for (const [action, label, tone, eligible] of groups) {
        if (!eligible.length) continue;
        const control = button(t(label, { count: eligible.length }), () => this.handlers.onAction(action, eligible), `${tone} compact`);
        control.disabled = busy;
        control.dataset.focusKey = action;
        actions.append(control);
      }
      if (dismiss.length) {
        const control = button(t("dismissSelected", { count: dismiss.length }), () => this.handlers.onDismiss(dismiss, true), "secondary compact", "eye-off");
        control.dataset.focusKey = "dismiss";
        actions.append(control);
      }
      nodes.push(actions);
      if (chosen.length < visible.length) {
        const all = element("button", "link-button", t("selectAllCount", { count: visible.length }));
        all.type = "button";
        all.dataset.focusKey = "select-all";
        all.addEventListener("click", () => this.handlers.onSelect(visible, true));
        nodes.push(all);
      }
      const clear = iconButton("close", t("clearSelection"), () => this.handlers.onClearSelection(), "selection-clear");
      clear.dataset.focusKey = "clear";
      nodes.push(clear);
      this.root.replaceChildren(...nodes);
      if (focused) this.root.querySelector(`[data-focus-key="${focused}"]`)?.focus({ preventScroll: true });
    }
    this.showBar();
  }

  showBar() {
    clearTimeout(this.timer);
    this.animation?.cancel();
    if (!this.root.hidden && !this.root.dataset.leaving) return;
    delete this.root.dataset.leaving;
    this.root.hidden = false;
    document.body.dataset.selecting = "true";
    if (this.root.animate && document.visibilityState === "visible") {
      this.root.animate(reducedMotion()
        ? [{ opacity: 0 }, { opacity: 1 }]
        : [{ opacity: 0, transform: "translate(-50%, 10px)" }, { opacity: 1, transform: "translate(-50%, 0)" }],
      { duration: 220, easing: EASE_OUT });
    }
  }

  hide() {
    if (this.root.hidden || this.root.dataset.leaving) return;
    this.key = "";
    delete document.body.dataset.selecting;
    const done = () => {
      if (!this.root.dataset.leaving) return;
      delete this.root.dataset.leaving;
      this.root.hidden = true;
      this.root.replaceChildren();
    };
    this.root.dataset.leaving = "true";
    if (!this.root.animate || reducedMotion() || document.visibilityState !== "visible") {
      done();
      return;
    }
    this.animation = this.root.animate(
      [{ opacity: 1, transform: "translate(-50%, 0)" }, { opacity: 0, transform: "translate(-50%, 6px)" }],
      { duration: 140, easing: EASE_OUT, fill: "forwards" },
    );
    this.animation.onfinish = done;
    this.timer = setTimeout(done, 400);
  }
}

export function emptyState({ iconName, title, hint, actions = [], className = "" }) {
  const node = element("div", `empty-state ${className}`.trim());
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
