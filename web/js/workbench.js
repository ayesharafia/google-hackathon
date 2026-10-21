import {mountEditors} from './input-editors.js';
import {createViewer} from './viewer3d.js?v=geometry-3';
import {mountGeometry} from './geometry-upload.js?v=geometry-3';
import {renderStudy,renderComparison} from './study-view.js';
import {restoreSession,connectSession,forgetSession,isPublicAccess} from './session.js?v=public-3';
const $ = id => document.getElementById(id);
let token = '', connected = false, connectionReady = false, current = null, dirty = false, busy = false, generation = 0, study = null, viewer = null;
let hosted=false, organization='', inventoryCursor='', inventoryNext=null, inventoryStack=[], activeJob=null;
let layoutGeneration=0; const geometryCache=new Map();
const editControls = ['snapshot', 'save', 'reload', 'freeze', 'export-draft'];
const geometryPanel = mountGeometry({
  read: () => JSON.parse($('snapshot').value),
  write: updateDraft,
  api,
  source: async path => (await request(path)).arrayBuffer(),
  action,
  save: saveDraft,
});
function message(text, error = false) { $('message').textContent = text; $('message').className = error ? 'error' : ''; }
function controls() {
  $('local-session').hidden=hosted;
  ['create', 'project-title', 'projects', 'open'].forEach(id => { $(id).disabled = !connected || busy; });
  $('open').disabled = !connected || busy || !$('projects').value;
  $('connection').hidden = hosted || !connectionReady || connected;
  $('disconnect').hidden = hosted || !connected || isPublicAccess();
  $('disconnect').disabled = busy;
  $('token').disabled = busy; document.querySelector('#connection button').disabled = busy;
  $('example').disabled = !connected || busy;
  ['realistic-example','motorout-example'].forEach(id=>$(id).disabled=!connected||busy);
  const readOnly=hosted&&current?.role!=='engineer';
  $('calculate').disabled = readOnly || !current || busy || dirty || !connected || !current.revisions.some(r=>r.draft_version===current.draft_version);
  $('export-study').disabled = !study || busy || !connected;
  $('export-pdf').disabled = !study || busy || !connected;
  ['compare-before','compare-after','compare'].forEach(id=>{$(id).disabled=busy||!connected||!current?.studies?.length;});
  document.querySelectorAll('#input-editors input,#input-editors select,#input-editors button,#input-editors textarea').forEach(input => { input.disabled = readOnly || busy || !current || !connected; });
  editControls.forEach(id => { $(id).disabled = !current || (!connected&&id!=='export-draft') || busy || (readOnly&&['snapshot','save','freeze'].includes(id)) || (id === 'freeze' && dirty); });
  $('next-projects').disabled=busy||!inventoryNext; $('previous-projects').disabled=busy||!inventoryStack.length;
  $('submit-review').disabled=busy||!study||!hosted||!['engineer','reviewer'].includes(current?.role);
  [...$('review-decision').options].forEach(option=>{option.disabled=option.value!=='comment'&&!current?.can_review;});
  if($('review-decision').selectedOptions[0]?.disabled)$('review-decision').value='comment';
  $('snapshot').disabled=!current||busy;$('snapshot').readOnly=readOnly||!connected;
  document.querySelectorAll('.revision-button,.review-export-button').forEach(button => { button.disabled = busy || !connected; });
  geometryPanel.setEnabled(Boolean(current && connected && !busy), dirty);
}
async function request(path, options = {}) {
  const headers = {...options.headers};
  if(hosted){headers.Authorization='Bearer '+token;headers['X-Organization-ID']=organization;if(current?.project_id)headers['X-Project-ID']=current.project_id;}
  const response = await fetch('/api/drone' + path, { ...options, credentials:'same-origin', cache:'no-store', headers, signal: AbortSignal.timeout(60000) });
  if(response.status===401){
    connected=false;token='';geometryCache.clear();
    if(hosted){$('individual-session').hidden=true;message('Your session expired or was revoked. Sign in again. Unsaved inputs remain in this editor.',true);}
    else{sessionStatus();message('Browser access expired or was forgotten. Reconnect to continue. Your open draft is still here.',true);}
    controls();
  }
  if (!response.ok) { let detail;try{detail=(await response.json()).detail;}catch{detail='HTTP '+response.status;}const error=new Error(typeof detail === 'string' ? detail : detail?.message || JSON.stringify(detail));error.detail=detail;throw error; }
  return response;
}
async function api(path, options = {}) { return (await request(path,options)).json(); }
function payload(method, body) { return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }; }
async function action(work) {
  if (busy) return;
  busy = true; controls();
  try { await work(); } catch (error) { message(error.message, true);if(error.detail?.code==='draft_conflict'){$('conflict-message').textContent='The server now has draft version '+error.detail.current_version+'. Your unsaved inputs are still in this editor. Export them, keep editing, or replace them with the latest saved draft.';$('draft-conflict').showModal();} }
  finally { busy = false; controls(); }
}
function preserveEdits() { return !dirty || confirm('Discard the unsaved edits and open the saved design?'); }
async function inventory(selected = '', cursor='') {
  const data = await api('/projects?limit=25'+(cursor?'&after='+encodeURIComponent(cursor):''));
  inventoryCursor=cursor;inventoryNext=data.next_cursor;
  $('projects').replaceChildren(...data.projects.map(project => { const option = document.createElement('option'); option.value = project.project_id; option.textContent = project.title + ' · ' + project.project_id.slice(-8); return option; }));
  if(selected&&!data.projects.some(p=>p.project_id===selected)&&current?.project_id===selected){const option=document.createElement('option');option.value=selected;option.textContent=current.title+' · current project';$('projects').append(option);}
  if (selected) $('projects').value = selected;
  controls();
}
function render(project) {
  current = project; dirty = false;
  $('more-revisions').hidden=!project.revisions_more;$('more-studies').hidden=!project.studies_more;
  $('invite-member').hidden=!hosted||!project.can_invite;
  $('review-workspace').hidden=!hosted;$('job-history').hidden=!hosted;if(hosted)loadJobs().catch(error=>message(error.message,true));
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
  geometryPanel.sync(project,JSON.parse(project.snapshot_json),false);
}
function currentStudy(){return !dirty&&current?.revisions.some(r=>r.draft_version===current.draft_version&&r.revision_sha256===study?.specification.revision_sha256);}
function showStudy(){if(study){renderStudy($('study-report'),study,currentStudy());if(hosted)loadReviews().catch(error=>message(error.message,true));}controls();}
async function geometryBytes(digest){
  if(!geometryCache.has(digest))geometryCache.set(digest,(async()=>{try{return await(await request('/projects/geometry-sources/'+digest)).arrayBuffer();}catch(error){geometryCache.delete(digest);throw new Error('Retained geometry unavailable: '+error.message);}})());
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
  mountEditors($('input-editors'), () => JSON.parse($('snapshot').value), updateDraft,
  async () => { if (dirty) throw new Error('Save the draft first to inspect these edits.');
    return api(`/projects/${current.project_id}/inspection`); }, dataset_json => guardedRequest(()=>api('/projects/performance-sources',payload('POST',{dataset_json}))),{
      conditionMap:(digest,policy)=>guardedRequest(()=>api('/projects/performance-sources/'+digest+'/condition',payload('POST',{policy}))),
      importGeometry:(files,units)=>guardedRequest(()=>{const body=new FormData();body.append('source_units',units);[...files].forEach(file=>body.append('files',file));return api('/import',{method:'POST',body});})
    });
}
function updateDraft(data) {
  $('snapshot').value=JSON.stringify(data,null,2);dirty=true;
  const inspection=$('inspection-report');if(inspection)inspection.textContent='Inputs edited. Save and inspect again.';
  $('save-state').textContent='Unsaved edits. Save before freezing a revision.';
  controls();showStudy();layout();geometryPanel.sync(current,data,true);
}
function sessionStatus() {
  $('session-status').textContent=!connectionReady?'Opening workspace…':isPublicAccess()
    ?'Open workspace. No sign-in required.':connected?'Connected. This browser is remembered for 30 days.'
    :'Connect once to remember this browser for 30 days.';
  if(isPublicAccess()){
    document.querySelector('header span').textContent='Shared local workbench';
    document.querySelector('footer').textContent='Shared workspace. Real aircraft inputs and engineering approval remain pending.';
  }
}
function clearWorkspace() {
  current=null;dirty=false;++generation;geometryCache.clear();++layoutGeneration;
  $('snapshot').value='';$('design-title').textContent='Open a project to begin.';$('save-state').textContent='';
  $('projects').replaceChildren();$('project-title').value='';
  $('input-editors').replaceChildren();$('project-record').textContent='No project open.';$('revision-detail').hidden=true;
  $('revisions').replaceChildren();$('studies').replaceChildren();study=null;$('study-report').replaceChildren();
  $('compare-before').replaceChildren();$('compare-after').replaceChildren();$('comparison-report').replaceChildren();
  if(viewer)viewer.showRotorLayout({rotors:[]},null);$('reset-layout').disabled=true;
  geometryPanel.sync(null,null,false);controls();
}
async function loadWorkspace() {
  sessionStatus();controls();await inventory(current?.project_id);
  message(current?'Your open draft is still here.':'Workspace ready. Select or create a project.');
}
$('connection').addEventListener('submit', event => {
  event.preventDefault(); if (busy) return;
  const accessToken=$('token').value;$('token').value='';
  action(async()=>{
    connected=await connectSession(accessToken);clearWorkspace();await loadWorkspace();
  });
});
$('disconnect').addEventListener('click',()=>{
  if(busy||(dirty&&!confirm('Discard unsaved edits and forget this browser?')))return;
  action(async()=>{await forgetSession();connected=false;clearWorkspace();sessionStatus();message('Browser access forgotten. Enter the workspace access token to reconnect.');});
});
$('create-project').addEventListener('submit', event => { event.preventDefault(); if (!preserveEdits()) return; action(async () => {
  const project = await api('/projects', payload('POST', { title: $('project-title').value }));
  ++generation; render(project); await inventory(project.project_id); $('project-title').value = '';
  message('Project created with explicit unknown inputs.');
}); });
$('open').addEventListener('click', () => { if ($('projects').value && preserveEdits()) action(() => openProject($('projects').value)); });
$('reload').addEventListener('click', () => { if (current && preserveEdits()) action(() => openProject(current.project_id)); });
$('snapshot').addEventListener('input', () => { dirty = true; $('save-state').textContent = 'Unsaved edits. Save before freezing a revision.'; const binding=$('study-report').querySelector('.study-binding');if(binding)binding.textContent='Inputs edited. This retained study belongs to the previous frozen design.';controls();layout(); });
 $('snapshot').addEventListener('change', () => {editors();showStudy();layout();try{geometryPanel.sync(current,JSON.parse($('snapshot').value),true);}catch(error){message('Invalid JSON: '+error.message,true);}});
function saveDraft() { return action(async () => {
  const snapshot = $('snapshot').value;
  const project = await api(`/projects/${current.project_id}/draft`, payload('PUT', { expected_version: current.draft_version, snapshot_json: snapshot }));
  render(project); message('Draft saved. Previous frozen revisions remain available.');
}); }
$('save').addEventListener('click',saveDraft);
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
$('calculate').addEventListener('click',()=>action(async()=>{const revision=current.revisions.find(r=>r.draft_version===current.draft_version);message('Evaluating covered maps, force/moment balance and every required case…');let result=await api(`/projects/${current.project_id}/studies`,payload('POST',{revision_sha256:revision.revision_sha256}));if(result.job_id){const job=await waitForJob(result);result=await api(`/projects/${current.project_id}/studies/${JSON.parse(job.result_json).study_sha256}`);}render(await api('/projects/'+current.project_id));study=result;showStudy();layout();message('Bounded local study retained. Engineering approval and real-aircraft validation remain pending.');}));
async function downloadStudy(kind){
  const path=`/projects/${current.project_id}/studies/${study.study_sha256}/${kind==='pdf'?'pdf':'export'}`;
  let response=await request(path);
  if(response.status===202){await waitForJob(await response.json());response=await request(path);}
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
sessionStatus();
initializeMode();


async function initializeMode(){
  try{
    const response=await fetch('/api/health',{credentials:'same-origin',cache:'no-store'});
    if(!response.ok)throw new Error('HTTP '+response.status);
    const health=await response.json();hosted=health.mode==='hosted';
    if(hosted){
      $('local-session').hidden=true;$('accept-invitation').hidden=false;
      const legacy=document.querySelector('header a[href="/web/results.html"]');if(legacy)legacy.hidden=true;
      $('individual-login').hidden=false;document.querySelector('header span').textContent='Private engineering workspace';
      document.querySelector('footer').textContent='Private project access. Synthetic studies do not establish aircraft validation.';
      connectionReady=true;controls();message('Sign in to open a private project.');return;
    }
    connected=await restoreSession();connectionReady=true;sessionStatus();controls();
    if(connected)await loadWorkspace();else message('Enter the workspace access token to connect.');
  }catch(error){connectionReady=true;controls();message('Workspace connection unavailable: '+error.message,true);}
}
async function sessionOrganizations(){
  const me=await api('/platform/me');$('login-password').value='';$('organization').replaceChildren(...me.organizations.map(org=>{const option=document.createElement('option');option.value=org.org_id;option.textContent=org.name;return option;}));
  organization=$('organization').value;$('individual-session').hidden=false;
}
$('individual-login').addEventListener('submit',event=>{event.preventDefault();action(async()=>{
  const response=await fetch('/api/drone/platform/login',payload('POST',{email:$('login-email').value,password:$('login-password').value}));$('login-password').value='';
  const result=await response.json();if(!response.ok)throw new Error(result.detail||'Sign-in failed');
  token=result.token;connected=true;geometryCache.clear();++generation;await sessionOrganizations();await inventory();message('Signed in. Select a private project.');
});});
$('organization').addEventListener('change',()=>{organization=$('organization').value;});
$('logout').addEventListener('click',()=>action(async()=>{await api('/platform/logout',payload('POST',{}));token='';connected=false;organization='';geometryCache.clear();$('individual-session').hidden=true;message('Signed out. Inputs remain in this page; save or export them before closing.');}));
$('next-projects').addEventListener('click',()=>{if(inventoryNext)action(async()=>{inventoryStack.push(inventoryCursor);await inventory('',inventoryNext);});});
$('previous-projects').addEventListener('click',()=>action(()=>inventory('',inventoryStack.pop()||'')));
['revisions','studies'].forEach(kind=>$('more-'+kind).addEventListener('click',()=>action(async()=>{
  const rawEditor=$('snapshot').value,wasDirty=dirty;const page=await api(`/projects/${current.project_id}/history/${kind}?limit=100`);let cursor=page.next_cursor;
  const retained=new Map(current[kind].map(r=>[kind==='revisions'?r.revision_sha256:r.study_sha256,r]));page[kind].forEach(r=>retained.set(kind==='revisions'?r.revision_sha256:r.study_sha256,r));
  // Load one bounded page at a time and keep its immutable continuation locally.
  if(current[kind+'_cursor']){const more=await api(`/projects/${current.project_id}/history/${kind}?limit=100&after=${encodeURIComponent(current[kind+'_cursor'])}`);more[kind].forEach(r=>retained.set(kind==='revisions'?r.revision_sha256:r.study_sha256,r));cursor=more.next_cursor;}
  const savedStudy=study;current[kind]=[...retained.values()];current[kind+'_cursor']=cursor;current[kind+'_more']=!!cursor;render(current);if(wasDirty){$('snapshot').value=rawEditor;dirty=true;$('save-state').textContent='Unsaved edits. Save before freezing a revision.';editors();}study=savedStudy;showStudy();
})));
async function waitForJob(submitted){
  const pid=current.project_id;activeJob={...submitted,project_id:pid};$('cancel-job').hidden=current?.role!=='engineer';$('retry-job').hidden=true;
  try{for(let poll=0;poll<600;poll++){
    const job=await api(`/projects/${pid}/jobs/${submitted.job_id}`);activeJob={...job,project_id:pid};const attempt=job.attempts.at(-1);
    $('job-progress').textContent='Job '+job.state+(attempt?' · '+Math.round(attempt.progress*100)+'% · '+attempt.detail:'');
    if(job.state==='succeeded'){activeJob=null;return job;}
    if(['failed','cancelled'].includes(job.state)){$('retry-job').hidden=current?.role!=='engineer';throw new Error(job.reason||'Job '+job.state);}
    await new Promise(resolve=>setTimeout(resolve,1000));
  }throw new Error('Job is still running. Reopen its project to check progress.');}
  finally{$('cancel-job').hidden=true;}
}
$('cancel-job').addEventListener('click',async()=>{if(!activeJob)return;try{await api(`/projects/${activeJob.project_id}/jobs/${activeJob.job_id}/cancel`,payload('POST',{}));}catch(error){message(error.message,true);}});
$('retry-job').addEventListener('click',()=>action(async()=>{if(activeJob){const job=await api(`/projects/${activeJob.project_id}/jobs/${activeJob.job_id}/retry`,payload('POST',{}));await waitForJob(job);message('Retry completed. Open the accepted study from history.');render(await api('/projects/'+current.project_id));}}));
async function loadReviews(){
  if(!current||!hosted)return;const pid=current.project_id;const result=await api('/platform/reviews/'+pid);if(pid!==current?.project_id)return;
  $('reviews').replaceChildren(...result.reviews.map(record=>{
    const li=document.createElement('li'),button=document.createElement('button');
    li.textContent=record.decision+' · '+record.author_email+' · '+record.comment+' ';
    button.type='button';button.className='review-export-button';button.textContent='Download review JSON';
    button.addEventListener('click',()=>action(async()=>{
      const path='/platform/reviews/'+pid+'/'+record.review_id+'/export';
      const response=await request(path);
      if(!response.ok){await api(path);throw new Error('Review download failed.');}
      const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');
      link.href=url;link.download='workflow-'+record.review_id+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
      message('Authenticated review download requested, bound to the exact study result.');
    }));li.append(button);return li;
  }));
}
$('submit-review').addEventListener('click',()=>action(async()=>{if(!study)return;await api('/platform/reviews/'+current.project_id,payload('POST',{study_sha256:study.study_sha256,decision:$('review-decision').value,comment:$('review-comment').value}));$('review-comment').value='';await loadReviews();message('Authenticated review retained against this exact study result.');}));

async function loadJobs(){
  const pid=current?.project_id;if(!pid||!hosted)return;const page=await api(`/projects/${pid}/jobs`);if(pid!==current?.project_id)return;
  $('jobs').replaceChildren(...page.jobs.map(record=>{const li=document.createElement('li'),button=document.createElement('button');button.type='button';button.textContent=record.kind+' · '+record.state+' · attempt '+record.attempt_count;
    button.addEventListener('click',()=>action(async()=>{const job=await waitForJob(record);if(record.kind==='study'){const receipt=JSON.parse(job.result_json);study=await api(`/projects/${pid}/studies/${receipt.study_sha256}`);showStudy();}message('Accepted job evidence reopened.');}));li.append(button);return li;}));
}

$('invite-member').addEventListener('submit',event=>{event.preventDefault();action(async()=>{const result=await api('/platform/projects/'+current.project_id+'/invitations',payload('POST',{email:$('invite-email').value,role:$('invite-role').value}));$('created-invitation').value=result.invitation_token;$('invitation-result').hidden=false;message('One-use invitation created for this email. It expires in 24 hours. Share it privately.');});});
$('accept-invitation').addEventListener('submit',event=>{event.preventDefault();action(async()=>{const result=await api('/platform/invitations/accept',payload('POST',{invitation_token:$('invitation-code').value}));$('invitation-code').value='';await sessionOrganizations();if(preserveEdits())await openProject(result.project_id);await inventory(result.project_id);message('Invitation accepted for this project.');});});
