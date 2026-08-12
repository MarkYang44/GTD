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
assert.strictEqual(document.lastEvent.type, "motion:scroll-frame");
assert(Math.abs(Number.parseFloat(parallax.style.values["--motion-parallax-offset"])) <= 6.6);
window.MotionSystem.destroy();
assert(!root.classList.contains("motion-ready"));
assert.strictEqual(surface.listeners.pointerenter.length, 0);
assert.strictEqual(surface.style.values["--motion-rx"], "0deg");
assert.strictEqual(parallax.style.values["--motion-parallax-offset"], "0px");
'''
        result = subprocess.run(
            ["node", "-e", script], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
