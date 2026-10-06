"""Actual PostgreSQL behavior, enabled by CI/service-local test DSN."""
import concurrent.futures
import json
import os
from uuid import uuid4

import pytest

from physimesh.core.artifacts import ArtifactStore
from physimesh.platform.database import MetadataDB
from physimesh.platform.identity import Identity
from physimesh.platform.jobs import Jobs, StaleAttempt
from physimesh.platform.postgres import PostgreSQLProjects
from physimesh.projects.contracts import snapshot_json
from physimesh.projects.repository import DraftConflict
from physimesh.projects.service import ProjectService

pytestmark = pytest.mark.integration


@pytest.fixture
def database():
    url = os.environ.get('PHYSIMESH_TEST_DATABASE_URL')
    if not url:
        pytest.skip('explicit PostgreSQL integration DSN is required')
    import psycopg
    from psycopg import sql
    schema = 'fixture_'+uuid4().hex
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    database = MetadataDB(url=url, pool_size=8, schema=schema)
    try:
        yield database
    finally:
        database.close()
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def test_fifty_independent_writers_and_contested_optimistic_version(database, tmp_path):
    repo = PostgreSQLProjects(database)
    projects = ProjectService(repo, ArtifactStore(tmp_path/'files'))
    seed = projects.create('Synthetic PostgreSQL write fixture')
    snapshot = json.loads(seed['snapshot_json'])
    ids = [seed['project_id']]+[repo.create(f'Synthetic concurrent {n}', seed['snapshot_json'])['project_id']
                               for n in range(49)]
    def save(pid):
        changed = json.loads(seed['snapshot_json'])
        changed['identity']['description'] = 'Independent writer '+pid
        return repo.save(pid, 0, snapshot_json(changed))
    with concurrent.futures.ThreadPoolExecutor(50) as pool:
        saved = list(pool.map(save, ids))
    assert len(saved) == 50 and all(r['draft_version'] == 1 for r in saved)
    def contested(n):
        changed = {**snapshot, 'identity': {**snapshot['identity'], 'description': f'Contender {n}'}}
        try:
            return ('saved', repo.save(ids[0], 1, snapshot_json(changed))['draft_version'])
        except DraftConflict as exc:
            return ('conflict', exc.current_version)
    with concurrent.futures.ThreadPoolExecutor(50) as pool:
        outcomes = list(pool.map(contested, range(50)))
    assert sum(state == 'saved' for state, version in outcomes) == 1
    assert sum(state == 'conflict' and version == 2 for state, version in outcomes) == 49
    assert repo.get(ids[0])['draft_version'] == 2
    # Verify one actual accepted contender; all others reported the current version.
    assert json.loads(repo.get(ids[0])['snapshot_json'])['identity']['description'].startswith('Contender ')


def test_postgres_leases_fences_and_tenant_inventory(database, tmp_path):
    identity = Identity(database)
    uid = identity.provision(uuid4().hex+'@example.test', password='synthetic-password-123')
    principal = identity.session(identity.login(
        # Read the administrative identity without leaking its credential in logs.
        next_email(identity, uid), 'synthetic-password-123')['token'])
    org = identity.organization(uid, 'Synthetic hosted integration')
    repo = PostgreSQLProjects(database)
    projects = ProjectService(repo, ArtifactStore(tmp_path/'files'))
    first, second = projects.create('Private A'), projects.create('Private B')
    identity.claim_project(principal, org, first['project_id'])
    assert [p['project_id'] for p in repo.page(user_id=uid)['projects']] == [first['project_id']]
    now = [100.]
    jobs = Jobs(database, clock=lambda: now[0], lease_s=5)
    submitted = jobs.submit(first['project_id'], 'study', {'revision': 'synthetic'})
    claim = jobs.claim('pg_worker_a')
    now[0] += 6
    new = jobs.claim('pg_worker_b')
    with pytest.raises(StaleAttempt):
        jobs.complete(claim, {'stale': True})
    jobs.complete(new, {'accepted': True})
    assert jobs.get(first['project_id'], submitted['job_id'])['state'] == 'succeeded'
    assert second['project_id'] not in [p['project_id'] for p in repo.page(user_id=uid)['projects']]


def next_email(identity, uid):
    with identity.database.connection() as db:
        return db.execute('SELECT email FROM users WHERE user_id=?', (uid,)).fetchone()[0]
