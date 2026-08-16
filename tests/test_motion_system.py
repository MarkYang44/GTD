import re
import subprocess
import unittest
from pathlib import Path

import app as web_app

CSS_PATH = Path("static/css/motion.css")
JS_PATH = Path("static/js/motion.js")


class SharedMotionAssetTests(unittest.TestCase):
    def test_pages_serve_shared_motion_assets_with_browser_mime_types(self):
        client = web_app.app.test_client()

        for path in ("/guide", "/kozekilmu"):
            page = client.get(path)
            self.assertEqual(page.status_code, 200)
            html = page.get_data(as_text=True)
            self.assertIn('href="/static/css/motion.css"', html)
            self.assertIn('<script defer src="/static/js/motion.js"></script>', html)

        stylesheet = client.get("/static/css/motion.css")
        script = client.get("/static/js/motion.js")
        self.addCleanup(stylesheet.close)
        self.addCleanup(script.close)
        self.assertEqual(stylesheet.status_code, 200)
        self.assertEqual(script.status_code, 200)
        self.assertEqual(stylesheet.mimetype, "text/css")
        self.assertIn(script.mimetype, {"application/javascript", "text/javascript"})

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
        self.assertNotRegex(JS_PATH.read_text(encoding="utf-8"), r"\.style\.backgroundImage\s*=")
        self.assertIn("radial-gradient", css)
        self.assertNotIn("NUMBER_SELECTOR", JS_PATH.read_text(encoding="utf-8"))

    def test_layered_sheen_is_opt_in_and_ordinary_surfaces_keep_background_fallback(self):
        css = CSS_PATH.read_text(encoding="utf-8")
        self.assertRegex(css, r"\[data-motion-sheen\]\s*\{[^}]*pointer-events:\s*none")
        self.assertRegex(css, r"\[data-motion-sheen\]\s*\{[^}]*opacity:\s*0")
        self.assertRegex(
            css,
            r"\.motion-surface-active\s*>\s*\[data-motion-sheen\]\s*\{[^}]*opacity:",
        )
        self.assertRegex(
            css,
            r"(?s)@media\s*\(prefers-reduced-motion:\s*reduce\).*?\[data-motion-sheen\][^{]*\{[^}]*display:\s*none",
        )

        script = r'''
const assert = require("assert");
const fs = require("fs");
class ClassList { constructor() { this.values = new Set(); } add(...names) { names.forEach((name) => this.values.add(name)); } remove(...names) { names.forEach((name) => this.values.delete(name)); } contains(name) { return this.values.has(name); } }
class Element {
  constructor({ sheen = false, background = "" } = {}) { this.classList = new ClassList(); this.listeners = {}; this.sheen = sheen; this.style = { values: {}, setProperty(name, value) { this.values[name] = value; }, removeProperty(name) { delete this.values[name]; }, getPropertyValue(name) { return this.values[name] || ""; } }; this.background = background; }
  getAttribute() { return null; }
  querySelector(selector) { return selector === "[data-motion-sheen]" && this.sheen ? {} : null; }
  addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
  removeEventListener(name, listener) { this.listeners[name] = (this.listeners[name] || []).filter((item) => item !== listener); }
  getBoundingClientRect() { return { left: 0, top: 0, width: 100, height: 100 }; }
}
const layered = new Element({ sheen: true, background: "layered-inline" });
const ordinary = new Element({ background: "ordinary-inline" });
const root = { classList: new ClassList(), querySelectorAll(selector) { return selector === "[data-motion-surface]" ? [layered, ordinary] : []; } };
const listeners = {};
global.document = { documentElement: root, hidden: false, body: { scrollHeight: 100 }, querySelectorAll: root.querySelectorAll.bind(root), querySelector() { return null; }, addEventListener(name, listener) { (listeners[name] ||= []).push(listener); }, removeEventListener() {}, dispatchEvent() {} };
global.window = { matchMedia(query) { return { matches: query.includes("pointer: fine") }; }, addEventListener() {}, removeEventListener() {}, innerHeight: 100, scrollY: 0, getComputedStyle(element) { return { backgroundImage: element === layered ? "layered-computed" : "ordinary-computed" }; } };
const frames = new Map(); let nextId = 1;
global.requestAnimationFrame = (callback) => { const id = nextId++; frames.set(id, callback); return id; };
global.cancelAnimationFrame = (id) => frames.delete(id);
global.IntersectionObserver = class { constructor() {} observe() {} disconnect() {} };
global.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init.detail; } };
function runFrames(timestamp) { for (const [id, callback] of [...frames]) { frames.delete(id); callback(timestamp); } }
new Function(fs.readFileSync("static/js/motion.js", "utf8"))();
runFrames(0);
layered.listeners.pointerenter[0]({ clientX: 75, clientY: 25 });
runFrames(1);
assert(layered.classList.contains("motion-surface-active"));
assert.strictEqual(layered.style.values["--motion-base-background"], undefined);
layered.listeners.pointerleave[0]();
assert(!layered.classList.contains("motion-surface-active"));
assert.strictEqual(layered.style.values["--motion-rx"], "0deg");
ordinary.listeners.pointerenter[0]({ clientX: 75, clientY: 25 });
runFrames(2);
assert(ordinary.classList.contains("motion-surface-fallback"));
assert.strictEqual(ordinary.style.values["--motion-base-background"], "ordinary-computed");
assert(Object.keys(ordinary.style.values).every((name) => name.startsWith("--motion-")));
ordinary.listeners.pointerleave[0]();
assert.strictEqual(ordinary.style.values["--motion-base-background"], undefined);
window.MotionSystem.destroy();
assert(!layered.classList.contains("motion-surface-active"));
'''
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_static_scroll_contract_survives_reduced_motion_and_missing_animation_apis(self):
        script = r'''
const assert = require("assert");
const fs = require("fs");
const source = fs.readFileSync("static/js/motion.js", "utf8");

function classList() { const values = new Set(); return { add(...names) { names.forEach((name) => values.add(name)); }, remove(...names) { names.forEach((name) => values.delete(name)); }, toggle(name, force) { if (force) values.add(name); else values.delete(name); }, contains(name) { return values.has(name); } }; }
function element() { return { classList: classList(), style: { values: {}, setProperty(name, value) { this.values[name] = value; } }, getAttribute() { return "0.5"; } }; }
function boot({ reduced, requestAnimationFrame, observer }) {
  const root = { classList: classList(), querySelectorAll() { return []; } };
  const topbar = element(); const progress = element(); const windowListeners = {}; const documentListeners = {}; const events = [];
  global.document = { documentElement: root, hidden: false, body: { scrollHeight: 1100 }, querySelectorAll() { return []; }, querySelector(selector) { return selector === "#topbar" ? topbar : selector === "#scroll-progress" ? progress : null; }, addEventListener(name, listener) { (documentListeners[name] ||= []).push(listener); }, removeEventListener() {}, dispatchEvent(event) { events.push(event); } };
  global.window = { matchMedia(query) { return { matches: query.includes("reduced") ? reduced : false }; }, scrollY: 13, innerHeight: 100, addEventListener(name, listener) { (windowListeners[name] ||= []).push(listener); }, removeEventListener() {} };
  global.requestAnimationFrame = requestAnimationFrame; global.cancelAnimationFrame = () => {}; global.IntersectionObserver = observer; global.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init.detail; } };
  new Function(source)();
  return { root, topbar, progress, windowListeners, events };
}

const reduced = boot({ reduced: true, requestAnimationFrame: undefined, observer: undefined });
assert(reduced.topbar.classList.contains("is-scrolled"));
assert.strictEqual(reduced.progress.style.values["--motion-scroll-progress"], "0.013");
assert.strictEqual(reduced.events.at(-1).type, "motion:scroll-frame");
reduced.windowListeners.scroll[0]();
assert.strictEqual(reduced.events.length, 2);
assert(!reduced.root.classList.contains("motion-enabled"));

let frame;
const degraded = boot({ reduced: false, requestAnimationFrame(callback) { frame = callback; return 1; }, observer: undefined });
assert(!degraded.root.classList.contains("motion-enabled"));
assert.strictEqual(typeof frame, "function");
frame(1);
assert(degraded.topbar.classList.contains("is-scrolled"));
assert.strictEqual(degraded.events.at(-1).type, "motion:scroll-frame");
'''
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_interrupted_number_animations_commit_their_latest_formatted_target(self):
        script = r'''
const assert = require("assert");
const fs = require("fs");
class ClassList { add() {} remove() {} contains() { return false; } }
class Element { constructor() { this.classList = new ClassList(); this.style = { setProperty() {} }; this.textContent = "00"; } getAttribute() { return null; } }
const root = { classList: new ClassList(), querySelectorAll() { return []; } };
const documentListeners = {}; const frames = new Map(); let nextId = 1;
global.document = { documentElement: root, hidden: false, body: { scrollHeight: 100 }, querySelectorAll() { return []; }, querySelector() { return null; }, addEventListener(name, listener) { (documentListeners[name] ||= []).push(listener); }, removeEventListener() {}, dispatchEvent() {} };
global.window = { matchMedia(query) { return { matches: query.includes("pointer: fine") }; }, innerHeight: 100, scrollY: 0, addEventListener() {}, removeEventListener() {} };
global.requestAnimationFrame = (callback) => { const id = nextId++; frames.set(id, callback); return id; }; global.cancelAnimationFrame = (id) => frames.delete(id); global.IntersectionObserver = class { constructor() {} observe() {} disconnect() {} }; global.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init.detail; } };
new Function(fs.readFileSync("static/js/motion.js", "utf8"))();
function run(timestamp) { for (const [id, callback] of [...frames]) { frames.delete(id); callback(timestamp); } }
const number = new Element();
window.MotionSystem.setNumber(number, "07"); run(0); run(140); assert.notStrictEqual(number.textContent, "07");
document.hidden = true; documentListeners.visibilitychange[0](); assert.strictEqual(number.textContent, "07");
document.hidden = false; documentListeners.visibilitychange[0]();
window.MotionSystem.setNumber(number, "03"); run(200); window.MotionSystem.destroy(); assert.strictEqual(number.textContent, "03");

const failingNumber = new Element();
const root2 = { classList: new ClassList(), querySelectorAll() { return []; } }; const frames2 = new Map(); let id2 = 1;
global.document = { documentElement: root2, hidden: false, body: { scrollHeight: 100 }, querySelectorAll() { return []; }, querySelector() { return null; }, addEventListener() {}, removeEventListener() {}, dispatchEvent() { throw new Error("fail after target queued"); } };
global.window = { matchMedia(query) { return { matches: query.includes("pointer: fine") }; }, innerHeight: 100, scrollY: 0, addEventListener() {}, removeEventListener() {} };
global.requestAnimationFrame = (callback) => { const id = id2++; frames2.set(id, callback); return id; }; global.cancelAnimationFrame = (id) => frames2.delete(id); global.IntersectionObserver = class { constructor() {} observe() {} disconnect() {} };
new Function(fs.readFileSync("static/js/motion.js", "utf8"))();
for (const [id, callback] of [...frames2]) { frames2.delete(id); callback(0); }
window.MotionSystem.setNumber(failingNumber, "09");
for (const [id, callback] of [...frames2]) { frames2.delete(id); callback(1); }
assert.strictEqual(failingNumber.textContent, "09");
'''
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_css_gives_settled_surfaces_and_parallax_short_unstaggered_transitions(self):
        css = CSS_PATH.read_text(encoding="utf-8")
        entering = re.search(
            r"\.motion-ready\.motion-enabled\s+\[data-motion-reveal\]\.motion-visible\s*\{([^}]*)\}",
            css,
        )
        self.assertIsNotNone(entering)
        self.assertIn("var(--motion-enter)", entering.group(1))
        self.assertIn("var(--motion-stagger)", entering.group(1))
        for selector in (
            r"\.motion-ready\.motion-enabled\s+\[data-motion-reveal\]\[data-motion-surface\]\.motion-settled",
            r"\.motion-ready\.motion-enabled\s+\[data-motion-reveal\]\[data-motion-parallax\]\.motion-settled",
        ):
            match = re.search(selector + r"\s*\{([^}]*)\}", css)
            self.assertIsNotNone(match, selector)
            self.assertIn("var(--motion-fast)", match.group(1))
            self.assertIn("transition-delay: 0ms", match.group(1))

        homepage = web_app.app.test_client().get("/").get_data(as_text=True)
        kozeki = web_app.app.test_client().get("/kozekilmu").get_data(as_text=True)
        self.assertRegex(homepage, r'data-motion-reveal[^>]*data-motion-surface')
        self.assertRegex(homepage, r'data-motion-parallax="0\.55"')
        self.assertRegex(kozeki, r'data-motion-reveal[^>]*data-motion-surface')
        self.assertRegex(kozeki, r'data-motion-reveal[^>]*data-motion-parallax')

    def test_runtime_marks_reveals_settled_only_after_their_transition_and_cleans_listeners(self):
        script = r'''
const assert = require("assert");
const fs = require("fs");
class ClassList { constructor() { this.values = new Set(); } add(...names) { names.forEach((name) => this.values.add(name)); } remove(...names) { names.forEach((name) => this.values.delete(name)); } contains(name) { return this.values.has(name); } }
class Element {
  constructor(attributes = {}) { this.attributes = attributes; this.classList = new ClassList(); this.style = { setProperty() {} }; this.listeners = {}; }
  getAttribute(name) { return this.attributes[name] ?? null; }
  addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
  removeEventListener(name, listener) { this.listeners[name] = (this.listeners[name] || []).filter((item) => item !== listener); }
  emit(name, event) { for (const listener of [...(this.listeners[name] || [])]) listener(event); }
}
const reveal = new Element({ "data-motion-reveal": "", "data-motion-surface": "", "data-motion-parallax": "0.5" });
const pending = new Element({ "data-motion-reveal": "" });
let elements = [reveal];
const root = { classList: new ClassList(), querySelectorAll(selector) { return selector === "[data-motion-reveal]" ? elements : []; } };
const frames = new Map(); let nextFrame = 1; let observer;
global.document = { documentElement: root, hidden: false, body: { scrollHeight: 100 }, querySelectorAll: root.querySelectorAll.bind(root), querySelector() { return null; }, addEventListener() {}, removeEventListener() {}, dispatchEvent() {} };
global.window = { matchMedia(query) { return { matches: query.includes("pointer: fine") }; }, innerHeight: 100, scrollY: 0, addEventListener() {}, removeEventListener() {}, getComputedStyle() { return { transitionDuration: "680ms, 680ms, 680ms", transitionDelay: "70ms, 70ms, 70ms", backgroundImage: "none" }; } };
global.requestAnimationFrame = (callback) => { const id = nextFrame++; frames.set(id, callback); return id; }; global.cancelAnimationFrame = (id) => frames.delete(id); global.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init.detail; } };
global.IntersectionObserver = class { constructor(callback) { this.callback = callback; this.observed = []; observer = this; } observe(element) { this.observed.push(element); } unobserve(element) { this.observed = this.observed.filter((item) => item !== element); } disconnect() { this.disconnected = true; } };
new Function(fs.readFileSync("static/js/motion.js", "utf8"))();
assert.strictEqual(observer.observed.filter((item) => item === reveal).length, 1);
observer.callback([{ isIntersecting: true, target: reveal }]);
assert(reveal.classList.contains("motion-visible"));
assert(!reveal.classList.contains("motion-settled"));
assert.strictEqual(reveal.listeners.transitionend.length, 1);
window.MotionSystem.refresh();
assert.strictEqual(reveal.listeners.transitionend.length, 1);
reveal.emit("transitionend", { target: reveal, propertyName: "filter" });
assert(!reveal.classList.contains("motion-settled"));
assert.strictEqual(reveal.listeners.transitionend.length, 1);
reveal.emit("transitionend", { target: {}, propertyName: "opacity" });
assert(!reveal.classList.contains("motion-settled"));
reveal.emit("transitionend", { target: reveal, propertyName: "opacity" });
assert(reveal.classList.contains("motion-settled"));
assert.strictEqual(reveal.listeners.transitionend.length, 0);
window.MotionSystem.refresh();
assert.strictEqual(reveal.listeners.transitionend.length, 0);

elements = [reveal, pending];
window.MotionSystem.refresh();
observer.callback([{ isIntersecting: true, target: pending }]);
assert.strictEqual(pending.listeners.transitionend.length, 1);
window.MotionSystem.destroy();
assert.strictEqual(pending.listeners.transitionend.length, 0);

const instantReveal = new Element({ "data-motion-reveal": "" });
const instantRoot = { classList: new ClassList(), querySelectorAll(selector) { return selector === "[data-motion-reveal]" ? [instantReveal] : []; } };
let instantObserver;
global.document = { documentElement: instantRoot, hidden: false, body: { scrollHeight: 100 }, querySelectorAll: instantRoot.querySelectorAll.bind(instantRoot), querySelector() { return null; }, addEventListener() {}, removeEventListener() {}, dispatchEvent() {} };
global.window = { matchMedia(query) { return { matches: query.includes("pointer: fine") }; }, innerHeight: 100, scrollY: 0, addEventListener() {}, removeEventListener() {}, getComputedStyle() { return { transitionDuration: "0s", transitionDelay: "0s", backgroundImage: "none" }; } };
global.requestAnimationFrame = () => 1; global.IntersectionObserver = class { constructor(callback) { this.callback = callback; instantObserver = this; } observe() {} unobserve() {} disconnect() {} };
new Function(fs.readFileSync("static/js/motion.js", "utf8"))();
instantObserver.callback([{ isIntersecting: true, target: instantReveal }]);
assert(instantReveal.classList.contains("motion-visible"));
assert(instantReveal.classList.contains("motion-settled"));
assert.strictEqual(instantReveal.listeners.transitionend, undefined);

const reducedReveal = new Element({ "data-motion-reveal": "" });
const reducedRoot = { classList: new ClassList(), querySelectorAll(selector) { return selector === "[data-motion-reveal]" ? [reducedReveal] : []; } };
global.document = { documentElement: reducedRoot, hidden: false, body: { scrollHeight: 100 }, querySelectorAll: reducedRoot.querySelectorAll.bind(reducedRoot), querySelector() { return null; }, addEventListener() {}, removeEventListener() {}, dispatchEvent() {} };
global.window = { matchMedia(query) { return { matches: query.includes("reduced") }; }, innerHeight: 100, scrollY: 0, addEventListener() {}, removeEventListener() {} };
global.requestAnimationFrame = undefined; global.IntersectionObserver = undefined;
new Function(fs.readFileSync("static/js/motion.js", "utf8"))();
assert(reducedReveal.classList.contains("motion-visible"));
assert(reducedReveal.classList.contains("motion-settled"));
'''
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_motion_topbar_transitions_its_webkit_and_standard_backdrop_filters(self):
        for source in (
            Path("static/css/index.css").read_text(encoding="utf-8"),
            Path("templates/guide.html").read_text(encoding="utf-8"),
            Path("templates/kozekilmu.html").read_text(encoding="utf-8"),
        ):
            topbar = re.search(r"\.topbar\s*\{([^}]*)\}", source)
            self.assertIsNotNone(topbar)
            self.assertRegex(topbar.group(1), r"-webkit-backdrop-filter\s+\.25s\s+ease")
            self.assertRegex(topbar.group(1), r"(?<!-)backdrop-filter\s+\.25s\s+ease")

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
assert(noApis.reveal.classList.contains("motion-settled"));
assert(!noApis.root.classList.contains("motion-enabled"));

let scheduled = 0;
const reduced = boot({ reduced: true, requestAnimationFrame() { scheduled += 1; return 1; }, observer: class {} });
assert.doesNotThrow(() => reduced.api.refresh());
const number = { textContent: "00" };
reduced.api.setNumber(number, 7);
assert.strictEqual(number.textContent, "7");
assert.strictEqual(scheduled, 1);
assert(reduced.root.classList.contains("motion-reduced"));
assert(reduced.reveal.classList.contains("motion-settled"));
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

    def test_runtime_syncs_topbar_threshold_and_preserves_numeric_string_width(self):
        script = r'''
const assert = require("assert");
const fs = require("fs");

class ClassList {
  constructor() { this.values = new Set(); }
  add(...names) { names.forEach((name) => this.values.add(name)); }
  remove(...names) { names.forEach((name) => this.values.delete(name)); }
  toggle(name, force) { if (force) this.add(name); else this.remove(name); }
  contains(name) { return this.values.has(name); }
}
class Element {
  constructor(attributes = {}) {
    this.attributes = attributes;
    this.classList = new ClassList();
    this.style = { setProperty() {} };
    this.textContent = "00";
    this.listeners = {};
  }
  getAttribute(name) { return this.attributes[name] ?? null; }
  addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
  removeEventListener() {}
  getBoundingClientRect() { return { left: 0, top: 0, width: 100, height: 100 }; }
}

const root = { classList: new ClassList(), querySelectorAll() { return []; } };
const topbar = new Element();
const progress = new Element();
const listeners = {};
global.document = {
  documentElement: root,
  hidden: false,
  body: { scrollHeight: 1100 },
  querySelectorAll: root.querySelectorAll.bind(root),
  querySelector(selector) { return selector === "#topbar" ? topbar : selector === "#scroll-progress" ? progress : null; },
  addEventListener(name, listener) { (listeners[name] ||= []).push(listener); },
  removeEventListener() {},
  dispatchEvent() {},
};
const windowListeners = {};
global.window = {
  matchMedia(query) { return { matches: query.includes("pointer: fine") }; },
  scrollY: 12,
  innerHeight: 100,
  addEventListener(name, listener) { (windowListeners[name] ||= []).push(listener); },
  removeEventListener() {},
};
const frames = new Map(); let nextId = 1;
global.requestAnimationFrame = (callback) => { const id = nextId++; frames.set(id, callback); return id; };
global.cancelAnimationFrame = (id) => frames.delete(id);
global.IntersectionObserver = class { constructor() {} observe() {} disconnect() {} };
global.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init.detail; } };
function runFrames(timestamp) {
  for (const [id, callback] of [...frames]) { frames.delete(id); callback(timestamp); }
}

new Function(fs.readFileSync("static/js/motion.js", "utf8"))();
runFrames(0);
assert(!topbar.classList.contains("is-scrolled"));
window.scrollY = 13;
windowListeners.scroll[0]();
runFrames(1);
assert(topbar.classList.contains("is-scrolled"));

const number = new Element();
window.MotionSystem.setNumber(number, "02");
runFrames(0);
runFrames(140);
assert.strictEqual(number.textContent, "01");
runFrames(280);
assert.strictEqual(number.textContent, "02");
window.MotionSystem.setNumber(number, 3);
runFrames(300);
runFrames(580);
assert.strictEqual(number.textContent, "3");
window.MotionSystem.setNumber(number, "not-a-number");
assert.strictEqual(number.textContent, "not-a-number");
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
assert(reveal.classList.contains("motion-settled"));
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
assert(observerReveal.classList.contains("motion-settled"));
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
    this.style = { values: {}, setProperty(name, value) { this.values[name] = value; }, removeProperty(name) { delete this.values[name]; }, getPropertyValue(name) { return this.values[name] || ""; } };
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
const softSurface = new Element({
  "data-motion-surface": "",
  "data-motion-tilt-strength": "0.4",
});
const blankStrengthSurface = new Element({ "data-motion-surface": "", "data-motion-tilt-strength": " " });
const malformedStrengthSurface = new Element({ "data-motion-surface": "", "data-motion-tilt-strength": "0.4oops" });
const negativeStrengthSurface = new Element({ "data-motion-surface": "", "data-motion-tilt-strength": "-1" });
const excessiveStrengthSurface = new Element({ "data-motion-surface": "", "data-motion-tilt-strength": "2" });
const surfaces = [surface, softSurface, blankStrengthSurface, malformedStrengthSurface, negativeStrengthSurface, excessiveStrengthSurface];
const parallax = new Element({ "data-motion-parallax": "0.55" });
const root = { classList: new ClassList(), querySelectorAll(selector) {
  if (selector === "[data-motion-reveal]") return [reveal];
  if (selector === "[data-motion-number]") return [number];
  if (selector === "[data-motion-surface]") return surfaces;
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
softSurface.listeners.pointerenter[0]({ clientX: 100, clientY: 0 });
for (const callback of [...queuedFrames.values()]) callback(650);
assert.strictEqual(softSurface.style.values["--motion-rx"], "0.24deg");
assert.strictEqual(softSurface.style.values["--motion-ry"], "0.24deg");
for (const invalidSurface of [blankStrengthSurface, malformedStrengthSurface]) {
  invalidSurface.listeners.pointerenter[0]({ clientX: 100, clientY: 0 });
  for (const callback of [...queuedFrames.values()]) callback(675);
  assert.strictEqual(invalidSurface.style.values["--motion-rx"], "0.6deg");
  assert.strictEqual(invalidSurface.style.values["--motion-ry"], "0.6deg");
}
negativeStrengthSurface.listeners.pointerenter[0]({ clientX: 100, clientY: 0 });
for (const callback of [...queuedFrames.values()]) callback(700);
assert.strictEqual(negativeStrengthSurface.style.values["--motion-rx"], "0.00deg");
assert.strictEqual(negativeStrengthSurface.style.values["--motion-ry"], "0.00deg");
excessiveStrengthSurface.listeners.pointerenter[0]({ clientX: 100, clientY: 0 });
for (const callback of [...queuedFrames.values()]) callback(725);
assert.strictEqual(excessiveStrengthSurface.style.values["--motion-rx"], "0.6deg");
assert.strictEqual(excessiveStrengthSurface.style.values["--motion-ry"], "0.6deg");
assert(surface.classList.contains("motion-surface-fallback"));
assert.strictEqual(surface.style.values["--motion-base-background"], "linear-gradient(#111, #222)");
assert.strictEqual(document.lastEvent.type, "motion:scroll-frame");
assert(Math.abs(Number.parseFloat(parallax.style.values["--motion-parallax-offset"])) <= 6.6);
window.MotionSystem.destroy();
assert(!root.classList.contains("motion-ready"));
for (const item of surfaces) assert.strictEqual(item.listeners.pointerenter.length, 0);
assert.strictEqual(surface.style.values["--motion-rx"], "0deg");
assert.strictEqual(parallax.style.values["--motion-parallax-offset"], "0px");
assert.strictEqual(surface.style.values["--motion-base-background"], undefined);
'''
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
