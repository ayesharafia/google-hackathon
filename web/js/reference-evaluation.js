const MODEL = 'coesa1976.lower-atmosphere.0-30km.v1';
export function mountEvaluationPanel(root, {api, readContext, isContext}) {
  const doc = root.ownerDocument;
  const el = (tag, text, cls) => {
    const node = doc.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  const panel = el('section', undefined, 'reference-evaluation');
  const heading = el('h2', 'Configuration-first reference evaluation');
  const warning = el('p', 'Architectures enumerated only; no aircraft solver or validation. Preview does not change saved project. Standard dry reference air, not local weather.', 'eval-warning');
  const form = el('form');
  const refresh = el('button', 'Refresh model catalog');
  refresh.type = 'button';
  refresh.dataset.testid = 'eval-refresh';
  const fields = el('div', undefined, 'eval-fields');
  const configuration = el('select');
  const altitude = el('input');
  altitude.type = 'number';
  altitude.min = '0';
  altitude.max = '30000';
  altitude.step = 'any';
  const kind = el('select');
  const option = (select, value, label) => {
    const item = el('option', label);
    item.value = value;
    select.append(item);
  };
  option(kind, '', 'Choose altitude kind');
  option(kind, 'geometric', 'Geometric');
  option(kind, 'geopotential', 'Geopotential');
  for (const [control, name, label] of [
    [configuration, 'configuration', 'Configuration'],
    [altitude, 'altitude', 'Altitude (m)'],
    [kind, 'kind', 'Altitude kind']
  ]) {
    control.dataset.testid = `eval-${name}`;
    const wrapper = el('label', label);
    wrapper.append(control);
    fields.append(wrapper);
  }
  const run = el('button', 'Run reference evaluation');
  run.type = 'submit';
  run.dataset.testid = 'eval-run';
  const status = el('p', 'Refresh the model catalog to begin.');
  status.dataset.testid = 'eval-status';
  status.setAttribute('role', 'status');
  const result = el('div', undefined, 'eval-result');
  result.dataset.testid = 'eval-result';
  form.append(refresh, fields, run);
  panel.append(heading, warning, form, status, result);
  root.replaceChildren(panel);
  let catalog = [], serial = 0, busy = false;
  let lastContext = readContext();
  const valid = () => catalog.some(c => c.id === configuration.value) &&
    altitude.value.trim() !== '' && Number.isFinite(Number(altitude.value)) &&
    Number(altitude.value) >= 0 && Number(altitude.value) <= 30000 &&
    ['geometric', 'geopotential'].includes(kind.value);
  const controls = () => { run.disabled = busy || !valid(); refresh.disabled = busy; };
  const resetCatalog = () => {
    catalog = [];
    configuration.replaceChildren();
    option(configuration, '', 'Choose configuration');
  };
  const clear = () => { serial++; busy = false; result.replaceChildren(); controls(); };
  const current = ticket => ticket.serial === serial && isContext(ticket.context);
  const call = async (path, options) => {
    const response = await api(path, options);
    if (response && typeof response.json === 'function') {
      const data = await response.json();
      if (!response.ok && !['MODEL_INAPPLICABLE', 'SOLVER_UNSUPPORTED'].includes(data?.status)) throw new Error('HTTP failure');
      return data;
    }
    return response;
  };
  const error = () => { status.textContent = 'Unable to verify the reference evaluation. Sign in and refresh the model catalog.'; };
  const edited = () => { clear(); status.textContent = 'Select explicit inputs, then run the reference evaluation.'; };
  configuration.addEventListener('change', edited);
  altitude.addEventListener('input', edited);
  kind.addEventListener('change', edited);
  refresh.addEventListener('click', async () => {
    clear(); resetCatalog(); controls();
    const ticket = {serial, context: readContext()};
    busy = true; controls(); status.textContent = 'Loading model catalog…';
    try {
      const data = await call('/evaluations/catalog', {method: 'GET'});
      if (!current(ticket)) return;
      const configs = data?.configurations;
      const models = data?.models;
      if (!Array.isArray(configs) || configs.length !== 8 ||
          !configs.every(c => typeof c?.id === 'string' && c.id.trim() && typeof c.name === 'string' && c.name.trim() && c.aircraft_solver_supported === false) ||
          new Set(configs.map(c => c.id)).size !== 8 || !Array.isArray(models) ||
          models.filter(m => m?.model_id === MODEL).length !== 1 ||
          !models.some(m => m?.model_id === MODEL && m.evaluation === 'atmosphere')) throw new Error('Invalid catalog');
      catalog = configs.map(c => ({id: c.id, name: c.name}));
      catalog.forEach(c => option(configuration, c.id, c.name));
      status.textContent = 'Catalog ready. Select all evaluation inputs.';
    } catch {
      if (!current(ticket)) return;
      resetCatalog(); error();
    } finally {
      if (current(ticket)) { busy = false; controls(); }
    }
  });
  const sameRequest = (value, request) => value && typeof value === 'object' &&
    Object.keys(value).length === Object.keys(request).length &&
    Object.keys(request).every(key => Object.hasOwn(value, key) && value[key] === request[key]);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !valid()) return;
    clear();
    const request = {configuration: configuration.value, evaluation: 'atmosphere', altitude_m: Number(altitude.value), altitude_kind: kind.value};
    const selected = catalog.find(c => c.id === request.configuration);
    const ticket = {serial, context: readContext()};
    busy = true; controls(); status.textContent = 'Computing reference evaluation…';
    try {
      const data = await call('/evaluations/evaluate', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(request)});
      if (!current(ticket)) return;
      if (!data || !sameRequest(data.inputs, request) ||
          (data.status === 'REFERENCE_COMPUTED' && data.model_id !== MODEL) || data.evidence_level !== 'unverified' ||
          data.aircraft_status !== null || data.feasibility !== null || typeof data.status !== 'string' || !data.status ||
          !Array.isArray(data.reasons) || !data.reasons.every(r => typeof r === 'string') ||
          ![data.input_sha256, data.evaluation_sha256].every(d => typeof d === 'string' && /^[a-f\d]{64}$/i.test(d))) throw new Error('Invalid response');
      const units = {pressure_pa: 'Pa', temperature_k: 'K', density_kg_m3: 'kg/m^3'};
      if (data.status === 'REFERENCE_COMPUTED' && !Object.entries(units).every(([key, unit]) =>
          typeof data.outputs?.[key] === 'number' && Number.isFinite(data.outputs[key]) && data.output_units?.[key] === unit)) throw new Error('Invalid outputs');
      const details = el('dl');
      const row = (label, value) => { details.append(el('dt', label), el('dd', String(value))); };
      row('Configuration', `${selected.name} (${selected.id})`);
      row('Model', data.model_id);
      row('Status', data.status);
      row('Evidence', 'unverified');
      row('Aircraft status', 'Unavailable');
      row('Feasibility', 'Unavailable');
      row('Input SHA-256', data.input_sha256);
      row('Evaluation SHA-256', data.evaluation_sha256);
      if (data.status === 'REFERENCE_COMPUTED') {
        for (const [key, unit] of Object.entries(units)) row(key, `${data.outputs[key]} ${unit}`);
        status.textContent = 'Reference computed; evidence remains unverified.';
      } else {
        details.append(el('dt', 'Refusal'), el('dd', 'Reference evaluation refused.'));
        status.textContent = `Reference evaluation refused: ${data.status}.`;
      }
      data.reasons.forEach(reason => row('Reason', reason));
      result.replaceChildren(details);
    } catch {
      if (!current(ticket)) return;
      result.replaceChildren(); error();
    } finally {
      if (current(ticket)) { busy = false; controls(); }
    }
  });
  const invalidate = message => {
    clear(); resetCatalog(); altitude.value = ''; kind.value = ''; controls();
    status.textContent = message == null ? 'Context changed. Refresh the model catalog.' : String(message);
    lastContext = readContext();
  };
  resetCatalog(); controls();
  return {
    invalidate,
    syncContext() {
      if (!isContext(lastContext)) invalidate();
      lastContext = readContext();
    }
  };
                      }
