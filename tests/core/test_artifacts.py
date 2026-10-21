import hashlib

import pytest

from physimesh.core.artifacts import ArtifactStore


def test_put_is_idempotent_and_content_addressed(tmp_path):
    s = ArtifactStore(tmp_path)
    a = s.put_bytes(b"solid x", kind="stl", meta={"name": "a"})
    b = s.put_bytes(b"solid x", kind="stl", meta={"name": "a"})
    assert a == b == hashlib.sha256(b"solid x").hexdigest()
    with s.open(a) as fh:
        assert fh.read() == b"solid x"
    assert s.meta(a)["kind"] == "stl"


def test_unknown_object_raises(tmp_path):
    with pytest.raises(KeyError):
        ArtifactStore(tmp_path).open("0" * 64)


@pytest.mark.parametrize("digest", ["../outside", "A" * 64, "x" * 64, ""])
def test_invalid_ids_cannot_escape_store(tmp_path, digest):
    store = ArtifactStore(tmp_path)
    with pytest.raises(ValueError):
        store.open(digest)
    with pytest.raises(ValueError):
        store.meta(digest)


def test_metadata_cannot_override_content_properties(tmp_path):
    store = ArtifactStore(tmp_path)
    digest = store.put_bytes(b"abc", kind="stl", meta={"kind": "fake", "size": 999})
    assert store.meta(digest) == {"kind": "stl", "size": 3}
    store.put_bytes(b"abc", kind="changed", meta={"name": "changed"})
    assert store.meta(digest) == {"kind": "stl", "size": 3}


def test_concurrent_publication_retains_one_metadata_record(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    store = ArtifactStore(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        digests = list(pool.map(lambda n: store.put_bytes(b"same", kind="stl", meta={"writer": n}), range(32)))
    assert len(set(digests)) == 1
    assert store.meta(digests[0])["writer"] in range(32)
    with store.open(digests[0]) as stream:
        assert stream.read() == b"same"


@pytest.mark.parametrize("corrupt", [b"wrong", b"", b"original-extra"])
def test_retry_refuses_corrupt_existing_object_without_overwriting(tmp_path, corrupt):
    store = ArtifactStore(tmp_path)
    digest = store.put_bytes(b"original", kind="stl", meta={"name": "first"})
    path = tmp_path / "objects" / digest[:2] / digest
    path.write_bytes(corrupt)

    with pytest.raises(ValueError, match="byte integrity failed"):
        store.put_bytes(b"original", kind="stl", meta={"name": "retry"})

    assert path.read_bytes() == corrupt
    assert store.meta(digest)["name"] == "first"
    assert list(path.parent.iterdir()) == [path]


def test_directory_sync_failure_reports_failure_and_retry_recovers(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    original_sync = store._sync_directory
    digest = hashlib.sha256(b"retryable").hexdigest()
    target = tmp_path / "objects" / digest[:2] / digest

    def fail_after_publication(path):
        if path == target.parent and target.exists():
            raise OSError("directory sync failed")
        original_sync(path)

    monkeypatch.setattr(store, "_sync_directory", fail_after_publication)
    with pytest.raises(OSError, match="directory sync failed"):
        store.put_bytes(b"retryable", kind="stl", meta={})
    assert target.read_bytes() == b"retryable"
    assert list(target.parent.iterdir()) == [target]

    monkeypatch.setattr(store, "_sync_directory", original_sync)
    assert store.put_bytes(b"retryable", kind="stl", meta={}) == digest
    assert store.meta(digest) == {"kind": "stl", "size": 9}
