import {energyCaseMatches} from './mission-energy.js?v=energy-1';

// Project each retained operating point independently; never solve or certify it.
const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : null;
const rows = value => Array.isArray(value) ? value : [];
const text = value => typeof value === 'string' && value.length ? value : 'Not recorded';
const numeric = value => typeof value === 'number' && Number.isFinite(value) ? value : null;
const names = value => rows(value).filter(value => typeof value === 'string' && value.length);
const binding = report => ({study_sha256:report?.study_sha256,
  revision_sha256:report?.specification?.revision_sha256, project_id:report?.specification?.project_id});
export const trimValue = value => numeric(value) === null ? 'Unavailable' : String(value);
export const trimVector = value => Array.isArray(value) && value.length === 3
  && Array.from(value).every(item => numeric(item) !== null) ? [...value] : null;

export function trimCaseIds(report) {
  return [...new Set([...rows(report?.cases), ...rows(report?.headline_candidate_checks)]
    .map(row => row?.case_id).filter(id => typeof id === 'string' && id.length))];
}

export function trimCaseView(report, caseId, point = 'shared') {
  const result = {binding:binding(report), caseId, point, available:false};
  if (!['shared','case'].includes(point) || typeof caseId !== 'string' || !caseId.length)
    return {...result, unavailable:'Choose a case and an evidence point.'};
  const cases = rows(report?.cases).filter(row => row?.case_id === caseId);
  const matches = (point === 'shared' ? rows(report?.headline_candidate_checks) : cases)
    .filter(row => row?.case_id === caseId);
  if (matches.length !== 1 || cases.length > 1)
    return {...result, unavailable:matches.length > 1 || cases.length > 1
      ? 'Ambiguous case evidence: duplicate records are retained. Inspect exact result JSON.'
      : 'Unavailable: no record was retained for this case at the selected evidence point.'};
  const record = matches[0], candidate = object(record.candidate), policy = object(record.residual_policy);
  const interval = object(candidate?.torque_band_moment_interval_nm);
  return {...result, available:true, record, outcome:text(record.outcome), reason:text(record.reason),
    scope:text(record.scope), candidate, policy, commands:rows(candidate?.commands).map(row => ({
      id:text(row?.rotor_id), thrust:numeric(row?.thrust_n), torque:numeric(row?.shaft_torque_nm),
      rpm:numeric(row?.signed_rpm), power:numeric(row?.electrical_power_w), current:numeric(row?.dc_input_current_a),
      scope:text(row?.scope),
    })), force:trimVector(candidate?.force_residual_n), moment:trimVector(candidate?.moment_residual_cg_nm),
    active:names(record.active_constraints), activeRecorded:Array.isArray(record.active_constraints)
      && record.active_constraints.every(value => typeof value === 'string' && value.length),
    failed:names(record.failed_rotor_ids),
    interval:interval ? {lower:trimVector(interval.lower), upper:trimVector(interval.upper),
      allowance:trimVector(interval.allowance), source:text(interval.source_note)} : null};
}

const el = (tag, value) => {const node = document.createElement(tag); if (value !== undefined) node.textContent = value; return node;};
const valueList = entries => {
  const dl = el('dl'); dl.className = 'trim-totals';
  for (const [label,value] of entries) {const row = el('div'); row.append(el('dt',label),el('dd',trimValue(value))); dl.append(row);}
  return dl;
};
function table(headers, values, label, className) {
  const wrap = el('div'); wrap.className = 'table-scroll '+className; wrap.tabIndex = 0;
  wrap.setAttribute('role','region'); wrap.setAttribute('aria-label',label);
  const table = el('table'), caption = el('caption',label), head = el('thead'), body = el('tbody'), hr = el('tr');
  headers.forEach(value => {const th = el('th',value); th.scope = 'col'; hr.append(th);}); head.append(hr);
  values.forEach(values => {const row = el('tr'); values.forEach((value,index) => {
    const cell = el(index === 0 ? 'th' : 'td',value); if (index === 0) cell.scope = 'row'; row.append(cell);
  }); body.append(row);});
  table.append(caption,head,body); wrap.append(table); return wrap;
}

export function renderTrimEvidence(container, report, options = {}) {
  const section = el('section'); section.className = 'trim-evidence'; section.setAttribute('aria-label','Case trim evidence');
  section.append(el('h4','Case trim evidence'),el('p','Inspect one recorded operating point at a time. The mission-payload check and individual case candidate can have different payloads and rotor commands.'));
  const identity = binding(report), ids = trimCaseIds(report), prior = options.trimSelection;
  const same = prior && Object.keys(identity).every(key => identity[key] && prior[key] === identity[key]);
  let caseId = same && ids.includes(prior.caseId) ? prior.caseId
    : ids.includes(report.limiting_case_id) ? report.limiting_case_id : ids[0] || '';
  let point = same && ['shared','case'].includes(prior.point) ? prior.point : 'shared';
  const bound = el('p','Study '+text(identity.study_sha256)+'\nFrozen revision '+text(identity.revision_sha256));
  bound.className = 'trim-binding'; section.append(bound);
  const fields = el('div'); fields.className = 'trim-fields';
  const caseLabel = el('label','Recorded mission case'), caseSelect = el('select'); caseSelect.dataset.trimSelect = 'case';
  caseSelect.setAttribute('aria-label','Recorded mission case');
  ids.forEach(id => {const option = el('option',id); option.value = id; caseSelect.append(option);});
  if (!ids.length) {const option = el('option','No case evidence'); option.value = ''; caseSelect.append(option);}
  caseSelect.value = caseId; caseSelect.disabled = !ids.length; caseLabel.append(caseSelect);
  const pointLabel = el('label','Evidence point'), pointSelect = el('select'); pointSelect.dataset.trimSelect = 'point';
  pointSelect.setAttribute('aria-label','Evidence point');
  for (const [value,label] of [['shared','At reported mission payload'],['case','Individual case candidate']]) {
    const option = el('option',label); option.value = value; pointSelect.append(option);
  }
  pointSelect.value = point; pointSelect.disabled = !ids.length; pointLabel.append(pointSelect); fields.append(caseLabel,pointLabel);
  const status = el('p'); status.className = 'trim-status'; status.setAttribute('role','status');
  const detail = el('div'); detail.className = 'trim-detail';
  section.append(fields,status,detail); container.append(section);
  const interactive = () => section.isConnected && options.isInteractive?.() !== false;
  function draw() {
    const view = trimCaseView(report,caseId,point); detail.replaceChildren();
    if (!view.available) {status.textContent = view.unavailable; return;}
    const selected = point === 'shared' ? 'Reported-payload check' : 'Individual case candidate / bound';
    status.textContent = selected+' · '+caseId+' · recorded outcome: '+view.outcome;
    detail.append(el('p',point === 'shared' ? 'Values below come only from the retained check at the reported mission payload.'
      : 'Values below come only from the individual case candidate; they do not describe the shared mission payload.'));
    if (view.outcome !== 'feasible') detail.append(el('p','Diagnostic record: these candidate values do not establish feasible trim or a supported payload.'));
    if (view.reason !== 'Not recorded') detail.append(el('p','Recorded reason: '+view.reason));
    detail.append(el('p','Recorded scope: '+view.scope));
    detail.append(valueList([['Candidate payload, kg',view.candidate?.payload_kg],['Total mass, kg',view.candidate?.total_mass_kg],
      ['Electrical power, W',view.candidate?.electrical_power_w],['Case energy, J',view.candidate?.energy_required_j]]));
    detail.append(el('p','Recorded active constraints: '+(!view.activeRecorded ? 'Unavailable.' : view.active.length ? view.active.join(', ') : 'None recorded.')));
    if (view.failed.length) detail.append(el('p','Recorded failed rotor IDs: '+view.failed.join(', ')));
    detail.append(el('p','Scroll each evidence table horizontally to inspect every column.'));
    if (view.commands.length) {
      detail.append(table(['Rotor','Thrust, N','Shaft torque, Nm','Signed RPM','Electrical power, W','DC input current, A'],
        view.commands.map(command => [command.id,...[command.thrust,command.torque,command.rpm,command.power,command.current].map(trimValue)]),
        'Recorded rotor commands','trim-commands'));
      const scopes = el('details'); scopes.append(el('summary','Recorded rotor command scope'));
      view.commands.forEach(command => scopes.append(el('p',command.id+': '+command.scope))); detail.append(scopes);
    } else detail.append(el('p','Rotor commands unavailable. Zero commands are not inferred.'));
    detail.append(table(['Residual','X','Y','Z','Recorded tolerance'],[
      ['Force, N',...[0,1,2].map(i => trimValue(view.force?.[i])),trimValue(view.policy?.force_tolerance_n)],
      ['Moment about CG, Nm',...[0,1,2].map(i => trimValue(view.moment?.[i])),trimValue(view.policy?.moment_tolerance_nm)],
    ],'Force and moment residuals','trim-residuals'));
    detail.append(el('p','Residual components use the recorded body axes; moments are about the candidate centre of gravity. Tolerances are numerical policy, not measurement accuracy or aircraft acceptance. No pass/fail is calculated here.'),
      el('p','Recorded policy: '+text(view.policy?.qualification)));
    if (view.interval) {
      detail.append(table(['Torque-band moment, Nm','X','Y','Z'],[
        ...[['Lower',view.interval.lower],['Upper',view.interval.upper],['Allowance',view.interval.allowance]]
          .map(([label,vector]) => [label,...[0,1,2].map(i => trimValue(vector?.[i]))]),
      ],'Torque-band moment interval, Nm','trim-interval'));
      detail.append(el('p','Torque-band source: '+view.interval.source));
    }
    const button = el('button','View this frozen case in 3D'); button.type = 'button';
    button.dataset.trimCase = caseId; button.dataset.trimStudy = identity.study_sha256 || ''; button.dataset.trimRevision = identity.revision_sha256 || '';
    button.disabled = !interactive() || typeof options.onViewCase !== 'function' || !energyCaseMatches(report,identity,caseId);
    button.addEventListener('click',() => {if (interactive() && !button.disabled && energyCaseMatches(report,identity,caseId)) options.onViewCase(caseId,identity);});
    detail.append(button,el('p','The 3D case view uses the study’s shared-payload context. Selecting an individual candidate here changes only this evidence sheet.'));
    const exact = el('details'); exact.append(el('summary','Exact selected trim record'),el('pre',JSON.stringify(view.record,null,2))); detail.append(exact);
  }
  function change() {
    if (!interactive()) return;
    caseId = caseSelect.value; point = pointSelect.value;
    options.onTrimSelection?.({...identity,caseId,point}); draw();
  }
  caseSelect.addEventListener('change',change); pointSelect.addEventListener('change',change); draw();
}
