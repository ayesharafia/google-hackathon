"""Constrained control allocation and hover trim residuals.

Implements [M-E05], [M-E07], [M-E08], [M-E56] for fixed-axis rotors with a
T = kT*Omega^2, Q = kQ*Omega^2 screening model. Interference and tilt make the
real map nonlinear [M§31]; replace kT/kQ with BEM/CFD maps in later tasks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

import numpy as np
from scipy.optimize import lsq_linear

G0 = 9.80665


@dataclass(frozen=True)
class AllocRotor:
    rotor_id: str
    position_body_m: Sequence[float]     # relative to aircraft reference
    axis_body: Sequence[float]           # unit thrust axis
    spin_sign: int                       # +1: rotation follows right-hand rule about axis
    k_thrust: float                      # N / (rad/s)^2
    k_torque: float                      # N m / (rad/s)^2  (aero torque magnitude)
    omega_max_rad_s: float               # SUSTAINED limit, not peak [M§5]
    failed: bool = False


@dataclass
class AllocationResult:
    omega_rad_s: np.ndarray
    wrench_achieved: np.ndarray          # [Fx,Fy,Fz,Mx,My,Mz] about CG, body frame
    wrench_required: np.ndarray
    eps_force: float                     # E08
    eps_moment: float
    residual_components: np.ndarray
    active_constraints: List[str] = field(default_factory=list)
    feasible: bool = False
    status: str = ""


def effectiveness_matrix(rotors: Sequence[AllocRotor], cg_body_m: Sequence[float]) -> np.ndarray:
    """Columns map u_i = Omega_i^2 to the 6-component wrench about the CG."""
    cols = []
    cg = np.asarray(cg_body_m, float)
    for r in rotors:
        a = np.asarray(r.axis_body, float); a = a / np.linalg.norm(a)
        f = r.k_thrust * a
        m = np.cross(np.asarray(r.position_body_m, float) - cg, f) - r.spin_sign * r.k_torque * a
        cols.append(np.concatenate([f, m]))
    return np.array(cols).T


def allocate_hover(rotors: Sequence[AllocRotor], mass_kg: float, cg_body_m: Sequence[float],
                   l_ref_m: float, body_force_n: Sequence[float] = (0, 0, 0),
                   body_moment_nm: Sequence[float] = (0, 0, 0), *, tol_force: float,
                   tol_moment: float) -> AllocationResult:
    """Level hover: rotors must supply -(m g + F_body) and cancel body moments.
    Unreachable conditions are reported; no artificial force is added [M§5]."""
    if mass_kg is None:
        raise ValueError("mass is null: inputs_incomplete")
    w_req = np.concatenate([np.array([0, 0, mass_kg * G0]) - np.asarray(body_force_n, float),
                            -np.asarray(body_moment_nm, float)])
    f_scale = mass_kg * G0
    m_scale = mass_kg * G0 * l_ref_m
    ws = np.array([1 / f_scale] * 3 + [1 / m_scale] * 3)
    a = effectiveness_matrix(rotors, cg_body_m)
    ub = np.array([0.0 if r.failed else r.omega_max_rad_s ** 2 for r in rotors])
    sol = lsq_linear(ws[:, None] * a, ws * w_req, bounds=(np.zeros(len(rotors)), np.maximum(ub, 1e-300)),
                     method="bvls")
    u = np.clip(sol.x, 0.0, ub)
    w = a @ u
    res = w - w_req
    eps_f = float(np.linalg.norm(res[:3]) / f_scale)
    eps_m = float(np.linalg.norm(res[3:]) / m_scale)
    active = []
    for r, ui, ubi in zip(rotors, u, ub):
        if r.failed:
            active.append(f"{r.rotor_id}: failed (mask)")
        elif ui >= ubi * (1 - 1e-9):
            active.append(f"{r.rotor_id}: at sustained max speed")
        elif ui <= 1e-12:
            active.append(f"{r.rotor_id}: at zero speed")
    feasible = eps_f <= tol_force and eps_m <= tol_moment
    return AllocationResult(np.sqrt(u), w, w_req, eps_f, eps_m, res, active, feasible,
                            "trimmed" if feasible else "unreachable")
