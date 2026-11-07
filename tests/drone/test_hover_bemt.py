"""BEMT physics checks; source: https://sankar.gatech.edu/AE6070/Combined.BE.Momentum.Theory.doc
These checks do not establish tip, swirl, stall, compressibility, ground, or interference validity.
"""
import itertools
import math
from decimal import Decimal, localcontext

import pytest

from physimesh.drone.hover_bemt import solve_hover

BASE = {
    "radius_m": 1.0, "angular_speed_rad_s": 100.0,
    "density_kg_m3": 1.225, "blade_count": 2, "chord_m": 0.05,
    "lift_curve_slope_per_rad": 5.7, "profile_drag_coefficient": 0.01,
    "pitch_tip_rad": 0.08, "root_cutout_fraction": 0.2,
}
NUMERIC_FIELDS = (
    "radius_m", "angular_speed_rad_s", "density_kg_m3", "chord_m",
    "lift_curve_slope_per_rad", "profile_drag_coefficient",
    "pitch_tip_rad", "root_cutout_fraction",
)

def assert_finite(result):
    values = (
        result.thrust_coefficient, result.blade_thrust_coefficient,
        result.induced_power_coefficient, result.profile_power_coefficient,
        result.shaft_power_coefficient, result.thrust_n, result.shaft_power_w,
        result.shaft_torque_nm, result.thrust_balance_coefficient,
        result.max_local_balance_coefficient,
    )
    assert all(math.isfinite(value) for value in values)
    for values in (result.radial_fraction, result.inflow_ratio, result.pitch_rad,
                   result.approx_inflow_angle_rad, result.approx_angle_of_attack_rad):
        assert isinstance(values, tuple)
        assert len(values) == result.annuli
        assert all(math.isfinite(value) for value in values)

@pytest.mark.parametrize("law", ["constant", "hyperbolic"])
def test_baseline_geometry_balance_and_scales(law):
    result = solve_hover(**BASE, twist_law=law)
    assert_finite(result)
    assert result.status == "COMPUTED_EXPERIMENTAL"
    assert result.physical_validation == "NOT_ESTABLISHED"
    assert result.annuli == 32
    assert abs(result.thrust_balance_coefficient) < 1e-14
    assert abs(result.max_local_balance_coefficient) < 1e-14
    expected_radii = [0.2 + (index + 0.5) * 0.8 / 32 for index in range(32)]
    assert result.radial_fraction == pytest.approx(expected_radii)
    for radius, inflow, pitch, phi, alpha in zip(
        result.radial_fraction, result.inflow_ratio, result.pitch_rad,
        result.approx_inflow_angle_rad, result.approx_angle_of_attack_rad,
    ):
        assert pitch == pytest.approx(0.08 if law == "constant" else 0.08 / radius)
        assert phi == pytest.approx(inflow / radius, rel=1e-12, abs=1e-15)
        assert alpha == pytest.approx(pitch - phi, rel=1e-12, abs=1e-15)
    assert result.thrust_n > 0
    assert result.thrust_n == pytest.approx(1.225 * math.pi * 100**2 * result.thrust_coefficient)
    assert result.shaft_power_w == pytest.approx(1.225 * math.pi * 100**3 * result.shaft_power_coefficient)
    assert result.shaft_torque_nm == pytest.approx(result.shaft_power_w / 100)
    assert result.shaft_power_coefficient == pytest.approx(
        result.induced_power_coefficient + result.profile_power_coefficient)

@pytest.mark.parametrize("annuli", [8, 32, 64])
def test_hyperbolic_exact_integrals(annuli):
    with localcontext() as context:
        context.prec = 80
        pi = Decimal("3.141592653589793238462643383279502884197169399375105820974944592307816406286208998")
        loading = Decimal(2) * Decimal("0.05") / pi * Decimal("5.7") / 8
        inflow = 2 * loading * Decimal("0.08") / (
            (loading**2 + 4 * loading * Decimal("0.08")).sqrt() + loading)
        thrust = 2 * inflow**2 * (1 - Decimal("0.2")**2)
        induced = 2 * inflow**3 * (1 - Decimal("0.2")**2)
    result = solve_hover(**BASE, twist_law="hyperbolic", annuli=annuli)
    assert result.inflow_ratio == pytest.approx([float(inflow)] * annuli, rel=1e-12)
    assert result.thrust_coefficient == pytest.approx(float(thrust), rel=1e-12)
    assert result.induced_power_coefficient == pytest.approx(float(induced), rel=1e-12)

def test_profile_midpoint_error_is_second_order():
    exact = (2 * 0.05 / math.pi) * 0.01 / 8 * (1 - 0.2**4)
    errors = [exact - solve_hover(**BASE, annuli=count).profile_power_coefficient
              for count in (8, 16, 32, 64)]
    assert all(error > 0 for error in errors)
    for coarse, fine in itertools.pairwise(errors):
        assert coarse / fine == pytest.approx(4, rel=1e-8)

@pytest.mark.parametrize("field,value,factors", [
    ("angular_speed_rad_s", 200.0, (4, 8, 4)),
    ("density_kg_m3", 2.45, (2, 2, 2)),
])
def test_physical_scaling(field, value, factors):
    base = solve_hover(**BASE)
    scaled = solve_hover(**{**BASE, field: value})
    assert (scaled.thrust_n, scaled.shaft_power_w, scaled.shaft_torque_nm) == pytest.approx(
        (base.thrust_n * factors[0], base.shaft_power_w * factors[1], base.shaft_torque_nm * factors[2]))

@pytest.mark.parametrize("drag", [0.0, 0.01])
def test_zero_pitch(drag):
    result = solve_hover(**{**BASE, "pitch_tip_rad": 0.0, "profile_drag_coefficient": drag})
    assert result.thrust_n == result.thrust_coefficient == result.blade_thrust_coefficient == 0
    assert result.induced_power_coefficient == 0
    assert (result.profile_power_coefficient > 0) == (drag > 0)
    assert (result.shaft_power_w > 0) == (drag > 0)
    assert (result.shaft_torque_nm > 0) == (drag > 0)

def test_immutable_result():
    result = solve_hover(**BASE)
    with pytest.raises(AttributeError):
        result.thrust_n = 0
    with pytest.raises(TypeError):
        result.radial_fraction[0] = 0

@pytest.mark.parametrize("field", NUMERIC_FIELDS)
@pytest.mark.parametrize("value", [True, False, "1", math.nan, math.inf, -math.inf])
def test_invalid_numeric_inputs(field, value):
    with pytest.raises((TypeError, ValueError)):
        solve_hover(**{**BASE, field: value})

@pytest.mark.parametrize("field,upper", [("blade_count", 32), ("annuli", 2048)])
def test_strict_integer_bounds(field, upper):
    for value in (1, upper):
        assert_finite(solve_hover(**{**BASE, field: value}))
    for value in (True, False, "2", 2.0, math.nan, math.inf, -1, 0, upper + 1):
        with pytest.raises((TypeError, ValueError)):
            solve_hover(**{**BASE, field: value})

@pytest.mark.parametrize("field,value", [
    ("twist_law", "linear"), ("twist_law", ""), ("twist_law", None),
    ("root_cutout_fraction", 0), ("root_cutout_fraction", 1), ("root_cutout_fraction", -0.1),
])
def test_invalid_law_and_cutout(field, value):
    with pytest.raises((TypeError, ValueError)):
        solve_hover(**{**BASE, field: value})

@pytest.mark.parametrize("field", ["radius_m", "angular_speed_rad_s", "density_kg_m3", "chord_m", "pitch_tip_rad"])
def test_extremes_fail_cleanly_or_remain_finite(field):
    try:
        result = solve_hover(**{**BASE, field: 1e300})
    except ValueError:
        return
    assert_finite(result)
