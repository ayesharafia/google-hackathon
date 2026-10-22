import test from 'node:test';
import assert from 'node:assert/strict';
import {sourceBindingCandidates, bindImportedSource} from '../../web/js/rotor-source-binding.js';

const receipt = () => ({source_sha256: 'a'.repeat(64), dataset: {dataset_id: 'measured-table', configuration_id: 'motor-prop-A', source_kind: 'measured'}});
const snapshot = () => ({rotors: [
  {rotor_id: 'r0', configuration_id: 'motor-prop-A', map_ref: 'old0', pitch_deg: 0, sustained_limits: {max_rpm: 1000}},
  {rotor_id: 'r1', configuration_id: 'motor-prop-A', map_ref: 'old1'},
  {rotor_id: 'other', configuration_id: 'motor-prop-B', map_ref: 'old2'},
], mission: {cases: [{name: 'hover', performance_source_by_rotor: {r0: 'case-override'}}]}});

test('candidate list exposes matching and mismatched configurations without selecting anything', () => {
  const data = snapshot();
  assert.deepEqual(sourceBindingCandidates(data, receipt()).map(r => r.matches), [true, true, false]);
  assert.equal(data.rotors[0].map_ref, 'old0');
});

test('binding changes only explicitly selected base-map references', () => {
  const data = snapshot(), original = JSON.stringify(data);
  const next = bindImportedSource(data, receipt(), ['r1'], original);
  assert.equal(JSON.stringify(data), original);
  assert.equal(next.rotors[0].map_ref, 'old0');
  assert.equal(next.rotors[1].map_ref, 'a'.repeat(64));
  assert.equal(next.rotors[2].map_ref, 'old2');
  assert.deepEqual(next.mission, data.mission);
  assert.deepEqual(next.rotors[0].sustained_limits, data.rotors[0].sustained_limits);
});

test('binding multiple matching rotors retains source kind as metadata, without adding approval', () => {
  const data = snapshot();
  const next = bindImportedSource(data, receipt(), ['r0', 'r1'], JSON.stringify(data));
  assert.equal(next.rotors[0].map_ref, next.rotors[1].map_ref);
  assert.equal('engineering_approval' in next, false);
  assert.equal('source_kind' in next.rotors[0], false);
});

for (const ids of [[], ['r0', 'r0'], ['missing'], ['other'], ['r0', 'other']]) {
  test(`invalid selection ${JSON.stringify(ids)} refuses atomically`, () => {
    const data = snapshot(), original = JSON.stringify(data);
    assert.throws(() => bindImportedSource(data, receipt(), ids, original), /Select|Selected rotor/);
    assert.equal(JSON.stringify(data), original);
  });
}

test('any draft edit invalidates the preview before binding', () => {
  const data = snapshot(), before = JSON.stringify(data);
  data.rotors[0].pitch_deg = 1;
  assert.throws(() => bindImportedSource(data, receipt(), ['r0'], before), /Draft inputs changed/);
  assert.equal(data.rotors[0].map_ref, 'old0');
});

test('preview identity cannot be omitted', () => {
  const data = snapshot();
  assert.throws(() => bindImportedSource(data, receipt(), ['r0']), /Draft inputs changed/);
});

test('configuration edit, deletion and duplicate IDs never silently remap a selection', () => {
  const data = snapshot(), before = JSON.stringify(data);
  data.rotors[0].configuration_id = 'motor-prop-B';
  assert.throws(() => bindImportedSource(data, receipt(), ['r0'], before), /Draft inputs changed/);
  assert.throws(() => bindImportedSource(data, receipt(), ['r0'], JSON.stringify(data)), /no longer matches/);
  data.rotors[0].rotor_id = 'r1';
  assert.throws(() => sourceBindingCandidates(data, receipt()), /unique rotor IDs/);
});

for (const broken of [
  {source_sha256: 'not-a-hash', dataset: receipt().dataset},
  {source_sha256: 'a'.repeat(64), dataset: {dataset_id: 'x'}},
  {source_sha256: 'a'.repeat(64), dataset: {...receipt().dataset, source_kind: 'approved'}},
]) test('incomplete/unknown import identity is not bindable: '+JSON.stringify(broken.dataset), () => {
  assert.throws(() => sourceBindingCandidates(snapshot(), broken), /complete retained source identity/);
});

test('empty rotor list yields no choices without inventing a configuration', () => {
  assert.deepEqual(sourceBindingCandidates({rotors: []}, receipt()), []);
});
