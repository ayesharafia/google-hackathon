const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
const send=(method,body)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export function mountRemoteConsent(root,opts){
 let scope='',counter=0,working=false;
 const title=el('h4','Remote MCP connections');const note=el('p','A compatible client signs in with the configured provider. Give it access to this project by entering its provider-issued client ID.');
 const status=el('p','Remote MCP is not configured.');status.setAttribute('role','status');
 const area=el('div');area.hidden=true;const endpoint=el('p');const form=el('form');form.className='agent-form';
 const id=el('input');id.id='remote-client-id';id.required=true;id.maxLength=512;const label=el('label','Provider client ID');label.append(id);
 const life=el('select');for(const [n,text] of [['3600','1 hour'],['28800','8 hours'],['86400','Up to 24 hours']])life.append(new Option(text,n));const duration=el('label','Connection lifetime');duration.append(life);
 const changes=el('input');changes.type='checkbox';changes.id='remote-reviewed';const changeLabel=el('label','Allow proposals and reviewed changes and studies');changeLabel.className='agent-check';changeLabel.append(changes);
 const create=el('button','Allow this client');create.type='submit';form.append(label,duration,changeLabel,create);
 const list=el('div');const refresh=el('button','Refresh remote connections');refresh.type='button';area.append(endpoint,form,refresh,list);root.append(title,note,status,area);
 const context=()=>opts.context(),key=c=>[c.generation,c.projectId,c.connected,c.publicAccess].join('|');
 function sync(){const c=context(),next=key(c);if(next!==scope){scope=next;++counter;id.value='';changes.checked=false;area.hidden=true;list.replaceChildren();if(c.connected&&c.projectId&&!c.publicAccess)load();}
  for(const e of [id,life,create,refresh])e.disabled=working||!c.connected||!c.projectId;changes.disabled=working||!c.canWrite;}
 async function load(){const ticket=scope,n=++counter;try{const info=await opts.api('/agent/remote-info');if(ticket!==scope||n!==counter)return;if(!info.enabled){area.hidden=true;status.textContent='Remote MCP is not configured on this server.';return;}
  const records=await opts.api('/agent/remote-consents?project_id='+encodeURIComponent(context().projectId));if(ticket!==scope||n!==counter)return;
  area.hidden=false;endpoint.textContent='MCP endpoint: '+info.endpoint;status.textContent='Only a signed-in, authorized client can use this project.';list.replaceChildren();
  for(const row of records.consents){const section=el('section');section.className='agent-connection-row';section.append(el('p',row.client_id+' · '+(row.revoked?'revoked':new Date(row.expires*1000)<=new Date()?'expired':'active')+' · '+row.groups.join(', ')+' · expires '+new Date(row.expires*1000).toLocaleString()));if(!row.revoked){const revoke=el('button','Revoke '+row.client_id);revoke.type='button';revoke.className='agent-text-action';revoke.addEventListener('click',()=>perform(async()=>{await opts.api('/agent/remote-consents/'+row.consent_id,{method:'DELETE'});await load();}));section.append(revoke);}list.append(section);}
 }catch(error){if(ticket===scope&&n===counter)status.textContent=error.message;}}
 async function perform(fn){if(working)return;const ticket=scope;working=true;sync();await opts.exclusive(async()=>{try{await fn();}catch(error){if(ticket===scope)status.textContent=error.message;}});working=false;sync();}
 form.addEventListener('submit',e=>{e.preventDefault();const c=context();if(!id.value.trim())return;perform(async()=>{await opts.api('/agent/remote-consents',send('POST',{project_id:c.projectId,client_id:id.value.trim(),groups:changes.checked?['read','propose','change','study']:['read'],lifetime_s:Number(life.value)}));id.value='';await load();});});
 refresh.addEventListener('click',()=>load());sync();return {sync};
}
