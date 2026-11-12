// Presentation only: retained API values are never recomputed or attributed to an input.
const groups = ['Mass', 'Battery', 'Rotors', 'Mission', 'Geometry', 'Model settings', 'Other declarations'];
export function changeGroup(path) {
  const [root, child] = String(path).split('/').slice(1).map(token => token.replace(/~1/g, '/').replace(/~0/g, '~'));
  if (root === 'masses') return 'Mass';
  if (root === 'mission' && ['energy_system', 'reserve_policy'].includes(child)) return 'Battery';
  if (root === 'rotors') return 'Rotors';
  if (['mission', 'atmosphere'].includes(root)) return 'Mission';
  if (['assembly', 'units_and_frames'].includes(root)) return 'Geometry';
  if (['fidelity', 'mesh', 'numerics', 'boundaries', 'physics', 'symmetry', 'validation', 'postprocessing', 'domain'].includes(root)) return 'Model settings';
  return 'Other declarations';
}
export function changeLabel(path) {
  const labels = {'/masses/items':'Mass ledger', '/rotors':'Rotor declarations', '/mission/cases':'Mission cases', '/mission/contract_definition':'Mission contract', '/mission/payload_positions_body_m':'Payload positions, m', '/mission/energy_system':'Battery energy system', '/mission/reserve_policy':'Energy reserve policy', '/assembly/components':'Geometry components', '/assembly/geometry_revision_sha256':'Geometry revision', '/units_and_frames':'Units and frames', '/fidelity/local_pilot':'Local model settings'};
  return labels[path] || path;
}
export function groupChanges(changes) {
  return groups.map(name => ({name, changes: changes.filter(change => changeGroup(change.path) === name)})).filter(group => group.changes.length);
}
export function payloadDelta(report, value) {
  return report.comparable_numeric_results === true && typeof value === 'number' && Number.isFinite(value) ? value + ' kg' : 'Unavailable';
}
export function recordedValue(change, key) {
  return Object.hasOwn(change, key) ? JSON.stringify(change[key], null, 2) : 'Not present';
}
const el = (tag, text) => {const node = document.createElement(tag); if (text !== undefined) node.textContent = text; return node;};
function tableRegion(label, headings, rows) {
  const wrap = el('div'), table = el('table'), head = el('thead'), header = el('tr'), body = el('tbody');
  wrap.className = 'table-scroll'; wrap.tabIndex = 0; wrap.setAttribute('role', 'region'); wrap.setAttribute('aria-label', label + '. Scroll horizontally when needed.');
  headings.forEach(text => {const th = el('th', text); th.scope = 'col'; header.append(th);}); head.append(header);
  rows.forEach(values => {const row = el('tr'); values.forEach((value, index) => {const cell = el(index ? 'td' : 'th', String(value)); if (!index) cell.scope = 'row'; row.append(cell);}); body.append(row);});
  table.append(head, body); wrap.append(table); return wrap;
}
export function renderComparison(container, report) {
  container.replaceChildren(el('h4', 'Recorded outcomes'));
  container.append(el('p', 'These records describe frozen designs. Unsaved draft edits do not change this comparison. Changed inputs do not establish why an outcome changed.'));
  container.append(tableRegion('Retained comparison table', ['Recorded quantity', 'Before', 'After'],
    [['Outcome', 'outcome'], ['Payload lower bound, kg', 'payload_lower_bound_kg'], ['Limiting case', 'limiting_case_id'], ['Aggregate limit', 'aggregate_limit'], ['Data scope', 'data_scope'], ['Mission semantics', 'mission_semantics'], ['Engineering approval', 'engineering_approval'], ['Study SHA-256', 'study_sha256']]
      .map(([label, key]) => [label, report.before[key] ?? 'Unavailable', report.after[key] ?? 'Unavailable'])));
  container.append(el('p', 'Recorded payload change: ' + payloadDelta(report, report.payload_change_kg) + '.'));
  if (report.comparable_numeric_results !== true) container.append(el('p', 'Numeric changes withheld by the comparison API. Model, result format, data scope, mission semantics and feasible outcomes must be compatible.'));
  container.append(el('h4', 'Cases and active limits'), el('p', 'Before and after limits are recorded states. “None recorded” does not mean that no physical limits exist. Scroll tables horizontally to inspect every column.'));
  const constraints = value => Array.isArray(value) && value.length ? value.join(', ') : 'None recorded';
  const cases = report.constraint_changes || [];
  if (!cases.length) container.append(el('p', 'No per-case comparison was recorded.'));
  cases.forEach(c => {
    const section = el('section'); section.className = 'comparison-case'; section.append(el('h5', c.case_id));
    section.append(tableRegion('Case ' + c.case_id, ['Recorded quantity', 'Before', 'After'], [
      ['Outcome', c.before_outcome ?? 'Not present', c.after_outcome ?? 'Not present'],
      ['Active limits', c.before_outcome == null ? 'Not present' : constraints(c.before_active_constraints), c.after_outcome == null ? 'Not present' : constraints(c.after_active_constraints)],
    ]), el('p', 'Newly active: ' + constraints(c.newly_active) + '. No longer active: ' + constraints(c.no_longer_active) + '.'), el('p', 'Recorded case payload change: ' + payloadDelta(report, c.case_payload_change_kg) + '.'));
    container.append(section);
  });
  container.append(el('h4', 'Frozen input changes'));
  const grouped = groupChanges(report.input_changes || []);
  if (!grouped.length) container.append(el('p', 'Frozen inputs are identical.'));
  else container.append(el('p', 'Arrays are compared as complete declarations. Items are not matched or assigned individual changes. Values and paths below preserve the API record.'));
  grouped.forEach(group => {
    const section = el('section'); section.className = 'comparison-group'; section.append(el('h5', group.name + ' · ' + group.changes.length));
    group.changes.forEach(change => {
      const detail = el('details'); detail.append(el('summary', changeLabel(change.path) + ' (' + change.kind + ')'));
      detail.append(el('p', 'Recorded path: ' + change.path));
      const values = el('div'); values.className = 'comparison-values';
      for (const key of ['before', 'after']) {const column = el('div'); column.append(el('h6', key === 'before' ? 'Before' : 'After'), el('pre', recordedValue(change, key))); values.append(column);}
      detail.append(values); section.append(detail);
    }); container.append(section);
  });
  container.append(el('p', report.qualification));
  const exact = el('details'); exact.append(el('summary', 'Exact comparison JSON'), el('pre', JSON.stringify(report, null, 2))); container.append(exact);
}

// A request may only publish into the same workspace and exact selected pair.
export function createComparisonController({readContext, isContext, readSelection, fetchReport, setState, render}) {
  let serial = 0;
  function invalidate(message = 'Study selections changed. Compare again to refresh the results.') {++serial; setState('stale', message);}
  async function compare() {
    const id = ++serial, context = readContext(), pair = readSelection();
    const current = () => id === serial && isContext(context);
    setState('pending', 'Comparing the selected retained studies…');
    try {
      const report = await fetchReport(context, pair);
      if (!current()) return;
      const selected = readSelection();
      if (selected.before !== pair.before || selected.after !== pair.after) {invalidate(); return;}
      if (report.schema_version !== 'retained_study_comparison_v1' || report.before?.study_sha256 !== pair.before || report.after?.study_sha256 !== pair.after) throw new Error('Comparison identity differs from the selected studies.');
      render(report); setState('current', 'Comparison matches the selected retained studies.');
    } catch (error) {
      if (current()) setState('failed', 'Comparison unavailable: ' + error.message);
      throw error;
    }
  }
  return {invalidate, compare};
}