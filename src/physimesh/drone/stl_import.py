"""Safe, bounded ASCII/binary STL parser [M§11]. Never executes content."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

_BIN_DTYPE = np.dtype([("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("attr", "<u2")])
# Binary STL: 80-byte header, 4-byte count, 50-byte facet [STD: STL format].
assert _BIN_DTYPE.itemsize == 50


class StlError(ValueError):
    pass


@dataclass(frozen=True)
class StlMesh:
    triangles: np.ndarray        # (N, 3, 3) float64, in the file's declared units (NOT yet SI)
    file_normals: np.ndarray     # (N, 3) as stored; never trusted for orientation
    fmt: str                     # "binary" | "ascii"
    solid_names: list[str]
    sha256: str
    n_bytes: int


def _check_finite(tris: np.ndarray) -> None:
    if not np.all(np.isfinite(tris)):
        raise StlError("non-finite vertex coordinate")


def _is_binary(data: bytes) -> bool:
    """Binary iff the size matches 84 + 50*N exactly. A header beginning with
    'solid' does NOT imply ASCII [M§11]."""
    if len(data) < 84:
        return False
    n = int.from_bytes(data[80:84], "little")
    return len(data) == 84 + 50 * n


def parse_stl(data: bytes, *, max_bytes: int, max_triangles: int) -> StlMesh:
    """Bounds come from configuration, not hard-coded limits [M§11]."""
    if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in (max_bytes, max_triangles)):
        raise StlError("byte and triangle limits must be positive integers from configuration")
    if len(data) > max_bytes:
        raise StlError(f"file has {len(data)} bytes, limit is {max_bytes}")
    digest = hashlib.sha256(data).hexdigest()
    if _is_binary(data):
        n = int.from_bytes(data[80:84], "little")
        if n == 0:
            raise StlError("binary STL declares zero triangles")
        if n > max_triangles:
            raise StlError(f"{n} triangles exceeds limit {max_triangles}")
        rec = np.frombuffer(data, dtype=_BIN_DTYPE, count=n, offset=84)
        tris = rec["v"].astype(np.float64)
        _check_finite(tris)
        return StlMesh(tris, rec["n"].astype(np.float64), "binary", [], digest, len(data))
    return _parse_ascii(data, max_triangles, digest)


def _parse_ascii(data: bytes, max_triangles: int, digest: str) -> StlMesh:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise StlError("not a valid binary STL (size mismatch) and not ASCII") from exc
    tok = text.split()
    if not tok or tok[0] != "solid":
        raise StlError("ASCII STL must start with 'solid'")
    tris, normals, names = [], [], []
    i, n_tok = 0, len(tok)

    def expect(word: str) -> None:
        nonlocal i
        if i >= n_tok or tok[i] != word:
            got = tok[i] if i < n_tok else "EOF"
            raise StlError(f"expected {word!r}, got {got!r} at token {i}")
        i += 1

    def floats(k: int) -> list[float]:
        nonlocal i
        if i + k > n_tok:
            raise StlError("truncated ASCII STL")
        try:
            vals = [float(t) for t in tok[i:i + k]]
        except ValueError as exc:
            raise StlError(f"bad number near token {i}") from exc
        i += k
        return vals

    while i < n_tok:
        expect("solid")
        name_parts = []
        while i < n_tok and tok[i] not in ("facet", "endsolid"):
            name_parts.append(tok[i]); i += 1
        names.append(" ".join(name_parts))
        while i < n_tok and tok[i] == "facet":
            i += 1
            expect("normal"); normals.append(floats(3))
            expect("outer"); expect("loop")
            tri = []
            for _ in range(3):
                expect("vertex"); tri.append(floats(3))
            expect("endloop"); expect("endfacet")
            tris.append(tri)
            if len(tris) > max_triangles:
                raise StlError(f"more than {max_triangles} triangles")
        expect("endsolid")
        while i < n_tok and tok[i] != "solid":   # skip optional name after endsolid
            i += 1
    if not tris:
        raise StlError("ASCII STL contains no facets")
    arr = np.asarray(tris, dtype=np.float64)
    _check_finite(arr)
    return StlMesh(arr, np.asarray(normals, float), "ascii", names, digest, len(data))
