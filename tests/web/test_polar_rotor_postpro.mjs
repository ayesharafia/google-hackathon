// Synthetic presentation unit tests only; no browser, API or science evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import {projectPolarRotor, formatApprox, plotBounds, renderPolarRotorPostpro} from '../../web/js/polar-rotor-postpro.js';

test('invalid projection input is refused', () => {
  for (const input of [undefined, null, [], {}, {outputs: {}}, 'CONVERGED']) {
    const view = projectPolarRotor(input);
    assert.equal(view.available, false);
    assert.match(view.reason, /Projection unavailable/);
  }
});

test('unsafe integer formatting is refused', () => {
  assert.throws(() => formatApprox(Number.MAX_SAFE_INTEGER + 1));
});

test('constant and signed bounds contain samples without forcing origin', () => {
  for (const values of [[0], [4, 4], [-4, -4], [-3, 0, 5]]) {
    const [min, max] = plotBounds(values);
    assert.ok(Number.isFinite(min) && Number.isFinite(max) && min < max);
    assert.ok(values.every(value => min < value && value < max));
  }
  assert.ok(plotBounds([4, 4])[0] > 0);
  assert.ok(plotBounds([-4, -4])[1] < 0);
});

import {readFileSync} from 'node:fs';
import {join} from 'node:path';
// Invented, incomplete projection-shape data only. No retained scientific receipt.
function syntheticProjection(state = 'CONVERGED') {
  const converged = state === 'CONVERGED';
  const selected = {evaluation_index: 0, psi_rad: 0.5, residual_m2_s: 0.001};
  const solutionUnits = {evaluation_index: 'index', psi_rad: 'rad', residual_m2_s: 'm^2/s'};
  const child = {status: 'COMPUTED_EXPERIMENTAL', residual_result_count: 1, load_result_count: 1, lookup_result_count: 1,
    outputs: {solve_state: state, solution: converged ? selected : null, evaluations: [{psi_rad: 0.5, result: {outputs: {residual_m2_s: 0.001}}}]},
    output_units: {solve_state: 'label', solution: converged ? solutionUnits : 'not_applicable'}};
  const contribution = {annulus_index: 0, selected_evaluation_index: 0, radial_width_m: 0.4, thrust_density_n_m: 5, torque_density_nm_m: -2, thrust_n: 2, torque_nm: -0.8};
  const contributionUnits = {annulus_index: 'index', selected_evaluation_index: 'index', radial_width_m: 'm', thrust_density_n_m: 'N/m', torque_density_nm_m: 'N*m/m', thrust_n: 'N', torque_nm: 'N*m'};
  return {evaluation: 'polar_rotor_experimental', schema_version: 'polar_rotor_v1', status: 'COMPUTED_EXPERIMENTAL',
    section_solve_result_count: 1, residual_result_count: 1, load_result_count: 1, lookup_result_count: 1,
    outputs: {rotor_state: converged ? 'COMPUTED' : 'NOT_RUN_SECTION_NOT_CONVERGED',
      annuli: [{annulus_index: 0, radial_inner_m: 0.2, radial_outer_m: 0.6, midpoint_radius_m: 0.4, radial_width_m: 0.4, solve_result: child}],
      integrated: converged ? {integration_method: 'MIDPOINT_PRESCRIBED_ANNULI', contributions: [contribution], totals: {thrust_n: 2, torque_nm: -0.8, shaft_power_w: -40}} : null},
    output_units: {rotor_state: 'label', annuli: [{annulus_index: 'index', radial_inner_m: 'm', radial_outer_m: 'm', midpoint_radius_m: 'm', radial_width_m: 'm'}],
      integrated: converged ? {integration_method: 'label', contributions: [contributionUnits], totals: {thrust_n: 'N', torque_nm: 'N*m', shaft_power_w: 'W'}} : 'not_applicable'}};
}
test('synthetic native paths and units project totals and preserve nonconverged nulls', () => {
  const computed = projectPolarRotor(syntheticProjection());
  assert.equal(computed.available, true); assert.equal(computed.totals.thrust_n, 2); assert.equal(computed.loads[0].torque, -2);
  for (const state of ['NOT_RUN_OUT_OF_POLAR_DOMAIN', 'NOT_BRACKETED', 'EVALUATION_BUDGET_EXHAUSTED', 'FLOAT_STAGNATION']) {
    const view = projectPolarRotor(syntheticProjection(state));
    assert.equal(view.available, true); assert.equal(view.totals, null); assert.equal(view.loads, null); assert.equal(view.rows[0].residual, null);
  }
});
test('synthetic malformed units, counts, indices and out-of-range scalars are refused', () => {
  for (const mutate of [v => v.output_units.integrated.totals.torque_nm = 'N', v => v.section_solve_result_count = '1',
    v => v.residual_result_count = 2, v => v.outputs.annuli[0].annulus_index = '0',
    v => v.outputs.integrated.totals.thrust_n = 1e13, v => v.outputs.integrated.contributions[0].torque_density_nm_m = 1e-13]) {
    const data = syntheticProjection(); mutate(data); assert.equal(projectPolarRotor(data).available, false);
  }
});
test('optional owner producer fixtures match presentation outcomes only', {skip: !process.env.POLAR_ROTOR_AUDIT_DIR}, () => {
  for (const name of ['computed', 'ood', 'budget', 'nonbracket']) {
    const data = JSON.parse(readFileSync(join(process.env.POLAR_ROTOR_AUDIT_DIR, name + '.json'), 'utf8'));
    const view = projectPolarRotor(data);
    assert.equal(view.available, name !== 'ood', name);
    if (name === 'computed') assert.deepEqual(view.totals, data.outputs.integrated.totals);
    if (name === 'budget' || name === 'nonbracket') assert.equal(view.totals, null);
  }
});

test('chart and table scrolling retains focusable wrappers, readable sizing and visible cues', () => {
  // Synthetic DOM structure/CSS regression check only, not a layout or browser audit.
  const nodes = [];
  const doc = {createElement(tag) {
    const n = {tag, ownerDocument: doc, children: [], attrs: {}, textContent: '',
      append(...children) {this.children.push(...children);},
      replaceChildren(...children) {this.children = children;},
      setAttribute(key, value) {this.attrs[key] = String(value);},
      set innerHTML(_) {throw new Error('Unsafe HTML sink');}};
    nodes.push(n); return n;
  }, createElementNS(ns, tag) {
    assert.equal(ns, 'http://www.w3.org/2000/svg'); return this.createElement(tag);
  }};
  const root = doc.createElement('div');
  assert.equal(renderPolarRotorPostpro(root, syntheticProjection()).available, true);
  for (const [kind, tag] of [['chart', 'svg'], ['table', 'table']]) {
    const wrappers = nodes.filter(n => n.className === 'polar-rotor-' + kind + '-scroll');
    assert.equal(wrappers.length, 2);
    for (const wrap of wrappers) {
      assert.equal(wrap.tabIndex, 0); assert.equal(wrap.attrs.role, 'region');
      assert.ok(wrap.attrs['aria-label'].includes('Scroll horizontally to see full ' + kind));
      assert.equal(wrap.children.length, 1); assert.equal(wrap.children[0].tag, tag);
      const parent = nodes.find(n => n.children.includes(wrap));
      const cue = parent.children[parent.children.indexOf(wrap) - 1];
      assert.equal(cue.textContent, 'Scroll horizontally to see full ' + kind + '.');
    }
  }
  const css = readFileSync(new URL('../../web/css/polar-rotor.css', import.meta.url), 'utf8');
  const rule = selector => css.slice(css.indexOf(selector)).split('{')[1].split('}')[0];
  assert.match(rule('.polar-rotor-card svg'), /width: 600px;/);
  assert.match(rule('.polar-rotor-card svg'), /min-width: 600px;/);
  assert.match(rule('.polar-rotor-card svg'), /max-width: none;/);
  assert.match(rule('.polar-rotor-card svg'), /font: 13px/);
  for (const selector of ['.polar-rotor-chart-scroll', '.polar-rotor-table-scroll']) {
    assert.match(rule(selector), /min-width: 0;/); assert.match(rule(selector), /max-width: 100%;/);
    assert.match(rule(selector), /overflow-x: auto;/);
  }
  assert.match(rule('.polar-rotor-card table'), /min-width: 52rem;/);
  assert.match(rule('.polar-rotor-postpro'), /grid-column: 1 \/ -1;/);
});
