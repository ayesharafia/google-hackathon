import pytest

from physimesh.drone.provenance import Provenance, canonical_json, sha256_bytes, sha256_record


def test_sha256_of_empty_bytes_is_standard_value():
    assert sha256_bytes(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_record_hash_independent_of_key_order():
    assert sha256_record({"a": 1, "b": [1.5, 2]}) == sha256_record({"b": [1.5, 2], "a": 1})


def test_canonical_json_rejects_nan():
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_null_backend_digest_blocks_execution():
    p = Provenance("drone_manifest_v1", "abc", "deadbeef", "2026-10-02T00:00:00Z",
                   backend_version="v2606", backend_image_digest=None)
    assert p.blocking_for_execution() == ["backend_image_digest"]


