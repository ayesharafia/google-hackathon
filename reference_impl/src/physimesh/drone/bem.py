"""Blade element momentum for axial flight / hover (propeller convention).

Implements [M-E11]..[M-E14] with angular-momentum swirl and optional Prandtl tip
loss [M-E55] applied to the MOMENTUM side only (recorded, never applied twice).
Out of scope here: strong crossflow, vortex-ring descent, windmilling (negative
loading) -> stations are reported unconverged, never silently accepted [M§6].
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

import numpy as np


@dataclass(frozen=True)
class TabulatedPolar:
    """Cl, Cd versus alpha (deg). Outside the table -> refused (no extrapolation)."""
    alpha_deg: np.ndarray
    cl: np.ndarray
    cd: np.ndarray
    source: str

    def __call__(self, alpha_rad: float, re: float, mach: float):
        a = math.degrees(alpha_rad)
        if not (self.alpha_deg[0] <= a <= self.alpha_deg[-1]):
            return None
        return float(np.interp(a, self.alpha_deg, self.cl)), float(np.interp(a, self.alpha_deg, self.cd))


@dataclass(frozen=True)
class Blade:
    n_blades: int
    radius_m: float
    root_cutout_m: float
    r_def_m: np.ndarray        # definition stations
    chord_m: np.ndarray
    twist_deg: np.ndarray      # includes collective pitch state [M§11]


@dataclass(frozen=True)
class BemSettings:
    radial_stations: int        # manifest starting value 80
    rel_load_residual: float    # manifest starting value 1e-4
    max_iterations: int         # manifest starting value 200
    relaxation: float           # REQUIRED; manifest gives no default
    tip_loss: str               # "prandtl" | "none"


def prandtl_tip_factor(n_blades: int, radius_m: float, r_m: float, phi_rad: float) -> float:
    """F = (2/pi) acos(exp(-B (R - r) / (2 r sin phi))) [M-E55]."""
    s = math.sin(phi_rad)
    if s <= 0.0 or r_m >= radius_m:
        return 0.0 if r_m >= radius_m else 1.0
    f = n_blades * (radius_m - r_m) / (2.0 * r_m * s)
    return (2.0 / math.pi) * math.acos(math.exp(-f))


@dataclass
class Station:
    r_m: float
    dr_m: float
    converged: bool
    iterations: int
    reason: str
    vi_m_s: float = float("nan")
    vtheta_m_s: float = float("nan")
    phi_rad: float = float("nan")
    alpha_rad: float = float("nan")
    dT_dr: float = float("nan")      # N/m
    dQ_dr: float = float("nan")      # N m / m
    residual: float = float("nan")
    loss_factor: float = 1.0


@dataclass
class BemResult:
    thrust_n: float
    torque_nm: float                 # aerodynamic torque magnitude to be supplied by the shaft
    shaft_power_w: float
    stations: List[Station]
    accepted: bool
    status: str
    loss_applies_to: str = "momentum"
    notes: List[str] = field(default_factory=list)


def _lift_slope_per_rad(polar) -> float:
    """Lift-curve slope from the polar itself (central difference about 0 deg)."""
    lo, hi = polar(math.radians(-1.0), 0.0, 0.0), polar(math.radians(1.0), 0.0, 0.0)
    if lo is None or hi is None:
        raise ValueError("polar must cover -1..+1 deg to initialise BEM")
    return (hi[0] - lo[0]) / math.radians(2.0)


def initial_inflow(r, c, theta, blade, omega, v_a, cla) -> float:
    """Closed-form linear-aerodynamics BEMT inflow (no tip loss, no swirl), used ONLY
    as the iteration starting point [STD: Leishman, Principles of Helicopter
    Aerodynamics, BEMT for hover/climb]. Returns induced velocity vi (m/s)."""
    sigma = blade.n_blades * c / (math.pi * blade.radius_m)
    rbar = r / blade.radius_m
    lam_c = v_a / (omega * blade.radius_m)
    k = sigma * cla / 16.0 - lam_c / 2.0
    lam = math.sqrt(k * k + sigma * cla * theta * rbar / 8.0) - k
    return max(lam * omega * blade.radius_m - v_a, 0.0)


def _station(r, dr, c, theta, blade, omega, v_a, rho, mu, a_snd, polar, st: BemSettings,
             cla: float) -> Station:
    vi = initial_inflow(r, c, theta, blade, omega, v_a, cla)
    vt = 0.0
    scale = 0.5 * rho * (omega * r) ** 2 * c * blade.n_blades
    for it in range(1, st.max_iterations + 1):
        wa = v_a + vi
        wt = omega * r - vt
        w = math.hypot(wa, wt)
        phi = math.atan2(wa, wt)                                           # E11
        alpha = theta - phi
        pol = polar(alpha, rho * w * c / mu, w / a_snd)
        if pol is None:
            return Station(r, dr, False, it, "alpha_outside_polar", vi, vt, phi, alpha)
        cl, cd = pol
        dl = 0.5 * rho * w * w * c * cl                                    # E12 per unit span
        dd = 0.5 * rho * w * w * c * cd
        dT = blade.n_blades * (dl * math.cos(phi) - dd * math.sin(phi))    # E13
        dQ = blade.n_blades * r * (dl * math.sin(phi) + dd * math.cos(phi))
        F = prandtl_tip_factor(blade.n_blades, blade.radius_m, r, phi) if st.tip_loss == "prandtl" else 1.0
        if dT < 0.0:
            return Station(r, dr, False, it, "negative_loading_unsupported", vi, vt, phi, alpha, dT, dQ)
        if F <= 0.0:
            return Station(r, dr, False, it, "tip_factor_zero", vi, vt, phi, alpha, dT, dQ)
        dT_mom = 4.0 * math.pi * rho * r * F * (v_a + vi) * vi                # E14 (with loss)
        res = abs(dT - dT_mom) / max(abs(dT), 1e-12 * scale)
        vi_new = 0.5 * (-v_a + math.sqrt(v_a * v_a + dT / (math.pi * rho * r * F)))
        vt_new = dQ / (4.0 * math.pi * rho * r * r * F * (v_a + vi_new)) if (v_a + vi_new) > 0 else 0.0
        if res < st.rel_load_residual and it > 1:
            return Station(r, dr, True, it, "converged", vi, vt, phi, alpha, dT, dQ, res, F)
        vi = (1.0 - st.relaxation) * vi + st.relaxation * vi_new
        vt = (1.0 - st.relaxation) * vt + st.relaxation * vt_new
    return Station(r, dr, False, st.max_iterations, "max_iterations", vi, vt, phi, alpha, dT, dQ, res, F)


def solve_rotor(blade: Blade, rpm: float, v_axial: float, rho: float, mu: float, a_sound: float,
                polar: Callable, settings: BemSettings) -> BemResult:
    if rpm == 0:
        return BemResult(float("nan"), float("nan"), float("nan"), [], False,
                         "unavailable_zero_rpm")
    if rpm < 0:
        raise ValueError("pass |RPM|; handedness is applied by the rotor frame")
    if not 0.0 < settings.relaxation <= 1.0:
        raise ValueError("relaxation must be in (0, 1]")
    omega = rpm * 2.0 * math.pi / 60.0
    edges = np.linspace(blade.root_cutout_m, blade.radius_m, settings.radial_stations + 1)
    mids = 0.5 * (edges[1:] + edges[:-1])
    drs = np.diff(edges)
    chord = np.interp(mids, blade.r_def_m, blade.chord_m)
    theta = np.radians(np.interp(mids, blade.r_def_m, blade.twist_deg))
    cla = _lift_slope_per_rad(polar)
    stations = [_station(float(r), float(dr), float(c), float(th), blade, omega, v_axial,
                         rho, mu, a_sound, polar, settings, cla)
                for r, dr, c, th in zip(mids, drs, chord, theta)]
    ok = all(s.converged for s in stations)
    T = float(sum(s.dT_dr * s.dr_m for s in stations if s.converged))
    Q = float(sum(s.dQ_dr * s.dr_m for s in stations if s.converged))
    status = "accepted" if ok else "rejected_unconverged_stations"
    return BemResult(T if ok else float("nan"), Q if ok else float("nan"),
                     Q * omega if ok else float("nan"), stations, ok, status)
