import math
import random
from decimal import Decimal, localcontext

import pytest

from physimesh.drone.hover_bemt import solve_hover

OUTPUTS = (
    "thrust_coefficient", "blade_thrust_coefficient",
    "induced_power_coefficient", "profile_power_coefficient",
    "shaft_power_coefficient", "thrust_n", "shaft_power_w", "shaft_torque_nm",
)


def inputs(**changes):
    values = {"radius_m": 0.7, "angular_speed_rad_s": 300.0,
                  "density_kg_m3": 1.2, "blade_count": 3, "chord_m": 0.04,
                  "lift_curve_slope_per_rad": 5.7, "profile_drag_coefficient": 0.012,
                  "pitch_tip_rad": 0.12, "root_cutout_fraction": 0.2, "annuli": 16}
    values.update(changes)
    return values


def reference(p):
    with localcontext() as ctx:
        ctx.prec = 80
        def d(x):
            return Decimal.from_float(x) if type(x) is float else Decimal(x)
        radius, omega, rho = map(d, (p["radius_m"], p["angular_speed_rad_s"],
                                     p["density_kg_m3"]))
        pi = Decimal("3.141592653589793238462643383279502884197169399375105820974944592307816406286208999")
        sigma = d(p["blade_count"]) * d(p["chord_m"]) / (pi * radius)
        a, cd = d(p["lift_curve_slope_per_rad"]), d(p["profile_drag_coefficient"])
        r0, root, tip = map(d, (p["root_cutout_fraction"],
                               p["pitch_root_rad"], p["pitch_tip_rad"]))
        dr = (1 - r0) / d(p["annuli"])
        A = sigma * a / 8
        ct = blade_ct = cpi = cp0 = Decimal(0)
        radial, pitch, inflow = [], [], []
        for i in range(p["annuli"]):
            r = r0 + (d(i) + Decimal("0.5")) * dr
            t = (r - r0) / (1 - r0)
            theta = (1 - t) * root + t * tip
            lam = (-A + (A * A + 4 * A * theta * r).sqrt()) / 2
            ct += 4 * lam * lam * r * dr
            blade_ct += sigma * a / 2 * (theta * r * r - lam * r) * dr
            cpi += 4 * lam**3 * r * dr
            cp0 += sigma * cd / 2 * r**3 * dr
            radial.append(float(r))
            pitch.append(float(theta))
            inflow.append(float(lam))
        cp = cpi + cp0
        thrust = rho * pi * radius**2 * (omega * radius)**2 * ct
        power = rho * pi * radius**2 * (omega * radius)**3 * cp
        outputs = tuple(map(float, (ct, blade_ct, cpi, cp0, cp,
                                    thrust, power, power / omega)))
        return outputs, radial, pitch, inflow


def check_reference(p):
    result = solve_hover(**p)
    outputs, radial, pitch, inflow = reference(p)
    for name, expected in zip(OUTPUTS, outputs):
        assert getattr(result, name) == pytest.approx(expected, rel=2e-11, abs=0)
    assert result.radial_fraction == pytest.approx(radial, rel=2e-14, abs=0)
    assert result.pitch_rad == pytest.approx(pitch, rel=2e-14, abs=0)
    assert result.inflow_ratio == pytest.approx(inflow, rel=2e-11, abs=0)
    return result


def test_equal_linear_endpoints_match_constant_floats():
    p = inputs()
    constant = solve_hover(**p)
    linear = solve_hover(**p, twist_law="linear", pitch_root_rad=p["pitch_tip_rad"])
    for name in OUTPUTS + ("thrust_balance_coefficient", "max_local_balance_coefficient"):
        assert getattr(linear, name) == pytest.approx(getattr(constant, name), abs=1e-14)
    for name in ("radial_fraction", "inflow_ratio", "pitch_rad",
                 "approx_inflow_angle_rad", "approx_angle_of_attack_rad"):
        assert getattr(linear, name) == pytest.approx(getattr(constant, name), abs=1e-14)


@pytest.mark.parametrize("cutout", [0.2, 0.6])
def test_endpoints_are_at_cutout_and_tip(cutout):
    check_reference(inputs(twist_law="linear", pitch_root_rad=0.04,
                           pitch_tip_rad=0.22, root_cutout_fraction=cutout))


@pytest.mark.parametrize("root", [None, True, False, "0.1", 0.1j, Decimal("0.1"),
                                      -0.1, math.nan, math.inf, -math.inf,
                                      math.nextafter(0.0, 1.0)])
def test_invalid_linear_root(root):
    with pytest.raises((TypeError, ValueError)):
        solve_hover(**inputs(twist_law="linear", pitch_root_rad=root))


def test_linear_requires_root():
    with pytest.raises((TypeError, ValueError)):
        solve_hover(**inputs(twist_law="linear"))


@pytest.mark.parametrize("law", ["constant", "hyperbolic"])
@pytest.mark.parametrize("root", [0.0, 0.12])
def test_old_laws_reject_extra_root(law, root):
    with pytest.raises((TypeError, ValueError)):
        solve_hover(**inputs(twist_law=law, pitch_root_rad=root))


@pytest.mark.parametrize("root,tip", [(0.0, 0.0), (0.0, 0.15), (0.15, 0.0)])
def test_zero_endpoints(root, tip):
    result = check_reference(inputs(twist_law="linear", pitch_root_rad=root, pitch_tip_rad=tip))
    if root == tip == 0:
        assert all(value == 0 for value in result.inflow_ratio)
        assert all(value == 0 for value in result.approx_inflow_angle_rad)
        assert all(value == 0 for value in result.approx_angle_of_attack_rad)


@pytest.mark.parametrize("root,tip", [(0.04, 0.24), (0.24, 0.04)])
def test_positive_increasing_and_decreasing_endpoints(root, tip):
    check_reference(inputs(twist_law="linear", pitch_root_rad=root, pitch_tip_rad=tip))


def test_cancellation_is_refused():
    with pytest.raises(ValueError):
        solve_hover(**inputs(twist_law="linear", chord_m=1e6,
                             pitch_root_rad=1e-20, pitch_tip_rad=1e-20))


def test_collapsed_midpoint_mesh_is_refused():
    with pytest.raises(ValueError):
        solve_hover(**inputs(twist_law="linear", pitch_root_rad=0.12,
                             root_cutout_fraction=math.nextafter(1.0, 0.0), annuli=32))


def test_seeded_decimal80_reference():
    rng = random.Random(20261107)
    for _ in range(80):
        radius = rng.uniform(0.1, 3.0)
        check_reference(inputs(
            twist_law="linear", radius_m=radius,
            angular_speed_rad_s=rng.uniform(50.0, 1000.0), density_kg_m3=rng.uniform(0.5, 2.0),
            blade_count=rng.randint(1, 8), chord_m=radius * rng.uniform(0.01, 0.1),
            lift_curve_slope_per_rad=rng.uniform(2.0, 7.0),
            pitch_root_rad=rng.uniform(0.001, 0.3), pitch_tip_rad=rng.uniform(0.001, 0.3),
            root_cutout_fraction=rng.uniform(0.1, 0.7), annuli=rng.randint(4, 32)))
