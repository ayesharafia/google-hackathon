const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
const payload=value=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
export function mountGroqChat(root,opts){
 let scope='',continuation='',pending=null,working=false,serial=0,runId='',configured=false,settingsBusy=false,settingsSerial=0,activeModel='';
 const status=el('p','Open a saved project to start.');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
 const form=el('form');form.className='groq-setup';
 const key=el('input');key.type='password';key.autocomplete='off';key.id='groq-key';key.maxLength=512;
 const model=el('input');model.id='groq-model';model.value='openai/gpt-oss-120b';model.maxLength=128;
 const label=(name,input)=>{const node=el('label',name);node.append(input);return node;};
 const saveSettings=el('button','Save AI settings');saveSettings.type='submit';
 const removeSettings=el('button','Remove saved key');removeSettings.type='button';
 const settingsStatus=el('p','Connect to configure AI.');settingsStatus.setAttribute('role','status');
 form.append(label('Groq API key',key),label('Groq model ID',model),saveSettings,removeSettings);
 const detail=el('details');detail.append(el('summary','Configure AI provider'),settingsStatus,el('p','Leave the key blank to keep the saved key. The server stores it encrypted.'),form);
 opts.settingsRoot.append(detail);
 const clear=el('button','New conversation');clear.type='button';
 const privacy=el('p','Sending a message shares your prompt and relevant project data with Groq and may incur usage charges. Conversation history lasts for this page session.');
 const transcript=el('div');transcript.className='groq-transcript';transcript.setAttribute('aria-label','Conversation');transcript.setAttribute('aria-live','polite');
 const promptForm=el('form');const prompt=el('textarea');prompt.id='groq-prompt';prompt.rows=3;prompt.maxLength=6000;
 const send=el('button','Send message');send.type='submit';promptForm.append(label('Ask about this project',prompt),send);
 const review=el('div');review.className='groq-review';const stop=el('button','Stop run');stop.type='button';stop.hidden=true;
 root.append(status,privacy,transcript,promptForm,stop,review,clear);
 const context=()=>opts.context();
 const scopeOf=c=>[c.generation,c.projectId,c.connected,c.publicAccess].join('|');
 function reset(){++serial;continuation='';pending=null;prompt.value='';transcript.replaceChildren();review.replaceChildren();working=false;}
 async function loadSettings(ticket){const number=++settingsSerial;try{const value=await opts.api('/agent/provider-settings');if(ticket!==scope||number!==settingsSerial)return;configured=value.configured;activeModel=value.model||'';model.value=value.model||'openai/gpt-oss-120b';settingsStatus.textContent=(value.shared?'Shared workspace: ':'')+(configured?'Groq key saved.':'No Groq key saved.');}catch(error){if(ticket!==scope||number!==settingsSerial)return;configured=false;settingsStatus.textContent=error.message;}sync();}
 function sync(){const c=context(),next=scopeOf(c);if(next!==scope){scope=next;reset();key.value='';configured=false;if(c.connected&&!c.publicAccess)loadSettings(next);}
  const available=Boolean(c.connected&&c.projectId&&!c.publicAccess&&(location.protocol==='https:'||['localhost','127.0.0.1','[::1]'].includes(location.hostname)));
  const settingsAvailable=Boolean(c.connected&&!c.publicAccess&&(location.protocol==='https:'||['localhost','127.0.0.1','[::1]'].includes(location.hostname)));
  for(const input of [key,model,saveSettings,removeSettings])input.disabled=!settingsAvailable||settingsBusy||working||Boolean(pending);
  for(const input of [prompt,send])input.disabled=!available||!configured||working||Boolean(pending);
  clear.disabled=working||!available;stop.hidden=!working||!runId;review.querySelectorAll('button').forEach(b=>{b.disabled=working||!available||(Boolean(pending)&&c.dirty);});status.textContent=!available?'Open an authenticated project over HTTPS or on this computer to use chat.':working?'Working with Groq…':pending?'Review the proposed action below.':c.dirty?'Save or discard unsaved edits before requesting changes.':'Ready for this saved project.';
  if(available&&!configured&&!working)status.textContent='Configure a Groq key in AI settings to start.';
 }
 form.addEventListener('submit',async e=>{e.preventDefault();if(settingsBusy)return;const ticket=scope;++settingsSerial;settingsBusy=true;sync();try{const value=await opts.api('/agent/provider-settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:key.value,model:model.value.trim()})});if(ticket!==scope)return;key.value='';configured=value.configured;if(activeModel&&activeModel!==value.model)reset();activeModel=value.model;settingsStatus.textContent=(value.shared?'Shared workspace: ':'')+'Groq key saved.';}catch(error){if(ticket===scope)settingsStatus.textContent=error.message;}finally{settingsBusy=false;sync();}});
 removeSettings.addEventListener('click',async()=>{if(settingsBusy)return;const ticket=scope;++settingsSerial;settingsBusy=true;sync();try{await opts.api('/agent/provider-settings',{method:'DELETE'});if(ticket!==scope)return;key.value='';configured=false;settingsStatus.textContent='Groq key removed.';reset();}catch(error){if(ticket===scope)settingsStatus.textContent=error.message;}finally{settingsBusy=false;sync();}});
 function add(kind,text){const block=el('section');block.className='groq-message';block.dataset.kind=kind.toLowerCase().replaceAll(' ','-');block.append(el('strong',kind),el('p',text));transcript.append(block);}
 function renderReview(result){review.replaceChildren(el('h4','Review requested action'));
  review.append(el('p',result.action));const preview=result.data.preview;
  if(Array.isArray(preview.changes)){const table=el('table'),head=el('tr');for(const title of ['Input','Before','After','Units'])head.append(el('th',title));table.append(head);
   for(const change of preview.changes){const row=el('tr');for(const value of [change.item_name?change.item_name+' · '+change.field:change.field,change.before,change.after,change.unit])row.append(el('td',value==null?'Unknown':Array.isArray(value)?value.join(', '):String(value)));table.append(row);}
   const wrap=el('div');wrap.className='agent-values';wrap.tabIndex=0;wrap.setAttribute('aria-label','Proposed values');wrap.append(table);review.append(wrap);}
  const details=el('details');details.append(el('summary','Exact review details'));const pre=el('pre',JSON.stringify(preview,null,2));pre.tabIndex=0;details.append(pre);review.append(details);
  const approve=el('button','Approve and run'),reject=el('button','Reject');approve.type=reject.type='button';
  approve.addEventListener('click',()=>decide(true));reject.addEventListener('click',()=>decide(false));review.append(approve,reject);
 }
 async function decide(approve){if(!pending||working||context().dirty)return;const ticket=scope,number=++serial;working=true;sync();
  await opts.exclusive(async()=>{try{const endpoint='/agent/reviews/'+pending.data.review_id+(approve?'/confirm':'/reject');
   const result=await opts.api(endpoint,payload(approve?{execute:true}:{}));if(ticket!==scope||number!==serial)return;
   add('Action',(result.action||pending.action)+' · '+result.status);review.replaceChildren();pending=null;await opts.saved();
   const resume=el('button','Continue with Groq');resume.type='button';resume.addEventListener('click',()=>run(''));review.append(resume);
  }catch(error){if(ticket===scope&&number===serial)add('Review error',error.message);}});working=false;sync();
 }
 async function run(text){const c=context();if(working)return;if(!configured){add('Chat error','Configure a Groq key in AI settings first.');return;}
  const ticket=scope,number=++serial;runId=crypto.randomUUID().replaceAll('-','');working=true;sync();if(text)add('You',text);
  await opts.exclusive(async()=>{try{const result=await opts.api('/agent/chat',payload({project_id:c.projectId,prompt:text,continuation,dirty:c.dirty,run_id:runId}));
   if(ticket!==scope||number!==serial)return;continuation=result.continuation||'';
   for(const action of result.actions||[])add('Action',action.action+' · '+action.status);
   if(result.status==='awaiting_review'){pending=result.review;renderReview(pending);}else if(result.status==='stopped'){add('Run stopped','No further actions will be requested. An action already in progress may have finished; check action history.');}else{review.replaceChildren();add('Assistant',result.message);}
  }catch(error){if(ticket===scope&&number===serial)add('Chat error',error.message);}});runId='';working=false;sync();
 }
 stop.addEventListener('click',async()=>{if(!runId)return;stop.disabled=true;try{await opts.api('/agent/chat/stop',payload({project_id:context().projectId,run_id:runId}));add('Stop requested','The current provider request or action may finish.');}catch(error){add('Stop error',error.message);}finally{stop.disabled=false;}});
 promptForm.addEventListener('submit',e=>{e.preventDefault();const text=prompt.value.trim();if(!text)return;if(!configured){add('Chat error','Configure a Groq key in AI settings first.');return;}prompt.value='';run(text);});
 clear.addEventListener('click',()=>{reset();sync();});sync();return {sync};
}
