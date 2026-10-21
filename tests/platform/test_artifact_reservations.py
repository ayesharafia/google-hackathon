"""Publication failures never manufacture access or permanently consume admission."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest

from physimesh.core.artifacts import ArtifactStore
from physimesh.platform.database import MetadataDB, Overloaded
from physimesh.platform.identity import Denied, Identity, Principal
from physimesh.platform.scoped_artifacts import ScopedArtifacts, artifact_scope


@pytest.fixture
def platform(tmp_path):
    now = [1000.]
    database = MetadataDB(tmp_path/'platform.sqlite')
    identity = Identity(database, clock=lambda: now[0])
    user = identity.provision('owner@example.test', password='fixture-password-123')
    principal = Principal(user, 'owner@example.test')
    org = identity.organization(user, 'Artifact accounting fixture')
    for project in ('project_a', 'project_b'):
        identity.claim_project(principal, org, project)
    return identity, ArtifactStore(tmp_path/'files'), now


def counts(identity):
    with identity.database.connection() as db:
        return (db.execute('SELECT artifact_bytes FROM platform_quota WHERE quota_id=1').fetchone()[0],
                db.execute('SELECT COUNT(*) FROM artifact_access').fetchone()[0],
                db.execute('SELECT COUNT(*) FROM artifact_reservations').fetchone()[0])


@pytest.mark.parametrize('partial', [False, True])
def test_failed_write_or_metadata_publication_grants_no_access_and_retry_succeeds(platform, monkeypatch, partial):
    identity, backend, _ = platform
    store = ScopedArtifacts(backend, identity)
    raw = b'private failure fixture'
    digest = hashlib.sha256(raw).hexdigest()
    original = backend.put_bytes

    def fail(*args, **kwargs):
        if partial:
            backend._atomic_write(backend._obj(digest), raw)
        raise OSError('synthetic storage failure')

    monkeypatch.setattr(backend, 'put_bytes', fail)
    with artifact_scope('project_a'), pytest.raises(OSError):
        store.put_bytes(raw, kind='fixture', meta={})
    assert counts(identity) == (0, 0, 0)
    with artifact_scope('project_a'), pytest.raises(Denied):
        store.open(digest)
    monkeypatch.setattr(backend, 'put_bytes', original)
    with artifact_scope('project_a'):
        assert store.put_bytes(raw, kind='fixture', meta={}) == digest
        assert store.open(digest).read() == raw
    assert counts(identity) == (len(raw), 1, 0)


def test_concurrent_identical_writes_charge_once_and_isolate_projects(platform):
    identity, backend, _ = platform
    store = ScopedArtifacts(backend, identity)
    barrier = Barrier(8)

    def write(_):
        with artifact_scope('project_a'):
            barrier.wait()
            return store.put_bytes(b'shared bytes', kind='fixture', meta={})

    with ThreadPoolExecutor(8) as pool:
        digests = list(pool.map(write, range(8)))
    assert len(set(digests)) == 1
    assert counts(identity) == (12, 1, 0)
    with artifact_scope('project_b'), pytest.raises(Denied):
        store.open(digests[0])
    with artifact_scope('project_b'):
        assert store.put_bytes(b'shared bytes', kind='fixture', meta={}) == digests[0]
    assert counts(identity) == (24, 2, 0)


def test_failed_concurrent_writer_does_not_revoke_successful_writer(platform, monkeypatch):
    identity, backend, _ = platform
    store = ScopedArtifacts(backend, identity)
    admitted, published = Event(), Event()
    original = backend.put_bytes

    def put(data, *, kind, meta):
        if meta.get('fail'):
            admitted.set()
            assert published.wait(5)
            raise OSError('late failed writer')
        return original(data, kind=kind, meta=meta)

    monkeypatch.setattr(backend, 'put_bytes', put)

    def failed():
        with artifact_scope('project_a'), pytest.raises(OSError):
            store.put_bytes(b'winner', kind='fixture', meta={'fail': True})

    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(failed)
        try:
            assert admitted.wait(5)
            with artifact_scope('project_a'):
                digest = store.put_bytes(b'winner', kind='fixture', meta={})
        finally:
            published.set()
        future.result()
    identity.require_artifact('project_a', digest)
    assert counts(identity) == (6, 1, 0)


def test_expired_crashed_reservations_recover_and_late_writers_cannot_finalize(platform):
    identity, _, now = platform
    first = identity.reserve_artifact('project_a', 'a'*64, 5_000_000_000)
    with pytest.raises(Denied, match='budget'):
        identity.reserve_artifact('project_a', 'b'*64, 1)
    assert counts(identity) == (0, 0, 1)
    now[0] += 301
    replacement = identity.reserve_artifact('project_a', 'b'*64, 1)
    with pytest.raises(Denied, match='expired'):
        identity.finish_artifact(first)
    identity.finish_artifact(replacement)
    assert counts(identity) == (1, 1, 0)


def test_pending_duplicates_reserve_once_but_other_grants_cannot_exceed_budget(platform):
    identity, _, _ = platform
    first = identity.reserve_artifact('project_a', 'a'*64, 5_000_000_000)
    second = identity.reserve_artifact('project_a', 'a'*64, 5_000_000_000)
    with pytest.raises(Denied, match='budget'):
        identity.grant_artifact('project_a', 'b'*64, 1)
    identity.finish_artifact(second)
    identity.cancel_artifact(first)
    assert counts(identity) == (5_000_000_000, 1, 0)
    with pytest.raises(ValueError, match='size'):
        identity.grant_artifact('project_a', 'a'*64, 0)


def test_finalization_or_cleanup_database_failure_leaves_only_expiring_reservation(platform, monkeypatch):
    identity, backend, now = platform
    store = ScopedArtifacts(backend, identity)
    finish, cancel = identity.finish_artifact, identity.cancel_artifact

    def unavailable(*args):
        raise Overloaded('synthetic metadata outage')

    monkeypatch.setattr(identity, 'finish_artifact', unavailable)
    monkeypatch.setattr(identity, 'cancel_artifact', unavailable)
    with artifact_scope('project_a'), pytest.raises(Overloaded):
        store.put_bytes(b'recover', kind='fixture', meta={})
    assert counts(identity) == (0, 0, 1)
    monkeypatch.setattr(identity, 'finish_artifact', finish)
    monkeypatch.setattr(identity, 'cancel_artifact', cancel)
    now[0] += 301
    with artifact_scope('project_a'):
        store.put_bytes(b'recover', kind='fixture', meta={})
    assert counts(identity) == (7, 1, 0)


def test_global_pending_budget_is_shared_and_cancellation_releases_admission(platform):
    identity, _, _ = platform
    # Synthetic aggregate baseline avoids allocating 50 GB of fixture bytes.
    with identity.database.connection(write=True) as db:
        db.execute('UPDATE platform_quota SET artifact_bytes=49999999990 WHERE quota_id=1')
    first = identity.reserve_artifact('project_a', 'a'*64, 10)
    duplicate = identity.reserve_artifact('project_a', 'a'*64, 10)
    with pytest.raises(Denied, match='budget'):
        identity.reserve_artifact('project_b', 'b'*64, 1)
    identity.cancel_artifact(first)
    with pytest.raises(Denied, match='budget'):
        identity.grant_artifact('project_b', 'b'*64, 1)
    identity.cancel_artifact(duplicate)
    identity.grant_artifact('project_b', 'b'*64, 1)
    assert counts(identity) == (49_999_999_991, 1, 0)


def test_failed_retry_preserves_prior_entitlement(platform, monkeypatch):
    identity, backend, _ = platform
    store = ScopedArtifacts(backend, identity)
    with artifact_scope('project_a'):
        digest = store.put_bytes(b'original', kind='fixture', meta={})

    def unavailable(*args, **kwargs):
        raise OSError('retry failed')

    monkeypatch.setattr(backend, 'put_bytes', unavailable)
    with artifact_scope('project_a'), pytest.raises(OSError):
        store.put_bytes(b'original', kind='fixture', meta={})
    identity.require_artifact('project_a', digest)
    assert counts(identity) == (8, 1, 0)


def test_backend_content_identity_mismatch_cannot_grant_access(platform, monkeypatch):
    identity, backend, _ = platform
    monkeypatch.setattr(backend, 'put_bytes', lambda *args, **kwargs: 'f'*64)
    with artifact_scope('project_a'), pytest.raises(ValueError, match='different content identity'):
        ScopedArtifacts(backend, identity).put_bytes(b'wrong backend identity', kind='fixture', meta={})
    assert counts(identity) == (0, 0, 0)


def test_migration_from_v5_preserves_existing_grants_and_rejects_future_versions(platform):
    identity, _, _ = platform
    identity.grant_artifact('project_a', 'a'*64, 17)
    with identity.database.connection(write=True) as db:
        db.execute('DROP TABLE artifact_reservations')
        db.execute('DELETE FROM platform_migrations WHERE version=6')
    upgraded = Identity(identity.database)
    upgraded.require_artifact('project_a', 'a'*64)
    assert counts(upgraded) == (17, 1, 0)
    with identity.database.connection(write=True) as db:
        db.execute('INSERT INTO platform_migrations VALUES(7)')
    with pytest.raises(ValueError, match='unsupported platform migration'):
        Identity(identity.database)
