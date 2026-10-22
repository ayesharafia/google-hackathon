import {renderMissionEnergy} from './mission-energy.js?v=energy-1';
const el=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
export function renderStudy(container,report,isCurrent,options={}){
  container.replaceChildren();
  const status=el('p',isCurrent?'Study applies to this saved revision.':'Retained study belongs to an earlier revision. Re-freeze and evaluate the edited design.');status.className='study-binding';container.append(status);
  container.append(el('p',report.data_scope==='analytic_fixture'?'ILLUSTRATIVE INPUTS: analytic software fixture. No client aircraft performance claim.':'Client inputs remain unvalidated; engineering approval pending.'));
  if(!['local_mission_capacity_v3','local_mission_capacity_v4'].includes(report.schema_version))container.append(el('p','Historical local record: earlier acceptance semantics, preserved as recorded. Re-evaluate a frozen design for current evidence.'));
  if(report.payload_lower_bound_kg!==null){const value=el('p',(Math.floor(report.payload_lower_bound_kg*100)/100).toFixed(2)+' kg');value.className='payload-value';container.append(value,el('p','Supported payload lower bound within the declared model. Display rounded down; exact value retained below.'),el('p',report.aggregate_limit?'Aggregate limit: '+report.aggregate_limit:'Limiting case: '+report.limiting_case_id));}
  else container.append(el('h4','Payload unavailable: '+report.outcome),...report.reasons.map(reason=>el('p',reason)));
  const table=el('table'),head=el('thead'),row=el('tr');['Case','Required','Outcome','Feasible bound, kg','Binding limits'].forEach(text=>row.append(el('th',text)));head.append(row);const body=el('tbody');
  report.cases.forEach(c=>{const tr=el('tr');[c.case_id,c.required?'Yes':'No',c.outcome,c.outcome==='feasible'?(c.candidate?.payload_kg??'Unavailable'):'Unavailable',c.active_constraints?.join(', ')||c.reason||'None identified'].forEach(v=>tr.append(el('td',String(v))));body.append(tr);});table.append(head,body);const wrap=el('div');wrap.className='table-scroll';wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label','Case capacity table. Scroll horizontally when needed.');wrap.append(table);container.append(el('p','Scroll the table horizontally to inspect every column.'),wrap);
  (report.headline_candidate_checks||[]).forEach(c=>{const detail=el('details');detail.append(el('summary','Shared payload trim: '+c.case_id),el('pre',JSON.stringify(c,null,2)));container.append(detail);});
  renderMissionEnergy(container,report,options);
  if(report.conditioning_sources&&Object.keys(report.conditioning_sources).length){container.append(el('h4','Conditioned source policy'));Object.values(report.conditioning_sources).forEach(source=>{container.append(el('p','Hull shift '+source.power_shift_w+' W; torque interval ±'+source.torque_error_bound_nm+' Nm. '+source.qualification));});}
  if(report.scenario_analysis){const a=report.scenario_analysis;container.append(el('h4','Deterministic scenario envelope'),el('p','Status: '+a.status+' · supported payload: '+(a.supported_payload_kg??'Unavailable')+' kg.'),el('p',a.qualification));a.scenarios.forEach(s=>container.append(el('p',s.scenario_id+': '+s.result.outcome+' · '+(s.result.payload_lower_bound_kg??'Unavailable')+' kg. '+s.correlation_note)));}
  if(report.external_allowables){const a=report.external_allowables;container.append(el('h4','Declared external payload caps'),el('p','Status: '+a.status+' · declared approved cap: '+(a.declared_approved_cap_kg??'Unavailable')+' kg · checked capped payload: '+(a.feasible_capped_payload_kg??'Unavailable')+' kg.'),el('p',a.qualification));}
  container.append(el('p',report.qualification),el('p','Frozen revision '+report.specification.revision_sha256));
  const detail=el('details');detail.append(el('summary','Exact result, sources and residual evidence'),el('pre',JSON.stringify(report,null,2)));container.append(detail);
}

export {renderComparison} from './design-comparison.js?v=comparison-1';
