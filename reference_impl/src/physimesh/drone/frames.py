"""Frames and transforms [M§3]. World ENU z-up; body x fwd, y left, z up."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np


class MissingInput(ValueError):
    pass


def rotation_matrix_zyx(yaw_rad: float, pitch_rad: float, roll_rad: float) -> np.ndarray:
    """Body-to-world rotation R = Rz(yaw) @ Ry(pitch) @ Rx(roll)."""
    cy, sy = math.cos(yaw_rad), math.sin(yaw_rad)
    cp, sp = math.cos(pitch_rad), math.sin(pitch_rad)
    cr, sr = math.cos(roll_rad), math.sin(roll_rad)
    rz = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]])
    ry = np.array([[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]])
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]])
    return rz @ ry @ rx


def is_orthogonal(m: np.ndarray, tol: float = 1e-12) -> bool:
    return bool(np.allclose(m @ m.T, np.eye(3), atol=tol))


def transform_points(m: np.ndarray, t: np.ndarray, pts: np.ndarray) -> np.ndarray:
    return np.asarray(pts, float) @ np.asarray(m, float).T + np.asarray(t, float)


def transform_vectors(m: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Polar vectors (force, velocity, thrust axis)."""
    return np.asarray(v, float) @ np.asarray(m, float).T


def transform_axial_vectors(m: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Axial vectors (moment, angular velocity): v' = det(M) M v  [M-E33]."""
    m = np.asarray(m, float)
    return float(np.linalg.det(m)) * (np.asarray(v, float) @ m.T)


def transform_tensor(m: np.ndarray, t2: np.ndarray) -> np.ndarray:
    """Rank-2 tensors such as inertia: T' = M T M^T."""
    m = np.asarray(m, float)
    return m @ np.asarray(t2, float) @ m.T


@dataclass(frozen=True)
class RotorFrame:
    rotor_id: str
    center_m: tuple
    axis: tuple                 # unit thrust axis a_i (normalised on creation)
    signed_rpm: Optional[float]  # + follows right-hand rule about axis [M§3]
    azimuth_zero_deg: Optional[float] = None
    phase_offset_deg: Optional[float] = None

    def __post_init__(self):
        a = np.asarray(self.axis, float)
        norm = float(np.linalg.norm(a))
        if not math.isfinite(norm) or norm == 0.0:
            raise ValueError(f"rotor {self.rotor_id}: axis must be a non-zero finite vector")
        object.__setattr__(self, "axis", tuple(a / norm))

    def omega_vector(self) -> np.ndarray:
        """Signed angular velocity vector in rad/s."""
        if self.signed_rpm is None:
            raise MissingInput(f"rotors[{self.rotor_id}].signed_rpm is null")
        return self.signed_rpm * 2.0 * math.pi / 60.0 * np.asarray(self.axis)

    def require_phase(self) -> None:
        """Blade-resolved transient comparisons need azimuth zero and phase [M§3]."""
        if self.azimuth_zero_deg is None or self.phase_offset_deg is None:
            raise MissingInput(f"rotors[{self.rotor_id}] azimuth zero / phase offset is null")
