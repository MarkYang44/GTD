// Accessible menus for row actions, right-clicks and composer options. Positioned through CSSOM (the
// CSP forbids inline style attributes, not style properties), kept inside the window, and closed on
// Escape, Tab, outside clicks, scrolling, resizing and window blur.
import { EASE_OUT, element, icon, reducedMotion } from "./ui.js";

let open = null;
let lastClosed = { anchor: null, time: 0 };
let serial = 0;
const read = value => (typeof value === "function" ? value() : value);

export function isMenuOpen() {
  return Boolean(open);
}

// Anchor buttons toggle their menu. The pointerdown that closes a menu is followed by a click on the
// same anchor; that click must not reopen it.
export function toggleMenu(anchor, build) {
  if (lastClosed.anchor === anchor && performance.now() - lastClosed.time < 500) {
    lastClosed.anchor = null;
    return;
  }
  if (open?.anchor === anchor) {
    closeMenu({ restore: true });
    return;
  }
  openMenu({ anchor, ...build() });
}

export function openMenu({ anchor = null, point = null, items, label = "", className = "", align = "start", returnFocus = anchor }) {
  closeMenu();
  const menu = element("div", `menu ${className}`.trim());
  menu.id = `menu-${++serial}`;
  menu.setAttribute("role", "menu");
  if (label) menu.setAttribute("aria-label", label);
  menu.tabIndex = -1;
  const entries = [];
  let pendingSeparator = false;
  for (const item of items.filter(Boolean)) {
    if (item.type === "separator") {
      pendingSeparator = entries.length > 0 || menu.childElementCount > 0;
      continue;
    }
    if (pendingSeparator) {
      const line = element("div", "menu-separator");
      line.setAttribute("role", "separator");
      menu.append(line);
      pendingSeparator = false;
    }
    if (item.type === "heading" || item.type === "note") {
      const text = element("p", `menu-${item.type}`, item.label);
      if (item.mono) text.classList.add("mono");
      if (item.title) text.title = item.title;
      menu.append(text);
      continue;
    }
    const entry = buildEntry(item);
    entries.push(entry);
    menu.append(entry.node);
  }
  menu.addEventListener("keydown", onKeydown);
  document.body.append(menu);
  const origin = place(menu, anchor, point, align);
  if (anchor) {
    anchor.setAttribute("aria-expanded", "true");
    anchor.setAttribute("aria-controls", menu.id);
  }
  open = { menu, anchor, entries, returnFocus, scrollX: window.scrollX, scrollY: window.scrollY };
  refreshEntries();
  if (menu.animate && document.visibilityState === "visible") {
    const lift = origin === "bottom" ? 3 : -3;
    menu.animate(reducedMotion()
      ? [{ opacity: 0 }, { opacity: 1 }]
      : [{ opacity: 0, transform: `translateY(${lift}px) scale(0.97)` }, { opacity: 1, transform: "none" }],
    { duration: 150, easing: EASE_OUT });
  }
  const initial = entries.find(entry => entry.role !== "menuitem" && read(entry.item.checked) && !read(entry.item.disabled))
    || entries.find(entry => !read(entry.item.disabled));
  (initial?.node || menu).focus({ preventScroll: true });
  document.addEventListener("pointerdown", onOutside, true);
  document.addEventListener("scroll", onScroll, true);
  window.addEventListener("resize", dismiss);
  window.addEventListener("blur", dismiss);
  return menu;
}

function buildEntry(item) {
  const role = item.type === "checkbox" ? "menuitemcheckbox" : item.type === "radio" ? "menuitemradio" : "menuitem";
  const node = element("button", "menu-item");
  node.type = "button";
  node.tabIndex = -1;
  node.setAttribute("role", role);
  if (item.danger) node.dataset.danger = "true";
  const mark = element("span", "menu-mark");
  if (role !== "menuitem") mark.append(icon("check"));
  else if (item.icon) mark.append(icon(item.icon));
  const copy = element("span", "menu-copy");
  copy.append(element("span", "menu-label", item.label));
  if (item.hint) copy.append(element("span", "menu-hint", item.hint));
  node.append(mark, copy);
  if (item.shortcut) node.append(element("kbd", "menu-shortcut", item.shortcut));
  const entry = { item, node, role };
  node.addEventListener("click", event => {
    event.stopPropagation();
    activate(entry);
  });
  // Hovering moves the highlight the same way the arrow keys do.
  node.addEventListener("pointermove", () => {
    if (document.activeElement !== node) node.focus({ preventScroll: true });
  });
  return entry;
}

function refreshEntries() {
  for (const { item, node, role } of open?.entries || []) {
    const disabled = Boolean(read(item.disabled));
    if (disabled) node.setAttribute("aria-disabled", "true");
    else node.removeAttribute("aria-disabled");
    if (role !== "menuitem") node.setAttribute("aria-checked", String(Boolean(read(item.checked))));
  }
}

function activate(entry) {
  const { item, role } = entry;
  if (read(item.disabled)) return;
  if (role === "menuitemcheckbox") {
    item.run?.(!read(item.checked));
    refreshEntries();
    return;
  }
  closeMenu({ restore: true });
  item.run?.();
}

function onKeydown(event) {
  if (!open) return;
  const entries = open.entries;
  const index = entries.findIndex(entry => entry.node === document.activeElement);
  const move = step => {
    if (!entries.length) return;
    let next = index;
    for (let tries = 0; tries < entries.length; tries += 1) {
      next = (next + step + entries.length) % entries.length;
      if (!read(entries[next].item.disabled)) break;
    }
    entries[next].node.focus({ preventScroll: true });
  };
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    move(event.key === "ArrowDown" ? 1 : -1);
  } else if (event.key === "Home" || event.key === "End") {
    event.preventDefault();
    const list = event.key === "Home" ? entries : [...entries].reverse();
    list.find(entry => !read(entry.item.disabled))?.node.focus({ preventScroll: true });
  } else if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    if (index >= 0) activate(entries[index]);
  } else if (event.key === "Escape" || event.key === "Tab") {
    event.preventDefault();
    event.stopPropagation();
    closeMenu({ restore: true });
  } else if (event.key.length === 1 && !event.metaKey && !event.ctrlKey && !event.altKey) {
    const key = event.key.toLocaleLowerCase();
    const order = [...entries.slice(index + 1), ...entries.slice(0, index + 1)];
    order.find(entry => entry.item.label.toLocaleLowerCase().startsWith(key))?.node.focus({ preventScroll: true });
  }
}

function onOutside(event) {
  if (!open || open.menu.contains(event.target)) return;
  lastClosed = { anchor: open.anchor?.contains(event.target) ? open.anchor : null, time: performance.now() };
  closeMenu();
}

// Scroll events arrive a frame late, so the one from scrolling a row into view can land after the
// menu opened. Close only when the page (or the anchor's container) really moved since then.
function onScroll(event) {
  if (!open || open.menu.contains(event.target)) return;
  const pageMoved = window.scrollX !== open.scrollX || window.scrollY !== open.scrollY;
  const anchorMoved = event.target !== document && Boolean(open.anchor && event.target.contains?.(open.anchor));
  if (pageMoved || anchorMoved) closeMenu();
}

function dismiss() {
  closeMenu();
}

export function closeMenu({ restore = false } = {}) {
  if (!open) return;
  const { menu, anchor, returnFocus } = open;
  open = null;
  document.removeEventListener("pointerdown", onOutside, true);
  document.removeEventListener("scroll", onScroll, true);
  window.removeEventListener("resize", dismiss);
  window.removeEventListener("blur", dismiss);
  if (anchor) {
    anchor.setAttribute("aria-expanded", "false");
    anchor.removeAttribute("aria-controls");
  }
  menu.removeEventListener("keydown", onKeydown);
  // While it fades out, the old menu is gone for keyboards and assistive technology.
  menu.inert = true;
  menu.setAttribute("aria-hidden", "true");
  const remove = () => menu.remove();
  if (!menu.animate || reducedMotion() || document.visibilityState !== "visible") remove();
  else {
    menu.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 100, easing: EASE_OUT, fill: "forwards" }).onfinish = remove;
    setTimeout(remove, 300);
  }
  if (restore && returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
}

function place(menu, anchor, point, align) {
  const margin = 8;
  const width = menu.offsetWidth;
  let height = menu.offsetHeight;
  const maxHeight = window.innerHeight - margin * 2;
  if (height > maxHeight) {
    menu.style.maxHeight = `${maxHeight}px`;
    height = maxHeight;
  }
  let x;
  let y;
  let origin = "top";
  if (point) {
    x = point.x;
    y = point.y;
    if (x + width > window.innerWidth - margin) x = x - width;
    if (y + height > window.innerHeight - margin) {
      y = y - height;
      origin = "bottom";
    }
  } else {
    const box = anchor.getBoundingClientRect();
    x = align === "end" ? box.right - width : box.left;
    y = box.bottom + 4;
    if (y + height > window.innerHeight - margin && box.top - height - 4 >= margin) {
      y = box.top - height - 4;
      origin = "bottom";
    }
  }
  x = Math.min(Math.max(margin, x), window.innerWidth - width - margin);
  y = Math.min(Math.max(margin, y), window.innerHeight - height - margin);
  menu.style.left = `${Math.round(x)}px`;
  menu.style.top = `${Math.round(y)}px`;
  menu.style.transformOrigin = `${align === "end" && !point ? "right" : "left"} ${origin}`;
  return origin;
}
