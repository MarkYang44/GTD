(() => {
  "use strict";

  const STORAGE_KEY = "gtd_language_v1";
  const LEGACY_KEY = "gtd_lmu_guide_language_v1";
  const VALID_LANGUAGES = new Set(["zh", "en"]);
  const ATTRIBUTE_NAMES = ["alt", "aria-label", "title", "placeholder"];
  const root = document.documentElement;

  function normalize(language) {
    return VALID_LANGUAGES.has(language) ? language : "zh";
  }

  function readStoredLanguage() {
    try {
      return normalize(window.localStorage.getItem(STORAGE_KEY) ?? window.localStorage.getItem(LEGACY_KEY));
    } catch (_error) {
      return "zh";
    }
  }

  function storeLanguage(language) {
    try {
      window.localStorage.setItem(STORAGE_KEY, language);
      window.localStorage.setItem(LEGACY_KEY, language);
    } catch (_error) {
      // Storage is optional; the visible language has already changed.
    }
  }

  function applyRoot(language) {
    const selected = normalize(language);
    root.dataset.guideLanguage = selected;
    root.lang = selected === "zh" ? "zh-CN" : "en";
    const title = root.getAttribute(`data-title-${selected}`);
    if (title) document.title = title;
    return selected;
  }

  function applyTranslatedAttributes(language) {
    for (const attribute of ATTRIBUTE_NAMES) {
      const selector = `[data-i18n-${attribute}-${language}]`;
      for (const element of document.querySelectorAll(selector)) {
        element.setAttribute(
          attribute,
          element.getAttribute(`data-i18n-${attribute}-${language}`),
        );
      }
    }
  }

  function apply(language, persist = false) {
    const selected = applyRoot(language);
    applyTranslatedAttributes(selected);

    const toggle = document.querySelector("#guide-language-toggle");
    if (toggle) {
      toggle.checked = selected === "en";
    }
    if (persist) {
      storeLanguage(selected);
    }
    if (typeof document.dispatchEvent === "function") {
      document.dispatchEvent(new CustomEvent("gtd:languagechange", {detail: {language: selected}}));
    }
    return selected;
  }

  function init() {
    const toggle = document.querySelector("#guide-language-toggle");
    apply(readStoredLanguage());
    if (!toggle || toggle.dataset.languageBound === "true") {
      return;
    }
    toggle.dataset.languageBound = "true";
    toggle.addEventListener("change", () => {
      apply(toggle.checked ? "en" : "zh", true);
    });
  }

  const api = {
    apply, init,
    get language() { return normalize(root.dataset.guideLanguage); },
    t(zh, en, params = {}) {
      const text = api.language === "en" ? en : zh;
      return text.replace(/\{(\w+)\}/g, (match, key) => Object.hasOwn(params, key) ? String(params[key]) : match);
    },
  };
  window.GtdLanguage = api;
  window.LmuGuideLanguage = api;
  window.addEventListener?.("storage", event => {
    if (event.key === STORAGE_KEY || event.key === null) apply(normalize(event.newValue));
  });
  window.addEventListener?.("pageshow", event => {
    if (event.persisted) apply(readStoredLanguage());
  });
  applyRoot(readStoredLanguage());
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
