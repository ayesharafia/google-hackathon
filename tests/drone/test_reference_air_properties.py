"""80-digit Decimal formula oracle, guards, identities and result isolation.

Oracle constants are independent decimal literals, not production imports.
The 5e-14 relative tolerance covers binary64 rounding and accepted-kernel layer
propagation at tested points only; it is not a universal accuracy guarantee.
"""

import importlib
import math
from dataclasses import FrozenInstanceError, asdict, replace
from decimal import Decimal, localcontext

import pytest

from physimesh.drone.reference_air_properties import reference_air_properties
from physimesh.drone.standard_atmosphere import standard_atmosphere

module = importlib.import_module("physimesh.drone.reference_air_properties")
D = Decimal
KINDS = ("geometric", "geopotential")
REL = 5e-14


def decimal_oracle(altitude, kind):
    """Integrate layers and evaluate the stated formulas at 80 decimal digits."""
    with localcontext() as context:
        context.prec = 80
        x = D(altitude)  # Exact binary input for floats, exact integer otherwise.
        radius, g0 = D("6356750"), D("9.80665")
        gas = D("8314.32") / D("28.9644")
        h = radius * x / (radius + x) if kind == "geometric" else x
        z = x if kind == "geometric" else radius * h / (radius - h)
        temperature, pressure = D("288.15"), D("101325")
        for bottom, top, lapse in (("0", "11000", "-0.0065"),
                                   ("11000", "20000", "0"),
                                   ("20000", "32000", "0.001")):
            dh, lapse = min(h, D(top)) - D(bottom), D(lapse)
            next_t = temperature + lapse * dh
            if lapse:
                pressure *= ((next_t / temperature).ln() * (-g0 / (gas * lapse))).exp()
            else:
                pressure *= (-g0 * dh / (gas * temperature)).exp()
            temperature = next_t
            if h <= D(top):
                break
        ratio = temperature / D("273.15")
        # sqrt(ratio**3) avoids reproducing the production float **1.5.
        mu = D("0.00001716") * D("383.48333") / (temperature + D("110.33333")) * (ratio**3).sqrt()
        sound = (D("1.4") * gas * temperature).sqrt()
        gravity = g0 * (radius / (radius + z))**2
        return {"geopotential_altitude_m": h, "geometric_altitude_m": z,
                "temperature_k": temperature, "pressure_pa": pressure,
                "density_kg_m3": pressure / (gas * temperature),
                "dynamic_viscosity_pa_s": mu, "speed_of_sound_m_s": sound, "gravity_m_s2": gravity}


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("altitude", [0, 1, 1234.5, 10000, 10999.999, 11000, 11000.001,
                                      19999.999, 20000, 20000.001, 29999.999, 30000])
def test_independent_decimal_oracle(altitude, kind):
    result = reference_air_properties(altitude_m=altitude, altitude_kind=kind)
    expected = decimal_oracle(altitude, kind)
    for name, value in expected.items():
        actual = getattr(result, name) if hasattr(result, name) else getattr(result.state, name)
        assert actual == pytest.approx(float(value), rel=REL, abs=1e-12 if name.endswith("altitude_m") else 0)


@pytest.mark.parametrize("kind", KINDS)
def test_rounded_sea_level_reference(kind):
    result = reference_air_properties(altitude_m=0, altitude_kind=kind)
    # Cambridge display increments: 0.1 m/s and 0.001e-5 Pa s.
    assert result.speed_of_sound_m_s == pytest.approx(340.3, abs=0.05, rel=0)
    assert result.dynamic_viscosity_pa_s == pytest.approx(1.789e-5, abs=5e-9, rel=0)
    assert result.gravity_m_s2 == 9.80665


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("boundary_h", [11000, 20000])
def test_layer_boundary_continuity(boundary_h, kind):
    # Centre geometric tests on the converted geopotential layer boundary.
    with localcontext() as context:
        context.prec = 80
        radius, h = D("6356750"), D(boundary_h)
        centre = float(radius * h / (radius - h)) if kind == "geometric" else float(h)
    values = [reference_air_properties(altitude_m=centre + offset, altitude_kind=kind)
              for offset in (-0.001, 0, 0.001)]
    for value in values:
        expected = decimal_oracle(value.state.input_altitude_m, kind)
        for name in ("dynamic_viscosity_pa_s", "speed_of_sound_m_s", "gravity_m_s2"):
            assert getattr(value, name) == pytest.approx(float(expected[name]), rel=REL)
    # A 2 mm span changes T by at most 1.3e-5 K and z by about 2 mm.
    for name in ("dynamic_viscosity_pa_s", "speed_of_sound_m_s", "gravity_m_s2"):
        assert abs(getattr(values[2], name) / getattr(values[0], name) - 1) < 1e-7


@pytest.mark.parametrize("kind", KINDS)
def test_upper_bound_one_sided_continuity_and_no_extrapolation(kind):
    edge = reference_air_properties(altitude_m=30000, altitude_kind=kind)
    below = reference_air_properties(altitude_m=29999.999, altitude_kind=kind)
    for name in ("dynamic_viscosity_pa_s", "speed_of_sound_m_s", "gravity_m_s2"):
        assert abs(getattr(edge, name) / getattr(below, name) - 1) < 1e-8
    with pytest.raises(ValueError):
        reference_air_properties(altitude_m=math.nextafter(30000.0, math.inf), altitude_kind=kind)
    if kind == "geopotential":
        assert edge.geometric_altitude_m > 30000  # Bound applies to input.


class IntSubclass(int):
    def __float__(self):
        raise AssertionError("must reject before conversion")


class FloatSubclass(float):
    def __float__(self):
        raise AssertionError("must reject before conversion")


class StringSubclass(str):
    pass


class FloatLike:
    def __float__(self):
        raise AssertionError("must reject before conversion")


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("value", [True, False, IntSubclass(1), FloatSubclass(1), FloatLike(),
                                   None, "1", D("1"), 1j, [], {}, object()])
def test_altitude_type_guards_before_upstream(value, kind, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid request reached upstream")
    monkeypatch.setattr(module, "standard_atmosphere", forbidden)
    with pytest.raises(TypeError):
        reference_air_properties(altitude_m=value, altitude_kind=kind)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("value", [-0.001, 30000.001, math.nan, math.inf, -math.inf,
                                   10**10000, -(10**10000)], ids=["negative", "high", "nan", "inf", "-inf", "huge", "-huge"])
def test_altitude_value_guards_before_upstream(value, kind, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid request reached upstream")
    monkeypatch.setattr(module, "standard_atmosphere", forbidden)
    with pytest.raises(ValueError):
        reference_air_properties(altitude_m=value, altitude_kind=kind)


@pytest.mark.parametrize("kind", ["", "MSL", "pressure", None, True, 1, [], {}, StringSubclass("geometric")])
def test_kind_guard(kind):
    with pytest.raises(ValueError):
        reference_air_properties(altitude_m=0, altitude_kind=kind)


@pytest.mark.parametrize("args,kwargs", [((0,), {"altitude_kind": "geometric"}),
                                        ((), {"altitude_m": 0}),
                                        ((), {"altitude_kind": "geometric"}),
                                        ((), {}), ((0, "geometric"), {}),
                                        ((), {"altitude_m": 0, "altitude_kind": "geometric", "extra": 1})])
def test_argument_count_and_keyword_contract(args, kwargs):
    with pytest.raises(TypeError):
        reference_air_properties(*args, **kwargs)


@pytest.mark.parametrize("field", ["input_altitude_m", "geopotential_altitude_m", "pressure_pa",
                                   "temperature_k", "density_kg_m3"])
@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, True, "1", None,
                                     IntSubclass(1), FloatSubclass(1), 10**10000],
                         ids=["nan", "inf", "-inf", "bool", "str", "none", "int-subclass", "float-subclass", "huge"])
def test_invalid_upstream_numeric_fields(field, invalid, monkeypatch):
    state = replace(standard_atmosphere(1000, altitude_kind="geometric"), **{field: invalid})
    monkeypatch.setattr(module, "standard_atmosphere", lambda *args, **kwargs: state)
    with pytest.raises(ValueError, match="upstream"):
        reference_air_properties(altitude_m=1000, altitude_kind="geometric")


@pytest.mark.parametrize("changes", [
    {"temperature_k": 0.0}, {"temperature_k": -1.0}, {"pressure_pa": 0.0},
    {"pressure_pa": -1.0}, {"density_kg_m3": 0.0}, {"density_kg_m3": -1.0},
    {"input_altitude_m": 2.0}, {"geopotential_altitude_m": -1.0},
    {"geopotential_altitude_m": 30001.0}, {"geopotential_altitude_m": 1.0},
    {"altitude_kind": "geopotential"}, {"model_id": "other"},
    {"evidence_status": "VALIDATED"}, {"temperature_k": 1e308},
])
def test_invalid_upstream_state_and_nonfinite_derived_values(changes, monkeypatch):
    state = replace(standard_atmosphere(1000, altitude_kind="geometric"), **changes)
    monkeypatch.setattr(module, "standard_atmosphere", lambda *args, **kwargs: state)
    with pytest.raises(ValueError):
        reference_air_properties(altitude_m=1000, altitude_kind="geometric")


@pytest.mark.parametrize("state", [None, {}, object()])
def test_invalid_upstream_state_type(state, monkeypatch):
    monkeypatch.setattr(module, "standard_atmosphere", lambda *args, **kwargs: state)
    with pytest.raises(ValueError, match="upstream"):
        reference_air_properties(altitude_m=0, altitude_kind="geometric")


def test_original_state_retained_without_recomputation(monkeypatch):
    state = standard_atmosphere(1234, altitude_kind="geometric")
    calls = []

    def upstream(altitude, *, altitude_kind):
        calls.append((altitude, altitude_kind))
        return state

    monkeypatch.setattr(module, "standard_atmosphere", upstream)
    result = reference_air_properties(altitude_m=1234, altitude_kind="geometric")
    assert result.state is state
    assert calls == [(1234.0, "geometric")]


@pytest.mark.parametrize("kind", KINDS)
def test_identities_and_finite_positive_values(kind):
    previous_g = math.inf
    for altitude in range(0, 30001, 500):
        result = reference_air_properties(altitude_m=altitude, altitude_kind=kind)
        assert result.state == standard_atmosphere(altitude, altitude_kind=kind)
        assert result.speed_of_sound_m_s**2 == pytest.approx(
            1.4 * result.state.pressure_pa / result.state.density_kg_m3, rel=2e-15)
        assert result.gravity_m_s2 < previous_g
        previous_g = result.gravity_m_s2
        for value in (result.dynamic_viscosity_pa_s, result.speed_of_sound_m_s, result.gravity_m_s2):
            assert type(value) is float and math.isfinite(value) and value > 0
        # g/G0 = (1-H/E)^2 is an independent rearrangement of the z equation.
        assert result.gravity_m_s2 / 9.80665 == pytest.approx(
            (1 - result.state.geopotential_altitude_m / 6356750)**2, rel=2e-15)


@pytest.mark.parametrize("h", [0, 11000, 20000, 29000])
def test_equivalent_altitude_kinds(h):
    with localcontext() as context:
        context.prec = 80
        z = float(D("6356750") * D(h) / (D("6356750") - D(h)))
    geometric = reference_air_properties(altitude_m=z, altitude_kind="geometric")
    potential = reference_air_properties(altitude_m=h, altitude_kind="geopotential")
    for name in ("geometric_altitude_m", "dynamic_viscosity_pa_s", "speed_of_sound_m_s", "gravity_m_s2"):
        assert getattr(geometric, name) == pytest.approx(getattr(potential, name), rel=REL)


def test_return_isolation_frozen_metadata_and_convention():
    first = reference_air_properties(altitude_m=0, altitude_kind="geometric")
    second = reference_air_properties(altitude_m=0, altitude_kind="geometric")
    assert first == second and first is not second and first.state is not second.state
    with pytest.raises(FrozenInstanceError):
        first.gravity_m_s2 = 1
    with pytest.raises(FrozenInstanceError):
        first.state.temperature_k = 1
    copy = asdict(first)
    copy["state"]["temperature_k"] = 1
    copy["physical_qualification"] = "VALIDATED"
    assert first.state.temperature_k == second.state.temperature_k == 288.15
    assert first.physical_qualification == first.numerical_qualification == "NOT_ESTABLISHED"
    assert "nasa-cape-sutherlandmks" in first.model_id
    assert first.viscosity_model == "NASA CAPE SutherlandMKS (mu0=1.716e-5 Pa s; T0=273.15 K; C=110.33333 K)"
    assert "gamma=1.4" in first.sound_model
    assert "6356750 m" in first.gravity_model
    # Deliberately distinct from the COESA beta/S convention, even at sea level.
    with localcontext() as context:
        context.prec = 80
        temperature = D("288.15")
        coesa_mu = D("1.458e-6") * (temperature**3).sqrt() / (temperature + D("110.4"))
    assert abs(first.dynamic_viscosity_pa_s / float(coesa_mu) - 1) > 1e-5
