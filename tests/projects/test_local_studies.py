import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.drone.atmosphere import G0
from physimesh.drone.local_results import LocalCapacityV3

AUTH = {'Authorization': 'Bearer test-token'}


def client(tmp_path):
    return TestClient(create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'test-token', None)))


def test_example_freeze_run_restart_export_and_edit_preserve_bound_record(tmp_path):
    import pytest
    c = client(tmp_path)
    project = c.post('/api/drone/projects/examples/hover', headers=AUTH).json()
    pid = project['project_id']; base = '/api/drone/projects/'+pid
    frozen = c.post(base+'/revisions', headers=AUTH, json={'expected_version': 1}).json()
    result = c.post(base+'/studies', headers=AUTH, json={'revision_sha256': frozen['revision_sha256']})
    assert result.status_code == 200
    report = result.json(); assert report['outcome'] == 'feasible'
    assert report['payload_lower_bound_kg'] == pytest.approx(153.6/G0-12)
    study = report['study_sha256']
    repeated = c.post(base+'/studies', headers=AUTH, json={'revision_sha256': frozen['revision_sha256']}).json()
    assert repeated == report
    snapshot = json.loads(project['snapshot_json']); snapshot['mission']['payload_positions_body_m'] = [[.4, 0, 0]]
    assert c.put(base+'/draft', headers=AUTH, json={'expected_version': 1, 'snapshot_json': json.dumps(snapshot)}).status_code == 200
    c = client(tmp_path)
    assert c.get(base+'/studies/'+study, headers=AUTH).json() == report
    exported = c.get(base+'/studies/'+study+'/export', headers=AUTH)
    assert json.loads(exported.content) == report
    inventory = c.get(base, headers=AUTH).json()
    assert len(inventory['studies']) == 1
    assert hashlib.sha256(exported.content).hexdigest() == inventory['studies'][0]['result_sha256']
    assert c.get(base+'/studies/'+study).status_code == 401
    assert c.get('/api/drone/projects/other/studies/'+study, headers=AUTH).status_code == 404


def test_missing_or_corrupt_performance_source_refuses_run_and_freeze(tmp_path):
    c = client(tmp_path)
    project = c.post('/api/drone/projects/examples/hover', headers=AUTH).json()
    pid = project['project_id']; base = '/api/drone/projects/'+pid
    frozen = c.post(base+'/revisions', headers=AUTH, json={'expected_version': 1}).json()
    ref = json.loads(project['snapshot_json'])['rotors'][0]['map_ref']
    object_path = tmp_path/'artifacts/objects'/ref[:2]/ref
    original = object_path.read_bytes(); object_path.write_bytes(original+b' ')
    response = c.post(base+'/studies', headers=AUTH, json={'revision_sha256': frozen['revision_sha256']})
    assert response.status_code == 422 and 'integrity' in response.text
    assert c.post(base+'/revisions', headers=AUTH, json={'expected_version': 1}).status_code == 422
    object_path.unlink()
    assert c.post(base+'/studies', headers=AUTH, json={'revision_sha256': frozen['revision_sha256']}).status_code == 422


def test_incomplete_frozen_design_retains_refusal_and_never_capacity(tmp_path):
    c = client(tmp_path)
    project = c.post('/api/drone/projects', headers=AUTH, json={'title':'Unknown aircraft'}).json()
    base = '/api/drone/projects/'+project['project_id']
    frozen = c.post(base+'/revisions', headers=AUTH, json={'expected_version':0}).json()
    report = c.post(base+'/studies', headers=AUTH, json={'revision_sha256':frozen['revision_sha256']}).json()
    assert report['outcome'] == 'unsupported' and report['payload_lower_bound_kg'] is None
    assert report['engineering_approval'] == 'pending'


def test_sequence_contract_refuses_missing_or_changed_aggregate_evidence(tmp_path):
    c = client(tmp_path)
    project = c.post('/api/drone/projects/examples/hover', headers=AUTH).json()
    base = '/api/drone/projects/'+project['project_id']
    snapshot = json.loads(project['snapshot_json'])
    snapshot['mission']['sequence'] = [{'segment_id': 'first', 'case_id': 'hover_long', 'duration_s': 180.,
        'source_note': 'Analytic sequence', 'power_profile': 'constant'},
        {'segment_id': 'second', 'case_id': 'hover_long', 'duration_s': 180.,
         'source_note': 'Analytic sequence', 'power_profile': 'constant'}]
    assert c.put(base+'/draft', headers=AUTH, json={'expected_version':1,'snapshot_json':json.dumps(snapshot)}).status_code == 200
    inspection = c.get(base+'/inspection', headers=AUTH).json()
    assert inspection['hover_readiness']['eligible']
    frozen = c.post(base+'/revisions', headers=AUTH, json={'expected_version':2}).json()
    response = c.post(base+'/studies', headers=AUTH, json={'revision_sha256':frozen['revision_sha256']})
    assert response.status_code == 200
    report = response.json()
    assert report['schema_version'] == 'local_mission_capacity_v3'
    assert report['payload_lower_bound_kg'] == pytest.approx(460800/360/10/G0-12)
    LocalCapacityV3.model_validate_json(json.dumps(report))
    changed = json.loads(json.dumps(report))
    changed['participating_case_bounds'][0]['candidate']['payload_kg'] = 0.
    with pytest.raises(ValueError, match='participating feasible case bound'):
        LocalCapacityV3.model_validate_json(json.dumps(changed))
    changed = json.loads(json.dumps(report))
    changed['participating_case_bounds'].append(changed['participating_case_bounds'][0])
    with pytest.raises(ValueError, match='unique bound'):
        LocalCapacityV3.model_validate_json(json.dumps(changed))
    for key in ('sequence_evidence', 'headline_candidate_checks'):
        changed = dict(report); changed.pop(key)
        with pytest.raises(ValueError):
            LocalCapacityV3.model_validate_json(json.dumps(changed))
    report['sequence_evidence']['total_energy_j'] += 1.
    with pytest.raises(ValueError, match='aggregate energy'):
        LocalCapacityV3.model_validate_json(json.dumps(report))


def test_corrupt_retained_result_refuses_export(tmp_path):
    c = client(tmp_path)
    project = c.post('/api/drone/projects/examples/hover', headers=AUTH).json()
    base = '/api/drone/projects/'+project['project_id']
    frozen = c.post(base+'/revisions', headers=AUTH, json={'expected_version':1}).json()
    result = c.post(base+'/studies', headers=AUTH, json={'revision_sha256':frozen['revision_sha256']}).json()
    record = c.get(base, headers=AUTH).json()['studies'][0]
    digest = record['result_sha256']
    path = tmp_path/'artifacts/objects'/digest[:2]/digest
    path.write_bytes(path.read_bytes()+b' ')
    assert c.get(base+'/studies/'+result['study_sha256']+'/export',headers=AUTH).status_code == 422


def test_historical_v2_sequence_reads_exports_and_reports_original_bytes_after_restart(tmp_path, monkeypatch):
    """Old producer fixture is read with its contract, never rewritten as current V3."""
    import sqlite3
    from pathlib import Path

    from physimesh.drone.local_results import LocalCapacityV2
    from physimesh.drone.provenance import canonical_json
    from physimesh.projects.contracts import DesignRevisionV1

    fixture = json.loads((Path(__file__).parent/'fixtures/retained-v2-sequence.json').read_text())
    raw = fixture['original_result_json'].encode()
    report = json.loads(raw)
    assert hashlib.sha256(raw).hexdigest() == fixture['result_sha256']
    assert 'participating_case_bounds' not in report
    LocalCapacityV2.model_validate_json(raw)
    upgraded = {**report, 'schema_version': 'local_mission_capacity_v3'}
    with pytest.raises(ValueError, match='every participating case'):
        LocalCapacityV3.model_validate_json(json.dumps(upgraded))
    revision = DesignRevisionV1.model_validate_json(canonical_json(fixture['revision']))
    pid = revision.project_id; base = '/api/drone/projects/'+pid
    c = client(tmp_path)
    assert c.app.state.projects.artifacts.put_bytes(raw, kind='historical_fixture', meta={}) == fixture['result_sha256']
    with sqlite3.connect(tmp_path/'projects.sqlite') as db:
        db.execute('INSERT INTO project_meta VALUES(?,?,?,?,?,?)',
                   (pid, 'Historical-code compatibility fixture', 2, revision.snapshot_json,
                    revision.created_utc, revision.created_utc))
        db.execute('INSERT INTO design_revisions VALUES(?,?,?,?,?)',
                   (pid, 2, revision.readiness_purpose, revision.revision_sha256(),
                    canonical_json(fixture['revision']).encode()))
        db.execute('INSERT INTO local_studies VALUES(?,?,?,?,?)',
                   (pid, revision.revision_sha256(), report['study_sha256'], fixture['result_sha256'],
                    revision.created_utc))
    c = client(tmp_path)
    def refuse(*args, **kwargs):
        pytest.fail('historical read/report cannot execute current capacity model')
    monkeypatch.setattr('physimesh.projects.studies.capacity_from_snapshot', refuse)
    route = base+'/studies/'+report['study_sha256']
    assert c.get(route, headers=AUTH).json() == report
    assert c.get(route+'/export', headers=AUTH).content == raw
    pdf = c.get(route+'/pdf', headers=AUTH)
    assert pdf.status_code == 200
    assert pdf.headers['X-Study-JSON-SHA256'] == fixture['result_sha256']
    assert c.get(route+'/export', headers=AUTH).content == raw
