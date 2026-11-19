// Settings save as soon as they change. Problems stay next to the setting that caused them.
import { errorParts } from "./strings.js";
import { $, button, element, fillCallout, icon, isMac, setText, shortcutLabel, toast } from "./ui.js";
import { platformName } from "./tasks.js";
import { defaultFolder, pickPath, reveal, saveSettings, setCookies } from "./service.js";
import { notice, showError } from "./feedback.js";
import { state, t } from "./store.js";

const PLATFORMS = ["youtube", "instagram", "bilibili"];
const MARKS = { youtube: "YT", instagram: "IG", bilibili: "BL" };
let busy = false;
let confirmRemove = "";
let confirmTimer = null;
let cookieKey = "";
let shortcutKey = "";
const cookieErrors = {};
const select = selector => document.querySelectorAll(selector);

async function change(run, { target = "settings", success } = {}) {
  if (busy || state.connection !== "ready") return false;
  busy = true;
  renderSettings(state, true);
  notice(target, "");
  try {
    await run();
    if (success) toast(success, { dismissLabel: t("dismiss") });
    return true;
  } catch (error) {
    showError(target, error);
    return false;
  } finally {
    busy = false;
    renderSettings(state, true);
  }
}

function saveFolder(value) {
  const next = value.trim();
  if (next === (state.settings?.download_dir || "") || (!state.settings?.download_dir && next === state.settings?.default_download_dir)) {
    renderSettings(state, true);
    return Promise.resolve(true);
  }
  return change(() => saveSettings({ download_dir: next }), { target: "folder", success: t("folderSaved") });
}

export async function chooseDefaultFolder() {
  try {
    const location = await pickPath("folder", $("default-folder").value.trim() || undefined);
    if (!location) return;
    $("default-folder").value = location;
    await saveFolder(location);
  } catch (error) {
    showError("folder", error);
  }
}

async function updateCookie(platform, path) {
  delete cookieErrors[platform];
  confirmRemove = "";
  clearTimeout(confirmTimer);
  const name = platformName(platform, t);
  let failure = null;
  const saved = await change(async () => {
    try {
      await setCookies(platform, path);
    } catch (error) {
      failure = error;
      throw error;
    }
  }, { target: "settings", success: t(path ? "cookiesImported" : "cookiesRemoved", { platform: name }) });
  if (!saved && failure) {
    notice("settings", "");
    cookieErrors[platform] = failure;
    renderCookies(true);
  }
}

function renderCookies(force = false) {
  const ready = state.connection === "ready" && !busy;
  const key = JSON.stringify([state.language, state.settings?.cookies, ready, confirmRemove, Object.keys(cookieErrors)]);
  if (!force && key === cookieKey) return;
  cookieKey = key;
  const rows = PLATFORMS.map(id => {
    const platform = platformName(id, t);
    const installed = Boolean(state.settings?.cookies?.[id]);
    const row = element("li", "cookie-row");
    row.dataset.platform = id;
    row.dataset.installed = String(installed);
    const mark = element("span", "cookie-mark", MARKS[id]);
    mark.setAttribute("aria-hidden", "true");
    const copy = element("div", "cookie-copy");
    const status = element("span", "cookie-status");
    status.append(icon(installed ? "check-circle" : "key"), element("span", "", t(installed ? "cookieImported" : "cookieMissing")));
    copy.append(element("strong", "", platform), status);
    const actions = element("div", "cookie-actions");
    const importButton = button(t(installed ? "replace" : "import"), async () => {
      try {
        const path = await pickPath("cookie");
        if (path) await updateCookie(id, path);
      } catch (error) {
        cookieErrors[id] = error;
        renderCookies(true);
      }
    }, "secondary compact");
    importButton.setAttribute("aria-label", t(installed ? "replaceCookies" : "importCookies", { platform }));
    importButton.disabled = !ready;
    actions.append(importButton);
    if (installed) {
      const confirming = confirmRemove === id;
      const remove = button(t(confirming ? "confirmRemove" : "remove"), () => {
        if (confirmRemove !== id) {
          confirmRemove = id;
          clearTimeout(confirmTimer);
          confirmTimer = setTimeout(() => {
            confirmRemove = "";
            renderCookies(true);
          }, 4000);
          renderCookies(true);
          document.querySelector(`.cookie-row[data-platform="${id}"] .cookie-actions .confirm`)?.focus();
          return;
        }
        confirmRemove = "";
        clearTimeout(confirmTimer);
        updateCookie(id, null);
      }, `${confirming ? "secondary confirm" : "ghost"} compact`);
      remove.setAttribute("aria-label", t(confirming ? "confirmRemoveCookies" : "removeCookies", { platform }));
      remove.disabled = !ready;
      actions.append(remove);
    }
    row.append(mark, copy, actions);
    if (cookieErrors[id]) {
      row.append(element("div", "callout"));
      fillCallout(row.lastElementChild, { tone: "error", codeLabel: t("errorCode"), ...errorParts(cookieErrors[id], state.language) });
    }
    return row;
  });
  const list = $("cookie-list");
  const focused = list.contains(document.activeElement)
    ? [document.activeElement.closest(".cookie-row")?.dataset.platform, document.activeElement.getAttribute("aria-label")] : null;
  list.replaceChildren(...rows);
  if (focused) {
    const [platform, label] = focused;
    const row = list.querySelector(`.cookie-row[data-platform="${platform}"]`);
    ([...(row?.querySelectorAll("button") || [])].find(node => node.getAttribute("aria-label") === label)
      || row?.querySelector("button"))?.focus({ preventScroll: true });
  }
}

function renderShortcuts() {
  if (shortcutKey === state.language) return;
  shortcutKey = state.language;
  const enter = isMac ? "↩" : "Enter";
  const rows = [
    ["scNew", [shortcutLabel("N")]],
    ["scPaste", [shortcutLabel("V")]],
    ["scFile", [shortcutLabel("O")]],
    ["scSearch", [shortcutLabel("F")]],
    ["scViews", [`${shortcutLabel("1")} – ${shortcutLabel("6")}`]],
    ["scSettings", [shortcutLabel(",")]],
    ["scSubmit", [enter]],
    ["scNewline", [isMac ? "⇧↩" : "Shift+Enter"]],
    ["scMove", ["↑", "↓"]],
    ["scDetails", [enter]],
    ["scSelect", [t("keySpace"), isMac ? "⌘-click" : "Ctrl+click"]],
    ["scSelectAll", [shortcutLabel("A")]],
    ["scMenu", [t("keyRightClick"), "⇧F10"]],
  ];
  $("shortcut-list").replaceChildren(...rows.map(([label, keys]) => {
    const row = element("div", "shortcut-row");
    const combo = element("dd", "shortcut-keys");
    keys.forEach((keyLabel, index) => {
      if (index) combo.append(element("span", "shortcut-or", t("or")));
      combo.append(element("kbd", "", keyLabel));
    });
    row.append(element("dt", "", t(label)), combo);
    return row;
  }));
}

// `force` re-syncs controls after a save even while the view is hidden.
export function renderSettings(s, force = false) {
  if (s.view !== "settings" && !force) return;
  const ready = s.connection === "ready" && !busy;
  const settings = s.settings;
  for (const input of select('input[name="language"], input[name="theme"]')) {
    input.disabled = !ready;
    // Keep the pending choice visible while it saves; resync once the response lands.
    if (!busy) input.checked = input.value === (input.name === "language" ? s.language : settings?.theme || "system");
  }
  const folder = settings ? settings.download_dir || settings.default_download_dir || "" : "";
  const input = $("default-folder");
  if (document.activeElement !== input || !ready) input.value = folder;
  input.disabled = !ready;
  for (const control of select("#folder-form button")) control.disabled = !ready;
  $("folder-default-tag").hidden = !settings || Boolean(settings.download_dir);
  $("reset-folder").hidden = !settings?.download_dir;
  setText($("app-version"), s.version ? t("versionLabel", { version: s.version }) : "Generalized Transmedia Downloader");
  $("data-folder-row").hidden = !settings?.data_dir;
  setText($("data-folder"), settings?.data_dir || "");
  $("open-data-folder").disabled = !settings?.data_dir;
  renderCookies(force);
  renderShortcuts();
}

export function initSettings() {
  for (const input of select('input[name="language"]')) {
    input.addEventListener("change", () => change(() => saveSettings({ language: input.value })));
  }
  for (const input of select('input[name="theme"]')) {
    input.addEventListener("change", () => change(() => saveSettings({ theme: input.value })));
  }
  $("folder-form").addEventListener("submit", event => {
    event.preventDefault();
    saveFolder($("default-folder").value);
  });
  $("default-folder").addEventListener("change", () => saveFolder($("default-folder").value));
  $("choose-default-folder").addEventListener("click", chooseDefaultFolder);
  $("reset-folder").addEventListener("click", () => {
    change(() => saveSettings({ download_dir: "" }), { target: "folder", success: t("folderSaved") });
  });
  $("open-default-folder").addEventListener("click", async () => {
    try {
      await reveal($("default-folder").value.trim() || defaultFolder());
    } catch (error) {
      showError("folder", error);
    }
  });
  $("open-data-folder").addEventListener("click", async () => {
    try {
      await reveal(state.settings?.data_dir);
    } catch (error) {
      showError("settings", error);
    }
  });
}
