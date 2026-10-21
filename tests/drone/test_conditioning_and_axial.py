"""Independent CT/CQ, hull, failure-state and inflow acceptance fixtures."""
import copy
import json
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.drone.atmosphere import G0
from physimesh.drone.capacity import capacity_from_snapshot
from physimesh.drone.conditioning import ConditionedMap, condition_map
from physimesh.drone.local_results import LocalCapacityV4
from physimesh.drone.trim import EXTENDED_MODEL_VERSION
from physimesh.projects.examples import create_hover_example
from physimesh.projects.performance import load_map, parse_map, source_bytes
from physimesh.projects.realistic import fixture_policy, realistic_dataset

AUTH = {'Authorization': 'Bearer fixture-token'}


def setup(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'fixture-token', None))
    project = create_hover_example(app.state.projects)
    snapshot = json.loads(project['snapshot_json'])
    snapshot['fidelity']['local_pilot']['model_version'] = EXTENDED_MODEL_VERSION
    return app, snapshot


def with_map(snapshot, model):
    for rotor in snapshot['rotors']:
        rotor.update(map_ref='fixture', configuration_id=model.configuration_id)
        rotor['sustained_limits']['max_rpm'] = 3000.
    for case in snapshot['mission']['cases']:
        case.update(torque_band_moment_allowance_nm=[0., 0., 5.],
                    torque_band_allowance_source='Analytic fixture allowance, not flight acceptance')
    return {'fixture': model}


@pytest.mark.parametrize('noise', [.001, .01, .05])
def test_multiple_seed_noise_envelopes_and_capacity_conservatism(tmp_path, noise):
    _, snapshot = setup(tmp_path)
    for case in snapshot['mission']['cases']:
        case['duration_s'] = 60.
    ideal = parse_map(json.dumps(realistic_dataset(0)).encode())
    ideal_result = capacity_from_snapshot(snapshot, with_map(snapshot, ideal))
    assert ideal_result['outcome'] == 'feasible'
    for seed in range(20):
        raw = parse_map(json.dumps(realistic_dataset(noise, seed)).encode())
        profile = condition_map(raw, fixture_policy(noise))
        assert np.all(np.array(profile['electrical_power_w'])+1e-9
                      >= np.array(profile['sample_upper_electrical_power_w']))
        conditioned = ConditionedMap(raw, 'a'*64, 'b'*64, profile)
        result = capacity_from_snapshot(snapshot, with_map(snapshot, conditioned))
        assert result['outcome'] == 'feasible', result
        assert result['payload_lower_bound_kg'] <= ideal_result['payload_lower_bound_kg']+1e-8
        band = result['headline_candidate_checks'][0]['candidate']['torque_band_moment_interval_nm']
        assert band['upper'][2] == pytest.approx(4*profile['torque_error_bound_nm'], abs=1e-7)
        assert band['lower'][2] == pytest.approx(-4*profile['torque_error_bound_nm'], abs=1e-7)


def test_torque_tolerance_and_all_independent_corners_are_not_silently_relaxed(tmp_path):
    _, snapshot = setup(tmp_path)
    raw = parse_map(json.dumps(realistic_dataset(.01)).encode())
    policy = fixture_policy().model_copy(update={'torque_relative_residual_tolerance': .000001})
    with pytest.raises(ValueError, match='residual'):
        condition_map(raw, policy)
    profile = condition_map(raw, fixture_policy())
    maps = with_map(snapshot, ConditionedMap(raw, 'a'*64, 'b'*64, profile))
    snapshot['mission']['cases'][0]['torque_band_moment_allowance_nm'] = [0., 0., .000001]
    result = capacity_from_snapshot(snapshot, maps)
    assert result['outcome'] == 'unsupported' and result['payload_lower_bound_kg'] is None
    assert 'torque interval' in result['reasons'][0]


def test_varying_torque_shaft_basis_efficiency_applied_once(tmp_path):
    _, snapshot = setup(tmp_path)
    results = []
    for basis in ('shaft', 'electrical'):
        raw = parse_map(json.dumps(realistic_dataset(0, basis=basis)).encode())
        profile = condition_map(raw, fixture_policy(0))
        model = ConditionedMap(raw, 'a'*64, 'b'*64, profile)
        results.append(capacity_from_snapshot(snapshot, with_map(snapshot, model)))
        point = model.evaluate(1500., density=raw.density_kg_m3, inflow=0., pitch=0.)
        measured = raw.points[5]
        assert point['electrical_power_w'] == pytest.approx(measured.shaft_torque_nm*1500*2*math.pi/60/.85)
    assert results[0]['payload_lower_bound_kg'] == pytest.approx(results[1]['payload_lower_bound_kg'])


def test_quad_motor_out_certificate_and_octo_reduced_feasible_capacity(tmp_path):
    app, snapshot = setup(tmp_path)
    digest = snapshot['rotors'][0]['map_ref']
    maps = {digest: load_map(app.state.projects.artifacts, digest)}
    snapshot['mission']['cases'] = [snapshot['mission']['cases'][0]]
    snapshot['mission']['cases'][0]['duration_s'] = 1.
    snapshot['mission']['energy_system'].update(max_electrical_power_w=10000., max_current_a=200.)
    snapshot['mission']['cases'][0]['failed_rotor_ids'] = ['r0']
    quad = capacity_from_snapshot(snapshot, maps)
    assert quad['outcome'] == 'infeasible', quad
    assert quad['cases'][0]['certificate']['gap'] > quad['cases'][0]['certificate']['rounding_guard']
    template = snapshot['rotors'][0]
    positions = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    snapshot['rotors'] = [{**template, 'rotor_id': 'r'+str(i), 'center_body_m': [x, y, 0.],
                           'rotation_sign': 1 if i % 2 == 0 else -1}
                          for i, (x, y) in enumerate(positions)]
    failed = capacity_from_snapshot(snapshot, maps)
    assert failed['outcome'] == 'feasible', failed
    command = next(c for c in failed['cases'][0]['candidate']['commands'] if c['rotor_id'] == 'r0')
    assert command['thrust_n'] == command['shaft_torque_nm'] == command['electrical_power_w'] == 0
    snapshot['mission']['cases'][0].pop('failed_rotor_ids')
    nominal = capacity_from_snapshot(snapshot, maps)
    assert nominal['payload_lower_bound_kg'] == pytest.approx(800/G0-12)
    assert 0 < failed['payload_lower_bound_kg'] < nominal['payload_lower_bound_kg']


@pytest.mark.parametrize('example', ['realistic', 'motorout'])
def test_real_api_fixture_to_frozen_result_export_pdf_and_restart(tmp_path, example):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'fixture-token', None))
    client = TestClient(app)
    response = client.post('/api/drone/projects/examples/'+example, headers=AUTH)
    assert response.status_code == 201, response.text
    project = response.json(); base = '/api/drone/projects/'+project['project_id']
    frozen = client.post(base+'/revisions', headers=AUTH, json={'expected_version': project['draft_version']})
    assert frozen.status_code == 200, frozen.text
    result = client.post(base+'/studies', headers=AUTH, json={'revision_sha256': frozen.json()['revision_sha256']})
    assert result.status_code == 200, result.text
    data = result.json(); assert data['outcome'] == 'feasible', data
    assert data['data_scope'] == 'analytic_fixture' and data['engineering_approval'] == 'pending'
    LocalCapacityV4.model_validate_json(result.content)
    if example == 'realistic':
        assert data['limiting_case_id'] == 'climb_2ms'
        assert data['cases'][-1]['candidate']['payload_kg'] < data['cases'][1]['candidate']['payload_kg']
    else:
        assert data['cases'][-1]['failed_rotor_ids'] == ['r0']
    source = next(iter(data['conditioning_sources'].values()))
    original = source_bytes(app.state.projects.artifacts, source['raw_source_sha256'])
    assert parse_map(original).source_kind == 'analytic_fixture'
    url = base+'/studies/'+data['study_sha256']
    exported = client.get(url+'/export', headers=AUTH)
    pdf = client.get(url+'/pdf', headers=AUTH)
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF-')
    restarted = TestClient(create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'fixture-token', None)))
    assert restarted.get(url+'/export', headers=AUTH).content == exported.content
    assert restarted.get(url+'/pdf', headers=AUTH).content == pdf.content
    assert source_bytes(app.state.projects.artifacts, source['raw_source_sha256']) == original


def test_climb_refuses_missing_matching_inflow_and_wrong_flow_sign(tmp_path):
    _, snapshot = setup(tmp_path)
    raw = parse_map(json.dumps(realistic_dataset(0)).encode())
    maps = with_map(snapshot, raw)
    case = snapshot['mission']['cases'][1]
    case.update(kind='axial_climb', axial_inflow_m_s=2., velocity_world_m_s=[0., 0., 2.],
                air_relative_velocity_body_m_s=[0., 0., -2.])
    result = capacity_from_snapshot(snapshot, maps)
    assert result['outcome'] == 'unsupported' and any('inflow' in r for r in result['reasons'])
    case['air_relative_velocity_body_m_s'] = [0., 0., 2.]
    result = capacity_from_snapshot(snapshot, maps)
    assert result['outcome'] == 'unsupported' and any('body-relative' in r for r in result['reasons'])
    bad = copy.deepcopy(snapshot); bad['mission']['cases'][0]['failed_rotor_ids'] = ['unknown']
    assert capacity_from_snapshot(bad, maps)['outcome'] == 'unsupported'
