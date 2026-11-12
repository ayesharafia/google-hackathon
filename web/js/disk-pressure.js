import {projectDiskPressure, renderDiskPressurePostpro} from './disk-pressure-postpro.js';

const MAX_BYTES = 16777216;
const EXPORT_SCHEMA = 'polar_rotor_disk_pressure_export_v1';
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const need = condition => {if (!condition) throw new Error('report unavailable');};
function same(left, right) {
  if (Object.is(left, right)) return true;
  if (!left || !right || typeof left !== 'object' || typeof right !== 'object' || Array.isArray(left) !== Array.isArray(right)) return false;
  const keys = Object.keys(left);
  return keys.length === Object.keys(right).length && keys.every(key => Object.hasOwn(right, key) && same(left[key], right[key]));
}
function inputCheck(raw) {
  for (let i = 0; i < raw.length; i++) {
    const code = raw.charCodeAt(i);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = raw.charCodeAt(++i);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return 'Unpaired Unicode surrogate: input cannot be sent unchanged as UTF-8.';
    } else if (code >= 0xdc00 && code <= 0xdfff) return 'Unpaired Unicode surrogate: input cannot be sent unchanged as UTF-8.';
  }
  if (!raw.trim()) return 'Paste a complete sealed polar-rotor response JSON.';
  if (new TextEncoder().encode(raw).byteLength > MAX_BYTES) return 'Request exceeds 16,777,216 UTF-8 bytes, including whitespace.';
  return '';
}
function withGeometry(data, raw) {
  try {
    const source = JSON.parse(raw), rows = source.outputs.annuli, units = source.output_units.annuli;
    need(source.evaluation === 'polar_rotor_experimental' && source.schema_version === 'polar_rotor_v1');
    need(Array.isArray(rows) && rows.length <= 8 && rows.length === data.outputs.annuli.length &&
      Array.isArray(units) && units.length === rows.length && data.output_units.annuli.length === rows.length);
    rows.forEach((row, index) => need(row.annulus_index === index));
    // View-only copies: V142 deliberately contains no radii. Keep its raw response intact for export.
    return {...data, outputs: {...data.outputs, annuli: data.outputs.annuli.map((row, index) => ({...row,
      radial_inner_m: rows[index].radial_inner_m, radial_outer_m: rows[index].radial_outer_m}))},
    output_units: {...data.output_units, annuli: data.output_units.annuli.map((row, index) => ({...row,
      radial_inner_m: units[index].radial_inner_m, radial_outer_m: units[index].radial_outer_m}))}};
  } catch {return data;}
}
// Canonicalize object-key order while preserving producer numeric tokens (1.0, -0.0, etc.).
// JSON.stringify on parsed Numbers would change Python's canonical bytes and their advertised digest.
function reportText(raw) {
  const tokens = raw.match(/"(?:[^"\\]|\\[\s\S])*"|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null|[{}\[\]:,]|\S/g) || [];
  let position = 0, nodes = 0;
  function take(expected) {need(tokens[position++] === expected);}
  function parse(depth = 0) {
    need(depth <= 40 && ++nodes <= 262144);
    const token = tokens[position++];
    if (token === '{') {
      const fields = new Map();
      if (tokens[position] !== '}') {
        do {
          if (fields.size) take(',');
          const key = JSON.parse(tokens[position++]); need(typeof key === 'string' && !fields.has(key));
          take(':'); fields.set(key, parse(depth + 1)); need(fields.size <= 256);
        } while (tokens[position] !== '}');
      }
      take('}');
      const keys = [...fields.keys()].sort((left, right) => {
        const a = Array.from(left, c => c.codePointAt(0)), b = Array.from(right, c => c.codePointAt(0));
        for (let i = 0; i < Math.min(a.length, b.length); i++) if (a[i] !== b[i]) return a[i] - b[i];
        return a.length - b.length;
      });
      return {fields, text: '{' + keys.map(key => JSON.stringify(key) + ':' + fields.get(key).text).join(',') + '}'};
    }
    if (token === '[') {
      const values = [];
      if (tokens[position] !== ']') {
        do {if (values.length) take(','); values.push(parse(depth + 1).text); need(values.length <= 256);} while (tokens[position] !== ']');
      }
      take(']'); return {text: '[' + values.join(',') + ']'};
    }
    need(token !== undefined);
    const value = JSON.parse(token);
    need(value === null || ['string', 'boolean', 'number'].includes(typeof value));
    return {text: typeof value === 'string' ? JSON.stringify(value) : token};
  }
  const tree = parse(); need(position === tokens.length);
  return tree.fields.get('outputs').fields.get('report').text;
}
function saveReport(doc, text) {
  const urls = doc.defaultView.URL;
  let url, anchor;
  try {
    url = urls.createObjectURL(new Blob([text], {type: 'application/json;charset=utf-8'}));
    anchor = doc.createElement('a'); anchor.href = url; anchor.download = 'disk-pressure-report.json';
    doc.body.append(anchor); anchor.click();
  } finally {
    try {anchor?.remove();} finally {if (url !== undefined) urls.revokeObjectURL(url);}
  }
}
export function mountDiskPressure(root, {request, isConnected, readContext = () => null, isContext = () => true, getRotorResponse}) {
  const doc = root.ownerDocument;
  const node = (tag, text, key) => {
    const el = doc.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (key) el.dataset.testid = 'disk-pressure-' + key;
    return el;
  };
  const panel = node('details'); panel.className = 'polar-rotor disk-pressure';
  panel.append(node('summary', 'Derived disk pressure · supplied rotor response'));
  const label = node('label', 'Complete sealed polar-rotor response JSON');
  const input = node('textarea', undefined, 'input'); input.rows = 12; input.spellcheck = false; input.autocomplete = 'off';
  input.setAttribute('aria-describedby', 'disk-pressure-help'); label.append(input);
  const help = node('p', 'Sent exactly as entered, up to 16,777,216 UTF-8 bytes. The server rejects malformed JSON, duplicate keys and nonfinite constants. HTTP 200 alone establishes neither computational nor physical success. No private project study is saved.');
  help.id = 'disk-pressure-help';
  const prefill = typeof getRotorResponse === 'function' ? node('button', 'Use current polar-rotor result', 'prefill') : null;
  if (prefill) prefill.type = 'button';
  const run = node('button', 'Derive disk pressure', 'run'); run.type = 'button';
  const exportButton = node('button', 'Export canonical report', 'export'); exportButton.type = 'button';
  const download = node('button', 'Download canonical report', 'download'); download.type = 'button';
  const clear = node('button', 'Clear JSON and results', 'clear'); clear.type = 'button';
  const actions = node('div'); actions.className = 'polar-rotor-actions';
  if (prefill) actions.append(prefill);
  actions.append(run, exportButton, download, clear);
  const status = node('p', '', 'status'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const projection = node('div', undefined, 'postpro');
  const result = node('pre', '', 'result'); result.hidden = true;
  const metadata = node('p', '', 'report-status'); metadata.setAttribute('role', 'status');
  panel.append(label, help, actions, status, projection, node('h4', 'Full raw derivation response'), result, metadata);
  root.append(panel);
  let online = Boolean(isConnected()), ctx = readContext(), serial = 0, busy = false, derivation = null, report = null;
  function erase() {
    derivation = null; report = null; result.textContent = ''; result.hidden = true; metadata.textContent = '';
    renderDiskPressurePostpro(projection, undefined);
  }
  function controls() {
    if (prefill) prefill.disabled = busy || !online || rotorResponseText() === null;
    run.disabled = busy || !online || Boolean(inputCheck(input.value));
    exportButton.disabled = busy || !online || !derivation || derivation.rawRequest !== input.value;
    download.disabled = busy || !online || !report || !derivation || derivation.rawRequest !== input.value;
    clear.disabled = busy; panel.setAttribute('aria-busy', String(busy));
  }
  function syncContext() {
    const connected = Boolean(isConnected());
    if (!isContext(ctx) || connected !== online) {
      ctx = readContext(); online = connected; ++serial; busy = false; input.value = ''; erase();
      status.textContent = online ? 'Context changed. Supply a fresh rotor response.' : 'Connect the workspace, then supply a rotor response.';
    }
    controls();
  }
  function current(id, snapshot) {
    if (!isContext(snapshot) || Boolean(isConnected()) !== online) {syncContext(); return false;}
    return online && id === serial;
  }
  function httpFailure(response) {
    return 'HTTP ' + response.status + (response.status === 422 ? ' · Invalid disk pressure request.' : ' · Disk pressure request failed.');
  }
  function rotorResponseText() {
    try {const text = getRotorResponse(); return typeof text === 'string' ? text : null;} catch {return null;}
  }
  function inputChanged(message) {
    ++serial; busy = false; erase();
    status.textContent = message || inputCheck(input.value) || 'Input available. Explicitly derive to continue.'; controls();
  }
  input.addEventListener('input', () => {
    syncContext(); inputChanged();
  });
  if (prefill) {
    doc.addEventListener('polar-rotor-capture-changed', syncContext);
    // Refresh freshness on panel interaction; no polling, requests or automatic derivation.
    root.addEventListener('pointerenter', syncContext);
    root.addEventListener('focusin', syncContext);
    prefill.addEventListener('click', () => {
      syncContext(); if (busy || !online) return;
      const text = rotorResponseText();
      if (text === null) {
        erase(); status.textContent = 'No fresh polar-rotor result available. Run the polar-rotor panel first, or paste a sealed response.'; controls(); return;
      }
      input.value = text; inputChanged('Polar-rotor result loaded. Explicitly derive to continue.');
    });
  }
  clear.addEventListener('click', () => {
    syncContext(); if (busy) return;
    ++serial; input.value = ''; erase(); status.textContent = 'JSON and results cleared.'; controls();
  });
  run.addEventListener('click', async () => {
    syncContext(); if (busy || !online || inputCheck(input.value)) return;
    const id = ++serial, snapshot = readContext(), raw = input.value;
    busy = true; erase(); controls(); status.textContent = 'Deriving from the supplied rotor response…';
    try {
      const response = await request('/disk-pressure/derive', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: raw});
      if (!current(id, snapshot)) return;
      if (response.status !== 200) {status.textContent = httpFailure(response); return;}
      const text = await response.text();
      if (!current(id, snapshot)) return;
      if (input.value !== raw) {erase(); status.textContent = 'Input changed. Derive again.'; return;}
      need(new TextEncoder().encode(text).byteLength <= MAX_BYTES);
      result.textContent = text; result.hidden = false;
      let data; try {data = JSON.parse(text);} catch { /* Keep raw text authoritative. */ }
      const view = renderDiskPressurePostpro(projection, withGeometry(data, raw));
      if (view.available) derivation = {rawRequest: raw, rawResponse: text, data};
      status.textContent = 'HTTP 200 · ' + (view.available ? 'Producer-reported derivation available.' : 'Derivation presentation unavailable.') + ' No independent verification; full raw JSON follows.';
    } catch {
      if (current(id, snapshot)) {erase(); status.textContent = 'Disk pressure request failed. Check the connection and retry.';}
    } finally {if (current(id, snapshot)) {busy = false; controls();}}
  });
  exportButton.addEventListener('click', async () => {
    syncContext(); if (busy || !online || !derivation || derivation.rawRequest !== input.value) return;
    const id = ++serial, snapshot = readContext(), saved = derivation;
    busy = true; report = null; metadata.textContent = ''; controls(); status.textContent = 'Exporting the current derivation…';
    try {
      // Send the exact V142 response text: reserializing Numbers could break its native seal.
      const response = await request('/disk-pressure/export', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: saved.rawResponse});
      if (!current(id, snapshot)) return;
      if (response.status !== 200) {status.textContent = httpFailure(response); return;}
      const raw = await response.text();
      if (!current(id, snapshot)) return;
      if (input.value !== saved.rawRequest) {erase(); status.textContent = 'Input changed. Derive again.'; return;}
      need(new TextEncoder().encode(raw).byteLength <= MAX_BYTES);
      const data = JSON.parse(raw), out = data.outputs, source = saved.data;
      need(data.evaluation === 'polar_rotor_disk_pressure_export' && data.schema_version === EXPORT_SCHEMA &&
        data.status === 'COMPUTED_EXPERIMENTAL' && data.disk_pressure_report_state === 'EXPORTED' && record(out));
      need(typeof out.report_canonical_sha256 === 'string' && /^[0-9a-f]{64}$/.test(out.report_canonical_sha256) &&
        Number.isSafeInteger(out.report_bytes) && out.report_bytes > 0 && out.report_bytes <= MAX_BYTES);
      const value = out.report;
      need(record(value) && value.title === 'Derived idealized actuator-disk pressure report' &&
        value.schema_version === EXPORT_SCHEMA && value.state_text === source.state_text &&
        value.derivation === source.outputs.derivation && value.input_digest === source.outputs.input_digest &&
        value.source_request_sha256 === source.request_sha256 && value.source_evaluation_sha256 === source.evaluation_sha256 &&
        Array.isArray(value.limitations) && same(value.limitations, source.limitations) &&
        same(value.output_units, source.output_units) && same(value.annuli, source.outputs.annuli) &&
        value.rotor_mean_disk_loading_pa === source.outputs.rotor_mean_disk_loading_pa &&
        value.rotor_active_annular_loading_pa === source.outputs.rotor_active_annular_loading_pa);
      const text = reportText(raw); need(new TextEncoder().encode(text).byteLength === out.report_bytes);
      report = {text};
      metadata.textContent = 'Producer-reported report_canonical_sha256: ' + out.report_canonical_sha256 + ' · report_bytes: ' + out.report_bytes + '. Digests are not independently verified and do not authenticate provenance.';
      status.textContent = 'Report available for explicit download.';
    } catch {
      if (current(id, snapshot)) {report = null; metadata.textContent = ''; status.textContent = 'Report export unavailable. No download is offered.';}
    } finally {if (current(id, snapshot)) {busy = false; controls();}}
  });
  download.addEventListener('click', () => {
    syncContext(); if (busy || !online || !report || !derivation || derivation.rawRequest !== input.value) return;
    try {saveReport(doc, report.text);} catch {metadata.textContent = 'Report download failed. Retry the explicit download.';}
  });
  erase(); status.textContent = online ? 'Paste a sealed rotor response, then explicitly derive.' : 'Connect the workspace, then supply a rotor response.';
  controls(); return {syncContext};
}
