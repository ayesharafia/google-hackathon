import math

import numpy as np
import pytest

from physimesh.drone.allocation import AllocRotor, allocate_hover
from physimesh.drone.mission import electrical_power, size_battery

G0 = 9.80665
RHO = 101325.0 / (287.05 * 288.15)


def x_quad(k_t=0.05, k_q=0.002, omega_max=400.0, failed=()):
    L = 2.0
    pos = [(L, -L, 0), (L, L, 0), (-L, L, 0), (-L, -L, 0)]
    spin = [+1, -1, +1, -1]
    return [AllocRotor(f"R{i}", p, (0, 0, 1), s, k_t, k_q, omega_max, i in failed)
            for i, (p, s) in enumerate(zip(pos, spin))]


def test_quad_hover_trim_fixture():
    r = allocate_hover(x_quad(), 1500.0, (0, 0, 0), 2.0, tol_force=1e-9, tol_moment=1e-9)
    assert r.feasible and r.status == "trimmed"
    assert np.allclose(r.omega_rad_s, 271.20080, rtol=1e-7)
    assert abs(r.wrench_achieved[5]) < 1e-6                  # yaw balanced


def test_body_download_raises_required_thrust():
    r0 = allocate_hover(x_quad(), 1500.0, (0, 0, 0), 2.0, tol_force=1e-9, tol_moment=1e-9)
    r1 = allocate_hover(x_quad(), 1500.0, (0, 0, 0), 2.0, body_force_n=(0, 0, -500.0),
                        tol_force=1e-9, tol_moment=1e-9)
    assert r1.wrench_required[2] == pytest.approx(r0.wrench_required[2] + 500.0)
    assert np.all(r1.omega_rad_s > r0.omega_rad_s)


def test_sustained_speed_limit_makes_hover_unreachable():
    r = allocate_hover(x_quad(omega_max=250.0), 1500.0, (0, 0, 0), 2.0,
                       tol_force=1e-3, tol_moment=1e-3)
    assert not r.feasible and r.status == "unreachable"
    assert all("sustained max" in a for a in r.active_constraints)


def test_motor_loss_quad_cannot_trim_all_axes():
    r = allocate_hover(x_quad(failed=(0,)), 1500.0, (0, 0, 0), 2.0, tol_force=1e-3, tol_moment=1e-3)
    assert not r.feasible and "R0: failed (mask)" in r.active_constraints


def test_electrical_power_eq46():
    p = electrical_power([1000.0, 1000.0], [0.9, 0.9], [0.95, 0.95], [1.0, 1.0], 100.0)
    assert p == pytest.approx(2000 / (0.9 * 0.95) + 100.0)


def _hover_pelec(m, a_tot=8 * math.pi * 1.5 ** 2, fm=0.7, eta=0.85, p_aux=2000.0):
    t = m * G0
    return t ** 1.5 / math.sqrt(2 * RHO * a_tot) / fm / eta + p_aux


@pytest.mark.parametrize("e_pack,minutes,status,mass", [
    (250.0, 10.0, "converged", 1442.1503),
    (200.0, 20.0, "converged", 3066.9058),
    (200.0, 60.0, "diverged", None),
])
def test_coupled_mass_energy_toy_cases(e_pack, minutes, status, mass):
    r = size_battery(1200.0, _hover_pelec, duration_s=minutes * 60, e_pack_wh_per_kg=e_pack,
                     f_usable=0.8, reserve_fraction=0.2, rel_tol=1e-6, max_iterations=500,
                     divergence_mass_kg=1e6)
    assert r.status == status
    if mass is not None:
        assert r.total_mass_kg == pytest.approx(mass, rel=1e-6)


def test_null_energy_density_blocks():
    with pytest.raises(ValueError):
        size_battery(1200.0, _hover_pelec, duration_s=600, e_pack_wh_per_kg=None, f_usable=0.8,
                     reserve_fraction=0.2, rel_tol=1e-6, max_iterations=10, divergence_mass_kg=1e6)
