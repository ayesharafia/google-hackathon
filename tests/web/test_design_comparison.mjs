import test from 'node:test';
import assert from 'node:assert/strict';
import {changeGroup, changeLabel, groupChanges, recordedValue, payloadDelta, createComparisonController} from '../../web/js/design-comparison.js';

test('known paths group without substring or escaped-pointer guesses', () => {
  for (const [path, group] of [['/masses/items','Mass'],['/mission/energy_system','Battery'],['/mission/reserve_policy','Battery'],['/rotors','Rotors'],['/mission/cases','Mission'],['/atmosphere/source','Mission'],['/assembly/geometry_revision_sha256','Geometry'],['/units_and_frames/cad_transform','Geometry'],['/fidelity','Model settings'],['/numerics','Model settings'],['/future/rotors','Other declarations'],['/rotors~1unknown','Other declarations']]) assert.equal(changeGroup(path),group);
});
test('grouping retains exact changes and whole arrays in stable group order', () => {
  const a={path:'/rotors',kind:'changed',before:[{id:'a'},{id:'b'}],after:[{id:'b'}]}, b={path:'/masses/items',kind:'changed'};
  const source=[a,b],copy=structuredClone(source),result=groupChanges(source);
  assert.deepEqual(result.map(g=>g.name),['Mass','Rotors']);assert.equal(result[1].changes[0],a);assert.deepEqual(source,copy);
});
test('absent, null, false, zero and empty declarations remain distinguishable', () => {
  assert.equal(recordedValue({},'before'),'Not present');
  for(const v of [null,false,0,'',[],{}])assert.equal(recordedValue({before:v},'before'),JSON.stringify(v,null,2));
});
test('numeric deltas require strict API permission and finite numbers', () => {
  for(const flag of [false,null,undefined,1,'true']) assert.equal(payloadDelta({comparable_numeric_results:flag},12),'Unavailable');
  for(const value of [null,undefined,NaN,Infinity,'3']) assert.equal(payloadDelta({comparable_numeric_results:true},value),'Unavailable');
  assert.equal(payloadDelta({comparable_numeric_results:true},0),'0 kg');assert.equal(payloadDelta({comparable_numeric_results:true},-2),'-2 kg');
});
function harness() {
  let selected={before:'a',after:'b'},workspace=1,resolve,reject;
  const states=[],reports=[];
  const controller=createComparisonController({readContext:()=>workspace,isContext:c=>c===workspace,readSelection:()=>({...selected}),fetchReport:()=>new Promise((ok,no)=>{resolve=ok;reject=no;}),setState:(...args)=>states.push(args),render:r=>reports.push(r)});
  return {controller,states,reports,choose:pair=>selected=pair,move:()=>workspace++,resolve:r=>resolve(r),reject:e=>reject(e)};
}
const report=()=>({schema_version:'retained_study_comparison_v1',before:{study_sha256:'a'},after:{study_sha256:'b'}});
test('matching pair publishes and pending precedes current',async()=>{const h=harness(),p=h.controller.compare();h.resolve(report());await p;assert.equal(h.reports.length,1);assert.deepEqual(h.states.map(s=>s[0]),['pending','current']);});
test('selection events stale the report and suppress delayed responses',async()=>{const h=harness(),p=h.controller.compare();h.controller.invalidate();h.resolve(report());await p;assert.equal(h.reports.length,0);assert.equal(h.states.at(-1)[0],'stale');});
test('even a selection mutation without an event is detected',async()=>{const h=harness(),p=h.controller.compare();h.choose({before:'b',after:'a'});h.resolve(report());await p;assert.equal(h.reports.length,0);assert.equal(h.states.at(-1)[0],'stale');});
test('changed workspace cannot publish a response',async()=>{const h=harness(),p=h.controller.compare();h.move();h.resolve(report());await p;assert.equal(h.reports.length,0);assert.equal(h.states.some(s=>s[0]==='current'),false);});
test('wrong identity or unsupported format is rejected',async()=>{for(const wrong of [{...report(),after:{study_sha256:'x'}},{...report(),schema_version:'unknown'}]){const h=harness(),p=h.controller.compare();h.resolve(wrong);await assert.rejects(p,/identity/);assert.equal(h.reports.length,0);assert.equal(h.states.at(-1)[0],'failed');}});
test('failed request reports unavailable and propagates existing error handling',async()=>{const h=harness(),p=h.controller.compare();h.reject(new Error('refused'));await assert.rejects(p,/refused/);assert.equal(h.states.at(-1)[0],'failed');});
test('earlier failures do not overwrite a newer stale state',async()=>{const h=harness(),p=h.controller.compare();h.controller.invalidate();h.reject(new Error('old request'));await assert.rejects(p,/old request/);assert.equal(h.states.at(-1)[0],'stale');});

test('friendly declaration names retain an exact-path fallback',()=>{assert.equal(changeLabel('/masses/items'),'Mass ledger');assert.equal(changeLabel('/unknown/added'),'/unknown/added');});
test('latest request wins when responses arrive out of order',async()=>{
  const waiting=[],states=[],reports=[];const controller=createComparisonController({readContext:()=>1,isContext:()=>true,readSelection:()=>({before:'a',after:'b'}),fetchReport:()=>new Promise(resolve=>waiting.push(resolve)),setState:s=>states.push(s),render:r=>reports.push(r)});
  const first=controller.compare(),second=controller.compare();waiting[1]({...report(),tag:'latest'});await second;waiting[0]({...report(),tag:'old'});await first;assert.deepEqual(reports.map(r=>r.tag),['latest']);assert.equal(states.at(-1),'current');
});
