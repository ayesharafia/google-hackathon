"""Welding, topology diagnostics, shells and stable component IDs [M§11]."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree

from .frames import RotorFrame


class _UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, a: int) -> int:
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def weld(triangles_m: np.ndarray, tol_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Merge vertices closer than tol_m (metres). Returns (vertices, faces)."""
    if not np.isfinite(tol_m) or not tol_m > 0:
        raise ValueError("topology tolerance must be > 0 m")
    triangles = np.asarray(triangles_m, float)
    if triangles.ndim != 3 or triangles.shape[1:] != (3, 3) or not np.isfinite(triangles).all():
        raise ValueError("triangles must be finite (N,3,3) coordinates in metres")
    pts = triangles.reshape(-1, 3)
    if not len(pts):
        raise ValueError("geometry has no triangles")
    uf = _UnionFind(len(pts))
    for a, b in cKDTree(pts).query_pairs(tol_m):
        uf.union(a, b)
    roots = np.array([uf.find(i) for i in range(len(pts))])
    uniq, inv = np.unique(roots, return_inverse=True)
    verts = pts[uniq]
    faces = inv.reshape(-1, 3)
    return verts, faces


@dataclass
class TopologyReport:
    n_triangles: int
    n_vertices: int
    n_shells: int
    shell_of_face: np.ndarray
    surface_area_m2: float
    bounds_min_m: np.ndarray
    bounds_max_m: np.ndarray
    degenerate_faces: list[int] = field(default_factory=list)
    duplicate_faces: list[int] = field(default_factory=list)
    boundary_edges: list[tuple[int, int]] = field(default_factory=list)      # holes / open
    nonmanifold_edges: list[tuple[int, int]] = field(default_factory=list)
    inconsistent_winding_edges: list[tuple[int, int]] = field(default_factory=list)
    signed_volume_by_shell_m3: dict[int, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def closed_and_consistent(self) -> bool:
        return not (self.boundary_edges or self.nonmanifold_edges
                    or self.inconsistent_winding_edges or self.degenerate_faces
                    or self.duplicate_faces)


def topology(verts: np.ndarray, faces: np.ndarray, area_tol_m2: float, *,
             min_feature_m: float | None = None) -> TopologyReport:
    """Diagnose triangulated SI geometry without healing [M§11].

    Shell bbox minimum extent is a preliminary thin-feature screen, not a slot search
    or proof of mesh resolution [ASSUMPTION: plan Task 3.2 first-version check].
    """
    verts, faces = np.asarray(verts, float), np.asarray(faces)
    if verts.ndim != 2 or verts.shape[1:] != (3,) or not len(verts) or not np.isfinite(verts).all():
        raise ValueError("vertices must be finite nonempty (N,3) metres")
    if faces.ndim != 2 or faces.shape[1:] != (3,) or not len(faces) or not np.issubdtype(faces.dtype, np.integer):
        raise ValueError("faces must be nonempty (N,3) integer indices")
    if faces.min() < 0 or faces.max() >= len(verts):
        raise ValueError("face index outside vertex range")
    if not np.isfinite(area_tol_m2) or area_tol_m2 < 0:
        raise ValueError("area tolerance must be finite m² >= 0")
    if min_feature_m is not None and (not np.isfinite(min_feature_m) or min_feature_m <= 0):
        raise ValueError("min_feature_m must be finite metres > 0")
    tri = verts[faces]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    # Triangle area: half the edge cross-product norm [STD: triangle geometry].
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    degenerate = [int(i) for i in np.nonzero(areas <= area_tol_m2)[0]]
    degenerate += [int(i) for i, f in enumerate(faces) if len(set(f.tolist())) < 3
                   and int(i) not in degenerate]
    seen: dict[tuple[int, ...], int] = {}
    duplicates = []
    for i, f in enumerate(faces):
        key = tuple(sorted(f.tolist()))
        if key in seen:
            duplicates.append(i)
        else:
            seen[key] = i
    directed: dict[tuple[int, int], list[int]] = defaultdict(list)
    undirected: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, (a, b, c) in enumerate(faces.tolist()):
        for u, v in ((a, b), (b, c), (c, a)):
            if u == v:
                continue
            directed[(u, v)].append(i)
            undirected[(min(u, v), max(u, v))].append(i)
    boundary, nonmanifold, bad_winding = [], [], []
    uf = _UnionFind(len(faces))
    for e, fs in undirected.items():
        if len(fs) == 1:
            boundary.append(e)
        elif len(fs) > 2:
            nonmanifold.append(e)
        else:
            u, v = e
            if len(directed.get((u, v), [])) != 1 or len(directed.get((v, u), [])) != 1:
                bad_winding.append(e)          # both faces traverse the edge the same way
        for f in fs[1:]:
            uf.union(fs[0], f)
    shell = np.array([uf.find(i) for i in range(len(faces))])
    _, shell = np.unique(shell, return_inverse=True)
    vol = defaultdict(float)
    # Oriented origin-to-face tetrahedron volume, scalar triple product / 6 [STD].
    sv = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])) / 6.0
    for s, v in zip(shell.tolist(), sv.tolist()):
        vol[s] += v
    warnings = []
    if min_feature_m is not None:
        for s in np.unique(shell):
            points = tri[shell == s].reshape(-1, 3)
            if np.ptp(points, axis=0).min() < min_feature_m:
                warnings.append(f"thin_feature_below_resolution: shell {s}")
    return TopologyReport(len(faces), len(verts), int(shell.max()) + 1 if len(faces) else 0,
                          shell, float(areas.sum()), verts.min(axis=0), verts.max(axis=0),
                          sorted(degenerate), duplicates, boundary, nonmanifold, bad_winding,
                          dict(vol), warnings)


def component_id(triangles_m: np.ndarray, grid_m: float) -> str:
    """Stable ID independent of triangle order and of cyclic vertex order.

    Coordinates are snapped to integer multiples of grid_m before hashing. Points
    lying almost exactly on a grid boundary can snap differently after a transform,
    so this ID identifies a component within one geometry revision; it is not a
    geometric-equality test (use symmetry.surface_distance for that). Winding cannot
    be distinguished when the declared quantization collapses vertices.
    """
    if not np.isfinite(grid_m) or grid_m <= 0:
        raise ValueError("component grid must be finite metres > 0")
    triangles = np.asarray(triangles_m, float)
    if triangles.ndim != 3 or triangles.shape[1:] != (3, 3) or not len(triangles) or not np.isfinite(triangles).all():
        raise ValueError("triangles must be finite nonempty (N,3,3) metres")
    scaled = triangles / grid_m
    # NumPy signed int64 representable magnitude bound [STD: integer representation].
    if not np.isfinite(scaled).all() or np.max(np.abs(scaled)) >= 2**63:
        raise ValueError("component grid overflows signed 64-bit coordinates")
    q = np.round(np.asarray(triangles_m, float) / grid_m).astype(np.int64)
    canon = []
    for t in q:
        rows = [tuple(r) for r in t.tolist()]
        canon.append(min(tuple(rows[k:] + rows[:k]) for k in range(3)))  # rotate, keep winding
    canon.sort()
    h = hashlib.sha256(repr(canon).encode("ascii")).hexdigest()
    # 16 hex digits is a revision-local display identifier [ASSUMPTION: reference contract];
    # full revision/source SHA256 remains required for provenance.
    return "cmp_" + h[:16]


@dataclass(frozen=True)
class TopologyTolerance:
    """Declared absolute/relative tolerances plus resolved SI tolerance [M§11]."""
    abs_tol_m: float
    rel_tol: float
    bbox_diagonal_m: float
    resolved_m: float


def resolve_topology_tolerance(triangles_m: np.ndarray, abs_tol_m: float,
                               rel_tol: float) -> TopologyTolerance:
    """Resolve max(abs_tol_m, rel_tol × bbox_diagonal_m), retaining both inputs [M§11]."""
    if not all(np.isfinite(v) and v >= 0 for v in (abs_tol_m, rel_tol)):
        raise ValueError("explicit finite nonnegative absolute and relative tolerances required")
    points = np.asarray(triangles_m, float)
    if points.ndim != 3 or points.shape[1:] != (3, 3) or not len(points) or not np.isfinite(points).all():
        raise ValueError("triangles must be finite nonempty (N,3,3) metres")
    diagonal = float(np.linalg.norm(np.ptp(points.reshape(-1, 3), axis=0)))
    resolved = max(abs_tol_m, rel_tol * diagonal)
    if not np.isfinite(resolved) or resolved <= 0:
        raise ValueError("resolved topology tolerance must be finite metres > 0")
    return TopologyTolerance(abs_tol_m, rel_tol, diagonal, resolved)


ROLES = ("body", "blade", "hub", "landing_gear", "payload", "ground", "excluded")  # [M§11]


@dataclass(frozen=True)
class Component:
    """Explicit classification of a revision-local shell; geometry does not supply rotor metadata."""
    component_id: str
    source_file_sha256: str
    shell_index: int | None
    role: str | None
    rotor_id: str | None
    requires_user_tag: bool


@dataclass(frozen=True)
class Assembly:
    """SI rotor frames, component tags and rotor-to-zone assignments [M§11].

    rotor_source_model explicitly declares source-modelled rotor IDs, never inferred
    from absent blades [ASSUMPTION: field name for plan Task 3.3 declaration].
    """
    components: tuple[Component, ...]
    rotors: tuple[RotorFrame, ...]
    rotation_zones: dict[str, str]
    rotor_source_model: frozenset[str] = frozenset()


def validate_assembly(a: Assembly) -> list[str]:
    """List blocking tags/assignments; RPM and axes must be supplied, never recovered from CAD [M§11]."""
    problems: list[str] = []
    rotor_ids = {r.rotor_id for r in a.rotors}
    if len(rotor_ids) != len(a.rotors):
        problems.append("duplicate rotor_id")
    component_ids = {c.component_id for c in a.components}
    if len(component_ids) != len(a.components):
        problems.append("duplicate component_id")
    for c in a.components:
        if c.role not in ROLES:
            problems.append(f"component {c.component_id}: role must be explicitly selected from {ROLES}")
        if c.requires_user_tag:
            problems.append(f"component {c.component_id}: user tag confirmation required")
        if c.role in ("blade", "hub") and c.rotor_id not in rotor_ids:
            problems.append(f"component {c.component_id}: blade/hub needs an existing rotor")
        elif c.rotor_id is not None and c.rotor_id not in rotor_ids:
            problems.append(f"component {c.component_id}: unknown rotor {c.rotor_id}")
        elif c.rotor_id is not None and c.role not in ("blade", "hub"):
            problems.append(f"component {c.component_id}: static role cannot be assigned to a rotor")
    for r in a.rotors:
        zone = a.rotation_zones.get(r.rotor_id)
        if not isinstance(zone, str) or not zone.strip():
            problems.append(f"rotor {r.rotor_id}: rotation zone required")
        if r.signed_rpm is None:
            problems.append(f"rotor {r.rotor_id}: signed RPM input required")
        if (not any(c.role == "blade" and c.rotor_id == r.rotor_id for c in a.components)
                and r.rotor_id not in a.rotor_source_model):
            problems.append(f"rotor {r.rotor_id}: blade or explicit rotor_source_model required")
    for rotor_id in a.rotation_zones.keys() | a.rotor_source_model:
        if rotor_id not in rotor_ids:
            problems.append(f"unknown rotor {rotor_id} in zone/source-model declarations")
    zones = [z for z in a.rotation_zones.values() if isinstance(z, str) and z.strip()]
    if len(set(zones)) != len(zones):
        problems.append("rotation zone assigned to multiple rotors")
    return problems
