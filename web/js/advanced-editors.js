/* Explicit policies and source bindings; no engineering tolerances are defaulted. */
const el = (tag, text) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; return n; };
const input = (label, value, update, type = 'text') => {
  const wrap = el('label', label), control = el('input'); control.type = type;
  if (type === 'number') control.step = 'any'; control.value = value ?? '';
  control.addEventListener('input', () => update(type === 'number' ? (control.value === '' ? null : Number(control.value)) : control.value));
  wrap.append(control); return wrap;
};
const button = (label, action) => { const b = el('button', label); b.type = 'button'; b.addEventListener('click', action); return b; };
function group(container, title, note) { const d = el('details'); d.append(el('summary', title), el('p', note)); container.append(d); return d; }

function jsonDeclarations(container, title, note, value, apply) {
  const d = group(container, title, note), label = el('label', 'Declarations JSON'), area = el('textarea');
  area.value = JSON.stringify(value || [], null, 2); area.rows = 8; label.append(area); const status = el('p'); status.setAttribute('role', 'status');
  d.append(label, button('Apply '+title.toLowerCase()+' to draft', () => {
    try { const parsed = JSON.parse(area.value); if (!Array.isArray(parsed)) throw new Error('Declare a JSON array.'); apply(parsed); status.textContent = 'Applied to draft. Save, inspect and freeze before evaluating.'; }
    catch (error) { status.textContent = 'Not applied: '+error.message; }
  }), status);
}

export function mountAdvanced(container, data, changed, rebuild, options) {
  if(!data.assembly||!Array.isArray(data.assembly.components)||data.assembly.components.some(c=>!c||typeof c!=='object'||Array.isArray(c))){container.append(el('p','Correct the assembly component declarations in the design JSON to use geometry authoring.'));return;}
  const conditioning = group(container, 'Condition a retained rotor map',
    'Raw bytes remain intact. Declare measurement bounds and fit tolerances with a source. The power hull is shifted above its sample envelope; torque bands require sourced moment allowances in each case.');
  let digest = '', policy = {schema_version: 'rotor_conditioning_policy_v1'}, result;
  const fields = el('div'); fields.className = 'fields';
  fields.append(input('Raw map SHA-256', '', v => digest = v), input('Policy source', '', v => policy.source_note = v));
  [['Maximum relative torque-fit residual', 'torque_relative_residual_tolerance'],
    ['Power relative uncertainty bound', 'power_relative_uncertainty'], ['Torque relative uncertainty bound', 'torque_relative_uncertainty'],
    ['Maximum hull shift / peak envelope power', 'max_power_shift_fraction']].forEach(([label, key]) => fields.append(input(label, null, v => policy[key] = v, 'number')));
  const status = el('p'); status.setAttribute('role', 'status');
  conditioning.append(fields, button('Condition retained map', async () => {
    try { result = await options.conditionMap(digest, policy); status.textContent = 'Raw '+result.raw_source_sha256+' → conditioned '+result.source_sha256+'. Shift '+result.conditioning.power_shift_w+' W; torque interval ±'+result.conditioning.torque_error_bound_nm+' Nm.'; }
    catch (error) { result = null; status.textContent = error.message; }
  }), button('Bind conditioned map to matching rotors', () => {
    if (!result) { status.textContent = 'Condition a retained map first.'; return; }
    let count = 0; data.rotors.forEach(r => { if (r.map_ref === result.raw_source_sha256 && r.configuration_id === result.dataset.configuration_id) { r.map_ref = result.source_sha256; count++; } });
    if (!count) { status.textContent = 'No rotor currently binds this raw source and configuration. Copy the conditioned hash into the intended rotor.'; return; }
    changed(); rebuild();
  }), status);

  const geometry = group(container, 'Airframe geometry and rotor links',
    'Import STL with explicit units. Geometry is a visual reference; it does not supply mass, thrust or installed-aircraft performance. Rotor centres remain declared body-frame metre coordinates.');
  const fileLabel = el('label', 'STL components'), files = el('input'); files.type = 'file'; files.multiple = true; files.accept = '.stl'; fileLabel.append(files);
  const unitLabel = el('label', 'Source length units'), units = el('select');
  [['', 'Choose source units'], ['m', 'metres'], ['mm', 'millimetres'], ['cm', 'centimetres'], ['in', 'inches']].forEach(([value, label]) => { const option = el('option', label); option.value = value; units.append(option); }); unitLabel.append(units);
  const note = el('p'); note.setAttribute('role', 'status');
  geometry.append(fileLabel, unitLabel, button('Import and attach STL components', async () => {
    try {
      if (!files.files.length || !units.value) throw new Error('Select STL files and explicitly declare source units.');
      const imported = await options.importGeometry(files.files, units.value);
      data.assembly ||= {}; data.assembly.components ||= [];
      const existing = new Set(data.assembly.components.map(c => c.source_sha256));
      const {sha256:importTransform,...transform}=imported.transform;
      const components = imported.components.filter(c => !existing.has(c.source_sha256)).map(c => ({...c, source_units: units.value,
        unit_scale_to_m: imported.unit_scale_to_m, import_transform_sha256:importTransform, transform:structuredClone(transform)}));
      data.assembly.components.push(...components); data.assembly.geometry_revision_sha256 = imported.geometry_revision_sha256;
      changed(); rebuild();
    } catch (error) { note.textContent = error.message; }
  }), note);
  (data.assembly?.components || []).forEach((c, index) => {
    const row = el('fieldset'); row.append(el('legend', c.filename || c.component_id),
      el('p', 'Source units: '+(c.source_units || 'unknown')+'; original SHA-256 '+c.source_sha256));
    if (c.transform) {
      [['Translation x, m', 'translation_m', 0], ['Translation y, m', 'translation_m', 1], ['Translation z, m', 'translation_m', 2],
        ['Yaw, degrees', 'rotation_deg_zyx', 0], ['Pitch, degrees', 'rotation_deg_zyx', 1], ['Roll, degrees', 'rotation_deg_zyx', 2]]
        .forEach(([label, key, i]) => row.append(input(label, c.transform[key]?.[i], v => { c.transform[key][i] = v;delete c.transform.sha256;changed(); }, 'number')));
    }
    row.append(button('Remove geometry component '+(index+1), () => {
      data.assembly.components.splice(index, 1); data.rotors.forEach(r => { if (r.component_id === c.component_id) r.component_id = null; }); rebuild();
    })); geometry.append(row);
  });
  if (data.assembly?.components?.length) data.rotors.forEach(r => {
    const label = el('label', 'Geometry reference for '+r.rotor_id), select = el('select'), none = el('option', 'No geometry reference'); none.value = ''; select.append(none);
    data.assembly.components.forEach(c => { const option = el('option', c.filename || c.component_id); option.value = c.component_id; select.append(option); });
    select.value = r.component_id || ''; select.addEventListener('change', () => { r.component_id = select.value || null; changed(); }); label.append(select); geometry.append(label);
  });

  const pilot = data.fidelity.local_pilot || {};
  jsonDeclarations(container, 'Deterministic joint scenarios',
    'Each deterministic_capacity_scenario_v1 needs scenario_id, source_note and correlation_note. Changes may bind mass_items_kg, map_sources_by_rotor, map_sources_by_case, atmosphere and body_loads_by_case. These are correlated declarations, not confidence intervals.',
    pilot.scenarios, value => { data.fidelity.local_pilot ||= {}; data.fidelity.local_pilot.scenarios = value; changed(); });
  jsonDeclarations(container, 'External payload caps',
    'Each external_payload_cap_v1 needs cap_id, kind (structural/operational), payload_kg, source_note, approval_status, approval_scope and an approval_reference for declared_approved. Approval declarations are not authenticated here. Caps remain separate from model capacity.',
    pilot.allowable_caps, value => { data.fidelity.local_pilot ||= {}; data.fidelity.local_pilot.allowable_caps = value; changed(); });
}