'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

class Element {
  constructor() {
    this.textContent = '';
    this.innerHTML = '';
    this.value = '';
    this.dataset = {};
    this.hidden = true;
    this.classList = {add() {}, remove() {}};
  }
  addEventListener() {}
  setAttribute() {}
  replaceChildren() { this.innerHTML = ''; }
  appendChild() {}
  querySelectorAll() { return []; }
  contains() { return false; }
  focus() {}
  scrollIntoView() {}
}

const nodes = new Map();
let language = 'zh';
const document = {
  getElementById(id) {
    if (!nodes.has(id)) nodes.set(id, new Element());
    return nodes.get(id);
  },
  querySelectorAll() { return []; },
  createElement() { return new Element(); },
  createTextNode(textContent) { return {textContent}; },
  addEventListener() {},
};
const window = {
  GtdLanguage: {
    get language() { return language; },
    t(zh, en, params = {}) {
      return (language === 'en' ? en : zh).replace(/\{(\w+)\}/g, (_, key) => params[key] ?? `{${key}}`);
    },
  },
  setTimeout() {},
};
const context = vm.createContext({
  document,
  window,
  localStorage: {getItem() { return null; }},
  fetch() { return new Promise(() => {}); },
  setTimeout() {},
  clearTimeout() {},
  console,
});
vm.runInContext(fs.readFileSync('static/js/task_api.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('static/js/index.js', 'utf8'), context);

function render(tasks, extra = {}) {
  context.__batch = {tasks, ...extra};
  return vm.runInContext('renderTaskList(__batch, new Set())', context);
}

// Running downloads show a progress bar beside the speed and time details.
let html = render([{
  id: 'run', url: 'https://www.bilibili.com/video/BV1', title: 'Concert', status: 'running',
  progress: {percent_text: '63.2%', speed_text: '12.4 MiB/s', eta_text: '00:42', total_size_text: '812.0 MiB'},
}]);
assert.match(html, /role="progressbar"/);
assert.match(html, /aria-valuenow="63.2"/);
assert.match(html, /width: 63\.2%/);
assert.match(html, /12\.4 MiB\/s/);

// Without a reported percentage there is no bar to mislead.
html = render([{id: 'run', url: 'u', status: 'running', progress: {speed_text: '计算中', eta_text: '计算中'}}]);
assert.doesNotMatch(html, /role="progressbar"/);

// The media title leads and the URL follows; generated titles are localized.
html = render([{id: 'a', url: 'https://youtu.be/one', title: 'Late night session', status: 'queued'}]);
assert.ok(html.indexOf('Late night session') < html.indexOf('https://youtu.be/one'));
language = 'en';
html = render([{id: 'b', url: 'https://youtu.be/two', title: '第 3 项', status: 'queued'}]);
assert.match(html, /Item 3/);
assert.doesNotMatch(html, /[一-鿿]/);
language = 'zh';

// Attempt history appears only after a retry.
const attempt = number => ({number, status: 'failed', started_at: 1700000000, finished_at: 1700000010, output_version: 1});
html = render([{
  id: 'c', url: 'u', status: 'failed', can_retry: true, attempt_count: 1, attempts: [attempt(1)],
  error: {error_code: 'AUTH_REQUIRED', message: '当前凭证无法访问该内容', suggestion: '请更新对应平台 Cookie 后重试'},
}]);
assert.doesNotMatch(html, /task-attempts/);
assert.match(html, /当前凭证无法访问该内容/);
assert.match(html, /请更新对应平台 Cookie 后重试/);
assert.match(html, /AUTH_REQUIRED/);
html = render([{
  id: 'c', url: 'u', status: 'failed', can_retry: true, attempt_count: 2, attempts: [attempt(1), attempt(2)],
  error: {error_code: 'AUTH_REQUIRED', message: 'x'},
}]);
assert.match(html, /task-attempts/);

// Saved paths select in one click.
html = render([{
  id: 'd', url: 'u', status: 'completed', can_redownload: true,
  result: {title: 'Done', filepath: '/tmp/Done.mp4', resolution: '1920x1080', filesize: '1 GiB'},
}], {media_type: 'video'});
assert.match(html, /class="task-path-value"[^>]*>\/tmp\/Done\.mp4</);

console.log('Task render harness passed');
