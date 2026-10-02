"""Deterministic, explicitly illustrative sphere STL for backend verification."""
from __future__ import annotations

import math
import struct

import numpy as np


def icosphere_triangles(diameter_m: float, subdivisions: int) -> np.ndarray:
    """Outward-wound icosphere triangles in SI metres; never client geometry."""
    if not isinstance(diameter_m, (int, float)) or not math.isfinite(diameter_m) or diameter_m <= 0:
        raise ValueError("diameter_m must be finite and positive")
    if isinstance(subdivisions, bool) or not isinstance(subdivisions, int) or not 0 <= subdivisions <= 6:
        raise ValueError("subdivisions must be an integer from 0 to 6")
    phi = (1 + math.sqrt(5)) / 2
    vertices = np.asarray([
        (-1, phi, 0), (1, phi, 0), (-1, -phi, 0), (1, -phi, 0),
        (0, -1, phi), (0, 1, phi), (0, -1, -phi), (0, 1, -phi),
        (phi, 0, -1), (phi, 0, 1), (-phi, 0, -1), (-phi, 0, 1),
    ], dtype=np.float64)
    vertices /= np.linalg.norm(vertices, axis=1)[:, None]
    points = [tuple(row) for row in vertices]
    faces = [
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
        (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
        (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
        (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1),
    ]
    for _ in range(subdivisions):
        cache: dict[tuple[int, int], int] = {}

        def midpoint(a: int, b: int, cache: dict[tuple[int, int], int] = cache) -> int:
            key = (min(a, b), max(a, b))
            if key not in cache:
                v = np.asarray(points[a]) + np.asarray(points[b])
                v /= np.linalg.norm(v)
                cache[key] = len(points)
                points.append(tuple(v))
            return cache[key]

        refined = []
        for a, b, c in faces:
            ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
            refined.extend(((a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)))
        faces = refined
    return np.asarray(points, dtype=np.float64)[np.asarray(faces, dtype=np.int32)] * (diameter_m / 2)


def binary_stl_bytes(triangles: np.ndarray, header: bytes = b"physicore demo icosphere") -> bytes:
    """Serialize valid finite triangles in the binary STL facet order."""
    tri = np.asarray(triangles, dtype=np.float64)
    if tri.ndim != 3 or tri.shape[1:] != (3, 3) or len(tri) == 0 or not np.isfinite(tri).all():
        raise ValueError("triangles must be finite nonempty (N,3,3)")
    if not isinstance(header, bytes) or len(header) > 80:
        raise ValueError("header must be at most 80 bytes")
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    mag = np.linalg.norm(cross, axis=1)
    if np.any(mag <= 0):
        raise ValueError("degenerate triangle")
    normals = cross / mag[:, None]
    records = np.empty(len(tri), dtype=np.dtype([("normal", "<f4", (3,)),
                                                 ("vertices", "<f4", (3, 3)), ("attribute", "<u2")]))
    records["normal"] = normals
    records["vertices"] = tri
    records["attribute"] = 0
    return header.ljust(80, b"\0") + struct.pack("<I", len(tri)) + records.tobytes()
