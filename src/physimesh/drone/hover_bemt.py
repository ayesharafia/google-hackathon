"""Experimental isolated-hover, small-angle, attached linear-lift BEMT.

References:
https://sankar.gatech.edu/AE6070/Combined.BE.Momentum.Theory.doc
https://kumar-sumeet.github.io/HeliAeroNotes/Lectures/2_BET/2_BEMT.html

Positive finite answers and balance diagnostics establish no physical acceptance.
Angles are approximations without a validated range. No loss factors, swirl,
stall, Reynolds polars, compressibility, non-hover flight, ground/interference,
or structural validation are included. Checks concern numerical representation.
"""

import math
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class HoverSolution:
    """Immutable numerical result; balance differences are blade minus momentum."""

    radial_fraction: tuple[float, ...]
    inflow_ratio: tuple[float, ...]
    pitch_rad: tuple[float, ...]
    approx_inflow_angle_rad: tuple[float, ...]
    approx_angle_of_attack_rad: tuple[float, ...]
    thrust_coefficient: float
    blade_thrust_coefficient: float
    induced_power_coefficient: float
    profile_power_coefficient: float
    shaft_power_coefficient: float
    thrust_n: float
    shaft_power_w: float
    shaft_torque_nm: float
    thrust_balance_coefficient: float
    max_local_balance_coefficient: float
    annuli: int
    physical_validation: str = "NOT_ESTABLISHED"
    status: str = "COMPUTED_EXPERIMENTAL"


def _normal(value: float, *, zero: bool = False) -> float:
    """Accept finite normal floats, permitting zero only when explicitly enabled."""
    if not math.isfinite(value) or (
        abs(value) < sys.float_info.min and not (zero and value == 0.0)
    ):
        raise ValueError("Value is outside the supported finite-normal range")
    return value


def _number(value: object, name: str, *, zero: bool = False) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a builtin float or int")
    try:
        result = _normal(float(value), zero=zero)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{name} is outside the supported numerical range") from error
    if result < 0.0:
        raise ValueError(f"{name} must be {'nonnegative' if zero else 'positive'}")
    return result


def _integer(value: object, name: str, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be a builtin int in 1..{maximum}")
    return value


def _mul(left: float, right: float) -> float:
    return _normal(left * right, zero=left == 0.0 or right == 0.0)


def _div(left: float, right: float) -> float:
    return _normal(left / right, zero=left == 0.0)


def _sum(values: list[float]) -> float:
    return _normal(math.fsum(values), zero=all(value == 0.0 for value in values))


def _positive_difference(left: float, right: float) -> float:
    """Subtract positive operands only when roughly half the significand remains.

    Exact zero operands preserve the zero-pitch branch. Otherwise require a
    positive difference exceeding sqrt(float epsilon) times the larger operand.
    This bounds cancellation amplification to roughly 1/sqrt(epsilon); it is a
    numerical support limit, not an angle or physical acceptance threshold.
    """
    difference = left - right
    if left == right == 0.0:
        return difference
    if difference <= math.sqrt(sys.float_info.epsilon) * max(left, right):
        raise ValueError("Subtractive cancellation exceeds supported numerical precision")
    return _normal(difference)


def solve_hover(
    *,
    radius_m,
    angular_speed_rad_s,
    density_kg_m3,
    blade_count,
    chord_m,
    lift_curve_slope_per_rad,
    profile_drag_coefficient,
    pitch_tip_rad,
    root_cutout_fraction,
    twist_law="constant",
    annuli=32,
    pitch_root_rad=None,
) -> HoverSolution:
    """Assemble uniform midpoint annuli; reject unsupported numerical extremes.

    This is numerical verification only. Residuals carry no acceptance threshold;
    neither small-angle applicability nor any physical envelope is established.
    """
    radius = _number(radius_m, "radius_m")
    omega = _number(angular_speed_rad_s, "angular_speed_rad_s")
    density = _number(density_kg_m3, "density_kg_m3")
    blades = _integer(blade_count, "blade_count", 32)
    chord = _number(chord_m, "chord_m")
    slope = _number(lift_curve_slope_per_rad, "lift_curve_slope_per_rad")
    drag = _number(profile_drag_coefficient, "profile_drag_coefficient", zero=True)
    tip_pitch = _number(pitch_tip_rad, "pitch_tip_rad", zero=True)
    cutout = _number(root_cutout_fraction, "root_cutout_fraction")
    count = _integer(annuli, "annuli", 2048)
    if cutout >= 1.0:
        raise ValueError("root_cutout_fraction must be strictly between zero and one")
    if type(twist_law) is not str or twist_law not in ("constant", "hyperbolic", "linear"):
        raise ValueError("twist_law must be 'constant', 'hyperbolic', or 'linear'")
    if twist_law == "linear":
        if pitch_root_rad is None:
            raise ValueError("pitch_root_rad is required for linear twist")
        root_pitch = _number(pitch_root_rad, "pitch_root_rad", zero=True)
    elif pitch_root_rad is not None:
        raise ValueError("pitch_root_rad is only supported for linear twist")

    try:
        width = _div(_normal(1.0 - cutout), float(count))
        edges = tuple(
            _normal(cutout + _mul(float(index), width))
            for index in range(count)
        ) + (1.0,)
        radii = tuple(
            _normal(cutout + _mul(index + 0.5, width)) for index in range(count)
        )
        if any(
            not edges[index] < radial < edges[index + 1]
            for index, radial in enumerate(radii)
        ):
            raise ValueError("Annulus edges and midpoints are not distinguishable")
        solidity = _div(_mul(float(blades), chord), _mul(math.pi, radius))
        solidity_slope = _mul(solidity, slope)
        blade_factor = _div(solidity_slope, 2.0)
        profile_factor = _div(_mul(solidity, drag), 2.0)
        area = _mul(math.pi, _mul(radius, radius))
        tip_speed = _mul(omega, radius)
        thrust_scale = _mul(_mul(density, area), _mul(tip_speed, tip_speed))
        power_scale = _mul(thrust_scale, tip_speed)
        inflows, pitches, angles, attacks = [], [], [], []
        momentum_terms, blade_terms, induced_terms, profile_terms = [], [], [], []
        local_balances = []
        for radial in radii:
            if twist_law == "linear":
                # Endpoints are at the cutout and tip, over the active span.
                fraction = _div(_normal(radial - cutout), _normal(1.0 - cutout))
                theta = _sum([
                    _mul(_normal(1.0 - fraction), root_pitch),
                    _mul(fraction, tip_pitch),
                ])
            else:
                theta = tip_pitch if twist_law == "constant" else _div(tip_pitch, radial)
            theta_radial = _mul(theta, radial)
            if theta_radial == 0.0:
                inflow = 0.0
            else:
                discriminant = _normal(
                    1.0 + _div(_mul(32.0, theta_radial), solidity_slope)
                )
                denominator = _normal(1.0 + math.sqrt(discriminant))
                inflow = _div(_mul(2.0, theta_radial), denominator)
            angle = _div(inflow, radial)
            attack = _positive_difference(theta, angle)
            radial_squared = _mul(radial, radial)
            inflow_squared = _mul(inflow, inflow)
            momentum_local = _mul(_mul(4.0, inflow_squared), radial)
            blade_difference = _positive_difference(
                _mul(theta, radial_squared), _mul(inflow, radial)
            )
            blade_local = _mul(blade_factor, blade_difference)
            induced_local = _mul(momentum_local, inflow)
            profile_local = _mul(profile_factor, _mul(radial_squared, radial))
            momentum_terms.append(_mul(momentum_local, width))
            blade_terms.append(_mul(blade_local, width))
            induced_terms.append(_mul(induced_local, width))
            profile_terms.append(_mul(profile_local, width))
            local_balances.append(abs(_normal(blade_local - momentum_local, zero=True)))
            inflows.append(inflow)
            pitches.append(theta)
            angles.append(angle)
            attacks.append(attack)
        thrust_coefficient = _sum(momentum_terms)
        blade_coefficient = _sum(blade_terms)
        induced_coefficient = _sum(induced_terms)
        profile_coefficient = _sum(profile_terms)
        power_coefficient = _sum([induced_coefficient, profile_coefficient])
        power = _mul(power_scale, power_coefficient)
        return HoverSolution(
            radial_fraction=radii,
            inflow_ratio=tuple(inflows),
            pitch_rad=tuple(pitches),
            approx_inflow_angle_rad=tuple(angles),
            approx_angle_of_attack_rad=tuple(attacks),
            thrust_coefficient=thrust_coefficient,
            blade_thrust_coefficient=blade_coefficient,
            induced_power_coefficient=induced_coefficient,
            profile_power_coefficient=profile_coefficient,
            shaft_power_coefficient=power_coefficient,
            thrust_n=_mul(thrust_scale, thrust_coefficient),
            shaft_power_w=power,
            shaft_torque_nm=_div(power, omega),
            thrust_balance_coefficient=_normal(
                blade_coefficient - thrust_coefficient, zero=True
            ),
            max_local_balance_coefficient=max(local_balances),
            annuli=count,
        )
    except (OverflowError, ZeroDivisionError) as error:
        raise ValueError("Derived calculation exceeds the supported numerical range") from error
