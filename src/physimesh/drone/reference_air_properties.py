"""Independent dry-air reference properties; no registry, API or DAG wiring.

Viscosity uses NASA CAPE SutherlandMKS, not exact COESA-1976 transport.
See docs/reference-air-properties.md for sources, constants and limitations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from physimesh.drone.standard_atmosphere import (
    EARTH_RADIUS_M,
    G0,
    MAX_INPUT_ALTITUDE_M,
    R_AIR,
    AltitudeKind,
    StandardAtmosphereState,
    standard_atmosphere,
)
from physimesh.drone.standard_atmosphere import (
    MODEL_ID as ATMOSPHERE_MODEL_ID,
)

MODEL_ID = "reference-dry-air.nasa-cape-sutherlandmks.0-30km.v1"
VISCOSITY_MODEL = "NASA CAPE SutherlandMKS (mu0=1.716e-5 Pa s; T0=273.15 K; C=110.33333 K)"
SOUND_MODEL = "dry ideal gas (gamma=1.4; accepted atmosphere R_AIR)"
GRAVITY_MODEL = "PDAS inverse-square (G0=9.80665 m/s^2; E=6356750 m)"
SUTHERLAND_MU0_PA_S = 1.716e-5
SUTHERLAND_T0_K = 273.15
SUTHERLAND_C_K = 110.33333
GAMMA_DRY_AIR = 1.4


@dataclass(frozen=True)
class ReferenceAirProperties:
    """SI values plus the original frozen atmosphere state and model metadata."""

    state: StandardAtmosphereState
    geometric_altitude_m: float
    dynamic_viscosity_pa_s: float
    speed_of_sound_m_s: float
    gravity_m_s2: float
    model_id: str = MODEL_ID
    viscosity_model: str = VISCOSITY_MODEL
    sound_model: str = SOUND_MODEL
    gravity_model: str = GRAVITY_MODEL
    physical_qualification: str = "NOT_ESTABLISHED"
    numerical_qualification: str = "NOT_ESTABLISHED"


def _validate_state(state: StandardAtmosphereState, altitude: float, kind: AltitudeKind) -> None:
    """Fail closed on malformed upstream output without changing its kernel."""
    if type(state) is not StandardAtmosphereState:
        raise ValueError("invalid upstream atmosphere state type")
    for name in ("input_altitude_m", "geopotential_altitude_m", "pressure_pa",
                 "temperature_k", "density_kg_m3"):
        value = getattr(state, name)
        # The accepted kernel returns builtin floats. Check type before math.
        if type(value) is not float or not math.isfinite(value):
            raise ValueError(f"invalid upstream atmosphere {name}")
    if (type(state.altitude_kind) is not str or state.altitude_kind != kind
            or state.input_altitude_m != altitude
            or not 0.0 <= state.geopotential_altitude_m <= MAX_INPUT_ALTITUDE_M
            or state.pressure_pa <= 0.0 or state.temperature_k <= 0.0
            or state.density_kg_m3 <= 0.0
            or type(state.model_id) is not str or state.model_id != ATMOSPHERE_MODEL_ID
            or type(state.evidence_status) is not str
            or state.evidence_status != "REFERENCE_MODEL_NOT_AIRCRAFT_VALIDATION"):
        raise ValueError("invalid upstream atmosphere state")
    expected_h = (EARTH_RADIUS_M * altitude / (EARTH_RADIUS_M + altitude)
                  if kind == "geometric" else altitude)
    if state.geopotential_altitude_m != expected_h:
        raise ValueError("upstream atmosphere altitude does not match request")


def reference_air_properties(*, altitude_m: float, altitude_kind: AltitudeKind) -> ReferenceAirProperties:
    """Return bounded reference mu [Pa s], a [m/s], g [m/s^2].

    Both arguments are mandatory keywords. Only exact builtin int/float altitude
    and exact builtin str convention are accepted. Input is 0..30000 m in the
    requested convention; this is not a bound on converted geometric altitude.
    Qualification remains NOT_ESTABLISHED; numerical tests are formula checks.
    """
    if type(altitude_kind) is not str or altitude_kind not in ("geometric", "geopotential"):
        raise ValueError("altitude_kind must be geometric or geopotential")
    if type(altitude_m) not in (int, float):
        raise TypeError("altitude_m must be a builtin int or float (excluding bool and subclasses)")
    # Range-check integers before conversion: even arbitrarily large ints fail
    # predictably, without an overflowing float conversion. NaN also fails here.
    if not 0 <= altitude_m <= MAX_INPUT_ALTITUDE_M:
        raise ValueError("altitude_m must be finite and in 0..30000 m")
    altitude = float(altitude_m)
    if not math.isfinite(altitude):
        raise ValueError("altitude_m must be finite and in 0..30000 m")
    state = standard_atmosphere(altitude, altitude_kind=altitude_kind)
    _validate_state(state, altitude, altitude_kind)
    z = (altitude if altitude_kind == "geometric" else
         EARTH_RADIUS_M * state.geopotential_altitude_m
         / (EARTH_RADIUS_M - state.geopotential_altitude_m))
    temperature = state.temperature_k
    try:
        mu = (SUTHERLAND_MU0_PA_S * (SUTHERLAND_T0_K + SUTHERLAND_C_K)
              / (temperature + SUTHERLAND_C_K) * (temperature / SUTHERLAND_T0_K) ** 1.5)
        sound = math.sqrt(GAMMA_DRY_AIR * R_AIR * temperature)
        gravity = G0 * (EARTH_RADIUS_M / (EARTH_RADIUS_M + z)) ** 2
    except (OverflowError, ZeroDivisionError) as exc:
        raise ValueError("invalid derived reference air properties") from exc
    if not math.isfinite(z) or z < 0 or any(
            not math.isfinite(value) or value <= 0 for value in (mu, sound, gravity)):
        raise ValueError("invalid derived reference air properties")
    return ReferenceAirProperties(state, z, mu, sound, gravity)
