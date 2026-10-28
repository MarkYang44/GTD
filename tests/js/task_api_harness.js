'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

assert.ok(fs.existsSync('static/js/task_api.js'), 'shared task transport must exist');
const timers = new Map();
let nextTimer = 0;
const context = vm.createContext({window: {}, AbortController,
  setTimeout(fn) { const id = ++nextTimer; timers.set(id, fn); return id; },
  clearTimeout(id) { timers.delete(id); },
  fetch: async () => ({ok: true, status: 200, json: async () => ({id: 'batch'})})});
vm.runInContext(fs.readFileSync('static/js/task_api.js', 'utf8'), context);
const api = context.window.GtdTaskApi;

(async () => {
  let result = await api.fetchJson('/batch');
  assert.strictEqual(result.data.id, 'batch');
  assert.strictEqual(timers.size, 0, 'successful requests must clear their timeout');
  for (const [base, failures, expected] of [[1200, 0, 1200], [1500, 1, 3000], [1500, 6, 30000], [6000, 2, 24000]]) {
    assert.strictEqual(api.backoffDelay(base, failures), expected);
  }

  let bodyReads = 0;
  context.fetch = async () => ({ok: false, status: 404, json: async () => {
    bodyReads += 1; return {error_code: 'BATCH_NOT_FOUND'};
  }});
  result = await api.fetchJson('/missing', {readErrorBody: false});
  assert.strictEqual(result.status, 404);
  assert.strictEqual(result.data, null);
  assert.strictEqual(bodyReads, 0, 'download polling must not wait for an error body');
  result = await api.fetchJson('/missing');
  assert.strictEqual(result.data.error_code, 'BATCH_NOT_FOUND');

  context.fetch = async () => ({ok: true, status: 200, json: async () => { throw new SyntaxError('invalid JSON'); }});
  await assert.rejects(api.fetchJson('/invalid'), /invalid JSON/);
  assert.strictEqual(timers.size, 0);

  let signal;
  context.fetch = (_url, options) => new Promise((_resolve, reject) => {
    signal = options.signal;
    signal.addEventListener('abort', () => reject(new Error('request aborted')));
  });
  const stalled = api.fetchJson('/stalled', {timeoutMs: 10});
  [...timers.values()][0]();
  await assert.rejects(stalled, /request aborted/);
  assert.ok(signal.aborted);
  assert.strictEqual(timers.size, 0);

  let bodyReady;
  const ready = new Promise(resolve => { bodyReady = resolve; });
  context.fetch = async (_url, options) => ({ok: true, status: 200,
    json: () => new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new Error('body aborted')));
      bodyReady();
    })});
  const body = api.fetchJson('/slow-body');
  await ready;
  [...timers.values()][0]();
  await assert.rejects(body, /body aborted/);
  assert.strictEqual(timers.size, 0, 'body timeout must release its timer');

  const upstream = new AbortController();
  context.fetch = (_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new Error('caller aborted')));
  });
  const cancelled = api.fetchJson('/cancel', {signal: upstream.signal});
  upstream.abort();
  await assert.rejects(cancelled, /caller aborted/);
  assert.strictEqual(timers.size, 0);

  const alreadyCancelled = new AbortController();
  alreadyCancelled.abort();
  context.fetch = async (_url, options) => {
    assert.ok(options.signal.aborted, 'an already-aborted caller must stay aborted');
    throw new Error('already aborted');
  };
  await assert.rejects(api.fetchJson('/already-cancelled', {signal: alreadyCancelled.signal}), /already aborted/);
  assert.strictEqual(timers.size, 0);

  const completed = new AbortController();
  context.fetch = async (_url, options) => {
    signal = options.signal;
    return {ok: true, status: 200, json: async () => ({})};
  };
  await api.fetchJson('/complete', {signal: completed.signal});
  completed.abort();
  assert.strictEqual(signal.aborted, false, 'completed requests must detach caller abort listeners');
  console.log('Task API harness passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
