"""Physics-controlled CFD eligibility and three-grid numerical evidence gates.

Hackathon H1 prototype. Does NOT execute OpenFOAM or qualify drone/rotor CFD.
"""
from __future__ import annotations
import math
from dataclasses import dataclass

from physimesh.drone.geometry import topology, weld
from physimesh.drone.stl_import import parse_stl
import numpy as np


@dataclass(frozen=True)
class GeometryDecision:
    status: str
    geometry_hash: str
    part: str
    reasons: tuple[str, ...]
    radius_m: float | None = None


def inspect_geometry(stl: bytes, *, units_to_m: float, declared_part: str) -> GeometryDecision:
    """Bounded STL inspection. No unverified automatic rotor recognition."""
    if declared_part not in ("stationary_sphere", "rotor", "airframe", "other"):
        raise ValueError("unknown part declaration")
    if isinstance(units_to_m, bool) or not isinstance(units_to_m, (int, float)) or not math.isfinite(units_to_m) or units_to_m <= 0:
        raise ValueError("explicit positive finite geometry units required")
    mesh = parse_stl(stl, max_bytes=50_000_000, max_triangles=1_000_000)
    vertices, faces = weld(mesh.triangles * units_to_m, tol_m=1e-7)
    report = topology(vertices, faces, area_tol_m2=1e-14)
    reasons = []
    if not report.closed_and_consistent:
        reasons.append("INVALID_TOPOLOGY")
    if declared_part != "stationary_sphere":
        reasons.append("NO_QUALIFIED_CFD_ADAPTER")
        return GeometryDecision("REJECTED" if "INVALID_TOPOLOGY" in reasons else "UNSUPPORTED",
                                mesh.sha256, declared_part, tuple(reasons))
    center = (report.bounds_min_m + report.bounds_max_m) / 2
    radii = np.linalg.norm(vertices - center, axis=1)
    radius = float(np.median(radii))
    if radius <= 0 or float(np.max(np.abs(radii - radius))) > 0.03 * radius:
        reasons.append("NOT_APPROXIMATELY_SPHERICAL")
    if np.linalg.norm(center) > 0.005 * radius:
        reasons.append("NOT_ORIGIN_CENTERED")
    if any(v <= 0 for v in report.signed_volume_by_shell_m3.values()):
        reasons.append("INVALID_SHELL_ORIENTATION")
    return GeometryDecision("REJECTED" if reasons else "SUPPORTED", mesh.sha256,
                            declared_part, tuple(reasons), radius)


def select_physics(geometry: GeometryDecision, *, speed_m_s: float,
                   diameter_m: float, nu_m2_s: float, sound_speed_m_s: float) -> dict:
    """Restricted steady incompressible sphere benchmark selection, not aircraft validation."""
    inputs = (speed_m_s, diameter_m, nu_m2_s, sound_speed_m_s)
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0 for x in inputs):
        raise ValueError("positive finite SI operating conditions required")
    reynolds = speed_m_s * diameter_m / nu_m2_s
    mach = speed_m_s / sound_speed_m_s
    reasons = list(geometry.reasons)
    if geometry.status != "SUPPORTED":
        reasons.append("GEOMETRY_NOT_ELIGIBLE")
    if mach >= 0.3:
        reasons.append("COMPRESSIBLE_REGIME_NOT_SUPPORTED")
    if not 1 <= reynolds <= 1e5:
        reasons.append("OUTSIDE_PROVISIONAL_REYNOLDS_SCREEN")
    return {"status": "UNSUPPORTED" if reasons else "SUPPORTED",
            "physics": None if reasons else "stationary_incompressible_external_steady_v2606",
            "reynolds_number": reynolds, "mach": mach, "reasons": reasons}


def propose_mesh_levels(physics: dict, *, base_divisions: tuple[int, int, int],
                        surface_level: tuple[int, int] = (1, 2)) -> list[dict]:
    """Candidates only. Real refinement ratios must use measured final mesh cells."""
    if physics.get("status") != "SUPPORTED":
        raise ValueError("physics eligibility required")
    if len(base_divisions) != 3 or any(type(x) is not int or not 4 <= x <= 60 for x in base_divisions):
        raise ValueError("base divisions out of conservative budget")
    if len(surface_level) != 2 or any(type(x) is not int or not 0 <= x <= 5 for x in surface_level) or surface_level[0] > surface_level[1]:
        raise ValueError("invalid surface levels")
    return [{"name": name, "background_divisions": [x * factor for x in base_divisions],
             "surface_level": list(surface_level)}
            for name, factor in zip(("coarse", "medium", "fine"), (1, 2, 4))]


@dataclass(frozen=True)
class GridResult:
    name: str
    cells: int
    value: float
    solver_converged: bool
    mesh_quality_pass: bool
    conservation_pass: bool
    case_hash: str


def assess_grid_independence(results: list[GridResult], *, quantity: str,
                             tolerance: float = 0.02) -> dict:
    """Three-grid observed order and conservative relative GCI, for 3D meshes.

    Require same geometry/domain/physics verified externally; distinct case hashes
    alone do not prove physical equivalence. Results ordered coarse to fine.
    """
    if not quantity or not isinstance(quantity, str) or not math.isfinite(tolerance) or not 0 < tolerance < 1:
        raise ValueError("invalid engineering quantity or tolerance")
    if len(results) != 3 or [x.name for x in results] != ["coarse", "medium", "fine"]:
        raise ValueError("three ordered results required")
    reasons = []
    if any(type(x.cells) is not int or x.cells <= 0 for x in results) or not results[0].cells < results[1].cells < results[2].cells:
        reasons.append("INVALID_REFINEMENT")
    if any(not isinstance(x.value, (int, float)) or not math.isfinite(x.value) for x in results):
        reasons.append("NONFINITE_RESULT")
    if any(not (x.solver_converged and x.mesh_quality_pass and x.conservation_pass) for x in results):
        reasons.append("SOLVER_MESH_OR_CONSERVATION_FAILURE")
    if len(set(x.case_hash for x in results)) != 3 or any(len(x.case_hash) != 64 or any(c not in "0123456789abcdef" for c in x.case_hash) for x in results):
        reasons.append("INVALID_CASE_PROVENANCE")
    if reasons:
        return {"status": "INSUFFICIENT_EVIDENCE", "reasons": reasons}
    h = [x.cells ** (-1 / 3) for x in results]
    r1, r2 = h[0] / h[1], h[1] / h[2]
    if min(r1, r2) <= 1.1 or abs(r1 - r2) / max(r1, r2) > 0.05:
        return {"status": "NOT_GRID_INDEPENDENT", "reasons": ["UNSUITABLE_REFINEMENT_RATIOS"]}
    q1, q2, q3 = [x.value for x in results]
    d1, d2 = q1 - q2, q2 - q3
    if d1 == 0 or d2 == 0 or d1 * d2 <= 0 or q3 == 0:
        return {"status": "NOT_GRID_INDEPENDENT", "reasons": ["NONMONOTONE_OR_DEGENERATE_TREND"]}
    p = math.log(abs(d1 / d2)) / math.log((r1 + r2) / 2)
    if not math.isfinite(p) or not 0 < p <= 6:
        return {"status": "NOT_GRID_INDEPENDENT", "reasons": ["UNRELIABLE_OBSERVED_ORDER"]}
    denominator = r2 ** p - 1
    extrapolated = q3 + (q3 - q2) / denominator
    gci = 1.25 * abs((q3 - q2) / q3) / denominator
    return {"status": "GRID_INDEPENDENT" if gci <= tolerance else "NOT_GRID_INDEPENDENT",
            "observed_order": p, "richardson_extrapolation": extrapolated,
            "relative_gci_fine": gci, "relative_tolerance": tolerance,
            "reasons": [] if gci <= tolerance else ["GCI_ABOVE_TOLERANCE"]}
