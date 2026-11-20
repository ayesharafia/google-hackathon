"""D2.1 reader checks against captured native v2606 files, never invented outputs."""
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from physimesh.solver.foam_ascii import (
    FoamAsciiError,
    face_centres_and_areas,
    read_boundary,
    read_faces,
    read_function_object_table,
    read_patch_field,
    read_points,
    read_raw_samples,
)

FIXTURE = Path(__file__).parent / "fixtures/sphere_coarse"


def test_captured_fixture_bytes_match_retained_manifest():
    manifest = json.loads((FIXTURE / "CAPTURE.json").read_text())
    for name, record in manifest["files"].items():
        raw = gzip.decompress((FIXTURE / (name + ".gz")).read_bytes())
        assert hashlib.sha256(raw).hexdigest() == record["original_sha256"]


def test_corrupt_captured_numeric_list_is_refused(tmp_path):
    text = gzip.decompress((FIXTURE / "constant/polyMesh/points.gz").read_bytes()).decode()
    end = text.rindex("\n)")
    path = tmp_path / "points"
    path.write_text(text[:end] + "\ninvalid-token\n" + text[end:])
    with pytest.raises(FoamAsciiError, match="invalid token"):
        read_points(path)


def test_sphere_native_area_vectors_closed_and_positive_solid_volume():
    points = read_points(FIXTURE / "constant/polyMesh/points.gz")
    faces = read_faces(FIXTURE / "constant/polyMesh/faces.gz")
    patch = read_boundary(FIXTURE / "constant/polyMesh/boundary.gz")["sphere"]
    selected = faces[patch["startFace"]:patch["startFace"] + patch["nFaces"]]
    centres, fluid_sf = face_centres_and_areas(points, selected)
    solid_sf = -fluid_sf
    assert np.allclose(solid_sf.sum(axis=0), 0, atol=1e-10)
    assert np.linalg.norm(solid_sf, axis=1).sum() == pytest.approx(math.pi, rel=0.005)
    assert np.einsum("ij,ij->", centres, solid_sf) / 3 > 0


def test_captured_patch_scalar_vector_lengths_and_dimensions():
    patch = read_boundary(FIXTURE / "constant/polyMesh/boundary.gz")["sphere"]
    pressure, dimensions = read_patch_field(FIXTURE / "812/p.gz", "sphere")
    shear, stress_dimensions = read_patch_field(FIXTURE / "812/wallShearStress.gz", "sphere")
    assert pressure.shape == (patch["nFaces"],)
    assert shear.shape == (patch["nFaces"], 3)
    assert dimensions == stress_dimensions == (0, 2, -2, 0, 0, 0, 0)
    # The native outlet p entry is uniform; expand it using retained nFaces.
    boundary = read_boundary(FIXTURE / "constant/polyMesh/boundary.gz")
    outlet, _ = read_patch_field(FIXTURE / "812/p.gz", "outlet")
    assert outlet.shape == (boundary["outlet"]["nFaces"],)
    assert np.all(outlet == 0)


def test_planar_quad_and_triangle_centroids_and_area():
    points = np.array([[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0]], float)
    centres, areas = face_centres_and_areas(points, [np.array([0, 1, 2, 3]), np.array([0, 1, 2])])
    assert np.allclose(centres, [[1, 1, 0], [4 / 3, 2 / 3, 0]])
    assert np.allclose(areas, [[0, 0, 4], [0, 0, 2]])


def test_native_force_headers_and_rows():
    headers, rows = read_function_object_table(FIXTURE / "postProcessing/forces/0/force.dat.gz")
    assert headers == ["Time", "total_x", "total_y", "total_z", "pressure_x", "pressure_y",
                       "pressure_z", "viscous_x", "viscous_y", "viscous_z"]
    assert rows.shape[1] == len(headers)
    assert np.allclose(rows[:, 1:4], rows[:, 4:7] + rows[:, 7:10], atol=1e-6)
    solver_headers, solver_rows = read_function_object_table(
        FIXTURE / "postProcessing/solverInfo1/0/solverInfo.dat.gz")
    assert "Ux_initial" in solver_headers and solver_rows.shape[1] == len(solver_headers)


def test_raw_samples_retain_native_column_names():
    headers, rows = read_raw_samples(FIXTURE / "postProcessing/cuttingPlane/812/U_yNormal.raw.gz")
    assert headers == ["x", "y", "z", "U_x", "U_y", "U_z"]
    assert rows.shape[1] == 6
    headers, rows = read_raw_samples(FIXTURE / "postProcessing/sample1/812/centreLine_p_U.xy.gz")
    assert headers == []  # Native .xy has no header. A caller must supply recorded sampling metadata.
    assert rows.shape[1] == 5
