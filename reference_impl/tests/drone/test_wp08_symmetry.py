import numpy as np
import pytest

from physimesh.drone.frames import RotorFrame
from physimesh.drone.geometry import topology, weld
from physimesh.drone.symmetry import (GeometryMatch, OperatingState, closest_point_on_triangle,
                                      geometric_match, physical_eligibility,
                                      reconstruct_full_loads, reflect_rotor, reflect_triangles,
                                      reflection_matrix)

from .conftest import CUBE_F, CUBE_V

PLANE_X0, PLANE_N = (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)          # y = 0 (body x-z plane)
GOOD = GeometryMatch(0.0, 0.0, 1e-6, True, 0.0)
KW = dict(pos_tol_m=1e-6, rpm_tol=1e-6, vel_tol_m_s=1e-9)


def hover():
    return OperatingState(freestream_world_m_s=(0, 0, 0), cg_world_m=(0, 0, 0))


def test_reflection_matrix_properties():
    h = reflection_matrix([0, 2.0, 0])
    assert np.allclose(h @ h, np.eye(3)) and np.linalg.det(h) == pytest.approx(-1.0)


def test_reflected_triangles_keep_outward_normals():
    cube = CUBE_V[CUBE_F] + [0, 1.0, 0]
    v, f = weld(reflect_triangles(PLANE_X0, PLANE_N, cube), 1e-9)
    rep = topology(v, f, 1e-18)
    assert rep.closed_and_consistent and rep.signed_volume_by_shell_m3[0] == pytest.approx(1.0)


def test_reflected_rotor_flips_handedness():
    r = RotorFrame("R1", (1.0, 2.0, 0.5), (0, 0, 1), 1000.0)
    img = reflect_rotor(PLANE_X0, PLANE_N, r, "R1'")
    assert np.allclose(img.center_m, (1.0, -2.0, 0.5))
    assert np.allclose(img.axis, (0, 0, 1)) and img.signed_rpm == pytest.approx(-1000.0)


def test_closest_point_matches_brute_force():
    rng = np.random.default_rng(1)
    a, b, c = rng.normal(size=(3, 3))
    u, v = np.meshgrid(np.linspace(0, 1, 401), np.linspace(0, 1, 401))
    m = (u + v) <= 1
    grid = a + u[m][:, None] * (b - a) + v[m][:, None] * (c - a)
    for p in rng.normal(scale=2.0, size=(20, 3)):
        q = closest_point_on_triangle(p, a, b, c)
        assert np.linalg.norm(p - q) <= np.min(np.linalg.norm(grid - p, axis=1)) + 1e-12


def test_symmetric_pair_matches_and_offset_pair_does_not():
    left = CUBE_V[CUBE_F] + [0, 1.0, 0]
    right = reflect_triangles(PLANE_X0, PLANE_N, left)
    ok = geometric_match(left, right, PLANE_X0, PLANE_N, abs_tol_m=1e-9, rel_tol=0.0)
    assert ok.within_tolerance and ok.max_distance_m < 1e-9
    bad = geometric_match(left, right + [0.01, 0, 0], PLANE_X0, PLANE_N, abs_tol_m=1e-3, rel_tol=0.0)
    assert not bad.within_tolerance and bad.max_distance_m == pytest.approx(0.01, rel=1e-6)


def test_counter_rotating_pair_is_eligible():
    rotors = [RotorFrame("L", (0, 1, 0), (0, 0, 1), 1000.0),
              RotorFrame("R", (0, -1, 0), (0, 0, 1), -1000.0)]
    e = physical_eligibility(PLANE_X0, PLANE_N, rotors, hover(), GOOD, **KW)
    assert e.eligible, e.reasons


def test_reject_single_swirling_rotor_on_plane():
    rotors = [RotorFrame("C", (0, 0, 0), (0, 0, 1), 1000.0)]
    e = physical_eligibility(PLANE_X0, PLANE_N, rotors, hover(), GOOD, **KW)
    assert not e.eligible and "handedness" in e.reasons[0]


def test_reject_co_rotating_pair():
    rotors = [RotorFrame("L", (0, 1, 0), (0, 0, 1), 1000.0),
              RotorFrame("R", (0, -1, 0), (0, 0, 1), 1000.0)]
    assert not physical_eligibility(PLANE_X0, PLANE_N, rotors, hover(), GOOD, **KW).eligible


def test_reject_asymmetric_rpm():
    rotors = [RotorFrame("L", (0, 1, 0), (0, 0, 1), 1000.0),
              RotorFrame("R", (0, -1, 0), (0, 0, 1), -990.0)]
    assert not physical_eligibility(PLANE_X0, PLANE_N, rotors, hover(), GOOD, **KW).eligible


@pytest.mark.parametrize("change", [
    dict(freestream_world_m_s=(0, 3.0, 0)),        # crosswind across plane
    dict(yaw_deg=5.0),
    dict(cg_world_m=(0, 0.2, 0)),                  # displaced payload
    dict(motor_loss=True),
    dict(asymmetric_transient_disturbance=True),
    dict(transient=True),                          # phases not shown consistent
])
def test_reject_listed_operating_states(change):
    rotors = [RotorFrame("L", (0, 1, 0), (0, 0, 1), 1000.0),
              RotorFrame("R", (0, -1, 0), (0, 0, 1), -1000.0)]
    st = hover()
    for k, v in change.items():
        setattr(st, k, v)
    assert not physical_eligibility(PLANE_X0, PLANE_N, rotors, st, GOOD, **KW).eligible


def test_ct06_reconstruct_offset_force_and_moment():
    f_half = np.array([3.0, 4.0, 100.0]); m_half = np.array([10.0, 20.0, 30.0])
    f, m = reconstruct_full_loads(f_half, m_half, PLANE_X0, PLANE_N, (0, 0, 0), pos_tol_m=1e-9)
    assert np.allclose(f, [6.0, 0.0, 200.0])           # side force cancels
    assert np.allclose(m, [0.0, 40.0, 0.0])            # roll and yaw cancel, pitch doubles


def test_moment_origin_off_plane_refused():
    with pytest.raises(ValueError):
        reconstruct_full_loads(np.zeros(3), np.zeros(3), PLANE_X0, PLANE_N, (0, 0.1, 0),
                               pos_tol_m=1e-9)
