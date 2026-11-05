"""Bounded COESA-1976 atmosphere, independent of aircraft feasibility.

Sources: https://www.pdas.com/atmosdef.html (layers and base conditions),
https://www.pdas.com/hydro.pdf (hydrostatic equations, altitude conversion).
Input convention is mandatory. This additive module does not change the legacy
isa_troposphere helper or wire a new model into any existing route implicitly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

AltitudeKind = Literal["geometric", "geopotential"]
MODEL_ID = "coesa1976.lower-atmosphere.0-30km.v1"
R_AIR = 8314.32 / 28.9644  # J/(kg K), source molecular weight and gas constant
G0 = 9.80665  # m/s2
EARTH_RADIUS_M = 6_356_750.0  # hydro.pdf convention, not a terrain radius
MAX_INPUT_ALTITUDE_M = 30_000.0
# Layer boundaries are geopotential metres; gradients are K/m.
LAYERS = ((0.0, 11_000.0, -0.0065),
          (11_000.0, 20_000.0, 0.0),
          (20_000.0, 32_000.0, 0.001))


@dataclass(frozen=True)
class StandardAtmosphereState:
    input_altitude_m: float
    altitude_kind: AltitudeKind
    geopotential_altitude_m: float
    pressure_pa: float
    temperature_k: float
    density_kg_m3: float
    model_id: str = MODEL_ID
    evidence_status: str = "REFERENCE_MODEL_NOT_AIRCRAFT_VALIDATION"


def _advance(p0: float, t0: float, dh: float, lapse: float) -> tuple[float, float]:
    temperature = t0 + lapse * dh
    if lapse == 0.0:
        pressure = p0 * math.exp(-G0 * dh / (R_AIR * t0))
    else:
        pressure = p0 * (temperature / t0) ** (-G0 / (R_AIR * lapse))
    return pressure, temperature


def standard_atmosphere(altitude_m: float, *,
                        altitude_kind: AltitudeKind) -> StandardAtmosphereState:
    """Return absolute p, T, rho for standard dry air, input 0..30,000 m.

    This is a reference atmosphere, not local weather or a pressure-altitude
    inversion. Unknown conventions, nonfinite values and out-of-range requests
    fail rather than extrapolate. No numerical tolerance is an aircraft limit.
    """
    if altitude_kind not in ("geometric", "geopotential"):
        raise ValueError("altitude_kind must be geometric or geopotential")
    if isinstance(altitude_m, bool) or not isinstance(altitude_m, (int, float)):
        raise TypeError("altitude_m must be a finite SI number")
    altitude = float(altitude_m)
    if not math.isfinite(altitude) or not 0.0 <= altitude <= MAX_INPUT_ALTITUDE_M:
        raise ValueError("standard_atmosphere input valid only for 0..30000 m")
    h = (EARTH_RADIUS_M * altitude / (EARTH_RADIUS_M + altitude)
         if altitude_kind == "geometric" else altitude)
    pressure, temperature = 101325.0, 288.15
    for bottom, top, lapse in LAYERS:
        stop = min(h, top)
        pressure, temperature = _advance(pressure, temperature, stop - bottom, lapse)
        if h <= top:
            break
    return StandardAtmosphereState(
        altitude, altitude_kind, h, pressure, temperature,
        pressure / (R_AIR * temperature),
    )
