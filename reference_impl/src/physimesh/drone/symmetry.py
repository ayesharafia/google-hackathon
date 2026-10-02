"""Mirror symmetry: geometry match, physical eligibility, load reconstruction.

Implements [M-E32], [M-E33]; rules from [M§12]. Execution is OFF by default [M§31].
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np
from scipy.spatial import cKDTree

from .frames import RotorFrame


def reflection_matrix(normal: Sequence[float]) -> np.ndarray:
    """H = 1 - 2 n n^T  [M-E32]."""
    n = np.asarray(normal, float)
    n = n / np.linalg.norm(n)
    return np.eye(3) - 2.0 * np.outer(n, n)


def reflect_points(x0: Sequence[float], normal: Sequence[float], pts: np.ndarray) -> np.ndarray:
    """x' = x0 + H (x - x0)  [M-E32]."""
    h = reflection_matrix(normal)
    x0 = np.asarray(x0, float)
    return x0 + (np.asarray(pts, float) - x0) @ h.T


def reflect_triangles(x0, normal, tris: np.ndarray) -> np.ndarray:
    """Reflect coordinates, then swap two vertices so normals stay outward [M§12]."""
    r = reflect_points(x0, normal, np.asarray(tris, float).reshape(-1, 3)).reshape(-1, 3, 3)
    return r[:, [0, 2, 1], :]


def reflect_rotor(x0, normal, rotor: RotorFrame, new_id: str) -> RotorFrame:
    """Thrust axis is polar (a' = H a); Omega is axial (Omega' = det(H) H Omega) [M-E33]."""
    h = reflection_matrix(normal)
    c = reflect_points(x0, normal, np.asarray(rotor.center_m, float)[None, :])[0]
    a_new = h @ np.asarray(rotor.axis, float)
    rpm_new = None
    if rotor.signed_rpm is not None:
        omega_new = np.linalg.det(h) * (h @ rotor.omega_vector())
        rpm_new = float(np.dot(omega_new, a_new)) * 60.0 / (2.0 * math.pi)
    return RotorFrame(new_id, tuple(c), tuple(a_new), rpm_new,
                      rotor.azimuth_zero_deg, rotor.phase_offset_deg)


# ------------------------------------------------------------- geometric match
def closest_point_on_triangle(p, a, b, c):
    """Ericson, Real-Time Collision Detection, 5.1.5 [STD]."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = ab @ ap, ac @ ap
    if d1 <= 0 and d2 <= 0:
        return a
    bp = p - b
    d3, d4 = ab @ bp, ac @ bp
    if d3 >= 0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        return a + (d1 / (d1 - d3)) * ab
    cp = p - c
    d5, d6 = ab @ cp, ac @ cp
    if d6 >= 0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        return a + (d2 / (d2 - d6)) * ac
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        return b + ((d4 - d3) / ((d4 - d3) + (d5 - d6))) * (c - b)
    denom = 1.0 / (va + vb + vc)
    return a + ab * (vb * denom) + ac * (vc * denom)


def sample_triangles(tris: np.ndarray, per_edge: int) -> np.ndarray:
    """Deterministic barycentric samples covering facet interiors, not only vertices [M§12]."""
    pts = []
    k = per_edge
    for i in range(k + 1):
        for j in range(k + 1 - i):
            u, v = i / k, j / k
            w = 1.0 - u - v
            pts.append(w * tris[:, 0] + u * tris[:, 1] + v * tris[:, 2])
    return np.concatenate(pts, axis=0)


def surface_distances(points: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Exact distance from each point to the triangle set (KD-tree candidate pruning)."""
    cent = tris.mean(axis=1)
    rmax = float(np.max(np.linalg.norm(tris - cent[:, None, :], axis=2)))
    tree = cKDTree(cent)
    d0, _ = tree.query(points)
    out = np.empty(len(points))
    for i, p in enumerate(points):
        cand = tree.query_ball_point(p, d0[i] + rmax + 1e-12)
        best = math.inf
        for t in cand:
            q = closest_point_on_triangle(p, *tris[t])
            best = min(best, float(np.linalg.norm(p - q)))
        out[i] = best
    return out


@dataclass(frozen=True)
class GeometryMatch:
    max_distance_m: float
    p95_distance_m: float
    tolerance_m: float
    within_tolerance: bool
    unmatched_fraction: float


def geometric_match(source_tris, target_tris, x0, normal, *, abs_tol_m: float,
                    rel_tol: float, samples_per_edge: int = 3) -> GeometryMatch:
    """Bidirectional distance between reflected source and intended counterpart.
    Tolerance = max(abs_tol, rel_tol * bounding-box diagonal) [M§12], [M§31].
    A heuristic score is NOT a physical eligibility result."""
    src = reflect_triangles(x0, normal, np.asarray(source_tris, float))
    tgt = np.asarray(target_tris, float)
    diag = float(np.linalg.norm(tgt.reshape(-1, 3).max(0) - tgt.reshape(-1, 3).min(0)))
    tol = max(abs_tol_m, rel_tol * diag)
    d1 = surface_distances(sample_triangles(src, samples_per_edge), tgt)
    d2 = surface_distances(sample_triangles(tgt, samples_per_edge), src)
    d = np.concatenate([d1, d2])
    return GeometryMatch(float(d.max()), float(np.percentile(d, 95)), tol,
                         bool(d.max() <= tol), float(np.mean(d > tol)))


# ------------------------------------------------------------- eligibility
@dataclass
class OperatingState:
    freestream_world_m_s: Sequence[float]
    gravity_world: Sequence[float] = (0.0, 0.0, -1.0)
    cg_world_m: Optional[Sequence[float]] = None
    yaw_deg: float = 0.0
    motor_loss: bool = False
    asymmetric_transient_disturbance: bool = False
    transient: bool = False
    phases_mirror_consistent: Optional[bool] = None


@dataclass
class Eligibility:
    eligible: bool
    reasons: List[str] = field(default_factory=list)


def physical_eligibility(x0, normal, rotors: Sequence[RotorFrame], state: OperatingState,
                         geometry: GeometryMatch, *, pos_tol_m: float, rpm_tol: float,
                         vel_tol_m_s: float) -> Eligibility:
    """Default = reject. Every rotor must map onto a partner with the reflected RPM;
    flow, gravity and CG must be invariant [M§12]."""
    n = np.asarray(normal, float); n = n / np.linalg.norm(n)
    x0 = np.asarray(x0, float)
    reasons: List[str] = []
    if not geometry.within_tolerance:
        reasons.append("geometry does not match its reflection within tolerance")
    if abs(float(np.dot(state.freestream_world_m_s, n))) > vel_tol_m_s:
        reasons.append("crosswind across the symmetry plane")
    if abs(float(np.dot(state.gravity_world, n))) > 1e-12:
        reasons.append("gravity not parallel to the plane")
    if state.yaw_deg != 0.0:
        reasons.append("yawed attitude")
    if state.motor_loss:
        reasons.append("motor loss case")
    if state.asymmetric_transient_disturbance:
        reasons.append("asymmetric transient disturbance")
    if state.cg_world_m is None:
        reasons.append("CG unknown (null)")
    elif abs(float(np.dot(np.asarray(state.cg_world_m, float) - x0, n))) > pos_tol_m:
        reasons.append("displaced payload / CG off the plane")
    if state.transient and state.phases_mirror_consistent is not True:
        reasons.append("transient rotor phases not shown to be mirror-consistent")
    for r in rotors:
        if r.signed_rpm is None:
            reasons.append(f"rotor {r.rotor_id}: RPM is null")
            continue
        img = reflect_rotor(x0, n, r, r.rotor_id + "'")
        partner = [q for q in rotors if q.signed_rpm is not None
                   and np.linalg.norm(np.asarray(q.center_m) - np.asarray(img.center_m)) <= pos_tol_m
                   and np.allclose(q.axis, img.axis, atol=1e-9)]
        if not partner:
            reasons.append(f"rotor {r.rotor_id}: no mirror partner")
        elif not any(abs(q.signed_rpm - img.signed_rpm) <= rpm_tol for q in partner):
            reasons.append(f"rotor {r.rotor_id}: mirror partner RPM/handedness does not match "
                           "(single swirling rotor or asymmetric RPM)")
    return Eligibility(not reasons, reasons)


def reconstruct_full_loads(force_n, moment_nm, x0, normal, moment_origin_m, *, pos_tol_m: float):
    """Simulated half + transformed partner. Origin must lie on the plane [M§12]."""
    n = np.asarray(normal, float); n = n / np.linalg.norm(n)
    if abs(float(np.dot(np.asarray(moment_origin_m, float) - np.asarray(x0, float), n))) > pos_tol_m:
        raise ValueError("moment origin must lie on the symmetry plane")
    h = reflection_matrix(n)
    f = np.asarray(force_n, float); m = np.asarray(moment_nm, float)
    return f + h @ f, m + np.linalg.det(h) * (h @ m)
