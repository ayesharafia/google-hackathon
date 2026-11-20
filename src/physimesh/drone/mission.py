"""Coupled mass-energy screening. Implements [M-E46], [M-E47] iterated with [M-E01].

Battery mass changes thrust and power, so sizing needs a fixed-point iteration,
not one pass [M§17]. Screening only: power-rate limits, thermal derating,
voltage sag, ageing and structure can demand more mass.
"""
from __future__ import annotations

import math
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

WH_TO_J = 3600.0


@dataclass
class MissionResult:
    status: str                    # converged | diverged | max_iterations
    iterations: int
    total_mass_kg: float
    battery_mass_kg: float
    electrical_power_w: float
    mission_energy_wh: float
    history_kg: list[float] = field(default_factory=list)


def electrical_power(shaft_powers_w: list[float], eta_motor: list[float], eta_inverter: list[float], eta_drive: list[float], p_aux_w: float) -> float:
    """Power in W, dimensionless efficiencies: sum P_shaft,i/(eta_m eta_inv eta_drv) + P_aux [M-E46]."""
    if not math.isfinite(p_aux_w) or p_aux_w < 0:
        raise ValueError('auxiliary power must be finite and nonnegative')
    total = p_aux_w
    for p, em, ei, ed in zip(shaft_powers_w, eta_motor, eta_inverter, eta_drive, strict=True):
        if not math.isfinite(p) or p < 0 or not all(math.isfinite(eta) and 0 < eta <= 1 for eta in (em, ei, ed)):
            raise ValueError('shaft power and efficiencies are invalid')
        if p == 0:
            continue
        if em*ei*ed < sys.float_info.min:
            smallest, middle, largest = sorted((em, ei, ed))
            total += p/smallest/middle/largest
        else:
            total += p/(em*ei*ed)
    if not math.isfinite(total):
        raise ValueError('electrical power overflowed')
    return total


def size_battery(mass_without_battery_kg: float, p_elec_of_mass: Callable[[float], float], *,
                 duration_s: float, e_pack_wh_per_kg: float, f_usable: float,
                 reserve_fraction: float, rel_tol: float, max_iterations: int,
                 divergence_mass_kg: float) -> MissionResult:
    """m_batt = (E_mission + E_reserve) / (e_pack f_usable)  [M-E47], constant-power segment.

    Numerical support requires finite normal converted pack and usable capacities,
    mission joules, reserved joules, battery mass, mission Wh and total mass.
    Zero power permits zero energies and battery mass; total mass may be zero
    only when base and battery masses are zero. Positive battery mass must
    increase the base mass. Unsupported results raise ValueError.
    """
    if not math.isfinite(mass_without_battery_kg) or mass_without_battery_kg < 0:
        raise ValueError('finite nonnegative mass without battery required')
    if not math.isfinite(reserve_fraction) or reserve_fraction < 0:
        raise ValueError('finite nonnegative reserve fraction required')
    if (not math.isfinite(rel_tol) or rel_tol <= 0 or not isinstance(max_iterations, int)
            or isinstance(max_iterations, bool) or max_iterations < 1
            or not math.isfinite(divergence_mass_kg) or divergence_mass_kg <= mass_without_battery_kg):
        raise ValueError('invalid iteration controls')
    if f_usable is not None and f_usable > 1:
        raise ValueError('usable fraction cannot exceed one')
    for name, v in (("duration_s", duration_s), ("e_pack_wh_per_kg", e_pack_wh_per_kg),
                    ("f_usable", f_usable)):
        if v is None or not math.isfinite(v) or not v > 0:
            raise ValueError(f"{name} must be supplied and > 0")
    e_pack = e_pack_wh_per_kg * WH_TO_J
    if not math.isfinite(e_pack) or e_pack < sys.float_info.min:
        raise ValueError('converted pack capacity outside numerical support')
    usable_capacity = e_pack * f_usable
    if not math.isfinite(usable_capacity) or usable_capacity < sys.float_info.min:
        raise ValueError('usable capacity outside numerical support')
    m = mass_without_battery_kg
    hist: list[float] = []
    for it in range(1, max_iterations + 1):
        p = p_elec_of_mass(m)
        if not math.isfinite(p) or p < 0:
            raise ValueError('power model must return finite nonnegative watts')
        e = p * duration_s
        if not math.isfinite(e) or (p > 0 and e < sys.float_info.min):
            raise ValueError('mission joules outside numerical support')
        reserved_j = e * (1.0 + reserve_fraction)
        if not math.isfinite(reserved_j) or (e > 0 and reserved_j < sys.float_info.min):
            raise ValueError('reserved joules outside numerical support')
        mb = reserved_j / usable_capacity
        if not math.isfinite(mb) or (reserved_j > 0 and mb < sys.float_info.min):
            raise ValueError('battery mass outside numerical support')
        mission_wh = e / WH_TO_J
        if not math.isfinite(mission_wh) or (e > 0 and mission_wh < sys.float_info.min):
            raise ValueError('mission Wh outside numerical support')
        m_new = mass_without_battery_kg + mb
        if (not math.isfinite(m_new)
                or (0 < m_new < sys.float_info.min)
                or (mb > 0 and m_new == mass_without_battery_kg)):
            raise ValueError('total mass outside numerical support')
        hist.append(m_new)
        if m_new > divergence_mass_kg:
            return MissionResult("diverged", it, m_new, mb, p, mission_wh, hist)
        if abs(m_new - m) <= rel_tol * m_new:
            return MissionResult("converged", it, m_new, mb, p, mission_wh, hist)
        m = m_new
    return MissionResult("max_iterations", max_iterations, m_new, mb, p, mission_wh, hist)
