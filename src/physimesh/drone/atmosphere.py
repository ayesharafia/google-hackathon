"""Atmosphere and local-flow screening. Implements [M-E03], [M-E04]."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .frames import MissingInput

R_AIR = 287.05          # J/(kg K) [M§4]
G0 = 9.80665            # m/s^2 [STD]
ISA_T0 = 288.15         # K [STD]
ISA_P0 = 101325.0       # Pa [STD]
ISA_LAPSE = 0.0065      # K/m, troposphere [STD]
ISA_TROPOPAUSE_M = 11000.0  # m [STD: ISA troposphere]


def sutherland_viscosity(t_k: float, mu_ref: float = 1.716e-5,
                         t_ref: float = 273.15, s: float = 110.4) -> float:
    """Sutherland law for air [STD]. Pa s."""
    return mu_ref * (t_k / t_ref) ** 1.5 * (t_ref + s) / (t_k + s)


@dataclass(frozen=True)
class Atmosphere:
    pressure_pa: float          # absolute
    temperature_k: float
    dynamic_viscosity_pa_s: float
    gamma: float
    source: str                 # provenance text, e.g. "ISA troposphere" or "measured 2026-..."
    viscosity_law: str | None

    @property
    def density(self) -> float:
        """Density in kg/m³: rho = p_abs / (R_air T) [M-E03]."""
        return self.pressure_pa / (R_AIR * self.temperature_k)

    @property
    def speed_of_sound(self) -> float:
        """Sound speed in m/s: a = sqrt(gamma R_air T) [M-E03]."""
        return math.sqrt(self.gamma * R_AIR * self.temperature_k)

    @property
    def kinematic_viscosity(self) -> float:
        """Kinematic viscosity in m²/s: nu = mu / rho [M-E03]."""
        return self.dynamic_viscosity_pa_s / self.density


def make_atmosphere(pressure_pa: float | None, temperature_k: float | None, *,
                    source: str, viscosity_pa_s: float | None = None,
                    viscosity_law: str | None = None, gamma: float = 1.4) -> Atmosphere:
    """Construct from absolute Pa, K and Pa s; gamma=1.4 ideal-air approximation [M§4]."""
    if pressure_pa is None:
        raise MissingInput("atmosphere.pressure_pa is null")
    if temperature_k is None:
        raise MissingInput("atmosphere.temperature_k is null")
    if not all(math.isfinite(v) and v > 0 for v in (pressure_pa, temperature_k, gamma)):
        raise ValueError("pressure must be absolute Pa > 0 and temperature Kelvin > 0")
    if (viscosity_pa_s is None) == (viscosity_law is None):
        raise MissingInput("supply exactly one of atmosphere.viscosity value or approved law")
    if viscosity_law is not None:
        if viscosity_law != "sutherland":
            raise ValueError(f"unapproved viscosity law {viscosity_law!r}")
        mu = sutherland_viscosity(temperature_k)
    else:
        mu = float(viscosity_pa_s)
    if not math.isfinite(mu) or mu <= 0:
        raise ValueError("dynamic viscosity must be finite Pa s > 0")
    return Atmosphere(float(pressure_pa), float(temperature_k), mu, gamma, source, viscosity_law)


def isa_troposphere(altitude_m: float) -> tuple[float, float]:
    """(pressure_pa, temperature_k) of the ISA troposphere, 0..11 km.

    ISA here uses R_air = 287.05 (manifest), so values differ from published ISA tables at ~1e-5 relative.
    """
    if not (0.0 <= altitude_m <= ISA_TROPOPAUSE_M):
        raise ValueError("isa_troposphere valid for 0..11000 m only")
    t = ISA_T0 - ISA_LAPSE * altitude_m
    p = ISA_P0 * (t / ISA_T0) ** (G0 / (ISA_LAPSE * R_AIR))
    return p, t


def check_altitude_pressure_consistency(altitude_m: float, pressure_pa: float,
                                        rel_tol: float) -> None:
    """Do not combine independent altitude and pressure inconsistently [M§4]."""
    if not math.isfinite(pressure_pa) or pressure_pa <= 0 or not math.isfinite(rel_tol) or rel_tol < 0:
        raise ValueError("pressure in Pa and dimensionless relative tolerance must be finite")
    p_isa, _ = isa_troposphere(altitude_m)
    if abs(pressure_pa - p_isa) > rel_tol * p_isa:
        raise ValueError(f"pressure {pressure_pa} Pa inconsistent with ISA at {altitude_m} m "
                         f"({p_isa:.1f} Pa); declare a non-standard atmosphere source")


def reynolds_chord(atm: Atmosphere, v_rel: float, chord_m: float) -> float:
    """Re_c = rho V_rel c / mu [M-E04]."""
    return atm.density * v_rel * chord_m / atm.dynamic_viscosity_pa_s


def local_mach(atm: Atmosphere, v_rel: float) -> float:
    """Dimensionless Mach number from speed v_rel in m/s [M-E04]."""
    return v_rel / atm.speed_of_sound


def tip_mach_screen(atm: Atmosphere, omega_rad_s: float, radius_m: float,
                    v_axial: float) -> float:
    """Axial-flight screening estimate only [M-E04], [M§4]."""
    return math.sqrt((omega_rad_s * radius_m) ** 2 + v_axial ** 2) / atm.speed_of_sound
