// Read-only, bounded presentation of current V136 output. No solver or integration.
export const PRESENTATION_LIMITS = Object.freeze({annuli: 8, evaluationsPerSection: 16, minNonzero: 1e-12, maxMagnitude: 1e12});
const STATES = ['CONVERGED', 'NOT_RUN_OUT_OF_POLAR_DOMAIN', 'NOT_BRACKETED', 'EVALUATION_BUDGET_EXHAUSTED', 'FLOAT_STAGNATION'];
const UNAVAILABLE = 'Projection unavailable: missing, malformed or outside presentation limits. Full raw response remains below.';
const NOTICE = 'Producer-reported; no independent verification. Not physical validation. Uncertainty not quantified. Browser plots and formatted values use approximate IEEE754 numbers. Full raw JSON is authoritative for captured text.';
const record = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const need = condition => {if (!condition) throw new Error('presentation unavailable');};
function scalar(v) {
  need(typeof v === 'number' && Number.isFinite(v) && (!Number.isInteger(v) || Number.isSafeInteger(v)) &&
    Math.abs(v) <= PRESENTATION_LIMITS.maxMagnitude && (v === 0 || Math.abs(v) >= PRESENTATION_LIMITS.minNonzero));
  return v;
}
function index(v, max) {need(Number.isSafeInteger(v) && v >= 0 && v < max); return v;}
function array(v, min, max) {need(Array.isArray(v) && v.length >= min && v.length <= max); return v;}
function units(v, expected) {need(record(v)); for (const [key, unit] of Object.entries(expected)) need(v[key] === unit);}
const ANNULUS_UNITS = {annulus_index: 'index', radial_inner_m: 'm', radial_outer_m: 'm', midpoint_radius_m: 'm', radial_width_m: 'm'};
const CONTRIBUTION_UNITS = {annulus_index: 'index', selected_evaluation_index: 'index', thrust_density_n_m: 'N/m', torque_density_nm_m: 'N*m/m', radial_width_m: 'm', thrust_n: 'N', torque_nm: 'N*m'};
const TOTAL_UNITS = {thrust_n: 'N', torque_nm: 'N*m', shaft_power_w: 'W'};
// Checks only the fields used by the view. No hashes, whole-result/schema guard,
// residual replay, integration arithmetic, source authenticity or physics checks.
export function projectPolarRotor(data) {
  try {
    need(record(data) && data.evaluation === 'polar_rotor_experimental' && data.schema_version === 'polar_rotor_v1' && data.status === 'COMPUTED_EXPERIMENTAL');
    const out = data.outputs, u = data.output_units;
    need(record(out) && record(u) && u.rotor_state === 'label');
    const annuli = array(out.annuli, 1, 8), annulusUnits = array(u.annuli, annuli.length, annuli.length);
    need(data.section_solve_result_count === annuli.length);
    let evaluations = 0;
    const rows = annuli.map((row, i) => {
      need(record(row)); need(index(row.annulus_index, annuli.length) === i);
      units(annulusUnits[i], ANNULUS_UNITS);
      const inner = scalar(row.radial_inner_m), outer = scalar(row.radial_outer_m), radius = scalar(row.midpoint_radius_m), width = scalar(row.radial_width_m);
      need(0 < inner && inner < radius && radius < outer && width > 0);
      if (i) need(annuli[i - 1].radial_outer_m === inner);
      const child = row.solve_result, c = child?.outputs, cu = child?.output_units;
      need(record(child) && child.status === 'COMPUTED_EXPERIMENTAL' && record(c) && record(cu));
      need(STATES.includes(c.solve_state) && cu.solve_state === 'label');
      const trace = array(c.evaluations, 1, 16);
      need(child.residual_result_count === trace.length && child.load_result_count === trace.length && child.lookup_result_count === trace.length);
      evaluations += trace.length;
      let selected = null, psi = null, residual = null;
      if (c.solve_state === 'CONVERGED') {
        need(record(c.solution)); units(cu.solution, {evaluation_index: 'index', psi_rad: 'rad', residual_m2_s: 'm^2/s'});
        selected = index(c.solution.evaluation_index, trace.length);
        psi = scalar(c.solution.psi_rad); residual = scalar(c.solution.residual_m2_s);
        const actual = trace[selected];
        need(record(actual) && actual.psi_rad === psi && actual.result?.outputs?.residual_m2_s === residual);
      } else {need(c.solution === null && cu.solution === 'not_applicable');}
      return {index: i, inner, outer, radius, width, state: c.solve_state, evaluations: trace.length, selected, psi, residual};
    });
    for (const key of ['residual_result_count', 'load_result_count', 'lookup_result_count']) need(data[key] === evaluations);
    const allConverged = rows.every(row => row.state === 'CONVERGED');
    need(out.rotor_state === (allConverged ? 'COMPUTED' : 'NOT_RUN_SECTION_NOT_CONVERGED'));
    let totals = null, loads = null;
    if (allConverged) {
      const integrated = out.integrated, iu = u.integrated;
      need(record(integrated) && record(iu) && integrated.integration_method === 'MIDPOINT_PRESCRIBED_ANNULI' && iu.integration_method === 'label');
      const contributions = array(integrated.contributions, rows.length, rows.length);
      const contributionUnits = array(iu.contributions, rows.length, rows.length);
      units(iu.totals, TOTAL_UNITS); need(record(integrated.totals));
      totals = Object.fromEntries(Object.keys(TOTAL_UNITS).map(key => [key, scalar(integrated.totals[key])]));
      loads = contributions.map((c, i) => {
        need(record(c)); units(contributionUnits[i], CONTRIBUTION_UNITS);
        need(index(c.annulus_index, rows.length) === i && index(c.selected_evaluation_index, rows[i].evaluations) === rows[i].selected);
        need(scalar(c.radial_width_m) === rows[i].width);
        // Display actual integrated contributions, never integrate or infer missing loads.
        return {radius: rows[i].radius, thrust: scalar(c.thrust_density_n_m), torque: scalar(c.torque_density_nm_m), thrustContribution: scalar(c.thrust_n), torqueContribution: scalar(c.torque_nm)};
      });
    } else {need(out.integrated === null && u.integrated === 'not_applicable');}
    return {available: true, rotorState: out.rotor_state, rows, totals, loads};
  } catch {return {available: false, reason: UNAVAILABLE};}
}
export function formatApprox(value) {
  scalar(value);
  if (Object.is(value, -0)) return '−0';
  return Number(value.toPrecision(5)).toString();
}
// Padded data extent, without forcing zero into positive/negative data. No area fill.
export function plotBounds(values) {
  array(values, 1, 8); values.forEach(scalar);
  const min = Math.min(...values), max = Math.max(...values);
  const pad = min === max ? (min === 0 ? 1 : Math.abs(min) * 0.1) : (max - min) * 0.1;
  const bounds = [min - pad, max + pad];
  need(bounds.every(Number.isFinite) && bounds[0] < bounds[1]);
  return bounds;
}
function tick(value) {return value === 0 ? '0' : value.toExponential(2);}
export function renderPolarRotorPostpro(root, data) {
  const doc = root.ownerDocument;
  const el = (tag, text, cls) => {const n = doc.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n;};
  const card = title => {const n = el('section', undefined, 'polar-rotor-card'); n.append(el('h4', title)); root.append(n); return n;};
  root.replaceChildren(); root.hidden = false; root.className = 'polar-rotor-postpro';
  root.append(el('h3', 'Rotor results · approximate visual view'), el('p', NOTICE));
  card('Pressure contours unavailable').append(el('p', 'The section-load rotor model supplies no matched native spatial pressure field or mesh. Pressure contours are pending genuine rotor field output.'));
  card('Flow vectors unavailable').append(el('p', 'The section-load rotor model supplies no matched native spatial velocity vector field or mesh. Flow vectors and velocity contours are pending genuine rotor field output.'),
    el('p', 'The separate stationary sphere pressure/velocity path does not supply rotor fields. No illustrative or interpolated CFD fields are shown.'));
  const view = projectPolarRotor(data);
  if (!view.available) {card('Presentation unavailable').append(el('p', view.reason)); return view;}
  const summary = card('Producer-reported integrated loads');
  summary.append(el('p', 'rotor_state: ' + view.rotorState));
  if (view.totals) {
    const metrics = el('dl', undefined, 'polar-rotor-metrics');
    for (const [key, label] of [['thrust_n', 'Thrust T (N)'], ['torque_nm', 'Torque Q (N·m)'], ['shaft_power_w', 'Shaft power P (W)']]) metrics.append(el('dt', label), el('dd', '≈ ' + formatApprox(view.totals[key])));
    summary.append(metrics);
  } else summary.append(el('p', 'Integrated T/Q/P unavailable: at least one producer section did not converge. No partial integration or zero totals are shown.'));
  function table(parent, caption, headings, records) {
    parent.append(el('p', 'Scroll horizontally to see full table.', 'polar-rotor-scroll-cue'));
    const wrap = el('div', undefined, 'polar-rotor-table-scroll'); wrap.tabIndex = 0; wrap.setAttribute('role', 'region'); wrap.setAttribute('aria-label', caption + '. Scroll horizontally to see full table.');
    const t = el('table'); t.append(el('caption', caption));
    const head = el('thead'), tr = el('tr');
    for (const name of headings) {const th = el('th', name); th.setAttribute('scope', 'col'); tr.append(th);} head.append(tr); t.append(head);
    const body = el('tbody');
    for (const values of records) {const row = el('tr'); for (const v of values) row.append(el('td', v)); body.append(row);} t.append(body); wrap.append(t); parent.append(wrap);
  }
  const state = card('Producer solve states and selected residuals');
  state.append(el('p', 'Indices are zero-based. Selected values appear only for producer-converged sections. Residuals are circulation closure values, not error or uncertainty estimates.'));
  table(state, 'Per-annulus producer solve information', ['Annulus index', 'Midpoint (m)', 'Solve state', 'Evaluations (count)', 'Selected index', 'Selected ψ (rad)', 'Selected residual (m²/s)'], view.rows.map(r => [String(r.index), formatApprox(r.radius), r.state, String(r.evaluations), r.selected === null ? 'unavailable' : String(r.selected), r.psi === null ? 'unavailable' : formatApprox(r.psi), r.residual === null ? 'unavailable' : formatApprox(r.residual)]));
  if (!view.loads) return view;
  function chart(title, key, unit) {
    const parent = card(title);
    parent.className += ' polar-rotor-chart';
    parent.append(el('p', 'Discrete producer contribution densities at annulus midpoints. No smoothing, field interpolation or origin fill.'));
    const ns = 'http://www.w3.org/2000/svg';
    const svgNode = (tag, attrs = {}, text) => {const n = doc.createElementNS(ns, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v)); if (text !== undefined) n.textContent = text; return n;};
    const svg = svgNode('svg', {viewBox: '0 0 600 300', role: 'img', 'aria-label': title + '. Discrete midpoint samples; numeric data table follows.'});
    svg.append(svgNode('title', {}, title), svgNode('desc', {}, 'Approximate producer values. Horizontal axis: midpoint radius in metres. Vertical axis: ' + unit + '. See the following table.'));
    const [xmin, xmax] = plotBounds(view.loads.map(r => r.radius)), [ymin, ymax] = plotBounds(view.loads.map(r => r[key]));
    const x = v => 112 + (v - xmin) / (xmax - xmin) * 456, y = v => 230 - (v - ymin) / (ymax - ymin) * 198;
    svg.append(svgNode('line', {x1: 112, x2: 568, y1: 230, y2: 230, stroke: '#526578'}), svgNode('line', {x1: 112, x2: 112, y1: 32, y2: 230, stroke: '#526578'}));
    for (const v of [ymin, (ymin + ymax) / 2, ymax]) {
      svg.append(svgNode('line', {x1: 112, x2: 568, y1: y(v), y2: y(v), stroke: '#d6dfe6'}), svgNode('text', {x: 102, y: y(v) + 4, 'text-anchor': 'end'}, tick(v)));
    }
    for (const v of [xmin, (xmin + xmax) / 2, xmax]) svg.append(svgNode('text', {x: x(v), y: 252, 'text-anchor': v === xmin ? 'start' : v === xmax ? 'end' : 'middle'}, tick(v)));
    svg.append(svgNode('text', {x: 112, y: 18}, unit), svgNode('text', {x: 340, y: 282, 'text-anchor': 'middle'}, 'Midpoint radius (m)'));
    for (const r of view.loads) svg.append(svgNode('circle', {cx: x(r.radius), cy: y(r[key]), r: 4, fill: '#175d91'}));
    const wrap = el('div', undefined, 'polar-rotor-chart-scroll'); wrap.tabIndex = 0;
    wrap.setAttribute('role', 'region'); wrap.setAttribute('aria-label', title + ' chart. Scroll horizontally to see full chart.');
    wrap.append(svg);
    parent.append(el('p', 'Scroll horizontally to see full chart.', 'polar-rotor-scroll-cue'), wrap);
  }
  chart('Thrust density (N/m)', 'thrust', 'N/m');
  chart('Torque density (N·m/m)', 'torque', 'N·m/m');
  const fallback = card('Annular contribution data · approximate values');
  table(fallback, 'Producer integrated contributions; accessible fallback for both charts', ['Annulus index', 'Midpoint (m)', 'Width (m)', 'Thrust density (N/m)', 'Torque density (N·m/m)', 'Thrust contribution (N)', 'Torque contribution (N·m)'], view.loads.map((r, i) => [String(i), formatApprox(r.radius), formatApprox(view.rows[i].width), formatApprox(r.thrust), formatApprox(r.torque), formatApprox(r.thrustContribution), formatApprox(r.torqueContribution)]));
  return view;
}
