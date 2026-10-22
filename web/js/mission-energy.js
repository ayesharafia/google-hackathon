// A projection of retained evidence, not an energy calculation or acceptance check.
const numeric = value => typeof value === 'number' && Number.isFinite(value) ? value : null;
const text = value => typeof value === 'string' && value.length ? value : 'Not recorded';
export const energyValue = value => numeric(value) === null ? 'Unavailable' : String(value);
export function energyCaseMatches(report, binding, caseId) {
  return Boolean(binding?.study_sha256 && binding?.revision_sha256 && binding?.project_id
    && report?.study_sha256 === binding.study_sha256
    && report.specification?.revision_sha256 === binding.revision_sha256
    && report.specification?.project_id === binding.project_id
    && typeof caseId === 'string' && caseId.length
    && Array.isArray(report.cases) && report.cases.filter(row => row?.case_id === caseId).length === 1);
}
export function energyBudgetView(report) {
  const sequence = report?.sequence_evidence;
  if (!sequence || typeof sequence !== 'object' || Array.isArray(sequence)) return null;
  return {
    binding: {study_sha256: report.study_sha256, revision_sha256: report.specification?.revision_sha256, project_id: report.specification?.project_id},
    usable: numeric(sequence.usable_energy_j), used: numeric(sequence.total_energy_j), remaining: numeric(sequence.remaining_usable_energy_j),
    tolerance: numeric(sequence.energy_tolerance_j),
    reserve: sequence.reserve_convention === 'held_usable_energy_fraction_applied_once'
      ? 'Held reserve was applied once in the recorded budget.' : 'Reserve handling is unavailable or unrecognized. See the exact evidence.',
    integration: sequence.integration_method === 'constant_power_exact_v1'
      ? 'Recorded integration: constant power over each segment.' : 'Integration method is unavailable or unrecognized. See the exact evidence.',
    segments: (Array.isArray(sequence.segments) ? sequence.segments : []).map(segment => ({
      id: text(segment?.segment_id), caseId: typeof segment?.case_id === 'string' ? segment.case_id : null,
      duration: numeric(segment?.duration_s), power: numeric(segment?.electrical_power_w),
      energy: numeric(segment?.energy_required_j), remaining: numeric(segment?.remaining_usable_energy_j),
      source: text(segment?.source_note), profile: text(segment?.power_profile),
    })),
  };
}
const el = (tag, value) => {const node = document.createElement(tag); if (value !== undefined) node.textContent = value; return node;};
export function renderMissionEnergy(container, report, {onViewCase} = {}) {
  const section = el('section'); section.className = 'mission-energy'; section.setAttribute('aria-label', 'Mission energy budget');
  section.append(el('h4', 'Mission energy budget'));
  const view = energyBudgetView(report);
  if (!view) {
    section.append(el('p', 'Unavailable: no ordered-sequence energy evidence was retained for this study. Individual case results do not establish a shared mission budget.'));
    container.append(section); return;
  }
  section.append(el('p', 'Recorded energy for the study’s reported payload. Scenario and allowable results have separate evidence. This is not a battery state-of-charge or endurance prediction.'));
  const binding = el('p', 'Study ' + text(view.binding.study_sha256) + '\nFrozen revision ' + text(view.binding.revision_sha256)); binding.className = 'energy-binding'; section.append(binding);
  const totals = el('dl'); totals.className = 'energy-totals';
  for (const [name, value] of [['Usable budget, J', view.usable], ['Energy used, J', view.used], ['Remaining usable, J', view.remaining]]) {
    const row = el('div'); row.append(el('dt', name), el('dd', energyValue(value))); totals.append(row);
  }
  section.append(totals, el('p', view.reserve), el('p', view.integration), el('p', 'Recorded energy tolerance: ' + energyValue(view.tolerance) + ' J. Values are displayed as recorded, including small negative remaining values. No reserve is subtracted here.'));
  if (!view.segments.length) section.append(el('p', 'Segment evidence unavailable. No segment energy is inferred from the totals.'));
  else {
    section.append(el('p', 'Segments stay in recorded order. Scroll the table horizontally to inspect energy use and remaining budget.'));
    const wrap = el('div'); wrap.className = 'table-scroll'; wrap.tabIndex = 0; wrap.setAttribute('role', 'region'); wrap.setAttribute('aria-label', 'Ordered mission energy table. Scroll horizontally when needed.');
    const table = el('table'), head = el('thead'), row = el('tr'), body = el('tbody');
    ['Segment and source', 'Referenced case', 'Duration, s', 'Electrical power, W', 'Energy used, J', 'Remaining usable, J'].forEach(label => {const th = el('th', label); th.scope = 'col'; row.append(th);}); head.append(row);
    view.segments.forEach(segment => {
      const tr = el('tr'), label = el('th', segment.id); label.scope = 'row';
      const source = el('p', segment.source); source.className = 'energy-source'; label.append(source, el('p', 'Power profile: ' + segment.profile));
      const reference = el('td', text(segment.caseId));
      if (typeof onViewCase === 'function' && energyCaseMatches(report, view.binding, segment.caseId)) {
        const button = el('button', 'View case'); button.type = 'button'; button.dataset.energyCase = segment.caseId;
        button.dataset.energyStudy = view.binding.study_sha256; button.dataset.energyRevision = view.binding.revision_sha256;
        button.setAttribute('aria-label', 'View case ' + segment.caseId + ' for segment ' + segment.id);
        button.addEventListener('click', () => onViewCase(segment.caseId, view.binding)); reference.append(button);
      } else reference.append(el('p', 'Case view unavailable.'));
      tr.append(label, reference, ...[segment.duration, segment.power, segment.energy, segment.remaining].map(value => el('td', energyValue(value)))); body.append(tr);
    }); table.append(head, body); wrap.append(table); section.append(wrap);
  }
  const exact = el('details'); exact.append(el('summary', 'Exact mission energy evidence'), el('pre', JSON.stringify(report.sequence_evidence, null, 2))); section.append(exact); container.append(section);
}
