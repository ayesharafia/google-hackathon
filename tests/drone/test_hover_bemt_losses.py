from dataclasses import FrozenInstanceError, asdict
from math import acos, exp, fsum, pi, sqrt

import pytest

from physimesh.drone.hover_bemt import solve_hover
from physimesh.drone.hover_bemt_losses import (
    prandtl_tip_hub_factor,
    solve_hover_prandtl,
)


def hover_kwargs(twist_law="constant"):
    return {"radius_m": 1., "angular_speed_rad_s": 100., "density_kg_m3": 1.225,
                "blade_count": 2, "chord_m": .05, "lift_curve_slope_per_rad": 5.7,
                "profile_drag_coefficient": .01, "pitch_tip_rad": .12,
                "root_cutout_fraction": .2, "annuli": 32, "twist_law": twist_law,
                "pitch_root_rad": .16 if twist_law == "linear" else None}


def independent_factor(r, lam, blades, hub):
    exponents = (blades / 2 * (1 - r) / lam,
                 blades / 2 * r * (r - hub) / (hub * lam))
    tip, hub_part = (1. if f >= 40 else 2 / pi * acos(exp(-f))
                     for f in exponents)
    return tip * hub_part


@pytest.mark.parametrize("r,lam,blades,hub", [
    (.3, .1, 1, .2), (.5, .2, 2, .1), (.8, .3, 3, .2),
    (.6, .7, 8, .4), (.9, 2., 32, .2),
])
def test_factor(r, lam, blades, hub):
    actual = prandtl_tip_hub_factor(radial_fraction=r, inflow_ratio=lam,
                                   blade_count=blades, hub_loss_radius_fraction=hub)
    assert actual == pytest.approx(independent_factor(r, lam, blades, hub), abs=2e-14, rel=0)


def test_zero_and_tiny_exponent():
    assert prandtl_tip_hub_factor(radial_fraction=.5, inflow_ratio=0.,
                                 blade_count=2, hub_loss_radius_fraction=.1) == 1.
    r, hub, lam, blades = .5, .1, 1e20, 2
    ftip = blades / 2 * (1 - r) / lam
    fhub = blades / 2 * r * (r - hub) / (hub * lam)
    leading = (2 / pi * sqrt(2 * ftip)) * (2 / pi * sqrt(2 * fhub))
    actual = prandtl_tip_hub_factor(radial_fraction=r, inflow_ratio=lam,
                                   blade_count=blades, hub_loss_radius_fraction=hub)
    assert actual > 0
    assert actual == pytest.approx(leading, rel=1e-14, abs=0)


@pytest.mark.parametrize("name,value", [
    (name, value)
    for name in ("radial_fraction", "inflow_ratio", "blade_count", "hub_loss_radius_fraction")
    for value in (True, False, float("nan"), float("inf"), -float("inf"), -1.)
] + [("radial_fraction", v) for v in (0., .2, 1., 1.1)]
  + [("hub_loss_radius_fraction", v) for v in (0., .5, 1.)]
  + [("blade_count", v) for v in (0, 33, 2.)])
def test_invalid_factor(name, value):
    kwargs = {"radial_fraction": .5, "inflow_ratio": .1,
                  "blade_count": 2, "hub_loss_radius_fraction": .2}
    kwargs[name] = value
    with pytest.raises(ValueError):
        prandtl_tip_hub_factor(**kwargs)


@pytest.mark.parametrize("twist_law", ["constant", "hyperbolic", "linear"])
@pytest.mark.parametrize("hub", [.1, .2])
def test_independent_hover(twist_law, hub):
    kwargs = hover_kwargs(twist_law)
    base = solve_hover(**kwargs)
    before = repr(base).encode()
    result = solve_hover_prandtl(hub_loss_radius_fraction=hub, **kwargs)
    assert repr(base).encode() == before
    dr, sa = .8 / 32, (2 * .05 / pi) * 5.7
    radii = tuple(.2 + (i + .5) * dr for i in range(32))
    pitches, inflows, factors = [], [], []
    for r in radii:
        theta = (.12 if twist_law == "constant" else .12 / r
                 if twist_law == "hyperbolic" else .16 + (.12 - .16) * (r - .2) / .8)
        lo = 2 * theta * r / (1 + sqrt(1 + 32 * theta * r / sa))
        hi = theta * r
        for _ in range(80):
            lam = (lo + hi) / 2
            residual = independent_factor(r, lam, 2, hub) * lam * lam + sa / 8 * lam - sa / 8 * theta * r
            if residual > 0:
                hi = lam
            else:
                lo = lam
        lam = (lo + hi) / 2
        pitches.append(theta)
        inflows.append(lam)
        factors.append(independent_factor(r, lam, 2, hub))
    ct = fsum(4 * f * inflow * inflow * r * dr for r, inflow, f in zip(radii, inflows, factors))
    cpi = fsum(4 * f * inflow**3 * r * dr for r, inflow, f in zip(radii, inflows, factors))
    midpoint_cp0 = fsum((2 * .05 / pi) * .01 / 2 * r**3 * dr for r in radii)
    cp0 = base.profile_power_coefficient
    assert result.solution.radial_fraction == pytest.approx(radii, rel=1e-10, abs=0)
    assert result.solution.pitch_rad == pytest.approx(pitches, rel=1e-10, abs=0)
    assert result.solution.inflow_ratio == pytest.approx(inflows, rel=1e-10, abs=0)
    assert result.solution.thrust_coefficient == pytest.approx(ct, rel=1e-10, abs=0)
    assert result.solution.induced_power_coefficient == pytest.approx(cpi, rel=1e-10, abs=0)
    assert result.solution.profile_power_coefficient == pytest.approx(midpoint_cp0, rel=1e-10, abs=0)
    assert result.solution.shaft_power_coefficient == pytest.approx(cp0 + cpi, rel=1e-10, abs=0)
    thrust_scale = 1.225 * pi * 100.**2
    assert result.solution.thrust_n == pytest.approx(ct * thrust_scale, rel=1e-10, abs=0)
    assert result.solution.shaft_power_w == pytest.approx((cp0 + cpi) * thrust_scale * 100., rel=1e-10, abs=0)
    assert result.solution.shaft_torque_nm == pytest.approx((cp0 + cpi) * thrust_scale, rel=1e-10, abs=0)
    assert result.solution.profile_power_coefficient == base.profile_power_coefficient
    assert result.tip_hub_loss_factor == pytest.approx(factors, rel=1e-10, abs=0)
    assert 1 <= result.max_fixed_point_iterations <= 100
    assert result.hub_loss_radius_fraction == hub
    assert result.loss_model == "prandtl_small_angle"
    assert result.physical_validation == "NOT_ESTABLISHED"
    assert "COMPUTED_EXPERIMENTAL" in repr(result.solution)
    with pytest.raises(FrozenInstanceError):
        result.max_fixed_point_iterations = 0


def test_zero_pitch_parity():
    kwargs = hover_kwargs()
    kwargs["pitch_tip_rad"] = 0.
    base = solve_hover(**kwargs)
    before = repr(base).encode()
    result = solve_hover_prandtl(hub_loss_radius_fraction=.2, **kwargs)
    assert repr(base).encode() == before
    assert asdict(result.solution) == asdict(base)
    assert result.tip_hub_loss_factor == (1.,) * 32
    assert result.max_fixed_point_iterations == 0


@pytest.mark.parametrize("extra", [{"max_iterations": v} for v in (1, 0, 1., True, 1001)]
                         + [{"unknown_option": 1}, {"hub_loss_radius_fraction": .3}]
                         + [{"hub_loss_radius_fraction": v} for v in (0., -1., True, float("nan"), float("inf"))])
def test_solver_rejections(extra):
    kwargs = dict(hover_kwargs(), hub_loss_radius_fraction=.2)
    kwargs.update(extra)
    with pytest.raises(ValueError):
        solve_hover_prandtl(**kwargs)
