import {mountComponentCalculations} from './simple-calculations.js?v=airspeed-independent';
import {createViewer} from './viewer3d.js?v=geometry-3';
import {STLLoader} from '/web/vendor/STLLoader.js';

const $ = id => document.getElementById(id);
const state = {aircraft:document.body.dataset.initialAircraft||'multirotor', step:1, geometry:[], viewer:null, viewing:false, loading:false, notes:''};
let componentCalculations=null;
const unitScale = {m:1,mm:.001,cm:.01,in:.0254,ft:.3048};
const fieldIds = ['payload','altitude','speed','duration','mass','rotors','diameter','rpm','wingarea','length','viscosity'];
const names = {multirotor:'Multirotor', 'fixed-wing':'Fixed-wing',hybrid:'Hybrid VTOL',helicopter:'Helicopter',tiltrotor:'Tiltrotor'};
const objectiveNames = {hover:'Hover and payload',rotor:'Rotor performance',aero:'Full-aircraft aerodynamics',dynamics:'Flight dynamics and rotor-out'};

function number(id) {
  const raw = $(id)?.value.trim() ?? '';
  return raw === '' ? null : Number(raw);
}
function isFiniteInRange(v,min,max=Infinity) {return v !== null && Number.isFinite(v) && v >= min && v <= max;}
function given(v) {return v !== null && Number.isFinite(v);}
function validCore() {
  return isFiniteInRange(number('payload'),0) && isFiniteInRange(number('altitude'),0,32000) &&
    isFiniteInRange(number('speed'),0) && isFiniteInRange(number('duration'),.01);
}
function isRotorcraft() {return state.aircraft !== 'fixed-wing';}
function physicsDecision() {
  const objective = $('objective').value;
  const reasons = [], requirements=[];
  let model, status='PARTIAL';
  if (objective==='hover') {
    model='Static-hover / payload and mission screening';
    if (!isRotorcraft()) reasons.push('Hover is not an eligible primary objective for the selected fixed-wing type.');
    requirements.push('Qualified rotor maps bound to rotor locations','Complete mass and centre-of-gravity ledger','Declared battery, motor and scenario limits');
    if (!given(number('mass'))) reasons.push('Aircraft mass has not been declared.');
    if (!isFiniteInRange(number('rotors'),1,32)) reasons.push('Rotor count is required.');
    if (!isFiniteInRange(number('diameter'),.00001)) reasons.push('Rotor geometry is incomplete.');
    if (state.aircraft==='fixed-wing') status='UNSUPPORTED';
  } else if (objective==='rotor') {
    model='Isolated rotor/BEMT experimental assessment';
    requirements.push('Explicit rotor geometry and operating RPM','Measured rotor data or declared aerodynamic coefficients','Check model regime and previously observed thrust/power discrepancies');
    if (!isFiniteInRange(number('diameter'),.00001) || !isFiniteInRange(number('rpm'),.00001)) reasons.push('Rotor diameter and speed are required.');
    if (state.aircraft==='fixed-wing') reasons.push('Select an applicable propeller/rotor source for this fixed-wing configuration.');
    status='EXPERIMENTAL';
  } else if (objective==='aero') {
    model='Full-aircraft external CFD';
    requirements.push('Reviewed watertight CAD, component roles and boundary patches','Validated turbulence and rotating-rotor coupling as needed','OpenFOAM-compatible case, mesh-quality gates and multi-grid validation');
    reasons.push('General drone/rotor-airframe CFD is not qualified in this branch.');
    status='UNSUPPORTED';
  } else if (objective==='propulsion') {
    model='Propulsion assessment';
    requirements.push('Declared propeller or rotor geometry and operating points','Verified motor, battery and propulsion performance data','Reviewed propulsion operating limits and efficiency evidence');
    reasons.push('Complete propulsion-system analysis is unavailable; isolated-hover rotor calculations exclude motor and battery performance.');
    status='UNSUPPORTED';
  } else if (objective==='structure') {
    model='Structural assessment';
    requirements.push('Declared materials and structural geometry','Reviewed loads, constraints and connections','Verified structural model and allowable limits');
    reasons.push('Full-aircraft structural analysis is unavailable; an ideal beam check is a separate component calculation.');
    status='UNSUPPORTED';
  } else if (objective==='full') {
    model='Full analysis: Aero, Propulsion and Structure';
    requirements.push('Aero: reviewed geometry, flow conditions and qualified aerodynamic evidence','Propulsion: verified propeller or rotor, motor and battery data','Structure: declared materials, loads, constraints and allowable limits','Reviewed coupling and consistent operating conditions across all three disciplines');
    reasons.push('Coupled full-aircraft execution is unavailable. Separate component checks do not constitute Full analysis.');
    status='UNSUPPORTED';
  } else {
    model='Simplified static allocation / numerical rotor-out dynamics';
    requirements.push('Rotor-arm geometry, inertia tensor and thrust limits','Controller/actuator parameters and failure scenarios','Independent physical flight-dynamics validation for flight claims');
    reasons.push('Defined numerical studies exist, but full nonlinear six-DOF flight qualification is not established.');
    status='EXPERIMENTAL';
  }
  if (!validCore()) reasons.push('Complete the four essential mission inputs.');
  if (!state.geometry.length) reasons.push('Upload geometry for geometry-driven analyses.');
  if (state.geometry.some(g=>g.role==='unassigned')) reasons.push('Declare each uploaded geometry component role.');
  if (state.geometry.length) requirements.push('Independently verify closed surfaces and valid topology before meshing');
  return {model,status,reasons,requirements};
}
function isa(altitudeM) {
  if (!isFiniteInRange(altitudeM,0,32000)) return null;
  const R=287.05287,g=9.80665;
  let T=288.15, P=101325;
  const layers=[[11000,-.0065],[20000,0],[32000,.001]];
  let prev=0;
  for (const [edge,lapse] of layers) {
    const dh=Math.min(altitudeM,edge)-prev;
    if (dh>0) {
      const next=T+lapse*dh;
      P*=lapse===0?Math.exp(-g*dh/(R*T)):Math.pow(next/T,-g/(lapse*R));
      T=next;
    }
    prev=edge;
    if (altitudeM<=edge) break;
  }
  return {temperature_k:T,pressure_pa:P,density_kg_m3:P/(R*T),speed_of_sound_m_s:Math.sqrt(1.4*R*T)};
}
function format(value,digits=3) {return Number.isFinite(value)?value.toLocaleString(undefined,{maximumFractionDigits:digits}):'—';}
function renderAtmosphere(){
  const atmospheric = isa(number('altitude'));
  const v=number('speed'), length=number('length'), nu=number('viscosity');
  $('atm-temperature').textContent=atmospheric?format(atmospheric.temperature_k,2)+' K':'—';
  $('atm-density').textContent=atmospheric?format(atmospheric.density_kg_m3,5)+' kg/m³':'—';
  $('atm-mach').textContent=atmospheric&&isFiniteInRange(v,0)?format(v/atmospheric.speed_of_sound_m_s,4):'—';
  const Re=atmospheric&&given(v)&&isFiniteInRange(length,.000001)&&isFiniteInRange(nu,.0000000001)?v*length/nu:null;
  $('atm-re').textContent=Re===null?'Need length + viscosity':format(Re,0);
}
function setSafeText(el,text){el.textContent=text;}
function showStep(step){
  state.step=step;
  document.querySelectorAll('main > .stage').forEach(section=>{section.hidden=section.id!=='step-'+step;});
  document.querySelectorAll('[data-step]').forEach(button=>{
    const n=Number(button.dataset.step);
    button.classList.toggle('active',n===step);
    button.classList.toggle('visited',n<step);
    if(n===step)button.setAttribute('aria-current','step');
    else button.removeAttribute('aria-current');
  });
  if(step>=2)renderPhysics();
  if(step>=3)renderPreflight();
  document.querySelector('main').scrollIntoView({block:'start',behavior:'instant'});
}
function decisionCard(title,desc,kind='warn'){
  const block=document.createElement('div');block.className='decision '+kind;
  const label=document.createElement('strong');label.textContent=title;
  const small=document.createElement('small');small.textContent=desc;
  block.append(label,small);return block;
}
function renderPhysics(){
  renderAtmosphere();
  const summary=$('mission-summary');
  if(summary){
    summary.replaceChildren();
    const entries=[['Aircraft',names[state.aircraft]],['Analysis focus',$('objective').selectedOptions[0].textContent],
      ['Payload',given(number('payload'))?number('payload')+' kg':'Not entered'],
      ['Altitude',given(number('altitude'))?number('altitude')+' m':'Not entered'],
      ['Speed',given(number('speed'))?number('speed')+' m/s':'Not entered'],
      ['Duration',given(number('duration'))?number('duration')+' min':'Not entered'],
      ['Geometry',state.geometry.length+' file(s)']];
    for(const [label,value] of entries){
      const row=document.createElement('div'),title=document.createElement('strong'),text=document.createElement('span');
      title.textContent=label+': ';text.textContent=value;row.append(title,text);summary.append(row);
    }
  }
  const plan=physicsDecision();
  const root=$('physics-plan');root.replaceChildren();
  const kind=document.body.dataset.workflow==='simple'?'warn':plan.status==='UNSUPPORTED'?'error':plan.status==='EXPERIMENTAL'?'warn':'ok';
  root.append(decisionCard(document.body.dataset.workflow==='simple'&&['full','aero','propulsion','structure','rotor'].includes($('objective').value)?'Component calculations available below':plan.status==='UNSUPPORTED'?'Unsupported analysis capability':plan.status==='EXPERIMENTAL'?'Experimental physics model':'Restricted workflow available',
    plan.model+(document.body.dataset.workflow==='simple'?'. Optional component checks below use explicit model inputs; they do not establish full-aircraft validity.':'. The current page does not execute the solver.'),kind));
  if (plan.reasons.length) {
    const sub=document.createElement('b');sub.textContent='Missing information or limitations';root.append(sub);
    const ul=document.createElement('ul');plan.reasons.forEach(reason=>{const li=document.createElement('li');li.textContent=reason;ul.append(li);});root.append(ul);
  }
  const sub=document.createElement('b');sub.textContent='Required physics evidence';root.append(sub);
  const ul=document.createElement('ul');plan.requirements.forEach(req=>{const li=document.createElement('li');li.textContent=req;ul.append(li);});root.append(ul);
}
function checkRow(label,ok,more){
  const item=document.createElement('div');
  const marker=document.createElement('span');marker.className='status-dot '+(ok?'passed':'missing');marker.textContent=ok?'✓':'!';
  const content=document.createElement('span');const b=document.createElement('b');b.textContent=label;
  const text=document.createElement('small');text.style.display='block';text.style.color='#72849b';text.style.marginTop='3px';text.textContent=more;
  content.append(b,text);item.append(marker,content);return item;
}
function flightAssessment(){
  const failures=componentCalculations?.failures()??[];
  const reasons=failures.map(item=>item.discipline+': '+item.reason);
  if(!validCore())reasons.push('Complete valid payload, altitude, speed and duration inputs.');
  if(!state.geometry.length)reasons.push('No aircraft geometry has been supplied.');
  else if(state.geometry.some(g=>g.role==='unassigned'))reasons.push('Choose a component role for every uploaded geometry file.');
  reasons.push('A complete aircraft flight simulation has not been run or validated.');
  reasons.push('Individual component checks cannot establish flight success or flight failure.');
  return {outcome:'NOT_DETERMINED',label:'Flight outcome: Not determined',failed_checks:failures,reasons};
}
function renderPreflight(){
  const plan=physicsDecision(), pre=$('preflight');
  const rolesComplete=state.geometry.length>0&&state.geometry.every(g=>g.role!=='unassigned');
  const adv=given(number('mass')) && (!isRotorcraft() || isFiniteInRange(number('rotors'),1,32));
  if(document.body.dataset.workflow==='simple'){
    const assessment=flightAssessment();
    const title=document.createElement('h2');title.textContent=assessment.label;
    const why=document.createElement('p');why.textContent=assessment.failed_checks.length?'Why: some component checks could not be completed.':'Why: there is not enough evidence for a flight verdict.';
    const list=document.createElement('ul');for(const reason of assessment.reasons){const item=document.createElement('li');item.textContent=reason;list.append(item);}
    pre.replaceChildren(title,why,list);
  }else pre.replaceChildren(
    checkRow('Mission data',validCore(),'Payload, altitude, speed and duration must be valid.'),
    checkRow('STL geometry preview',state.geometry.length>0,'Local geometry preview only; keep the original STL files with your export.'),
    checkRow('Component roles',rolesComplete,'Part roles must be explicitly declared; automatic recognition is not qualified.'),
    checkRow('Detailed engineering inputs',adv,'Mass, rotor geometry and verified source data depend on the physics model.'),
    checkRow('Scientific model qualification',false,'Selected model: '+plan.model+'; aircraft-specific solver verification is still required.'),
    checkRow('Mesh independence',false,'No solver runs, measured cell counts, or independent three-mesh results yet.')
  );
  const box=$('run-reason');box?.replaceChildren(decisionCard(document.body.dataset.workflow==='simple'?'Export intake and any component records':'Numerical solver not connected to this screen',
    'Download the declared inputs, preflight notes and any completed component records. No full-aircraft CFD or physical validation is established.', 'warn'));
}
function refresh(){
  if($('fixed-wing-launch'))$('fixed-wing-launch').hidden=state.aircraft!=='fixed-wing';
  componentCalculations?.invalidate();
  const geom=state.geometry.length>0, inputs=validCore(), plan=physicsDecision();
  $('geometry-indicator').textContent=geom?'✓':'○';$('geometry-indicator').classList.toggle('ok',geom);
  $('geometry-check').textContent=geom?`${state.geometry.length} geometry file(s) previewed`:'Geometry missing';
  $('inputs-indicator').textContent=inputs?'✓':'○';$('inputs-indicator').classList.toggle('ok',inputs);
  $('inputs-check').textContent=inputs?'Mission inputs valid':'Complete mission inputs';
  $('physics-indicator').textContent=plan.status==='PARTIAL'?'✓':'!';
  $('physics-indicator').classList.toggle('ok',plan.status==='PARTIAL');
  $('physics-check').textContent=plan.status==='UNSUPPORTED'?'Analysis not qualified':plan.status==='EXPERIMENTAL'?'Experimental model':'Physics requirements pending';
  if(state.step>=2)renderPhysics();
  if(state.step>=3)renderPreflight();
}
function setAircraft(kind){
  state.aircraft=kind;
  document.querySelectorAll('.aircraft-option').forEach(b=>{
    const chosen=b.dataset.aircraft===kind;
    b.classList.toggle('active',chosen);b.setAttribute('aria-pressed',String(chosen));
  });
  $('objective').value=kind==='fixed-wing'?'aero':'hover';
  refresh();
}
async function sha256(buffer){
  if(!globalThis.crypto?.subtle)return null;
  const digest=await crypto.subtle.digest('SHA-256',buffer);
  return [...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');
}
function componentRow(g){
  const line=document.createElement('div');line.className='file-item';
  const text=document.createElement('span');text.className='filename';
  const name=document.createElement('b');name.textContent=g.name;
  const info=document.createElement('small');info.textContent=format(g.triangles,0)+' triangles · '+(g.bytes/(1024*1024)).toFixed(2)+' MB';
  text.append(name,info);
  const role=document.createElement('select');role.setAttribute('aria-label','Role of '+g.name);
  for (const [v,label] of [['unassigned','Select role'],['fuselage','Fuselage'],['rotor','Rotor'],['wing','Wing'],['arm','Arm'],['other','Other']]){
    const op=document.createElement('option');op.value=v;op.textContent=label;role.append(op);
  }
  role.value=g.role;
  role.addEventListener('change',()=>{g.role=role.value;refresh();});
  line.append(text,role);return line;
}
function renderFiles(){
  const list=$('geometry-list');list.replaceChildren(...state.geometry.map(componentRow));
  const viewer=$('geometry-view'),chip=$('viewer-chip'),placeholder=$('geometry-placeholder');
  if(state.geometry.length===0){placeholder.hidden=false;chip.hidden=true;state.viewer?.clear();return;}
  try {
    state.viewer??=createViewer(viewer);
    state.viewer.showStl(state.geometry.map(x=>x.buffer),unitScale[$('geometry-units').value]);
    placeholder.hidden=true;chip.hidden=false;
    $('geometry-status').textContent=state.geometry.length+' STL file(s) loaded. Component roles and topology remain unverified.';
  }catch(err){
    placeholder.hidden=false;chip.hidden=true;
    $('geometry-status').textContent='3D preview unavailable: '+(err?.message||String(err));
  }
}
async function handleFiles(files) {
  if(state.loading)return;
  if(!Object.hasOwn(unitScale,$('geometry-units').value)){
    $('geometry-status').textContent='Select the STL source units before uploading.';return;
  }
  const list=Array.from(files||[]).filter(Boolean);
  if(!list.length)return;
  if(list.length>8){$('geometry-status').textContent='Maximum eight STL components per preview.';return;}
  state.loading=true;$('geometry-status').textContent='Parsing geometry locally…';
  try {
    const loader=new STLLoader(),read=[];
    let totalBytes=0,totalTriangles=0;
    for(const file of list){
      totalBytes+=file.size;
      if(!/\.stl$/i.test(file.name))throw new Error('Only .stl files are supported by this preview.');
      if(file.size>50_000_000||totalBytes>50_000_000)throw new Error('STL input exceeds 50 MB total upload limit.');
      const buffer=await file.arrayBuffer();
      const parsed=loader.parse(buffer);
      const positions=parsed.getAttribute('position');
      const n=positions.count/3;
      const validPositions=positions.array.every(Number.isFinite);
      parsed.dispose();
      if(!Number.isInteger(n)||n<1||!validPositions)throw new Error('STL must contain complete triangles with finite coordinates.');
      totalTriangles+=n;
      if(totalTriangles>1_000_000)throw new Error('Geometry exceeds one million triangles.');
      read.push({name:file.name,bytes:file.size,triangles:n,buffer,sha256:await sha256(buffer),role:'unassigned'});
    }
    state.geometry=read;renderFiles();
  }catch(error){
    $('geometry-status').textContent='Import rejected: '+(error?.message||String(error));
  }finally{state.loading=false;refresh();}
}
function exportIntake(){
  const values=Object.fromEntries(fieldIds.map(id=>[id,number(id)]));
  const atmospheric=isa(values.altitude);
  const physics=physicsDecision();
  const report={
    schema:'physimesh.hackathon.simulation_intake.v1',
    document_type:'user_declared_analysis_intake_NOT_SOLVER_RESULT',
    generated_at_utc:new Date().toISOString(),
    workflow:document.body.dataset.workflow==='simple'?'simple_analysis':'hackathon_intake',
    component_calculations:componentCalculations?.records() ?? [],
    flight_assessment:flightAssessment(),
    aircraft_configuration:state.aircraft,
    objective:$('objective').value,
    input_units:{payload:'kg',altitude:'m',speed:'m/s',duration:'min',mass:'kg',rotors:'count',
                 diameter:'m',rpm:'1/min',wingarea:'m2',length:'m',viscosity:'m2/s'},
    declared_inputs:values,
    user_notes:state.notes,
    geometry:{source_units:$('geometry-units').value||null,files:state.geometry.map(x=>({
      filename:x.name,sha256_original_bytes:x.sha256,byte_count:x.bytes,triangle_count_preview:x.triangles,declared_role:x.role
    })),source_bytes_included:false,topology_validated:false},
    atmosphere_preview:atmospheric,
    physics_preflight:{model:physics.model,status:physics.status,
                       missing_or_unsupported:physics.reasons,required_evidence:physics.requirements},
    mesh_study:{minimum_levels:3,target_quantity:null,measured_cells:[],
                solver_runs_completed:0,grid_independence:'NOT_ESTABLISHED'},
    scientific_status:'NOT_SIMULATED'
  };
  const blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob),a=document.createElement('a');
  a.href=url;a.download='PHYSIMESH_drone_simulation_intake.json';document.body.append(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
document.querySelectorAll('.aircraft-option').forEach(b=>b.addEventListener('click',()=>setAircraft(b.dataset.aircraft)));
document.querySelectorAll('[data-step]').forEach(b=>b.addEventListener('click',()=>showStep(Number(b.dataset.step))));
document.querySelectorAll('[data-goto]').forEach(b=>b.addEventListener('click',()=>showStep(Number(b.dataset.goto))));
fieldIds.forEach(id=>$(id)?.addEventListener('input',refresh));
$('objective').addEventListener('change',refresh);
$('geometry-units').addEventListener('change',()=>{
  if(state.geometry.length){state.geometry=[];renderFiles();$('geometry-status').textContent='Source units changed. Re-upload geometry for a correct preview.';}
  refresh();
});
$('geometry-files').addEventListener('change',event=>{
  const files=Array.from(event.target.files||[]);
  event.target.value=''; // Allow retrying the same file after choosing units or correcting an error.
  handleFiles(files);
});
const drop=$('geometry-drop');
drop.addEventListener('dragover',event=>{event.preventDefault();drop.classList.add('dragging');});
drop.addEventListener('dragleave',()=>drop.classList.remove('dragging'));
drop.addEventListener('drop',event=>{event.preventDefault();drop.classList.remove('dragging');handleFiles(event.dataTransfer?.files);});
$('continue').addEventListener('click',()=>showStep(2));
$('physics-back').addEventListener('click',()=>showStep(1));
$('physics-next').addEventListener('click',()=>showStep(3));
$('export')?.addEventListener('click',exportIntake);
$('example').addEventListener('click',()=>{
  const example={payload:10,altitude:500,speed:0,duration:15};
  Object.entries(example).forEach(([id,value])=>$(id).value=String(value));
  state.notes='Illustrative mission input values for UI evaluation only; not validated hardware or flight performance.';
  refresh();
});
$('inputs-form').addEventListener('submit',event=>event.preventDefault());
refresh();

if($('component-calculations')) componentCalculations=mountComponentCalculations($('component-calculations'));

$('setup-fixed-wing')?.addEventListener('click',()=>{if(state.aircraft!=='fixed-wing')return;showStep(2);const panel=document.querySelector('[data-calculation="aero"]');if(panel){panel.open=true;panel.scrollIntoView({block:'start'});panel.querySelector('input')?.focus();}});
