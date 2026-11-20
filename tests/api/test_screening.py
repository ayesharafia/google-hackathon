from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.core.artifacts import ArtifactStore
from physimesh.drone.demo_screening import example_request

AUTH = {'Authorization': 'Bearer test-token'}


def fixture(tmp_path):
    body = example_request(ArtifactStore(tmp_path/'artifacts'))
    client = TestClient(create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'test-token', None)))
    return client, body


def test_complete_example_reports_lowest_case_and_no_validation_claim(tmp_path):
    client, body = fixture(tmp_path)
    assert client.post('/api/drone/screening', json=body).status_code == 401
    response = client.post('/api/drone/screening', headers=AUTH, json=body)
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'screening_only'
    assert result['limiting_case_id'] == 'climb'
    assert result['max_payload_kg'] == min(case['max_payload_kg'] for case in result['cases'])
    assert result['empty_airframe_mass_kg'] == 65


def test_missing_case_blocks_headline(tmp_path):
    client, body = fixture(tmp_path)
    body['case_inputs'].pop()
    result = client.post('/api/drone/screening', headers=AUTH, json=body).json()
    assert result['status'] == 'inputs_incomplete' and result['max_payload_kg'] is None


def test_source_hash_cannot_be_reused_with_changed_thrust(tmp_path):
    client, body = fixture(tmp_path)
    body['case_inputs'][0]['rotors'][0]['force_world_n'][2] *= 2
    result = client.post('/api/drone/screening', headers=AUTH, json=body).json()
    assert result['status'] == 'inputs_incomplete' and result['max_payload_kg'] is None
    assert any('source' in item for item in result['blocking'])


def test_unapproved_snapshot_and_unresolved_sources_block(tmp_path):
    client, body = fixture(tmp_path)
    body['approved_design_sha256'] = None
    assert client.post('/api/drone/screening', headers=AUTH, json=body).json()['max_payload_kg'] is None
    client, body = fixture(tmp_path)
    body['case_inputs'][0]['rotors'][0]['performance_source_sha256'] = 'a'*64
    assert client.post('/api/drone/screening', headers=AUTH, json=body).json()['max_payload_kg'] is None


def test_hover_power_and_tip_mach_are_labelled_screening_diagnostics(tmp_path):
    import math

    client, body = fixture(tmp_path)
    result = client.post('/api/drone/screening', headers=AUTH, json=body).json()
    hover = next(item for item in result['rotor_diagnostics'] if item['case_id'] == 'hover')
    rho = 101325/(287.05*288.15)
    assert math.isclose(hover['isolated_ideal_hover_power_w'], 350**1.5/math.sqrt(2*rho*math.pi*.65**2))
    assert math.isclose(hover['tip_mach'], (1500*2*math.pi/60*.65)/math.sqrt(1.4*287.05*288.15))
    assert next(item for item in result['rotor_diagnostics'] if item['case_id'] == 'climb')['isolated_ideal_hover_power_w'] is None


def test_browser_number_roundtrip_does_not_invalidate_snapshot_approval(tmp_path):
    client, body = fixture(tmp_path)
    # Browser JSON.stringify serializes a Python-origin 1.0 as 1.
    assert body['project']['units_and_frames']['cad_transform']['scale'] == 1.0
    body['project']['units_and_frames']['cad_transform']['scale'] = 1
    response = client.post('/api/drone/screening', headers=AUTH, json=body)
    assert response.json()['status'] == 'screening_only'


def test_complete_inputs_with_insufficient_energy_have_an_infeasible_reason(tmp_path):
    client, _ = fixture(tmp_path)
    body = example_request(ArtifactStore(tmp_path/'artifacts'), hover_duration_s=600)
    result = client.post('/api/drone/screening', headers=AUTH, json=body).json()
    assert result['max_payload_kg'] is None
    assert result['status'] == 'requirement_not_met' and result['outcome'] == 'infeasible_limits'
    assert result['reasons'][0]['code'] == 'usable_energy_exceeded'
    assert result['reasons'][0]['actual_j'] == 14_400_000
    assert result['reasons'][0]['limit_j'] == 11_520_000


def test_approved_mass_change_cannot_keep_old_usable_energy(tmp_path):
    from physimesh.drone.snapshot_hash import snapshot_sha256
    client, body = fixture(tmp_path)
    body['project']['masses']['items'][2]['mass_kg'] = 10
    body['approved_design_sha256'] = snapshot_sha256(body['project'])
    result = client.post('/api/drone/screening', headers=AUTH, json=body).json()
    assert result['max_payload_kg'] is None and result['pack_consistency']['status'] == 'inconsistent'
    assert result['reasons'][0]['code'] == 'pack_energy_consistency'


def test_tilted_approved_case_does_not_publish_a_trim_unchecked_number(tmp_path):
    from physimesh.drone.snapshot_hash import snapshot_sha256
    client, body = fixture(tmp_path)
    body['project']['mission']['cases'][0]['attitude_deg_zyx'][1] = 10
    body['approved_design_sha256'] = snapshot_sha256(body['project'])
    result = client.post('/api/drone/screening', headers=AUTH, json=body).json()
    assert result['max_payload_kg'] is None and result['outcome'] == 'unsupported_scope'
