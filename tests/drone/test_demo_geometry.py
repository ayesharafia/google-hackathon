import hashlib
import math

import numpy as np
import pytest

from physimesh.drone.demo_geometry import binary_stl_bytes, icosphere_triangles
from physimesh.drone.geometry import topology, weld
from physimesh.drone.stl_import import parse_stl


def test_five_subdivision_sphere_is_closed_and_matches_area():
    triangles = icosphere_triangles(1.0, 5)
    assert triangles.shape == (20_480, 3, 3)
    vertices, faces = weld(triangles, 1e-9)
    report = topology(vertices, faces, 1e-18)
    assert report.closed_and_consistent
    assert report.n_shells == 1
    assert report.signed_volume_by_shell_m3[0] > 0
    assert abs(report.surface_area_m2 / math.pi - 1) < 0.00031


def test_binary_stl_roundtrip_and_determinism():
    triangles = icosphere_triangles(1.0, 2)
    data = binary_stl_bytes(triangles)
    assert data == binary_stl_bytes(icosphere_triangles(1.0, 2))
    parsed = parse_stl(data, max_bytes=2_000_000, max_triangles=10_000)
    assert np.allclose(parsed.triangles, triangles, atol=1e-6)
    assert parsed.sha256 == hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize("diameter,subdivisions", [(0, 1), (float("nan"), 1), (1, -1), (1, 7)])
def test_invalid_demo_geometry_is_refused(diameter, subdivisions):
    with pytest.raises(ValueError):
        icosphere_triangles(diameter, subdivisions)
