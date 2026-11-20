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
