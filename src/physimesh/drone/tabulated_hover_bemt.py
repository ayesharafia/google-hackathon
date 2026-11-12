"""Experimental isolated-hover closure for tabulated chord and blade angle.

Piecewise-linear SI geometry supplies the local rotor-normalized solidity
sigma(x) = B*c(R*x)/(pi*R). Each midpoint uses the accepted attached-linear
blade/momentum closure independently. This extends geometry representation;
it establishes no physical validation, aircraft feasibility, or qualification.

Angles and inflow angles use small-angle approximations with no established
validity envelope. Lift slope and profile drag are constant: no Reynolds
polars, stall, swirl, compressibility, tip/root loss, ground/interference, or
structural qualification is included. Geometry provenance is supplied by the
caller; no missing hub geometry, airfoil, or uncertainty is inferred.

Constant chord and constant or affine blade angle reduce algebraically to the
accepted hover model. A table only approximates hyperbolic twist in general.
Constant pitch length is not constant blade angle.
"""

import math
from dataclasses import dataclass

from .hover_bemt import (
    _div,
    _integer,
    _mul,
    _normal,
    _number,
    _positive_difference,
    _sum,
)

MODEL = "tabulated_geometry_hover_experimental"
VERSION = "0.1"
_STATION_KEYS = frozenset(("radius_m", "chord_m", "blade_angle_rad"))
_GEOMETRY_KINDS = frozenset(
    ("measured", "digitized_measurement", "as_designed", "synthetic")
)


@dataclass(frozen=True)
class GeometryStation:
    """Immutable snapshot of one caller-supplied true-radius SI station."""

    radius_m: float
    chord_m: float
    blade_angle_rad: float


@dataclass(frozen=True)
class TabulatedHoverSolution:
    """Immutable midpoint result; balance residuals are blade minus momentum.

    Arrays have one entry per annulus. Local balance residuals compare the
    coefficient integrands before multiplication by the annular width.
    Geometry labels record caller assertions, not independently verified facts.
    """

    radius_m: float
    root_cutout_m: float
    geometry_source: str
    geometry_kind: str
    uncertainty_status: str
    stations: tuple[GeometryStation, ...]
    radii_m: tuple[float, ...]
    chord_m: tuple[float, ...]
    blade_angle_rad: tuple[float, ...]
    radial_fraction: tuple[float, ...]
    local_solidity: tuple[float, ...]
    inflow_ratio: tuple[float, ...]
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
    local_balance_coefficient: tuple[float, ...]
    max_local_balance_coefficient: float
    annuli: int
    model: str = MODEL
    version: str = VERSION
    physical_validation: str = "NOT_ESTABLISHED"
    status: str = "COMPUTED_EXPERIMENTAL"


def _provenance(value: object, name: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > 2000:
        raise ValueError(f"{name} must be a nonblank builtin str of at most 2000 characters")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"{name} must be valid UTF-8 text") from error
    return value


def _stations(value: object, radius: float, cutout: float) -> tuple[GeometryStation, ...]:
    if type(value) is not list or not 2 <= len(value) <= 256:
        raise ValueError("stations must be a builtin list containing 2..256 stations")
    result = []
    previous_fraction = None
    for index, station in enumerate(value):
        if (
            type(station) is not dict
            or any(type(key) is not str for key in station)
            or station.keys() != _STATION_KEYS
        ):
            raise ValueError(
                "Each station must be a builtin dict with exactly radius_m, chord_m, blade_angle_rad"
            )
        radial = _number(station["radius_m"], f"stations[{index}].radius_m", zero=True)
        chord = _number(station["chord_m"], f"stations[{index}].chord_m")
        angle = _number(station["blade_angle_rad"], f"stations[{index}].blade_angle_rad", zero=True)
        if radial > radius:
            raise ValueError("Station radii must lie in [0, radius_m]")
        fraction = _div(radial, radius)
        if result:
            if radial <= result[-1].radius_m:
                raise ValueError("Station radii must be strictly increasing")
            _normal(radial - result[-1].radius_m)
            if fraction <= previous_fraction:
                raise ValueError("Normalized station radii are not distinguishable")
        result.append(GeometryStation(radial, chord, angle))
        previous_fraction = fraction
    if result[0].radius_m > cutout or result[-1].radius_m != radius:
        raise ValueError("Stations must cover the entire active interval and end exactly at radius_m")
    return tuple(result)


def _interpolate(
    radial: float, left: GeometryStation, right: GeometryStation
) -> tuple[float, float]:
    """Interpolate both fields independently, without extension or clamping."""
    if radial == left.radius_m:
        return left.chord_m, left.blade_angle_rad
    if radial == right.radius_m:
        return right.chord_m, right.blade_angle_rad
    if not left.radius_m < radial < right.radius_m:
        raise ValueError("Geometry interpolation would extrapolate")
    span = _normal(right.radius_m - left.radius_m)
    offset = _normal(radial - left.radius_m)
    _normal(right.radius_m - radial)
    fraction = _div(offset, span)
    complement = _normal(1.0 - fraction)
    if not 0.0 < fraction < 1.0 or not 0.0 < complement < 1.0:
        raise ValueError("Interpolation coordinates are not distinguishable from endpoints")

    def interpolate(start: float, end: float) -> float:
        # Preserve constant fields exactly, including an identically zero angle.
        if start == end:
            return start
        return _sum([_mul(complement, start), _mul(fraction, end)])

    return (
        interpolate(left.chord_m, right.chord_m),
        interpolate(left.blade_angle_rad, right.blade_angle_rad),
    )


def solve_tabulated_hover(
    *,
    radius_m,
    angular_speed_rad_s,
    density_kg_m3,
    blade_count,
    root_cutout_m,
    annuli,
    lift_curve_slope_per_rad,
    profile_drag_coefficient,
    stations,
    geometry_source,
    geometry_kind,
    uncertainty_status,
) -> TabulatedHoverSolution:
    """Solve uniform physical midpoint annuli using caller-supplied SI geometry.

    Keyword fields are strict; stations must be a builtin list of exact builtin
    dictionaries. The first station may be anywhere from zero to the cutout;
    the last must equal the rotor radius exactly. No extrapolation, endpoint
    autofill, normalization of inputs, or physical acceptance is performed.
    Finite-normal arithmetic and distinguishable coordinates are required.
    """
    radius = _number(radius_m, "radius_m")
    omega = _number(angular_speed_rad_s, "angular_speed_rad_s")
    density = _number(density_kg_m3, "density_kg_m3")
    blades = _integer(blade_count, "blade_count", 32)
    cutout = _number(root_cutout_m, "root_cutout_m")
    count = _integer(annuli, "annuli", 2048)
    slope = _number(lift_curve_slope_per_rad, "lift_curve_slope_per_rad")
    drag = _number(profile_drag_coefficient, "profile_drag_coefficient", zero=True)
    source = _provenance(geometry_source, "geometry_source")
    uncertainty = _provenance(uncertainty_status, "uncertainty_status")
    if type(geometry_kind) is not str or geometry_kind not in _GEOMETRY_KINDS:
        raise ValueError(
            "geometry_kind must be measured, digitized_measurement, as_designed, or synthetic"
        )
    if cutout >= radius:
        raise ValueError("root_cutout_m must be strictly between zero and radius_m")

    try:
        geometry = _stations(stations, radius, cutout)
        cutout_fraction = _div(cutout, radius)
        if not 0.0 < cutout_fraction < 1.0:
            raise ValueError("Normalized cutout is not distinguishable from endpoints")
        span_m = _normal(radius - cutout)
        width_m = _div(span_m, float(count))
        width = _div(width_m, radius)
        edges_m = tuple(
            _normal(cutout + _mul(float(index), width_m)) for index in range(count)
        ) + (radius,)
        radii_m = tuple(
            _normal(cutout + _mul(index + 0.5, width_m)) for index in range(count)
        )
        edges = tuple(_div(edge, radius) for edge in edges_m)
        radii = tuple(_div(radial, radius) for radial in radii_m)
        if any(
            not (
                edges_m[index] < radial_m < edges_m[index + 1]
                and edges[index] < radii[index] < edges[index + 1]
            )
            for index, radial_m in enumerate(radii_m)
        ):
            raise ValueError("Annulus edges and midpoints are not distinguishable")

        circumference_factor = _mul(math.pi, radius)
        area = _mul(math.pi, _mul(radius, radius))
        tip_speed = _mul(omega, radius)
        thrust_scale = _mul(_mul(density, area), _mul(tip_speed, tip_speed))
        power_scale = _mul(thrust_scale, tip_speed)
        chords, pitches, solidities, inflows, angles, attacks = [], [], [], [], [], []
        momentum_terms, blade_terms, induced_terms, profile_terms = [], [], [], []
        local_balances = []
        segment = 0
        for radial_m, radial in zip(radii_m, radii):
            while segment < len(geometry) - 2 and radial_m > geometry[segment + 1].radius_m:
                segment += 1
            chord, theta = _interpolate(radial_m, geometry[segment], geometry[segment + 1])
            solidity = _div(_mul(float(blades), chord), circumference_factor)
            solidity_slope = _mul(solidity, slope)
            blade_factor = _div(solidity_slope, 2.0)
            profile_factor = _div(_mul(solidity, drag), 2.0)
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
            local_balances.append(_normal(blade_local - momentum_local, zero=True))
            chords.append(chord)
            pitches.append(theta)
            solidities.append(solidity)
            inflows.append(inflow)
            angles.append(angle)
            attacks.append(attack)

        thrust_coefficient = _sum(momentum_terms)
        blade_coefficient = _sum(blade_terms)
        induced_coefficient = _sum(induced_terms)
        profile_coefficient = _sum(profile_terms)
        power_coefficient = _sum([induced_coefficient, profile_coefficient])
        power = _mul(power_scale, power_coefficient)
        return TabulatedHoverSolution(
            radius_m=radius,
            root_cutout_m=cutout,
            geometry_source=source,
            geometry_kind=geometry_kind,
            uncertainty_status=uncertainty,
            stations=geometry,
            radii_m=radii_m,
            chord_m=tuple(chords),
            blade_angle_rad=tuple(pitches),
            radial_fraction=radii,
            local_solidity=tuple(solidities),
            inflow_ratio=tuple(inflows),
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
            local_balance_coefficient=tuple(local_balances),
            max_local_balance_coefficient=max(abs(balance) for balance in local_balances),
            annuli=count,
        )
    except (OverflowError, ZeroDivisionError) as error:
        raise ValueError("Derived calculation exceeds the supported numerical range") from error
