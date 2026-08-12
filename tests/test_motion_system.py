import re
import subprocess
import unittest
from pathlib import Path


CSS_PATH = Path("static/css/motion.css")
JS_PATH = Path("static/js/motion.js")


class SharedMotionAssetTests(unittest.TestCase):
    def test_shared_assets_define_the_declared_motion_contract(self):
        css = CSS_PATH.read_text(encoding="utf-8")
        script = JS_PATH.read_text(encoding="utf-8")

        for attribute in (
            "data-motion-reveal",
            "data-motion-surface",
            "data-motion-parallax",
            "data-motion-number",
        ):
            self.assertIn(attribute, css + script)
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn("(hover: hover) and (pointer: fine)", css)
        self.assertIn('matchMedia("(prefers-reduced-motion: reduce)")', script)
        self.assertIn('matchMedia("(hover: hover) and (pointer: fine)")', script)

    def test_engine_has_one_scheduler_and_no_idle_animation_loop(self):
        script = JS_PATH.read_text(encoding="utf-8")
        self.assertIn("function scheduleFrame", script)
        self.assertIn("requestAnimationFrame(runFrame)", script)
        self.assertNotIn("setInterval(", script)
        self.assertNotIn("setTimeout(", script)
        self.assertRegex(script, r"document\.hidden")
        self.assertRegex(script, r"cancelAnimationFrame\(")

    def test_engine_is_fail_open_and_exposes_lifecycle_api(self):
        css = CSS_PATH.read_text(encoding="utf-8")
        script = JS_PATH.read_text(encoding="utf-8")
        self.assertRegex(css, r"\[data-motion-reveal\]\s*\{[^}]*opacity:\s*1")
        self.assertIn('root.classList.add("motion-ready")', script)
        self.assertIn('root.classList.remove("motion-ready"', script)
        self.assertIn("refresh,", script)
        self.assertIn("destroy,", script)
        self.assertIn('new CustomEvent("motion:scroll-frame"', script)

    def test_css_composes_transforms_without_claiming_existing_card_pseudo_elements(self):
        css = CSS_PATH.read_text(encoding="utf-8")
        index_css = Path("static/css/index.css").read_text(encoding="utf-8")

        self.assertNotIn("[data-motion-surface] > *", css)
        self.assertRegex(
            css,
            r"\[data-motion-reveal\]\[data-motion-surface\].*?perspective\(1200px\)",
        )
        self.assertRegex(
            css,
            r"\[data-motion-reveal\]\[data-motion-parallax\].*?--motion-parallax-offset",
        )
        self.assertIn(".card::before", index_css)
        self.assertNotIn("[data-motion-surface]::before", css)
        self.assertNotIn("[data-motion-surface]::after", css)
        self.assertIn("backgroundImage", JS_PATH.read_text(encoding="utf-8"))
        self.assertIn("radial-gradient", JS_PATH.read_text(encoding="utf-8"))
        self.assertNotIn("NUMBER_SELECTOR", JS_PATH.read_text(encoding="utf-8"))

    def test_runtime_is_static_without_animation_apis_or_for_reduced_motion(self):
        script = r'''
const assert = require("assert");
const fs = require("fs");
const source = fs.readFileSync("static/js/motion.js", "utf8");

function classList() {
  const values = new Set();
  return { add(...names) { names.forEach((name) => values.add(name)); }, remove(...names) { names.forEach((name) => values.delete(name)); }, contains(name) { return values.has(name); } };
}
function boot({ reduced, requestAnimationFrame, observer }) {
  const reveal = { classList: classList(), style: { setProperty() {} }, getAttribute() { return null; } };
  const root = { classList: classList(), querySelectorAll(selector) { return selector === "[data-motion-reveal]" ? [reveal] : []; } };
  global.document = { documentElement: root, hidden: false, body: { scrollHeight: 100 }, querySelectorAll: root.querySelectorAll.bind(root), querySelector() { return null; }, addEventListener() {}, removeEventListener() {}, dispatchEvent() {} };
  global.window = { matchMedia(query) { return { matches: query.includes("reduced") ? reduced : false }; }, addEventListener() {}, removeEventListener() {}, innerHeight: 100, scrollY: 0 };
  global.requestAnimationFrame = requestAnimationFrame;
  global.cancelAnimationFrame = () => {};
  global.IntersectionObserver = observer;
  global.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init.detail; } };
  new Function(source)();
  return { root, reveal, api: window.MotionSystem };
}

const noApis = boot({ reduced: false, requestAnimationFrame: undefined, observer: undefined });
assert.doesNotThrow(() => noApis.api.refresh());
assert(noApis.reveal.classList.contains("motion-visible"));
assert(!noApis.root.classList.contains("motion-enabled"));

let scheduled = 0;
const reduced = boot({ reduced: true, requestAnimationFrame() { scheduled += 1; return 1; }, observer: class {} });
assert.doesNotThrow(() => reduced.api.refresh());
const number = { textContent: "00" };
reduced.api.setNumber(number, 7);
assert.strictEqual(number.textContent, "7");
assert.strictEqual(scheduled, 0);
assert(reduced.root.classList.contains("motion-reduced"));
'''
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_runtime_replaces_active_number_and_deduplicates_refresh(self):
        script = r'''
const assert = require("assert");
const fs = require("fs");
class ClassList { constructor() { this.values = new Set(); } add(...names) { names.forEach((name) => this.values.add(name)); } remove(...names) { names.forEach((name) => this.values.delete(name)); } contains(name) { return this.values.has(name); } }
class Element {
  constructor(attributes = {}) { this.attributes = attributes; this.classList = new ClassList(); this.style = { setProperty() {} }; this.textContent = "0"; this.listeners = {}; }
  getAttribute(name) { return this.attributes[name] ?? null; }
  addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
  removeEventListener(name, listener) { this.listeners[name] = (this.listeners[name] || []).filter((item) => item !== listener); }
  getBoundingClientRect() { return { left: 0, top: 0, width: 100, height: 100 }; }
}
const reveal = new Element({ "data-motion-reveal": "" });
const number = new Element({ "data-motion-number": "" });
const surface = new Element({ "data-motion-surface": "" });
const root = { classList: new ClassList(), querySelectorAll(selector) { return selector === "[data-motion-reveal]" ? [reveal] : selector === "[data-motion-surface]" ? [surface] : []; } };
const documentListeners = {};
global.document = { documentElement: root, hidden: false, body: { scrollHeight: 100 }, querySelectorAll: root.querySelectorAll.bind(root), querySelector() { return null; }, addEventListener(name, listener) { (documentListeners[name] ||= []).push(listener); }, removeEventListener() {}, dispatchEvent() {} };
global.window = { matchMedia(query) { return { matches: query.includes("pointer: fine") }; }, addEventListener() {}, removeEventListener() {}, innerHeight: 100, scrollY: 0 };
let nextId = 1;
const frames = new Map();
global.requestAnimationFrame = (callback) => { const id = nextId++; frames.set(id, callback); return id; };
global.cancelAnimationFrame = (id) => frames.delete(id);
let observer;
global.IntersectionObserver = class { constructor(callback) { this.callback = callback; this.observeCount = 0; observer = this; } observe() { this.observeCount += 1; } unobserve() {} disconnect() {} };
global.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init.detail; } };
new Function(fs.readFileSync("static/js/motion.js", "utf8"))();
window.MotionSystem.refresh();
window.MotionSystem.refresh();
assert.strictEqual(surface.listeners.pointerenter.length, 1);
assert.strictEqual(observer.observeCount, 1);
assert(!reveal.classList.contains("motion-visible"));
window.MotionSystem.setNumber(number, 12);
for (const callback of [...frames.values()]) callback(0);
for (const callback of [...frames.values()]) callback(140);
assert.strictEqual(number.textContent, "6");
window.MotionSystem.setNumber(number, 3);
for (const callback of [...frames.values()]) callback(280);
assert.strictEqual(number.textContent, "6");
for (const callback of [...frames.values()]) callback(560);
assert.strictEqual(number.textContent, "3");
window.MotionSystem.setNumber(number, null);
assert.strictEqual(number.textContent, "null");
window.MotionSystem.setNumber(number, true);
assert.strictEqual(number.textContent, "true");
'''
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_runtime_visibility_and_asynchronous_errors_fail_open(self):
        script = r'''
const assert = require("assert");
const fs = require("fs");
class ClassList { constructor() { this.values = new Set(); } add(...names) { names.forEach((name) => this.values.add(name)); } remove(...names) { names.forEach((name) => this.values.delete(name)); } contains(name) { return this.values.has(name); } }
class Element { constructor(attributes = {}) { this.attributes = attributes; this.classList = new ClassList(); this.style = { values: {}, setProperty(name, value) { this.values[name] = value; } }; this.listeners = {}; } getAttribute(name) { return this.attributes[name] ?? null; } addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); } removeEventListener(name, listener) { this.listeners[name] = (this.listeners[name] || []).filter((item) => item !== listener); } getBoundingClientRect() { return { left: 0, top: 0, width: 100, height: 100 }; } }
const reveal = new Element({ "data-motion-reveal": "" });
const surface = new Element({ "data-motion-surface": "" });
const root = { classList: new ClassList(), querySelectorAll(selector) { return selector === "[data-motion-reveal]" ? [reveal] : selector === "[data-motion-surface]" ? [surface] : []; } };
const listeners = {};
global.document = { documentElement: root, hidden: false, body: { scrollHeight: 100 }, querySelectorAll: root.querySelectorAll.bind(root), querySelector() { return null; }, addEventListener(name, listener) { (listeners[name] ||= []).push(listener); }, removeEventListener(name, listener) { listeners[name] = (listeners[name] || []).filter((item) => item !== listener); }, dispatchEvent() { throw new Error("frame failure"); } };
global.window = { matchMedia(query) { return { matches: query.includes("pointer: fine") }; }, addEventListener() {}, removeEventListener() {}, innerHeight: 100, scrollY: 0 };
const frames = new Map(); let nextId = 1;
global.requestAnimationFrame = (callback) => { const id = nextId++; frames.set(id, callback); return id; };
global.cancelAnimationFrame = (id) => frames.delete(id);
let observer;
global.IntersectionObserver = class { constructor(callback) { this.callback = callback; this.disconnected = false; observer = this; } observe() {} unobserve() {} disconnect() { this.disconnected = true; } };
global.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init.detail; } };
new Function(fs.readFileSync("static/js/motion.js", "utf8"))();
surface.listeners.pointerenter[0]({ clientX: 100, clientY: 0 });
document.hidden = true;
listeners.visibilitychange[0]();
assert.strictEqual(surface.style.values["--motion-rx"], "0deg");
assert.strictEqual(frames.size, 0);
document.hidden = false;
listeners.visibilitychange[0]();
for (const callback of [...frames.values()]) assert.doesNotThrow(() => callback(1));
assert(!root.classList.contains("motion-ready"));
assert(reveal.classList.contains("motion-visible"));
assert.strictEqual(surface.listeners.pointerenter.length, 0);
assert(observer.disconnected);

const observerReveal = new Element({ "data-motion-reveal": "" });
const observerRoot = { classList: new ClassList(), querySelectorAll(selector) { return selector === "[data-motion-reveal]" ? [observerReveal] : []; } };
const observerListeners = {};
global.document = { documentElement: observerRoot, hidden: false, body: { scrollHeight: 100 }, querySelectorAll: observerRoot.querySelectorAll.bind(observerRoot), querySelector() { return null; }, addEventListener(name, listener) { (observerListeners[name] ||= []).push(listener); }, removeEventListener() {}, dispatchEvent() {} };
global.window = { matchMedia(query) { return { matches: query.includes("pointer: fine") }; }, addEventListener() {}, removeEventListener() {}, innerHeight: 100, scrollY: 0 };
global.requestAnimationFrame = () => 1;
global.cancelAnimationFrame = () => {};
let failingObserver;
global.IntersectionObserver = class { constructor(callback) { this.callback = callback; this.disconnected = false; failingObserver = this; } observe() {} unobserve() {} disconnect() { this.disconnected = true; } };
new Function(fs.readFileSync("static/js/motion.js", "utf8"))();
assert.doesNotThrow(() => failingObserver.callback([{ isIntersecting: true, target: null }]));
assert(!observerRoot.classList.contains("motion-ready"));
assert(observerReveal.classList.contains("motion-visible"));
assert(failingObserver.disconnected);
'''
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_runtime_handles_numbers_lifecycle_and_surface_cleanup(self):
        script = r'''
const assert = require("assert");
const fs = require("fs");

class ClassList {
  constructor() { this.values = new Set(); }
  add(...names) { names.forEach((name) => this.values.add(name)); }
  remove(...names) { names.forEach((name) => this.values.delete(name)); }
  contains(name) { return this.values.has(name); }
}

class Element {
  constructor(attributes = {}) {
    this.attributes = attributes;
    this.classList = new ClassList();
    this.style = { values: {}, setProperty(name, value) { this.values[name] = value; } };
    this.textContent = "00";
    this.listeners = {};
  }
  getAttribute(name) { return this.attributes[name] ?? null; }
  hasAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attributes, name); }
  addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
  removeEventListener(name, listener) { this.listeners[name] = (this.listeners[name] || []).filter((item) => item !== listener); }
  getBoundingClientRect() { return { left: 0, top: 0, width: 100, height: 100 }; }
}

const reveal = new Element({ "data-motion-reveal": "" });
const number = new Element({ "data-motion-number": "" });
const surface = new Element({ "data-motion-surface": "" });
const parallax = new Element({ "data-motion-parallax": "0.55" });
const root = { classList: new ClassList(), querySelectorAll(selector) {
  if (selector === "[data-motion-reveal]") return [reveal];
  if (selector === "[data-motion-number]") return [number];
  if (selector === "[data-motion-surface]") return [surface];
  if (selector === "[data-motion-parallax]") return [parallax];
  if (selector === "[data-motion-group]") return [];
  return [];
} };
const documentListeners = {};
global.document = {
  documentElement: root,
  hidden: false,
  body: { scrollHeight: 1100, offsetHeight: 1100 },
  addEventListener(name, listener) { (documentListeners[name] ||= []).push(listener); },
  removeEventListener(name, listener) { documentListeners[name] = (documentListeners[name] || []).filter((item) => item !== listener); },
  dispatchEvent(event) { this.lastEvent = event; },
  querySelector(selector) { return selector === "#topbar" ? null : null; },
  querySelectorAll(selector) { return root.querySelectorAll(selector); },
};
global.window = {
  matchMedia(query) { return { matches: query.includes("pointer: fine") }; },
  scrollY: 50,
  innerHeight: 100,
  addEventListener() {},
  removeEventListener() {},
  getComputedStyle() { return { backgroundImage: "linear-gradient(#111, #222)" }; },
};
let nextFrame = 1;
const queuedFrames = new Map();
global.requestAnimationFrame = (callback) => { const id = nextFrame++; queuedFrames.set(id, callback); return id; };
global.cancelAnimationFrame = (id) => queuedFrames.delete(id);
global.CustomEvent = class CustomEvent { constructor(type, init) { this.type = type; this.detail = init.detail; } };
global.IntersectionObserver = class IntersectionObserver {
  constructor(callback) { this.callback = callback; this.items = []; }
  observe(item) { this.items.push(item); }
  unobserve(item) { this.items = this.items.filter((entry) => entry !== item); }
  disconnect() { this.items = []; }
};

eval(fs.readFileSync("static/js/motion.js", "utf8"));
assert(root.classList.contains("motion-ready"));
assert(root.classList.contains("motion-enabled"));
assert(root.classList.contains("motion-fine-pointer"));
assert.strictEqual(surface.listeners.pointerenter.length, 1);
window.MotionSystem.setNumber(number, "not-a-number");
assert.strictEqual(number.textContent, "not-a-number");
window.MotionSystem.setNumber(number, 12);
window.MotionSystem.setNumber(number, 3);
for (const callback of [...queuedFrames.values()]) callback(500);
for (const callback of [...queuedFrames.values()]) callback(900);
assert.strictEqual(number.textContent, "3");
surface.listeners.pointerenter[0]({ clientX: 100, clientY: 0 });
for (const callback of [...queuedFrames.values()]) callback(600);
assert.strictEqual(surface.style.values["--motion-rx"], "0.6deg");
assert.strictEqual(surface.style.values["--motion-ry"], "0.6deg");
assert(surface.style.backgroundImage.includes("radial-gradient"));
assert(surface.style.backgroundImage.includes("linear-gradient(#111, #222)"));
assert.strictEqual(document.lastEvent.type, "motion:scroll-frame");
assert(Math.abs(Number.parseFloat(parallax.style.values["--motion-parallax-offset"])) <= 6.6);
window.MotionSystem.destroy();
assert(!root.classList.contains("motion-ready"));
assert.strictEqual(surface.listeners.pointerenter.length, 0);
assert.strictEqual(surface.style.values["--motion-rx"], "0deg");
assert.strictEqual(parallax.style.values["--motion-parallax-offset"], "0px");
assert.strictEqual(surface.style.backgroundImage, "");
'''
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
