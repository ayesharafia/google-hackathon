import copy
import json

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.drone.atmosphere import G0
from physimesh.drone.local_results import LocalCapacityV4
from physimesh.projects.performance import retain_map

AUTH = {'Authorization': 'Bearer fixture-token'}


def prepare(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'fixture-token', None))
    client = TestClient(app)
    project = client.post('/api/drone/projects/examples/hover', headers=AUTH).json()
    snapshot = json.loads(project['snapshot_json'])
    snapshot['fidelity']['local_pilot']['model_version'] = 'convex_axial_capacity_v2'
    return app, client, project, snapshot


def run(client, project, snapshot):
    base = '/api/drone/projects/'+project['project_id']
    saved = client.put(base+'/draft', headers=AUTH, json={
        'expected_version': project['draft_version'], 'snapshot_json': json.dumps(snapshot)})
    assert saved.status_code == 200, saved.text
    frozen = client.post(base+'/revisions', headers=AUTH, json={'expected_version': saved.json()['draft_version']})
    assert frozen.status_code == 200, frozen.text
    return client.post(base+'/studies', headers=AUTH, json={'revision_sha256': frozen.json()['revision_sha256']})


def scenario(name='heavier', **changes):
    return {'schema_version': 'deterministic_capacity_scenario_v1', 'scenario_id': name,
            'source_note': 'Analytic joint-scenario software fixture',
            'correlation_note': 'The specified changes occur together; no independent cross-product.', **changes}


def cap(payload=1., status='declared_approved'):
    return {'schema_version': 'external_payload_cap_v1', 'cap_id': 'fixture_cap', 'kind': 'structural',
            'payload_kg': payload, 'source_note': 'Synthetic cap; not structural analysis',
            'approval_status': status, 'approval_scope': 'Software fixture only',
            'approval_reference': 'fixture-reference' if status == 'declared_approved' else None}


def test_correlated_mass_density_and_map_scenario_and_sourced_cap(tmp_path):
    app, client, project, snapshot = prepare(tmp_path)
    digest = snapshot['rotors'][0]['map_ref']
    raw = client.get('/api/drone/projects/performance-sources/'+digest, headers=AUTH).json()
    raw['density_kg_m3'] *= .9
    for point in raw['points']:
        point['thrust_n'] *= .9; point['shaft_torque_nm'] *= .9
    alternative = retain_map(app.state.projects.artifacts, json.dumps(raw).encode())['source_sha256']
    pilot = snapshot['fidelity']['local_pilot']
    pilot['scenarios'] = [scenario(mass_items_kg={'structure': 11.},
        atmosphere={'pressure_pa': 101325*.9, 'temperature_k': 288.15, 'source': 'Fixture low density'},
        map_sources_by_rotor={r['rotor_id']: alternative for r in snapshot['rotors']})]
    pilot['allowable_caps'] = [cap(1.)]
    response = run(client, project, snapshot)
    assert response.status_code == 200, response.text
    data = response.json(); analysis = data['scenario_analysis']
    assert data['payload_lower_bound_kg'] == pytest.approx(153.6/G0-12)
    assert analysis['supported_payload_kg'] == pytest.approx(138.24/G0-13)
    assert analysis['status'] == 'supported' and len(analysis['scenarios']) == 1
    assert analysis['limiting_scenario_ids'] == ['heavier']
    allowable = data['external_allowables']
    assert allowable['feasible_capped_payload_kg'] == 1.
    assert allowable['declared_approved_cap_kg'] == 1.
    assert data['engineering_approval'] == 'pending'
    assert len(allowable['candidate_checks']) == len(analysis['common_payload_checks']) == 2
    LocalCapacityV4.model_validate_json(response.content)


def test_changed_density_without_matching_map_retains_incomplete_envelope(tmp_path):
    _, client, project, snapshot = prepare(tmp_path)
    snapshot['fidelity']['local_pilot']['scenarios'] = [scenario(atmosphere={
        'pressure_pa': 90000., 'temperature_k': 288.15, 'source': 'Declared fixture atmosphere'})]
    response = run(client, project, snapshot)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['outcome'] == 'feasible'
    assert data['scenario_analysis']['status'] == 'incomplete'
    assert data['scenario_analysis']['supported_payload_kg'] is None
    inner = data['scenario_analysis']['scenarios'][0]['result']
    assert inner['outcome'] == 'unsupported' and 'density' in inner['reasons'][0]


def test_no_silent_confidence_or_approval_and_missing_source_refuses(tmp_path):
    _, client, project, snapshot = prepare(tmp_path)
    pilot = snapshot['fidelity']['local_pilot']; pilot['allowable_caps'] = [cap(status='proposed')]
    response = run(client, project, snapshot)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['scenario_analysis']['status'] == 'not_declared'
    assert data['external_allowables']['status'] == 'no_declared_approved_cap'
    assert data['external_allowables']['feasible_capped_payload_kg'] is None
    bad = cap(); bad['source_note'] = ' '
    pilot['allowable_caps'] = [bad]
    from physimesh.drone.scenarios import assess_scenarios_and_caps
    with pytest.raises(ValueError, match='source/scope'):
        assess_scenarios_and_caps(snapshot, {}, {})


def test_cap_below_feasible_interval_is_not_assumed_feasible(tmp_path):
    _, client, project, snapshot = prepare(tmp_path)
    for case in snapshot['mission']['cases']:
        case['body_force_body_n'] = [0., 0., 200.]
    snapshot['fidelity']['local_pilot']['allowable_caps'] = [cap(0.)]
    response = run(client, project, snapshot)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['outcome'] == 'feasible' and data['payload_lower_bound_kg'] > 0
    assert data['external_allowables']['status'] == 'unresolved'
    assert data['external_allowables']['feasible_capped_payload_kg'] is None
    assert data['external_allowables']['candidate_checks'][0]['case_checks'][0]['outcome'] == 'infeasible'


def test_retained_contract_rejects_forged_envelope_or_caps(tmp_path):
    _, client, project, snapshot = prepare(tmp_path)
    snapshot['fidelity']['local_pilot'].update(scenarios=[scenario(mass_items_kg={'structure': 11.})],
                                              allowable_caps=[cap()])
    response = run(client, project, snapshot)
    assert response.status_code == 200, response.text
    for mutation in ('envelope', 'missing_check', 'cap', 'energy'):
        data = copy.deepcopy(response.json())
        if mutation == 'envelope':
            data['scenario_analysis']['supported_payload_kg'] += 1.
        elif mutation == 'missing_check':
            data['scenario_analysis']['common_payload_checks'].pop()
        elif mutation == 'cap':
            data['external_allowables']['feasible_capped_payload_kg'] += 1.
        else:
            c = data['external_allowables']['candidate_checks'][0]
            c.update(sequence_energy_j=1000000., usable_energy_j=1., energy_tolerance_j=.001)
        with pytest.raises(ValueError):
            LocalCapacityV4.model_validate_json(json.dumps(data))


def test_legacy_model_refuses_extended_declarations(tmp_path):
    app, _, _, snapshot = prepare(tmp_path)
    snapshot['fidelity']['local_pilot'].update(model_version='convex_static_hover_v1',
                                              scenarios=[scenario(mass_items_kg={'structure': 11.})])
    from physimesh.drone.capacity import capacity_from_snapshot
    from physimesh.projects.performance import load_map
    digest = snapshot['rotors'][0]['map_ref']
    data = capacity_from_snapshot(snapshot, {digest: load_map(app.state.projects.artifacts, digest)})
    assert data['outcome'] == 'unsupported' and data['payload_lower_bound_kg'] is None
