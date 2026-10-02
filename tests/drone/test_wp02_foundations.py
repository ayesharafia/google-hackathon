import numpy as np
import pytest

from physimesh.drone.provenance import Provenance, canonical_json, sha256_bytes, sha256_record
from physimesh.drone.units import (
    DIM_KINEMATIC_PRESSURE,
    DIM_PRESSURE_PA,
    UnitsError,
    length_factor,
    parse_foam_dimensions,
    to_si_length,
)


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


def test_null_source_unit_is_rejected_never_inferred():
    with pytest.raises(UnitsError, match="source_units is null"):
        length_factor(None)


def test_mm_conversion_is_recorded():
    v, rec = to_si_length(np.array([1000.0, 25.4]), "mm")
    assert np.allclose(v, [1.0, 0.0254])
    assert (rec.from_unit, rec.to_unit, rec.factor) == ("mm", "m", 1e-3)


def test_inch_is_exact():
    assert length_factor("in") == 0.0254


def test_parse_foam_dimensions_pressure_and_kinematic():
    assert parse_foam_dimensions("dimensions      [1 -1 -2 0 0 0 0];") == DIM_PRESSURE_PA
    assert parse_foam_dimensions("dimensions [0 2 -2 0 0];") == DIM_KINEMATIC_PRESSURE




@pytest.mark.parametrize("value", [None, float("nan"), float("inf")])
def test_unknown_or_nonfinite_length_cannot_reach_si(value):
    with pytest.raises(UnitsError):
        to_si_length(value, "m")


@pytest.mark.parametrize("text", ["dimensions [1 -1 -2 0 0 0];", "dimensions [nan 0 0 0 0];",
                                 "dimensions [1.5 0 0 0 0];", "dimensions [bad 0 0 0 0];"])
def test_invalid_dimensions_are_rejected(text):
    with pytest.raises(UnitsError):
        parse_foam_dimensions(text)
