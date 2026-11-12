// Synthetic presentation/controller tests only; no browser, API or physics assertions.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {PRESENTATION_LIMITS, projectDiskPressure, formatApprox, renderDiskPressurePostpro} from '../../web/js/disk-pressure-postpro.js';
import {mountDiskPressure} from '../../web/js/disk-pressure.js';
import {mountPolarRotor} from '../../web/js/polar-rotor.js';

const STATE = 'This is a derived IDEALIZED ACTUATOR-DISK quantity from integrated annulus thrust, ' +
  'expressed as a derived disk pressure jump; NOT surface pressure, NOT a solved or CFD pressure field. ' +
  'It carries no spatial/vector information beyond the axisymmetric annulus it derives from. ' +
  'The full-disk mean spreads thrust over the whole disk including any inner hole; ' +
  'the active-annular mean spreads it only over the modeled annuli. ' +
  'Their averaging areas differ whenever the innermost radius > 0; for nonzero total thrust, the means differ.';
const DERIVATION = 'ACTUATOR_DISK_IDENTITY_FROM_INTEGRATED_ANNULUS_THRUST';
const EXPORT_SCHEMA = 'polar_rotor_disk_pressure_export_v1';
// Incomplete, deliberately synthetic records: no model or retained receipt is represented.
function syntheticDerivation() {
  return {evaluation: 'polar_rotor_disk_pressure', schema_version: 'polar_rotor_disk_pressure_v1',
    status: 'COMPUTED_EXPERIMENTAL', disk_pressure_state: 'DERIVED', state_text: STATE, limitations: [STATE],
    outputs: {derivation: DERIVATION, annuli: [{annulus_index: 0, disk_pressure_jump_pa: 12.5}, {annulus_index: 1, disk_pressure_jump_pa: -2}],
      rotor_mean_disk_loading_pa: 1, rotor_active_annular_loading_pa: 2, input_digest: 'a'.repeat(64)},
    output_units: {derivation: 'label', annuli: [{annulus_index: 'index', disk_pressure_jump_pa: 'Pa'}, {annulus_index: 'index', disk_pressure_jump_pa: 'Pa'}],
      rotor_mean_disk_loading_pa: 'Pa', rotor_active_annular_loading_pa: 'Pa', input_digest: 'sha256'},
    request_sha256: 'a'.repeat(64), evaluation_sha256: 'b'.repeat(64)};
}
function syntheticRotor() {
  return {evaluation: 'polar_rotor_experimental', schema_version: 'polar_rotor_v1',
    outputs: {annuli: [{annulus_index: 0, radial_inner_m: 1, radial_outer_m: 2}, {annulus_index: 1, radial_inner_m: 2, radial_outer_m: 4}]},
    output_units: {annuli: [{radial_inner_m: 'm', radial_outer_m: 'm'}, {radial_inner_m: 'm', radial_outer_m: 'm'}]}};
}
function syntheticProjection() {
  const data = syntheticDerivation(), source = syntheticRotor();
  data.outputs.annuli.forEach((row, index) => Object.assign(row, source.outputs.annuli[index]));
  data.output_units.annuli.forEach((row, index) => Object.assign(row, source.output_units.annuli[index]));
  return data;
}
function dom() {
  const nodes = [], saves = [], events = [];
  const documentListeners = new Map();
  const doc = {
    addEventListener(type, listener) {
      if (!documentListeners.has(type)) documentListeners.set(type, []);
      documentListeners.get(type).push(listener);
    },
    dispatchEvent(event) {for (const listener of documentListeners.get(event.type) || []) listener(event); return true;},
    createElement(tag) {
    const listeners = new Map();
    const node = {tag, ownerDocument: doc, children: [], attrs: {}, dataset: {}, value: '', hidden: false,
      append(...children) {this.children.push(...children);}, replaceChildren(...children) {this.children = children;},
      setAttribute(key, value) {this.attrs[key] = String(value);}, addEventListener(key, fn) {listeners.set(key, fn);},
      dispatchEvent(event) {listeners.get(event.type)?.(event); if (event.bubbles) doc.dispatchEvent(event); return true;},
      fire(key) {return listeners.get(key)?.();}, click() {events.push('click');}, remove() {events.push('remove');}};
    Object.defineProperty(node, 'innerHTML', {set() {throw new Error('Unsafe HTML sink');}});
    let text = '';
    Object.defineProperty(node, 'textContent', {get() {return text + this.children.map(child => child.textContent).join('');},
      set(value) {text = String(value); this.children = [];}});
    nodes.push(node); return node;
  }};
  doc.body = {append() {events.push('append');}};
  doc.defaultView = {CustomEvent: class {
    constructor(type, {bubbles = false} = {}) {this.type = type; this.bubbles = bubbles; this.detail = null;}
  }, URL: {createObjectURL(blob) {saves.push(blob); events.push('create'); return 'blob:synthetic-report';},
    revokeObjectURL() {events.push('revoke');}}};
  return {doc, nodes, saves, events, root: doc.createElement('section')};
}

test('invalid projection inputs and missing native geometry are refused', () => {
  for (const data of [undefined, null, [], {}, {outputs: {}}, 'DERIVED', syntheticDerivation()]) {
    const view = projectDiskPressure(data); assert.equal(view.available, false); assert.match(view.reason, /Projection unavailable/);
  }
});
test('synthetic presentation copies bounded rows and both actual V142 mean fields without arithmetic', () => {
  assert.ok(Object.isFrozen(PRESENTATION_LIMITS));
  const data = syntheticProjection(), before = structuredClone(data), view = projectDiskPressure(data);
  assert.deepEqual(view, {available: true, stateText: STATE,
    rows: [{index: 0, inner: 1, outer: 2, pressure: 12.5}, {index: 1, inner: 2, outer: 4, pressure: -2}], meanFull: 1, meanActive: 2});
  assert.deepEqual(data, before);
});
test('stripped producer labels are refused', () => {
  for (const label of ['IDEALIZED ACTUATOR-DISK', 'NOT surface pressure', 'NOT a solved or CFD pressure field',
    'no spatial/vector information', 'full-disk mean', 'active-annular mean']) {
    const data = syntheticProjection(); data.state_text = data.state_text.replace(label, 'removed');
    assert.equal(projectDiskPressure(data).available, false, label);
  }
});
test('malformed presentation fields and units refuse the complete projection', () => {
  for (const mutate of [data => data.evaluation = 'other', data => data.schema_version = 'other',
    data => data.status = 'EXECUTION_FAILED', data => data.disk_pressure_state = 'NOT_RUN',
    data => data.outputs.annuli = [], data => data.outputs.annuli = Array(9).fill(data.outputs.annuli[0]),
    data => data.outputs.annuli[0].annulus_index = '0', data => data.outputs.annuli[0].annulus_index = false,
    data => data.outputs.annuli[0].radial_inner_m = -1, data => data.outputs.annuli[0].radial_outer_m = 1,
    data => data.outputs.annuli[1].radial_inner_m = 3, data => data.outputs.annuli[0].disk_pressure_jump_pa = NaN,
    data => data.outputs.rotor_mean_disk_loading_pa = Infinity, data => data.outputs.rotor_active_annular_loading_pa = '2',
    data => data.outputs.annuli[0].disk_pressure_jump_pa = 1e13, data => data.outputs.annuli[0].disk_pressure_jump_pa = 1e-13,
    data => data.outputs.annuli[0].disk_pressure_jump_pa = Number.MAX_SAFE_INTEGER + 1,
    data => data.output_units.annuli[0].disk_pressure_jump_pa = 'N', data => data.output_units.annuli[1].radial_outer_m = 'Pa',
    data => data.output_units.rotor_active_annular_loading_pa = 'N', data => data.output_units.annuli.pop(),
    data => data.state_text = STATE + ' '.repeat(2001)]) {
    const data = syntheticProjection(); mutate(data); assert.equal(projectDiskPressure(data).available, false);
  }
});
test('approximate formatter refuses unsafe integers and preserves signed zero', () => {
  assert.throws(() => formatApprox(Number.MAX_SAFE_INTEGER + 1));
  assert.throws(() => formatApprox(Infinity)); assert.equal(formatApprox(-0), '−0');
  assert.equal(formatApprox(12.345678), '12.346');
});
test('render retains verbatim labels, honest unavailable fields, accessible tables and no field claims', () => {
  const h = dom(); const data = syntheticProjection(); data.state_text += ' <img src=x onerror=alert(1)>';
  assert.equal(renderDiskPressurePostpro(h.root, data).available, true);
  assert.ok(h.root.textContent.includes(data.state_text)); assert.match(h.root.textContent, /Producer-reported; no independent verification/);
  assert.match(h.root.textContent, /Not physical validation/); assert.match(h.root.textContent, /approximate IEEE754/);
  assert.match(h.root.textContent, /Full raw JSON is authoritative/);
  assert.match(h.root.textContent, /Pressure contours are pending genuine field output/);
  assert.match(h.root.textContent, /Flow vectors are pending genuine field output/);
  const headings = h.nodes.filter(node => /^h[345]$/.test(node.tag)).map(node => node.textContent).join('\n');
  assert.doesNotMatch(headings, /surface pressure|CFD contour/);
  const textOutsideProducerLabel = h.nodes.filter(node => !node.children.length && node.textContent !== data.state_text).map(node => node.textContent).join('\n');
  assert.doesNotMatch(textOutsideProducerLabel, /surface pressure|CFD/);
  assert.equal(h.nodes.some(node => ['svg', 'img', 'script', 'canvas'].includes(node.tag)), false);
  const wrap = h.nodes.find(node => node.className === 'polar-rotor-table-scroll');
  assert.equal(wrap.tabIndex, 0); assert.equal(wrap.attrs.role, 'region'); assert.match(wrap.attrs['aria-label'], /Scroll horizontally/);
  assert.deepEqual(h.nodes.filter(node => node.tag === 'dd').map(node => node.textContent), ['approx 1', 'approx 2']);
  assert.deepEqual(h.nodes.filter(node => node.tag === 'td').map(node => node.textContent),
    ['0', 'approx 1', 'approx 2', 'approx 12.5', '1', 'approx 2', 'approx 4', 'approx -2']);
});
test('unavailable render still shows producer label and notice, with no numeric values', () => {
  const h = dom(), data = syntheticProjection(); data.outputs.rotor_active_annular_loading_pa = null;
  assert.equal(renderDiskPressurePostpro(h.root, data).available, false);
  assert.ok(h.root.textContent.includes(STATE)); assert.match(h.root.textContent, /Projection unavailable/);
  assert.equal(h.nodes.some(node => ['table', 'dd', 'td'].includes(node.tag)), false);
});

const response = (text, status = 200) => ({status, text: async () => text});
const deferred = () => {let resolve, reject; const promise = new Promise((yes, no) => {resolve = yes; reject = no;}); return {promise, resolve, reject};};
function harness(getRotorResponse) {
  const h = dom(), calls = [], queue = [];
  let online = true, generation = 1;
  const mounted = mountDiskPressure(h.root, {isConnected: () => online, readContext: () => generation, isContext: value => value === generation, getRotorResponse,
    request(path, options) {calls.push({path, options}); assert.ok(queue.length, 'request must be explicitly queued'); return queue.shift()();}});
  const el = key => h.nodes.find(node => node.dataset.testid === 'disk-pressure-' + key);
  return {...h, calls, mounted, el, queue: fn => queue.push(fn),
    edit(raw) {el('input').value = raw; el('input').fire('input');},
    run: () => el('run').fire('click'), export: () => el('export').fire('click'), download: () => el('download').fire('click'),
    connect(value, sync = true) {online = value; if (sync) mounted.syncContext();},
    change(sync = true) {generation++; if (sync) mounted.syncContext();}};
}
async function derived(h, data = syntheticDerivation(), raw = JSON.stringify(data)) {
  h.edit(JSON.stringify(syntheticRotor())); h.queue(async () => response(raw)); await h.run();
  assert.equal(h.el('export').disabled, false); return raw;
}
function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  return JSON.stringify(value);
}
function reportResponse(data = syntheticDerivation(), transform = value => value) {
  const report = {title: 'Derived idealized actuator-disk pressure report', schema_version: EXPORT_SCHEMA,
    ...structuredClone(data.outputs), state_text: data.state_text, limitations: data.limitations,
    source_request_sha256: data.request_sha256, source_evaluation_sha256: data.evaluation_sha256, output_units: data.output_units};
  const text = transform(canonical(report));
  return {text, raw: '{"evaluation":"polar_rotor_disk_pressure_export","schema_version":' + JSON.stringify(EXPORT_SCHEMA) +
    ',"status":"COMPUTED_EXPERIMENTAL","disk_pressure_report_state":"EXPORTED","outputs":{"report":' + text +
    ',"report_canonical_sha256":"' + 'c'.repeat(64) + '","report_bytes":' + new TextEncoder().encode(text).byteLength + '}}'};
}
test('mount stays idle and empty; only explicit raw POSTs occur and HTTP 422 is generic', async () => {
  const h = harness(); assert.equal(h.calls.length, 0); assert.equal(h.el('input').value, '');
  assert.equal(h.el('run').disabled, true); assert.equal(h.el('export').disabled, true); assert.equal(h.el('download').disabled, true);
  for (const raw of [' {"duplicate":1,"duplicate":2,"native":9007199254740993,"zero":-0.0} ', '{"x":NaN}', '{"PRIVATE_INPUT":']) {
    h.edit(raw); assert.equal(h.el('run').disabled, false);
    let reads = 0; h.queue(async () => ({status: 422, text() {reads++; throw new Error('PRIVATE_ERROR');}}));
    await h.run(); assert.equal(reads, 0);
    assert.deepEqual(h.calls.at(-1), {path: '/disk-pressure/derive', options: {method: 'POST', headers: {'Content-Type': 'application/json'}, body: raw}});
    assert.equal(h.el('status').textContent, 'HTTP 422 · Invalid disk pressure request.');
    assert.equal(h.el('export').disabled, true); assert.equal(h.el('result').hidden, true);
  }
});
test('input transport bounds refuse oversized UTF-8 and literal unpaired surrogates', async () => {
  const h = harness();
  for (const raw of [' ', '\ud800', '\udfff', 'µ'.repeat(8388609)]) {
    h.edit(raw); assert.equal(h.el('run').disabled, true); await h.run(); assert.equal(h.calls.length, 0);
  }
});
test('native response is exported unchanged and report download preserves canonical float tokens', async () => {
  const h = harness(), data = syntheticDerivation();
  const raw = JSON.stringify(data).replace('"rotor_mean_disk_loading_pa":1', '"rotor_mean_disk_loading_pa":1.0');
  await derived(h, data, raw);
  assert.equal(h.el('result').textContent, raw);
  const exported = reportResponse(data, text => text.replace('"rotor_mean_disk_loading_pa":1', '"rotor_mean_disk_loading_pa":1.0'));
  h.queue(async () => response(exported.raw)); await h.export();
  assert.deepEqual(h.calls.at(-1), {path: '/disk-pressure/export', options: {method: 'POST', headers: {'Content-Type': 'application/json'}, body: raw}});
  assert.equal(h.saves.length, 0); assert.equal(h.el('download').disabled, false);
  assert.match(h.el('report-status').textContent, new RegExp('c'.repeat(64))); assert.match(h.el('report-status').textContent, /report_bytes/);
  h.download(); assert.equal(await h.saves[0].text(), exported.text);
  assert.deepEqual(h.events, ['create', 'append', 'click', 'remove', 'revoke']);
  assert.equal(h.nodes.find(node => node.tag === 'a').download, 'disk-pressure-report.json');
  h.edit(JSON.stringify(syntheticRotor()) + ' ');
  assert.equal(h.el('export').disabled, true); assert.equal(h.el('download').disabled, true);
  assert.equal(h.el('report-status').textContent, '');
});
test('busy and rapid double submission discipline prevents duplicate POSTs', async () => {
  const h = harness(), waiting = deferred(); h.edit(JSON.stringify(syntheticRotor())); h.queue(() => waiting.promise);
  const pending = h.run(); assert.equal(h.el('run').disabled, true); assert.equal(h.el('export').disabled, true);
  await h.run(); await h.export(); assert.equal(h.calls.length, 1);
  waiting.resolve(response(JSON.stringify(syntheticDerivation()))); await pending;
  const exportWait = deferred(); h.queue(() => exportWait.promise); const exportPending = h.export();
  assert.equal(h.el('run').disabled, true); assert.equal(h.el('export').disabled, true); await h.export();
  assert.equal(h.calls.length, 2); exportWait.resolve(response(reportResponse().raw)); await exportPending;
  assert.equal(h.el('download').disabled, false);
});
test('delayed response bodies cannot replace edited or disconnected work', async () => {
  for (const action of [h => h.edit('changed input'), h => h.connect(false), h => h.change(false)]) {
    const h = harness(), waiting = deferred(), reading = deferred(); h.edit(JSON.stringify(syntheticRotor()));
    h.queue(async () => ({status: 200, text() {reading.resolve(); return waiting.promise;}}));
    const pending = h.run(); await reading.promise; action(h);
    waiting.resolve(JSON.stringify(syntheticDerivation())); await pending;
    assert.equal(h.el('export').disabled, true); assert.equal(h.el('result').hidden, true); assert.equal(h.saves.length, 0);
  }
});
test('stale export resolution and rejection cannot publish a download', async () => {
  for (const reject of [false, true]) {
    const h = harness(); await derived(h); const waiting = deferred(); h.queue(() => waiting.promise);
    const pending = h.export(); h.edit('edited input');
    if (reject) waiting.reject(new Error('PRIVATE_SECRET')); else waiting.resolve(response(reportResponse().raw));
    await pending; assert.equal(h.el('download').disabled, true); assert.equal(h.el('report-status').textContent, '');
    assert.doesNotMatch(h.el('status').textContent, /PRIVATE_SECRET/);
  }
});
test('non-200 export bodies stay unread; malformed or label-stripped reports offer no download', async () => {
  const h = harness(); await derived(h);
  let reads = 0; h.queue(async () => ({status: 500, text() {reads++; return 'PRIVATE_ERROR';}})); await h.export();
  assert.equal(reads, 0); assert.equal(h.el('status').textContent, 'HTTP 500 · Disk pressure request failed.');
  for (const raw of ['{', '{}', reportResponse().raw.replace('NOT surface pressure', 'removed'),
    reportResponse().raw.replace('"report_bytes":', '"report_bytes":0,"duplicate_report_bytes":')]) {
    h.queue(async () => response(raw)); await h.export(); assert.equal(h.el('download').disabled, true);
    assert.equal(h.el('report-status').textContent, '');
  }
});
test('workflow refusals leave raw data and producer labels visible, with export disabled', async () => {
  const h = harness(), data = syntheticDerivation(); data.status = 'MODEL_INAPPLICABLE'; data.outputs = {};
  h.edit(JSON.stringify(syntheticRotor())); h.queue(async () => response(JSON.stringify(data))); await h.run();
  assert.equal(h.el('result').hidden, false); assert.ok(h.el('postpro').textContent.includes(STATE));
  assert.match(h.el('postpro').textContent, /Projection unavailable/); assert.equal(h.el('export').disabled, true);
});
test('context changes clear the panel, and minimal connection-only injection is supported', () => {
  const h = harness(); h.edit('{}'); h.connect(false); assert.equal(h.el('input').value, ''); assert.equal(h.el('run').disabled, true);
  h.connect(true); assert.equal(h.calls.length, 0); h.edit('{}'); h.change(); assert.equal(h.el('input').value, '');
  const d = dom(); assert.doesNotThrow(() => mountDiskPressure(d.root, {request() {assert.fail('automatic request');}, isConnected: () => false}));
});
test('optional prefill copies the fresh raw string without a request or automatic derivation', () => {
  const raw = ' \n' + JSON.stringify(syntheticRotor()) + '\n ';
  const h = harness(() => raw), button = h.el('prefill');
  assert.equal(h.el('input').value, ''); assert.equal(h.calls.length, 0);
  assert.equal(button.type, 'button'); assert.equal(button.textContent, 'Use current polar-rotor result');
  assert.equal(button.disabled, false);
  const actions = h.nodes.find(node => node.className === 'polar-rotor-actions');
  assert.ok(actions.children.indexOf(button) < actions.children.indexOf(h.el('run')));
  button.fire('click');
  assert.equal(h.el('input').value, raw); assert.equal(h.calls.length, 0);
  assert.equal(h.el('run').disabled, false); assert.equal(h.el('export').disabled, true);
  assert.equal(h.el('status').textContent, 'Polar-rotor result loaded. Explicitly derive to continue.');
  assert.equal(harness().el('prefill'), undefined, 'absent dependency retains the original controls');
});
test('prefill invalidates an existing derivation until another explicit Derive', async () => {
  const raw = JSON.stringify(syntheticRotor()), h = harness(() => raw);
  await derived(h); assert.equal(h.el('export').disabled, false);
  const count = h.calls.length; h.el('prefill').fire('click');
  assert.equal(h.calls.length, count); assert.equal(h.el('export').disabled, true);
  assert.equal(h.el('download').disabled, true); assert.equal(h.el('result').hidden, true);
  h.queue(async () => response(JSON.stringify(syntheticDerivation()))); await h.run();
  assert.equal(h.calls.length, count + 1); assert.equal(h.el('export').disabled, false);
});
test('null and throwing rotor getters disable prefill without changing status on controls', () => {
  for (const getter of [() => null, () => {throw new Error('PRIVATE_GETTER');}]) {
    const h = harness(getter), before = h.el('status').textContent;
    assert.equal(h.el('prefill').disabled, true);
    assert.doesNotThrow(() => h.mounted.syncContext());
    // Native disabled buttons do not dispatch a user click.
    if (!h.el('prefill').disabled) h.el('prefill').fire('click');
    assert.equal(h.el('input').value, ''); assert.equal(h.calls.length, 0);
    assert.equal(h.el('status').textContent, before);
  }
});
test('a rotor result that becomes stale at the handoff refuses prefill and erases derivation', async () => {
  let text = JSON.stringify(syntheticRotor());
  const h = harness(() => text); await derived(h);
  const count = h.calls.length;
  text = null; h.el('prefill').fire('click');
  assert.equal(h.el('prefill').disabled, true); assert.equal(h.el('export').disabled, true);
  assert.equal(h.el('result').hidden, true); assert.equal(h.calls.length, count);
  assert.equal(h.el('status').textContent, 'No fresh polar-rotor result available. Run the polar-rotor panel first, or paste a sealed response.');
});
test('panel interaction refreshes a fake rotor getter as its result becomes fresh or stale', () => {
  let text = null;
  const h = harness(() => text); assert.equal(h.el('prefill').disabled, true);
  text = JSON.stringify(syntheticRotor()); h.root.fire('pointerenter');
  assert.equal(h.el('prefill').disabled, false); h.el('prefill').fire('click');
  assert.equal(h.el('input').value, text); const status = h.el('status').textContent;
  text = null; h.root.fire('focusin'); assert.equal(h.el('prefill').disabled, true);
  assert.equal(h.el('status').textContent, status); assert.equal(h.calls.length, 0);
});
test('capture-change signal updates prefill without disk-panel pointer, focus or input events', () => {
  let text = null;
  const h = harness(() => text), status = h.el('status').textContent;
  assert.equal(h.el('prefill').disabled, true);
  text = JSON.stringify(syntheticRotor());
  h.doc.dispatchEvent(new h.doc.defaultView.CustomEvent('polar-rotor-capture-changed', {bubbles: true}));
  assert.equal(h.el('prefill').disabled, false);
  text = null;
  h.doc.dispatchEvent(new h.doc.defaultView.CustomEvent('polar-rotor-capture-changed', {bubbles: true}));
  assert.equal(h.el('prefill').disabled, true);
  assert.equal(h.el('status').textContent, status); assert.equal(h.el('input').value, '');
  assert.equal(h.calls.length, 0);
});
test('real rotor mount signals capture storage, rerun, request edits and context invalidation without a payload', async () => {
  const h = dom(), signals = [], requests = [];
  let generation = 1;
  const catalog = {catalog: {evaluation: 'polar_rotor_experimental', schema_version: 'polar_rotor_v1', limitations: []},
    transport: {limits: {body_bytes: 1048576}}};
  const raw = JSON.stringify({...syntheticRotor(), status: 'COMPUTED_EXPERIMENTAL'});
  const context = {readContext: () => generation, isContext: value => value === generation, isConnected: () => true};
  const rotor = mountPolarRotor(h.root, {...context, request: async path => {
    requests.push(path);
    return {ok: true, status: 200, text: async () => path.endsWith('/catalog') ? JSON.stringify(catalog) : raw};
  }});
  const diskRoot = h.doc.createElement('section');
  mountDiskPressure(diskRoot, {...context, getRotorResponse: () => rotor.currentResponseText(),
    request() {assert.fail('capture signals must not dispatch a disk-pressure request');}});
  h.doc.addEventListener('polar-rotor-capture-changed', event => signals.push(event));
  const el = id => h.nodes.find(node => node.dataset.testid === id);
  const prefill = el('disk-pressure-prefill'); assert.equal(prefill.disabled, true);
  el('polar-rotor-input').value = '{}'; el('polar-rotor-input').fire('input');
  await el('polar-rotor-refresh').fire('click');
  await el('polar-rotor-run').fire('click');
  assert.equal(rotor.currentResponseText(), raw); assert.equal(prefill.disabled, false);
  const storedCount = signals.length;
  const rerun = el('polar-rotor-run').fire('click');
  assert.equal(prefill.disabled, true); assert.equal(signals.length, storedCount + 1);
  await rerun; assert.equal(prefill.disabled, false);
  el('polar-rotor-input').value = '{"edited":true}'; el('polar-rotor-input').fire('input');
  assert.equal(rotor.currentResponseText(), null); assert.equal(prefill.disabled, true);
  await el('polar-rotor-run').fire('click'); assert.equal(prefill.disabled, false);
  const beforeContext = signals.length;
  generation++; rotor.syncContext();
  assert.equal(rotor.currentResponseText(), null); assert.equal(prefill.disabled, true);
  assert.equal(signals.length, beforeContext + 1);
  assert.ok(signals.every(event => event.bubbles === true && event.detail === null));
  assert.equal(el('disk-pressure-input').value, ''); assert.equal(requests.length, 4);
});
test('prefill cannot replace input while busy or disconnected', async () => {
  const raw = JSON.stringify(syntheticRotor()), h = harness(() => raw), waiting = deferred();
  h.edit(raw); h.queue(() => waiting.promise); const pending = h.run();
  assert.equal(h.el('prefill').disabled, true); h.el('prefill').fire('click'); assert.equal(h.calls.length, 1);
  waiting.resolve(response(JSON.stringify(syntheticDerivation()))); await pending;
  assert.equal(h.el('export').disabled, false);
  h.connect(false); assert.equal(h.el('prefill').disabled, true); h.el('prefill').fire('click');
  assert.equal(h.el('input').value, ''); assert.equal(h.calls.length, 1);
});
test('workbench registers the section, mount and context synchronization using existing CSS', () => {
  const html = readFileSync(new URL('../../web/workbench.html', import.meta.url), 'utf8');
  const js = readFileSync(new URL('../../web/js/workbench.js', import.meta.url), 'utf8');
  assert.ok(html.indexOf('id="disk-pressure"') > html.indexOf('id="polar-rotor"'));
  assert.match(html, /<section id="disk-pressure" aria-label="Derived disk pressure workbench"><\/section>/);
  assert.match(js, /import \{mountDiskPressure\}/); assert.match(js, /diskPressure=mountDiskPressure/); assert.match(js, /diskPressure\.syncContext\(\)/);
  assert.match(js, /getRotorResponse:\(\)=>polarRotor\.currentResponseText\(\)/);
});
