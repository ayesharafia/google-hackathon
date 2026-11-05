"""Router integration tests, not full application authentication tests."""
import json
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from physimesh.api.atmosphere import router
from physimesh.drone.atmosphere import R_AIR as LEGACY_R_AIR
from physimesh.drone.atmosphere import make_atmosphere
from physimesh.drone.models import project_from_mapping, readiness
from physimesh.drone.provenance import sha256_record
from physimesh.drone.standard_atmosphere import MODEL_ID

app = FastAPI()
app.include_router(router)
client = TestClient(app)
BODY = {"model_id": MODEL_ID, "altitude_m": 20000.0, "altitude_kind": "geometric"}


def test_api_evidence_is_bound_deterministic_and_not_validation():
    first = client.post('/api/drone/atmosphere/evaluate', json=BODY)
    assert first.status_code == 200
    data = first.json()
    assert data == client.post('/api/drone/atmosphere/evaluate', json=BODY).json()
    assert data['input_sha256'] == sha256_record(BODY)
    digest = data.pop('evaluation_sha256')
    assert digest == sha256_record(data)
    assert data['evidence_level'] == 'unverified'
    assert data['aircraft_status'] is None
    assert data['model']['mesh_required'] is False


def test_api_refuses_unsupported_incomplete_and_unknown_inputs():
    for changes in [{'model_id': 'arbitrary'}, {'altitude_kind': 'pressure'},
                    {'altitude_m': 30001.0}, {'altitude_m': -1.0},
                    {'altitude_m': '20000'}, {'altitude_m': True}, {'extra': 1}]:
        assert client.post('/api/drone/atmosphere/evaluate', json=BODY | changes).status_code == 422
    assert client.post('/api/drone/atmosphere/evaluate', json={}).status_code == 422


def test_change_invalidates_evidence_and_legacy_snapshot_binding():
    a = client.post('/api/drone/atmosphere/evaluate', json=BODY).json()
    b = client.post('/api/drone/atmosphere/evaluate', json=BODY | {'altitude_m': 21000.0}).json()
    assert a['input_sha256'] != b['input_sha256']
    assert a['evaluation_sha256'] != b['evaluation_sha256']
    path = Path(__file__).resolve().parents[2] / 'src/physimesh/drone/schema/drone_manifest_v1.yaml'
    project = yaml.safe_load(path.read_text())
    before = sha256_record(project)
    project['atmosphere'] = a['atmosphere_values']
    assert sha256_record(project) != before
    # Existing project parser/readiness consume explicit values, not a hidden
    # fallback. Other missing aircraft fields must still block readiness.
    snapshot = project_from_mapping(project)
    report = readiness(snapshot, 'screening')
    assert not report.ready
    assert not [p for p in report.blocking if p.startswith('atmosphere.')]
    values = a['atmosphere_values']
    atm = make_atmosphere(values['pressure_pa'], values['temperature_k'],
                          source=values['source'], viscosity_law='sutherland')
    # Existing manifest R_air is rounded differently; no silent model substitution.
    assert abs(atm.density / a['outputs']['density_kg_m3']
               - a['model']['gas_constant_j_kg_k'] / LEGACY_R_AIR) < 1e-12
    assert 'geometric' in values['source']
    assert json.loads(json.dumps(a)) == a


def test_model_convention_and_height_each_bind_evidence():
    geometric = client.post('/api/drone/atmosphere/evaluate', json=BODY).json()
    potential = client.post('/api/drone/atmosphere/evaluate', json=BODY | {
        'altitude_kind': 'geopotential'}).json()
    assert geometric['evaluation_sha256'] != potential['evaluation_sha256']
    assert geometric['atmosphere_values']['source'] != potential['atmosphere_values']['source']
    assert geometric['outputs']['pressure_pa'] != potential['outputs']['pressure_pa']
