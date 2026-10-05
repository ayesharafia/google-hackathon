import {mountEditors} from './input-editors.js';
import {createViewer} from './viewer3d.js';
import {renderStudy,renderComparison} from './study-view.js';
const $ = id => document.getElementById(id);
let token = '', current = null, dirty = false, busy = false, generation = 0, study = null, viewer = null;
let layoutGeneration=0; const geometryCache=new Map();
const editControls = ['snapshot', 'save', 'reload', 'freeze', 'export-draft'];
function message(text, error = false) { $('message').textContent = text; $('message').className = error ? 'error' : ''; }
function controls() {
  ['create', 'project-title', 'projects', 'open'].forEach(id => { $(id).disabled = !token || busy; });
  $('open').disabled = !token || busy || !$('projects').value;
  $('token').disabled = busy; document.querySelector('#connection button').disabled = busy;
  $('example').disabled = !token || busy;
  ['realistic-example','motorout-example'].forEach(id=>$(id).disabled=!token||busy);
  $('calculate').disabled = !current || busy || dirty || !token || !current.revisions.some(r=>r.draft_version===current.draft_version);
  $('export-study').disabled = !study || busy || !token;
  $('export-pdf').disabled = !study || busy || !token;
  ['compare-before','compare-after','compare'].forEach(id=>{$(id).disabled=busy||!token||!current?.studies?.length;});
  document.querySelectorAll('#input-editors input,#input-editors select,#input-editors button,#input-editors textarea').forEach(input => { input.disabled = busy || !current || !token; });
  editControls.forEach(id => { $(id).disabled = !current || !token || busy || (id === 'freeze' && dirty); });
  document.querySelectorAll('.revision-button').forEach(button => { button.disabled = busy || !token; });
}
async function api(path, options = {}) {
  const response = await fetch('/api/drone' + path, { ...options, headers: { Authorization: 'Bearer ' + token, ...options.headers }, signal: AbortSignal.timeout(60000) });
  const data = await response.json();
  if (!response.ok) { const detail = data.detail;const error=new Error(typeof detail === 'string' ? detail : detail?.message || JSON.stringify(detail));error.detail=detail;throw error; }
  return data;
}
function payload(method, body) { return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }; }
async function action(work) {
  if (busy) return;
  busy = true; controls();
  try { await work(); } catch (error) { message(error.message, true);if(error.detail?.code==='draft_conflict'){$('conflict-message').textContent='The server now has draft version '+error.detail.current_version+'. Your unsaved inputs are still in this editor. Export them, keep editing, or replace them with the latest saved draft.';$('draft-conflict').showModal();} }
  finally { busy = false; controls(); }
}
function preserveEdits() { return !dirty || confirm('Discard the unsaved edits and open the saved design?'); }
async function inventory(selected = '') {
  const data = await api('/projects');
  $('projects').replaceChildren(...data.projects.map(project => { const option = document.createElement('option'); option.value = project.project_id; option.textContent = project.title + ' · ' + project.project_id.slice(-8); return option; }));
  if (selected) $('projects').value = selected;
}
function render(project) {
  current = project; dirty = false;
  study=null;$('study-report').replaceChildren();
  $('snapshot').value = JSON.stringify(JSON.parse(project.snapshot_json), null, 2);
  $('design-title').textContent = project.title;
  $('save-state').textContent = 'Saved draft version ' + project.draft_version + '. Edits create a new version; retained revisions stay unchanged.';
  $('project-record').textContent = project.project_id + ' · version ' + project.draft_version;
  $('revision-detail').hidden = true;
  editors();
  const rows = project.revisions.map(record => {
    const li = document.createElement('li'), button = document.createElement('button');
    button.type = 'button'; button.className = 'revision-button';
    button.textContent = 'Draft ' + record.draft_version + ' · ' + record.revision_sha256.slice(0, 12);
    button.addEventListener('click', () => action(async () => {
      const pid = current.project_id, request = generation;
      const revision = await api(`/projects/${pid}/revisions/${record.revision_sha256}`);
      if (request !== generation || pid !== current?.project_id) return;
      $('revision-summary').textContent = 'Immutable local revision ' + record.revision_sha256 + '. Engineering approval pending.';
      $('revision-json').textContent = JSON.stringify(revision, null, 2);
      $('revision-detail').hidden = false;
    }));
    li.append(button); return li;
  });
  if (!rows.length) { const li = document.createElement('li'); li.textContent = 'No frozen revision yet.'; rows.push(li); }
  $('revisions').replaceChildren(...rows); controls();
  $('studies').replaceChildren(...(project.studies||[]).map(record=>{
    const li=document.createElement('li'),button=document.createElement('button');button.type='button';button.className='revision-button';button.textContent='Study '+record.study_sha256.slice(0,12);
    button.addEventListener('click',()=>action(async()=>{study=await api(`/projects/${current.project_id}/studies/${record.study_sha256}`);showStudy();layout();}));li.append(button);return li;
  }));
  ['compare-before','compare-after'].forEach(id=>$(id).replaceChildren(...(project.studies||[]).map(record=>{
    const option=document.createElement('option');option.value=record.study_sha256;option.textContent=record.created_utc+' · '+record.study_sha256.slice(0,12);return option;
  })));
  if(project.studies?.length>1)$('compare-before').selectedIndex=1;
  $('comparison-report').replaceChildren();layout();controls();
}
function currentStudy(){return !dirty&&current?.revisions.some(r=>r.draft_version===current.draft_version&&r.revision_sha256===study?.specification.revision_sha256);}
function showStudy(){if(study)renderStudy($('study-report'),study,currentStudy());}
async function geometryBytes(digest){
  if(!geometryCache.has(digest))geometryCache.set(digest,(async()=>{const response=await fetch('/api/drone/projects/geometry-sources/'+digest,{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(60000)});if(!response.ok){geometryCache.delete(digest);throw new Error('Retained geometry unavailable: HTTP '+response.status);}return response.arrayBuffer();})());
  return geometryCache.get(digest);
}
async function layout(){const request=++layoutGeneration;try{const data=JSON.parse($('snapshot').value),components=data.assembly?.components||[];
  if(!data.rotors?.length&&!components.length){if(viewer)viewer.showRotorLayout({rotors:[]},null);$('layout-note').textContent='No declared rotor layout or airframe. Add inputs or create a labelled example.';$('reset-layout').disabled=true;return;}
  if(components.length>64)throw new Error('Assembly preview supports at most 64 declared components.');
  const geometries=await Promise.all(components.map(async component=>({component,buffer:await geometryBytes(component.source_sha256)})));
  if(request!==layoutGeneration)return;
  if(geometries.reduce((sum,g)=>sum+g.buffer.byteLength,0)>50000000)throw new Error('Assembly preview exceeds 50 MB.');
  const bound=currentStudy()?study?.headline_candidate_checks?.find(c=>c.case_id===study.limiting_case_id||study.aggregate_limit):null;
  const record=currentStudy()?study?.cases?.find(c=>c.case_id===study.limiting_case_id):null;
  const highlighted=(data.rotors||[]).filter(r=>record?.active_constraints?.some(c=>c.startsWith(r.rotor_id+'_'))).map(r=>r.rotor_id),failed=bound?.failed_rotor_ids||[];
  viewer??=createViewer($('layout-view'));const count=viewer.showRotorLayout(data,bound?.candidate?.cg_body_m,{geometries,highlightedRotors:highlighted,failedRotors:failed});
  $('layout-note').textContent=count+' declared rotor disks; '+geometries.length+' retained airframe components. '+(record?'Governing case: '+record.case_id+'. ':'')+(highlighted.length?'Amber active rotor limits: '+highlighted.filter(r=>!failed.includes(r)).join(', ')+'. ':'')+(failed.length?'Red failed rotors: '+failed.join(', ')+'. ':'')+'Positions use the declared body frame. Geometry does not establish aircraft performance.';$('reset-layout').disabled=!(count||geometries.length);
}catch(error){if(request!==layoutGeneration)return;if(viewer)viewer.showRotorLayout({rotors:[]},null);$('layout-note').textContent='Layout unavailable: '+error.message;$('reset-layout').disabled=true;}}
async function guardedRequest(work){const request=generation,pid=current?.project_id,raw=$('snapshot').value;const result=await work();if(request!==generation||pid!==current?.project_id||raw!==$('snapshot').value)throw new Error('Inputs changed during import. The source was retained; reopen the import step to bind it to the current draft.');return result;}
async function openProject(pid) {
  const request = ++generation;
  const project = await api('/projects/' + pid);
  if (request !== generation) return;
  render(project); message('Saved design reopened. Physical readiness has not been inferred.');
}
function editors() {
  mountEditors($('input-editors'), () => JSON.parse($('snapshot').value), data => {
    $('snapshot').value = JSON.stringify(data, null, 2); dirty = true; const inspection=$('inspection-report');if(inspection)inspection.textContent='Inputs edited. Save and inspect again.';
    $('save-state').textContent = 'Unsaved edits. Save before freezing a revision.'; controls();
    showStudy();layout();
  }, async () => { if (dirty) throw new Error('Save the draft first to inspect these edits.');
    return api(`/projects/${current.project_id}/inspection`); }, dataset_json => guardedRequest(()=>api('/projects/performance-sources',payload('POST',{dataset_json}))),{
      conditionMap:(digest,policy)=>guardedRequest(()=>api('/projects/performance-sources/'+digest+'/condition',payload('POST',{policy}))),
      importGeometry:(files,units)=>guardedRequest(()=>{const body=new FormData();body.append('source_units',units);[...files].forEach(file=>body.append('files',file));return api('/import',{method:'POST',body});})
    });
}
$('connection').addEventListener('submit', event => {
  event.preventDefault(); if (busy) return;
  if (!preserveEdits()) return;
  token = $('token').value; $('token').value = ''; current = null; dirty = false; ++generation;
  geometryCache.clear();++layoutGeneration;
  $('snapshot').value = ''; $('design-title').textContent = 'Open a project to begin.';
  $('input-editors').replaceChildren();
  $('project-record').textContent = 'No project open.'; $('revision-detail').hidden = true;
  $('revisions').replaceChildren();
  $('studies').replaceChildren();study=null;$('study-report').replaceChildren();
  $('compare-before').replaceChildren();$('compare-after').replaceChildren();$('comparison-report').replaceChildren();
  if(viewer)viewer.showRotorLayout({rotors:[]},null);$('reset-layout').disabled=true;
  action(async () => { try { await inventory(); message('Connected to the local workspace. Select or create a project.'); }
    catch (error) { token = ''; throw error; } });
});
$('create-project').addEventListener('submit', event => { event.preventDefault(); if (!preserveEdits()) return; action(async () => {
  const project = await api('/projects', payload('POST', { title: $('project-title').value }));
  ++generation; render(project); await inventory(project.project_id); $('project-title').value = '';
  message('Project created with explicit unknown inputs.');
}); });
$('open').addEventListener('click', () => { if ($('projects').value && preserveEdits()) action(() => openProject($('projects').value)); });
$('reload').addEventListener('click', () => { if (current && preserveEdits()) action(() => openProject(current.project_id)); });
$('snapshot').addEventListener('input', () => { dirty = true; $('save-state').textContent = 'Unsaved edits. Save before freezing a revision.'; const binding=$('study-report').querySelector('.study-binding');if(binding)binding.textContent='Inputs edited. This retained study belongs to the previous frozen design.';controls();layout(); });
$('snapshot').addEventListener('change', () => {editors();showStudy();layout();});
$('save').addEventListener('click', () => action(async () => {
  const snapshot = $('snapshot').value;
  const project = await api(`/projects/${current.project_id}/draft`, payload('PUT', { expected_version: current.draft_version, snapshot_json: snapshot }));
  render(project); message('Draft saved. Previous frozen revisions remain available.');
}));
$('freeze').addEventListener('click', () => action(async () => {
  const result = await api(`/projects/${current.project_id}/revisions`, payload('POST', { expected_version: current.draft_version, purpose: 'screening' }));
  await openProject(current.project_id); message('Saved revision frozen: ' + result.revision_sha256 + '. Engineering approval pending.');
}));
function downloadDraft(){
  try { const raw = JSON.stringify(JSON.parse($('snapshot').value), null, 2), url = URL.createObjectURL(new Blob([raw], { type: 'application/json' }));
    const a = document.createElement('a'); a.href = url; a.download = current.project_id + (dirty ? '-unsaved' : '-v' + current.draft_version) + '.json'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),60000);
    message(dirty ? 'Unsaved input JSON download requested. This is not a retained revision.' : 'Saved draft JSON download requested.');
  } catch (error) { message('Invalid JSON: ' + error.message, true); }
}
$('export-draft').addEventListener('click',downloadDraft);
$('conflict-export').addEventListener('click',downloadDraft);
$('conflict-keep').addEventListener('click',()=>{$('draft-conflict').close();$('save').focus();});
$('conflict-reload').addEventListener('click',()=>{$('draft-conflict').close();action(()=>openProject(current.project_id));});
window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
$('example').addEventListener('click',()=>{if(!preserveEdits())return;action(async()=>{const project=await api('/projects/examples/hover',payload('POST',{}));++generation;render(project);await inventory(project.project_id);message('Illustrative design created. Save/freeze and evaluate; no real aircraft data is used.');});});
['realistic','motorout'].forEach(kind=>$(kind+'-example').addEventListener('click',()=>{if(!preserveEdits())return;action(async()=>{const project=await api('/projects/examples/'+kind,payload('POST',{}));++generation;render(project);await inventory(project.project_id);message('Synthetic noisy CT/CQ fixture created. Its uncertainty bounds and moment allowances are software declarations; no client data is used.');});}));
$('calculate').addEventListener('click',()=>action(async()=>{const revision=current.revisions.find(r=>r.draft_version===current.draft_version);message('Evaluating covered maps, force/moment balance and every required case…');const result=await api(`/projects/${current.project_id}/studies`,payload('POST',{revision_sha256:revision.revision_sha256}));render(await api('/projects/'+current.project_id));study=result;showStudy();layout();message('Bounded local study retained. Engineering approval and real-aircraft validation remain pending.');}));
async function downloadStudy(kind){
  const response=await fetch(`/api/drone/projects/${current.project_id}/studies/${study.study_sha256}/${kind==='pdf'?'pdf':'export'}`,{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(60000)});
  if(!response.ok){let detail;try{detail=(await response.json()).detail;}catch{}throw new Error(typeof detail==='string'?detail:'Study export failed: '+response.status);}
  const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download='hover-study-'+study.study_sha256+'.'+kind;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
  message(kind==='pdf'?'PDF download requested. The report identifies the exact retained JSON and frozen inputs.':'Exact retained JSON download requested, including source and revision bindings.');
}
$('export-study').addEventListener('click',()=>action(()=>downloadStudy('json')));
$('export-pdf').addEventListener('click',()=>action(()=>downloadStudy('pdf')));
$('compare').addEventListener('click',()=>action(async()=>{
  const report=await api(`/projects/${current.project_id}/comparisons`,payload('POST',{before:$('compare-before').value,after:$('compare-after').value}));
  renderComparison($('comparison-report'),report);message('Retained studies compared. Current unsaved inputs do not change either record.');
}));
$('reset-layout').addEventListener('click',()=>viewer?.reset());
controls();
message('Connect with the token used to start this local server. It is held in memory for this page only.');
