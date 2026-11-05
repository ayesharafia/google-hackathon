import {mountAtmospherePreview} from './atmosphere-preview.js?v=atmosphere-preview-1';
/* Native draft authoring; blank numeric fields preserve unknowns. */
import {mountSourceLibrary} from './source-library.js?v=source-explorer-1';
import {mountAdvanced} from './advanced-editors.js';
import {renderSourceBinding} from './rotor-source-binding.js?v=source-binding-1';
const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
function field(label,value,update,type='number'){
  const wrap=node('label',label),input=node('input');input.type=type;if(type==='number')input.step='any';input.value=value??'';
  input.addEventListener('input',()=>update(type==='number'?(input.value===''?null:Number(input.value)):(input.value||null)));wrap.append(input);return wrap;
}
function button(text,act){const b=node('button',text);b.type='button';b.addEventListener('click',act);return b;}
function choice(label,value,values,update){const wrap=node('label',label),select=node('select');const empty=node('option','Choose explicitly');empty.value='';select.append(empty);values.forEach(v=>{const o=node('option',v);o.value=v;select.append(o);});select.value=value??'';select.addEventListener('change',()=>update(select.value||null));wrap.append(select);return wrap;}
function triple(row,label,object,key,changed){['x','y','z'].forEach((axis,i)=>row.append(field(label+' '+axis,object[key]?.[i],v=>{if(!Array.isArray(object[key]))object[key]=[null,null,null];object[key][i]=v;changed();})));}
export function mountEditors(container,read,write,inspect,importMap,options={}){
  container.replaceChildren();let data;
  try{data=read();}catch{container.append(node('p','Correct the input JSON to reopen the structured editors.'));return;}
  const mapping=v=>v&&typeof v==='object'&&!Array.isArray(v);
  if(![data?.masses,data?.mission,data?.atmosphere,data?.identity,data?.fidelity].every(mapping)||!Array.isArray(data.masses.items)||!Array.isArray(data.mission.cases)||!Array.isArray(data.rotors)||[...data.masses.items,...data.mission.cases,...data.rotors,...(Array.isArray(data.mission.sequence)?data.mission.sequence:[])].some(v=>!mapping(v))||(data.mission.energy_system&&!mapping(data.mission.energy_system))){container.append(node('p','Design groups are malformed. Correct the input JSON before using structured editors.'));return;}
  const changed=()=>write(data),rebuild=()=>{const opened=[...container.querySelectorAll('details[open]')].map(d=>d.querySelector('summary').textContent);const focus=document.activeElement?.textContent;changed();mountEditors(container,read,write,inspect,importMap,options);container.querySelectorAll('details').forEach(d=>{d.open=opened.includes(d.querySelector('summary').textContent);});[...container.querySelectorAll('button')].find(b=>b.textContent===focus)?.focus();};
  const mass=node('section');mass.append(node('h3','Mass and payload placement'),node('p','Mass in kg; positions in body-frame metres. Add explicit zero entries for empty categories.'));
  (data.masses.items||[]).forEach((item,index)=>{
    const row=node('fieldset');row.append(node('legend','Mass item '+(index+1)),field('Item name',item.name,v=>{item.name=v;changed();},'text'));
    const label=node('label','Category'),select=node('select');['payload','structure','propulsion','energy','avionics','other'].forEach(value=>{const o=node('option',value);o.value=value;select.append(o);});select.value=item.category;
    select.addEventListener('change',()=>{item.category=select.value;changed();});label.append(select);row.append(label,field('Mass, kg',item.mass_kg,v=>{item.mass_kg=v;changed();}));
    triple(row,'Position, m',item,'cg_body_m',changed);
    row.append(field('Source / uncertainty note',item.source_note,v=>{item.source_note=v;changed();},'text'),button('Remove mass item '+(index+1),()=>{data.masses.items.splice(index,1);rebuild();}));mass.append(row);
  });
  mass.append(button('Add mass item',()=>{data.masses.items||=[];data.masses.items.push({name:'mass_'+(data.masses.items.length+1),category:'structure',mass_kg:null,cg_body_m:[null,null,null],source_note:null});rebuild();}));
  const placement=node('div');placement.className='fields';['x','y','z'].forEach((axis,i)=>placement.append(field('Candidate payload '+axis+', m',data.mission.payload_positions_body_m?.[0]?.[i],v=>{if(!Array.isArray(data.mission.payload_positions_body_m))data.mission.payload_positions_body_m=[];if(!Array.isArray(data.mission.payload_positions_body_m[0]))data.mission.payload_positions_body_m[0]=[null,null,null];data.mission.payload_positions_body_m[0][i]=v;changed();})));mass.append(placement);
  const pack=node('section');pack.append(node('h3','Fixed battery pack'),node('p','Bind the battery ledger items. Hold reserve back once from usable pack energy.'));
  const pf=node('div');pf.className='fields';const energy=data.mission.energy_system||{},setPack=(key,v)=>{data.mission.energy_system||={};data.mission.energy_system[key]=v;changed();};
  pf.append(choice('Pack mode',energy.mode,['fixed'],v=>setPack('mode',v)),choice('Voltage model',energy.voltage_model,['declared_constant_bus'],v=>setPack('voltage_model',v)),field('Battery ledger names, comma separated',Array.isArray(energy.pack_mass_item_names)?energy.pack_mass_item_names.join(', '):'',v=>setPack('pack_mass_item_names',v?v.split(',').map(s=>s.trim()):null),'text'));
  [['Pack energy density, Wh/kg','pack_wh_per_kg'],['Usable fraction before reserve','usable_fraction'],['Usable energy after reserve, J','usable_energy_j'],['Pack power limit, W','max_electrical_power_w'],['Nominal voltage, V','nominal_voltage_v'],['Pack current limit, A','max_current_a']].forEach(([label,key])=>pf.append(field(label,energy[key],v=>setPack(key,v))));
  pf.append(field('Held reserve fraction',data.mission.reserve_policy?.value,v=>{data.mission.reserve_policy={kind:'fraction',value:v,convention:'held_usable_energy_fraction'};changed();}));pack.append(pf);
  const cases=node('section');cases.append(node('h3','Required alternative cases'),node('p','Static hover is the first trim regime. Other conditions require an eligible model.'));
  const atm=node('div');atm.className='fields';[['Absolute pressure, Pa','pressure_pa','number'],['Temperature, K','temperature_k','number'],['Atmosphere source','source','text']].forEach(([label,key,type])=>atm.append(field(label,data.atmosphere[key],v=>{data.atmosphere[key]=v;changed();},type)));cases.append(atm);
  if(options.evaluateAtmosphere)mountAtmospherePreview(cases,{read,evaluate:options.evaluateAtmosphere,apply:next=>{data=next;rebuild();}});
  (data.mission.cases||[]).forEach((c,index)=>{
    const row=node('fieldset');row.append(node('legend','Case '+(index+1)),field('Case ID',c.name,v=>{c.name=v;changed();},'text'),field('Duration, s',c.duration_s,v=>{c.duration_s=v;changed();}),field('Case source / scope',c.source_note,v=>{c.source_note=v;changed();},'text'));
    row.append(choice('Case kind',c.kind,['hover','axial_climb'],v=>{c.kind=v;changed();}),
      field('Failed rotor IDs, comma separated',c.failed_rotor_ids?.join(', '),v=>{c.failed_rotor_ids=v?v.split(',').map(s=>s.trim()):[];changed();},'text'),
      field('Declared axial climb inflow, m/s',c.axial_inflow_m_s,v=>{c.axial_inflow_m_s=v;changed();}));
    triple(row,'World velocity, m/s',c,'velocity_world_m_s',changed);
    triple(row,'Torque-band moment allowance, Nm',c,'torque_band_moment_allowance_nm',changed);
    row.append(field('Torque-band allowance source',c.torque_band_allowance_source,v=>{c.torque_band_allowance_source=v;changed();},'text'));
    data.rotors.forEach(r=>row.append(field('Case map SHA-256 for '+r.rotor_id,c.performance_source_by_rotor?.[r.rotor_id],v=>{c.performance_source_by_rotor||={};if(v)c.performance_source_by_rotor[r.rotor_id]=v;else delete c.performance_source_by_rotor[r.rotor_id];changed();},'text')));
    const required=node('label','Required for headline'),check=node('input');check.type='checkbox';check.checked=c.required!==false;check.addEventListener('change',()=>{c.required=check.checked;changed();});required.append(check);row.append(required);
    triple(row,'Air-relative velocity, m/s',c,'air_relative_velocity_body_m_s',changed);
    triple(row,'Body force, N',c,'body_force_body_n',changed);triple(row,'Body moment about origin, Nm',c,'body_moment_origin_body_nm',changed);
    triple(row,'Angular velocity, rad/s',c,'angular_velocity_body_rad_s',changed);triple(row,'Angular acceleration, rad/s²',c,'angular_acceleration_body_rad_s2',changed);
    row.append(field('Body-load source, including zero loads',c.body_load_source,v=>{c.body_load_source=v;changed();},'text'));
    row.append(button('Remove case '+(index+1),()=>{data.mission.cases.splice(index,1);rebuild();}));cases.append(row);
  });
  cases.append(button('Add static hover case',()=>{data.mission.cases||=[];data.mission.cases.push({name:'hover_'+(data.mission.cases.length+1),kind:'hover',required:true,duration_s:null,velocity_world_m_s:[0,0,0],attitude_deg_zyx:[0,0,0],acceleration_target_m_s2:[0,0,0],air_relative_velocity_body_m_s:[null,null,null],angular_velocity_body_rad_s:[0,0,0],angular_acceleration_body_rad_s2:[0,0,0],source_note:null});rebuild();}));
  const checks=node('section');checks.append(node('h3','Saved input checks'));const output=node('div');output.id='inspection-report';
  checks.append(button('Inspect saved mass and readiness',async()=>{try{const r=await inspect();output.replaceChildren(node('p',r.mass.complete?`Installed mass ${r.mass.total_mass_kg} kg; empty mass ${r.mass.empty_airframe_mass_kg} kg; CG [${r.mass.cg_body_m.join(', ')}] m.`:'Mass incomplete: '+[...r.mass.missing,...r.mass.errors].join('; ')),node('p','Pack: '+r.pack.status+(r.pack.detail?' · '+r.pack.detail:'')));const detail=node('details');detail.append(node('summary','Full saved-input report'),node('pre',JSON.stringify(r,null,2)));output.append(detail);}catch(error){output.textContent=error.message;}}),output);
  const model=node('section');model.append(node('h3','Study model and provenance'),node('p','Fixed-condition convex hover curves are supported. Missing or unsupported inputs withhold a payload result.'));
  const mf=node('div');mf.className='fields';data.fidelity||={};const pilot=data.fidelity.local_pilot||{};
  const setModel=(key,v)=>{data.fidelity.local_pilot||={};data.fidelity.local_pilot[key]=v;changed();};
  mf.append(choice('Data scope',data.identity?.data_scope,['analytic_fixture','client_unvalidated'],v=>{data.identity.data_scope=v;changed();}),choice('Local trim model',pilot.model_version,['convex_static_hover_v1','convex_axial_capacity_v2'],v=>setModel('model_version',v)),field('Auxiliary electrical power, W',pilot.auxiliary_power_w,v=>setModel('auxiliary_power_w',v)));
  ['lower','upper'].forEach((label,i)=>mf.append(field('Declared payload '+label+' domain, kg',pilot.payload_domain_kg?.[i],v=>{data.fidelity.local_pilot||={};if(!Array.isArray(data.fidelity.local_pilot.payload_domain_kg))data.fidelity.local_pilot.payload_domain_kg=[null,null];data.fidelity.local_pilot.payload_domain_kg[i]=v;changed();})));model.append(mf);
  const rotors=node('section');rotors.append(node('h3','Rotors and retained performance sources'),node('p','Import rotor_map_v1 JSON, then explicitly choose matching rotors. Original bytes are retained; importing a file does not approve its performance.'));
  const upload=node('label','Import performance JSON'),file=node('input');file.type='file';file.accept='.json,application/json';upload.append(file);const importResult=node('div');
  let importGeneration=0;
  file.addEventListener('change',async()=>{const request=++importGeneration;try{if(!file.files[0])return;importResult.replaceChildren();if(file.files[0].size>500000)throw new Error('Map source exceeds 500 kB limit.');const raw=await file.files[0].text();if(request!==importGeneration)return;const result=await importMap(raw);if(request!==importGeneration||!file.isConnected)return;renderSourceBinding(importResult,result,read(),{
    read,enabled:()=>!file.disabled&&file.isConnected,
    apply:(next,count)=>{data=next;rebuild();options.onMapBound?.(count);container.querySelector('[data-readiness-group=rotors]>summary')?.focus();}
  });}catch(error){if(request===importGeneration&&file.isConnected)importResult.textContent=error.message;}finally{if(request===importGeneration)file.value='';}});rotors.append(upload,importResult);
  mountSourceLibrary(rotors,{...options,read,apply:(next,count)=>{data=next;rebuild();options.onMapBound?.(count);container.querySelector('[data-readiness-group=rotors]>summary')?.focus();}});
  (data.rotors||[]).forEach((r,index)=>{const row=node('fieldset');row.append(node('legend','Rotor '+(index+1)));
    [['Rotor ID','rotor_id'],['Configuration ID','configuration_id'],['Retained map SHA-256','map_ref']].forEach(([label,key])=>row.append(field(label,r[key],v=>{r[key]=v;changed();},'text')));
    triple(row,'Centre, m',r,'center_body_m',changed);triple(row,'Unit axis',r,'axis_body',changed);
    [['Radius, m','radius_m'],['Pitch, degrees','pitch_deg'],['Rotation sign: +1 or -1','rotation_sign']].forEach(([label,key])=>row.append(field(label,r[key],v=>{r[key]=v;changed();})));
    [['Continuous RPM limit','max_rpm'],['Continuous DC input power, W','max_electrical_power_w'],['Continuous DC input current, A','max_input_current_a']].forEach(([label,key])=>row.append(field(label,r.sustained_limits?.[key],v=>{r.sustained_limits||={};r.sustained_limits[key]=v;changed();})));
    row.append(button('Remove rotor '+(index+1),()=>{data.rotors.splice(index,1);rebuild();}));rotors.append(row);
  });rotors.append(button('Add rotor',()=>{data.rotors||=[];data.rotors.push({rotor_id:'rotor_'+(data.rotors.length+1),configuration_id:null,map_ref:null,center_body_m:[null,null,null],axis_body:[null,null,null],radius_m:null,pitch_deg:null,rotation_sign:null,sustained_limits:{}});rebuild();}));
  const ordered=node('section');ordered.append(node('h3','Chronological mission'),node('p','Optional ordered constant-hover segments share one fixed pack. Leave empty for alternative-case analysis. Variable or transient profiles require another model.'));
  (Array.isArray(data.mission.sequence)?data.mission.sequence:[]).forEach((s,index)=>{const row=node('fieldset');row.append(node('legend','Segment '+(index+1)),field('Segment ID',s.segment_id,v=>{s.segment_id=v;changed();},'text'),field('Referenced case ID',s.case_id,v=>{s.case_id=v;changed();},'text'),field('Segment duration, s',s.duration_s,v=>{s.duration_s=v;changed();}),field('Segment source / scope',s.source_note,v=>{s.source_note=v;changed();},'text'),choice('Power profile',s.power_profile,['constant'],v=>{s.power_profile=v;changed();}),button('Remove segment '+(index+1),()=>{data.mission.sequence.splice(index,1);rebuild();}));ordered.append(row);});
  ordered.append(button('Add constant-hover segment',()=>{if(!Array.isArray(data.mission.sequence))data.mission.sequence=[];data.mission.sequence.push({segment_id:'segment_'+(data.mission.sequence.length+1),case_id:null,duration_s:null,source_note:null,power_profile:'constant'});rebuild();}));
  [[mass,'mass'],[pack,'battery'],[cases,'cases'],[model,'model'],[rotors,'rotors'],[ordered,'sequence']].forEach(([section,key])=>{const group=node('details');group.dataset.readinessGroup=key;const heading=section.querySelector('h3');group.append(node('summary',heading.textContent));heading.remove();group.append(section);container.append(group);});container.append(checks);
  mountAdvanced(container,data,changed,rebuild,options);
}
