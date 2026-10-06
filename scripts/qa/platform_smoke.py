#!/usr/bin/env python3
"""Local hosted-mode synthetic journey: sessions, private projects, worker and reports.

Use runtime credentials only. No provider/aircraft qualification is implied.
"""
import json
import os
import secrets
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.platform.worker import run_one


def run(root):
    settings = Settings(root, root/'jobs.sqlite', '', None, hosted_mode=True)
    app = create_app(settings)
    identity = app.state.identity
    owner_password, viewer_password = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    owner_id = identity.provision('owner@example.test', password=owner_password)
    identity.provision('viewer@example.test', password=viewer_password)
    org = identity.organization(owner_id, 'Synthetic smoke organization')
    client = TestClient(app)
    owner_token = client.post('/api/drone/platform/login', json={
        'email': 'owner@example.test', 'password': owner_password}).json()['token']
    viewer_token = client.post('/api/drone/platform/login', json={
        'email': 'viewer@example.test', 'password': viewer_password}).json()['token']
    owner = {'Authorization': 'Bearer '+owner_token, 'X-Organization-ID': org}
    viewer = {'Authorization': 'Bearer '+viewer_token}
    project = client.post('/api/drone/projects/examples/realistic', headers=owner)
    assert project.status_code == 201, project.text
    project = project.json()
    base = '/api/drone/projects/'+project['project_id']
    assert client.get(base, headers=viewer).status_code == 403
    invitation = client.post('/api/drone/platform/projects/'+project['project_id']+'/invitations',
                             headers=owner, json={'email': 'viewer@example.test', 'role': 'viewer'})
    assert invitation.status_code == 201, invitation.text
    accepted = client.post('/api/drone/platform/invitations/accept', headers=viewer,
                           json={'invitation_token': invitation.json()['invitation_token']})
    assert accepted.status_code == 200, accepted.text
    assert client.get(base, headers=viewer).status_code == 200
    assert client.put(base+'/draft', headers=viewer, json={
        'expected_version': project['draft_version'], 'snapshot_json': project['snapshot_json']}).status_code == 403
    revision = client.post(base+'/revisions', headers=owner,
                           json={'expected_version': project['draft_version']})
    assert revision.status_code == 200, revision.text
    submitted = client.post(base+'/studies', headers=owner,
                            json={'revision_sha256': revision.json()['revision_sha256']})
    assert submitted.status_code == 202, submitted.text
    job = submitted.json()
    # Subprocess configuration matches this synthetic app, never printed or saved.
    os.environ.update(PHYSIMESH_MODE='hosted', PHYSIMESH_DATA_ROOT=str(root),
                      PHYSIMESH_DB_PATH=str(root/'jobs.sqlite'))
    assert run_one(app, 'smoke-study-worker')
    completed = client.get(base+'/jobs/'+job['job_id'], headers=owner)
    assert completed.status_code == 200 and completed.json()['state'] == 'succeeded', completed.text
    record = json.loads(completed.json()['result_json'])
    study = client.get(base+'/studies/'+record['study_sha256'], headers=viewer)
    assert study.status_code == 200 and study.json()['outcome'] == 'feasible', study.text
    path = base+'/studies/'+record['study_sha256']+'/pdf'
    first = client.get(path, headers=viewer)
    assert first.status_code == 202, first.text
    assert run_one(app, 'smoke-report-worker')
    pdf = client.get(path, headers=viewer)
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF-'), pdf.text
    assert client.get(path, headers=viewer).content == pdf.content
    assert client.post('/api/drone/platform/logout', headers=viewer).status_code == 200
    assert client.get(base, headers=viewer).status_code == 401
    print(json.dumps({'fixture': 'analytic V4 only', 'journey': 'passed',
                      'individual_sessions': 'passed', 'viewer_write_denial': 'passed',
                      'private_project_denial': 'passed', 'queued_study': 'passed',
                      'queued_report_and_verified_reuse': 'passed', 'revocation': 'passed'}))
    app.state.metadata.close()


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='physimesh-platform-') as directory:
        run(Path(directory))
