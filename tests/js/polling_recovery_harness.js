'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
class Element {
  constructor() { this.textContent = ''; this.html = ''; this.children = []; this.value = ''; this.dataset = {}; this.hidden = true; this.classList = {remove(){}, add(){}}; }
  get innerHTML() { return this.html; } set innerHTML(value) { this.html = String(value); this.children = []; }
  addEventListener() {} setAttribute() {} replaceChildren(...children) { this.children = children; this.html = ''; }
  appendChild(child) { this.innerHTML += String(child.textContent).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'); }
  querySelectorAll() { return []; } contains() { return false; } focus() {} scrollIntoView() {}
}
const nodes = new Map(); const listeners = {}; let requests = 0; let language = 'zh';
const document = { getElementById(id) { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); }, querySelectorAll() { return []; }, createElement() { return new Element(); }, createTextNode(textContent) { return {textContent}; }, addEventListener(name, fn) { listeners[name] = fn; } };
const window = {GtdLanguage: {get language(){ return language; }, t(zh,en,params={}) { return (language === 'en' ? en : zh).replace(/\{(\w+)\}/g, (_,key) => params[key] ?? `{${key}}`); }}, setTimeout() {}};
const context = vm.createContext({document,window,localStorage:{getItem(){return null;}},fetch(){requests++;return new Promise(()=>{});}, setTimeout(){}, clearTimeout(){}, console});
vm.runInContext(fs.readFileSync('static/js/task_api.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('static/js/index.js','utf8'), context);

(async () => {
  let timers = [];
  context.setTimeout = (fn, delay) => { timers.push({fn,delay}); return timers.length; };
  context.clearTimeout = () => {};
  const stored = new Map();
  context.localStorage = {getItem:k=>stored.get(k)??null, setItem:(k,v)=>stored.set(k,v),removeItem:k=>stored.delete(k)};
  const settle = async () => { for (let round = 0; round < 6; round += 1) await new Promise(resolve => setImmediate(resolve)); };
  const panel = () => nodes.get('task-container').children.map(child => child.innerHTML).join('');

  // A saved batch that no longer exists leaves the panel with a notice and stops polling.
  context.fetch = async () => ({ok:false,status:404});
  vm.runInContext("selectHistoryBatch('missing')",context);
  await settle();
  assert.strictEqual(vm.runInContext('pollingActive',context),false,'missing batches must stop polling');
  assert.ok(!nodes.get('videoDownloadButton').disabled,'saved batches never hold the download cards');
  assert.strictEqual(nodes.get('taskNotice').hidden,false);
  assert.match(nodes.get('taskNotice').textContent,/不存在|已过期/);
  assert.strictEqual(stored.get('gtd_current_batch_v1'),undefined,'a vanished batch is not remembered');
  assert.strictEqual(panel(),'');

  // Network errors back off and keep the batch on screen.
  context.fetch = async () => { throw new Error('offline'); };
  timers=[];
  vm.runInContext("selectHistoryBatch('recoverable')",context);
  await settle();
  assert.strictEqual(vm.runInContext('pollingActive',context),true);
  assert.ok(timers.at(-1).delay>=1600,'network errors must back off');
  assert.match(nodes.get('task-summary').textContent,/连接|重试/);
  assert.strictEqual(nodes.get('task-container').children.length,1);

  // Recovery renders the batch and stops polling once it has finished.
  context.fetch = async () => ({ok:true,json:async()=>({id:'recoverable',media_type:'video',total:1,completed:1,failed:0,tasks:[{id:'t',url:'test',status:'completed',result:{title:'done'},can_redownload:true}],all_done:true})});
  await vm.runInContext('pollStatus()',context);
  await settle();
  assert.strictEqual(vm.runInContext('pollingActive',context),false);
  assert.ok(!nodes.get('videoDownloadButton').disabled,'saved batches never hold the download cards');
  assert.match(panel(),/done/);
  assert.match(nodes.get('task-summary').textContent,/完成 1/);
  assert.doesNotMatch(nodes.get('task-summary').textContent,/recoverable/,'summaries omit the internal batch ID');

  // An answer that started before a task action cannot end tracking for that batch.
  let finishOld;
  context.fetch = (_url, options = {}) => options.method === 'POST'
    ? Promise.resolve({ok:true,status:200,json:async()=>({})})
    : new Promise(resolve => { finishOld = resolve; });
  vm.runInContext("selectHistoryBatch('old-batch')", context);
  await settle();
  await vm.runInContext("operateTask('retry', 'stale', 'old-batch')", context);
  finishOld({ok:true,status:200,json:async()=>({id:'old-batch',all_done:true,tasks:[{id:'stale',status:'completed',result:{title:'stale-title'}}]})});
  await settle();
  assert.doesNotMatch(panel(), /stale-title/);
  assert.strictEqual(vm.runInContext('pollingActive', context), true, 'the batch is read again after the action');

  // Persisting a batch reference is independent of download-directory history.
  vm.runInContext("rememberCurrentBatch('saved-id')",context);
  assert.strictEqual(stored.get('gtd_current_batch_v1'),'saved-id');
  vm.runInContext("rememberCurrentBatch(null)",context);
  assert.strictEqual(stored.get('gtd_current_batch_v1'),undefined);

  // Request timeout actually aborts the request and frees the polling lock.
  context.AbortController=AbortController;
  let signal;
  context.fetch=(_url,options)=>new Promise((_resolve,reject)=>{
    signal=options.signal;
    signal.addEventListener('abort',()=>reject(new Error('aborted')));
  });
  timers=[];
  const request=vm.runInContext("fetchJsonWithTimeout('/test',100)",context);
  timers[0].fn();
  await assert.rejects(request,/aborted/);
  assert.strictEqual(signal.aborted,true);
  // Receiving headers must not end the timeout while the JSON body is stalled.
  timers=[];
  let bodyReady;
  const ready=new Promise(resolve=>{bodyReady=resolve;});
  context.fetch=async (_url,options)=>({ok:true,status:200,json:()=>new Promise((_resolve,reject)=>{
    options.signal.addEventListener('abort',()=>reject(new Error('body aborted')));
    bodyReady();
  })});
  const bodyRequest=vm.runInContext("fetchJsonWithTimeout('/slow-body',100)",context);
  await ready;
  timers[0].fn();
  await assert.rejects(bodyRequest,/body aborted/);
  console.log('Polling recovery harness passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
