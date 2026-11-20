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
