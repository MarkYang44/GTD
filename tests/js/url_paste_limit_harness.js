'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

class Element {
  constructor() {
    this.classList = {add() {}, remove() {}};
    this.dataset = {};
    this.disabled = false;
    this.hidden = true;
    this.innerHTML = '';
    this.listeners = {};
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
  setAttribute() {}
  get offsetWidth() { return 0; }
}

const elements = new Map();
const documentListeners = {};
let language = 'zh';
const alerts = [];
const alertValues = [];
const timers = [];
const document = {
  hidden: false,
  addEventListener(name, listener) { (documentListeners[name] ||= []).push(listener); },
  createElement() { return new Element(); },
  createTextNode(textContent) { return {textContent}; },
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, new Element());
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
  setTimeout(callback) { timers.push(callback); },
};
const context = vm.createContext({
  alert(message) {
    alerts.push(message);
    alertValues.push(elements.get('videoUrls').value);
  },
  clearTimeout() {},
  console,
  document,
  fetch() { return Promise.reject(new Error('offline')); },
  localStorage: {getItem() { return null; }, removeItem() {}, setItem() {}},
  setTimeout() {},
  window,
});

vm.runInContext(fs.readFileSync('static/js/index.js', 'utf8'), context);

function lines(first, last) {
  return Array.from({length: last - first + 1}, (_, index) => `url-${first + index}`).join('\n');
}

function nonEmptyLineCount(value) {
  return value.split('\n').map(line => line.trim()).filter(Boolean).length;
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
  }
  while (timers.length) timers.shift()();
  return prevented;
}

const video = elements.get('videoUrls');
const audio = elements.get('audioUrls');

video.value = lines(1, 18);
alerts.length = 0;
alertValues.length = 0;
assert.strictEqual(paste(video, `\n${lines(19, 20)}`), false);
assert.strictEqual(nonEmptyLineCount(video.value), 20);
assert.deepStrictEqual(alerts, ['已达到 20 行链接上限，请勿继续粘贴。']);
assert.strictEqual(
  nonEmptyLineCount(alertValues[0]),
  20,
  'the exact-limit notice must appear after the accepted paste is visible',
);

video.value = lines(1, 18);
const original = video.value;
alerts.length = 0;
assert.strictEqual(paste(video, `\n${lines(19, 21)}`), true);
assert.strictEqual(video.value, original, 'an overflowing paste must be rejected in full');
assert.strictEqual(alerts.length, 1);

video.value = lines(1, 20);
alerts.length = 0;
const replaceStart = video.value.indexOf('url-19');
assert.strictEqual(paste(video, 'replacement', replaceStart, video.value.length), false);
assert.strictEqual(nonEmptyLineCount(video.value), 19);
assert.deepStrictEqual(alerts, []);

audio.value = lines(1, 20);
alerts.length = 0;
assert.strictEqual(paste(audio, '\nextra'), true);
assert.strictEqual(nonEmptyLineCount(audio.value), 20);
assert.strictEqual(alerts.length, 1);

language = 'en';
audio.value = lines(1, 19);
alerts.length = 0;
assert.strictEqual(paste(audio, '\nurl-20'), false);
assert.match(alerts[0], /20-line URL limit/);
assert.doesNotMatch(alerts[0], /[\u4e00-\u9fff]/);

console.log('URL paste limit harness passed');
