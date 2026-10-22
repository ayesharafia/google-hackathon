import test from 'node:test';
import assert from 'node:assert/strict';
import {issueDestination, readinessRows} from '../../web/js/engineering-readiness.js';

const complete = () => ({
  draft_version: 3,
  mass: {complete: true, missing: [], errors: []},
  pack: {status: 'consistent'},
  hover_readiness: {eligible: true, blocking: [], cases: [{case_id: 'hover', eligible: true, blocking: []}]},
});

test('uninspected state never presents a passing input check', () => {
  const rows = readinessRows(null);
  assert.deepEqual(rows.slice(0, 3).map(row => row.state), ['Not inspected', 'Not inspected', 'Not inspected']);
  assert.equal(rows[3].state, 'Not assessed');
  assert.equal(rows[4].state, 'Pending qualified review');
});

test('eligible inputs never promote source evidence or qualified approval', () => {
  const report = complete();
  const rows = readinessRows(report);
  assert.equal(rows[0].state, 'Inputs complete');
  assert.equal(rows[1].state, 'Declarations consistent');
  assert.equal(rows[2].state, 'Required inputs eligible');
  assert.equal(rows[3].state, 'Not assessed');
  assert.equal(rows[4].state, 'Pending qualified review');
  assert.equal('payload_kg' in rows[2], false);
});

test('mass missing fields and errors remain separately visible', () => {
  const report = complete();
  report.mass = {complete: false, missing: ['masses.energy'], errors: ['mass must be >= 0']};
  const row = readinessRows(report)[0];
  assert.equal(row.state, 'Needs attention');
  assert.deepEqual(row.issues, ['masses.energy', 'mass must be >= 0']);
  report.mass.complete = true;
  assert.equal(readinessRows(report)[0].state, 'Needs attention');
});

test('pack disagreement differs from incomplete and unassessed inputs', () => {
  const report = complete();
  report.pack = {status: 'inconsistent'};
  assert.equal(readinessRows(report)[1].state, 'Values disagree');
  assert.match(readinessRows(report)[1].issues[0], /usable energy/);
  report.pack = {status: 'inputs_incomplete', detail: 'select energy-category battery mass items'};
  assert.equal(readinessRows(report)[1].state, 'Missing or invalid inputs');
  assert.equal(readinessRows(report)[1].issues[0], report.pack.detail);
  report.pack = {status: 'future_contract'};
  assert.equal(readinessRows(report)[1].state, 'Not assessed');
});

test('an ineligible optional case is not hidden by aggregate required eligibility', () => {
  const report = complete();
  report.hover_readiness.cases.push({case_id: 'optional', eligible: false, blocking: ['map outside coverage']});
  const row = readinessRows(report)[2];
  assert.equal(row.state, 'Required inputs eligible');
  assert.deepEqual(row.cases[1].blocking, ['map outside coverage']);
});

test('separate supplied-point screening state cannot overwrite model eligibility', () => {
  const report = complete();
  report.screening_readiness = {ready: false, blocking: ['rotors[0].model']};
  assert.equal(readinessRows(report)[2].state, 'Required inputs eligible');
  report.hover_readiness.eligible = false;
  report.screening_readiness.ready = true;
  assert.equal(readinessRows(report)[2].state, 'Not eligible');
});

test('partial reports preserve unknown input states instead of false conclusions', () => {
  const rows = readinessRows({mass: {}, pack: {}, hover_readiness: {}});
  assert.equal(rows[0].state, 'Not inspected');
  assert.equal(rows[1].state, 'Not assessed');
  assert.equal(rows[2].state, 'Not inspected');
});

test('diagnostic text is retained as data and does not mutate the report', () => {
  const report = complete();
  report.hover_readiness.blocking = ['<img src=x onerror=alert(1)>', {field: 'unknown'}];
  const original = JSON.stringify(report);
  const rows = readinessRows(report);
  assert.equal(rows[2].issues[0], '<img src=x onerror=alert(1)>');
  assert.equal(rows[2].issues[1], '{"field":"unknown"}');
  assert.equal(JSON.stringify(report), original);
});

for (const [reason, destination] of [
  ['masses.energy: missing', 'mass'], ['payload position required', 'mass'],
  ['pack consistency', 'battery'], ['nominal bus voltage', 'battery'],
  ['map RPM coverage', 'rotors'], ['rotor current limit', 'rotors'],
  ['sequence segment duration', 'sequence'], ['local_pilot.model_version', 'model'],
  ['payload domain reversed', 'model'], ['atmosphere source', 'cases'],
  ['angular acceleration outside case', 'cases'], ['unfamiliar backend diagnostic', 'json'],
]) test(`action routes ${reason} to ${destination}`, () => assert.equal(issueDestination(reason), destination));
