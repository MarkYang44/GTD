"""Behavioral coverage for the opt-in calm motion profile."""
import subprocess
import unittest


class CalmMotionTests(unittest.TestCase):
    def test_calm_skips_pointer_and_parallax_work_but_preserves_lifecycle(self):
        script = r'''
const assert = require("assert");
const fs = require("fs");
const source = fs.readFileSync("static/js/motion.js", "utf8");
class Element {
  constructor(attributes = {}) {
    this.attributes = attributes;
    const values = new Set();
    this.classList = {
      add(...names) { names.forEach(name => values.add(name)); },
      remove(...names) { names.forEach(name => values.delete(name)); },
      contains(name) { return values.has(name); },
      toggle(name, force) { if (force) values.add(name); else values.delete(name); },
    };
    this.listeners = {};
    this.style = { values: {}, setProperty(name, value) { this.values[name] = value; } };
    this.textContent = "00";
  }
  getAttribute(name) { return this.attributes[name] ?? null; }
  addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
  removeEventListener(name, listener) { this.listeners[name] = (this.listeners[name] || []).filter(item => item !== listener); }
  emit(name, event) { for (const listener of [...(this.listeners[name] || [])]) listener(event); }
}
function boot({ reduced = false, fail = false } = {}) {
  const root = new Element(); root.dataset = { motionProfile: "calm" };
  const reveal = new Element({ "data-motion-reveal": "" });
  const surface = new Element({ "data-motion-surface": "" });
  const parallax = new Element({ "data-motion-parallax": "0.55" });
  const topbar = new Element();
  const doc = new Element(); const win = new Element();
  const queried = [];
  Object.assign(doc, {
    documentElement: root, hidden: false, body: { scrollHeight: 1100 },
    querySelectorAll(selector) {
      queried.push(selector);
      return selector === "[data-motion-reveal]" ? [reveal] : selector === "[data-motion-surface]" ? [surface] : selector === "[data-motion-parallax]" ? [parallax] : [];
    },
    querySelector(selector) { return selector === "#topbar" ? topbar : null; },
    dispatchEvent(event) { if (fail) throw new Error("frame failure"); this.lastEvent = event; },
  });
  Object.assign(win, {
    innerHeight: 100, scrollY: 0,
    matchMedia(query) { return { matches: query.includes("reduced") ? reduced : true }; },
    getComputedStyle() { return { transitionDuration: reduced ? "0s" : "0.28s" }; },
  });
  global.document = doc; global.window = win;
  const frames = new Map(); let nextId = 0; let observer;
  global.requestAnimationFrame = callback => { frames.set(++nextId, callback); return nextId; };
  global.cancelAnimationFrame = id => frames.delete(id);
  global.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init.detail; } };
  global.IntersectionObserver = class {
    constructor(callback) { this.callback = callback; observer = this; }
    observe() {} unobserve() {} disconnect() { this.disconnected = true; }
  };
  new Function(source)();
  return { root, reveal, surface, parallax, topbar, doc, win, queried, frames, observer,
    run(time) { for (const [id, callback] of [...frames]) { frames.delete(id); callback(time); } } };
}
const calm = boot();
assert.deepStrictEqual(Object.keys(calm.surface.listeners), [], "calm must not install pointer listeners");
assert(!calm.root.classList.contains("motion-fine-pointer"));
calm.run(0);
calm.win.scrollY = 500; calm.win.emit("scroll"); calm.run(1);
calm.win.MotionSystem.refresh(); calm.run(2);
assert.deepStrictEqual(calm.parallax.style.values, {}, "calm must not change parallax offsets");
assert(calm.topbar.classList.contains("is-scrolled"));
assert.strictEqual(calm.doc.lastEvent.detail.progress, 0.5);
calm.observer.callback([{ target: calm.reveal, isIntersecting: true }]);
assert(calm.reveal.classList.contains("motion-visible"));
calm.reveal.emit("transitionend", { target: calm.reveal, propertyName: "opacity" });
assert(calm.reveal.classList.contains("motion-settled"));
const number = new Element();
calm.win.MotionSystem.setNumber(number, "08"); calm.run(10); calm.run(150);
assert.strictEqual(number.textContent, "04");
calm.doc.hidden = true; calm.doc.emit("visibilitychange");
assert.strictEqual(number.textContent, "08");
assert.strictEqual(calm.frames.size, 0);
calm.doc.hidden = false; calm.doc.emit("visibilitychange");
calm.win.MotionSystem.setNumber(number, "03"); calm.run(200);
calm.win.MotionSystem.destroy();
assert.strictEqual(number.textContent, "03");
assert.strictEqual(calm.frames.size, 0);
assert(calm.observer.disconnected);
assert(!calm.queried.includes("[data-motion-surface]"));
assert(!calm.queried.includes("[data-motion-parallax]"));
const failing = boot({ fail: true });
failing.win.MotionSystem.setNumber(number, "09"); failing.run(0);
assert.strictEqual(number.textContent, "09");
assert(failing.reveal.classList.contains("motion-visible"));
assert(failing.reveal.classList.contains("motion-settled"));
assert(!failing.root.classList.contains("motion-ready"));
assert.deepStrictEqual(failing.parallax.style.values, {});
const reduced = boot({ reduced: true });
assert(reduced.reveal.classList.contains("motion-settled"));
reduced.win.MotionSystem.setNumber(number, "05");
assert.strictEqual(number.textContent, "05");
reduced.win.MotionSystem.destroy();
'''
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
