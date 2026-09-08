const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = path.resolve(__dirname, '../../static/js/theme.js');
assert.ok(fs.existsSync(script), 'Theme bootstrap script is missing');
const source = fs.readFileSync(script, 'utf8');
const KEY = 'gtd_theme_v1';

function page({stored = null, blocked = false, ready = false, controls = true} = {}) {
  const listeners = {};
  const changes = {};
  const writes = [];
  const storage = {
    getItem(key) {
      if (blocked) throw new Error('Storage blocked');
      return key === KEY ? stored : null;
    },
    setItem(key, value) {
      if (blocked) throw new Error('Storage blocked');
      writes.push([key, value]);
      stored = value;
    },
  };
  const toggle = {checked: false, dataset: {}, addEventListener: (name, fn) => { changes[name] = fn; }};
  const meta = {content: '', setAttribute(name, value) { this[name] = value; }};
  const root = {dataset: {theme: 'dark'}, style: {}};
  const document = {
    documentElement: root,
    readyState: ready ? 'complete' : 'loading',
    querySelector(selector) {
      if (!controls || this.readyState === 'loading') return null;
      return selector === '#theme-toggle' ? toggle : selector === 'meta[name="theme-color"]' ? meta : null;
    },
    addEventListener: (name, fn) => { listeners[name] = fn; },
  };
  const window = {localStorage: storage, addEventListener: (name, fn) => { listeners[name] = fn; }};
  vm.runInNewContext(source, {document, window});
  return {
    root, toggle, meta, writes,
    ready() { document.readyState = 'complete'; listeners.DOMContentLoaded?.(); },
    change(light) { toggle.checked = light; changes.change(); },
    storage(key, newValue) { listeners.storage({key, newValue, storageArea: storage}); },
    restore(value) { stored = value; listeners.pageshow?.({persisted: true}); },
  };
}

for (const stored of [null, '', 'garbage', 'LIGHT', 'dark', 'light']) {
  const p = page({stored});
  const expected = stored === 'light' ? 'light' : 'dark';
  assert.equal(p.root.dataset.theme, expected, 'Theme must apply before DOMContentLoaded');
  assert.equal(p.root.style.colorScheme, expected, 'Native controls must match before CSS loads');
  p.ready();
  assert.equal(p.toggle.checked, expected === 'light');
  assert.ok(/^#[0-9a-f]{6}$/i.test(p.meta.content), 'Browser theme color must be set');
  assert.deepEqual(p.writes, [], 'Reading settings must not rewrite storage');
}

const p = page();
p.ready();
const darkColor = p.meta.content;
p.change(true);
assert.equal(p.root.dataset.theme, 'light');
assert.equal(p.root.style.colorScheme, 'light');
assert.notEqual(p.meta.content, darkColor);
assert.deepEqual(p.writes, [[KEY, 'light']]);
const nextPage = page({stored: p.writes.at(-1)[1], ready: true});
assert.equal(nextPage.root.dataset.theme, 'light', 'Navigation must restore selection');
assert.equal(nextPage.toggle.checked, true);
p.change(false);
assert.equal(p.root.dataset.theme, 'dark');
assert.deepEqual(p.writes.at(-1), [KEY, 'dark']);

const sync = page({ready: true});
sync.storage(KEY, 'light');
assert.equal(sync.root.dataset.theme, 'light');
assert.equal(sync.toggle.checked, true);
sync.storage('unrelated', 'dark');
assert.equal(sync.root.dataset.theme, 'light');
sync.storage(KEY, 'invalid');
assert.equal(sync.root.dataset.theme, 'dark');
sync.storage(KEY, 'light');
sync.storage(null, null);
assert.equal(sync.root.dataset.theme, 'dark', 'Cleared storage resets to default');
assert.equal(sync.toggle.checked, false);
assert.deepEqual(sync.writes, [], 'Cross-tab synchronization must not loop');
sync.restore('light');
assert.equal(sync.root.dataset.theme, 'light', 'Back-forward cache must restore the latest preference');
assert.equal(sync.toggle.checked, true);

const denied = page({blocked: true, ready: true});
assert.equal(denied.root.dataset.theme, 'dark');
denied.change(true);
assert.equal(denied.root.dataset.theme, 'light', 'Blocked storage must not disable switching');
assert.equal(denied.root.style.colorScheme, 'light');
assert.doesNotThrow(() => page({ready: true, controls: false}));
console.log('Theme runtime: early boot, persistence, switch, storage sync, blocked storage passed');
