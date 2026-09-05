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
vm.runInContext(`renderTasks({media_type:'audio', tasks:[{id:'a',url:'https://example.com/中文',status:'completed',result:{title:'用户中文标题',filepath:'/中文/音频.mp3'},can_redownload:true}]});`,context);
language = 'en';
assert.strictEqual(typeof listeners['gtd:languagechange'], 'function', 'dynamic UI must respond to language changes');
listeners['gtd:languagechange']({detail:{language}});
assert.match(nodes.get('task-container').innerHTML,/Completed/);
assert.match(nodes.get('task-container').innerHTML,/用户中文标题/);
assert.match(nodes.get('task-container').innerHTML,/\/中文\/音频.mp3/);
assert.match(nodes.get('task-container').innerHTML,/Redownload/);
assert.strictEqual(requests,1,'switching a completed task must not restart polling');
assert.match(vm.runInContext('renderDownloadProgress({speed_text:"计算中",eta_text:"计算中"})',context),/Calculating/);
assert.match(vm.runInContext('formatApiError({error_code:"NETWORK_TIMEOUT",message:"网络连接源站超时",suggestion:"请检查网络或代理设置后重试"})',context),/timed out/);
vm.runInContext(`pendingPreview={title:'合集标题',entries:[{id:'1',title:'标题',selectable:true},{id:'2',title:'标题2',selectable:true}]};pendingDownloadSettings={mediaType:'video'};collectionSelectedIds=new Set(['2']);collectionRenderLimit=100;renderCollectionEntries('video');`,context);
const before = vm.runInContext('JSON.stringify([...collectionSelectedIds])',context);
language = 'zh'; listeners['gtd:languagechange']({detail:{language}});
assert.strictEqual(vm.runInContext('JSON.stringify([...collectionSelectedIds])',context),before);
assert.strictEqual(vm.runInContext('collectionRenderLimit',context),100);
assert.strictEqual(requests,1);
console.log('Download language harness passed');
