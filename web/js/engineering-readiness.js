/* Presentation of saved-input checks. This module never evaluates an aircraft. */
const list = value => Array.isArray(value) ? value.map(item => typeof item === 'string' ? item : JSON.stringify(item)) : [];

export function issueDestination(reason) {
  const text = String(reason).toLowerCase();
  if (/local_pilot|model_version|data_scope|fidelity|auxiliary|payload domain/.test(text)) return 'model';
  if (/mass|\bcg\b|payload position/.test(text)) return 'mass';
  if (/sequence|segment/.test(text)) return 'sequence';
  if (/rotor|\bmap\b|rpm|pitch|configuration|performance.source/.test(text)) return 'rotors';
  if (/pack|energy|battery|voltage|current/.test(text)) return 'battery';
  if (/case|mission|atmosphere|inflow|attitude|velocity|acceleration|body.load|frame/.test(text)) return 'cases';
  return 'json';
}

export function readinessRows(report) {
  const mass = report?.mass, pack = report?.pack, model = report?.hover_readiness;
  const massIssues = [...list(mass?.missing), ...list(mass?.errors)];
  const massComplete = mass?.complete === true && !massIssues.length;
  const modelIssues = list(model?.blocking ?? model?.reasons);
  const cases = Array.isArray(model?.cases) ? model.cases : [];
  return [
    {key: 'mass', title: 'Mass & placement', state: typeof mass?.complete !== 'boolean' ? 'Not inspected' : massComplete ? 'Inputs complete' : 'Needs attention',
      note: massComplete ? 'Saved mass-ledger inputs are complete. Measurement accuracy is unassessed.' : 'Declare masses and body-frame positions, including the battery and payload.',
      issues: massIssues, group: 'mass'},
    {key: 'battery', title: 'Battery budget', state: !pack ? 'Not inspected' : pack.status === 'consistent' ? 'Declarations consistent' : pack.status === 'inconsistent' ? 'Values disagree' : pack.status === 'inputs_incomplete' ? 'Missing or invalid inputs' : 'Not assessed',
      note: pack?.status === 'consistent' ? 'Energy declarations agree, with reserve held once. Battery capability is unvalidated.' : 'Bind battery mass, specific energy, usable fraction and reserve to one budget.',
      issues: pack?.detail ? [String(pack.detail)] : pack?.status === 'inconsistent' ? ['Declared usable energy does not agree with the derived pack budget.'] : [], group: 'battery'},
    {key: 'model', title: 'Model & cases', state: typeof model?.eligible !== 'boolean' ? 'Not inspected' : model.eligible === true ? 'Required inputs eligible' : 'Not eligible',
      note: model?.eligible === true ? 'Required cases match the bounded model inputs. This check calculates no payload.' : 'Resolve required-case inputs and model coverage before interpreting a study.',
      issues: modelIssues, cases, group: 'cases'},
    {key: 'sources', title: 'Source evidence', state: 'Not assessed',
      note: 'File integrity does not verify measured accuracy or applicability to the installed aircraft.',
      issues: [], group: 'rotors'},
    {key: 'review', title: 'Engineering acceptance', state: 'Pending qualified review',
      note: 'Input checks, workflow comments and frozen revisions do not grant aircraft approval.',
      issues: [], group: null},
  ];
}

const labels = {mass: 'Open mass & placement', battery: 'Open battery inputs', cases: 'Open mission cases',
  rotors: 'Open rotor sources', sequence: 'Open mission sequence', model: 'Open model settings', json: 'Open full input JSON'};

export function renderReadiness(container, report, navigate) {
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const action = group => {
    const button = node('button', labels[group], 'readiness-action');
    button.type = 'button'; button.dataset.readinessTarget = group;
    button.addEventListener('click', () => navigate(group));
    return button;
  };
  container.replaceChildren();
  const checks = node('div', undefined, 'readiness-checks');
  for (const row of readinessRows(report)) {
    const section = node('section', undefined, 'readiness-check');
    section.dataset.check = row.key;
    const heading = node('div', undefined, 'readiness-check-heading');
    const title = node('h4', row.title); title.id = 'readiness-' + row.key;
    section.setAttribute('aria-labelledby', title.id);
    heading.append(title, node('p', row.state, 'readiness-result'));
    const body = node('div', undefined, 'readiness-check-body'); body.append(node('p', row.note));
    if (row.issues.length) {
      const issues = node('ul', undefined, 'readiness-issues');
      for (const issue of row.issues) {
        const item = node('li'); item.append(node('span', issue));
        item.append(action(row.key === 'model' ? issueDestination(issue) : row.group));
        issues.append(item);
      }
      body.append(issues);
    } else if (row.group) body.append(action(row.group));
    if (row.cases?.length) {
      const cases = node('ul', undefined, 'readiness-cases');
      for (const item of row.cases) {
        const caseRow = node('li');
        caseRow.append(node('strong', String(item.case_id ?? 'Unnamed case')),
          node('span', item.eligible === true ? 'Eligible inputs' : item.eligible === false ? 'Not eligible' : 'Not assessed'));
        const reasons = list(item.blocking);
        if (reasons.length) {
          const detail = node('ul');
          for (const reason of reasons) {
            const issue = node('li'); issue.append(node('span', reason), action(issueDestination(reason))); detail.append(issue);
          }
          caseRow.append(detail);
        }
        cases.append(caseRow);
      }
      body.append(cases);
    }
    section.append(heading, body); checks.append(section);
  }
  container.append(checks);
  if (report?.screening_readiness) {
    const details = node('details', undefined, 'readiness-screening');
    details.append(node('summary', 'Separate supplied-point screening checks'));
    details.append(node('p', 'This is a different input contract from the bounded map-based model above. Neither check establishes engineering acceptance.'));
    const blockers = list(report.screening_readiness.blocking);
    if (blockers.length) {
      const items = node('ul');
      for (const reason of blockers) { const item = node('li'); item.append(node('span', reason), action(issueDestination(reason))); items.append(item); }
      details.append(items);
    } else details.append(node('p', report.screening_readiness.ready === true ? 'No supplied-point input blockers returned.' : 'Screening input readiness is not established.'));
    container.append(details);
  }
}
