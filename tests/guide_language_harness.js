const assert = require('assert');
const fs = require('fs');
const script = fs.readFileSync('templates/guide.html', 'utf8').match(/<script>\s*([\s\S]*?)<\/script>/)[1];
const listeners = {};
function heading(id, textContent) {
  return { id, textContent, setAttribute() {}, getBoundingClientRect() { return {top: 80}; } };
}
const zh = [heading('开始使用', '开始使用'), heading('下载操作流程', '下载操作流程')];
const en = [heading('getting-started', 'Getting started'), heading('download-workflow', 'Download workflow')];
const articles = {'guide-markdown': {querySelectorAll() {return zh;}}, 'guide-markdown-en': {querySelectorAll() {return en;}}};
const toc = {
  children: [],
  set textContent(value) {this.children = [];},
  appendChild(child) {this.children.push(child);},
  querySelectorAll() {return this.children.map(item => item.children[0]);}
};
global.document = {
  readyState: 'complete',
  getElementById(id) {return id === 'guide-toc-list' ? toc : articles[id];},
  addEventListener(name, fn) {(listeners[name] ||= []).push(fn);},
  createElement() {return {children: [], appendChild(child) {this.children.push(child);}, classList: {toggle(){}}, set href(value) {this.hash = value;}};}
};
const refreshed = [];
global.window = {
  GtdLanguage: {language: 'en'},
  location: {hash: '#下载操作流程'},
  history: {replaceState(_, __, hash) {window.location.hash = hash;}},
  MotionSystem: {refresh(article) {refreshed.push(article);}}
};
new Function(script)();
assert.deepStrictEqual(toc.querySelectorAll().map(x => x.textContent), ['Getting started', 'Download workflow']);
assert.strictEqual(window.location.hash, '#download-workflow', 'a Chinese anchor must resolve to the visible English section on initial load');
for (const language of ['zh', 'en', 'zh']) {
  window.GtdLanguage.language = language;
  listeners['gtd:languagechange'][0]();
  assert.strictEqual(toc.children.length, 2, 'TOC must not accumulate duplicate links');
  assert.strictEqual(window.location.hash, language === 'en' ? '#download-workflow' : '#下载操作流程');
  assert.strictEqual(refreshed.at(-1), articles[language === 'en' ? 'guide-markdown-en' : 'guide-markdown']);
}
assert.strictEqual(listeners['motion:scroll-frame'].length, 1);
console.log('Guide language TOC harness passed');
