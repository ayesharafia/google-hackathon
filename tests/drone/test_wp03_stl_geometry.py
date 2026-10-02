import numpy as np
import pytest

from physimesh.drone.geometry import component_id, topology, weld
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


def test_closed_cube_is_clean(cube_tris):
    v, f = weld(cube_tris, 1e-9)
    rep = topology(v, f, area_tol_m2=1e-18)
    assert rep.n_vertices == 8 and rep.n_shells == 1
    assert rep.closed_and_consistent
    assert rep.surface_area_m2 == pytest.approx(6.0)
    assert rep.signed_volume_by_shell_m3[0] == pytest.approx(1.0)   # +1 => outward normals


def test_missing_triangle_is_a_hole(cube_tris):
    v, f = weld(cube_tris[1:], 1e-9)
    rep = topology(v, f, 1e-18)
    assert len(rep.boundary_edges) == 3 and not rep.closed_and_consistent


def test_flipped_triangle_breaks_winding(cube_tris):
    t = cube_tris.copy(); t[0] = t[0][[0, 2, 1]]
    v, f = weld(t, 1e-9)
    rep = topology(v, f, 1e-18)
    assert len(rep.inconsistent_winding_edges) == 3


def test_two_disjoint_cubes_are_two_shells(cube_tris):
    both = np.concatenate([cube_tris, cube_tris + [3.0, 0, 0]])
    v, f = weld(both, 1e-9)
    assert topology(v, f, 1e-18).n_shells == 2


def test_degenerate_and_duplicate_detected(cube_tris):
    sliver = np.array([[[0, 0, 0], [0.5, 0, 0], [1, 0, 0]]], float)
    t = np.concatenate([cube_tris, cube_tris[:1], sliver])
    v, f = weld(t, 1e-9)
    rep = topology(v, f, 1e-18)
    assert 12 in rep.duplicate_faces and 13 in rep.degenerate_faces


def test_weld_tolerance_must_be_positive(cube_tris):
    with pytest.raises(ValueError):
        weld(cube_tris, 0.0)


# ---------- component id ----------
def test_component_id_independent_of_triangle_and_vertex_order(cube_tris):
    rng = np.random.default_rng(0)
    shuffled = cube_tris[rng.permutation(12)]
    rotated = np.array([t[[1, 2, 0]] for t in shuffled])     # cyclic: winding kept
    assert component_id(cube_tris, 1e-6) == component_id(rotated, 1e-6)


def test_component_id_changes_when_winding_flips(cube_tris):
    flipped = np.array([t[[0, 2, 1]] for t in cube_tris])
    assert component_id(cube_tris, 1e-6) != component_id(flipped, 1e-6)


def test_thin_shell_below_declared_feature_resolution(cube_tris):
    thin = cube_tris * [1, 1, 0.001]
    verts, faces = weld(thin, 1e-9)
    report = topology(verts, faces, 1e-18, min_feature_m=0.01)
    assert report.closed_and_consistent
    assert report.warnings == ["thin_feature_below_resolution: shell 0"]


def test_resolved_tolerance_retains_declared_inputs(cube_tris):
    from physimesh.drone.geometry import resolve_topology_tolerance
    record = resolve_topology_tolerance(cube_tris, abs_tol_m=1e-6, rel_tol=1e-5)
    assert record.abs_tol_m == 1e-6 and record.rel_tol == 1e-5
    assert record.bbox_diagonal_m == pytest.approx(np.sqrt(3))
    assert record.resolved_m == pytest.approx(1e-5 * np.sqrt(3))


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_component_grid_must_be_finite_positive(cube_tris, value):
    with pytest.raises(ValueError):
        component_id(cube_tris, value)


def test_topology_rejects_negative_face_indices(cube_tris):
    verts, faces = weld(cube_tris, 1e-9)
    faces[0, 0] = -1
    with pytest.raises(ValueError, match="index"):
        topology(verts, faces, 1e-18)


def test_topology_diagnostics_do_not_mutate_geometry(cube_tris):
    before = cube_tris.copy()
    verts, faces = weld(cube_tris, 1e-9)
    before_verts, before_faces = verts.copy(), faces.copy()
    topology(verts, faces, 1e-18, min_feature_m=0.01)
    assert np.array_equal(cube_tris, before)
    assert np.array_equal(verts, before_verts)
    assert np.array_equal(faces, before_faces)


def test_component_id_cyclic_invariance_when_vertices_quantize_together():
    triangle = np.array([[[0, 0, 0], [.1, .1, 0], [1, 0, 0]]])
    assert component_id(triangle, 1.) == component_id(triangle[:, [1, 2, 0]], 1.)
