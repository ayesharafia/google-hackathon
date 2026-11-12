// Bounded presentation only. Geometry may be copied from the submitted rotor response.
export const PRESENTATION_LIMITS = Object.freeze({annuli: 8, minNonzero: 1e-12, maxMagnitude: 1e12});
const UNAVAILABLE = 'Projection unavailable: missing, malformed or outside presentation limits. Full raw response remains below.';
const NOTICE = 'Producer-reported; no independent verification. Not physical validation. Uncertainty not quantified. Formatted values use approximate IEEE754 numbers. Full raw JSON is authoritative for captured text.';
const LABELS = ['derived IDEALIZED ACTUATOR-DISK quantity from integrated annulus thrust',
  'NOT surface pressure', 'NOT a solved or CFD pressure field',
  'no spatial/vector information beyond the axisymmetric annulus',
  'full-disk mean spreads thrust over the whole disk including any inner hole',
  'active-annular mean spreads it only over the modeled annuli'];
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const need = condition => {if (!condition) throw new Error('presentation unavailable');};
function scalar(value) {
  need(typeof value === 'number' && Number.isFinite(value) &&
    (!Number.isInteger(value) || Number.isSafeInteger(value)) &&
    Math.abs(value) <= PRESENTATION_LIMITS.maxMagnitude &&
    (value === 0 || Math.abs(value) >= PRESENTATION_LIMITS.minNonzero));
  return value;
}
export function formatApprox(value) {
  scalar(value);
  if (Object.is(value, -0)) return '−0';
  return Number(value.toPrecision(5)).toString();
}
// Inspect only presentation fields; no hashes, integration, authenticity or physics checks.
export function projectDiskPressure(data) {
  try {
    need(record(data) && data.evaluation === 'polar_rotor_disk_pressure' &&
      data.schema_version === 'polar_rotor_disk_pressure_v1' && data.status === 'COMPUTED_EXPERIMENTAL' &&
      data.disk_pressure_state === 'DERIVED');
    need(typeof data.state_text === 'string' && data.state_text.length <= 2000 &&
      LABELS.every(label => data.state_text.includes(label)));
    const out = data.outputs, units = data.output_units;
    need(record(out) && record(units) && Array.isArray(out.annuli) &&
      out.annuli.length >= 1 && out.annuli.length <= PRESENTATION_LIMITS.annuli &&
      Array.isArray(units.annuli) && units.annuli.length === out.annuli.length);
    const rows = out.annuli.map((row, index) => {
      need(record(row) && Number.isSafeInteger(row.annulus_index) && row.annulus_index === index);
      const u = units.annuli[index];
      need(record(u) && u.annulus_index === 'index' && u.radial_inner_m === 'm' &&
        u.radial_outer_m === 'm' && u.disk_pressure_jump_pa === 'Pa');
      const inner = scalar(row.radial_inner_m), outer = scalar(row.radial_outer_m);
      need(0 <= inner && inner < outer);
      if (index) need(out.annuli[index - 1].radial_outer_m === inner);
      return {index, inner, outer, pressure: scalar(row.disk_pressure_jump_pa)};
    });
    need(units.rotor_mean_disk_loading_pa === 'Pa' && units.rotor_active_annular_loading_pa === 'Pa');
    return {available: true, stateText: data.state_text, rows,
      meanFull: scalar(out.rotor_mean_disk_loading_pa), meanActive: scalar(out.rotor_active_annular_loading_pa)};
  } catch {return {available: false, reason: UNAVAILABLE};}
}
export function renderDiskPressurePostpro(root, data) {
  const doc = root.ownerDocument;
  const el = (tag, text, cls) => {const node = doc.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node;};
  const card = title => {const node = el('section', undefined, 'polar-rotor-card'); node.append(el('h4', title)); root.append(node); return node;};
  root.replaceChildren(); root.hidden = false; root.className = 'polar-rotor-postpro disk-pressure-postpro';
  root.append(el('h3', 'Derived disk loading · approximate view'), el('p', NOTICE));
  const label = typeof data?.state_text === 'string' && data.state_text.length <= 2000 ? data.state_text : 'Producer state_text unavailable.';
  card('Producer label · verbatim').append(el('p', label));
  const unavailable = card('Spatial fields unavailable');
  unavailable.append(el('h5', 'Pressure contours unavailable'),
    el('p', 'No matched native spatial pressure field or mesh is supplied. Pressure contours are pending genuine field output.'),
    el('h5', 'Flow vectors unavailable'),
    el('p', 'No native velocity vector field is supplied. Flow vectors are pending genuine field output.'));
  const view = projectDiskPressure(data);
  if (!view.available) {card('Presentation unavailable').append(el('p', view.reason)); return view;}
  const loading = card('Derived idealized actuator-disk loading');
  loading.append(el('p', 'Annulus radii are copied from the submitted rotor response for display only. Indices are zero-based.'));
  const metrics = el('dl', undefined, 'polar-rotor-metrics');
  for (const [label, value] of [['Full-disk mean loading (Pa)', view.meanFull], ['Active-annular mean loading (Pa)', view.meanActive]]) {
    metrics.append(el('dt', label), el('dd', 'approx ' + formatApprox(value)));
  }
  loading.append(metrics, el('p', 'Scroll horizontally to see full table.', 'polar-rotor-scroll-cue'));
  const wrap = el('div', undefined, 'polar-rotor-table-scroll'); wrap.tabIndex = 0;
  wrap.setAttribute('role', 'region'); wrap.setAttribute('aria-label', 'Derived annulus loading. Scroll horizontally to see full table.');
  const table = el('table'); table.append(el('caption', 'Derived annular disk pressure jump · approximate values'));
  const head = el('thead'), header = el('tr');
  for (const name of ['Annulus index', 'Inner radius (m)', 'Outer radius (m)', 'Derived Δp (Pa)']) {
    const cell = el('th', name); cell.setAttribute('scope', 'col'); header.append(cell);
  }
  head.append(header); table.append(head);
  const body = el('tbody');
  for (const row of view.rows) {
    const line = el('tr'); line.append(el('td', String(row.index)));
    for (const value of [row.inner, row.outer, row.pressure]) line.append(el('td', 'approx ' + formatApprox(value)));
    body.append(line);
  }
  table.append(body); wrap.append(table); loading.append(wrap);
  return view;
}
