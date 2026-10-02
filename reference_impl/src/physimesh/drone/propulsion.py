"""Momentum theory, propeller coefficients, measured rotor maps.

Implements [M-E09], [M-E10], [M-E15], [M-E16]; map rules [M§7].
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np


class Unavailable:
    """Returned instead of a number when a quantity is undefined (e.g. n = 0)."""

    def __init__(self, reason: str):
        self.reason = reason

    def __repr__(self) -> str:
        return f"Unavailable({self.reason!r})"


@dataclass(frozen=True)
class IdealHover:
    disk_area_m2: float
    induced_velocity_m_s: float
    ideal_power_w: float
    disk_loading_n_m2: float


def ideal_hover(thrust_n: float, radius_m: float, rho: float) -> IdealHover:
    """Isolated ideal rotor in hover; a lower bound on power [M-E09]."""
    if thrust_n < 0 or radius_m <= 0 or rho <= 0:
        raise ValueError("need thrust >= 0, radius > 0, rho > 0")
    a = math.pi * radius_m ** 2
    vi = math.sqrt(thrust_n / (2.0 * rho * a))
    return IdealHover(a, vi, thrust_n * vi, thrust_n / a)


@dataclass(frozen=True)
class FigureOfMerit:
    value: float
    flags: List[str]


def figure_of_merit(ideal_power_w: float, q_shaft_nm: float, omega_rad_s: float) -> FigureOfMerit:
    """FM = P_ideal / (Q Omega). Isolated-hover only [M-E10]. FM > 1 is impossible."""
    p_shaft = q_shaft_nm * omega_rad_s
    if p_shaft <= 0:
        raise ValueError("shaft power must be positive for hover FM")
    fm = ideal_power_w / p_shaft
    flags = ["physically_inconsistent_fm_gt_1"] if fm > 1.0 else []
    return FigureOfMerit(fm, flags)


@dataclass(frozen=True)
class Coefficients:
    n_rev_s: float
    ct: float
    cq: float
    cp: float
    convention: str = "propeller_rho_n2_D4"


def propeller_coefficients(thrust_n: float, torque_nm: float, rpm: float, diameter_m: float,
                           rho: float):
    """C_T = T/(rho n^2 D^4), C_Q = Q/(rho n^2 D^5), C_P = 2 pi C_Q [M-E15].
    At zero RPM the coefficients are undefined -> Unavailable [M§7]."""
    n = rpm / 60.0
    if n == 0.0:
        return Unavailable("coefficients undefined at zero RPM")
    ct = thrust_n / (rho * n ** 2 * diameter_m ** 4)
    cq = torque_nm / (rho * n ** 2 * diameter_m ** 5)
    p = torque_nm * 2.0 * math.pi * n
    cp = p / (rho * n ** 3 * diameter_m ** 5)
    return Coefficients(n, ct, cq, cp)


def advance_ratio_and_efficiency(v_axial: float, rpm: float, diameter_m: float,
                                 thrust_n: float, p_shaft_w: float):
    """J = V/(nD), eta_p = T V / P. eta_p -> 0 in hover is NOT zero capability [M-E16]."""
    n = rpm / 60.0
    if n == 0.0:
        return Unavailable("J undefined at zero RPM"), Unavailable("eta undefined at zero RPM")
    j = v_axial / (n * diameter_m)
    eta = thrust_n * v_axial / p_shaft_w if p_shaft_w > 0 else Unavailable("P_shaft <= 0")
    return j, eta


@dataclass
class RotorMap:
    """Measured map: interpolation only inside the tested envelope [M§7]."""
    rpm: np.ndarray                 # 1-D increasing
    v_axial_m_s: np.ndarray         # 1-D increasing
    thrust_n: np.ndarray            # shape (len(rpm), len(v_axial))
    torque_nm: np.ndarray           # signed per torque_sign_convention
    rho_test: float
    torque_sign_convention: str     # "aero_resisting" | "motor_shaft_positive"
    power_kind: str                 # "shaft" | "electrical"
    metadata: Dict[str, str] = field(default_factory=dict)   # fixture, pitch, thermal state, uncertainty

    def lookup(self, rpm: float, v_axial: float):
        from scipy.interpolate import RegularGridInterpolator
        if not (self.rpm[0] <= rpm <= self.rpm[-1] and
                self.v_axial_m_s[0] <= v_axial <= self.v_axial_m_s[-1]):
            return Unavailable("outside tested envelope; extrapolation refused")
        pt = np.array([[rpm, v_axial]])
        t = RegularGridInterpolator((self.rpm, self.v_axial_m_s), self.thrust_n)(pt)[0]
        q = RegularGridInterpolator((self.rpm, self.v_axial_m_s), self.torque_nm)(pt)[0]
        return float(t), float(q)
