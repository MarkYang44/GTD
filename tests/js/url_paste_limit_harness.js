'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

class ClassList {
  constructor() { this.values = new Set(); }
  add(...names) { names.forEach(name => this.values.add(name)); }
  remove(...names) { names.forEach(name => this.values.delete(name)); }
  contains(name) { return this.values.has(name); }
}

class Element {
  constructor(id = '') {
    this.id = id;
    this.attributes = {};
    this.classList = new ClassList();
    this.dataset = {};
    this.disabled = false;
    this.hidden = true;
    this.innerHTML = '';
    this.listeners = {};
    this.placeholder = '';
    this.selectionEnd = 0;
    this.selectionStart = 0;
    this.style = {};
    this.textContent = '';
    this.value = '';
  }
  addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
  appendChild() {}
  contains() { return false; }
  focus() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
  replaceChildren() { this.innerHTML = ''; }
  scrollIntoView() {}
  setAttribute(name, value) { this.attributes[name] = String(value); }
  get offsetWidth() { return 0; }
}

const elements = new Map();
const documentListeners = {};
const requests = [];
let language = 'zh';
const document = {
  hidden: false,
  addEventListener(name, listener) { (documentListeners[name] ||= []).push(listener); },
  createElement() { return new Element(); },
  createTextNode(textContent) { return {textContent}; },
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, new Element(id));
    return elements.get(id);
  },
  querySelector() { return null; },
  querySelectorAll() { return []; },
};
const window = {
  GtdLanguage: {
    get language() { return language; },
    t(zh, en, params = {}) {
      return (language === 'en' ? en : zh).replace(
        /\{(\w+)\}/g,
        (_, key) => params[key] ?? `{${key}}`,
      );
    },
  },
  MotionSystem: {},
  setTimeout() {},
};
const context = vm.createContext({
  alert() { throw new Error('feedback must be inline; alert() blocks the page'); },
  clearTimeout() {},
  console,
  document,
  fetch(url) {
    requests.push(url);
    return Promise.reject(new Error('offline'));
  },
  localStorage: {getItem() { return null; }, removeItem() {}, setItem() {}},
  setTimeout() {},
  window,
});

vm.runInContext(fs.readFileSync('static/js/task_api.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('static/js/index.js', 'utf8'), context);

function lines(first, last) {
  return Array.from({length: last - first + 1}, (_, index) => `url-${first + index}`).join('\n');
}

function nonEmptyLineCount(value) {
  return value.split('\n').map(line => line.trim()).filter(Boolean).length;
}

function input(element) {
  (element.listeners.input || []).forEach(listener => listener({target: element}));
}

function paste(element, text, start = element.value.length, end = start) {
  element.selectionStart = start;
  element.selectionEnd = end;
  let prevented = false;
  const event = {
    clipboardData: {getData(type) { return type === 'text' ? text : ''; }},
    preventDefault() { prevented = true; },
  };
  const listeners = element.listeners.paste || [];
  assert.strictEqual(listeners.length, 1, 'each URL input must register one paste listener');
  listeners[0](event);
  if (!prevented) {
    element.value = element.value.slice(0, start) + text + element.value.slice(end);
    input(element);
  }
  return prevented;
}

function keydown(element, init) {
  let prevented = false;
  (element.listeners.keydown || []).forEach(listener => listener({
    key: 'Enter',
    preventDefault() { prevented = true; },
    ...init,
  }));
  return prevented;
}

const video = elements.get('videoUrls');
const audio = elements.get('audioUrls');
const videoNotice = elements.get('videoNotice');
const audioNotice = elements.get('audioNotice');
const videoCount = elements.get('videoUrlCount');
const audioCount = elements.get('audioUrlCount');

assert.strictEqual(videoCount.hidden, true, 'an empty box shows no counter');

// Reaching the limit is accepted, counted, and explained beside the box.
video.value = lines(1, 18);
input(video);
assert.strictEqual(videoCount.hidden, false);
assert.strictEqual(videoCount.textContent, '18 / 20 行');
assert.strictEqual(paste(video, `\n${lines(19, 20)}`), false);
assert.strictEqual(nonEmptyLineCount(video.value), 20);
assert.strictEqual(videoNotice.hidden, false);
assert.match(videoNotice.textContent, /20 行上限/);
assert.strictEqual(videoCount.textContent, '20 / 20 行');
assert.ok(videoCount.classList.contains('is-full'));

// An overflowing paste is rejected in full.
video.value = lines(1, 18);
input(video);
const original = video.value;
assert.strictEqual(paste(video, `\n${lines(19, 21)}`), true);
assert.strictEqual(video.value, original, 'an overflowing paste must be rejected in full');
assert.strictEqual(videoNotice.hidden, false);
assert.match(videoNotice.textContent, /未添加/);

// Dropping back under the limit clears the limit notice.
video.value = lines(1, 20);
input(video);
const replaceStart = video.value.indexOf('url-19');
assert.strictEqual(paste(video, 'replacement', replaceStart, video.value.length), false);
assert.strictEqual(nonEmptyLineCount(video.value), 19);
assert.strictEqual(videoNotice.hidden, true);
assert.strictEqual(videoCount.textContent, '19 / 20 行');
assert.ok(!videoCount.classList.contains('is-full'));

// Each card keeps its own feedback.
audio.value = lines(1, 20);
input(audio);
assert.strictEqual(paste(audio, '\nextra'), true);
assert.strictEqual(nonEmptyLineCount(audio.value), 20);
assert.strictEqual(audioNotice.hidden, false);
assert.strictEqual(videoNotice.hidden, true);

// Notices and counters follow the language switch without new requests.
const requestsBeforeSwitch = requests.length;
language = 'en';
(documentListeners['gtd:languagechange'] || []).forEach(listener => listener({detail: {language}}));
assert.match(audioNotice.textContent, /20-line limit/);
assert.doesNotMatch(audioNotice.textContent, /[一-鿿]/);
assert.strictEqual(audioCount.textContent, '20 / 20 lines');
assert.strictEqual(requests.length, requestsBeforeSwitch);

// Ctrl/Cmd+Enter submits the box it was pressed in; an empty box explains what to do.
video.value = '';
input(video);
assert.strictEqual(videoCount.hidden, true);
assert.strictEqual(keydown(video, {ctrlKey: true}), true);
assert.strictEqual(videoNotice.hidden, false);
assert.match(videoNotice.textContent, /Paste at least one video link/);
assert.ok(!requests.includes('/api/preview'));
video.value = 'https://youtu.be/example';
input(video);
assert.strictEqual(videoNotice.hidden, true, 'typing a link clears the empty-box notice');
assert.strictEqual(keydown(audio, {}), false, 'plain Enter keeps adding lines');
assert.strictEqual(keydown(video, {key: 'Enter', ctrlKey: true, isComposing: true}), false, 'IME composition is left alone');
assert.strictEqual(keydown(video, {metaKey: true}), true);
assert.ok(requests.includes('/api/preview'));

console.log('URL input feedback harness passed');
