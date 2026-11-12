/* Workflow prerequisites reflect plan Tasks 1.5–12.3 [M§26]. No guessed design values. */
const stages = {
  import: { label: 'Geometry intake', title: 'Bring the assembly, and its units.',
    description: 'An STL describes a surface. Start with the original component files and an explicit declaration of their units.',
    requirements: [['Original component files', 'Keep the airframe and rotating parts identifiable.'], ['Declared source units', 'Metres, millimetres, centimetres, inches or feet. Units are never inferred.'], ['Component transforms', 'Record the position, orientation and source of every component.']],
    pending: 'Import is pending implementation.', next: 'Parser, topology and repair contracts are built. Uploads and the 3D viewer are pending; no file has been imported.' },
  assemble: { label: 'Assembly contract', title: 'Every component needs a role.',
    description: 'Assign stationary and rotating parts before defining the fluid domain.',
    requirements: [['Component assignments', 'Identify the airframe, blades, hubs and other surfaces.'], ['Rotor centres and axes', 'Declare the thrust direction, signed rotation and component transforms.'], ['Geometry diagnostics', 'Retain topology, bounds and every proposed repair.']],
    pending: 'Assembly entry is pending implementation.', next: 'Assembly validation is built. Component assignment and the 3D viewer are pending; no assembly is defined.' },
  conditions: { label: 'Operating conditions', title: 'The environment is an input.',
    description: 'Record the mass ledger and atmosphere for each operating case. Missing values remain unknown.',
    requirements: [['Complete mass ledger', 'Record structure, propulsion, energy, avionics, other equipment and any installed payload.'], ['Atmosphere', 'Declare absolute pressure and temperature with units.'], ['Operating envelope', 'Supply inflow, RPM, ground clearance, mission conditions and component limits.']],
    pending: 'Condition entry is pending implementation.', next: 'Schema, units, atmosphere and mass validation are built. No operating case is defined.' },
  mesh: { label: 'Fluid domain', title: 'A surface is only the beginning.',
    description: 'CFD requires a fluid volume, boundary conditions and evidence of mesh quality.',
    requirements: [['Ready geometry', 'Use a retained assembly with declared units and checked topology.'], ['Domain and mesh policy', 'Declare boundaries, refinement, wall layers and rotor zones.'], ['Verified backend profile', 'Support must be established by the exact release and the relevant fixture.']],
    pending: 'Project meshing is pending implementation.', next: 'WP04 will connect mesh requests to verified backend capabilities. No project mesh exists.' },
  run: { label: 'Execution contract', title: 'Run only what is ready.',
    description: 'An immutable project snapshot and verified backend profile must precede a solver run.',
    requirements: [['Complete project snapshot', 'All required inputs, units and references must pass readiness gates.'], ['Explicit resource limits', 'Supply CPU, memory, disk and wall-time budgets.'], ['Retained run evidence', 'Keep the translated settings, logs, native fields and hashes.']],
    pending: 'Project solver execution is pending implementation.', next: 'Backend adapters arrive in WP04. No aircraft solver run is available.' },
  results: { label: 'Engineering evidence', title: 'A result keeps its sources.',
    description: 'Loads, plots and decisions must resolve to retained calculations, measurements or solver data.',
    requirements: [['Native loads and provenance', 'Identify the case, frame, moment origin, units and sign convention.'], ['Numerical assessment', 'Evaluate convergence and controlled mesh or time changes.'], ['Applicable validation', 'A completed process does not establish an aircraft feasibility claim.']],
    pending: 'Project results are pending implementation.', next: 'Loads and evidence workflows arrive in WP05 onwards. No aircraft result is available.' }
};
const tabs = [...document.querySelectorAll('[data-stage]')];
function selectStage(tab, moveFocus = false) {
  const stage = stages[tab.dataset.stage];
  tabs.forEach(item => { item.setAttribute('aria-selected', String(item === tab)); item.tabIndex = item === tab ? 0 : -1; });
  document.querySelector('#stage-panel').setAttribute('aria-labelledby', tab.id);
  document.querySelector('#sheet-title').textContent = stage.label;
  document.querySelector('#stage-title').textContent = stage.title;
  document.querySelector('#stage-description').textContent = stage.description;
  document.querySelector('#pending-title').textContent = stage.pending;
  document.querySelector('#pending-description').textContent = stage.next;
  const list = document.querySelector('#requirements');
  list.replaceChildren(...stage.requirements.map(([title, body]) => {
    const li = document.createElement('li');
    const mark = document.createElement('span'); mark.textContent = '›'; mark.setAttribute('aria-hidden', 'true');
    const text = document.createElement('div'); const strong = document.createElement('strong'); strong.textContent = title;
    const description = document.createElement('span'); description.textContent = body;
    text.append(strong, description); li.append(mark, text); return li;
  }));
  if (moveFocus) tab.focus();
}
tabs.forEach((tab, index) => {
  tab.addEventListener('click', () => selectStage(tab));
  tab.addEventListener('keydown', event => {
    let target;
    if (['ArrowDown', 'ArrowRight'].includes(event.key)) target = tabs[(index + 1) % tabs.length];
    if (['ArrowUp', 'ArrowLeft'].includes(event.key)) target = tabs[(index + tabs.length - 1) % tabs.length];
    if (event.key === 'Home') target = tabs[0];
    if (event.key === 'End') target = tabs[tabs.length - 1];
    if (target) { event.preventDefault(); selectStage(target, true); }
  });
});
async function refreshHealth() {
  const button = document.querySelector('#refresh'); const status = document.querySelector('#server-status');
  button.disabled = true; status.textContent = 'Checking server…';
  try {
    const response = await fetch('/api/health', { cache: 'no-store', signal: AbortSignal.timeout(8000) });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const health = await response.json();
    status.textContent = 'Server reachable';
    document.querySelector('#application-state').textContent = health.status === 'ok' ? 'Online' : 'Unexpected response';
    document.querySelector('#pin-state').textContent = health.backend_pinned ? 'Configured' : 'Not configured';
    document.querySelector('#capability-state').textContent = health.capabilities?.length ? health.capabilities.join(', ') : 'None registered';
    document.querySelector('#image-reference').textContent = health.backend_image || 'No backend image configured for this application.';
  } catch (error) {
    status.textContent = 'Server unavailable';
    document.querySelector('#application-state').textContent = 'Connection failed';
    document.querySelector('#pin-state').textContent = 'Unknown';
    document.querySelector('#capability-state').textContent = 'Unknown';
    document.querySelector('#image-reference').textContent = 'Could not read server configuration. Use Check again to retry.';
  } finally {
    button.disabled = false;
  }
}
document.querySelector('#refresh').addEventListener('click', refreshHealth);
refreshHealth();