"""Numerical verification of the bounded COESA reference atmosphere.

Unlike independent rounded PDAS table tests, these tests check numerical
consistency using an independently specified temperature profile and Simpson
integration of d(log p)/dh = -g/(R*T). They do not validate weather, aircraft,
or physical accuracy.

Reference constants, layers, and base conditions:
https://www.pdas.com/atmosdef.html
Hydrostatic equation and altitude conversion:
https://www.pdas.com/hydro.pdf
These URLs document provenance; the tests perform no network access.
"""

import math
from itertools import pairwise

import pytest

from physimesh.drone.standard_atmosphere import standard_atmosphere

_ORACLE_G = 9.80665
_ORACLE_R = 8314.32 / 28.9644
_ORACLE_P0 = 101325.0
_ORACLE_RADIUS = 6_356_750.0
_BOUNDARIES = (11_000.0, 20_000.0)

_HEIGHTS = tuple(
    sorted(
        {float(h) for h in range(0, 30_001, 125)}
        | {
            boundary + offset
            for boundary in _BOUNDARIES
            for offset in (-1.0, -0.001, 0.0, 0.001, 1.0)
        }
    )
)


def _temperature(h):
    if h <= 11_000.0:
        return 288.15 - 0.0065 * h
    if h <= 20_000.0:
        return 216.65
    return 216.65 + 0.001 * (h - 20_000.0)


def _log_pressure_ratio(h, max_step=100.0):
    """Integrate the hydrostatic ODE, splitting every crossed layer boundary."""
    edges = [0.0, *(b for b in _BOUNDARIES if b < h), h]
    contributions = []
    for bottom, top in pairwise(edges):
        if top == bottom:
            continue
        panels = max(2, 2 * math.ceil((top - bottom) / (2 * max_step)))
        step = (top - bottom) / panels

        def integrand(x):
            return -_ORACLE_G / (_ORACLE_R * _temperature(x))

        interior = math.fsum(
            (4 if i % 2 else 2) * integrand(bottom + i * step)
            for i in range(1, panels)
        )
        contributions.append(
            step * (integrand(bottom) + interior + integrand(top)) / 3
        )
    return math.fsum(contributions)


def test_oracle_refinement_converges_independently():
    # Simpson error decreases by about 16 on halving the step. The additive
    # allowance accommodates floating-point summation near convergence.
    for h in (5_500.0, 11_000.0, 15_500.0, 20_000.0, 30_000.0):
        coarse, medium, fine, finer = (
            _log_pressure_ratio(h, step) for step in (400, 200, 100, 50)
        )
        assert abs(fine - medium) <= abs(medium - coarse) / 8 + 2e-14
        assert abs(finer - fine) <= abs(fine - medium) / 8 + 2e-14
        assert abs(finer - fine) < 2e-11


def test_dense_geopotential_pressure_matches_numerical_oracle():
    for h in _HEIGHTS:
        state = standard_atmosphere(h, altitude_kind="geopotential")
        expected = _ORACLE_P0 * math.exp(_log_pressure_ratio(h))
        # Refinement above establishes an oracle error comfortably below 1e-9.
        assert state.pressure_pa == pytest.approx(expected, rel=1e-9), h


def test_dense_geometric_states_match_numerical_oracle():
    for z in _HEIGHTS:
        h = _ORACLE_RADIUS * z / (_ORACLE_RADIUS + z)
        state = standard_atmosphere(z, altitude_kind="geometric")
        expected = _ORACLE_P0 * math.exp(_log_pressure_ratio(h))
        assert state.geopotential_altitude_m == pytest.approx(h, abs=1e-10)
        assert state.temperature_k == pytest.approx(_temperature(h), abs=1e-10)
        assert state.pressure_pa == pytest.approx(expected, rel=1e-9), z


def test_dense_altitude_roundtrip_states():
    # Geometric inputs through 30 km map to geopotential inputs within the
    # public domain; the inverse of geopotential 30 km would exceed that domain.
    for z in _HEIGHTS:
        h = _ORACLE_RADIUS * z / (_ORACLE_RADIUS + z)
        recovered_z = _ORACLE_RADIUS * h / (_ORACLE_RADIUS - h)
        assert recovered_z == pytest.approx(z, rel=2e-15, abs=1e-10)

        # Use the original in-domain value. The inverse can round one ULP
        # above 30 km; the strict production domain must not be widened.
        geometric = standard_atmosphere(z, altitude_kind="geometric")
        geopotential = standard_atmosphere(h, altitude_kind="geopotential")
        assert geometric.geopotential_altitude_m == pytest.approx(h, abs=1e-10)
        for attribute in ("pressure_pa", "temperature_k", "density_kg_m3"):
            assert getattr(geometric, attribute) == pytest.approx(
                getattr(geopotential, attribute), rel=2e-13
            )


def test_dense_temperature_and_ideal_gas_closure():
    for kind in ("geometric", "geopotential"):
        for altitude in _HEIGHTS:
            h = (
                altitude
                if kind == "geopotential"
                else _ORACLE_RADIUS * altitude / (_ORACLE_RADIUS + altitude)
            )
            state = standard_atmosphere(altitude, altitude_kind=kind)
            assert state.temperature_k == pytest.approx(
                _temperature(h), abs=1e-10
            )
            assert state.pressure_pa > 0
            assert state.density_kg_m3 > 0
            assert state.pressure_pa == pytest.approx(
                state.density_kg_m3 * _ORACLE_R * state.temperature_k,
                rel=5e-15,
            )


def test_centered_hydrostatic_derivative_off_boundaries():
    step = 1.0
    for h in range(250, 30_000, 250):
        if any(abs(h - boundary) <= step for boundary in _BOUNDARIES):
            continue
        below = standard_atmosphere(h - step, altitude_kind="geopotential")
        above = standard_atmosphere(h + step, altitude_kind="geopotential")
        derivative = (
            math.log(above.pressure_pa) - math.log(below.pressure_pa)
        ) / (2 * step)
        expected = -_ORACLE_G / (_ORACLE_R * _temperature(h))
        # A 1 m centered stencil has O(step**2) truncation error; 2e-9 relative
        # covers that error and cancellation in the logarithm subtraction.
        assert derivative == pytest.approx(expected, rel=2e-9), h


def test_isothermal_layer_pressure_ratios():
    # Secondary analytic check confined to the independently stated 216.65 K
    # layer; this expression is not used by the numerical pressure oracle.
    for bottom, top in (
        (11_000.0, 20_000.0),
        (11_001.0, 15_000.0),
        (13_500.0, 19_999.0),
    ):
        lower = standard_atmosphere(bottom, altitude_kind="geopotential")
        upper = standard_atmosphere(top, altitude_kind="geopotential")
        expected_ratio = math.exp(
            -9.80665 * (top - bottom) / ((8314.32 / 28.9644) * 216.65)
        )
        assert upper.pressure_pa / lower.pressure_pa == pytest.approx(
            expected_ratio, rel=2e-13
        )
