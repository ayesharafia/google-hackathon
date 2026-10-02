"""Mandatory force fixtures [M§16] and CT02/CT04 [M§33]."""
import numpy as np
import pytest

from physimesh.postpro.loads3d import (
    DIM_KINEMATIC_PRESSURE,
    DIM_PRESSURE_PA,
    ForceLedger,
    LedgerEntry,
    SemanticsError,
    integrate_surface_loads,
    reconcile,
    rotor_loads,
    solid_area_vectors_from_backend,
    source_reaction,
    to_physical_pressure,
    transfer_moment,
)
from tests.drone.conftest import CUBE_F, CUBE_V


def cube_faces():
    tri = CUBE_V[CUBE_F]
    centres = tri.mean(axis=1)
    s = 0.5 * np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])  # outward = solid -> fluid
    return centres, s


ZERO_TAU = np.zeros((12, 3))


def test_uniform_pressure_on_closed_cube_gives_zero_force_and_moment():   # CT02
    x, s = cube_faces()
    r = integrate_surface_loads(x, s, np.full(12, 5000.0), ZERO_TAU, [0.5, 0.5, 0.5], 0.0)
    assert np.allclose(r.force_total_n, 0, atol=1e-9)
    assert np.allclose(r.moment_total_nm, 0, atol=1e-9)


def test_reference_pressure_cancels_on_closed_surface_only():
    x, s = cube_faces()
    p = np.linspace(0, 100, 12)
    a = integrate_surface_loads(x, s, p, ZERO_TAU, [0, 0, 0], 0.0).force_total_n
    b = integrate_surface_loads(x, s, p, ZERO_TAU, [0, 0, 0], 1e5).force_total_n
    assert np.allclose(a, b, atol=1e-6)
    top = slice(2, 4)                                   # open patch: p_ref matters
    a = integrate_surface_loads(x[top], s[top], p[top], ZERO_TAU[top], [0, 0, 0], 0.0)
    b = integrate_surface_loads(x[top], s[top], p[top], ZERO_TAU[top], [0, 0, 0], 1e5)
    assert not np.allclose(a.force_total_n, b.force_total_n)


def test_pressure_on_one_planar_patch():
    x, s = cube_faces()
    top = slice(2, 4)                                   # z = 1 face, area 1, n_s = +z
    r = integrate_surface_loads(x[top], s[top], np.full(2, 200.0), ZERO_TAU[top], [0, 0, 0], 0.0)
    assert np.allclose(r.force_total_n, [0, 0, -200.0])   # pressure pushes into the solid


def test_linear_pressure_field_gives_buoyancy_like_force():
    x, s = cube_faces()
    k = 1234.0
    p = 1e5 - k * x[:, 2]                               # p = p0 - k z ; centroid rule exact
    r = integrate_surface_loads(x, s, p, ZERO_TAU, [0, 0, 0], 0.0)
    assert np.allclose(r.force_total_n, [0, 0, k * 1.0], atol=1e-6)   # F = k V


def test_known_tangential_traction_gives_shear_force():
    x, s = cube_faces()
    top = slice(2, 4)
    tau = np.tile([7.0, 0, 0], (2, 1))
    r = integrate_surface_loads(x[top], s[top], np.zeros(2), tau, [0, 0, 0], 0.0)
    assert np.allclose(r.force_viscous_n, [7.0, 0, 0])
    assert np.allclose(r.force_pressure_n, 0)


def test_offset_load_gives_correct_moment():
    x = np.array([[2.0, 0, 0]]); s = np.array([[0, 0, 1.0]])
    r = integrate_surface_loads(x, s, np.zeros(1), np.array([[0, 0, 10.0]]), [0, 0, 0], 0.0)
    assert np.allclose(r.moment_total_nm, [0, -20.0, 0])


def test_moment_transfer_matches_direct_integration():
    x, s = cube_faces()
    p = 1e5 - 50 * x[:, 0] + 3 * x[:, 1]
    a = integrate_surface_loads(x, s, p, ZERO_TAU, [0, 0, 0], 0.0)
    b = integrate_surface_loads(x, s, p, ZERO_TAU, [1, 2, 3], 0.0)
    assert np.allclose(transfer_moment(a.moment_total_nm, [0, 0, 0], [1, 2, 3], a.force_total_n),
                       b.moment_total_nm)


def test_backend_normals_are_flipped_once():
    _, s = cube_faces()
    assert np.allclose(solid_area_vectors_from_backend(-s), s)


def test_rotating_blade_torque_and_power_sign():
    # Blade face at r = (1,0,0), Omega = +100 rad/s about +z; air resists with -y traction.
    x = np.array([[1.0, 0, 0]]); s = np.array([[0, 0, 0.01]])
    tau = np.array([[0, -50.0, 0]])
    r = integrate_surface_loads(x, s, np.zeros(1), tau, [0, 0, 0], 0.0)
    rl = rotor_loads(r.force_total_n, r.moment_total_nm, [0, 0, 1], np.array([0, 0, 100.0]))
    assert rl.q_aero_nm == pytest.approx(-0.5)        # resisting
    assert rl.p_shaft_w == pytest.approx(50.0)        # positive shaft input


def test_actuator_reaction_is_opposite_to_source_on_fluid():
    f = np.tile([0, 0, -1000.0], (4, 1))              # source pushes air down
    F, M = source_reaction(f, np.full(4, 0.25), np.zeros((4, 3)), [0, 0, 0])
    assert np.allclose(F, [0, 0, 1000.0]) and np.allclose(M, 0)


def test_kinematic_pressure_converted_once():               # CT04
    rho = 1.2250123
    pk = np.array([10.0, -4.0])
    p_from_k = to_physical_pressure(pk, DIM_KINEMATIC_PRESSURE, field_name="p", rho=rho)
    p_from_pa = to_physical_pressure(pk * rho, DIM_PRESSURE_PA, field_name="p", rho=rho)
    assert np.allclose(p_from_k, p_from_pa)
    assert np.allclose(to_physical_pressure(p_from_pa, DIM_PRESSURE_PA, field_name="p", rho=rho),
                       p_from_pa)                       # Pa never multiplied again


def test_p_rgh_and_bad_dimensions_refused():
    with pytest.raises(SemanticsError):
        to_physical_pressure(np.ones(1), DIM_PRESSURE_PA, field_name="p_rgh", rho=1.2)
    with pytest.raises(SemanticsError):
        to_physical_pressure(np.ones(1), (0, 1, -1, 0, 0, 0, 0), field_name="p", rho=1.2)
    with pytest.raises(SemanticsError):
        to_physical_pressure(np.ones(1), DIM_KINEMATIC_PRESSURE, field_name="p", rho=None)


def test_reconciliation_tolerance():
    ok = reconcile([100.05, 0, 0], [100.0, 0, 0], rel_tol=1e-3, abs_tol=1e-6)
    bad = reconcile([100.2, 0, 0], [100.0, 0, 0], rel_tol=1e-3, abs_tol=1e-6)
    assert ok.status == "accepted" and bad.status == "diagnostic_only"


def test_ledger_refuses_double_counting():
    led = ForceLedger()
    z = np.zeros(3)
    led.add(LedgerEntry("rotor_source_reaction", "R1", ("rotorZone1",), z, z))
    with pytest.raises(ValueError, match="double count"):
        led.add(LedgerEntry("rotor_wall", "R1", ("blade1",), z, z))
    led.add(LedgerEntry("body", "fuselage", ("fuselage",), np.array([0, 0, -5.0]), z))
    with pytest.raises(ValueError, match="already counted"):
        led.add(LedgerEntry("body", "fuselage2", ("fuselage",), z, z))


def test_ledger_aero_total_excludes_gravity():
    led = ForceLedger()
    z = np.zeros(3)
    led.add(LedgerEntry("rotor_wall", "R1", ("b1",), np.array([0, 0, 100.0]), z))
    led.add(LedgerEntry("body", "fus", ("f",), np.array([0, 0, -10.0]), z))
    led.add(LedgerEntry("gravity", "gravity", (), np.array([0, 0, -80.0]), z))
    f, _ = led.aerodynamic_total()
    assert np.allclose(f, [0, 0, 90.0])
