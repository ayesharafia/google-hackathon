"""Public persistence behavior across connections, restarts and conflicting requests."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.core.artifacts import ArtifactStore
from physimesh.projects.repository import DraftConflict
from physimesh.projects.service import ProjectService
from physimesh.projects.sqlite import SQLiteProjects

AUTH = {'Authorization': 'Bearer test-token'}


def service(tmp_path):
    return ProjectService(SQLiteProjects(tmp_path / 'projects.sqlite'), ArtifactStore(tmp_path / 'artifacts'))


def test_restart_repeated_freeze_and_edit_preserve_original(tmp_path):
    first = service(tmp_path)
    project = first.create('Retained design')
    pid = project['project_id']
    frozen = first.freeze(pid, 0, 'screening')
    restarted = service(tmp_path)
    assert restarted.repository.get(pid)['snapshot_json'] == project['snapshot_json']
    assert restarted.freeze(pid, 0, 'screening') == frozen
    snapshot = json.loads(project['snapshot_json'])
    snapshot['identity']['description'] = 'Edited'
    saved = restarted.save(pid, 0, json.dumps(snapshot))
    assert saved['draft_version'] == 1
    original = restarted.repository.revision(pid, frozen['revision_sha256'])
    assert original.snapshot_json == project['snapshot_json'] and original.approval == 'draft'
    with pytest.raises(DraftConflict):
        restarted.freeze(pid, 0, 'screening')


def test_independent_simultaneous_connections_have_one_winning_save(tmp_path):
    first, second = service(tmp_path), service(tmp_path)
    project = first.create('Concurrent design')
    barrier = Barrier(2)

    def edit(app, label):
        snapshot = json.loads(project['snapshot_json'])
        snapshot['identity']['description'] = label
        barrier.wait()
        try:
            return app.save(project['project_id'], 0, json.dumps(snapshot))
        except DraftConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        a = executor.submit(edit, first, 'A')
        b = executor.submit(edit, second, 'B')
        outcomes = [a.result(), b.result()]
    assert sum(isinstance(outcome, DraftConflict) for outcome in outcomes) == 1
    winner = next(outcome for outcome in outcomes if isinstance(outcome, dict))
    assert service(tmp_path).repository.get(project['project_id']) == winner


def test_nonfinite_duplicate_and_missing_sources_refuse_without_losing_draft(tmp_path):
    app = service(tmp_path)
    project = app.create('Integrity')
    for raw in ('{"identity":{},"identity":{}}', '{"value":NaN}'):
        with pytest.raises(ValueError):
            app.save(project['project_id'], 0, raw)
    assert app.repository.get(project['project_id'])['draft_version'] == 0
    snapshot = json.loads(project['snapshot_json'])
    snapshot['assembly']['components'] = [{'source_sha256': '0' * 64}]
    app.save(project['project_id'], 0, json.dumps(snapshot))
    with pytest.raises(ValueError, match='not retained'):
        app.freeze(project['project_id'], 1, 'screening')


def test_frozen_revision_cannot_be_read_through_another_project(tmp_path):
    app = service(tmp_path)
    a, b = app.create('A'), app.create('B')
    frozen = app.freeze(a['project_id'], 0, 'screening')
    from physimesh.projects.repository import ProjectMissing
    with pytest.raises(ProjectMissing):
        app.repository.revision(b['project_id'], frozen['revision_sha256'])


def test_api_local_journey_restart_conflict_and_auth(tmp_path):
    settings = Settings(tmp_path, tmp_path / 'jobs.sqlite', 'test-token', None)
    client = TestClient(create_app(settings))
    assert client.get('/api/drone/projects').status_code == 401
    assert client.post('/api/drone/projects', headers=AUTH, json={'title': '  '}).status_code == 422
    project = client.post('/api/drone/projects', headers=AUTH, json={'title': 'API design'}).json()
    path = '/api/drone/projects/' + project['project_id']
    data = {'expected_version': 0, 'snapshot_json': project['snapshot_json']}
    assert client.put(path + '/draft', headers=AUTH, json=data).json()['draft_version'] == 1
    conflict = client.put(path + '/draft', headers=AUTH, json=data)
    assert conflict.status_code == 409 and conflict.json()['detail']['current_version'] == 1
    assert client.post(path + '/revisions', headers=AUTH,
                       json={'expected_version': 0}).status_code == 409
    frozen = client.post(path + '/revisions', headers=AUTH,
                         json={'expected_version': 1}).json()
    client = TestClient(create_app(settings))
    assert client.get(path, headers=AUTH).json()['draft_version'] == 1
    assert client.get(path + '/revisions/' + frozen['revision_sha256'], headers=AUTH).json()['approval'] == 'draft'
    assert client.get('/api/drone/projects/missing', headers=AUTH).status_code == 404
