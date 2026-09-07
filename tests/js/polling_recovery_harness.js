'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
class Element {
  constructor() { this.textContent = ''; this.innerHTML = ''; this.value = ''; this.dataset = {}; this.hidden = true; this.classList = {remove(){}, add(){}}; }
  addEventListener() {} setAttribute() {} replaceChildren() { this.innerHTML = ''; }
  appendChild(child) { this.innerHTML += String(child.textContent).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'); }
  querySelectorAll() { return []; } contains() { return false; } focus() {} scrollIntoView() {}
}
const nodes = new Map(); const listeners = {}; let requests = 0; let language = 'zh';
const document = { getElementById(id) { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); }, querySelectorAll() { return []; }, createElement() { return new Element(); }, createTextNode(textContent) { return {textContent}; }, addEventListener(name, fn) { listeners[name] = fn; } };
const window = {GtdLanguage: {get language(){ return language; }, t(zh,en,params={}) { return (language === 'en' ? en : zh).replace(/\{(\w+)\}/g, (_,key) => params[key] ?? `{${key}}`); }}, setTimeout() {}};
const context = vm.createContext({document,window,localStorage:{getItem(){return null;}},fetch(){requests++;return new Promise(()=>{});}, setTimeout(){}, clearTimeout(){}, console});
vm.runInContext(fs.readFileSync('static/js/index.js','utf8'), context);

(async () => {
  let timers = [];
  context.setTimeout = (fn, delay) => { timers.push({fn,delay}); return timers.length; };
  context.clearTimeout = () => {};
  const stored = new Map();
  context.localStorage = {getItem:k=>stored.get(k)??null, setItem:(k,v)=>stored.set(k,v),removeItem:k=>stored.delete(k)};
  context.fetch = async () => ({ok:false,status:404});
  await vm.runInContext("currentBatchId='missing';isDownloading=true;pollingActive=true;setControlsDisabled(true);pollStatus()",context);
  assert.strictEqual(vm.runInContext('pollingActive',context),false,'missing batches must stop polling');
  assert.strictEqual(nodes.get('videoDownloadButton').disabled,false);
  assert.match(nodes.get('task-summary').textContent,/不存在|已过期/);

  context.fetch = async () => { throw new Error('offline'); };
  timers=[];
  await vm.runInContext("currentBatchId='recoverable';isDownloading=true;pollingActive=true;pollStatus()",context);
  assert.strictEqual(vm.runInContext('currentBatchId',context),'recoverable');
  assert.strictEqual(vm.runInContext('pollingActive',context),true);
  assert.ok(timers.at(-1).delay>=1600,'network errors must back off');
  assert.match(nodes.get('task-summary').textContent,/连接|重试/);

  context.fetch = async () => ({ok:true,json:async()=>({id:'recoverable',media_type:'video',total:1,completed:1,failed:0,tasks:[{id:'t',url:'test',status:'completed',result:{title:'done'},can_redownload:true}],all_done:true})});
  await vm.runInContext('pollStatus()',context);
  assert.strictEqual(vm.runInContext('pollingActive',context),false);
  assert.strictEqual(nodes.get('videoDownloadButton').disabled,false);
  assert.match(nodes.get('task-container').innerHTML,/done/);

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
