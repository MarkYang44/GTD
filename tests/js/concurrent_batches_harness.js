'use strict';

// Drives the real download page script through overlapping batches: a fake DOM,
// a scripted server, and manual timers so every polling sweep is explicit.
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
    this.listeners = {};
    this.style = {};
    this.textContent = '';
    this.value = '';
    this.childNodes = [];
    this.html = '';
    this.htmlWrites = 0;
  }
  get innerHTML() { return this.html; }
  set innerHTML(value) { this.html = String(value); this.childNodes = []; this.htmlWrites += 1; }
  get children() { return this.childNodes; }
  replaceChildren(...nodes) { this.childNodes = nodes; this.html = ''; }
  appendChild(node) { this.childNodes.push(node); return node; }
  addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  contains() { return false; }
  focus() {}
  scrollIntoView() { scrolledTo.push(this.id); }
  get offsetWidth() { return 0; }
}

const elements = new Map();
const documentListeners = {};
const scrolledTo = [];
let language = 'zh';
const document = {
  hidden: false,
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, new Element(id));
    return elements.get(id);
  },
  createElement() { return new Element(); },
  createTextNode(textContent) { return {textContent}; },
  querySelector(selector) {
    return selector === 'input[name="audioFormat"]:checked' ? {value: 'flac'} : null;
  },
  querySelectorAll() { return []; },
  addEventListener(name, listener) { (documentListeners[name] ||= []).push(listener); },
};

const timers = new Map();
let lastTimerId = 0;

// A scripted local server. Batch snapshots mirror TaskManager._public_batch.
const server = {
  batches: new Map(),
  history: [],
  previewReplies: [],
  downloadReplies: [],
  heldBatchReads: new Map(),
  log: [],
  offline: false,
  inFlight: 0,
  maxInFlight: 0,
};

function reply(status, data) {
  return {ok: status >= 200 && status < 300, status, json: async () => JSON.parse(JSON.stringify(data))};
}

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return {promise, resolve};
}

function readBatch(id) {
  server.inFlight += 1;
  server.maxInFlight = Math.max(server.maxInFlight, server.inFlight);
  const held = server.heldBatchReads.get(id);
  server.heldBatchReads.delete(id);
  const answer = held ? held.promise
    : server.offline ? Promise.reject(new Error('offline'))
      : Promise.resolve(server.batches.has(id) ? reply(200, server.batches.get(id))
        : reply(404, {error_code: 'BATCH_NOT_FOUND'}));
  return answer.finally(() => { server.inFlight -= 1; });
}

function fetch(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  server.log.push(`${method} ${url}`);
  if (method === 'GET' && url.startsWith('/api/batch/')) return readBatch(url.slice('/api/batch/'.length));
  if (url === '/api/capabilities') {
    return Promise.resolve(reply(200, {aria2c_available: true, folder_picker_available: false, default_download_dir: '/downloads'}));
  }
  if (url === '/api/batches') return Promise.resolve(reply(200, {batches: server.history}));
  if (url === '/api/preview') return Promise.resolve(server.previewReplies.shift());
  if (url === '/api/download') {
    server.lastDownload = JSON.parse(options.body);
    return Promise.resolve(server.downloadReplies.shift());
  }
  const retryAll = /^\/api\/batch\/([^/]+)\/retry-failed$/.exec(url);
  if (retryAll) {
    const snapshot = server.batches.get(retryAll[1]);
    setBatch(retryAll[1], snapshot.media_type, snapshot.tasks.map(task => (
      task.status === 'failed' ? taskState(task.id, task.title, 'queued') : task)));
    return Promise.resolve(reply(200, server.batches.get(retryAll[1])));
  }
  if (/^\/api\/batch\/[^/]+\/task\/[^/]+\/(cancel|retry|redownload)$/.test(url)) return Promise.resolve(reply(200, {}));
  return Promise.resolve(reply(404, {}));
}

function taskState(id, title, status, extra = {}) {
  return {
    id, url: `https://youtu.be/${id}`, title, status, platform: 'youtube', progress: null,
    postprocessing: null, result: null, error: status === 'failed'
      ? {error_code: 'NETWORK_TIMEOUT', message: '网络连接源站超时', suggestion: '', retryable: true} : null,
    attempt_count: 1, attempts: [], speed_mode_used: 'standard', turbo_fallback: false,
    can_cancel: status === 'queued' || status === 'running',
    can_retry: status === 'failed' || status === 'cancelled',
    can_redownload: status === 'completed',
    ...extra,
  };
}

function setBatch(id, mediaType, tasks) {
  const count = status => tasks.filter(task => task.status === status).length;
  server.batches.set(id, {
    id, media_type: mediaType, audio_format: mediaType === 'audio' ? 'flac' : 'mp3',
    speed_mode: 'standard', download_dir: '/downloads', subtitle_options: {}, total: tasks.length,
    active: count('running') + count('running_uninterruptible'), queued: count('queued'),
    completed: count('completed'), failed: count('failed'), cancelled: count('cancelled'),
    all_done: tasks.every(task => ['completed', 'failed', 'cancelled'].includes(task.status)),
    tasks,
  });
}

function summary(id, mediaType) {
  const snapshot = server.batches.get(id);
  const {tasks, ...rest} = snapshot;
  return {...rest, created_at: 1700000000, media_type: mediaType};
}

const window = {
  GtdLanguage: {
    get language() { return language; },
    t(zh, en, params = {}) {
      return (language === 'en' ? en : zh).replace(/\{(\w+)\}/g, (_, key) => params[key] ?? `{${key}}`);
    },
  },
  setTimeout() {},
};
const storage = new Map();
const context = vm.createContext({
  console,
  document,
  fetch,
  window,
  localStorage: {getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)},
  setTimeout(fn, delay = 0) { lastTimerId += 1; timers.set(lastTimerId, {fn, delay}); return lastTimerId; },
  clearTimeout(id) { timers.delete(id); },
});
vm.runInContext(fs.readFileSync('static/js/task_api.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('static/js/index.js', 'utf8'), context);

const el = id => document.getElementById(id);
const run = source => vm.runInContext(source, context);
async function settle() {
  for (let round = 0; round < 6; round += 1) await new Promise(resolve => setImmediate(resolve));
}
// Fires the polling timer the page scheduled, i.e. one sweep.
async function sweep() {
  const due = [...timers.values()];
  timers.clear();
  due.forEach(timer => timer.fn());
  await settle();
}
const pollDelays = () => [...timers.values()].map(timer => timer.delay);
const groups = () => el('task-container').children;
const panelHtml = () => groups().map(group => group.innerHTML).join('\n');
const batchReads = () => server.log.filter(entry => entry.startsWith('GET /api/batch/'));
function handlersIn(html) {
  return [...html.matchAll(/onclick="(operateTask\([^"]*\))"/g)].map(match => match[1].replaceAll('&#39;', "'"));
}
function cardState(mediaType) {
  return {
    links: el(`${mediaType}Urls`).disabled,
    download: el(`${mediaType}DownloadButton`).disabled,
    folder: el(`${mediaType}DownloadDir`).disabled,
    turbo: el(`${mediaType}TurboToggle`).disabled,
  };
}
const usable = {links: false, download: false, folder: false, turbo: false};
const locked = {links: true, download: true, folder: true, turbo: true};

function queueSingle(mediaType, batchId) {
  server.previewReplies.push(reply(200, {
    preview_id: `preview-${batchId}`, title: batchId, title_is_generated: false, is_single: true,
    requires_selection: false, entries: [{id: `entry-${batchId}`, title: batchId, position: 1, selectable: true}],
  }));
  server.downloadReplies.push(reply(200, {batch_id: batchId, task_count: server.batches.get(batchId).total, download_dir: '/downloads'}));
}

async function submitSingle(mediaType, batchId) {
  queueSingle(mediaType, batchId);
  el(`${mediaType}Urls`).value = `https://youtu.be/${batchId}`;
  await run(`startDownload('${mediaType}')`);
  await settle();
}

(async () => {
  await settle();

  // A card waits only for its own links; the other card and history stay usable.
  setBatch('A', 'video', [
    taskState('a1', 'Alpine ride', 'running', {progress: {percent_text: '40%', speed_text: '2 MiB/s', eta_text: '00:30'}}),
    taskState('a2', 'Boat trip', 'queued'),
    taskState('a3', 'Canyon walk', 'queued'),
  ]);
  const previewGate = deferred();
  server.previewReplies.push(previewGate.promise);
  el('videoUrls').value = 'https://youtu.be/A';
  const firstSubmission = run("startDownload('video')");
  await settle();
  assert.deepStrictEqual(cardState('video'), locked, 'links being prepared are frozen until the server answers');
  assert.strictEqual(el('videoDanmakuToggle').disabled, true);
  assert.deepStrictEqual(cardState('audio'), usable, 'the other card stays usable while one card prepares links');
  assert.strictEqual(el('batchHistory').disabled, false);
  assert.match(el('task-title').textContent, /正在解析输入/, 'an empty panel still says what is happening');
  server.downloadReplies.push(reply(200, {batch_id: 'A', task_count: 3, download_dir: '/downloads'}));
  previewGate.resolve(reply(200, {
    preview_id: 'preview-A', title: 'A', title_is_generated: false, is_single: true, requires_selection: false,
    entries: [{id: 'entry-A', title: 'A', position: 1, selectable: true}],
  }));
  await firstSubmission;
  await settle();

  // Once the server accepts a batch, both cards are free while it downloads.
  assert.deepStrictEqual(cardState('video'), usable, 'an accepted batch releases its card');
  assert.deepStrictEqual(cardState('audio'), usable);
  assert.strictEqual(el('videoDanmakuToggle').disabled, false);
  assert.strictEqual(el('videoUrls').value, '', 'the box clears for the next batch');
  assert.strictEqual(groups().length, 1);
  assert.match(panelHtml(), /Alpine ride/);
  assert.doesNotMatch(panelHtml(), /task-group-header/, 'a single batch keeps the plain panel layout');
  assert.strictEqual(el('task-title').textContent, '视频下载任务');
  assert.strictEqual(el('task-summary').textContent, '共 3 个 · 完成 0 · 失败 0 · 取消 0');
  assert.strictEqual(el('metric-active').textContent, '01');
  assert.strictEqual(el('metric-queue').textContent, '02');
  assert.ok(scrolledTo.includes('task-card'), 'the page shows the panel when a batch starts');
  assert.ok(server.log.filter(entry => entry === 'GET /api/batches').length >= 2, 'history refreshes after a submission');

  // A second submission shows its rows above the first batch while it is sent.
  setBatch('B', 'audio', [
    taskState('b1', 'Blue hour', 'running'),
    taskState('b2', 'Coastline', 'queued'),
  ]);
  const downloadGate = deferred();
  server.previewReplies.push(reply(200, {
    preview_id: 'preview-B', title: 'B', title_is_generated: false, is_single: true, requires_selection: false,
    entries: [{id: 'entry-B', title: 'B', position: 1, selectable: true}],
  }));
  server.downloadReplies.push(downloadGate.promise);
  el('audioUrls').value = 'https://youtu.be/B';
  const secondSubmission = run("startDownload('audio')");
  await settle();
  assert.strictEqual(groups().length, 2, 'submitting never hides a running batch');
  assert.match(groups()[1].innerHTML, /Alpine ride/);
  assert.match(groups()[0].innerHTML, /等待可用下载槽位/);
  assert.strictEqual(el('metric-queue').textContent, '03', 'rows being submitted count as queued');
  downloadGate.resolve(reply(200, {batch_id: 'B', task_count: 2, download_dir: '/downloads'}));
  await secondSubmission;
  await settle();

  // Both batches stay listed, newest first, and the metrics add them up.
  assert.strictEqual(groups().length, 2);
  assert.match(groups()[0].innerHTML, /Blue hour/);
  assert.match(groups()[1].innerHTML, /Alpine ride/);
  assert.match(groups()[0].innerHTML, /task-group-header/);
  assert.match(groups()[0].innerHTML, /源 FLAC 音频下载任务/);
  assert.match(groups()[1].innerHTML, /视频下载任务/);
  assert.strictEqual(el('task-title').textContent, '下载任务');
  assert.strictEqual(el('task-summary').textContent, '2 个批次 · 进行中 2 · 已结束 0');
  assert.strictEqual(el('metric-active').textContent, '02');
  assert.strictEqual(el('metric-queue').textContent, '03');
  assert.deepStrictEqual(cardState('audio'), usable);

  // Each sweep reads every running batch, one request at a time.
  server.log = [];
  await sweep();
  assert.deepStrictEqual(batchReads(), ['GET /api/batch/B', 'GET /api/batch/A']);
  assert.strictEqual(server.maxInFlight, 1, 'polling stays serial across batches');
  assert.deepStrictEqual(pollDelays(), [800]);

  // Only the batch whose data changed is rewritten, so selections elsewhere survive.
  const writesBefore = groups().map(group => group.htmlWrites);
  const a = server.batches.get('A');
  setBatch('A', 'video', [{...a.tasks[0], progress: {percent_text: '80%', speed_text: '2 MiB/s', eta_text: '00:10'}}, a.tasks[1], a.tasks[2]]);
  await sweep();
  assert.strictEqual(groups()[1].htmlWrites, writesBefore[1] + 1);
  assert.strictEqual(groups()[0].htmlWrites, writesBefore[0], 'an unchanged batch is not re-rendered');

  // Network trouble backs off and keeps every batch on screen.
  server.offline = true;
  server.log = [];
  await sweep();
  assert.deepStrictEqual(batchReads(), ['GET /api/batch/B'], 'a failed request ends the sweep');
  assert.deepStrictEqual(pollDelays(), [1600]);
  assert.strictEqual(el('task-summary').textContent, '连接暂不可用，正在自动重试…');
  assert.strictEqual(groups().length, 2);
  server.offline = false;
  await sweep();
  assert.strictEqual(el('task-summary').textContent, '2 个批次 · 进行中 2 · 已结束 0');
  assert.deepStrictEqual(pollDelays(), [800]);

  // Hidden pages slow down; becoming visible polls at once.
  document.hidden = true;
  documentListeners.visibilitychange.forEach(listener => listener());
  assert.deepStrictEqual(pollDelays(), [3000]);
  document.hidden = false;
  server.log = [];
  documentListeners.visibilitychange.forEach(listener => listener());
  await settle();
  assert.deepStrictEqual(batchReads(), ['GET /api/batch/B', 'GET /api/batch/A']);

  // A finished batch stays listed until the focus moves, and stops being polled.
  setBatch('A', 'video', [
    taskState('a1', 'Alpine ride', 'completed', {result: {title: 'Alpine ride', filepath: '/downloads/Alpine ride.mp4'}}),
    taskState('a2', 'Boat trip', 'completed'),
    taskState('a3', 'Canyon walk', 'failed'),
  ]);
  await sweep();
  assert.strictEqual(groups().length, 2);
  assert.strictEqual(el('task-summary').textContent, '2 个批次 · 进行中 1 · 已结束 1');
  assert.strictEqual(el('retryFailedButton').hidden, false);
  server.log = [];
  await sweep();
  assert.deepStrictEqual(batchReads(), ['GET /api/batch/B'], 'finished batches are not polled again');

  // Row actions name their own batch; retrying revives polling for that batch.
  const retryA3 = handlersIn(groups()[1].innerHTML).find(handler => handler.includes("'retry'"));
  assert.ok(retryA3, 'failed rows offer a retry');
  server.log = [];
  await run(retryA3);
  await settle();
  assert.ok(server.log.includes('POST /api/batch/A/task/a3/retry'), retryA3);
  assert.ok(batchReads().includes('GET /api/batch/A'), 'an action refreshes its batch');

  // Retry all failed tasks covers every listed batch.
  setBatch('A', 'video', [
    taskState('a1', 'Alpine ride', 'completed'), taskState('a2', 'Boat trip', 'completed'), taskState('a3', 'Canyon walk', 'failed'),
  ]);
  setBatch('B', 'audio', [taskState('b1', 'Blue hour', 'running'), taskState('b2', 'Coastline', 'failed')]);
  await sweep();
  server.log = [];
  await run('retryFailedTasks()');
  await settle();
  assert.ok(server.log.includes('POST /api/batch/B/retry-failed'));
  assert.ok(server.log.includes('POST /api/batch/A/retry-failed'));
  assert.strictEqual(server.batches.get('A').tasks[2].status, 'queued');

  // A new submission sends finished batches to history but keeps running ones.
  setBatch('A', 'video', [
    taskState('a1', 'Alpine ride', 'completed'), taskState('a2', 'Boat trip', 'completed'), taskState('a3', 'Canyon walk', 'completed'),
  ]);
  await sweep();
  setBatch('C', 'video', [taskState('c1', 'Dune sunrise', 'running')]);
  await submitSingle('video', 'C');
  assert.strictEqual(groups().length, 2);
  assert.match(groups()[0].innerHTML, /Dune sunrise/);
  assert.match(groups()[1].innerHTML, /Blue hour/);
  assert.doesNotMatch(panelHtml(), /Alpine ride/, 'a finished batch leaves when a new batch takes focus');
  assert.strictEqual(storage.get('gtd_current_batch_v1'), 'C');

  // Saved batches open on top without interrupting running ones.
  setBatch('saved1', 'video', [taskState('s1', 'Old harbour', 'completed')]);
  setBatch('saved2', 'audio', [taskState('s2', 'Night train', 'completed')]);
  server.history = [summary('saved1', 'video'), summary('saved2', 'audio')];
  await run('refreshBatchHistory()');
  await settle();
  server.log = [];
  run("selectHistoryBatch('saved1')");
  await settle();
  assert.deepStrictEqual(groups().map(group => /Old harbour|Dune sunrise|Blue hour/.exec(group.innerHTML)?.[0]),
    ['Old harbour', 'Dune sunrise', 'Blue hour']);
  assert.ok(batchReads().includes('GET /api/batch/saved1'));
  assert.strictEqual(el('batchHistory').value, 'saved1');
  run("selectHistoryBatch('saved2')");
  await settle();
  assert.deepStrictEqual(groups().map(group => /Night train|Old harbour|Dune sunrise|Blue hour/.exec(group.innerHTML)?.[0]),
    ['Night train', 'Dune sunrise', 'Blue hour'], 'browsing history replaces only the saved batch in view');
  server.log = [];
  await sweep();
  assert.deepStrictEqual(batchReads(), ['GET /api/batch/C', 'GET /api/batch/B'], 'running batches keep updating');

  // A batch that vanished leaves with a notice; the others keep going.
  server.batches.delete('C');
  await sweep();
  assert.strictEqual(groups().length, 2);
  assert.doesNotMatch(panelHtml(), /Dune sunrise/);
  assert.strictEqual(el('taskNotice').hidden, false);
  assert.match(el('taskNotice').textContent, /不存在或已过期/);
  server.log = [];
  await sweep();
  assert.deepStrictEqual(batchReads(), ['GET /api/batch/B']);

  // An answer that predates a task action cannot mark the batch finished.
  const staleRead = deferred();
  server.heldBatchReads.set('B', staleRead);
  await sweep();
  await run("operateTask('cancel', 'b1', 'B')");
  await settle();
  setBatch('B', 'audio', [taskState('b1', 'Blue hour', 'cancelled'), taskState('b2', 'Coastline', 'completed')]);
  staleRead.resolve(reply(200, {...server.batches.get('B'), tasks: [taskState('b1', 'Stale title', 'completed')], all_done: true}));
  await settle();
  assert.doesNotMatch(panelHtml(), /Stale title/);
  server.log = [];
  await sweep();
  assert.deepStrictEqual(batchReads(), ['GET /api/batch/B'], 'the batch is read again after the action');

  // Polling ends once every listed batch has finished.
  await sweep();
  assert.deepStrictEqual(pollDelays(), []);
  assert.strictEqual(el('metric-active').textContent, '00');
  assert.strictEqual(el('metric-queue').textContent, '00');

  // One item list can wait for a choice; a second one waits its turn, single items still go through.
  server.previewReplies.push(reply(200, {
    preview_id: 'preview-list', title: 'Road trip', title_is_generated: false, is_single: false, requires_selection: true,
    entries: [{id: 'v1', title: 'Leg one', position: 1, selectable: true}, {id: 'v2', title: 'Leg two', position: 2, selectable: true}],
  }));
  el('videoUrls').value = 'https://youtube.com/playlist?list=road';
  await run("startDownload('video')");
  await settle();
  assert.strictEqual(el('collectionPreview').hidden, false);
  assert.deepStrictEqual(cardState('video'), locked, 'links waiting for a choice stay frozen');
  setBatch('D', 'audio', [taskState('d1', 'Echo', 'queued')]);
  await submitSingle('audio', 'D');
  assert.strictEqual(server.lastDownload.media_type, 'audio');
  assert.strictEqual(el('collectionPreview').hidden, false, 'a single item does not need the open choice');
  assert.match(panelHtml(), /Echo/);
  server.previewReplies.push(reply(200, {
    preview_id: 'preview-mix', title: 'Mix', title_is_generated: false, is_single: false, requires_selection: true,
    entries: [{id: 'm1', title: 'Song one', position: 1, selectable: true}, {id: 'm2', title: 'Song two', position: 2, selectable: true}],
  }));
  el('audioUrls').value = 'https://youtube.com/playlist?list=mix';
  await run("startDownload('audio')");
  await settle();
  assert.strictEqual(el('audioNotice').hidden, false);
  assert.match(el('audioNotice').textContent, /正在等待选择条目/);
  assert.strictEqual(el('audioUrls').value, 'https://youtube.com/playlist?list=mix', 'the waiting links stay in their box');
  assert.deepStrictEqual(cardState('audio'), usable);
  assert.match(el('collectionPreviewList').innerHTML, /Leg one/, 'the open choice is untouched');
  server.downloadReplies.push(reply(200, {batch_id: 'E', task_count: 1, download_dir: '/downloads'}));
  setBatch('E', 'video', [taskState('v2', 'Leg two', 'queued')]);
  run("updateCollectionSelection({dataset: {entryId: 'v1'}, checked: false})");
  await run('submitPreview()');
  await settle();
  assert.deepStrictEqual(server.lastDownload.selected_entry_ids, ['v2']);
  assert.strictEqual(server.lastDownload.media_type, 'video');
  assert.strictEqual(el('collectionPreview').hidden, true);
  assert.strictEqual(el('audioNotice').hidden, true, 'the wait notice goes once the open choice is resolved');
  assert.deepStrictEqual(cardState('video'), usable);
  assert.strictEqual(el('videoUrls').value, '');
  assert.match(groups()[0].innerHTML, /Leg two/);
  assert.match(panelHtml(), /Echo/);

  // A rejected single item reports in its own card and leaves the panel as it was.
  const panelBefore = panelHtml();
  server.previewReplies.push(reply(200, {
    preview_id: 'preview-F', title: 'F', title_is_generated: false, is_single: true, requires_selection: false,
    entries: [{id: 'entry-F', title: 'F', position: 1, selectable: true}],
  }));
  server.downloadReplies.push(reply(400, {error_code: 'INVALID_DOWNLOAD_DIR', message: '下载目录不可写', suggestion: ''}));
  el('videoUrls').value = 'https://youtu.be/F';
  await run("startDownload('video')");
  await settle();
  assert.strictEqual(el('videoNotice').hidden, false);
  assert.match(el('videoNotice').textContent, /下载目录不可写/);
  assert.strictEqual(el('videoUrls').value, 'https://youtu.be/F');
  assert.deepStrictEqual(cardState('video'), usable);
  assert.strictEqual(panelHtml(), panelBefore);

  // Every panel string follows the language switch.
  language = 'en';
  documentListeners['gtd:languagechange'].forEach(listener => listener({detail: {language}}));
  assert.strictEqual(el('task-title').textContent, 'Download tasks');
  assert.match(el('task-summary').textContent, /^\d+ batches · \d+ in progress · \d+ finished$/);
  assert.doesNotMatch(panelHtml(), /[一-鿿]/);

  console.log('Concurrent batches harness passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
