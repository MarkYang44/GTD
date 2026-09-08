(() => {
  "use strict";

  const STORAGE_KEY = "gtd_theme_v1";
  const root = document.documentElement;

  function normalize(theme) {
    return theme === "light" ? "light" : "dark";
  }

  function readTheme() {
    try {
      return normalize(window.localStorage.getItem(STORAGE_KEY));
    } catch (_error) {
      return "dark";
    }
  }

  function apply(theme, persist = false) {
    const selected = normalize(theme);
    root.dataset.theme = selected;
    root.style.colorScheme = selected;

    const toggle = document.querySelector("#theme-toggle");
    if (toggle) toggle.checked = selected === "light";
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", selected === "light" ? "#f5f7f6" : "#0b1111");

    if (persist) {
      try {
        window.localStorage.setItem(STORAGE_KEY, selected);
      } catch (_error) {
        // The switch remains usable when browser storage is unavailable.
      }
    }
  }

  function init() {
    apply(root.dataset.theme);
    const toggle = document.querySelector("#theme-toggle");
    if (toggle) {
      toggle.addEventListener("change", () => apply(toggle.checked ? "light" : "dark", true));
    }
  }

  window.addEventListener("storage", event => {
    if (event.key === STORAGE_KEY || event.key === null) apply(event.newValue);
  });
  window.addEventListener("pageshow", event => {
    if (event.persisted) apply(readTheme());
  });

  // Runs before stylesheets so the saved palette is used on the first paint.
  apply(readTheme());
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, {once: true});
  } else {
    init();
  }
})();
