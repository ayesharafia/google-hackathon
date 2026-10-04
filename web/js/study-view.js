const el=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
export function renderStudy(container,report,isCurrent){
  container.replaceChildren();
  const status=el('p',isCurrent?'Study applies to this saved revision.':'Retained study belongs to an earlier revision. Re-freeze and evaluate the edited design.');status.className='study-binding';container.append(status);
  container.append(el('p',report.data_scope==='analytic_fixture'?'ILLUSTRATIVE INPUTS: analytic software fixture. No client aircraft performance claim.':'Client inputs remain unvalidated; engineering approval pending.'));
  if(report.payload_lower_bound_kg!==null){const value=el('p',(Math.floor(report.payload_lower_bound_kg*100)/100).toFixed(2)+' kg');value.className='payload-value';container.append(value,el('p','Supported payload lower bound within the declared model. Display rounded down; exact value retained below.'),el('p',report.aggregate_limit?'Aggregate limit: '+report.aggregate_limit:'Limiting case: '+report.limiting_case_id));}
  else container.append(el('h4','Payload unavailable: '+report.outcome),...report.reasons.map(reason=>el('p',reason)));
  const table=el('table'),head=el('thead'),row=el('tr');['Case','Required','Outcome','Feasible bound, kg','Binding limits'].forEach(text=>row.append(el('th',text)));head.append(row);const body=el('tbody');
  report.cases.forEach(c=>{const tr=el('tr');[c.case_id,c.required?'Yes':'No',c.outcome,c.candidate?.payload_kg??'Unavailable',c.active_constraints?.join(', ')||c.reason||'None identified'].forEach(v=>tr.append(el('td',String(v))));body.append(tr);});table.append(head,body);const wrap=el('div');wrap.className='table-scroll';wrap.append(table);container.append(wrap);
  (report.headline_candidate_checks||[]).forEach(c=>{const detail=el('details');detail.append(el('summary','Shared payload trim: '+c.case_id),el('pre',JSON.stringify(c,null,2)));container.append(detail);});
  if(report.sequence_evidence){const seq=report.sequence_evidence;container.append(el('h4','Chronological fixed-pack energy'),el('p',seq.total_energy_j+' J used from '+seq.usable_energy_j+' J after reserve.'));seq.segments.forEach(s=>container.append(el('p',s.segment_id+': '+s.duration_s+' s · '+s.electrical_power_w+' W · '+s.remaining_usable_energy_j+' J remaining.')));}
  container.append(el('p',report.qualification),el('p','Frozen revision '+report.specification.revision_sha256));
  const detail=el('details');detail.append(el('summary','Exact result, sources and residual evidence'),el('pre',JSON.stringify(report,null,2)));container.append(detail);
}
