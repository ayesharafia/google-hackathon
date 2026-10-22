/* Explicit draft reference assignment, never source conditioning or validation. */
function sourceInfo(receipt) {
  const data = receipt?.dataset;
  if (!/^[0-9a-f]{64}$/.test(receipt?.source_sha256 || '')
      || typeof data?.configuration_id !== 'string' || !data.configuration_id.trim()
      || typeof data?.dataset_id !== 'string' || !data.dataset_id.trim()
      || !['analytic_fixture', 'measured'].includes(data.source_kind)) {
    throw new Error('The import did not return a complete retained source identity. Import again.');
  }
  return data;
}

export function sourceBindingCandidates(snapshot, receipt) {
  const data = sourceInfo(receipt);
  if (!Array.isArray(snapshot?.rotors) || snapshot.rotors.some(rotor =>
    !rotor || typeof rotor.rotor_id !== 'string' || !rotor.rotor_id.trim())
    || new Set(snapshot.rotors.map(rotor => rotor.rotor_id)).size !== snapshot.rotors.length) {
    throw new Error('Declare unique rotor IDs before choosing a retained source.');
  }
  return snapshot.rotors.map(rotor => ({
    rotor_id: rotor.rotor_id,
    configuration_id: rotor.configuration_id,
    matches: rotor.configuration_id === data.configuration_id,
  }));
}

export function bindImportedSource(snapshot, receipt, selectedIds, expectedSnapshot) {
  if (typeof expectedSnapshot !== 'string' || JSON.stringify(snapshot) !== expectedSnapshot) {
    throw new Error('Draft inputs changed since this import preview. Import again to refresh the rotor choices.');
  }
  const candidates = sourceBindingCandidates(snapshot, receipt);
  if (!Array.isArray(selectedIds) || !selectedIds.length || new Set(selectedIds).size !== selectedIds.length) {
    throw new Error('Select at least one matching rotor, without duplicate selections.');
  }
  for (const id of selectedIds) {
    const rotor = candidates.find(item => item.rotor_id === id);
    if (!rotor || !rotor.matches) throw new Error('Selected rotor no longer matches this source configuration. Import again.');
  }
  const next = JSON.parse(JSON.stringify(snapshot));
  for (const rotor of next.rotors) if (selectedIds.includes(rotor.rotor_id)) rotor.map_ref = receipt.source_sha256;
  return next;
}

export function renderSourceBinding(container, receipt, snapshot, options) {
  const data = sourceInfo(receipt), baseline = JSON.stringify(snapshot);
  const candidates = sourceBindingCandidates(snapshot, receipt);
  const node = (tag, text) => { const element = document.createElement(tag); if (text !== undefined) element.textContent = text; return element; };
  container.replaceChildren(); container.className = 'source-binding';
  container.append(node('h4', 'Imported rotor source'),
    node('p', 'Dataset: ' + data.dataset_id + '. Configuration: ' + data.configuration_id + '.'),
    node('p', 'Source kind: ' + data.source_kind + '. This declaration does not verify measured accuracy or aircraft applicability.'));
  const identity = node('p', 'Retained source: '); identity.append(node('code', receipt.source_sha256)); container.append(identity);
  const selected = new Set(), choices = node('fieldset');
  choices.append(node('legend', 'Choose rotors to receive this source'));
  choices.append(node('p', 'Configuration matching only. Inspect the saved draft to check operating conditions and model coverage.'));
  for (const rotor of candidates) {
    const label = node('label'); label.className = 'source-binding-choice';
    const input = node('input'); input.type = 'checkbox'; input.value = rotor.rotor_id;
    input.disabled = !rotor.matches || !options.enabled(); input.dataset.sourceCompatible = String(rotor.matches);
    input.addEventListener('change', () => { if (input.checked) selected.add(rotor.rotor_id); else selected.delete(rotor.rotor_id); });
    label.append(input, node('span', rotor.rotor_id + (rotor.matches ? ': matching configuration' : ': configuration does not match')));
    choices.append(label);
  }
  if (!candidates.some(rotor => rotor.matches)) {
    choices.append(node('p', 'No rotor has this configuration. Declare the intended rotor configuration, then import again.'));
  }
  const status = node('p'); status.setAttribute('role', 'status'); status.className = 'source-binding-status';
  const apply = node('button', 'Apply source to selected rotors'); apply.type = 'button';
  apply.dataset.sourceApply = 'true'; apply.disabled = !options.enabled() || !candidates.some(rotor => rotor.matches);
  apply.addEventListener('click', () => {
    try {
      if (!options.enabled()) throw new Error('Reconnect and finish the current action before applying a source.');
      const next = bindImportedSource(options.read(), receipt, [...selected], baseline);
      options.apply(next, selected.size);
    } catch (error) { status.textContent = error.message; }
  });
  container.append(choices, apply, status);
}
