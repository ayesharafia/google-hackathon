import {mountCantilever} from './cantilever-screening.js?v=beam-1';
import {mountThermal} from './thermal-screening.js?v=thermal-1';
import {mountFixedWing} from './fixed-wing-screening.js?v=wing-1';
import {mountJourney} from './workbench-journey.js?v=journey-1';
import {mountEvaluationPanel} from './reference-evaluation.js?v=reference-1';
import {mountRemoteConsent} from './remote-consent.js?v=remote-1';
import {mountGroqChat} from './groq-chat.js?v=groq-2';
import {createReviewPackDownloader} from './review-pack.js?v=pack-1';
import {mountJobActivity} from './job-activity.js?v=jobs-1';
import {mountAgentWorkspace} from './agent-workspace.js?v=agent-1';
import {energyCaseMatches} from './mission-energy.js?v=energy-1';
import {mountEditors} from './input-editors.js?v=atmosphere-preview-1';
import {createViewer} from './viewer3d.js?v=geometry-3';
import {mountGeometry} from './geometry-upload.js?v=geometry-3';
import {renderStudy,renderComparison} from './study-view.js?v=trim-1';
import {restoreSession,connectSession,forgetSession,isPublicAccess} from './session.js?v=public-3';
import {renderReadiness} from './engineering-readiness.js?v=readiness-1';
import {createComparisonController} from './design-comparison.js?v=comparison-1';
const $ = id => document.getElementById(id);
let providerSigninEnabled = false;
let token = '', connected = false, connectionReady = false, current = null, dirty = false, busy = false, generation = 0, study = null, viewer = null;
let hosted=false, organization='', inventoryCursor='', inventoryNext=null, inventoryStack=[], activeJob=null;
let layoutGeneration=0, viewSnapshot=null, viewRevision='', viewMode='draft', selectedCase=''; const geometryCache=new Map();
let inspectionSerial=0;
let trimSelection=null;
const context = () => ({generation, token, organization, project:current?.project_id});
const isContext = c => c.generation===generation && c.token===token && c.organization===organization && c.project===current?.project_id;
const cantilever=mountCantilever($('cantilever-screening'),{api,readContext:context,isContext});
const thermal=mountThermal($('thermal-screening'),{api,readContext:context,isContext});
const fixedWing=mountFixedWing($('fixed-wing-screening'),{api,readContext:context,isContext});
const journey=mountJourney($('workbench-journey'));
const referenceEvaluation=mountEvaluationPanel($('reference-evaluation'),{api,readContext:context,isContext});
const comparisons = createComparisonController({
  readContext: context, isContext,
  readSelection: () => ({before:$('compare-before').value, after:$('compare-after').value}),
  fetchReport: (c, pair) => api(`/projects/${c.project}/comparisons`, payload('POST', pair)),
  render: report => renderComparison($('comparison-report'), report),
  setState: (state, text) => {
    const out=$('comparison-report'); out.dataset.state=state;out.setAttribute('aria-busy',String(state==='pending'));
    if(state!=='current')out.replaceChildren();
    $('comparison-status').textContent=text;
  },
});
const reviewPack = createReviewPackDownloader({
  readContext: context, isContext, readStudy:()=>study,
  fetchPack:binding=>request(`/projects/${binding.project}/studies/${binding.study}/review-pack`),
  waitJob:(job,current)=>waitForJob(job,current),
  save:(blob,name)=>{const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);},
  setState:(state,text)=>{$('review-pack-status').textContent=text;$('review-pack-status').dataset.state=state;$('export-pack').setAttribute('aria-busy',String(state==='pending'));},
});
const jobActivity=mountJobActivity({
  list:$('jobs'),detail:$('job-detail'),refresh:$('refresh-jobs'),more:$('more-jobs'),
  request:api,readContext:context,isContext,
  canRead:()=>Boolean(hosted&&connected&&current),
  canWrite:()=>Boolean(hosted&&connected&&current?.role==='engineer'&&!busy),
  canOpen:()=>Boolean(connected&&current&&!busy),
  openStudy:digest=>action(()=>selectStudy(digest)),
});
function updateContext(){
  journey.sync({connected,projectTitle:current?.title??null,draftVersion:current?.draft_version??null,dirty,viewMode,revision:viewRevision||null,study:study?.study_sha256??null});
  $('display-context').textContent=!current?'No project selected.':viewMode==='draft'?'Viewer: '+(dirty?'unsaved':'saved')+' draft version '+current.draft_version+'. Editor changes affect this draft only.':'Viewer: frozen revision '+viewRevision+' · '+(viewMode==='study'?'selected study '+study?.study_sha256:'selected revision')+'. Draft edits do not change this view.';
  $('show-draft-layout').disabled=!current||busy||viewMode==='draft';
  $('view-case').disabled=!study||viewMode!=='study'||busy;
  document.querySelectorAll('#studies button').forEach(button=>button.setAttribute('aria-current',String(button.dataset.study===study?.study_sha256)));
  document.querySelectorAll('#revisions button').forEach(button=>button.setAttribute('aria-current',String(viewMode!=='draft'&&button.dataset.revision===viewRevision)));
}
function clearWorkspace(){
  jobActivity.reset();$('job-activity').hidden=true;
  ++generation;++layoutGeneration;geometryCache.clear();current=null;study=null;dirty=false;viewSnapshot=null;viewRevision='';viewMode='draft';selectedCase='';activeJob=null;inventoryCursor='';inventoryNext=null;inventoryStack=[];
  $('snapshot').value='';$('input-editors').replaceChildren();$('study-report').replaceChildren();$('comparison-report').replaceChildren();$('revision-detail').hidden=true;
  ['revisions','studies','jobs','reviews','compare-before','compare-after','view-case','projects','study-summary','guided-readiness','layout-inputs'].forEach(id=>$(id).replaceChildren());
  $('design-title').textContent='Open a project to begin.';$('project-record').textContent='No project open.';$('save-state').textContent='Missing physical inputs stay unknown.';
  ['review-workspace','job-history','invite-member','invitation-result'].forEach(id=>$(id).hidden=true);
  $('more-revisions').hidden=true;$('more-studies').hidden=true;$('editor-navigation').replaceChildren(new Option('Choose an input group',''));
  $('created-invitation').value='';$('job-progress').textContent='';$('cancel-job').hidden=true;$('retry-job').hidden=true;
  resetReadiness();reviewPack.invalidate();comparisons.invalidate('Open a project with retained studies to compare.');
  if(viewer)viewer.showRotorLayout({rotors:[]},null);$('layout-note').textContent='No design selected.';$('reset-layout').disabled=true;$('project-title').value='';geometryPanel.sync(null,null,false);updateContext();controls();
}
async function selectStudy(record){
  reviewPack.invalidate('Study selection changed. Download a new pack for the selected record.');
  const c=context();const retained=typeof record==='string'?await api(`/projects/${c.project}/studies/${record}`):record;
  const revision=await api(`/projects/${c.project}/revisions/${retained.specification.revision_sha256}`);
  if(!isContext(c))return;
  const frozen=JSON.parse(revision.snapshot_json);study=retained;viewSnapshot=frozen;viewRevision=retained.specification.revision_sha256;viewMode='study';selectedCase=retained.limiting_case_id||retained.headline_candidate_checks?.[0]?.case_id||'';
  $('view-case').replaceChildren(...(retained.cases||[]).map(row=>{const option=document.createElement('option');option.value=row.case_id;option.textContent=row.case_id+' · '+row.outcome;return option;}));$('view-case').value=selectedCase;showStudy();layout();await loadSummary();
}
async function loadSummary(){
  const c=context(),digest=study?.study_sha256,out=$('study-summary');out.replaceChildren();
  if(!digest)return;out.textContent='Loading retained study summary…';
  try{const summary=await api(`/projects/${c.project}/studies/${digest}/summary`);if(!isContext(c)||study?.study_sha256!==digest)return;
    if(summary.schema_version!=='study_summary_v1'||summary.study_sha256!==digest||summary.revision_sha256!==study.specification.revision_sha256||summary.project_id!==c.project||summary.snapshot_sha256!==study.specification.snapshot_sha256)throw new Error('Summary identity differs from selected study.');
    out.replaceChildren();const title=document.createElement('h4');title.textContent='Retained study summary';out.append(title);
    for(const [key,name] of [['nominal','Nominal model bound'],['scenario','Deterministic scenario bound'],['allowable','Checked allowable payload']]){const bound=summary.bounds[key],line=document.createElement('p');line.textContent=(bound.label||name)+': '+(bound.payload_kg==null?'Unavailable':bound.payload_kg+' kg')+' · '+bound.status+'. '+bound.qualification;out.append(line);if(key==='allowable'){const note=document.createElement('p');note.textContent='Declared external cap: '+(bound.declared_cap_kg==null?'Unavailable':bound.declared_cap_kg+' kg')+'. Approval declarations are not authenticated engineering acceptance.';out.append(note);}}
  }catch(error){if(isContext(c)&&study?.study_sha256===digest)out.textContent='Retained summary unavailable: '+error.message+'. Detailed retained evidence and exports remain available.';}
}
const editControls = ['snapshot', 'save', 'reload', 'freeze', 'export-draft'];
const geometryPanel = mountGeometry({
  read: () => JSON.parse($('snapshot').value),
  write: updateDraft,
  api,
  source: async path => (await request(path)).arrayBuffer(),
  action,
  save: saveDraft,
});
const agentPanel = mountAgentWorkspace($('agent-workspace'),{
  api,exclusive:action,
  context:()=>({generation,connected,projectId:current?.project_id,version:current?.draft_version,
    projectTitle:current?.title,
    dirty,busy,publicAccess:isPublicAccess(),canWrite:!hosted||current?.role==='engineer',
    massNames:current?JSON.parse(current.snapshot_json).masses.items.map(item=>item.name):[]}),
  saved:async()=>{const c=context(),project=await api('/projects/'+current.project_id);if(isContext(c)&&!dirty)render(project);},
});
const groqChat=mountGroqChat($('groq-chat'),{settingsRoot:$('ai-settings'),api,exclusive:action,context:()=>({generation,connected,projectId:current?.project_id,dirty,publicAccess:isPublicAccess()}),saved:async()=>{const c=context(),project=await api('/projects/'+current.project_id);if(isContext(c)&&!dirty)render(project);}});
const remoteConsent=mountRemoteConsent($('remote-consent'),{api,exclusive:action,context:()=>({generation,connected,projectId:current?.project_id,publicAccess:isPublicAccess(),canWrite:!hosted||current?.role==='engineer'})});
function message(text, error = false) { $('message').textContent = text; $('message').className = error ? 'error' : ''; }
function controls() {
  fixedWing.syncContext();
  thermal.syncContext();
  cantilever.syncContext();
  referenceEvaluation.syncContext();
  if(!connected)referenceEvaluation.invalidate('Sign in or connect the workspace, then refresh the model catalog.');
  updateContext();
  agentPanel.sync();
  groqChat.sync();
  remoteConsent.sync();
  $('organization-signin').hidden = !hosted || !providerSigninEnabled || connected;
  jobActivity.updateAccess();
  ['organization','logout'].forEach(id=>$(id).disabled=busy);
  document.querySelectorAll('#individual-login input,#individual-login button,#accept-invitation input,#accept-invitation button').forEach(el=>el.disabled=busy);
  $('local-session').hidden=hosted;
  ['create', 'project-title', 'projects', 'open'].forEach(id => { $(id).disabled = !connected || busy; });
  $('open').disabled = !connected || busy || !$('projects').value;
  $('inspect-saved').disabled = !connected || busy || !current || dirty;
  document.querySelectorAll('#guided-readiness button').forEach(button=>{button.disabled=!connected||busy||!current;});
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
  $('export-pack').disabled = !study || busy || !connected;
  $('review-pack-binding').textContent=study?'Study '+study.study_sha256+' · frozen revision '+study.specification.revision_sha256+'. Unsaved draft edits are excluded.':'No retained study selected.';
  document.querySelectorAll('[data-energy-case]').forEach(button=>{button.disabled=busy||!connected||!energyCaseMatches(study,{study_sha256:button.dataset.energyStudy,revision_sha256:button.dataset.energyRevision,project_id:current?.project_id},button.dataset.energyCase);});
  document.querySelectorAll('.trim-evidence select').forEach(select=>{select.disabled=busy||!connected||!study||!select.closest('.trim-evidence').querySelector('[data-trim-select=case]').value;});
  document.querySelectorAll('[data-trim-case]').forEach(button=>{button.disabled=busy||!connected||!energyCaseMatches(study,{study_sha256:button.dataset.trimStudy,revision_sha256:button.dataset.trimRevision,project_id:current?.project_id},button.dataset.trimCase);});
  ['compare-before','compare-after','compare'].forEach(id=>{$(id).disabled=busy||!connected||!current?.studies?.length;});
  document.querySelectorAll('#input-editors input,#input-editors select,#input-editors button,#input-editors textarea').forEach(input => { input.disabled = readOnly || busy || !current || !connected; });
  document.querySelectorAll('[data-library-read=true]').forEach(input=>{input.disabled=!connected||busy||!current;});
  document.querySelectorAll('[data-source-sample]').forEach(mark=>{const disabled=!connected||busy||!current;mark.setAttribute('aria-disabled',String(disabled));mark.setAttribute('tabindex',disabled||mark.dataset.selected!=='true'?'-1':'0');});
  document.querySelectorAll('[data-local-disabled=true]').forEach(input=>{input.disabled=true;});
  document.querySelectorAll('[data-source-compatible=false]').forEach(input=>{input.disabled=true;});
  document.querySelectorAll('[data-source-apply]').forEach(button=>{if(!button.closest('.source-binding')?.querySelector('[data-source-compatible=true]'))button.disabled=true;});
  editControls.forEach(id => { $(id).disabled = !current || (!connected&&id!=='export-draft') || busy || (readOnly&&['snapshot','save','freeze'].includes(id)) || (id === 'freeze' && dirty); });
  $('next-projects').disabled=busy||!inventoryNext; $('previous-projects').disabled=busy||!inventoryStack.length;
  $('submit-review').disabled=busy||!study||!hosted||!['engineer','reviewer'].includes(current?.role);
  [...$('review-decision').options].forEach(option=>{option.disabled=option.value!=='comment'&&!current?.can_review;});
  if($('review-decision').selectedOptions[0]?.disabled)$('review-decision').value='comment';
  $('snapshot').disabled=!current||busy;$('snapshot').readOnly=readOnly||!connected;
  document.querySelectorAll('.revision-button,.review-export-button').forEach(button => { button.disabled = busy || !connected; });
  geometryPanel.setEnabled(Boolean(current && connected && !busy && !readOnly), dirty);
}
async function request(path, options = {}) {
  const requested=context(),headers = {...options.headers};
  if(hosted){if(token)headers.Authorization='Bearer '+token;if(organization)headers['X-Organization-ID']=organization;if(current?.project_id)headers['X-Project-ID']=current.project_id;}
  const response = await fetch('/api/drone' + path, { ...options, credentials:'same-origin', cache:'no-store', headers, signal: AbortSignal.timeout(60000) });
  if(!isContext(requested))throw new Error('Workspace context changed; the previous response was ignored.');
  if(response.status===401){
    connected=false;token='';++generation;++layoutGeneration;reviewPack.invalidate('Reconnect and select a retained study.');comparisons.invalidate('Connection changed. Reconnect and compare again.');geometryCache.clear();$('invitation-result').hidden=true;$('created-invitation').value='';
    if(hosted){$('individual-session').hidden=true;message('Your session expired or was revoked. Sign in again. Unsaved inputs remain in this editor.',true);}
    else{sessionStatus();message('Browser access expired or was forgotten. Reconnect to continue. Your open draft is still here.',true);}
    controls();
  }
  if (!response.ok) { let detail;try{detail=(await response.json()).detail;}catch{detail='HTTP '+response.status;}const error=new Error(typeof detail === 'string' ? detail : detail?.message || JSON.stringify(detail));error.detail=detail;throw error; }
  return response;
}
async function api(path, options = {}) { const c=context(),data=await(await request(path,options)).json();if(!isContext(c))throw new Error('Workspace context changed; the previous response was ignored.');return data; }
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
  if(current?.project_id!==project.project_id){jobActivity.reset();geometryCache.clear();++layoutGeneration;$('reviews').replaceChildren();$('jobs').replaceChildren();$('created-invitation').value='';$('invitation-result').hidden=true;}
  viewSnapshot=null;viewRevision='';viewMode='draft';selectedCase='';$('view-case').replaceChildren();
  current = project; dirty = false;
  $('more-revisions').hidden=!project.revisions_more;$('more-studies').hidden=!project.studies_more;
  $('invite-member').hidden=!hosted||!project.can_invite;
  $('review-workspace').hidden=!hosted;$('job-history').hidden=!hosted;$('job-activity').hidden=!hosted;if(hosted)loadJobs().catch(error=>message(error.message,true));
  study=null;reviewPack.invalidate();$('study-report').replaceChildren();$('study-summary').replaceChildren();resetReadiness();
  $('snapshot').value = JSON.stringify(JSON.parse(project.snapshot_json), null, 2);
  $('design-title').textContent = project.title;
  $('save-state').textContent = 'Saved draft version ' + project.draft_version + '. Edits create a new version; retained revisions stay unchanged.';
  $('project-record').textContent = project.project_id + ' · version ' + project.draft_version;
  $('revision-detail').hidden = true;
  editors();
  const rows = project.revisions.map(record => {
    const li = document.createElement('li'), button = document.createElement('button');
    button.type = 'button'; button.className = 'revision-button';button.dataset.revision=record.revision_sha256;
    button.textContent = 'Draft ' + record.draft_version + ' · ' + record.revision_sha256.slice(0, 12);
    button.addEventListener('click', () => action(async () => {
      const pid = current.project_id, request = generation;
      const revision = await api(`/projects/${pid}/revisions/${record.revision_sha256}`);
      if (request !== generation || pid !== current?.project_id) return;
      viewSnapshot=JSON.parse(revision.snapshot_json);viewRevision=record.revision_sha256;viewMode='revision';layout();updateContext();
      $('revision-summary').textContent = 'Immutable local revision ' + record.revision_sha256 + '. Engineering approval pending.';
      $('revision-json').textContent = JSON.stringify(revision, null, 2);
      $('revision-detail').hidden = false;
    }));
    li.append(button); return li;
  });
  if (!rows.length) { const li = document.createElement('li'); li.textContent = 'No frozen revision yet.'; rows.push(li); }
  $('revisions').replaceChildren(...rows); controls();
  $('studies').replaceChildren(...(project.studies||[]).map(record=>{
    const li=document.createElement('li'),button=document.createElement('button');button.type='button';button.className='revision-button';button.dataset.study=record.study_sha256;button.textContent='Study '+record.study_sha256.slice(0,12);
    button.addEventListener('click',()=>action(()=>selectStudy(record.study_sha256)));li.append(button);return li;
  }));
  ['compare-before','compare-after'].forEach(id=>$(id).replaceChildren(...(project.studies||[]).map(record=>{
    const option=document.createElement('option');option.value=record.study_sha256;option.textContent=record.created_utc+' · '+record.study_sha256.slice(0,12);return option;
  })));
  if(project.studies?.length>1)$('compare-before').selectedIndex=1;
  comparisons.invalidate(project.studies?.length?'Choose retained studies, then compare.':'No retained studies yet. Freeze and evaluate a design first.');layout();controls();
  geometryPanel.sync(project,JSON.parse(project.snapshot_json),false);
}
function currentStudy(){return !dirty&&current?.revisions.some(r=>r.draft_version===current.draft_version&&r.revision_sha256===study?.specification.revision_sha256);}
function showStudy(){
  if(study){
    const requested=context();
    renderStudy($('study-report'),study,currentStudy(),{trimSelection,
      isInteractive:()=>connected&&!busy&&isContext(requested),
      onTrimSelection:selection=>{if(isContext(requested)&&selection.study_sha256===study?.study_sha256)trimSelection=selection;},
      onViewCase:async(caseId,binding)=>{
      if(busy||!connected||!isContext(requested)||!energyCaseMatches(study,binding,caseId))return;
      await action(async()=>{
        if(viewMode!=='study'||viewRevision!==binding.revision_sha256)await selectStudy(binding.study_sha256);
        if(!connected||!isContext(requested)||!energyCaseMatches(study,binding,caseId))return;
        selectedCase=caseId;$('view-case').value=caseId;layout();
      });
      if(connected&&isContext(requested)&&energyCaseMatches(study,binding,caseId)&&viewMode==='study'&&selectedCase===caseId)$('view-case').focus();
    }});
    if(hosted)loadReviews().catch(error=>message(error.message,true));
  }
  controls();
}
async function geometryBytes(digest){
  const requested=context();
  if(!geometryCache.has(digest))geometryCache.set(digest,(async()=>{
    const bytes=await(await request('/projects/geometry-sources/'+digest)).arrayBuffer();
    if(!isContext(requested))throw new Error('Workspace changed while loading geometry.');
    return bytes;
  })().catch(error=>{if(isContext(requested))geometryCache.delete(digest);throw error;}));
  return geometryCache.get(digest);
}
async function layout(){const request=++layoutGeneration;let inputsShown=false;updateContext();try{const data=viewMode==='draft'?JSON.parse($('snapshot').value):viewSnapshot,components=data?.assembly?.components||[];
  showLayoutInputs(data);inputsShown=true;
  if(!data.rotors?.length&&!components.length){if(viewer)viewer.showRotorLayout({rotors:[]},null);$('layout-note').textContent='No declared rotor layout or airframe. Add inputs or create a labelled example.';$('reset-layout').disabled=true;return;}
  if(components.length>64)throw new Error('Assembly preview supports at most 64 declared components.');
  const geometries=await Promise.all(components.map(async component=>({component,buffer:await geometryBytes(component.source_sha256)})));
  if(request!==layoutGeneration)return;
  if(geometries.reduce((sum,g)=>sum+g.buffer.byteLength,0)>50000000)throw new Error('Assembly preview exceeds 50 MB.');
  const bound=viewMode==='study'?study?.headline_candidate_checks?.find(c=>c.case_id===selectedCase):null;
  const record=viewMode==='study'?study?.cases?.find(c=>c.case_id===selectedCase):null;
  const highlighted=(data.rotors||[]).filter(r=>record?.active_constraints?.some(c=>c.startsWith(r.rotor_id+'_'))).map(r=>r.rotor_id),failed=bound?.failed_rotor_ids||[];
  viewer??=createViewer($('layout-view'));const count=viewer.showRotorLayout(data,bound?.candidate?.cg_body_m,{geometries,highlightedRotors:highlighted,failedRotors:failed});
  $('layout-note').textContent=count+' declared rotor disks; '+geometries.length+' retained airframe components. '+(record?'Selected case: '+record.case_id+(record.case_id===study?.limiting_case_id?' (governing)':'')+'. ':'')+(highlighted.length?'Amber active rotor limits: '+highlighted.filter(r=>!failed.includes(r)).join(', ')+'. ':'')+(failed.length?'Red failed rotors: '+failed.join(', ')+'. ':'')+'Positions use the declared body frame. Geometry does not establish aircraft performance.';$('reset-layout').disabled=!(count||geometries.length);
}catch(error){if(request!==layoutGeneration)return;if(!inputsShown)$('layout-inputs').replaceChildren();if(viewer)viewer.showRotorLayout({rotors:[]},null);const selected=viewMode==='study'?study?.cases?.find(c=>c.case_id===selectedCase):null;$('layout-note').textContent=(selected?'Selected case: '+selected.case_id+'. ':'')+'Layout unavailable: '+error.message+(inputsShown?' Declared numeric inputs and source references remain available below.':'');$('reset-layout').disabled=true;}}
function showLayoutInputs(data){
  const out=$('layout-inputs');out.replaceChildren();
  for(const rotor of data.rotors||[]){const line=document.createElement('p');line.dataset.rotorId=rotor.rotor_id;line.textContent='Rotor '+rotor.rotor_id+' · centre ['+(rotor.center_body_m||[]).join(', ')+'] m · axis ['+(rotor.axis_body||[]).join(', ')+'] · map '+(rotor.map_ref||'Unknown');out.append(line);}
  for(const component of data.assembly?.components||[]){const line=document.createElement('p');line.textContent='Component '+component.component_id+' · source '+component.source_sha256+' · source units '+(component.source_units||'Unknown')+' · translation ['+(component.transform?.translation_m||[]).join(', ')+'] m';out.append(line);}
}
async function guardedRequest(work,staleMessage='Inputs changed during import. Reopen the import step and review the current draft before binding.'){const request=generation,pid=current?.project_id,raw=$('snapshot').value;const result=await work();if(request!==generation||pid!==current?.project_id||raw!==$('snapshot').value)throw new Error(staleMessage);return result;}
async function openProject(pid) {
  comparisons.invalidate('Opening a project. Compare its retained studies again.');
  geometryCache.clear();++layoutGeneration;
  const request = ++generation;
  const project = await api('/projects/' + pid);
  if (request !== generation) return;
  render(project); message('Saved design reopened. Physical readiness has not been inferred.');
}
function editors() {
  mountEditors($('input-editors'), () => JSON.parse($('snapshot').value), updateDraft,
  inspectSavedInputs, dataset_json => guardedRequest(()=>api('/projects/performance-sources',payload('POST',{dataset_json}))),{
      evaluateAtmosphere:inputs=>guardedRequest(()=>api('/atmosphere/evaluate',payload('POST',inputs)),'Draft changed while evaluating atmosphere. Preview again before applying.'),
      conditionMap:(digest,policy)=>guardedRequest(()=>api('/projects/performance-sources/'+digest+'/condition',payload('POST',{policy}))),
      importGeometry:(files,units)=>guardedRequest(()=>{const body=new FormData();body.append('source_units',units);[...files].forEach(file=>body.append('files',file));return api('/import',{method:'POST',body});}),
      sourceRequest:(path,init)=>guardedRequest(()=>api('/projects/'+current.project_id+'/source-library'+path,init)),
      sourceDownload:async(id,filename)=>{const c=context();const response=await request('/projects/'+current.project_id+'/source-library/'+id+'/original');const blob=await response.blob();if(!isContext(c))throw new Error('Project changed during download.');const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);},
      onMapBound:count=>message('Retained source applied to '+count+' selected rotor'+(count===1?'':'s')+'. Save the draft, then inspect its inputs again.')
    });
  refreshNavigation();
}
function refreshNavigation(){
  const groups=[...$('input-editors').children].filter(el=>el.tagName==='DETAILS'||el.tagName==='SECTION');
  $('editor-navigation').replaceChildren(new Option('Choose an input group',''),...groups.map((el,index)=>{el.id='editor-group-'+index;return new Option(el.querySelector('summary,h3')?.textContent||'Inputs',el.id);}));
}
new MutationObserver(refreshNavigation).observe($('input-editors'),{childList:true});
function navigateInputs(id){const target=document.getElementById(id);if(target){target.open=true;target.scrollIntoView({block:'start',behavior:'auto'});target.querySelector('summary,input,select,textarea,button')?.focus();}}
function navigateReadiness(group){
  const target=document.querySelector('#input-editors [data-readiness-group="'+group+'"]');
  navigateInputs(target?.id||'design-json');
}
function resetReadiness(stale=false){
  ++inspectionSerial;$('guided-readiness').setAttribute('aria-busy','false');
  $('readiness-status').textContent=!current?'Open a project to inspect its saved inputs.':stale
    ?'Checks out of date. Save your edits, then inspect the saved draft again.'
    :'Saved draft '+current.draft_version+' has not been inspected here.';
  $('guided-readiness').replaceChildren();
  if(current)renderReadiness($('guided-readiness'),null,navigateReadiness);
}
async function inspectSavedInputs(){
  if(!current||dirty)throw new Error('Save the draft first to inspect these edits.');
  const c=context(),version=current.draft_version,raw=$('snapshot').value,serial=++inspectionSerial;
  $('readiness-status').textContent='Inspecting saved draft '+version+'…';
  $('guided-readiness').setAttribute('aria-busy','true');
  try{
    const report=await api(`/projects/${current.project_id}/inspection`);
    if(serial!==inspectionSerial||!isContext(c)||dirty||current.draft_version!==version||$('snapshot').value!==raw)
      throw new Error('Inputs changed during inspection. Save and inspect again.');
    if(report.draft_version!==version)throw new Error('The saved draft changed on the server. Reload the saved draft before inspecting again.');
    renderReadiness($('guided-readiness'),report,navigateReadiness);
    $('readiness-status').textContent='Inspected saved draft '+version+'. These checks do not apply to frozen revisions or retained studies.';
    controls();return report;
  }catch(error){
    if(serial===inspectionSerial&&isContext(c)){
      renderReadiness($('guided-readiness'),null,navigateReadiness);
      $('readiness-status').textContent='Inspection unavailable. '+error.message;
    }
    throw error;
  }finally{if(serial===inspectionSerial)$('guided-readiness').setAttribute('aria-busy','false');}
}
function updateDraft(data) {
  $('snapshot').value=JSON.stringify(data,null,2);dirty=true;resetReadiness(true);
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

async function loadWorkspace() {
  sessionStatus();controls();await inventory(current?.project_id);
  message(current?'Your open draft is still here.':'Workspace ready. Select or create a project.');
}
$('connection').addEventListener('submit', event => {
  event.preventDefault(); if (busy) return;
  if(!preserveEdits())return;
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
$('snapshot').addEventListener('input', () => { dirty = true; resetReadiness(true);$('save-state').textContent = 'Unsaved edits. Save before freezing a revision.'; const binding=$('study-report').querySelector('.study-binding');if(binding)binding.textContent='Inputs edited. This retained study belongs to the previous frozen design.';controls();layout(); });
 $('snapshot').addEventListener('change', () => {editors();showStudy();layout();try{geometryPanel.sync(current,JSON.parse($('snapshot').value),true);}catch(error){message('Invalid JSON: '+error.message,true);}});
function saveDraft() { return action(async () => {
  const snapshot = $('snapshot').value;
  const project = await api(`/projects/${current.project_id}/draft`, payload('PUT', { expected_version: current.draft_version, snapshot_json: snapshot }));
  render(project); message('Draft saved. Previous frozen revisions remain available.');
}); }
$('save').addEventListener('click',saveDraft);
$('inspect-saved').addEventListener('click',()=>action(inspectSavedInputs));
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
$('calculate').addEventListener('click',()=>action(async()=>{const revision=current.revisions.find(r=>r.draft_version===current.draft_version);message('Evaluating covered maps, force/moment balance and every required case…');let result=await api(`/projects/${current.project_id}/studies`,payload('POST',{revision_sha256:revision.revision_sha256}));if(result.job_id){const job=await waitForJob(result);result=await api(`/projects/${current.project_id}/studies/${JSON.parse(job.result_json).study_sha256}`);}render(await api('/projects/'+current.project_id));await selectStudy(result);message('Bounded local study retained. Engineering approval and real-aircraft validation remain pending.');}));
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
$('export-pack').addEventListener('click',()=>action(()=>reviewPack.download()));
['compare-before','compare-after'].forEach(id=>$(id).addEventListener('change',()=>comparisons.invalidate()));
$('compare').addEventListener('click',()=>action(()=>comparisons.compare()));
$('show-draft-layout').addEventListener('click',()=>{viewMode='draft';viewSnapshot=null;viewRevision='';layout();controls();});
$('view-case').addEventListener('change',()=>{selectedCase=$('view-case').value;layout();});
$('editor-navigation').addEventListener('change',()=>{navigateInputs($('editor-navigation').value);});
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
      const signInResponse=await fetch('/api/oidc/status',{credentials:'same-origin',cache:'no-store'});
      const signIn=signInResponse.ok?await signInResponse.json():{enabled:false,connected:false};
      providerSigninEnabled=signIn.enabled;connectionReady=true;
      if(signIn.connected){connected=true;++generation;await sessionOrganizations();await inventory();message('Signed in. Select a private project.');}
      else message(new URLSearchParams(location.search).get('signin')==='failed'?'Organization sign-in failed. Try again or contact your administrator.':'Sign in to open a private project.');
      controls();return;
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
  if(!preserveEdits())return;clearWorkspace();token='';connected=false;organization='';
  const response=await fetch('/api/drone/platform/login',payload('POST',{email:$('login-email').value,password:$('login-password').value}));$('login-password').value='';
  const result=await response.json();if(!response.ok)throw new Error(result.detail||'Sign-in failed');
  token=result.token;connected=true;geometryCache.clear();++generation;await sessionOrganizations();await inventory();message('Signed in. Select a private project.');
});});
$('organization').addEventListener('change',()=>{const next=$('organization').value;if(!preserveEdits()){$('organization').value=organization;return;}clearWorkspace();organization=next;action(async()=>{await inventory();message('Organization changed. Select a project.');});});
$('logout').addEventListener('click',()=>{if(!preserveEdits())return;action(async()=>{await api('/platform/logout',payload('POST',{}));clearWorkspace();token='';connected=false;organization='';$('individual-session').hidden=true;message('Signed out. Project data has been cleared from this page.');});});
$('next-projects').addEventListener('click',()=>{if(inventoryNext)action(async()=>{inventoryStack.push(inventoryCursor);await inventory('',inventoryNext);});});
$('previous-projects').addEventListener('click',()=>action(()=>inventory('',inventoryStack.pop()||'')));
['revisions','studies'].forEach(kind=>$('more-'+kind).addEventListener('click',()=>action(async()=>{
  const rawEditor=$('snapshot').value,wasDirty=dirty;const page=await api(`/projects/${current.project_id}/history/${kind}?limit=100`);let cursor=page.next_cursor;
  const retained=new Map(current[kind].map(r=>[kind==='revisions'?r.revision_sha256:r.study_sha256,r]));page[kind].forEach(r=>retained.set(kind==='revisions'?r.revision_sha256:r.study_sha256,r));
  // Load one bounded page at a time and keep its immutable continuation locally.
  if(current[kind+'_cursor']){const more=await api(`/projects/${current.project_id}/history/${kind}?limit=100&after=${encodeURIComponent(current[kind+'_cursor'])}`);more[kind].forEach(r=>retained.set(kind==='revisions'?r.revision_sha256:r.study_sha256,r));cursor=more.next_cursor;}
  const savedStudy=study,savedView={viewSnapshot,viewRevision,viewMode,selectedCase},caseOptions=[...$('view-case').options].map(o=>o.cloneNode(true));current[kind]=[...retained.values()];current[kind+'_cursor']=cursor;current[kind+'_more']=!!cursor;render(current);if(wasDirty){$('snapshot').value=rawEditor;dirty=true;$('save-state').textContent='Unsaved edits. Save before freezing a revision.';editors();}study=savedStudy;({viewSnapshot,viewRevision,viewMode,selectedCase}=savedView);$('view-case').replaceChildren(...caseOptions);$('view-case').value=selectedCase;showStudy();layout();await loadSummary();
})));
async function waitForJob(submitted,stillCurrent=()=>true){
  const pid=current.project_id;activeJob={...submitted,project_id:pid};$('cancel-job').hidden=current?.role!=='engineer';$('retry-job').hidden=true;
  try{for(let poll=0;poll<600;poll++){
    if(!stillCurrent())throw new Error('Study or workspace changed during report preparation.');
    const job=await api(`/projects/${pid}/jobs/${submitted.job_id}`);if(!stillCurrent())throw new Error('Study or workspace changed during report preparation.');activeJob={...job,project_id:pid};const attempt=job.attempts.at(-1);
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
  if(current&&hosted&&connected)await jobActivity.browse();
}

$('invite-member').addEventListener('submit',event=>{event.preventDefault();action(async()=>{const result=await api('/platform/projects/'+current.project_id+'/invitations',payload('POST',{email:$('invite-email').value,role:$('invite-role').value}));$('created-invitation').value=result.invitation_token;$('invitation-result').hidden=false;message('One-use invitation created for this email. It expires in 24 hours. Share it privately.');});});
$('accept-invitation').addEventListener('submit',event=>{event.preventDefault();if(!preserveEdits())return;action(async()=>{const result=await api('/platform/invitations/accept',payload('POST',{invitation_token:$('invitation-code').value}));$('invitation-code').value='';await sessionOrganizations();await openProject(result.project_id);await inventory(result.project_id);message('Invitation accepted for this project.');});});
