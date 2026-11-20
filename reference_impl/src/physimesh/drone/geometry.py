"""Welding, topology diagnostics, shells and stable component IDs [M§11]."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
from scipy.spatial import cKDTree


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


def weld(triangles_m: np.ndarray, tol_m: float) -> Tuple[np.ndarray, np.ndarray]:
    """Merge vertices closer than tol_m (metres). Returns (vertices, faces)."""
    if not tol_m > 0:
        raise ValueError("topology tolerance must be > 0 m")
    pts = np.asarray(triangles_m, float).reshape(-1, 3)
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
    degenerate_faces: List[int] = field(default_factory=list)
    duplicate_faces: List[int] = field(default_factory=list)
    boundary_edges: List[Tuple[int, int]] = field(default_factory=list)      # holes / open
    nonmanifold_edges: List[Tuple[int, int]] = field(default_factory=list)
    inconsistent_winding_edges: List[Tuple[int, int]] = field(default_factory=list)
    signed_volume_by_shell_m3: Dict[int, float] = field(default_factory=dict)

    @property
    def closed_and_consistent(self) -> bool:
        return not (self.boundary_edges or self.nonmanifold_edges
                    or self.inconsistent_winding_edges or self.degenerate_faces
                    or self.duplicate_faces)


def topology(verts: np.ndarray, faces: np.ndarray, area_tol_m2: float) -> TopologyReport:
    tri = verts[faces]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    degenerate = [int(i) for i in np.nonzero(areas <= area_tol_m2)[0]]
    degenerate += [int(i) for i, f in enumerate(faces) if len(set(f.tolist())) < 3
                   and int(i) not in degenerate]
    seen: Dict[Tuple[int, ...], int] = {}
    duplicates = []
    for i, f in enumerate(faces):
        key = tuple(sorted(f.tolist()))
        if key in seen:
            duplicates.append(i)
        else:
            seen[key] = i
    directed: Dict[Tuple[int, int], List[int]] = defaultdict(list)
    undirected: Dict[Tuple[int, int], List[int]] = defaultdict(list)
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
    sv = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])) / 6.0
    for s, v in zip(shell.tolist(), sv.tolist()):
        vol[s] += v
    return TopologyReport(len(faces), len(verts), int(shell.max()) + 1 if len(faces) else 0,
                          shell, float(areas.sum()), verts.min(axis=0), verts.max(axis=0),
                          sorted(degenerate), duplicates, boundary, nonmanifold, bad_winding,
                          dict(vol))


def component_id(triangles_m: np.ndarray, grid_m: float) -> str:
    """Stable ID independent of triangle order and of cyclic vertex order.

    Coordinates are snapped to integer multiples of grid_m before hashing. Points
    lying almost exactly on a grid boundary can snap differently after a transform,
    so this ID identifies a component within one geometry revision; it is not a
    geometric-equality test (use symmetry.surface_distance for that).
    """
    q = np.round(np.asarray(triangles_m, float) / grid_m).astype(np.int64)
    canon = []
    for t in q:
        rows = [tuple(r) for r in t.tolist()]
        k = rows.index(min(rows))
        canon.append(tuple(rows[k:] + rows[:k]))     # rotate, keep winding
    canon.sort()
    h = hashlib.sha256(repr(canon).encode("ascii")).hexdigest()
    return "cmp_" + h[:16]
