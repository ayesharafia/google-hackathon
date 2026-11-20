import numpy as np
import pytest

from physimesh.drone.geometry import initial_revision, repair, topology, weld


def test_orientation_creates_logged_revision_without_mutating_parent(cube_tris):
    triangles = cube_tris.copy()
    triangles[0] = triangles[0, [0, 2, 1]]
    parent = initial_revision(triangles)
    before = parent.triangles_m.copy()
    result = repair(parent, ["orient_consistently"], confirmed_by=None)
    verts, faces = weld(result.triangles_m, 1e-9)
    assert topology(verts, faces, 1e-18).closed_and_consistent
    assert result.parent_sha256 == parent.revision_sha256
    assert result.revision_sha256 != parent.revision_sha256
    assert result.operations == ("orient_consistently",)
    assert result.area_after_m2 == pytest.approx(parent.area_after_m2, abs=1e-12)
    assert np.array_equal(before, parent.triangles_m)
    assert result.max_surface_distance_m == pytest.approx(0, abs=1e-12)


def test_hole_closing_not_offered(cube_tris):
    with pytest.raises(ValueError, match="not offered"):
        repair(initial_revision(cube_tris), ["close_holes"], confirmed_by="user")


def test_repair_revision_hash_is_deterministic(cube_tris):
    parent = initial_revision(cube_tris)
    first = repair(parent, ["orient_consistently"], confirmed_by=None)
    second = repair(parent, ["orient_consistently"], confirmed_by=None)
    assert first.revision_sha256 == second.revision_sha256


def test_duplicate_removal_records_area_change(cube_tris):
    parent = initial_revision(np.concatenate([cube_tris, cube_tris[:1]]))
    result = repair(parent, ["remove_duplicate"], confirmed_by=None)
    assert len(result.triangles_m) == 12
    assert result.area_before_m2 == pytest.approx(6.5)
    assert result.area_after_m2 == pytest.approx(6)
    assert result.max_surface_distance_m == pytest.approx(0, abs=1e-12)


def test_degenerate_removal_records_distance_and_bounds(cube_tris):
    point_facet = np.full((1, 3, 3), 3.)
    parent = initial_revision(np.concatenate([cube_tris, point_facet]))
    result = repair(parent, ["remove_degenerate"], confirmed_by=None)
    assert result.bounds_before_m[1] == (3, 3, 3)
    assert result.bounds_after_m[1] == (1, 1, 1)
    assert result.max_surface_distance_m == pytest.approx(np.sqrt(12))


def test_open_shell_remains_open_after_orientation(cube_tris):
    result = repair(initial_revision(cube_tris[1:]), ["orient_consistently"], confirmed_by=None)
    verts, faces = weld(result.triangles_m, 1e-9)
    assert len(topology(verts, faces, 1e-18).boundary_edges) == 3


def test_closed_inward_shell_is_flipped_outward(cube_tris):
    result = repair(initial_revision(cube_tris[:, [0, 2, 1]]), ["orient_consistently"], confirmed_by=None)
    verts, faces = weld(result.triangles_m, 1e-9)
    assert topology(verts, faces, 1e-18).signed_volume_by_shell_m3[0] == pytest.approx(1)


def test_revision_geometry_cannot_be_made_writeable(cube_tris):
    revision = initial_revision(cube_tris)
    with pytest.raises(ValueError):
        revision.triangles_m.flags.writeable = True
    cube_tris[:] = 9
    assert np.max(revision.triangles_m) == 1


def test_repair_cannot_remove_entire_geometry():
    parent = initial_revision(np.zeros((1, 3, 3)))
    with pytest.raises(ValueError, match="nonempty"):
        repair(parent, ["remove_degenerate"], confirmed_by=None)
