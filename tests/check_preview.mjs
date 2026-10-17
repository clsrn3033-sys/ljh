// Offline DOM-behaviour check using Node's standard library, not a browser test.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const html = fs.readFileSync(process.argv[2] || 'preview/index.html', 'utf8');
const json = html.match(/<script type="application\/json" id="trace">([\s\S]*?)<\/script>/)[1];
const source = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
class Element {
  constructor() { this.listeners = {}; this.attributes = {}; this.dataset = {}; this.textContent = ''; }
  addEventListener(event, handler) { this.listeners[event] = handler; }
  setAttribute(key, value) { this.attributes[key] = value; }
  click() { this.listeners.click({target:this}); }
}
const elements = new Map();
const get = id => { if(!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
get('trace').textContent = json;
const cases = ['success','corruption','cancel'].map(kind => {const e=new Element();e.dataset.case=kind;return e;});
let tick = null;
const context = vm.createContext({document:{getElementById:get,querySelectorAll:()=>cases},
  setInterval:fn=>{tick=fn;return 1;},clearInterval:()=>{tick=null;}});
vm.runInContext(source, context);
assert.equal(get('phase').textContent, '백업 준비');
assert.equal(get('previous').disabled, true);
assert.ok(get('screen').src.startsWith('data:image/png;base64,iVBOR'));
get('next').click();
assert.equal(get('phase').textContent, '외장 하드 연결 · SD카드 대기');
get('restart').click();
get('play').click();
let count=0;
while(tick && count++ < 100) tick();
assert.equal(tick, null);
assert.equal(get('phase').textContent, '검증 완료 · 안전 분리 필요');
assert.equal(get('jobs').textContent, '1개');
assert.equal(get('next').disabled, true);
cases[1].click();
assert.equal(get('jobs').textContent, '0개');
assert.equal(get('result').textContent, '실패 감지');
get('seek').value=get('seek').max;
get('seek').listeners.input({target:get('seek')});
assert.equal(get('phase').textContent, '실패 · 원본 보존');
cases[2].click();
assert.equal(get('result').textContent, '중단 확인');
assert.equal(cases[2].attributes['aria-pressed'], 'true');
assert.equal(cases[1].attributes['aria-pressed'], 'false');
assert.equal(get('original').textContent, '변경 없음');
console.log('PASS: offline playback, seek, case switching, PNG data and result labels');
