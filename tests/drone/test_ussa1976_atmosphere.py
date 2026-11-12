"""V152: USSA-1976 reproducibility checks, not physical validation.

Published fixtures: NOAA-S/T 76-1562, Table I, doc pp. 60/62 (geopotential
rows). Source URL, scan locators, errata and the adjudicated 25 km density
discrepancy are preserved in specs/drone-high-altitude-atmosphere.md.
The numerical oracle integrates hydrostatic balance rather than reproducing
the implementation's layer pressure recurrence. No network access is used.
"""

import math
from dataclasses import FrozenInstanceError
from itertools import pairwise

import pytest

from physimesh.drone.atmosphere import (
    check_altitude_pressure_consistency,
    isa_troposphere,
    ussa1976_state,
)


@pytest.mark.parametrize("h,t,p_mb,rho", [
    (20_000.0, 216.650, 54.748, 8.8035e-2),
    (25_000.0, 221.650, 25.110, 3.9446e-2),
    (30_000.0, 226.650, 11.718, 1.8012e-2),
])
def test_published_geopotential_table(h, t, p_mb, rho):
    state = ussa1976_state(h, altitude_kind="geopotential")
    assert state.temperature_k == pytest.approx(t, rel=0, abs=0.001)
    assert state.pressure_pa == pytest.approx(100 * p_mb, rel=1e-4)
    # At 25 km the table's independently rounded rho column is inconsistent
    # with P/T and rho/rho0; v2 explicitly pins 1e-3, not a tuned tolerance.
    assert state.density_kg_m3 == pytest.approx(rho, rel=1e-3)


def _reference_temperature(h):
    if h <= 11_000:
        return 288.15 - 0.0065 * h
    if h <= 20_000:
        return 216.65
    if h <= 32_000:
        return 216.65 + (h - 20_000) / 1000
    return 228.65 + 0.0028 * (h - 32_000)


def _hydrostatic_log_ratio(h, step_limit):
    """Composite Simpson integration of d(log P)/dH, split at layer edges."""
    edges = [0.0, *(b for b in (11_000, 20_000, 32_000) if b < h), h]
    pieces = []
    for lower, upper in pairwise(edges):
        if upper == lower:
            continue
        n = max(2, 2 * math.ceil((upper - lower) / (2 * step_limit)))
        step = (upper - lower) / n

        def gradient(x):
            return -9.80665 * 28.9644 / (8314.32 * _reference_temperature(x))

        interior = math.fsum(
            (4 if i % 2 else 2) * gradient(lower + i * step)
            for i in range(1, n)
        )
        pieces.append(step / 3 * (gradient(lower) + interior + gradient(upper)))
    return math.fsum(pieces)


def test_hydrostatic_oracle_refinement_and_full_range():
    for h in range(0, 47_001, 500):
        coarse = _hydrostatic_log_ratio(h, 100)
        fine = _hydrostatic_log_ratio(h, 50)
        assert abs(coarse - fine) < 2e-11
        state = ussa1976_state(h, altitude_kind="geopotential")
        assert state.pressure_pa == pytest.approx(101325 * math.exp(fine), rel=1e-9)
        assert state.temperature_k == pytest.approx(_reference_temperature(h), abs=1e-10)
        assert state.density_kg_m3 > 0


@pytest.mark.parametrize("h,t", [(11_000, 216.65), (20_000, 216.65), (32_000, 228.65)])
def test_layer_continuity(h, t):
    at = ussa1976_state(h, altitude_kind="geopotential")
    assert at.temperature_k == pytest.approx(t, abs=1e-10)
    for offset in (-1e-4, 1e-4):
        near = ussa1976_state(h + offset, altitude_kind="geopotential")
        assert near.temperature_k == pytest.approx(at.temperature_k, rel=0, abs=7e-7)
        assert near.pressure_pa == pytest.approx(at.pressure_pa, rel=2e-8)


def test_legacy_troposphere_agreement_and_refusals_unchanged():
    for h in range(0, 11_001, 100):
        pressure, temperature = isa_troposphere(h)
        state = ussa1976_state(h, altitude_kind="geopotential")
        # v2 pins 1e-4: legacy R_air=287.05 differs from R*/M0.
        assert state.pressure_pa == pytest.approx(pressure, rel=1e-4)
        assert state.temperature_k == temperature
    assert isa_troposphere(0) == (101325.0, 288.15)
    for h in (-1, 11_001, 20_000, 47_000):
        with pytest.raises(ValueError, match="0..11000 m only"):
            isa_troposphere(h)
        with pytest.raises(ValueError, match="0..11000 m only"):
            check_altitude_pressure_consistency(h, 1000.0, 1e-3)


@pytest.mark.parametrize("h", [0, 11_000, 20_000, 25_000, 32_000, 47_000])
def test_declared_altitude_conversion_and_roundtrip(h):
    # USSA-1976 eqs. 18/19, r0 from doc p. 8, not the older PDAS convention.
    z = 6_356_766.0 * h / (6_356_766.0 - h)
    potential = ussa1976_state(h, altitude_kind="geopotential")
    geometric = ussa1976_state(z, altitude_kind="geometric")
    assert potential.geometric_altitude_m == pytest.approx(z, rel=2e-15)
    assert geometric.geopotential_altitude_m == pytest.approx(h, abs=1e-10)
    assert geometric.pressure_pa == pytest.approx(potential.pressure_pa, rel=2e-13)
    assert geometric.temperature_k == pytest.approx(potential.temperature_k, abs=1e-10)
    if h:
        different = ussa1976_state(h, altitude_kind="geometric")
        assert different.pressure_pa > potential.pressure_pa


@pytest.mark.parametrize("h", [-1, 47_001, math.inf, -math.inf, math.nan, 10**1000])
def test_refuses_invalid_geopotential_height(h):
    with pytest.raises(ValueError, match="0..47000 geopotential m only"):
        ussa1976_state(h, altitude_kind="geopotential")


def test_strict_geometric_upper_boundary():
    z_max = 6_356_766.0 * 47_000 / (6_356_766.0 - 47_000)
    assert ussa1976_state(z_max, altitude_kind="geometric").temperature_k == pytest.approx(270.65)
    for z in (-1, math.nextafter(z_max, math.inf), math.inf, math.nan):
        with pytest.raises(ValueError):
            ussa1976_state(z, altitude_kind="geometric")


@pytest.mark.parametrize("value", [True, False, None, "20000", [], {}])
def test_refuses_non_numeric_height(value):
    with pytest.raises(TypeError):
        ussa1976_state(value, altitude_kind="geopotential")


def test_requires_explicit_known_altitude_convention():
    with pytest.raises(TypeError):
        ussa1976_state(20_000)
    for kind in (None, "", "pressure", "MSL", True, []):
        with pytest.raises(ValueError, match="altitude_kind"):
            ussa1976_state(20_000, altitude_kind=kind)


def test_derived_properties_units_and_provenance():
    for h in (0, 20_000, 32_000, 47_000):
        state = ussa1976_state(h, altitude_kind="geopotential")
        # Eq. 1 ideal-gas closure; eq. 50 small-perturbation sound speed;
        # eq. 51 uses beta directly, not the legacy mu_ref normalization.
        assert state.density_kg_m3 * (8314.32 / 28.9644) * state.temperature_k == pytest.approx(
            state.pressure_pa, rel=5e-15)
        assert state.speed_of_sound_m_s**2 == pytest.approx(
            1.4 * 8314.32 / 28.9644 * state.temperature_k, rel=5e-15)
        assert state.dynamic_viscosity_pa_s == pytest.approx(
            1.458e-6 * math.sqrt(state.temperature_k) / (1 + 110.4 / state.temperature_k), rel=5e-15)
        assert state.source == "DERIVED_FROM_USSA_1976_NOT_MEASURED"
    with pytest.raises(FrozenInstanceError):
        state.pressure_pa = 0


def test_upper_layer_end_and_monotone_pressure():
    previous = math.inf
    for h in range(0, 47_001, 100):
        state = ussa1976_state(h, altitude_kind="geopotential")
        assert 0 < state.pressure_pa < previous
        previous = state.pressure_pa
    assert ussa1976_state(47_000, altitude_kind="geopotential").temperature_k == pytest.approx(270.65)
