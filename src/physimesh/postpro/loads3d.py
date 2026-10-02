"""Native surface loads, rotor loads, source reactions, reconciliation, ledger.

Implements [M-E31], [M-E41]..[M-E44]. Source of truth: unsmoothed native face
values [M§16]. Never integrate a visualisation surface.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

DIM_PRESSURE_PA = (1, -1, -2, 0, 0, 0, 0)
DIM_KINEMATIC_PRESSURE = (0, 2, -2, 0, 0, 0, 0)


class SemanticsError(ValueError):
    pass


# ---------------------------------------------------------------- semantics
def to_physical_pressure(values: np.ndarray, dims: tuple[int, ...], *, field_name: str,
                         rho: float | None) -> np.ndarray:
    """Convert backend pressure to Pa exactly once (CT04) [M§16].

    Dimensions decide, never the field name. p_rgh needs hydrostatic
    reconstruction and is refused here.
    """
    if field_name == "p_rgh":
        raise SemanticsError("p_rgh requires hydrostatic reconstruction; not supported")
    v = np.asarray(values, float)
    if tuple(dims) == DIM_PRESSURE_PA:
        return v.copy()
    if tuple(dims) == DIM_KINEMATIC_PRESSURE:
        if rho is None or not rho > 0:
            raise SemanticsError("kinematic pressure needs a declared density rho > 0")
        return v * rho
    raise SemanticsError(f"invalid pressure dimensions {dims}")


def to_physical_stress(values: np.ndarray, dims: tuple[int, ...], *,
                       rho: float | None) -> np.ndarray:
    """Same rule for wall shear stress (kinematic m^2/s^2 or Pa)."""
    return to_physical_pressure(values, dims, field_name="wallShearStress", rho=rho)


def solid_area_vectors_from_backend(sf_domain_outward: np.ndarray) -> np.ndarray:
    """OpenFOAM boundary-face area vectors point out of the fluid domain, i.e.
    into the solid. Our convention n_s points from solid into fluid [M§3], so
    flip once here. [VERIFY-IN-BACKEND] with the closed-cube fixture."""
    return -np.asarray(sf_domain_outward, float)


# ---------------------------------------------------------------- integrals
@dataclass(frozen=True)
class SurfaceLoads:
    force_pressure_n: np.ndarray
    force_viscous_n: np.ndarray
    force_total_n: np.ndarray
    moment_total_nm: np.ndarray
    moment_origin_m: np.ndarray
    area_m2: float
    p_ref_pa: float


def integrate_surface_loads(face_centres_m: np.ndarray, area_vectors_solid_m2: np.ndarray,
                            pressure_pa: np.ndarray, viscous_traction_pa: np.ndarray,
                            moment_origin_m: Sequence[float], p_ref_pa: float) -> SurfaceLoads:
    """t = -(p - p_ref) n_s + tau.n_s ; F = sum t |S| ; M = sum (x - x_o) x t |S|.

    viscous_traction_pa is the per-face vector tau.n_s in Pa acting ON the solid.
    Do not integrate a smoothed visualisation surface. Moment about a rotor
    centre is different from moment about vehicle centre of gravity [M§16].
    Implements [M-E41], [M-E42].
    """
    x = np.asarray(face_centres_m, float)
    s = np.asarray(area_vectors_solid_m2, float)
    p = np.asarray(pressure_pa, float)
    tv = np.asarray(viscous_traction_pa, float)
    mag = np.linalg.norm(s, axis=1)
    f_p = -(p - p_ref_pa)[:, None] * s
    f_v = tv * mag[:, None]
    f = f_p + f_v
    origin = np.asarray(moment_origin_m, float)
    m = np.cross(x - origin, f).sum(axis=0)
    return SurfaceLoads(f_p.sum(axis=0), f_v.sum(axis=0), f.sum(axis=0), m, origin,
                        float(mag.sum()), float(p_ref_pa))


def transfer_moment(m_about_a: np.ndarray, x_a: Sequence[float], x_o: Sequence[float],
                    force: np.ndarray) -> np.ndarray:
    """M_O = M_A + (x_A - x_O) x F  [M-E44]."""
    return np.asarray(m_about_a, float) + np.cross(np.asarray(x_a, float) - np.asarray(x_o, float),
                                                   np.asarray(force, float))


@dataclass(frozen=True)
class RotorLoads:
    thrust_n: float
    q_aero_nm: float          # aerodynamic torque about the axis (negative = resisting for +Omega)
    p_shaft_w: float          # positive = shaft power into the rotor in normal propulsion


def rotor_loads(force_n: np.ndarray, moment_about_rotor_center_nm: np.ndarray,
                axis: Sequence[float], omega_vec_rad_s: np.ndarray) -> RotorLoads:
    """T = F.a ; Q_aero = M.a ; P_shaft = -M_aero.Omega  [M-E43]."""
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    m = np.asarray(moment_about_rotor_center_nm, float)
    return RotorLoads(float(np.dot(force_n, a)), float(np.dot(m, a)),
                      float(-np.dot(m, omega_vec_rad_s)))


def source_reaction(force_density_on_fluid: np.ndarray, cell_volumes_m3: np.ndarray,
                    cell_centres_m: np.ndarray, rotor_center_m: Sequence[float]):
    """Reaction on the aircraft of a volume source acting on the fluid [M-E31]."""
    f = np.asarray(force_density_on_fluid, float) * np.asarray(cell_volumes_m3, float)[:, None]
    F = -f.sum(axis=0)
    M = -np.cross(np.asarray(cell_centres_m, float) - np.asarray(rotor_center_m, float), f).sum(axis=0)
    return F, M


# ---------------------------------------------------------------- reconciliation
@dataclass(frozen=True)
class Reconciliation:
    passed: bool
    abs_error: np.ndarray
    allowed: np.ndarray
    status: str               # "accepted" | "diagnostic_only"


def reconcile(ours: np.ndarray, native: np.ndarray, *, rel_tol: float, abs_tol: float) -> Reconciliation:
    """Component-wise |ours - native| <= rel_tol*|native| + abs_tol [M§32]."""
    ours = np.asarray(ours, float); native = np.asarray(native, float)
    err = np.abs(ours - native)
    allowed = rel_tol * np.abs(native) + abs_tol
    ok = bool(np.all(err <= allowed))
    return Reconciliation(ok, err, allowed, "accepted" if ok else "diagnostic_only")


# ---------------------------------------------------------------- force ledger
LEDGER_CATEGORIES = ("rotor_source_reaction", "rotor_wall", "body", "gravity", "external")


@dataclass
class LedgerEntry:
    category: str
    item_id: str              # rotor id, component id, or "gravity"
    patches: tuple[str, ...]
    force_n: np.ndarray
    moment_cg_nm: np.ndarray


@dataclass
class ForceLedger:
    entries: list[LedgerEntry] = field(default_factory=list)
    excluded_components: list[str] = field(default_factory=list)

    def add(self, e: LedgerEntry) -> None:
        if e.category not in LEDGER_CATEGORIES:
            raise ValueError(f"unknown ledger category {e.category}")
        if e.category in ("rotor_source_reaction", "rotor_wall"):
            other = "rotor_wall" if e.category == "rotor_source_reaction" else "rotor_source_reaction"
            if any(x.category == other and x.item_id == e.item_id for x in self.entries):
                raise ValueError(f"rotor {e.item_id}: both source reaction and wall traction "
                                 "would double count [M§10]")
        used = {p for x in self.entries for p in x.patches}
        dup = used.intersection(e.patches)
        if dup:
            raise ValueError(f"patches already counted: {sorted(dup)}")
        self.entries.append(e)

    def aerodynamic_total(self):
        """Rotor + body categories only [M§17]."""
        sel = [e for e in self.entries if e.category in ("rotor_source_reaction", "rotor_wall", "body")]
        return (sum((e.force_n for e in sel), np.zeros(3)),
                sum((e.moment_cg_nm for e in sel), np.zeros(3)))
