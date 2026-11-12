// Unit DOM tests only. All response fixtures are synthetic, not actual physics,
// HTTP/API/browser evidence, or physical/computational qualification.
// The owner runs these tests independently; authors must not report them as passed.
import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {mountTabulatedSolvedElectrothermal} from '../../web/js/tabulated-solved-electrothermal.js';
import {mountTabulatedElectrothermal} from '../../web/js/tabulated-electrothermal.js';
import {mountPolarRotor} from '../../web/js/polar-rotor.js';

const repo = fileURLToPath(new URL('../../', import.meta.url));
// Read the actual Python API catalog, without invoking an evaluator. Never invent schema identity.
function readCatalog(module) {
  return execFileSync(process.env.PYTHON || 'python3', ['-B', '-c',
    'import asyncio,json; from physimesh.api.' + module + ' import catalog; print(json.dumps(asyncio.run(catalog())))'],
    {cwd: repo, env: {...process.env, PYTHONPATH: repo + '/src', PYTHONDONTWRITEBYTECODE: '1'},
      encoding: 'utf8', timeout: 10000, maxBuffer: 8 * 1048576});
}
const catalogRaw = readCatalog('polar_rotor');
const actualCatalog = JSON.parse(catalogRaw);
const response = (raw, status = 200) => ({ok: status >= 200 && status < 300, status, text: async () => raw});
const deferred = () => {let resolve, reject; const promise = new Promise((a, b) => {resolve = a; reject = b;}); return {promise, resolve, reject};};
function harness(connected = true, {saveCapture, defaultSave = false, failAt, mount = mountPolarRotor, namespace = 'polar-rotor', rawCatalog = catalogRaw} = {}) {
  const nodes = [], saves = [], urlEvents = [], liveURLs = new Set();
  let unsafeHTMLWrites = 0;
  function fail(stage) {if (failAt === stage) throw new Error('PRIVATE_DOWNLOAD_SECRET');}
  const doc = {createElement(tag) {
    if (tag === 'a') fail('anchor');
    const listeners = new Map(), attrs = new Map();
    const el = {tag, ownerDocument: doc, children: [], dataset: {}, value: '', textContent: '', hidden: false,
      append(...children) {this.children.push(...children);},
      replaceChildren(...children) {this.children = [...children];},
      setAttribute(k, v) {attrs.set(k, String(v));}, getAttribute(k) {return attrs.get(k);},
      addEventListener(k, fn) {listeners.set(k, fn);}, fire(k) {return listeners.get(k)?.();},
      click() {urlEvents.push('click'); fail('click');},
      remove() {urlEvents.push('remove'); fail('remove'); this.attached = false;},
      set innerHTML(_) {++unsafeHTMLWrites; throw new Error('Unsafe HTML sink');}};
    let ownText = '';
    Object.defineProperty(el, 'textContent', {
      get() {return ownText + this.children.map(child => child.textContent).join('');},
      set(value) {ownText = String(value); this.children = [];},
    });
    nodes.push(el); return el;
  }};
  doc.body = {append(el) {urlEvents.push('append'); fail('append'); el.attached = true;}};
  doc.defaultView = {URL: {
    createObjectURL(blob) {urlEvents.push('create'); fail('create'); saves.push({blob}); liveURLs.add('blob:unit-capture'); return 'blob:unit-capture';},
    revokeObjectURL(url) {urlEvents.push('revoke'); liveURLs.delete(url);},
  }};
  let context = {generation: 1, token: 'unit-token', organization: 'unit-org', project: undefined};
  const calls = [], queue = [];
  const mounted = mount(doc.createElement('section'), {
    readContext: () => ({...context}),
    isContext: c => Object.keys(context).every(k => c[k] === context[k]), isConnected: () => connected,
    request: (path, options) => {calls.push({path, options}); return queue.length ? queue.shift()(path, options) : Promise.resolve(response(rawCatalog));},
    saveCapture: defaultSave ? undefined : (saveCapture || ((blob, filename) => {saves.push({blob, filename});})),
  });
  const el = key => nodes.find(n => n.dataset.testid === namespace + '-' + key);
  return {nodes, calls, saves, urlEvents, liveURLs, mounted, el,
    get unsafeHTMLWrites() {return unsafeHTMLWrites;},
    queue(fn) {queue.push(fn);},
    edit(raw) {el('input').value = raw; el('input').fire('input');},
    async refresh() {await el('refresh').fire('click');},
    run() {return el('run').fire('click');},
    download() {return el('download').fire('click');},
    change(patch, sync = true) {context = {...context, ...patch}; if (sync) mounted.syncContext();},
    connect(value, sync = true) {connected = value; if (sync) mounted.syncContext();},
  };
}
async function ready() {const h = harness(); await h.refresh(); h.edit('{}'); assert.equal(h.el('run').disabled, false); return h;}
const statuses = ['COMPUTED_EXPERIMENTAL', 'MODEL_INAPPLICABLE', 'SOLVER_UNSUPPORTED', 'EXECUTION_FAILED'];
// Synthetic response envelopes test identity recognition, not scientific execution.
const recognized = (status = statuses[0]) => ({
  evaluation: actualCatalog.catalog.evaluation, schema_version: actualCatalog.catalog.schema_version, status,
});

test('mount is collapsed and idle; real fresh catalog enables standalone caller input', async () => {
  const h = harness(); assert.equal(h.calls.length, 0);
  assert.notEqual(h.nodes.find(n => n.tag === 'details').open, true);
  assert.equal(h.el('input').value, ''); assert.equal(h.el('run').disabled, true);
  h.edit('{}'); assert.equal(h.el('run').disabled, true);
  await h.refresh(); assert.equal(h.calls[0].path, '/polar-rotor/catalog');
  assert.equal(h.el('catalog').textContent, catalogRaw); assert.equal(h.el('run').disabled, false);
  await h.refresh(); assert.equal(h.calls.length, 2);
  assert.ok(actualCatalog.catalog.limitations.every(s => catalogRaw.includes(s)));
});
test('raw body preserves whitespace, duplicate keys and native integers over 2**53, negative zero and Unicode', async () => {
  const h = await ready(), raw = ' \n{"integer":9007199254740993,"zero":-0.0,"text":"µ","duplicate":1,"duplicate":2} ';
  h.edit(raw); h.queue(async () => response(JSON.stringify(recognized('MODEL_INAPPLICABLE')))); await h.run();
  assert.deepEqual(h.calls.at(-1), {path: '/polar-rotor/evaluate', options: {method: 'POST', headers: {'Content-Type': 'application/json'}, body: raw}});
});
test('full raw result preserves native integers, hashes, nested data and malicious HTML as text', async () => {
  const h = await ready(), raw = ' {"status":"COMPUTED_EXPERIMENTAL","native":9007199254740993,"zero":-0.0,"micro":"µ","nested":{"html":"<img src=x onerror=alert(1)>","hash":"literal-hash"}}\n';
  h.queue(async () => response(raw)); await h.run();
  assert.equal(h.el('result').textContent, raw); assert.equal(h.el('result').hidden, false);
  assert.equal(h.el('result').children.length, 0);
});
test('synthetic recognized state roster is string-only, HTML-safe and leaves numeric T/Q/P raw', async () => {
  // Synthetic display fixtures only, deliberately including untrusted state types.
  // No evaluator runs here; these envelopes establish no physical qualification.
  const h = await ready();
  const html = '<img src=x onerror=alert(1)><script>synthetic()</script>';
  // Literal numeric tokens avoid a test-side Number roundtrip before the UI sees them.
  const totals = '{"totals":{"thrust_n":9007199254740993,"torque_nm":-0.0,"shaft_power_w":1.2300e+4}}';
  const cases = [
    {name: 'three converged', rotor: 'COMPUTED', solves: ['CONVERGED', 'CONVERGED', 'CONVERGED'], integrated: totals},
    ...['NOT_RUN_OUT_OF_POLAR_DOMAIN', 'NOT_BRACKETED', 'EVALUATION_BUDGET_EXHAUSTED'].map(state => ({
      name: state, rotor: 'NOT_RUN_SECTION_NOT_CONVERGED', solves: [state, 'CONVERGED', 'CONVERGED'], integrated: 'null',
    })),
    {name: 'non-string nested states', rotor: 0, solves: [42, {untrusted: 'CONVERGED'}, null], integrated: totals},
    {name: 'malicious string states', rotor: html, solves: [html, 'CONVERGED', 'CONVERGED'], integrated: totals},
  ];
  for (const fixture of cases) {
    const annuli = fixture.solves.map(solve_state => ({solve_result: {outputs: {solve_state}}}));
    const raw = ' \n{' + JSON.stringify(recognized()).slice(1, -1) +
      ',"outputs":{"rotor_state":' + JSON.stringify(fixture.rotor) +
      ',"annuli":' + JSON.stringify(annuli) + ',"integrated":' + fixture.integrated + '}}\n ';
    const calls = h.calls.length;
    h.queue(async () => response(raw)); await h.run();
    assert.equal(h.calls.length, calls + 1, fixture.name);
    assert.equal(h.el('result').textContent, raw, fixture.name);
    assert.equal(h.el('result').children.length, 0, 'raw response creates no markup');
    const states = h.el('states');
    assert.equal(states.hidden, false, fixture.name);
    assert.match(states.textContent, /Producer-reported string states only/);
    assert.match(states.textContent, /no independent result or hash verification/);
    const rotor = states.children.find(n => n.tag === 'p' && n.textContent.startsWith('rotor_state: '));
    assert.equal(rotor.textContent, 'rotor_state: ' + (typeof fixture.rotor === 'string' ? fixture.rotor : 'unavailable'));
    assert.equal(rotor.children.length, 0, 'rotor state stays in a text sink');
    const roster = states.children.find(n => n.tag === 'ol');
    assert.equal(roster.children.length, 3, 'all three annuli remain in order');
    assert.deepEqual(roster.children.map(n => n.textContent), fixture.solves.map(state =>
      'solve_state: ' + (typeof state === 'string' ? state : 'unavailable')));
    for (const item of roster.children) {
      assert.equal(item.tag, 'li');
      assert.equal(item.children.length, 0, 'solve state creates no nested markup');
    }
    assert.equal(h.unsafeHTMLWrites, 0);
    assert.equal(h.nodes.some(n => n.tag === 'img' || n.tag === 'script'), false);
    // Check every text leaf outside the raw blocks, including labels and status.
    const summaryText = h.nodes.filter(n => n !== h.el('result') && n !== h.el('catalog') && !n.children.length)
      .map(n => n.textContent).join('\n');
    assert.doesNotMatch(summaryText, /900719925474099[23]|1\.2300e\+4|\b12300\b|-0\.0|thrust_n|torque_nm|shaft_power_w/);
    assert.match(h.el('status').textContent, /HTTP 200 does not mean convergence/);
    assert.equal(h.el('download').disabled, false, 'identity recognition does not guard nested state claims');
    await h.download();
    const capture = JSON.parse(await h.saves.at(-1).blob.text());
    assert.equal(typeof capture.raw_response_json, 'string');
    assert.equal(capture.raw_response_json, raw, 'capture retains original numeric spelling and string states');
    assert.equal(h.calls.length, calls + 1, 'download adds no HTTP or model call');
  }
});
for (const status of [...statuses, 'RESEARCH_ONLY', 'INPUT_INVALID', 'UNKNOWN', null, 0, false]) test('HTTP 200 status is labeled without physical success: ' + status, async () => {
  const h = await ready(), raw = JSON.stringify(recognized(status)); h.queue(async () => response(raw)); await h.run();
  assert.equal(h.el('result').textContent, raw);
  assert.ok(h.el('status').textContent.includes(statuses.includes(status) ? status : 'unrecognized or unavailable'));
  assert.match(h.el('status').textContent, /neither computational nor physical success/);
  if (status !== 'COMPUTED_EXPERIMENTAL') assert.doesNotMatch(h.el('status').textContent, /status: COMPUTED_EXPERIMENTAL/);
});
test('unparseable 200 is disclosed raw with unavailable status', async () => {
  const h = await ready(); h.queue(async () => response('<html>not JSON</html>')); await h.run();
  assert.equal(h.el('result').textContent, '<html>not JSON</html>'); assert.match(h.el('status').textContent, /unrecognized or unavailable/);
});
for (const stage of ['catalog', 'run']) for (const failure of ['network', 'non200', 'text']) test(stage + ' failures are generic: ' + failure, async () => {
  const h = stage === 'run' ? await ready() : harness();
  h.queue(async () => {
    if (failure === 'network') throw new Error('private exception BODY_SECRET');
    if (failure === 'text') return {ok: true, text: async () => {throw new Error('BODY_SECRET');}};
    return response('{"detail":"BODY_SECRET"}', 422);
  });
  await (stage === 'run' ? h.run() : h.refresh());
  assert.doesNotMatch(h.el('status').textContent, /BODY_SECRET|private exception/);
  assert.equal(h.el('result').textContent, ''); assert.equal(h.el('result').hidden, true);
  if (stage === 'catalog') assert.equal(h.el('run').disabled, true);
});
test('disconnected mount and sync never fetch; direct button handlers are gated', async () => {
  const h = harness(false); h.edit('{}'); await h.refresh(); await h.run();
  assert.equal(h.calls.length, 0); assert.equal(h.el('run').disabled, true); assert.equal(h.el('refresh').disabled, true);
  h.connect(true); assert.equal(h.calls.length, 0); assert.equal(h.el('input').value, '');
});
test('blank and actual unpaired surrogates are blocked; escaped surrogate JSON belongs to server', async () => {
  const h = await ready(), count = h.calls.length;
  for (const raw of ['', ' \n\t', '\ud800', '\udc00', 'a\ud800b', '\ud800\ud800']) {
    h.edit(raw); assert.equal(h.el('run').disabled, true); await h.run(); assert.equal(h.calls.length, count);
  }
  for (const raw of ['{"escaped":"\\ud800"}', '{malformed', 'null', '[]', '"😀"']) {
    h.edit(raw); assert.equal(h.el('run').disabled, false);
    h.queue(async () => response('', 422)); await h.run(); assert.equal(h.calls.at(-1).options.body, raw);
  }
});
test('actual UTF-8 cap minus one, exact and plus one include whitespace and µ bytes', async () => {
  const h = await ready(), max = 1048576, prefix = ' \n{"text":"', suffix = '"}\n ';
  const available = max - new TextEncoder().encode(prefix + suffix).byteLength;
  const repeats = Math.floor((available - 1) / 2);
  const content = 'µ'.repeat(repeats) + 'a'.repeat(available - 2 * repeats);
  for (const [raw, bytes, allowed] of [
    [prefix + content.slice(0, -1) + suffix, max - 1, true],
    [prefix + content + suffix, max, true],
    [prefix + content + 'a' + suffix, max + 1, false],
  ]) {
    assert.equal(new TextEncoder().encode(raw).byteLength, bytes);
    h.edit(raw); assert.equal(h.el('run').disabled, !allowed);
    const count = h.calls.length;
    if (allowed) h.queue(async () => response(JSON.stringify(recognized('MODEL_INAPPLICABLE'))));
    await h.run(); assert.equal(h.calls.length, count + Number(allowed));
    if (allowed) assert.equal(h.calls.at(-1).options.body, raw);
  }
});
for (const mutate of [d => d.catalog.evaluation = 'other', d => d.catalog.schema_version = 'other',
  d => d.transport.limits.body_bytes++, d => d.transport.limits.body_bytes = '1048576', d => delete d.catalog.limitations,
  d => delete d.catalog, d => delete d.transport]) test('wrong catalog identity/limit cannot enable run: ' + mutate, async () => {
  const h = harness(), d = structuredClone(actualCatalog); mutate(d); h.edit('{}');
  h.queue(async () => response(JSON.stringify(d))); await h.refresh(); assert.equal(h.el('run').disabled, true);
});
test('refresh immediately invalidates old catalog/results, guards duplicate clicks, failure leaves run disabled', async () => {
  const h = await ready(); h.queue(async () => response(JSON.stringify(recognized('MODEL_INAPPLICABLE')))); await h.run();
  const d = deferred(); h.queue(() => d.promise); const p = h.el('refresh').fire('click'), count = h.calls.length;
  assert.equal(h.el('result').textContent, ''); assert.equal(h.el('catalog').textContent, ''); assert.equal(h.el('run').disabled, true);
  await h.refresh(); await h.run(); assert.equal(h.calls.length, count);
  d.reject(new Error('secret')); await p; assert.equal(h.el('run').disabled, true);
});
for (const phase of ['response', 'text']) for (const invalidate of ['input', 'clear', 'refresh', 'generation', 'project', 'organization', 'token', 'disconnect']) {
  test('late ' + phase + ' after ' + invalidate + ' cannot disclose result', async () => {
    const h = await ready(), d = deferred();
    h.queue(() => phase === 'response' ? d.promise : Promise.resolve({ok: true, status: 200, text: () => d.promise}));
    const p = h.run(); await Promise.resolve();
    const count = h.calls.length; await h.run(); assert.equal(h.calls.length, count, 'busy blocks duplicate run');
    if (invalidate === 'input') h.edit('{changed');
    else if (invalidate === 'clear') h.el('clear').fire('click');
    else if (invalidate === 'refresh') {h.edit('{}'); await h.refresh();}
    else if (invalidate === 'disconnect') h.connect(false);
    else h.change({[invalidate]: 'new'});
    const before = h.el('status').textContent;
    d.resolve(phase === 'response' ? response('{"status":"COMPUTED_EXPERIMENTAL","secret":9007199254740993}') : '{"status":"COMPUTED_EXPERIMENTAL","secret":9007199254740993}');
    await p; assert.equal(h.el('result').textContent, ''); assert.equal(h.el('status').textContent, before);
    if (!['input', 'refresh'].includes(invalidate)) assert.equal(h.el('input').value, '');
  });
}
for (const phase of ['response', 'text']) test('catalog text await detects unsynced context change: ' + phase, async () => {
  const h = harness(), d = deferred(); h.edit('{}');
  h.queue(() => phase === 'response' ? d.promise : Promise.resolve({ok: true, text: () => d.promise}));
  const p = h.el('refresh').fire('click'); await Promise.resolve(); h.change({project: 'other'}, false);
  d.resolve(phase === 'response' ? response(catalogRaw) : catalogRaw); await p;
  assert.equal(h.el('catalog').textContent, ''); assert.equal(h.el('input').value, ''); assert.equal(h.el('run').disabled, true);
});
test('all sensitive state clears on every context dimension or disconnect; reconnect requires explicit refresh', async () => {
  for (const key of ['generation', 'project', 'organization', 'token', 'disconnect']) {
    const h = await ready(); h.queue(async () => response(JSON.stringify(recognized('MODEL_INAPPLICABLE')))); await h.run();
    if (key === 'disconnect') h.connect(false); else h.change({[key]: 'other'});
    for (const name of ['catalog', 'result']) assert.equal(h.el(name).textContent, '');
    assert.equal(h.el('input').value, ''); assert.equal(h.el('run').disabled, true);
    const count = h.calls.length; h.connect(true); h.mounted.syncContext(); assert.equal(h.calls.length, count);
  }
});

test('capture outer bundle preserves all three raw strings for all four recognized statuses', async () => {
  for (const status of statuses) {
    const h = harness();
    const rawCatalog = ' \n{"native":9007199254740993,"zero":-0.0,"micro":"µ","duplicate":1,"duplicate":2,' + catalogRaw.trim().slice(1) + '\n ';
    h.queue(async () => response(rawCatalog)); await h.refresh();
    const rawRequest = ' \n{"native":9007199254740993,"zero":-0.0,"micro":"µ","duplicate":1,"duplicate":2,"text":"é😀"}\n ';
    const rawResponse = ' \n{"native":9007199254740993,"zero":-0.0,"micro":"µ","duplicate":1,"duplicate":2,"hash":"unverified-producer-hash",' + JSON.stringify(recognized(status)).slice(1) + '\n ';
    h.edit(rawRequest); h.queue(async () => response(rawResponse, 201)); await h.run();
    assert.equal(h.saves.length, 0, 'no automatic save');
    assert.equal(h.el('download').disabled, false);
    const count = h.calls.length; await h.download(); assert.equal(h.calls.length, count, 'download performs no request or evaluation');
    assert.equal(h.saves.length, 1);
    const {blob, filename} = h.saves[0];
    assert.ok(blob instanceof Blob); assert.equal(blob.type, 'application/json;charset=utf-8');
    assert.equal(filename, 'polar-rotor-browser-capture.json');
    const envelope = JSON.parse(await blob.text());
    assert.deepEqual(Object.keys(envelope).sort(), ['schema_version', 'description', 'evaluation', 'response_schema_version', 'status', 'http_status', 'raw_catalog_json', 'raw_request_json', 'raw_response_json'].sort());
    assert.equal(envelope.schema_version, 'browser_capture_v1');
    assert.equal(envelope.description, 'Unverified local browser capture. Not a retained project study or server-attested execution record; embedded hashes are unverified producer data. No independent physical or computational verification, numerical qualification, installed-aircraft validation, feasibility, flight or safety qualification.');
    assert.equal(envelope.evaluation, actualCatalog.catalog.evaluation);
    assert.equal(envelope.response_schema_version, actualCatalog.catalog.schema_version);
    assert.equal(envelope.status, status); assert.equal(envelope.http_status, 201);
    for (const key of ['raw_catalog_json', 'raw_request_json', 'raw_response_json']) assert.equal(typeof envelope[key], 'string');
    assert.equal(envelope.raw_catalog_json, rawCatalog);
    assert.equal(envelope.raw_request_json, rawRequest);
    assert.equal(envelope.raw_response_json, rawResponse);
    assert.equal(h.calls.at(-1).options.body, rawRequest);
    assert.doesNotMatch(await blob.text(), /unit-token|unit-org|timestamp|generation|credentials/);
    assert.deepEqual(h.urlEvents, [], 'injected saver uses no object URL');
  }
});

test('initial and unknown, malformed or mismatched identities cannot export; successful HTTP stays raw', async () => {
  const initial = harness(); assert.equal(initial.el('download').disabled, true);
  await initial.download(); assert.equal(initial.saves.length, 0); assert.equal(initial.calls.length, 0);
  const valid = recognized();
  for (const raw of ['not JSON', 'null', '[]', JSON.stringify([valid]), JSON.stringify({result: valid}),
    JSON.stringify({...valid, status: 'UNKNOWN'}), JSON.stringify({...valid, status: null}),
    JSON.stringify({status: valid.status}), JSON.stringify({...valid, evaluation: 'other'}),
    JSON.stringify({...valid, schema_version: 'other'})]) {
    const h = await ready(); h.queue(async () => response(raw)); await h.run();
    assert.equal(h.el('result').textContent, raw); assert.equal(h.el('result').hidden, false);
    assert.equal(h.el('download').disabled, true); assert.match(h.el('capture-status').textContent, /Capture unavailable/);
    await h.download(); assert.equal(h.saves.length, 0);
  }
});

test('input, clear, refresh, context dimensions and disconnect invalidate a current capture', async () => {
  for (const mutation of ['input', 'clear', 'refresh', 'generation', 'token', 'organization', 'project', 'disconnect']) {
    const h = await ready(); h.queue(async () => response(JSON.stringify(recognized()))); await h.run();
    assert.equal(h.el('download').disabled, false);
    if (mutation === 'input') h.edit('{changed}');
    else if (mutation === 'clear') h.el('clear').fire('click');
    else if (mutation === 'refresh') await h.refresh();
    else if (mutation === 'disconnect') h.connect(false, false);
    else h.change({[mutation]: 'changed'}, false);
    await h.download();
    assert.equal(h.el('download').disabled, true); assert.equal(h.saves.length, 0);
    assert.equal(h.el('result').textContent, '');
    assert.equal(h.el('states').hidden, true);
    assert.equal(h.el('states').children.length, 0);
  }
});

test('starting a new run removes old capture and failed runs cannot restore it', async () => {
  for (const failure of ['network', 'http', 'text']) {
    const h = await ready(); h.queue(async () => response(JSON.stringify(recognized()))); await h.run();
    const d = deferred(); h.queue(() => d.promise); const pending = h.run();
    assert.equal(h.el('download').disabled, true); assert.equal(h.el('result').textContent, '');
    await h.download(); assert.equal(h.saves.length, 0);
    if (failure === 'network') d.reject(new Error('PRIVATE_RUN_SECRET'));
    else if (failure === 'http') d.resolve(response(JSON.stringify(recognized()), 422));
    else d.resolve({ok: true, status: 200, text: async () => {throw new Error('PRIVATE_RUN_SECRET');}});
    await pending; await h.download();
    assert.equal(h.el('download').disabled, true); assert.equal(h.saves.length, 0);
    assert.doesNotMatch(h.el('status').textContent, /PRIVATE_RUN_SECRET/);
  }
});

test('programmatic input mismatch without an input event refuses capture on click', async () => {
  const h = await ready(); h.queue(async () => response(JSON.stringify(recognized()))); await h.run();
  h.el('input').value = ' {"edited":true} ';
  const count = h.calls.length; await h.download();
  assert.equal(h.calls.length, count); assert.equal(h.saves.length, 0);
  assert.equal(h.el('download').disabled, true); assert.equal(h.el('result').textContent, '');
  assert.match(h.el('capture-status').textContent, /Capture unavailable/);
});

test('injected save failures disclose only generic text', async () => {
  for (const asynchronous of [false, true]) {
    const h = harness(true, {saveCapture: () => {
      if (asynchronous) return Promise.reject(new Error('PRIVATE_DOWNLOAD_SECRET'));
      throw new Error('PRIVATE_DOWNLOAD_SECRET');
    }});
    await h.refresh(); h.edit('{}'); h.queue(async () => response(JSON.stringify(recognized()))); await h.run();
    const count = h.calls.length; await h.download();
    assert.equal(h.calls.length, count);
    assert.match(h.el('capture-status').textContent, /download failed/);
    assert.doesNotMatch(h.el('capture-status').textContent, /PRIVATE_DOWNLOAD_SECRET/);
    assert.deepEqual(h.urlEvents, []);
  }
});

test('default saver uses Blob and temporary anchor with URL cleanup, including failures (DOM double)', async () => {
  for (const failAt of [undefined, 'create', 'anchor', 'append', 'click', 'remove']) {
    const h = harness(true, {defaultSave: true, failAt});
    await h.refresh(); h.edit('{}'); h.queue(async () => response(JSON.stringify(recognized()))); await h.run();
    assert.equal(h.saves.length, 0); const count = h.calls.length; await h.download();
    assert.equal(h.calls.length, count); assert.equal(h.liveURLs.size, 0, 'no leaked object URL');
    if (failAt !== 'create') {
      assert.equal(h.urlEvents.at(-1), 'revoke');
      assert.ok(h.saves[0].blob instanceof Blob);
      assert.equal(h.saves[0].blob.type, 'application/json;charset=utf-8');
      assert.equal(JSON.parse(await h.saves[0].blob.text()).raw_request_json, '{}');
    }
    if (!failAt) {
      assert.deepEqual(h.urlEvents, ['create', 'append', 'click', 'remove', 'revoke']);
      const anchor = h.nodes.find(n => n.tag === 'a');
      assert.equal(anchor.download, 'polar-rotor-browser-capture.json');
      assert.equal(anchor.href, 'blob:unit-capture'); assert.equal(anchor.attached, false);
    } else {
      assert.match(h.el('capture-status').textContent, /download failed/);
      assert.doesNotMatch(h.el('capture-status').textContent, /PRIVATE_DOWNLOAD_SECRET/);
    }
  }
});

test('pending and stale response/text awaits cannot enable capture or export', async () => {
  for (const phase of ['response', 'text']) for (const invalidate of ['input', 'clear', 'refresh', 'context', 'disconnect', 'programmatic']) {
    const h = await ready(), d = deferred(), raw = JSON.stringify(recognized());
    h.queue(() => phase === 'response' ? d.promise : Promise.resolve({ok: true, status: 200, text: () => d.promise}));
    const pending = h.run(); await Promise.resolve();
    assert.equal(h.el('download').disabled, true); await h.download(); assert.equal(h.saves.length, 0);
    if (invalidate === 'input') h.edit('{changed}');
    else if (invalidate === 'clear') h.el('clear').fire('click');
    else if (invalidate === 'refresh') {h.edit('{}'); await h.refresh();}
    else if (invalidate === 'context') h.change({project: 'other'}, false);
    else if (invalidate === 'disconnect') h.connect(false, false);
    else h.el('input').value = '{programmatic}';
    d.resolve(phase === 'response' ? response(raw) : raw); await pending; await h.download();
    assert.equal(h.el('download').disabled, true); assert.equal(h.saves.length, 0);
    assert.equal(h.el('result').textContent, '');
    assert.equal(h.el('states').hidden, true);
    assert.equal(h.el('states').children.length, 0);
  }
});

