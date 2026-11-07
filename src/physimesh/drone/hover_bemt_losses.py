"""Experimental Prandtl tip/hub losses for the core's small-angle hover model.

References: https://raw.githubusercontent.com/byuflowlab/CCBlade.jl/master/src/airfoils.jl
and https://forums.nrel.gov/t/hub-losses/368 . The small-angle substitution
|sin(phi)| ~= lambda/r is ours. An explicit hub radius does not validate a
physical hub, and numerical convergence establishes no physical acceptance.
No swirl, stall, polars, Mach/Re effects, non-hover, strength, or electrical
model is included; no NASA fit or bias correction is claimed.
"""

import math
from dataclasses import dataclass, replace

from . import hover_bemt as core


@dataclass(frozen=True)
class PrandtlHoverSolution:
    """Immutable numerical result with explicit, unvalidated loss metadata."""

    solution: core.HoverSolution
    tip_hub_loss_factor: tuple[float, ...]
    max_fixed_point_iterations: int
    hub_loss_radius_fraction: float
    loss_model: str = "prandtl_small_angle"
    physical_validation: str = "NOT_ESTABLISHED"


def _part(numerator: float, divisor: float) -> float:
    # Saturation at f >= 40 has absolute factor error < 3e-18. Guard the
    # comparison too: unsupported intermediate ranges are conservatively refused.
    if numerator >= core._mul(40.0, divisor):
        return 1.0
    exponent = core._div(numerator, divisor)
    sine = core._normal(math.sqrt(core._normal(-math.expm1(-core._mul(2.0, exponent)))))
    return core._mul(2.0 / math.pi, math.atan2(sine, math.exp(-exponent)))


def _factor(radial: float, inflow: float, blades: int, hub: float) -> float:
    if inflow == 0.0:
        return 1.0
    half_blades = core._div(float(blades), 2.0)
    tip = _part(core._mul(half_blades, core._normal(1.0 - radial)), inflow)
    hub_part = _part(
        core._mul(core._mul(half_blades, radial), core._normal(radial - hub)),
        core._mul(hub, inflow),
    )
    factor = core._mul(tip, hub_part)
    if not 0.0 < factor <= 1.0:
        raise ValueError("Prandtl factor must be positive and at most one")
    return factor


def prandtl_tip_hub_factor(
    *, radial_fraction, inflow_ratio, blade_count, hub_loss_radius_fraction
) -> float:
    """Return Ftip * Fhub using lambda/r; zero inflow has the limit F = 1."""
    try:
        radial = core._number(radial_fraction, "radial_fraction")
        inflow = core._number(inflow_ratio, "inflow_ratio", zero=True)
        blades = core._integer(blade_count, "blade_count", 32)
        hub = core._number(hub_loss_radius_fraction, "hub_loss_radius_fraction")
        if not 0.0 < hub < radial < 1.0:
            raise ValueError("Require 0 < hub_loss_radius_fraction < radial_fraction < 1")
        return _factor(radial, inflow, blades, hub)
    except (OverflowError, ZeroDivisionError) as error:
        raise ValueError("Prandtl factor exceeds the supported numerical range") from error


def _station(theta, radial, inflow, blades, hub, solidity_slope, cap):
    if theta == 0.0:
        return 0.0, 1.0, 0
    theta_radial = core._mul(theta, radial)
    for iterations in range(1, cap + 1):
        factor = _factor(radial, inflow, blades, hub)
        discriminant = core._normal(
            1.0 + core._div(
                core._mul(core._mul(32.0, factor), theta_radial), solidity_slope
            )
        )
        updated = core._div(
            core._mul(2.0, theta_radial), core._normal(1.0 + math.sqrt(discriminant))
        )
        change = abs(core._normal(updated - inflow, zero=True))
        if change <= core._mul(1e-13, max(abs(updated), abs(inflow))):
            return updated, _factor(radial, updated, blades, hub), iterations
        inflow = updated
    raise ValueError("Prandtl fixed-point iteration did not converge")


def solve_hover_prandtl(
    *, hub_loss_radius_fraction, max_iterations=100, **hover_kwargs
) -> PrandtlHoverSolution:
    """Solve the original hover inputs with explicit tip/hub loss iteration.

    The hub must be no larger than the numerical root cutout. Iteration and
    local balance tolerances concern numerical representation only.
    """
    try:
        try:
            base = core.solve_hover(**hover_kwargs)
        except TypeError as error:
            raise ValueError("Unsupported or missing hover arguments") from error
        hub = core._number(hub_loss_radius_fraction, "hub_loss_radius_fraction")
        cap = core._integer(max_iterations, "max_iterations", 1000)
        cutout = float(hover_kwargs["root_cutout_fraction"])
        if not hub <= cutout:
            raise ValueError("hub_loss_radius_fraction must not exceed root_cutout_fraction")
        radius = float(hover_kwargs["radius_m"])
        omega = float(hover_kwargs["angular_speed_rad_s"])
        density = float(hover_kwargs["density_kg_m3"])
        blades = hover_kwargs["blade_count"]
        solidity = core._div(
            core._mul(float(blades), float(hover_kwargs["chord_m"])),
            core._mul(math.pi, radius),
        )
        solidity_slope = core._mul(solidity, float(hover_kwargs["lift_curve_slope_per_rad"]))
        blade_factor = core._div(solidity_slope, 2.0)
        width = core._div(core._normal(1.0 - cutout), float(base.annuli))
        area = core._mul(math.pi, core._mul(radius, radius))
        tip_speed = core._mul(omega, radius)
        thrust_scale = core._mul(core._mul(density, area), core._mul(tip_speed, tip_speed))
        power_scale = core._mul(thrust_scale, tip_speed)
        inflows, factors, angles, attacks, iteration_counts = [], [], [], [], []
        momentum_terms, blade_terms, induced_terms, balances = [], [], [], []
        for radial, theta, initial in zip(
            base.radial_fraction, base.pitch_rad, base.inflow_ratio
        ):
            inflow, factor, iterations = _station(
                theta, radial, initial, blades, hub, solidity_slope, cap
            )
            angle = core._div(inflow, radial)
            attack = core._positive_difference(theta, angle)
            blade_difference = core._positive_difference(
                core._mul(theta, core._mul(radial, radial)), core._mul(inflow, radial)
            )
            blade_local = core._mul(blade_factor, blade_difference)
            momentum_local = core._mul(
                core._mul(core._mul(4.0, factor), core._mul(inflow, inflow)), radial
            )
            balance = abs(core._normal(blade_local - momentum_local, zero=True))
            if balance > core._mul(1e-10, max(abs(blade_local), abs(momentum_local))):
                raise ValueError("Prandtl local blade/momentum balance did not converge")
            momentum_terms.append(core._mul(momentum_local, width))
            blade_terms.append(core._mul(blade_local, width))
            induced_terms.append(core._mul(core._mul(momentum_local, inflow), width))
            inflows.append(inflow)
            factors.append(factor)
            angles.append(angle)
            attacks.append(attack)
            balances.append(balance)
            iteration_counts.append(iterations)
        thrust_coefficient = core._sum(momentum_terms)
        blade_coefficient = core._sum(blade_terms)
        induced_coefficient = core._sum(induced_terms)
        power_coefficient = core._sum([induced_coefficient, base.profile_power_coefficient])
        power = core._mul(power_scale, power_coefficient)
        solution = replace(
            base,
            inflow_ratio=tuple(inflows),
            approx_inflow_angle_rad=tuple(angles),
            approx_angle_of_attack_rad=tuple(attacks),
            thrust_coefficient=thrust_coefficient,
            blade_thrust_coefficient=blade_coefficient,
            induced_power_coefficient=induced_coefficient,
            shaft_power_coefficient=power_coefficient,
            thrust_n=core._mul(thrust_scale, thrust_coefficient),
            shaft_power_w=power,
            shaft_torque_nm=core._div(power, omega),
            thrust_balance_coefficient=core._normal(
                blade_coefficient - thrust_coefficient, zero=True
            ),
            max_local_balance_coefficient=max(balances),
        )
        return PrandtlHoverSolution(solution, tuple(factors), max(iteration_counts), hub)
    except (OverflowError, ZeroDivisionError) as error:
        raise ValueError("Prandtl hover exceeds the supported numerical range") from error
