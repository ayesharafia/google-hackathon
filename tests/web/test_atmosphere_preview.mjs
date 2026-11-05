import test from 'node:test';
import assert from 'node:assert/strict';
import {ATMOSPHERE_MODEL,atmosphereInputs,atmosphereDraft,mountAtmospherePreview} from '../../web/js/atmosphere-preview.js';
const inputs=()=>atmosphereInputs(20000,'geometric');
const response=()=>({inputs:inputs(),model:{model_id:ATMOSPHERE_MODEL},outputs:{pressure_pa:5529.3,temperature_k:216.65,density_kg_m3:0.08891},atmosphere_values:{source:ATMOSPHERE_MODEL+'; 20000 m geometric',altitude_m:20000,pressure_pa:5529.3,temperature_k:216.65,viscosity:{law:'sutherland',value_pa_s:null},gamma:1.4},evidence_level:'unverified',aircraft_status:null});
test('explicit supported inputs only',()=>{assert.equal(inputs().model_id,ATMOSPHERE_MODEL);for(const value of [null,'20000',NaN,Infinity,-1,30001,true])assert.throws(()=>atmosphereInputs(value,'geometric'));for(const kind of ['',null,'pressure'])assert.throws(()=>atmosphereInputs(0,kind));});
test('apply copies only atmosphere fields, original and other groups unchanged',()=>{const draft={atmosphere:{source:'manual',custom:'preserved'},masses:{items:[]},mission:{cases:[]}},copy=structuredClone(draft),r=response();r.atmosphere_values.injected='no';const next=atmosphereDraft(draft,r,inputs());assert.deepEqual(draft,copy);assert.equal(next.atmosphere.source,r.atmosphere_values.source);assert.equal(next.atmosphere.custom,'preserved');assert.equal(next.atmosphere.injected,undefined);assert.deepEqual(next.masses,draft.masses);assert.deepEqual(next.mission,draft.mission);});
test('reject stale convention or altitude, validation upgrade, nonfinite or mismatched output',()=>{for(const mutate of [r=>r.inputs.altitude_m++,r=>r.inputs.altitude_kind='geopotential',r=>r.evidence_level='validated',r=>r.aircraft_status='ready',r=>r.outputs.pressure_pa=Infinity,r=>r.atmosphere_values.temperature_k++,r=>r.model.model_id='other']){const r=response();mutate(r);assert.throws(()=>atmosphereDraft({atmosphere:{}},r,inputs()));}});
test('input key ordering is not an identity change',()=>{const r=response();r.inputs={altitude_kind:'geometric',altitude_m:20000,model_id:ATMOSPHERE_MODEL};assert.equal(atmosphereDraft({atmosphere:{}},r,inputs()).atmosphere.altitude_m,20000);});

test('reject unsupported or missing gamma and viscosity',()=>{
  for(const mutate of [
    r=>delete r.atmosphere_values.gamma,
    r=>r.atmosphere_values.gamma=1.3,
    r=>r.atmosphere_values.gamma='1.4',
    r=>r.atmosphere_values.gamma=NaN,
    r=>delete r.atmosphere_values.viscosity,
    r=>r.atmosphere_values.viscosity=null,
    r=>r.atmosphere_values.viscosity.law='constant',
    r=>delete r.atmosphere_values.viscosity.value_pa_s,
    r=>r.atmosphere_values.viscosity.value_pa_s=0.0000142,
  ]){
    const r=response(),draft={atmosphere:{}},before=structuredClone(draft);
    mutate(r);
    assert.throws(()=>atmosphereDraft(draft,r,inputs()),/gamma or viscosity/);
    assert.deepEqual(draft,before);
  }
  const r=response(),next=atmosphereDraft({atmosphere:{}},r,inputs());
  assert.equal(next.atmosphere.gamma,r.atmosphere_values.gamma);
  assert.deepEqual(next.atmosphere.viscosity,r.atmosphere_values.viscosity);
  assert.notEqual(next.atmosphere.viscosity,r.atmosphere_values.viscosity);
});

// Minimal DOM double: exercises the event handlers and explicit naming contract.
function mountFixture(t){
  const previous=Object.getOwnPropertyDescriptor(globalThis,'document');
  const nodes=[];
  const createElement=tag=>{
    const attributes=new Map(),listeners=new Map();
    const node={tag,children:[],dataset:{},isConnected:true,value:'',
      append(...children){this.children.push(...children);},
      setAttribute(name,value){attributes.set(name,String(value));},
      getAttribute(name){return attributes.get(name)??null;},
      addEventListener(type,listener){listeners.set(type,listener);},
      fire(type){return listeners.get(type)?.();}};
    nodes.push(node);
    return node;
  };
  Object.defineProperty(globalThis,'document',{configurable:true,value:{createElement}});
  t.after(()=>{
    if(previous)Object.defineProperty(globalThis,'document',previous);
    else delete globalThis.document;
  });
  let draft={atmosphere:{}},applied=0;
  const pending=[];
  mountAtmospherePreview(createElement('div'),{
    read:()=>draft,
    apply:next=>{draft=next;applied++;},
    evaluate:()=>new Promise(resolve=>pending.push(resolve)),
  });
  const altitude=nodes.find(n=>n.tag==='input'),kind=nodes.find(n=>n.tag==='select');
  const [preview,use]=nodes.filter(n=>n.tag==='button');
  altitude.value='20000';kind.value='geometric';
  return {altitude,kind,preview,use,pending,
    get draft(){return draft;},get applied(){return applied;}};
}

test('convention has an exact explicit accessible name; only apply mutates',async t=>{
  const f=mountFixture(t);
  assert.equal(f.kind.getAttribute('aria-label'),'Altitude convention');
  const before=structuredClone(f.draft),request=f.preview.fire('click');
  f.pending.shift()(response());await request;
  assert.deepEqual(f.draft,before);assert.equal(f.applied,0);
  assert.equal(f.use.disabled,false);
  f.use.fire('click');
  assert.equal(f.applied,1);assert.equal(f.draft.atmosphere.gamma,1.4);
  f.use.fire('click');assert.equal(f.applied,1);
});

test('stale requests and changed drafts cannot apply',async t=>{
  const f=mountFixture(t),first=f.preview.fire('click');
  f.kind.fire('change');f.pending.shift()(response());await first;
  assert.equal(f.use.disabled,true);f.use.fire('click');assert.equal(f.applied,0);
  const second=f.preview.fire('click');
  f.draft.atmosphere.source='changed';f.pending.shift()(response());await second;
  assert.equal(f.use.disabled,true);assert.equal(f.applied,0);
  const third=f.preview.fire('click');
  f.pending.shift()(response());await third;
  f.draft.atmosphere.source='changed again';f.use.fire('click');
  assert.equal(f.applied,0);assert.equal(f.use.disabled,true);
});
