// Keep caller and server JSON as text: native integers may exceed binary64 precision.
const MAX_BYTES = 1048576;
const EVALUATION = 'tabulated_solved_electrothermal_experimental';
const SCHEMA_VERSION = 'tabulated_solved_electrothermal_v1';
const STATUSES = ['COMPUTED_EXPERIMENTAL', 'MODEL_INAPPLICABLE', 'SOLVER_UNSUPPORTED', 'EXECUTION_FAILED'];
const CAPTURE_LABEL = 'Unverified local browser capture. Not a retained project study or server-attested execution record; embedded hashes are unverified producer data. No physical validation, feasibility, trim, global infeasibility, mission, flight or safety qualification.';
const CAPTURE_FILENAME = 'tabulated-solved-electrothermal-browser-capture.json';
function saveBrowserCapture(doc, blob, filename) {
  const urls = doc.defaultView.URL;
  let url, anchor;
  try {
    url = urls.createObjectURL(blob);
    anchor = doc.createElement('a');
    anchor.href = url; anchor.download = filename;
    doc.body.append(anchor); anchor.click();
  } finally {
    try { anchor?.remove(); } finally { if (url !== undefined) urls.revokeObjectURL(url); }
  }
}
function inputCheck(raw) {
  for (let i = 0; i < raw.length; i++) {
    const code = raw.charCodeAt(i);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = raw.charCodeAt(++i);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return 'Unpaired Unicode surrogate: input cannot be sent unchanged as UTF-8.';
    } else if (code >= 0xdc00 && code <= 0xdfff) return 'Unpaired Unicode surrogate: input cannot be sent unchanged as UTF-8.';
  }
  if (!raw.trim()) return 'Supply your complete caller-owned V129 request JSON.';
  if (new TextEncoder().encode(raw).byteLength > MAX_BYTES) return 'Request exceeds 1,048,576 UTF-8 bytes, including whitespace.';
  return '';
}
export function mountTabulatedSolvedElectrothermal(root, {request, readContext, isContext, isConnected, saveCapture}) {
  const doc = root.ownerDocument;
  const save = saveCapture || ((blob, filename) => saveBrowserCapture(doc, blob, filename));
  const node = (tag, text, key) => {
    const el = doc.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (key) el.dataset.testid = 'tabulated-solved-electrothermal-' + key;
    return el;
  };
  const panel = node('details');
  panel.className = 'tabulated-solved-electrothermal';
  panel.append(node('summary', 'Advanced: coupled solved electrothermal request JSON'));
  panel.append(node('p', 'Independent standalone caller JSON, separate from saved project inputs; this is not a complete configuration wizard. Supply your complete V129 request with your own tables, sources, properties and prescribed chronology. No defaults or automatic model selection. Nothing here is autosaved.'));
  panel.append(node('p', 'Coupled bounded static point solve, DC power, prescribed chronology and one-way allocated heat with caller-declared properties. Any residual unmet retains all ordered points and skips energy/thermal output. HTTP 200 does not mean physical success. Full catalog and child limitations apply.'));
  const refresh = node('button', 'Refresh catalog', 'refresh'); refresh.type = 'button';
  const catalogDetails = node('details'); catalogDetails.append(node('summary', 'Full raw catalog and limitations'));
  const catalogText = node('pre', '', 'catalog'); catalogDetails.append(catalogText);
  const label = node('label', 'Complete caller-owned request JSON');
  const input = node('textarea', undefined, 'input'); input.rows = 12; input.spellcheck = false;
  input.autocomplete = 'off'; input.setAttribute('aria-describedby', 'tabulated-solved-electrothermal-help');
  label.append(input);
  const help = node('p', 'Sent exactly as entered. Maximum 1,048,576 UTF-8 bytes including whitespace. The server owns strict JSON parsing, duplicate-key rejection, schema and scientific admission.');
  help.id = 'tabulated-solved-electrothermal-help';
  const run = node('button', 'Run supplied request', 'run'); run.type = 'button';
  const clear = node('button', 'Clear JSON and results', 'clear'); clear.type = 'button';
  const download = node('button', 'Download current raw evidence', 'download'); download.type = 'button';
  const captureStatus = node('p', 'Capture unavailable. Run a fresh recognized response first.', 'capture-status');
  captureStatus.setAttribute('role', 'status');
  const actions = node('div'); actions.className = 'tabulated-solved-electrothermal-actions'; actions.append(refresh, run, clear, download);
  const status = node('p', '', 'status'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const result = node('pre', '', 'result'); result.hidden = true;
  panel.append(actions, catalogDetails, label, help, status, result, node('p', CAPTURE_LABEL), captureStatus); root.append(panel);
  let ctx = readContext(), online = Boolean(isConnected()), serial = 0, busy = false, catalogReady = false;
  let capture = null;
  function eraseResult() {
    capture = null; result.textContent = ''; result.hidden = true;
    captureStatus.textContent = 'Capture unavailable. Run a fresh recognized response first.';
  }
  function controls() {
    refresh.disabled = busy || !online;
    run.disabled = busy || !online || !catalogReady || Boolean(inputCheck(input.value));
    download.disabled = busy || !online || !capture || capture.id !== serial || input.value !== capture.rawRequest;
    panel.setAttribute('aria-busy', String(busy));
  }
  function syncContext() {
    const connected = Boolean(isConnected());
    if (!isContext(ctx) || connected !== online) {
      ctx = readContext(); online = connected; ++serial; busy = false; catalogReady = false;
      input.value = ''; catalogText.textContent = ''; eraseResult();
      status.textContent = online ? 'Context changed. Refresh the catalog and supply a new request.' : 'Connect the workspace, then explicitly refresh the catalog.';
    }
    controls();
  }
  function current(id, snapshot) {
    if (!isContext(snapshot) || Boolean(isConnected()) !== online) { syncContext(); return false; }
    return id === serial && online;
  }
  input.addEventListener('input', () => {
    syncContext(); ++serial; busy = false; eraseResult();
    status.textContent = inputCheck(input.value) || (catalogReady ? 'Request text available. Server admission has not run.' : 'Refresh the catalog before running.'); controls();
  });
  clear.addEventListener('click', () => {
    syncContext(); ++serial; busy = false; input.value = ''; eraseResult();
    status.textContent = 'Request JSON and results cleared.'; controls();
  });
  refresh.addEventListener('click', async () => {
    syncContext(); if (busy || !online) return;
    const snapshot = readContext(), id = ++serial;
    busy = true; catalogReady = false; catalogText.textContent = ''; eraseResult(); controls();
    status.textContent = 'Fetching a fresh catalog…';
    try {
      const response = await request('/tabulated-solved-electrothermal/catalog');
      if (!current(id, snapshot)) return;
      const raw = await response.text();
      if (!current(id, snapshot)) return;
      catalogText.textContent = raw;
      const data = JSON.parse(raw);
      catalogReady = response.ok && data?.catalog?.evaluation === EVALUATION &&
        data.catalog.schema_version === SCHEMA_VERSION &&
        Array.isArray(data.catalog.limitations) && data.transport?.limits?.body_bytes === MAX_BYTES;
      status.textContent = catalogReady ? 'Fresh catalog available. Review its full limitations before running.' : 'Catalog identity unavailable. Running is disabled.';
    } catch {
      if (current(id, snapshot)) status.textContent = 'Catalog refresh failed. Check the connection and retry.';
    } finally { if (current(id, snapshot)) { busy = false; controls(); } }
  });
  run.addEventListener('click', async () => {
    syncContext(); if (busy || !online || !catalogReady || inputCheck(input.value)) return;
    const snapshot = readContext(), id = ++serial, raw = input.value, rawCatalog = catalogText.textContent;
    busy = true; eraseResult(); controls(); status.textContent = 'Submitting supplied request…';
    try {
      const response = await request('/tabulated-solved-electrothermal/evaluate', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: raw});
      if (!current(id, snapshot)) return;
      const text = await response.text();
      if (!current(id, snapshot)) return;
      if (input.value !== raw) { eraseResult(); status.textContent = 'Request text changed. Run the current input again.'; return; }
      if (!response.ok) throw new Error();
      result.textContent = text; result.hidden = false;
      let data;
      try { data = JSON.parse(text); } catch { /* Full raw result remains visible. */ }
      const topStatus = data?.status;
      if (data && !Array.isArray(data) && data.evaluation === EVALUATION &&
          data.schema_version === SCHEMA_VERSION && STATUSES.includes(topStatus)) {
        capture = {id, snapshot, rawCatalog, rawRequest: raw, rawResponse: text, httpStatus: response.status, status: topStatus};
        captureStatus.textContent = 'Current raw evidence available for explicit local download. ' + CAPTURE_LABEL;
      }
      status.textContent = 'HTTP ' + response.status + ' · structured workflow status: ' + (STATUSES.includes(topStatus) ? topStatus : 'unrecognized or unavailable') + '. HTTP 200 alone establishes neither computational nor physical success. Full raw response follows.';
    } catch {
      if (current(id, snapshot)) { eraseResult(); status.textContent = 'Request failed. Check connection and server admission requirements, then retry.'; }
    } finally { if (current(id, snapshot)) { busy = false; controls(); } }
  });
  download.addEventListener('click', async () => {
    syncContext();
    if (busy || !online || !capture) return;
    if (capture.id !== serial || !isContext(capture.snapshot) || input.value !== capture.rawRequest) {
      eraseResult(); controls(); return;
    }
    const saved = capture;
    try {
      // Serialize only the outer envelope. Embedded JSON stays exactly as captured.
      const envelope = JSON.stringify({
        schema_version: 'browser_capture_v1', description: CAPTURE_LABEL,
        evaluation: EVALUATION, response_schema_version: SCHEMA_VERSION,
        status: saved.status, http_status: saved.httpStatus,
        raw_catalog_json: saved.rawCatalog, raw_request_json: saved.rawRequest,
        raw_response_json: saved.rawResponse,
      }, null, 2);
      await save(new Blob([envelope], {type: 'application/json;charset=utf-8'}), CAPTURE_FILENAME);
    } catch {
      if (capture === saved && current(saved.id, saved.snapshot)) captureStatus.textContent = 'Local capture download failed. Retry the explicit download.';
    }
  });
  status.textContent = online ? 'Explicitly refresh the catalog, then supply your request JSON.' : 'Connect the workspace, then explicitly refresh the catalog.';
  controls();
  return {syncContext};
}
