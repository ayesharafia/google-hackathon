import math

import numpy as np
import pytest

from physimesh.drone.bem import Blade, BemSettings, TabulatedPolar, prandtl_tip_factor, solve_rotor
from physimesh.drone.propulsion import (RotorMap, Unavailable, figure_of_merit, ideal_hover,
                                        propeller_coefficients)

RHO = 101325.0 / (287.05 * 288.15)
MU = 1.7892976e-5
A_SND = 340.29229

# Thin-airfoil test polar: Cl = 2 pi alpha, Cd = 0.01, valid -8..+8 deg [STD textbook model,
# used ONLY as a test fixture; real designs need measured/computed polars].
_A = np.linspace(-8, 8, 33)
TEST_POLAR = TabulatedPolar(_A, 2 * math.pi * np.radians(_A), np.full_like(_A, 0.01), "thin-airfoil test")
TEST_BLADE = Blade(2, 1.0, 0.15, np.array([0.15, 1.0]), np.array([0.12, 0.08]), np.array([16.0, 6.0]))
SET = BemSettings(80, 1e-4, 200, relaxation=0.5, tip_loss="prandtl")


# ---------- momentum & coefficients ----------
def test_ideal_hover_fixture():
    h = ideal_hover(1000.0, 1.0, RHO)
    assert h.induced_velocity_m_s == pytest.approx(11.398294, rel=1e-7)
    assert h.ideal_power_w == pytest.approx(11398.294, rel=1e-7)
    assert h.disk_loading_n_m2 == pytest.approx(318.30989, rel=1e-7)


def test_figure_of_merit_fixture_and_impossible_value_flagged():
    p = ideal_hover(1000.0, 1.0, RHO).ideal_power_w
    omega = 500 * 2 * math.pi / 60
    assert figure_of_merit(p, 300.0, omega).value == pytest.approx(0.72563792, rel=1e-7)
    assert "physically_inconsistent_fm_gt_1" in figure_of_merit(p, 100.0, omega).flags


def test_coefficients_fixture_and_cp_equals_2pi_cq():
    c = propeller_coefficients(1000.0, 100.0, 500.0, 2.0, RHO)
    assert c.ct == pytest.approx(0.73468652, rel=1e-7)
    assert c.cq == pytest.approx(0.036734326, rel=1e-7)
    assert c.cp == pytest.approx(2 * math.pi * c.cq, rel=1e-12)


def test_zero_rpm_coefficients_unavailable():
    assert isinstance(propeller_coefficients(10.0, 1.0, 0.0, 1.0, RHO), Unavailable)


def test_rotor_map_refuses_extrapolation():
    m = RotorMap(np.array([1000.0, 2000.0]), np.array([0.0, 10.0]),
                 np.array([[100.0, 80.0], [400.0, 350.0]]), np.array([[10.0, 9.0], [40.0, 38.0]]),
                 1.225, "motor_shaft_positive", "shaft")
    assert m.lookup(1500.0, 0.0) == pytest.approx((250.0, 25.0))
    assert isinstance(m.lookup(2500.0, 0.0), Unavailable)


# ---------- BEM ----------
def test_prandtl_tip_fixture():
    assert prandtl_tip_factor(2, 1.0, 0.9, math.radians(10)) == pytest.approx(0.64636050, rel=1e-7)


def test_bem_hover_all_stations_converge_and_satisfy_momentum_balance():
    r = solve_rotor(TEST_BLADE, 1500.0, 0.0, RHO, MU, A_SND, TEST_POLAR, SET)
    assert r.accepted, [s.reason for s in r.stations if not s.converged]
    for s in r.stations:                               # E13 vs E14 self-consistency
        mom = 4 * math.pi * RHO * s.r_m * s.loss_factor * s.vi_m_s * s.vi_m_s
        assert abs(s.dT_dr - mom) <= 1e-4 * abs(s.dT_dr)
    assert r.thrust_n > 0 and r.shaft_power_w > 0


def test_bem_power_not_below_ideal_momentum_bound():
    r = solve_rotor(TEST_BLADE, 1500.0, 0.0, RHO, MU, A_SND, TEST_POLAR, SET)
    p_ideal = ideal_hover(r.thrust_n, TEST_BLADE.radius_m, RHO).ideal_power_w
    assert r.shaft_power_w >= p_ideal


def test_bem_station_refinement_sensitivity_is_reported():
    coarse = solve_rotor(TEST_BLADE, 1500.0, 0.0, RHO, MU, A_SND, TEST_POLAR, SET)
    fine = solve_rotor(TEST_BLADE, 1500.0, 0.0, RHO, MU, A_SND, TEST_POLAR,
                       BemSettings(160, 1e-4, 200, 0.5, "prandtl"))
    change = abs(fine.thrust_n - coarse.thrust_n) / fine.thrust_n
    assert change < 0.02          # provisional 2 % gate [M§15]; record the value, not just pass


def test_bem_rejects_when_alpha_leaves_polar():
    steep = Blade(2, 1.0, 0.15, np.array([0.15, 1.0]), np.array([0.12, 0.08]), np.array([40.0, 30.0]))
    r = solve_rotor(steep, 1500.0, 0.0, RHO, MU, A_SND, TEST_POLAR, SET)
    assert not r.accepted and math.isnan(r.thrust_n)
    assert any(s.reason == "alpha_outside_polar" for s in r.stations)


def test_bem_zero_rpm_unavailable():
    assert solve_rotor(TEST_BLADE, 0.0, 0.0, RHO, MU, A_SND, TEST_POLAR, SET).status == "unavailable_zero_rpm"


def test_bem_relaxation_has_no_silent_default():
    with pytest.raises(ValueError):
        solve_rotor(TEST_BLADE, 1500.0, 0.0, RHO, MU, A_SND, TEST_POLAR, BemSettings(80, 1e-4, 200, 0.0, "none"))
