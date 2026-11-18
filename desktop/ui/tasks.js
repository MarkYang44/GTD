import { formatError, progressStage } from "./strings.js";

export const isActive = task => ["running", "running_uninterruptible"].includes(task.status);
export const taskKey = task => `${task.batch_id}/${task.id}`;

export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

export function button(text, click, tone = "subdued") {
  const node = element("button", `button ${tone}`, text);
  node.type = "button";
  node.addEventListener("click", click);
  return node;
}

export function taskName(task, t) {
  return task.result?.title || task.title || (task.platform === "local" ? t("local") : task.url) || t("unknown");
}

export function platformName(platform, t) {
  return { youtube: "YouTube", instagram: "Instagram", bilibili: "Bilibili", local: t("local") }[platform] || platform;
}

export function statusText(task, t) {
  if (isActive(task) && task.platform === "local") return t("extracting");
  if (isActive(task) && task.postprocessing) return t("processing");
  return t(task.status || "unknown");
}

function badge(task, t) {
  const node = element("span", "badge", statusText(task, t));
  node.dataset.status = task.status;
  return node;
}

function checkbox(label, key, change) {
  const input = document.createElement("input");
  input.type = "checkbox";
  input.setAttribute("aria-label", label);
  input.dataset.focusKey = key;
  input.addEventListener("change", () => change(input.checked));
  return input;
}

export function empty(text, hint) {
  const state = element("div", "empty-state");
  state.append(element("p", "", text));
  if (hint) state.append(element("p", "muted small", hint));
  return state;
}

function taskProgress(task, t) {
  const progress = task.progress || {};
  const sourcePercent = progress.percent_text?.trim();
  const percent = Number.parseFloat(sourcePercent);
  const result = element("div", "task-progress");
  if (isActive(task) && Number.isFinite(percent)) {
    const meter = element("progress");
    meter.max = 100;
    meter.value = Math.max(0, Math.min(100, percent));
    meter.setAttribute("aria-label", `${t("progress")} · ${taskName(task, t)}`);
    const line = element("div", "progress-line");
    line.append(meter, element("span", "small", sourcePercent));
    result.append(line);
  }
  const eta = metricText(progress.eta_text, t);
  const telemetry = isActive(task) && [metricText(progress.speed_text, t), eta && `${t("eta")} ${eta}`].filter(Boolean);
  if (telemetry?.length) result.append(element("p", "muted small", telemetry.join(" · ")));
  if (!result.childElementCount) result.append(element("span", "muted", "—"));
  return result;
}

function matches(task, filter) {
  return filter === "all" || (filter === "active" ? isActive(task) : task.status === filter);
}

function tableControls(rows, options) {
  const { t, selected, filter, onFilter, busy, onAction } = options;
  const toolbar = element("div", "table-toolbar");
  const chosen = rows.filter(task => selected.has(taskKey(task)));
  const filterInput = element("select", "status-filter");
  filterInput.setAttribute("aria-label", t("filterTasks"));
  filterInput.dataset.focusKey = "filter";
  for (const status of ["all", "active", "queued", "completed", "failed", "cancelled"]) {
    const option = element("option", "", t(status === "all" ? "allTasks" : status));
    option.value = status;
    filterInput.append(option);
  }
  filterInput.value = filter;
  filterInput.addEventListener("change", () => onFilter(filterInput.value));
  toolbar.append(filterInput);
  if (chosen.length) {
    toolbar.append(element("span", "muted small", t("selectedTasks", { count: chosen.length })));
    for (const [action, label] of [["cancel", "cancelSelected"], ["retry", "retrySelected"], ["redownload", "redownloadSelected"]]) {
      const eligible = chosen.filter(task => task[`can_${action}`]);
      if (!eligible.length) continue;
      const control = button(t(label), () => onAction(action, eligible));
      control.disabled = busy;
      control.dataset.focusKey = action;
      toolbar.append(control);
    }
  }
  return toolbar;
}

export function renderTable(container, tasks, options) {
  const { t, selected, focused, filter, onSelect, onFocus, hasBatch, view } = options;
  const rows = tasks.filter(task => matches(task, filter));
  const focusedControl = container.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
  const root = document.createDocumentFragment();
  if (tasks.length) root.append(tableControls(rows, options));
  if (!rows.length) {
    if (filter !== "all" && tasks.length) root.append(empty(t("noMatches")));
    else if (view === "queue") root.append(empty(t("queueEmpty"), t("queueEmptyHint")));
    else root.append(empty(t(hasBatch ? "noMatches" : "noBatches")));
  } else {
    const wrap = element("div", "table-wrap");
    const table = element("table", "task-table");
    const header = table.createTHead().insertRow();
    const body = table.createTBody();
    const all = checkbox(t("selectAllTasks"), "select-all", checked => onSelect(rows, checked));
    const selectedCount = rows.filter(task => selected.has(taskKey(task))).length;
    all.checked = selectedCount === rows.length;
    all.indeterminate = selectedCount > 0 && !all.checked;
    for (const label of [all, t("task"), t("status"), t("progress")]) {
      const column = element("th");
      column.scope = "col";
      column.append(label);
      header.append(column);
    }
    for (const task of rows) {
      const row = body.insertRow();
      const name = taskName(task, t);
      const key = taskKey(task);
      const choice = checkbox(t("selectTask", { name }), `select-${key}`, checked => onSelect([task], checked));
      choice.checked = selected.has(key);
      row.dataset.focused = key === focused;
      row.insertCell().append(choice);
      const info = row.insertCell();
      const nameButton = button(name, () => onFocus(key), "task-name");
      nameButton.title = name;
      nameButton.dataset.focusKey = `details-${key}`;
      nameButton.setAttribute("aria-pressed", String(key === focused));
      info.append(nameButton, element("div", "muted small", [platformName(task.platform, t), t(task.media_type)].filter(Boolean).join(" · ")));
      row.insertCell().append(badge(task, t));
      row.insertCell().append(taskProgress(task, t));
    }
    wrap.append(table);
    root.append(wrap);
  }

  container.replaceChildren(root);
  if (focusedControl) {
    [...container.querySelectorAll("[data-focus-key]")].find(node => node.dataset.focusKey === focusedControl)?.focus({ preventScroll: true });
  }
}

export function formatTime(timestamp, language) {
  return timestamp ? new Date(timestamp * 1000).toLocaleString(language === "zh" ? "zh-CN" : "en-US", {
    dateStyle: "medium", timeStyle: "short",
  }) : "—";
}

function appendFacts(parent, pairs, t) {
  const facts = element("dl", "task-facts");
  for (const [label, value] of pairs) {
    if (value != null && value !== "") facts.append(element("dt", "", t(label)), element("dd", "", value));
  }
  if (facts.childElementCount) parent.append(facts);
}

function metricText(value, t) {
  return value === "计算中" ? "…" : value === "未知" ? t("unknown") : value;
}

export function renderInspector(container, task, options) {
  const { t, language, busy, onAction, onReveal } = options;
  const heading = element("h2", "", t("details"));
  if (!task) {
    container.replaceChildren(heading, element("p", "muted", t("noDetails")));
    return;
  }
  const result = task.result || {};
  const fragment = document.createDocumentFragment();
  const taskTitle = element("p", "inspector-title", taskName(task, t));
  fragment.append(heading, taskTitle, badge(task, t));

  if (task.status === "queued") fragment.append(element("p", "muted small", t("waitSlot")));
  if (isActive(task)) {
    const stage = progressStage(task, language);
    if (stage) fragment.append(element("p", "muted small", stage));
    if (language === "zh" && task.postprocessing?.detail_text) {
      fragment.append(element("p", "muted small", task.postprocessing.detail_text));
    }
    if (task.turbo_fallback) fragment.append(element("p", "muted small", t("turboFallback")));
    if (task.status === "running_uninterruptible") fragment.append(element("p", "muted small", t("turboBusy")));
    appendFacts(fragment, [
      ["progress", task.progress?.percent_text],
      ["speed", metricText(task.progress?.speed_text, t)],
      ["eta", metricText(task.progress?.eta_text, t)],
      ["size", metricText(task.progress?.total_size_text, t)],
    ], t);
  }

  if (task.error) fragment.append(element("p", "notice", formatError(task.error, language)));
  appendFacts(fragment, [
    ["sourceLink", task.platform !== "local" ? task.url : null],
    ["format", result.format],
    ["resolution", result.resolution],
    ["videoCodec", result.vcodec],
    ["audioCodec", result.acodec],
    ["sourceCodec", [result.source_acodec, result.source_abr_kbps && `${result.source_abr_kbps} kbps`].filter(Boolean).join(" · ")],
    ["fps", result.fps],
    ["size", result.filesize],
    ["version", result.output_version_actual],
    ["output", result.filepath],
  ], t);
  if (result.audio_format_fallback) fragment.append(element("p", "muted small", t("formatFallback")));
  const trackStatus = { embedded: "embedded", partial: "partial", unavailable: "unavailableTracks" }[result.subtitle_status];
  if (trackStatus) fragment.append(element("p", "muted small", t(trackStatus)));
  for (const warning of result.subtitle_warnings || []) {
    const track = { manual: "subtitles", automatic: "automatic", danmaku: "danmaku", subtitle_metadata: "subtitles", subtitle_embedding: "subtitles", mkv_remux: "format" }[String(warning).split(":")[0]];
    fragment.append(element("p", "muted small", track ? t("trackWarning", { track: t(track) }) : warning));
  }

  const controls = element("div", "inline-actions");
  for (const action of ["cancel", "retry", "redownload"]) {
    if (!task[`can_${action}`]) continue;
    const key = action === "redownload" && task.platform === "local" ? "reextract" : action;
    const control = button(t(key), () => onAction(action, [task]));
    control.disabled = busy;
    control.dataset.focusKey = action;
    controls.append(control);
  }
  if (result.filepath) {
    const reveal = button(t("showOutput"), () => onReveal(result.filepath));
    reveal.dataset.focusKey = "reveal";
    controls.append(reveal);
  }
  if (controls.childElementCount) fragment.append(controls);

  if (task.attempts?.length) {
    fragment.append(element("h3", "", t("attempts")));
    const attempts = element("ol", "attempt-list");
    for (const attempt of task.attempts) {
      const item = element("li");
      item.append(element("strong", "", `#${attempt.number} · ${t(attempt.status)}`));
      const times = [formatTime(attempt.started_at, language)];
      if (attempt.finished_at) times.push(formatTime(attempt.finished_at, language));
      item.append(element("span", "muted small", times.join(" → ")));
      if (attempt.output_version > 1) item.append(element("span", "muted small", `${t("version")} ${attempt.output_version}`));
      if (attempt.error && attempt.number < task.attempt_count) item.append(element("span", "muted small", formatError(attempt.error, language)));
      attempts.append(item);
    }
    fragment.append(attempts);
  }

  const focusedControl = container.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
  container.replaceChildren(fragment);
  if (focusedControl) container.querySelector(`[data-focus-key="${focusedControl}"]`)?.focus({ preventScroll: true });
}
