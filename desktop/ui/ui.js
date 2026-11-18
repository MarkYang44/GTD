// Small DOM toolkit shared by every view: icons, keyed reconciliation, motion, toasts.
export const $ = id => document.getElementById(id);
export const EASE_OUT = "cubic-bezier(0.23, 1, 0.32, 1)";
export const EASE_IN_OUT = "cubic-bezier(0.77, 0, 0.175, 1)";
export const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
const SVG = "http://www.w3.org/2000/svg";
const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
export const reducedMotion = () => motionQuery.matches;
// Minimized windows freeze animations; changes made then should simply appear on return.
const quietMotion = () => reducedMotion() || document.visibilityState !== "visible";

export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

export function icon(name, className = "icon") {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", className);
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const use = document.createElementNS(SVG, "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

export function setIcon(svg, name) {
  const use = svg.firstElementChild;
  if (use.getAttribute("href") !== `#i-${name}`) use.setAttribute("href", `#i-${name}`);
}

export function button(text, click, tone = "secondary", iconName) {
  const node = element("button", `button ${tone}`);
  node.type = "button";
  if (iconName) node.append(icon(iconName));
  node.append(element("span", "", text));
  if (click) node.addEventListener("click", click);
  return node;
}

export function iconButton(name, label, click, className = "") {
  const node = element("button", `icon-button ${className}`.trim());
  node.type = "button";
  node.setAttribute("aria-label", label);
  node.title = label;
  node.append(icon(name));
  if (click) node.addEventListener("click", click);
  return node;
}

// An inline message with a headline, an optional fix, its error code and follow-up actions.
export function callout({ tone = "error", message, suggestion, code, actions = [], codeLabel = "Error code" }) {
  const node = element("div", "callout");
  node.dataset.tone = tone;
  fillCallout(node, { tone, message, suggestion, code, actions, codeLabel });
  return node;
}

export function fillCallout(node, { tone = "error", message, suggestion, code, actions = [], codeLabel = "Error code" }) {
  node.dataset.tone = tone;
  const glyph = { error: "alert", warning: "alert", ok: "check-circle" }[tone] || "info";
  const body = element("div", "callout-body");
  body.append(element("p", "callout-title", message));
  if (suggestion) body.append(element("p", "callout-text", suggestion));
  if (code || actions.length) {
    const foot = element("div", "callout-foot");
    if (code) {
      const chip = element("code", "code-chip", code);
      chip.title = codeLabel;
      foot.append(chip);
    }
    foot.append(...actions);
    body.append(foot);
  }
  node.replaceChildren(icon(glyph, "icon callout-icon"), body);
}

export function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

export function setHidden(node, hidden) {
  if (node.hidden !== hidden) node.hidden = hidden;
}

// Make `container` hold exactly `nodes`, in order, moving existing nodes instead of recreating them.
export function reconcile(container, nodes) {
  const active = container.contains(document.activeElement) ? document.activeElement : null;
  const wanted = new Set(nodes);
  for (const child of [...container.children]) if (!wanted.has(child)) child.remove();
  let cursor = container.firstElementChild;
  for (const node of nodes) {
    if (node === cursor) {
      cursor = cursor.nextElementSibling;
      continue;
    }
    container.insertBefore(node, cursor);
  }
  // Moving a node drops its focus; restore it so polling never steals the keyboard position.
  if (active?.isConnected && document.activeElement !== active) active.focus({ preventScroll: true });
}

// Animate items that changed position during `mutate` (FLIP), so reordering stays legible.
export function flip(items, mutate) {
  if (quietMotion()) {
    mutate();
    return;
  }
  const before = new Map();
  const viewport = window.innerHeight;
  for (const item of items) {
    const box = item.getBoundingClientRect();
    if (box.bottom > -80 && box.top < viewport + 80) before.set(item, box.top);
  }
  mutate();
  for (const [item, top] of before) {
    if (!item.isConnected) continue;
    const delta = top - item.getBoundingClientRect().top;
    if (Math.abs(delta) < 2) continue;
    item.animate([{ transform: `translateY(${delta}px)` }, { transform: "none" }], { duration: 260, easing: EASE_IN_OUT });
  }
}

export function fadeIn(node, { y = -4, duration = 200 } = {}) {
  if (!node.animate || document.visibilityState !== "visible") return;
  const keyframes = reducedMotion()
    ? [{ opacity: 0 }, { opacity: 1 }]
    : [{ opacity: 0, transform: `translateY(${y}px)` }, { opacity: 1, transform: "none" }];
  node.animate(keyframes, { duration, easing: EASE_OUT });
}

export function flash(node) {
  node.classList.remove("flash");
  void node.offsetWidth;
  node.classList.add("flash");
  node.addEventListener("animationend", () => node.classList.remove("flash"), { once: true });
}

const closingAnimations = new WeakMap();

export function openDialog(dialog) {
  // A close still animating (or paused while the window is hidden) must not shut the new session.
  const closing = closingAnimations.get(dialog);
  if (closing) {
    clearTimeout(closing.timer);
    closing.animation.onfinish = null;
    closing.animation.cancel();
    closingAnimations.delete(dialog);
    delete dialog.dataset.closing;
  }
  if (dialog.open) return;
  dialog.showModal();
  dialog.animate?.(reducedMotion()
    ? [{ opacity: 0 }, { opacity: 1 }]
    : [{ opacity: 0, transform: "translateY(8px) scale(0.97)" }, { opacity: 1, transform: "none" }],
  { duration: 240, easing: EASE_OUT });
}

// `returnFocus` is applied after the modal is gone; while it animates out the page is still inert.
export function closeDialog(dialog, { returnFocus } = {}) {
  if (!dialog.open || dialog.dataset.closing) return;
  if (!dialog.animate) {
    dialog.close();
    returnFocus?.focus({ preventScroll: true });
    return;
  }
  dialog.dataset.closing = "true";
  const animation = dialog.animate(reducedMotion()
    ? [{ opacity: 1 }, { opacity: 0 }]
    : [{ opacity: 1, transform: "none" }, { opacity: 0, transform: "scale(0.98)" }],
  { duration: 150, easing: EASE_OUT, fill: "forwards" });
  const finish = () => {
    if (closingAnimations.get(dialog)?.animation !== animation) return;
    clearTimeout(closingAnimations.get(dialog).timer);
    closingAnimations.delete(dialog);
    delete dialog.dataset.closing;
    dialog.close();
    animation.cancel();
    returnFocus?.focus({ preventScroll: true });
  };
  // Hidden or occluded windows pause animations; never leave a modal blocking the page on that.
  closingAnimations.set(dialog, { animation, timer: setTimeout(finish, 400) });
  animation.onfinish = finish;
}

const toastLimit = 3;

export function toast(message, { tone = "ok", action, duration = 4200, dismissLabel = "Dismiss" } = {}) {
  const region = $("toasts");
  const item = element("div", "toast");
  item.dataset.tone = tone;
  item.append(icon(tone === "error" ? "alert" : tone === "info" ? "info" : "check-circle", "icon toast-icon"));
  item.append(element("p", "toast-text", message));
  if (action) {
    const control = element("button", "toast-action", action.label);
    control.type = "button";
    control.addEventListener("click", () => {
      action.run();
      dismiss();
    });
    item.append(control);
  }
  const close = iconButton("close", dismissLabel, () => dismiss(), "toast-close");
  item.append(close);

  let timer = null;
  let remaining = duration;
  let started = 0;
  const schedule = () => {
    clearTimeout(timer);
    started = performance.now();
    timer = setTimeout(dismiss, remaining);
  };
  const pause = () => {
    clearTimeout(timer);
    remaining = Math.max(900, remaining - (performance.now() - started));
  };
  function dismiss() {
    clearTimeout(timer);
    if (item.dataset.state === "closing") return;
    item.dataset.state = "closing";
    const done = () => item.remove();
    if (reducedMotion() || !item.animate) {
      done();
      return;
    }
    item.animate([{ opacity: 1, transform: "none" }, { opacity: 0, transform: "translateY(6px) scale(0.98)" }],
      { duration: 160, easing: EASE_OUT, fill: "forwards" }).onfinish = done;
    setTimeout(done, 400);
  }
  item.addEventListener("pointerenter", pause);
  item.addEventListener("pointerleave", schedule);
  item.addEventListener("focusin", pause);
  item.addEventListener("focusout", schedule);
  const open = [...region.children].filter(node => node.dataset.state !== "closing");
  for (const old of open.slice(0, Math.max(0, open.length - toastLimit + 1))) old.querySelector(".toast-close").click();
  region.append(item);
  fadeIn(item, { y: 10, duration: 280 });
  schedule();
  return dismiss;
}

export async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall back to a selection copy below; some WebViews gate the async clipboard.
  }
  const proxy = element("textarea", "clipboard-proxy");
  proxy.value = text;
  proxy.setAttribute("readonly", "");
  document.body.append(proxy);
  proxy.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  }
  proxy.remove();
  return copied;
}

const locale = language => (language === "zh" ? "zh-CN" : "en-US");

export function formatDateTime(timestamp, language) {
  return timestamp ? new Date(timestamp * 1000).toLocaleString(locale(language), {
    dateStyle: "medium", timeStyle: "short",
  }) : "—";
}

export function formatClock(timestamp, language) {
  return timestamp ? new Date(timestamp * 1000).toLocaleTimeString(locale(language), {
    hour: "numeric", minute: "2-digit",
  }) : "";
}

export function dayKey(timestamp) {
  const date = new Date(timestamp * 1000);
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

export function dayLabel(timestamp, language, t) {
  const date = new Date(timestamp * 1000);
  const today = new Date();
  const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
  if (dayKey(timestamp) === dayKey(today.getTime() / 1000)) return t("today");
  if (dayKey(timestamp) === dayKey(yesterday.getTime() / 1000)) return t("yesterday");
  return date.toLocaleDateString(locale(language), {
    month: "short", day: "numeric", ...(date.getFullYear() === today.getFullYear() ? {} : { year: "numeric" }),
  });
}

export function formatDuration(seconds, language) {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  if (language === "zh") {
    if (hours) return `${hours} 小时 ${minutes} 分`;
    if (minutes) return `${minutes} 分 ${rest} 秒`;
    return `${rest} 秒`;
  }
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m ${rest}s`;
  return `${rest}s`;
}

export function shortcutLabel(key) {
  return isMac ? `⌘${key}` : `Ctrl+${key}`;
}
