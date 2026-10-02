import numpy as np
import pytest

from physimesh.drone.stl_import import StlError, parse_stl

from .conftest import ascii_stl, binary_stl

LIMITS = {"max_bytes": 10_000_000, "max_triangles": 100_000}


# ---------- parser ----------
def test_binary_roundtrip(cube_tris):
    m = parse_stl(binary_stl(cube_tris), **LIMITS)
    assert m.fmt == "binary" and m.triangles.shape == (12, 3, 3)
    assert np.allclose(m.triangles, cube_tris)


def test_binary_starting_with_solid_is_binary(cube_tris):
    m = parse_stl(binary_stl(cube_tris, header=b"solid exported-by-cad"), **LIMITS)
    assert m.fmt == "binary"


def test_ascii_roundtrip(cube_tris):
    m = parse_stl(ascii_stl(cube_tris, "body"), **LIMITS)
    assert m.fmt == "ascii" and m.solid_names == ["body"]
    assert np.allclose(m.triangles, cube_tris)


def test_truncated_binary_rejected(cube_tris):
    with pytest.raises(StlError):
        parse_stl(binary_stl(cube_tris)[:-10], **LIMITS)


def test_nan_rejected(cube_tris):
    bad = cube_tris.copy(); bad[0, 0, 0] = np.nan
    with pytest.raises(StlError, match="non-finite"):
        parse_stl(binary_stl(bad), **LIMITS)


def test_triangle_limit_enforced(cube_tris):
    with pytest.raises(StlError, match="exceeds limit"):
        parse_stl(binary_stl(cube_tris), max_bytes=10_000, max_triangles=5)


def test_byte_limit_enforced(cube_tris):
    with pytest.raises(StlError, match="limit"):
        parse_stl(binary_stl(cube_tris), max_bytes=100, max_triangles=100)


def test_hash_is_of_raw_bytes(cube_tris):
    data = binary_stl(cube_tris)
    import hashlib
    assert parse_stl(data, **LIMITS).sha256 == hashlib.sha256(data).hexdigest()




@pytest.mark.parametrize("limit", [None, 0, -1, float("inf"), True])
def test_parser_requires_explicit_positive_integer_limits(cube_tris, limit):
    with pytest.raises(StlError, match="positive integers"):
        parse_stl(binary_stl(cube_tris), max_bytes=limit, max_triangles=100)


def test_ascii_triangle_limit_enforced(cube_tris):
    with pytest.raises(StlError, match="triangles"):
        parse_stl(ascii_stl(cube_tris), max_bytes=10000, max_triangles=5)


def test_ascii_nonfinite_vertex_rejected(cube_tris):
    bad = cube_tris.copy()
    bad[0, 0, 0] = np.inf
    with pytest.raises(StlError, match="non-finite"):
        parse_stl(ascii_stl(bad), **LIMITS)


def test_file_coordinates_are_preserved_without_unit_inference(cube_tris):
    mesh = parse_stl(binary_stl(cube_tris * 1000), **LIMITS)
    assert np.max(mesh.triangles) == 1000
