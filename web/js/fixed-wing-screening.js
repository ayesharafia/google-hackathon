const CONFIG = Object.freeze({configuration:'fixed_wing',evaluation:'fixed_wing_aerodynamic_screening'});
const PHYSICS = [
  ['density_kg_m3','Air density (kg/m³)'],['airspeed_m_s','Airspeed (m/s)'],
  ['wing_area_m2','Wing area (m²)'],['span_m','Wingspan (m)'],
  ['characteristic_length_m','Characteristic length (m)'],['dynamic_viscosity_pa_s','Dynamic viscosity (Pa·s)'],
  ['speed_of_sound_m_s','Speed of sound (m/s)'],['lift_coefficient','Lift coefficient CL (dimensionless)'],
  ['zero_lift_drag_coefficient','Zero-lift drag coefficient CD₀ (dimensionless)'],['span_efficiency','Span efficiency (dimensionless; > 0, ≤ 1)']
];
const ENVELOPE = [
  ['mach_min','Minimum Mach (dimensionless)'],['mach_max','Maximum Mach (dimensionless)'],
  ['reynolds_min','Minimum Reynolds number (dimensionless)'],['reynolds_max','Maximum Reynolds number (dimensionless)'],
  ['lift_coefficient_min','Minimum lift coefficient (dimensionless)'],['lift_coefficient_max','Maximum lift coefficient (dimensionless)']
];
const OUTPUTS = [
  ['dynamic_pressure_pa','Dynamic pressure q','Pa'],['aspect_ratio','Aspect ratio AR','1'],
  ['induced_drag_coefficient','Induced drag coefficient CDi','1'],['drag_coefficient','Drag coefficient CD','1'],
  ['lift_n','Lift L','N'],['drag_n','Drag D','N'],['drag_power_w','Aerodynamic drag power D × V','W'],
  ['reynolds_number','Reynolds number Re','1'],['mach_number','Mach number','1']
];
function exact(a,b) {
  if (a === b) return true;
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object' || Array.isArray(a) || Array.isArray(b)) return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every(k => Object.hasOwn(b,k) && exact(a[k],b[k]));
}
export function mountFixedWing(root,{api,readContext,isContext}) {
  const doc = root.ownerDocument;
  const node = (tag,text,cls) => { const n = doc.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
  const test = (n,id) => { n.setAttribute('data-testid',id); return n; };
  const main = node('section',undefined,'fixed-wing-screening');
  main.append(node('h2','Fixed-wing aerodynamic screening'),node('p','Configuration is fixed-wing; evaluation uses supplied aerodynamic coefficients.'));
  main.append(node('p','Supplied coefficients and the declared envelope are unverified. No stall, trim, propulsion, aircraft feasibility, or validation assessment is provided. Drag power is aerodynamic D × V, not shaft or electrical power.','wing-warning'));
  const form = node('form'); form.noValidate = true;
  const grid = node('div',undefined,'wing-grid'), fields = new Map();
  function field([key,label],parent) {
    const wrap = node('label'), input = test(node('input'),'wing-'+key);
    input.type = 'number'; input.step = 'any'; input.required = true; input.name = key;
    wrap.append(node('span',label),input); parent.append(wrap); fields.set(key,input);
  }
  PHYSICS.forEach(f => field(f,grid));
  const envelope = node('details'); envelope.open = true;
  envelope.append(node('summary','Coefficient envelope (all bounds required)'));
  const boundsGrid = node('div',undefined,'wing-grid'); ENVELOPE.forEach(f => field(f,boundsGrid)); envelope.append(boundsGrid);
  const sourceLabel = node('label'), source = test(node('textarea'),'wing-source');
  source.required = true; source.name = 'coefficient_source'; source.rows = 4;
  sourceLabel.append(node('span','Coefficient source declaration (1–2000 characters; explain provenance and applicability)'),source);
  const run = test(node('button','Run aerodynamic screening'),'wing-run'); run.type = 'submit'; run.disabled = true;
  const status = test(node('p','Enter all inputs and declare the coefficient source.'),'wing-status');
  status.setAttribute('role','status'); status.setAttribute('aria-live','polite');
  const result = test(node('div',undefined,'wing-result'),'wing-result'); result.hidden = true;
  form.append(grid,envelope,sourceLabel,run); main.append(form,status,result); root.append(main);
  let serial = 0, busy = false, context = readContext();
  function request() {
    const values = {};
    for (const [key,input] of fields) {
      if (!input.value.trim() || input.validity.badInput) return null;
      const value = Number(input.value); if (!Number.isFinite(value)) return null; values[key] = value;
    }
    if (PHYSICS.slice(0,7).some(([key]) => values[key] <= 0)) return null;
    if (values.zero_lift_drag_coefficient < 0 || values.span_efficiency <= 0 || values.span_efficiency > 1) return null;
    if (values.mach_min < 0 || values.reynolds_min <= 0) return null;
    if (['mach','reynolds','lift_coefficient'].some(k => values[k+'_max'] < values[k+'_min'])) return null;
    if (!source.value.trim() || Array.from(source.value).length > 2000) return null;
    return {...CONFIG,...Object.fromEntries(PHYSICS.map(([k]) => [k,values[k]])),coefficient_source:source.value,
      coefficient_envelope:Object.fromEntries(ENVELOPE.map(([k]) => [k,values[k]]))};
  }
  function clearResult() { result.replaceChildren(); result.hidden = true; }
  function refresh() { run.disabled = busy || !request(); }
  function syncContext() {
    if (isContext(context)) return false;
    context = readContext(); ++serial; busy = false;
    fields.forEach(input => { input.value = ''; }); source.value = ''; clearResult(); refresh();
    status.textContent = 'Context changed. Sign in and re-enter all inputs.'; return true;
  }
  form.addEventListener('input',() => {
    syncContext(); ++serial; busy = false; clearResult(); refresh();
    status.textContent = request() ? 'Ready to screen supplied coefficients.' : 'Enter all required values, valid ranges, and a coefficient source.';
  });
  function current(id,snapshot) {
    if (!isContext(snapshot)) { syncContext(); return false; }
    return id === serial;
  }
  function validResult(data,req) {
    const hash = v => typeof v === 'string' && /^[a-f\d]{64}$/i.test(v);
    return data.model_id === 'fixed_wing_supplied_coefficient_screening_v1' && data.evidence_level === 'unverified'
      && data.aircraft_status === null && data.feasibility === null && exact(data.inputs,req)
      && data.schema_version === 'fixed_wing_screening_request_v1' && hash(data.input_sha256) && hash(data.evaluation_sha256)
      && data.coefficient_source === req.coefficient_source && exact(data.coefficient_envelope,req.coefficient_envelope)
      && data.outputs && data.output_units && Object.keys(data.outputs).length === 9 && Object.keys(data.output_units).length === 9
      && OUTPUTS.every(([k,,unit]) => typeof data.outputs[k] === 'number' && Number.isFinite(data.outputs[k]) && data.output_units[k] === unit);
  }
  function pair(list,label,value) { list.append(node('dt',label),node('dd',String(value))); }
  function render(data,req) {
    const list = node('dl');
    OUTPUTS.forEach(([k,label,unit]) => pair(list,label,data.outputs[k]+' '+(unit === '1' ? '(dimensionless)' : unit)));
    result.append(list,node('p','Evidence: unverified. Aircraft status: unavailable. Feasibility: unavailable.'));
    const declaration = node('p','Source declaration: '+req.coefficient_source,'wing-declaration'); result.append(declaration);
    const details = node('details'), bounds = node('dl'); details.append(node('summary','Declared coefficient envelope'));
    ENVELOPE.forEach(([k,label]) => pair(bounds,label,req.coefficient_envelope[k])); details.append(bounds); result.append(details);
    const hashes = node('dl'); pair(hashes,'Input SHA-256',data.input_sha256); pair(hashes,'Evaluation SHA-256',data.evaluation_sha256);
    result.append(hashes); result.hidden = false;
  }
  form.addEventListener('submit',async event => {
    event.preventDefault(); if (syncContext() || busy) return;
    const req = request(); if (!req) { refresh(); return; }
    const snapshot = readContext(), id = ++serial;
    if (!isContext(snapshot)) { syncContext(); status.textContent = 'Sign in and re-enter all inputs.'; return; }
    busy = true; clearResult(); refresh(); status.textContent = 'Screening supplied coefficients…';
    try {
      const response = await api('/fixed-wing/screen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});
      if (!current(id,snapshot)) return;
      const data = response && typeof response.json === 'function' ? await response.json() : response;
      if (!current(id,snapshot)) return;
      if (!data || typeof data.status !== 'string') throw new Error('Invalid response');
      if (data.status !== 'SCREENING_COMPUTED') {
        const reasons = Array.isArray(data.reasons) ? data.reasons.filter(v => typeof v === 'string').join('; ') : '';
        status.textContent = data.status+(reasons ? ': '+reasons : '')+'. Sign in and check inputs.'; return;
      }
      if (response?.ok === false || !validResult(data,req)) throw new Error('Unverified response structure');
      render(data,req); status.textContent = 'SCREENING_COMPUTED - supplied-coefficient screening; evidence unverified.';
    } catch {
      if (current(id,snapshot)) { clearResult(); status.textContent = 'Screening failed. Sign in and check inputs.'; }
    } finally {
      if (current(id,snapshot)) { busy = false; refresh(); }
    }
  });
  return {syncContext};
}
