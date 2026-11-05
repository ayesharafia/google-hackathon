import math

import numpy as np
import pytest

from physimesh.drone.performance import RotorMapV1


def curve(rows, *, basis="electrical", efficiency=None, intervals=None):
    return RotorMapV1(
        dataset_id="test-map",
        configuration_id="test-config",
        source_kind="analytic_fixture",
        source_description="Source-bound numerical regression fixture",
        units="rpm_N_Nm_W",
        torque_convention="absorbed_shaft_magnitude",
        density_kg_m3=1.225,
        axial_inflow_m_s=0.0,
        pitch_deg=0.0,
        max_continuous_duration_s=60.0,
        power_basis=basis,
        efficiency=efficiency,
        efficiency_source="fixture" if efficiency is not None else None,
        covered_intervals_rpm=(
            intervals if intervals is not None
            else ((rows[0][0], rows[-1][0]),)
        ),
        points=tuple(
            {'rpm': r, 'thrust_n': t, 'shaft_torque_nm': q, 'power_w': p}
            for r, t, q, p in rows
        ),
    )


def evaluate(m, rpm):
    return m.evaluate(rpm, density=1.225, inflow=0.0, pitch=0.0)


# Independent ordinary-case expectations, not calculations copied from the patch.
def test_normal_electrical_curve():
    m = curve([(0., 0., 0., 0.), (60., 10., 0., 100.)])
    result = evaluate(m, 30.)
    assert result["thrust_n"] == pytest.approx(5.)
    assert result["electrical_power_w"] == pytest.approx(50.)
    profile = m.convex_static_profile()
    np.testing.assert_allclose(profile["power_slopes"], [10.])
    np.testing.assert_allclose(profile["power_offsets"], [0.])


def test_normal_shaft_curve():
    m = curve(
        [(0., 0., 2., 0.), (60., 10., 2., 4. * math.pi)],
        basis="shaft", efficiency=0.5,
    )
    assert evaluate(m, 30.)["electrical_power_w"] == pytest.approx(
        4. * math.pi
    )
    np.testing.assert_allclose(
        m.convex_static_profile()["power"], [0., 8. * math.pi]
    )


def test_coverage_hole_remains_rejected():
    m = curve(
        [(0., 0., 0., 0.), (30., 1., 0., 1.),
         (60., 2., 0., 2.), (90., 3., 0., 3.)],
        intervals=((0., 30.), (60., 90.)),
    )
    with pytest.raises(ValueError, match="covered intervals"):
        evaluate(m, 45.)


# Each of these rejects or returns a finite value where the original fails.
def test_constructor_rejects_finite_inputs_with_overflowing_demand():
    with pytest.raises(ValueError, match="shaft demand must be finite"):
        curve([(0., 0., 1e308, 0.), (120., 1., 1e308, 0.)])


def test_evaluate_rejects_interior_demand_overflow():
    m = curve([(0., 0., 1e308, 0.), (120., 1., 0., 0.)])
    with pytest.raises(ValueError, match="must be finite"):
        evaluate(m, 60.)


def test_huge_rpm_representable_demand_uses_safe_order():
    m = curve([(0., 0., 1., 0.), (1e308, 1., 1., 2e307)])
    result = evaluate(m, 1e308)
    assert result["electrical_power_w"] == 2e307
    assert math.isfinite(result["electrical_power_w"])


def test_zero_torque_at_huge_rpm_remains_valid():
    m = curve([(0., 0., 0., 0.), (1e308, 1., 0., 0.)])
    assert evaluate(m, 1e308)["electrical_power_w"] == 0.


@pytest.mark.parametrize("operation", ["evaluate", "profile"])
def test_efficiency_conversion_overflow_rejected(operation):
    m = curve(
        [(0., 0., 1., 0.), (60., 1., 1., 2. * math.pi)],
        basis="shaft", efficiency=1e-308,
    )
    with np.errstate(over="ignore", invalid="ignore"), pytest.raises(ValueError, match="must be finite"):
        if operation == "evaluate":
            evaluate(m, 60.)
        else:
            m.convex_static_profile()


@pytest.mark.parametrize("thrust", [
    (0., 1e-308),  # Infinite power slope.
    (2., 3.),     # Finite slope, infinite power offset.
])
def test_profile_rejects_nonfinite_power_coefficients(thrust):
    m = curve([
        (0., thrust[0], 0., 0.),
        (60., thrust[1], 0., 1e308),
    ])
    with np.errstate(over="ignore", invalid="ignore"), pytest.raises(ValueError, match="must be finite"):
        m.convex_static_profile()
