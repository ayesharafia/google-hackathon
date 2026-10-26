// Literal durable-job evidence. Viewing a job never submits or retries work.
const states=['queued','running','succeeded','failed','cancelled'];
const attemptStates=['running','accepted','failed','cancelled','expired'];
const finite=n=>typeof n==='number'&&Number.isFinite(n);
const integer=n=>Number.isInteger(n)&&n>=0;
const hash=s=>typeof s==='string'&&/^[0-9a-f]{64}$/.test(s);
const jobId=s=>typeof s==='string'&&/^job_[a-zA-Z0-9_-]{1,100}$/.test(s);
const object=s=>{try{const value=JSON.parse(s);return value&&typeof value==='object'&&!Array.isArray(value)?value:null;}catch{return null;}};
const canonical=value=>JSON.stringify(value,(_key,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);
export function jobTime(value){
  if(!finite(value))return 'Not recorded';
  const date=new Date(value*1000);return Number.isFinite(date.getTime())?date.toISOString():'Unavailable';
}
export function jobView(job,project,id){
  if(!job||!jobId(id)||job.job_id!==id||job.project_id!==project)throw new Error('Job identity differs from the selected project or job.');
  if(!['study','report'].includes(job.kind)||!states.includes(job.state)||!integer(job.attempt_count)
      ||job.attempt_count>5||!integer(job.generation)||!integer(job.max_attempts)||job.max_attempts<1||job.max_attempts>5
      ||!finite(job.created_at)||!finite(job.ready_at)||!(job.reason==null||typeof job.reason==='string'))
    throw new Error('Job status or recorded metadata is unsupported.');
  if(!Array.isArray(job.attempts)||job.attempts.length!==job.attempt_count||job.attempts.some((a,i)=>
    !a||a.job_id!==id||typeof a.attempt_id!=='string'||!a.attempt_id||!integer(a.generation)||a.generation<1
    ||a.generation>job.generation||(i>0&&a.generation<=job.attempts[i-1].generation)
    ||!attemptStates.includes(a.state)||!finite(a.started_at)||!(a.finished_at==null||finite(a.finished_at))
    ||!finite(a.progress)||a.progress<0||a.progress>1||typeof a.detail!=='string'))
    throw new Error('Attempt history is missing or inconsistent.');
  const spec=object(job.spec_json),receipt=object(job.result_json);let study=null;
  if(job.state==='succeeded'&&spec&&receipt&&hash(receipt.artifact_sha256)){
    if(job.kind==='study'&&hash(spec.revision_sha256)&&hash(receipt.study_sha256))study=receipt.study_sha256;
    if(job.kind==='report'&&hash(spec.study_sha256)&&spec.report_identity&&receipt.report_identity
        &&canonical(spec.report_identity)===canonical(receipt.report_identity))study=spec.study_sha256;
  }
  return {job,study,canCancel:['queued','running'].includes(job.state),
    canRetry:['failed','cancelled'].includes(job.state)&&job.attempt_count<5};
}
export function jobPage(page){
  if(!page||!Array.isArray(page.jobs)||page.jobs.length>100||!(page.next_cursor==null||typeof page.next_cursor==='string'))throw new Error('Job history response is unsupported.');
  const seen=new Set();for(const row of page.jobs){
    if(!row||!jobId(row.job_id)||seen.has(row.job_id)||!['study','report'].includes(row.kind)||!states.includes(row.state)
        ||!integer(row.attempt_count)||row.attempt_count>5||!finite(row.created_at))throw new Error('Job history entry is invalid or duplicated.');
    seen.add(row.job_id);
  }return page;
}
export function createJobActivity({request,readContext,isContext,canWrite,changed,now=()=>new Date().toISOString()}){
  let epoch=0,listSerial=0,detailSerial=0;
  let state={items:[],cursor:null,selected:'',view:null,listPending:false,detailPending:false,commandPending:false,checked:null,message:'Choose a job to inspect. Recorded status updates only when refreshed.'};
  const emit=()=>changed({...state});
  const valid=(c,e)=>epoch===e&&isContext(c);
  function reset(){++epoch;++listSerial;++detailSerial;state={items:[],cursor:null,selected:'',view:null,listPending:false,detailPending:false,commandPending:false,checked:null,message:'Choose a job to inspect. Recorded status updates only when refreshed.'};emit();}
  async function browse(more=false){
    if(state.listPending||more&&!state.cursor)return;
    const c=readContext(),e=epoch,ticket=++listSerial,cursor=more?state.cursor:null;
    state.listPending=true;emit();
    try{const page=jobPage(await request(`/projects/${c.project}/jobs?limit=25`+(cursor?'&after='+encodeURIComponent(cursor):'')));
      if(!valid(c,e)||ticket!==listSerial)return;
      const rows=more?[...state.items,...page.jobs]:page.jobs;
      state.items=[...new Map(rows.map(row=>[row.job_id,row])).values()];state.cursor=page.next_cursor;
    }catch(error){if(valid(c,e)&&ticket===listSerial)state.message='Job history unavailable: '+error.message;}
    finally{if(valid(c,e)&&ticket===listSerial){state.listPending=false;emit();}}
  }
  async function inspect(id){
    if(state.commandPending)return;
    const c=readContext(),e=epoch,ticket=++detailSerial;
    state.selected=id;state.view=null;state.checked=null;state.detailPending=true;state.commandPending=false;state.message='Loading selected job…';emit();
    try{const job=await request(`/projects/${c.project}/jobs/${id}`);if(!valid(c,e)||ticket!==detailSerial)return;
      state.view=jobView(job,c.project,id);state.checked=now();state.message='Recorded job loaded. Refresh to check for changes.';
    }catch(error){if(valid(c,e)&&ticket===detailSerial){state.view=null;state.message='Job inspection unavailable: '+error.message;}}
    finally{if(valid(c,e)&&ticket===detailSerial){state.detailPending=false;emit();}}
  }
  async function recover(kind){
    if(state.commandPending||state.detailPending||!state.view||!canWrite()||!['cancel','retry'].includes(kind)
        ||!(kind==='cancel'?state.view.canCancel:state.view.canRetry))return;
    const c=readContext(),e=epoch,ticket=++detailSerial,id=state.selected;
    state.commandPending=true;state.message=kind==='retry'?'Requesting another attempt…':'Requesting cancellation…';emit();
    try{const job=await request(`/projects/${c.project}/jobs/${id}/${kind}`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      if(!valid(c,e)||ticket!==detailSerial)return;
      state.view=jobView(job,c.project,id);state.checked=now();state.message='Server response recorded: '+job.state+'. Refresh to check later changes.';
      state.items=state.items.map(row=>row.job_id===id?{...row,state:job.state,attempt_count:job.attempt_count,reason:job.reason}:row);
    }catch(error){if(valid(c,e)&&ticket===detailSerial){state.view=null;state.checked=null;state.message='Recovery request unavailable: '+error.message+'. Refresh the job before another action.';}}
    finally{if(valid(c,e)&&ticket===detailSerial){state.commandPending=false;emit();}}
  }
  return {reset,browse,inspect,recover,getState:()=>({...state})};
}
const el=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
export function mountJobActivity({list,detail,refresh,more,request,readContext,isContext,canRead,canWrite,canOpen,openStudy}){
  let current=null,drawn=null,actionControls=[],focusAfter='';
  const controller=createJobActivity({request,readContext,isContext,canWrite,changed:render});
  function updateAccess(){
    if(!current)return;
    refresh.disabled=!canRead()||current.listPending;more.disabled=!canRead()||current.listPending;more.hidden=!current.cursor;
    list.querySelectorAll('button').forEach(button=>button.disabled=!canRead()||current.commandPending);
    for(const [button,allowed] of actionControls)button.disabled=!allowed()||!canRead()||current.detailPending||current.commandPending;
  }
  function render(state){
    if(!state.selected)focusAfter='';
    const focusedJob=list.contains(document.activeElement)?document.activeElement.dataset.jobId:null;
    if(detail.contains(document.activeElement)&&document.activeElement.tagName==='BUTTON')focusAfter=document.activeElement.textContent;
    current=state;list.replaceChildren();list.setAttribute('aria-busy',String(state.listPending));
    if(!state.items.length)list.append(el('li',state.listPending?'Loading jobs…':'No jobs loaded.'));
    for(const row of state.items){const li=el('li'),button=el('button',row.kind+' · '+row.state+'\n'+row.job_id.slice(-8)+' · attempts '+row.attempt_count);
      button.type='button';button.dataset.jobId=row.job_id;button.setAttribute('aria-pressed',String(row.job_id===state.selected));
      button.addEventListener('click',()=>{if(canRead()&&button.isConnected){controller.inspect(row.job_id);detail.focus({preventScroll:true});detail.scrollIntoView({block:'start'});}});li.append(button);list.append(li);}
    // Preserve focus on list updates, and avoid rebuilding a selected exact record for pagination.
    const signature=state.selected+'|'+state.detailPending+'|'+state.commandPending+'|'+state.checked+'|'+state.message;
    if(drawn!==signature){drawn=signature;detail.replaceChildren();actionControls=[];
      detail.setAttribute('aria-busy',String(state.detailPending||state.commandPending));
      const status=el('p',state.message);status.setAttribute('role','status');detail.append(status);
      if(state.selected){const refreshJob=el('button','Refresh selected job');refreshJob.type='button';refreshJob.addEventListener('click',()=>{if(canRead()&&refreshJob.isConnected&&!current.commandPending)controller.inspect(current.selected);});detail.append(refreshJob);actionControls.push([refreshJob,()=>!current.commandPending]);}
      if(state.view)renderDetail(state);
    }updateAccess();
    if(focusedJob)list.querySelector(`[data-job-id="${focusedJob}"]`)?.focus({preventScroll:true});
    if(focusAfter&&!state.detailPending&&!state.commandPending){
      const target=[...detail.querySelectorAll('button')].find(button=>button.textContent===focusAfter&&!button.disabled&&!button.hidden);
      (target||detail).focus({preventScroll:true});focusAfter='';
    }
  }
  function renderDetail(state){
    const view=state.view,job=view.job,binding=el('p',job.job_id+'\nProject '+job.project_id);binding.className='job-binding';detail.append(binding);
    const facts=el('dl');facts.className='job-facts';
    for(const [label,value] of [['Recorded state',job.state],['Job type',job.kind],['Created, UTC',jobTime(job.created_at)],['Eligible to run, UTC',jobTime(job.ready_at)],['Attempts started',job.attempt_count],['Current attempt limit',job.max_attempts],['Failure reason',job.reason??'Not recorded'],['Last checked, UTC',state.checked]]){
      const pair=el('div');pair.append(el('dt',label),el('dd',String(value)));facts.append(pair);
    }detail.append(facts,el('p','Progress is reported by each attempt; it is not an estimate of time remaining. Refresh status manually.'));
    const scroll=el('div');scroll.className='table-scroll';scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label','Recorded job attempts. Scroll horizontally for all columns.');
    const table=el('table'),caption=el('caption','Recorded attempts'),head=el('thead'),hr=el('tr'),body=el('tbody');
    for(const label of ['Generation','State','Started, UTC','Finished, UTC','Reported progress','Detail']){const th=el('th',label);th.scope='col';hr.append(th);}head.append(hr);
    for(const attempt of job.attempts){const tr=el('tr'),th=el('th',String(attempt.generation));th.scope='row';tr.append(th,...[attempt.state,jobTime(attempt.started_at),jobTime(attempt.finished_at),String(attempt.progress*100)+'%',attempt.detail].map(value=>el('td',value)));body.append(tr);}
    table.append(caption,head,body);scroll.append(table);if(job.attempts.length)detail.append(scroll);else detail.append(el('p','No attempt has been recorded.'));
    const actions=el('div');actions.className='job-recovery';
    for(const [kind,label,allowed] of [['cancel','Cancel selected job',view.canCancel],['retry','Retry selected job',view.canRetry]]){
      const button=el('button',label);button.type='button';button.hidden=!allowed;
      button.addEventListener('click',()=>{if(canRead()&&button.isConnected&&current.view===view)controller.recover(kind);});actions.append(button);actionControls.push([button,()=>canWrite()&&allowed]);
    }
    if(view.study){const open=el('button','Open associated retained study');open.type='button';
      open.addEventListener('click',()=>{if(canRead()&&canOpen()&&open.isConnected&&current.view===view&&!current.commandPending)openStudy(view.study,job);});
      actions.append(open);actionControls.push([open,()=>canOpen()]);}
    detail.append(actions,el('p',canWrite()?'Recovery uses the existing server rules and attempt limits. Retry may run computation again.':'Viewing job evidence grants no permission to cancel or retry work.'));
    const exact=el('details');exact.append(el('summary','Exact job record'),el('pre',JSON.stringify(job,null,2)));detail.append(exact);
  }
  refresh.addEventListener('click',()=>{if(canRead())controller.browse();});more.addEventListener('click',()=>{if(canRead())controller.browse(true);});
  controller.reset();return {...controller,updateAccess};
}
