"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync("static/js/lmu_guide_language.js", "utf8");

class Element {
  constructor(attributes = {}) {
    this.attributes = { ...attributes };
    this.dataset = {};
    this.listeners = {};
    this.checked = false;
    this.lang = "";
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  addEventListener(name, listener) {
    (this.listeners[name] ||= []).push(listener);
  }
}

function boot({
  stored = null,
  throwGet = false,
  throwSet = false,
  readyState = "complete",
} = {}) {
  const root = new Element({
    "data-title-zh": "LMU 赛道指南 - GTD",
    "data-title-en": "LMU Circuit Guide - GTD",
  });
  const image = new Element({
    "data-i18n-alt-zh": "Bahrain 赛道",
    "data-i18n-alt-en": "Bahrain circuit",
  });
  const navigation = new Element({
    "data-i18n-aria-label-zh": "LMU 彩蛋分页",
    "data-i18n-aria-label-en": "LMU easter egg pages",
  });
  const toggle = new Element({
    "data-i18n-aria-label-zh": "切换为英文",
    "data-i18n-aria-label-en": "Switch to Chinese",
  });
  const values = new Map();
  const storageWrites = [];
  if (stored !== null) values.set("gtd_lmu_guide_language_v1", stored);

  const localStorage = {
    getItem(key) {
      if (throwGet) throw new Error("blocked read");
      return values.get(key) ?? null;
    },
    setItem(key, value) {
      if (throwSet) throw new Error("blocked write");
      storageWrites.push([key, value]);
      values.set(key, value);
    },
  };

  const documentListeners = {};
  const document = {
    documentElement: root,
    readyState,
    title: "",
    querySelector(selector) {
      return selector === "#guide-language-toggle" ? toggle : null;
    },
    querySelectorAll(selector) {
      if (selector.startsWith("[data-i18n-alt-")) return [image];
      if (selector.startsWith("[data-i18n-aria-label-")) return [navigation, toggle];
      return [];
    },
    addEventListener(name, listener, options) {
      (documentListeners[name] ||= []).push({ listener, options });
    },
  };
  const window = { localStorage };
  vm.runInNewContext(source, { document, window, console });
  return {
    root,
    image,
    navigation,
    toggle,
    values,
    storageWrites,
    document,
    documentListeners,
    api: window.LmuGuideLanguage,
  };
}

const initial = boot();
assert.strictEqual(initial.root.dataset.guideLanguage, "zh");
assert.strictEqual(initial.root.lang, "zh-CN");
assert.strictEqual(initial.document.title, "LMU 赛道指南 - GTD");
assert.strictEqual(initial.image.getAttribute("alt"), "Bahrain 赛道");
assert.strictEqual(initial.navigation.getAttribute("aria-label"), "LMU 彩蛋分页");
assert.strictEqual(initial.toggle.checked, false);

initial.toggle.checked = true;
initial.toggle.listeners.change[0]();
assert.strictEqual(initial.root.dataset.guideLanguage, "en");
assert.strictEqual(initial.root.lang, "en");
assert.strictEqual(initial.document.title, "LMU Circuit Guide - GTD");
assert.strictEqual(initial.image.getAttribute("alt"), "Bahrain circuit");
assert.strictEqual(initial.navigation.getAttribute("aria-label"), "LMU easter egg pages");
assert.strictEqual(initial.values.get("gtd_lmu_guide_language_v1"), "en");

initial.api.init();
initial.api.init();
assert.strictEqual(initial.toggle.listeners.change.length, 1);

const restored = boot({ stored: "en" });
assert.strictEqual(restored.root.dataset.guideLanguage, "en");
assert.strictEqual(restored.toggle.checked, true);

for (const setup of [{ stored: "invalid" }, { throwGet: true }]) {
  const fallback = boot(setup);
  assert.strictEqual(fallback.root.dataset.guideLanguage, "zh");
  assert.strictEqual(fallback.toggle.checked, false);
}

const blockedWrite = boot({ throwSet: true });
blockedWrite.toggle.checked = true;
blockedWrite.toggle.listeners.change[0]();
assert.strictEqual(blockedWrite.root.dataset.guideLanguage, "en");

const loading = boot({ readyState: "loading" });
assert.strictEqual(loading.root.dataset.guideLanguage, undefined);
assert.strictEqual(loading.toggle.listeners.change, undefined);
assert.strictEqual(loading.documentListeners.DOMContentLoaded.length, 1);
assert.strictEqual(loading.documentListeners.DOMContentLoaded[0].options.once, true);
loading.documentListeners.DOMContentLoaded[0].listener();
assert.strictEqual(loading.root.dataset.guideLanguage, "zh");
assert.strictEqual(loading.toggle.listeners.change.length, 1);

const publicApi = boot();
assert.strictEqual(publicApi.api.apply("invalid"), "zh");
assert.strictEqual(publicApi.root.dataset.guideLanguage, "zh");
assert.deepStrictEqual(publicApi.storageWrites, []);
assert.strictEqual(publicApi.api.apply("en", false), "en");
assert.deepStrictEqual(publicApi.storageWrites, []);
