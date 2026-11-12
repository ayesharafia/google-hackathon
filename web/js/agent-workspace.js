/* A model-neutral connection/review sheet. Credentials never enter browser storage. */
const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
const body=value=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
const requestId=()=>globalThis.crypto?.randomUUID?.().replaceAll('-','')||'request_'+Date.now()+'_'+Math.random().toString(36).slice(2);
const time=value=>new Intl.DateTimeFormat(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZoneName:'short'}).format(new Date(value*1000));
const plannedLabels={workspace_creation:'new-project creation',geometry:'geometry tools',source_library:'source library tools',source_binding:'source assignment',remaining_authoring:'additional design inputs',reports:'report generation',collaboration:'team workflows',embedded_conversation:'in-app conversation',owner_development:'owner code changes',http_mcp:'hosted MCP connections'};
export const scopeKey=c=>[c.generation,c.projectId,c.connected,c.publicAccess].join('|');
export function connectionConfig(origin){
  const url=new URL(origin);
  if(!['https:','http:'].includes(url.protocol))throw new Error('An HTTP workspace origin is required.');
  return {mcpServers:{PhysiCore:{command:'python3',args:['-m','physimesh.agent.mcp'],env:{
    PHYSICORE_API_URL:url.origin,PHYSICORE_AGENT_TOKEN_FILE:'/path/to/private/physicore-credential.txt'}}}};
}
export function editValue(field,raw){
  const parts=raw.split(',').map(v=>v.trim());
  if(parts.some(v=>!v||!/^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?$/i.test(v)))throw new Error('Enter explicit finite numbers.');
  const values=parts.map(Number);
  if(values.some(v=>!Number.isFinite(v)))throw new Error('Enter finite values.');
  if(field==='cg_body_m'){if(values.length!==3)throw new Error('Enter exactly three body coordinates.');return values;}
  if(values.length!==1)throw new Error('Enter one value.');return values[0];
}
export function proposalMatches(p,c){return Boolean(c.connected&&c.canWrite&&!c.dirty&&p?.project_id===c.projectId&&p.expected_version===c.version);}

export function mountAgentWorkspace(root,options){
  let key='',pending=false,serial=0,proposal=null,lastApplied=null;
  const status=el('p','Open a saved project to connect an AI client.');status.role='status';status.setAttribute('aria-live','polite');status.className='agent-status';status.id='agent-status';
  const binding=el('p');binding.className='agent-binding';
  const connect=el('form');connect.className='agent-form';
  function field(labelText,input){const label=el('label',labelText);label.append(input);return label;}
  function button(text,handler,cls=''){const b=el('button',text);b.type='button';b.className=cls;b.addEventListener('click',()=>{if(b.isConnected)handler(b);});return b;}
  const name=el('input');name.id='agent-client-name';name.required=true;name.maxLength=100;name.value='My AI client';
  const life=el('select');life.id='agent-lifetime';for(const [value,label] of [['3600','1 hour'],['28800','8 hours'],['86400','24 hours maximum']])life.append(new Option(label,value));
  const reviewed=el('input');reviewed.type='checkbox';reviewed.id='agent-reviewed';
  const check=field('Allow reviewed draft changes and studies',reviewed);check.className='agent-check';
  const create=el('button','Create AI connection');create.type='submit';
  connect.append(field('Connection name',name),field('Connection lifetime',life),check,create);
  const credential=el('section');credential.hidden=true;credential.className='agent-credential';
  const secret=el('input');secret.id='agent-credential';secret.type='password';secret.readOnly=true;secret.autocomplete='off';secret.setAttribute('aria-describedby','agent-secret-help');
  const help=el('p','Shown once. Keep this credential in your AI client’s protected configuration, outside the conversation.');help.id='agent-secret-help';
  const show=button('Show credential',()=>{secret.type=secret.type==='password'?'text':'password';show.textContent=secret.type==='password'?'Show credential':'Hide credential';});
  const clear=button('Clear credential from this page',()=>{clearSecret();setStatus('Credential cleared from this page. The connection remains active until revoked or expired.');},'agent-text-action');
  const download=button('Download MCP connection settings',()=>{
    const blob=new Blob([JSON.stringify(connectionConfig(location.origin),null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download='physicore-mcp-connection.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    setStatus('Connection settings downloaded without a credential. Save the credential privately and set its file path in those settings.');
  });
  const credentialActions=el('div');credentialActions.className='agent-actions';credentialActions.append(show,clear,download);
  credential.append(field('AI-client credential (shown once)',secret),help,credentialActions,
    el('p','Install the PhysiCore MCP extra in the AI client’s Python environment. The connection settings contain a private credential-file path to configure.'));
  const refresh=button('Refresh AI connections and actions',()=>perform(load,true));refresh.id='agent-refresh';
  const connections=el('div');connections.id='agent-connections';
  const catalog=el('details');catalog.append(el('summary','Available actions and limits'));const catalogBody=el('div');catalog.append(catalogBody);
  const prepare=el('details');prepare.append(el('summary','Prepare a project change'));
  const form=el('form');form.className='agent-form';
  const selection=el('select');selection.id='agent-edit-field';
  for(const [value,label] of [['mission.duration_s','Mission duration'],['mission.payload_mass_kg','Installed payload mass'],['mass_kg','Existing mass item'],['cg_body_m','Existing mass item position']])selection.append(new Option(label,value));
  const item=el('select');item.id='agent-item-name';const itemLabel=field('Saved mass item name',item);
  const value=el('input');value.id='agent-edit-value';value.required=true;value.inputMode='decimal';
  const valueLabel=field('New value',value),units=el('select');units.id='agent-edit-unit';
  const preview=el('button','Preview change');preview.type='submit';
  form.append(field('Change',selection),itemLabel,valueLabel,field('Declared units',units),preview);
  const changes=el('div');changes.id='agent-proposal';prepare.append(el('p','These controls use the same actions as MCP clients. Only explicit user values are proposed; measurements and sources are never inferred.'),form,changes);
  const history=el('div');history.id='agent-history';
  root.append(binding,status,connect,credential,refresh,connections,catalog,prepare,history);

  function setStatus(text,error=false){status.textContent=text;status.className='agent-status'+(error?' error':'');}
  function clearSecret(){secret.value='';secret.type='password';credential.hidden=true;show.textContent='Show credential';}
  function usable(){const c=options.context();return c.connected&&c.projectId&&!c.publicAccess;}
  function active(ticket){return ticket===key&&ticket===scopeKey(options.context());}
  async function perform(work,readOnly=false){
    if(pending||!usable())return;
    const ticket=key;pending=true;sync();
    const execute=async()=>{try{await work(ticket);}catch(error){if(active(ticket))setStatus(error.message,true);}};
    try{if(readOnly)await execute();else await options.exclusive(execute);}
    finally{if(active(ticket))pending=false;sync();}
  }
  function layoutFields(){
    const vector=selection.value==='cg_body_m',mass=['mass_kg','cg_body_m'].includes(selection.value);
    itemLabel.hidden=!mass;item.required=mass;
    const text=vector?'New body coordinates, x, y, z':'New value';valueLabel.firstChild.textContent=text;
    units.replaceChildren(...(vector?['m','cm','mm']:selection.value==='mission.duration_s'?['s','min']:['kg','g']).map(v=>new Option(v,v)));
    value.value='';
  }
  selection.addEventListener('change',layoutFields);layoutFields();
  function valuesTable(values,reverse=false){
    const wrap=el('div');wrap.className='agent-values';wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label','Proposed values; scroll horizontally if needed');
    const table=el('table'),head=el('thead'),row=el('tr');for(const text of ['Input','Before','After','Units'])row.append(el('th',text));head.append(row);table.append(head);
    const tbody=el('tbody');for(const change of values){const tr=el('tr');for(const v of [change.item_name?change.item_name+' · '+change.field:change.field,reverse?change.after:change.before,reverse?change.before:change.after,change.unit])tr.append(el('td',Array.isArray(v)?v.join(', '):v==null?'Unknown':String(v)));tbody.append(tr);}table.append(tbody);wrap.append(table);return wrap;
  }
  function renderProposal(){
    changes.replaceChildren();if(!proposal)return;
    changes.append(el('h4','Review declared input changes'),el('p','Saved draft '+proposal.expected_version+' · '+proposal.proposal_id),valuesTable(proposal.changes),el('p',proposal.qualification));
    const apply=button('Apply reviewed change',()=>perform(async ticket=>{
      const c=options.context();if(!proposalMatches(proposal,c))throw new Error('Draft context changed. Save and prepare a new proposal.');
      const selected=proposal;
      const prepared=await options.api('/agent/actions/proposal.apply',body({request_id:requestId(),arguments:{project_id:c.projectId,proposal_id:selected.proposal_id}}));
      if(!active(ticket)||proposal!==selected)return;
      const candidate=prepared.data.preview;
      if(prepared.status!=='awaiting_review'||candidate.proposal_id!==selected.proposal_id||JSON.stringify(candidate.changes)!==JSON.stringify(selected.changes))throw new Error('Review binding changed. Refresh action history.');
      const result=await options.api('/agent/reviews/'+prepared.data.review_id+'/confirm',body({execute:true}));
      if(!active(ticket))return;
      lastApplied={proposal:selected,version:result.data.draft_version};proposal=null;renderProposal();
      await options.saved();if(!active(ticket))return;
      setStatus('Reviewed change saved as draft '+result.data.draft_version+'. Frozen evidence remains available.');await load(ticket);
    }));
    apply.dataset.agentApply='true';changes.append(apply);
  }
  function renderRecords(records,ticket){
    history.replaceChildren(el('h4','Action history and pending reviews'));
    const pendingReviews=records.reviews.filter(r=>['pending','approved'].includes(r.status));
    if(!pendingReviews.length)history.append(el('p','No pending action reviews.'));
    for(const review of pendingReviews){
      const section=el('section');section.className='agent-review';section.append(el('h4',review.action),el('p',review.status+' · expires '+time(review.expires)));
      if(review.preview.changes)section.append(valuesTable(review.preview.changes,review.preview.operation==='undo'));
      else{const details=el('details');details.append(el('summary','Exact action inputs'),el('pre',JSON.stringify(review.preview,null,2)));section.append(details);}
      const approve=button('Approve and run '+review.action,b=>perform(async t=>{
        if(!b.isConnected||!active(ticket)||options.context().dirty)throw new Error('Save your open edits before approving a saved-design action.');
        const result=await options.api('/agent/reviews/'+review.review_id+'/confirm',body({execute:true}));
        if(!active(t))return;
        if(review.action==='proposal.apply')lastApplied={proposal:review.preview,version:result.data.draft_version};
        if(review.action==='proposal.undo')lastApplied=null;
        if(['proposal.apply','proposal.undo','design.freeze','study.run'].includes(review.action))await options.saved();
        setStatus('Action '+result.status+'. Its exact receipt is available below.');await load(t);
      }));approve.dataset.agentMutation='true';approve.dataset.agentExpires=String(review.expires);approve.disabled=review.expires*1000<=Date.now();
      const reject=button('Reject '+review.action,b=>perform(async t=>{
        if(!b.isConnected||!active(ticket))return;await options.api('/agent/reviews/'+review.review_id+'/reject',body({}));if(active(t)){setStatus('Review rejected.');await load(t);}
      }),'agent-text-action');reject.dataset.agentWrite='true';
      const actions=el('div');actions.className='agent-actions';actions.append(approve,reject);section.append(actions);history.append(section);
    }
    if(lastApplied){
      const undo=button('Undo the change from this page',()=>perform(async t=>{
        const c=options.context(),applied=lastApplied;
        if(c.dirty||c.version!==applied.version)throw new Error('Later draft changes exist. Undo cannot replace them.');
        const prepared=await options.api('/agent/actions/proposal.undo',body({request_id:requestId(),arguments:{project_id:c.projectId,proposal_id:applied.proposal.proposal_id}}));
        if(!active(t)||prepared.status!=='awaiting_review')return;
        const binding=prepared.data.preview;
        if(binding.proposal_id!==applied.proposal.proposal_id||binding.expected_current_version!==c.version)throw new Error('Undo context changed.');
        const result=await options.api('/agent/reviews/'+prepared.data.review_id+'/confirm',body({execute:true}));
        if(!active(t))return;lastApplied=null;await options.saved();if(active(t)){setStatus('Previous inputs restored in new draft '+result.data.draft_version+'.');await load(t);}
      }));undo.dataset.agentMutation='true';history.append(undo);
    }
    const receipts=el('details');receipts.append(el('summary','Recorded action receipts ('+records.invocations.length+')'));history.append(receipts);
    if(!records.invocations.length)receipts.append(el('p','No recorded actions for this user and project.'));
    for(const record of records.invocations){
      const row=el('div');row.className='agent-receipt';row.append(el('p',record.action+' · '+record.state+' · '+record.receipt_id.slice(-8)+(record.reason?' · '+record.reason:'')));
      const exact=el('div');
      const inspect=button('Inspect receipt '+record.receipt_id.slice(-8),b=>perform(async t=>{
        if(!b.isConnected||!active(ticket))return;
        const result=await options.api('/agent/actions/receipt.get',body({request_id:requestId(),arguments:{project_id:options.context().projectId,receipt_id:record.receipt_id}}));
        if(active(t)&&b.isConnected)exact.replaceChildren(el('pre',JSON.stringify(result.data,null,2)));
      },true),'agent-text-action');inspect.dataset.agentRead='true';row.append(inspect,exact);receipts.append(row);
    }
  }
  async function load(ticket){
    const c=options.context(),request=++serial;
    const [catalogData,grants,records]=await Promise.all([
      options.api('/agent/catalog?project_id='+encodeURIComponent(c.projectId)),options.api('/agent/grants'),options.api('/agent/records/'+c.projectId)]);
    if(!active(ticket)||request!==serial)return;
    catalogBody.replaceChildren(el('p',catalogData.actions.length+' actions available. Planned: '+catalogData.pending_domains.map(name=>plannedLabels[name]||name).join(', ')+'.'));
    const list=el('ul');for(const action of catalogData.actions)list.append(el('li',action.id+' · '+action.description));catalogBody.append(list);
    connections.replaceChildren(el('h4','Connections for this project'));
    const visible=grants.grants.filter(g=>g.project_id===c.projectId);
    if(!visible.length)connections.append(el('p','No AI connections created here.'));
    for(const grant of visible){
      const row=el('div');row.className='agent-connection-row';const expired=grant.revoked||grant.expires*1000<=Date.now();
      row.append(el('p',grant.name+' · '+(grant.revoked?'revoked':expired?'expired':'active')+' · '+grant.calls+'/'+grant.max_calls+' action calls · expires '+time(grant.expires)));
      if(!expired)row.append(button('Revoke '+grant.name,b=>perform(async t=>{if(!b.isConnected||!active(ticket))return;await options.api('/agent/grants/'+grant.grant_id,{method:'DELETE'});if(active(t)){clearSecret();setStatus('AI connection revoked.');await load(t);}}),'agent-text-action'));
      connections.append(row);
    }
    renderRecords(records,ticket);sync();
  }
  connect.addEventListener('submit',event=>{event.preventDefault();perform(async ticket=>{
    clearSecret();const c=options.context(),groups=c.canWrite?['read','propose']:['read'];if(reviewed.checked&&c.canWrite)groups.push('change','study');
    const result=await options.api('/agent/grants',body({project_id:c.projectId,name:name.value,lifetime_s:Number(life.value),groups}));
    if(!active(ticket))return;secret.value=result.token;credential.hidden=false;
    setStatus('AI connection created. This credential is shown once and has no owner code permissions.');await load(ticket);
  });});
  form.addEventListener('submit',event=>{event.preventDefault();perform(async ticket=>{
    const c=options.context();if(c.dirty||!c.canWrite)throw new Error('Save the draft first, with project write permission.');
    const edit={field:selection.value,value:editValue(selection.value,value.value),unit:units.value};if(!itemLabel.hidden)edit.item_name=item.value;
    const result=await options.api('/agent/actions/design.propose',body({request_id:requestId(),arguments:{project_id:c.projectId,expected_version:c.version,edits:[edit]}}));
    if(!active(ticket)||c.version!==options.context().version||options.context().dirty)return;
    proposal=result.data;renderProposal();setStatus('Proposal prepared. Review each value before applying.');sync();
  });});
  function sync(){
    const c=options.context(),next=scopeKey(c);
    if(next!==key){key=next;++serial;pending=false;proposal=null;lastApplied=null;clearSecret();connections.replaceChildren();history.replaceChildren();catalogBody.replaceChildren();changes.replaceChildren();setStatus(c.publicAccess?'AI client access requires an authenticated workspace.':c.projectId?'Refresh to inspect this project’s AI capabilities and actions.':'Open a saved project to connect an AI client.');}
    const disabled=!usable()||pending||c.busy;
    binding.textContent=c.projectId?(c.projectTitle||'Project')+' · '+c.projectId.slice(-8)+' · saved draft '+c.version+(c.dirty?' · unsaved browser edits':''):'';
    for(const input of connect.querySelectorAll('input,select,button'))input.disabled=disabled;
    reviewed.disabled=disabled||!c.canWrite;refresh.disabled=disabled;
    for(const input of form.querySelectorAll('input,select,button'))input.disabled=disabled||!c.canWrite||c.dirty;
    for(const b of changes.querySelectorAll('button'))b.disabled=disabled||!proposalMatches(proposal,c);
    if(proposal&&!pending&&!proposalMatches(proposal,c))setStatus('Draft inputs changed. Save your edits, then prepare a new proposal.');
    for(const b of history.querySelectorAll('button'))b.disabled=disabled||(b.dataset.agentRead!=='true'&&!c.canWrite)||(b.dataset.agentMutation==='true'&&c.dirty)||(b.dataset.agentExpires&&Number(b.dataset.agentExpires)*1000<=Date.now());
    for(const b of connections.querySelectorAll('button'))b.disabled=disabled;
    if(item.dataset.version!==String(c.version)+'|'+c.projectId){item.replaceChildren(new Option('Choose a saved item',''),...(c.massNames||[]).map(n=>new Option(n,n)));item.dataset.version=String(c.version)+'|'+c.projectId;}
    root.setAttribute('aria-busy',String(pending));
  }
  sync();return {sync};
}