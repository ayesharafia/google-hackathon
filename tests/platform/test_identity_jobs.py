import concurrent.futures

import pytest

from physimesh.core.artifacts import ArtifactStore
from physimesh.platform.database import MetadataDB, Overloaded
from physimesh.platform.identity import Denied, Identity, InvalidSession
from physimesh.platform.jobs import Jobs, StaleAttempt
from physimesh.platform.scoped_artifacts import ScopedArtifacts, artifact_scope


@pytest.fixture
def platform(tmp_path):
    now = [1000.]
    db = MetadataDB(tmp_path/'platform.sqlite')
    identity = Identity(db, clock=lambda: now[0])
    owner = identity.provision('owner@example.test', password='fixture-password-123')
    other = identity.provision('viewer@example.test', password='fixture-password-456')
    owner_principal = identity.session(identity.login('owner@example.test', 'fixture-password-123')['token'])
    viewer = identity.session(identity.login('viewer@example.test', 'fixture-password-456')['token'])
    org = identity.organization(owner, 'Synthetic local integration')
    identity.claim_project(owner_principal, org, 'project_a')
    identity.claim_project(owner_principal, org, 'project_b')
    return identity, owner_principal, viewer, now, db, other


def test_session_expiration_revocation_and_invitation_boundaries(platform):
    identity, owner, viewer, now, _, _ = platform
    with pytest.raises(Denied):
        identity.authorize(viewer, 'project_a')
    invite = identity.invite(owner, 'project_a', viewer.email, 'viewer')['invitation_token']
    with pytest.raises(Denied):
        identity.accept(owner, invite)
    identity.accept(viewer, invite)
    assert identity.authorize(viewer, 'project_a')
    with pytest.raises(Denied):
        identity.accept(viewer, invite)
    with pytest.raises(Denied):
        identity.authorize(viewer, 'project_a', write=True)
    with pytest.raises(Denied):
        identity.authorize(viewer, 'project_a', review=True)
    with pytest.raises(Denied):
        identity.authorize(viewer, 'project_b')
    token = identity.login(viewer.email, 'fixture-password-456')['token']
    identity.revoke(viewer, all_sessions=True)
    with pytest.raises(InvalidSession):
        identity.session(token)
    token = identity.login(owner.email, 'fixture-password-123')['token']
    now[0] += 43201
    with pytest.raises(InvalidSession):
        identity.session(token)


def test_wrong_password_throttles_without_creating_sessions(platform):
    identity, _, viewer, now, _, _ = platform
    with pytest.raises(InvalidSession):
        identity.login(viewer.email, 'incorrect-password-123')
    with pytest.raises(InvalidSession, match='throttled'):
        identity.login(viewer.email, 'fixture-password-456')
    now[0] += 3
    assert identity.login(viewer.email, 'fixture-password-456')['token']


def test_artifact_hash_is_not_project_authorization(platform, tmp_path):
    identity, owner, viewer, _, _, _ = platform
    store = ScopedArtifacts(ArtifactStore(tmp_path/'files'), identity)
    with artifact_scope('project_a'):
        digest = store.put_bytes(b'private bytes', kind='fixture', meta={})
    with artifact_scope('project_b'), pytest.raises(Denied):
        store.open(digest)
    with pytest.raises(Denied):
        store.open(digest)
    invitation = identity.invite(owner, 'project_a', viewer.email, 'reviewer')['invitation_token']
    identity.accept(viewer, invitation)
    identity.authorize(viewer, 'project_a', review=True)
    with artifact_scope('project_a'):
        assert store.open(digest).read() == b'private bytes'
    identity.remove_member(owner, 'project_a', viewer.user_id)
    with pytest.raises(Denied):
        identity.authorize(viewer, 'project_a')


def test_fencing_recovery_cancellation_and_immutable_accepted_result(platform):
    _, _, _, now, db, _ = platform
    jobs = Jobs(db, clock=lambda: now[0], lease_s=5)
    submitted = jobs.submit('project_a', 'study', {'revision': 'fixture'})
    assert jobs.submit('project_a', 'study', {'revision': 'fixture'})['job_id'] == submitted['job_id']
    first = jobs.claim('worker_a')
    jobs.heartbeat(first, .25, 'integrity checks')
    now[0] += 6
    second = jobs.claim('worker_b')
    assert second['generation'] == 2
    with pytest.raises(StaleAttempt):
        jobs.complete(first, {'result_sha256': 'stale'})
    jobs.complete(second, {'result_sha256': 'accepted'})
    with pytest.raises(StaleAttempt):
        jobs.complete(second, {'result_sha256': 'replacement'})
    retained = jobs.get('project_a', submitted['job_id'])
    assert retained['state'] == 'succeeded'
    assert 'accepted' in retained['result_json'] and 'replacement' not in retained['result_json']
    assert [a['state'] for a in retained['attempts']] == ['expired', 'accepted']
    jobs.cancel('project_a', submitted['job_id'])
    assert jobs.get('project_a', submitted['job_id'])['state'] == 'succeeded'
    queued = jobs.submit('project_a', 'report', {'study': 'fixture'})
    claim = jobs.claim('worker_c')
    jobs.cancel('project_a', queued['job_id'])
    with pytest.raises(StaleAttempt):
        jobs.heartbeat(claim)
    with pytest.raises(StaleAttempt):
        jobs.complete(claim, {'pdf': 'cancelled'})
    jobs.retry('project_a', queued['job_id'])
    new = jobs.claim('worker_d')
    assert new['generation'] > claim['generation']
    jobs.fail(new, 'permanent error', retry=False)
    with pytest.raises(Denied):
        jobs.get('project_b', queued['job_id'])


def test_bounded_admission_and_atomic_concurrent_claims(platform):
    _, _, _, now, db, _ = platform
    jobs = Jobs(db, clock=lambda: now[0], per_project_limit=2, queue_limit=3, max_running=1)
    jobs.submit('project_a', 'study', {'revision': 'one'})
    jobs.submit('project_a', 'study', {'revision': 'two'})
    with pytest.raises(Overloaded):
        jobs.submit('project_a', 'study', {'revision': 'three'})
    with concurrent.futures.ThreadPoolExecutor(10) as pool:
        claims = list(pool.map(lambda n: jobs.claim(f'worker_{n}'), range(10)))
    assert sum(claim is not None for claim in claims) == 1
    jobs.complete(next(c for c in claims if c), {'accepted': 'one'})
    assert jobs.claim('next')
