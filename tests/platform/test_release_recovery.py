import hashlib
import sqlite3

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.platform.backup import backup_local, restore_local
from physimesh.platform.database import MetadataDB
from physimesh.platform.identity import Identity
from physimesh.platform.jobs import Jobs


def test_backup_restore_preserves_database_and_refuses_corruption(tmp_path):
    live, snapshot, restored = (tmp_path/name for name in ('live', 'backup', 'restored'))
    live.mkdir()
    with sqlite3.connect(live/'projects.sqlite') as db:
        db.execute('CREATE TABLE evidence(value TEXT)')
        db.execute("INSERT INTO evidence VALUES ('historical bytes')")
    (live/'artifacts').mkdir()
    (live/'artifacts'/'fixture').write_bytes(b'immutable evidence')
    receipt = backup_local(live, snapshot)
    assert restore_local(snapshot, restored, manifest_sha256=receipt['manifest_sha256'])['files'] == 2
    with sqlite3.connect(restored/'projects.sqlite') as db:
        assert db.execute('SELECT value FROM evidence').fetchone()[0] == 'historical bytes'
    assert (restored/'artifacts'/'fixture').read_bytes() == b'immutable evidence'
    with pytest.raises(ValueError, match='new'):
        restore_local(snapshot, restored, manifest_sha256=receipt['manifest_sha256'])
    (snapshot/'artifacts'/'fixture').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='integrity'):
        restore_local(snapshot, tmp_path/'corrupt', manifest_sha256=receipt['manifest_sha256'])
    (snapshot/'artifacts'/'fixture').write_bytes(b'immutable evidence')
    (snapshot/'extra').write_bytes(b'unlisted')
    with pytest.raises(ValueError, match='unlisted'):
        restore_local(snapshot, tmp_path/'extra', manifest_sha256=receipt['manifest_sha256'])
    assert not (tmp_path/'extra').exists()
    with pytest.raises(ValueError, match='manifest integrity'):
        restore_local(snapshot, tmp_path/'forged', manifest_sha256='0'*64)
    with pytest.raises(ValueError, match='must exist'):
        backup_local(tmp_path/'missing', tmp_path/'empty')


def test_build_bound_jobs_cannot_be_claimed_by_a_different_release(tmp_path):
    db = MetadataDB(tmp_path/'metadata.sqlite')
    identity = Identity(db)
    uid = identity.provision('owner@example.test', password='synthetic-password')
    principal = identity.session(identity.login('owner@example.test', 'synthetic-password')['token'])
    org = identity.organization(uid, 'fixture')
    identity.claim_project(principal, org, 'project_fixture')
    jobs = Jobs(db)
    job = jobs.submit('project_fixture', 'study', {'application_build': 'a'*64})
    assert jobs.claim('wrong-build', build_sha256='b'*64) is None
    claim = jobs.claim('correct-build', build_sha256='a'*64)
    assert claim['job_id'] == job['job_id']
    jobs.complete(claim, {'immutable_result': 'accepted'})
    # Ledger acceptance survives closing/reopening connections.
    reopened = Jobs(MetadataDB(tmp_path/'metadata.sqlite'))
    assert reopened.get('project_fixture', job['job_id'])['state'] == 'succeeded'


def test_hosted_http_authorization_body_limits_metrics_and_project_reservation(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', '', None, hosted_mode=True,
                              monitoring_token='synthetic-operations-token'))
    identity = app.state.identity
    uid = identity.provision('owner@example.test', password='synthetic-password')
    identity.provision('outsider@example.test', password='synthetic-password')
    org = identity.organization(uid, 'fixture')
    with TestClient(app) as client:
        assert client.get('/api/drone/projects').status_code == 401
        token = client.post('/api/drone/platform/login', json={'email': 'owner@example.test',
                            'password': 'synthetic-password'}).json()['token']
        headers = {'Authorization': 'Bearer '+token, 'X-Organization-ID': org}
        # Reservation expires without consuming a project and can be explicitly released.
        principal = identity.session(token)
        reservation = identity.reserve_project(principal, org)
        identity.release_project_reservation(reservation)
        project = client.post('/api/drone/projects/examples/realistic', headers=headers).json()
        base = '/api/drone/projects/'+project['project_id']
        assert client.get(base).status_code == 401
        outsider = client.post('/api/drone/platform/login', json={'email': 'outsider@example.test',
                               'password': 'synthetic-password'}).json()['token']
        assert client.get(base, headers={'Authorization': 'Bearer '+outsider}).status_code == 403
        assert client.post('/api/drone/projects', headers={**headers, 'Content-Length': '7000000'},
                           content=b'{}').status_code == 413
        assert client.get('/internal/metrics').status_code == 401
        metrics = client.get('/internal/metrics', headers={'Authorization': 'Bearer synthetic-operations-token'})
        assert metrics.status_code == 200 and 'physimesh_handler_seconds_count' in metrics.text
        assert project['project_id'] not in metrics.text and token not in metrics.text
        with app.state.metadata.connection() as db:
            assert db.execute('SELECT COUNT(*) FROM project_reservations').fetchone()[0] == 0
        assert client.post('/api/drone/platform/logout', headers=headers).status_code == 200
        assert client.get(base, headers=headers).status_code == 401


def test_manifest_digest_is_external_to_backup(tmp_path):
    root = tmp_path/'live'
    root.mkdir()
    with sqlite3.connect(root/'projects.sqlite') as db:
        db.execute('CREATE TABLE fixture(value INTEGER)')
    (root/'artifacts').mkdir()
    receipt = backup_local(root, tmp_path/'snapshot')
    assert hashlib.sha256((tmp_path/'snapshot'/'manifest.jsonl').read_bytes()).hexdigest() == receipt['manifest_sha256']


def test_review_export_is_scoped_and_does_not_approve_physics(tmp_path):
    from physimesh.platform.scoped_artifacts import artifact_scope
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', '', None, hosted_mode=True))
    identity = app.state.identity
    owner = identity.provision('owner@example.test', password='synthetic-password')
    outsider = identity.provision('outsider@example.test', password='synthetic-password')
    owner_token = identity.login('owner@example.test', 'synthetic-password')['token']
    outsider_token = identity.login('outsider@example.test', 'synthetic-password')['token']
    org = identity.organization(owner, 'review fixture')
    with TestClient(app) as client:
        headers = {'Authorization': 'Bearer '+owner_token, 'X-Organization-ID': org}
        project = client.post('/api/drone/projects/examples/realistic', headers=headers).json()
        pid = project['project_id']
        with artifact_scope(pid):
            revision = app.state.projects.freeze(pid, project['draft_version'], 'screening')
            study = app.state.studies.run(pid, revision['revision_sha256'])
        assert study['engineering_approval'] == 'pending'
        path = '/api/drone/platform/reviews/'+pid
        assert client.post(path, headers=headers, json={'study_sha256': '0'*64, 'decision': 'comment',
                                                       'comment': 'missing'}).status_code == 404
        record = client.post(path, headers=headers, json={'study_sha256': study['study_sha256'],
                             'decision': 'accepted', 'comment': 'Synthetic workflow review only'})
        assert record.status_code == 201, record.text
        export = path+'/'+record.json()['review_id']+'/export'
        unauthorized = client.get(export, headers={'Authorization': 'Bearer '+outsider_token})
        assert unauthorized.status_code == 403
        downloaded = client.get(export, headers=headers)
        assert downloaded.status_code == 200
        assert downloaded.headers['X-Content-SHA256'] == hashlib.sha256(downloaded.content).hexdigest()
        assert downloaded.json()['review']['user_id'] == owner
        with artifact_scope(pid):
            assert app.state.studies.read(pid, study['study_sha256'])['engineering_approval'] == 'pending'
        assert outsider != owner
