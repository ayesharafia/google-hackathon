export function mountJourney(root) {
  const doc = root.ownerDocument;
  const make = (tag, className, text) => {
    const el = doc.createElement(tag);
    el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  };
  root.classList.add('workbench-journey');
  const panel = make('section', 'wj-panel');
  const nav = make('nav', 'wj-nav');
  nav.setAttribute('aria-label', 'Workbench journey');
  const steps = [
    ['Configuration', 'reference-evaluation'],
    ['Inputs', 'input-editors'],
    ['Simulation', 'study-controls'],
    ['Results', 'study-report']
  ];
  for (const [label, id] of steps) {
    const anchor = make('a', 'wj-link', label);
    anchor.setAttribute('href', `#${id}`);
    anchor.addEventListener('click', event => {
      if (event.defaultPrevented || event.button !== 0 ||
          event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const target = doc.getElementById(id);
      if (!target || typeof target.focus !== 'function') return;
      target.setAttribute('tabindex', '-1');
      target.focus({ preventScroll: true });
      target.scrollIntoView({ block: 'start', behavior: 'auto' });
    });
    nav.append(anchor);
  }
  const note = make('p', 'wj-note',
    'Reference configuration is separate from saved-project inputs. Simulation below is a bounded study, not aircraft validation.');
  const summary = make('dl', 'wj-summary');
  const values = new Map();
  for (const [label, initial] of [
    ['Project', 'No project selected'],
    ['Inputs', 'Unavailable'],
    ['Selected study', 'No retained study selected'],
    ['Aircraft validation', 'Not established']
  ]) {
    const card = make('div', 'wj-card');
    const value = make('dd', 'wj-value', initial);
    card.append(make('dt', 'wj-label', label), value);
    summary.append(card);
    values.set(label, value);
  }
  panel.append(nav, note, summary);
  root.append(panel);
  return {
    sync(state) {
      const title = typeof state.projectTitle === 'string' &&
        state.projectTitle.trim() ? state.projectTitle : null;
      const hasProject = state.connected === true && title !== null;
      const version = Number.isInteger(state.draftVersion) &&
        state.draftVersion >= 0 ? state.draftVersion : null;
      values.get('Project').textContent = state.connected === true
        ? title || 'No project selected' : 'Signed out / no loaded project';
      values.get('Inputs').textContent = !hasProject ? 'Unavailable'
        : state.dirty || version === null ? 'Unsaved draft'
        : `Saved draft version ${version}`;
      values.get('Selected study').textContent = hasProject &&
        typeof state.study === 'string' && state.study.trim()
        ? state.study : 'No retained study selected';
      values.get('Aircraft validation').textContent = 'Not established';
    }
  };
}
