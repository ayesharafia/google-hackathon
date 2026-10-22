"""Project geometry survives restart, edits and frozen revisions without byte substitution."""
import hashlib
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.drone.demo_geometry import binary_stl_bytes, icosphere_triangles

AUTH = {'Authorization': 'Bearer test-token'}


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(tmp_path, tmp_path / 'jobs.sqlite', 'test-token', None)))


def create(client, title='Geometry design'):
    return client.post('/api/drone/projects', headers=AUTH, json={'title': title}).json()


def upload(client, diameter=100):
    raw = binary_stl_bytes(icosphere_triangles(diameter, 0))
    response = client.post('/api/drone/import', headers=AUTH, data={'source_units': 'mm'},
                           files={'files': ('airframe.stl', raw, 'model/stl')})
    assert response.status_code == 200, response.text
    return raw, response.json()


def attached(project, report):
    snapshot = json.loads(project['snapshot_json'])
    snapshot['assembly'].update(geometry_import_sha256=report['report_sha256'],
                                geometry_revision_sha256=report['geometry_revision_sha256'],
                                components=deepcopy(report['components']))
    snapshot['units_and_frames'].update(
        source_units=report['conversion']['from'],
        cad_transform={key: report['transform'][key]
                       for key in ('scale', 'rotation_deg_zyx', 'translation_m')})
    return snapshot


def save(client, project, snapshot):
    return client.put('/api/drone/projects/' + project['project_id'] + '/draft', headers=AUTH,
                      json={'expected_version': project['draft_version'], 'snapshot_json': json.dumps(snapshot)})


def test_geometry_original_units_and_record_reopen_after_restart(client):
    project = create(client)
    raw, report = upload(client)
    path = '/api/drone/projects/' + project['project_id']
    assert client.get(path + '/geometry', headers=AUTH).json() == {'report': None}
    saved = save(client, project, attached(project, report))
    assert saved.status_code == 200, saved.text
    restarted = TestClient(create_app(client.app.state.settings))
    reopened = restarted.get(path + '/geometry', headers=AUTH).json()['report']
    assert reopened == report
    assert reopened['unit_scale_to_m'] == 0.001
    digest = hashlib.sha256(raw).hexdigest()
    original = restarted.get(path + '/geometry/' + digest + '.stl', headers=AUTH)
    assert original.status_code == 200 and original.content == raw
    assert original.headers['x-content-sha256'] == digest
    assert original.headers['cache-control'] == 'private, no-store'


def test_multiple_stl_components_retain_separate_originals(client):
    project = create(client)
    sources = [binary_stl_bytes(icosphere_triangles(size, 0)) for size in (100, 50)]
    response = client.post('/api/drone/import', headers=AUTH, data={'source_units': 'mm'},
                           files=[('files', (name, raw, 'model/stl'))
                                  for name, raw in zip(('body.stl', 'hub.stl'), sources)])
    assert response.status_code == 200, response.text
    report = response.json()
    assert save(client, project, attached(project, report)).status_code == 200
    path = '/api/drone/projects/' + project['project_id']
    reopened = client.get(path + '/geometry', headers=AUTH).json()['report']
    assert [c['filename'] for c in reopened['components']] == ['body.stl', 'hub.stl']
    for raw in sources:
        digest = hashlib.sha256(raw).hexdigest()
        assert client.get(path + '/geometry/' + digest + '.stl', headers=AUTH).content == raw


def test_replace_remove_and_frozen_revision_keep_distinct_geometry(client):
    project = create(client)
    raw, first = upload(client)
    project = save(client, project, attached(project, first)).json()
    path = '/api/drone/projects/' + project['project_id']
    frozen = client.post(path + '/revisions', headers=AUTH,
                         json={'expected_version': project['draft_version']}).json()['revision_sha256']
    _, second = upload(client, 200)
    project = save(client, project, attached(project, second)).json()
    old_source = path + '/geometry/' + hashlib.sha256(raw).hexdigest() + '.stl'
    assert client.get(old_source, headers=AUTH).status_code == 404
    assert client.get(old_source, headers=AUTH, params={'revision_sha256': frozen}).content == raw
    snapshot = json.loads(project['snapshot_json'])
    snapshot['assembly'].update(geometry_import_sha256=None, geometry_revision_sha256=None, components=[])
    assert save(client, project, snapshot).status_code == 200
    assert client.get(path + '/geometry', headers=AUTH).json()['report'] is None
    historical = client.get(path + '/geometry', headers=AUTH, params={'revision_sha256': frozen})
    assert historical.json()['report'] == first


def test_geometry_routes_require_auth_and_same_project_reference(client):
    a, b = create(client, 'A'), create(client, 'B')
    raw, report = upload(client)
    a = save(client, a, attached(a, report)).json()
    path = '/api/drone/projects/' + a['project_id']
    source_path = '/geometry/' + hashlib.sha256(raw).hexdigest() + '.stl'
    assert client.get(path + '/geometry').status_code == 401
    assert client.get(path + source_path).status_code == 401
    assert client.get('/api/drone/projects/' + b['project_id'] + source_path, headers=AUTH).status_code == 404
    frozen = client.post(path + '/revisions', headers=AUTH,
                         json={'expected_version': a['draft_version']}).json()['revision_sha256']
    assert client.get('/api/drone/projects/' + b['project_id'] + '/geometry', headers=AUTH,
                      params={'revision_sha256': frozen}).status_code == 404


@pytest.mark.parametrize('changed', ['units', 'source', 'revision', 'transform', 'report'])
def test_inconsistent_geometry_save_keeps_previous_draft(client, changed):
    project = create(client)
    _, report = upload(client)
    snapshot = attached(project, report)
    if changed == 'units':
        snapshot['units_and_frames']['source_units'] = 'm'
    elif changed == 'source':
        snapshot['assembly']['components'][0]['source_sha256'] = '0' * 64
    elif changed == 'revision':
        snapshot['assembly']['geometry_revision_sha256'] = '0' * 64
    elif changed == 'transform':
        snapshot['units_and_frames']['cad_transform']['scale'] = 2
    else:
        snapshot['assembly']['geometry_import_sha256'] = '0' * 64
    assert save(client, project, snapshot).status_code == 422
    retained = client.get('/api/drone/projects/' + project['project_id'], headers=AUTH).json()
    assert retained['snapshot_json'] == project['snapshot_json'] and retained['draft_version'] == 0


def test_corrupt_original_is_refused_by_read_save_and_freeze(client):
    project = create(client)
    raw, report = upload(client)
    project = save(client, project, attached(project, report)).json()
    digest = hashlib.sha256(raw).hexdigest()
    object_path = client.app.state.settings.data_root / 'artifacts' / 'objects' / digest[:2] / digest
    object_path.write_bytes(b'changed geometry')
    path = '/api/drone/projects/' + project['project_id']
    response = client.get(path + '/geometry/' + digest + '.stl', headers=AUTH)
    assert response.status_code == 422 and 'integrity' in response.text
    assert save(client, project, json.loads(project['snapshot_json'])).status_code == 422
    assert client.post(path + '/revisions', headers=AUTH,
                       json={'expected_version': project['draft_version']}).status_code == 422
    assert client.get(path, headers=AUTH).json()['draft_version'] == project['draft_version']


def test_invalid_upload_and_stale_save_do_not_replace_saved_geometry(client):
    project = create(client)
    _, first = upload(client)
    stale = save(client, project, attached(project, first)).json()
    newer = save(client, stale, json.loads(stale['snapshot_json'])).json()
    failed = client.post('/api/drone/import', headers=AUTH, data={'source_units': 'mm'},
                         files={'files': ('broken.stl', b'not an STL', 'model/stl')})
    assert failed.status_code == 422
    _, second = upload(client, 200)
    assert save(client, stale, attached(stale, second)).status_code == 409
    path = '/api/drone/projects/' + project['project_id']
    assert client.get(path, headers=AUTH).json() == newer
    assert client.get(path + '/geometry', headers=AUTH).json()['report'] == first


def test_component_tagging_does_not_detach_original_geometry(client):
    project = create(client)
    _, report = upload(client)
    snapshot = attached(project, report)
    snapshot['assembly']['components'][0].update(role='airframe', requires_user_tag=False, rotor_id=None)
    assert save(client, project, snapshot).status_code == 200
    path = '/api/drone/projects/' + project['project_id']
    assert client.get(path + '/geometry', headers=AUTH).json()['report'] == report
