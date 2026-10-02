"""Strict readers for retained native OpenFOAM ASCII output [M§16; MVP D2.1].

No macros, code streams or dictionary expressions are evaluated. Gzip support
is lossless storage for captured test artifacts, not a field transformation.
"""
from __future__ import annotations

import gzip
import re
import warnings
from pathlib import Path

import numpy as np


class FoamAsciiError(ValueError):
    """Unsupported or corrupt native ASCII evidence cannot be used for loads."""


def _numbers(text: str, dtype=float) -> np.ndarray:
    """Refuse partial numeric parsing, including NumPy's legacy warning path."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            return np.fromstring(text, sep=" ", dtype=dtype)
    except (ValueError, Warning) as exc:
        raise FoamAsciiError("invalid token in native numeric list") from exc


def _text(path: str | Path) -> str:
    path = Path(path)
    if not path.exists() and path.with_name(path.name + ".gz").exists():
        path = path.with_name(path.name + ".gz")
    raw = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FoamAsciiError("native reader requires ASCII output") from exc
    if re.search(r"\bformat\s+binary\s*;", text):
        raise FoamAsciiError("native reader requires writeFormat ascii")
    return text


def _without_comments(text: str) -> str:
    return re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL))


def _balanced(text: str, opening: int, left="{", right="}") -> tuple[str, int]:
    depth, index = 1, opening + 1
    while depth:
        if index >= len(text):
            raise FoamAsciiError("unbalanced native list/dictionary")
        depth += (text[index] == left) - (text[index] == right)
        index += 1
    return text[opening + 1:index - 1], index


def _named_block(text: str, name: str) -> str:
    match = re.search(rf'(?m)^\s*"?{re.escape(name)}"?\s*\{{', text)
    if match is None:
        raise FoamAsciiError(f"missing native dictionary: {name}")
    return _balanced(text, text.index("{", match.start()))[0]


def _root_list(text: str) -> tuple[int, str]:
    text = _without_comments(text)
    if re.search(r"\bFoamFile\s*\{", text):
        match = re.search(r"\bFoamFile\s*\{", text)
        _, end = _balanced(text, text.index("{", match.start()))
        text = text[end:]
    match = re.match(r"\s*(\d+)\s*\(", text)
    if match is None:
        raise FoamAsciiError("missing native counted list")
    contents, _ = _balanced(text, text.index("(", match.start()), "(", ")")
    return int(match[1]), contents


def read_points(path: str | Path) -> np.ndarray:
    """Read the native point list as (N,3) SI metres."""
    count, contents = _root_list(_text(path))
    values = _numbers(contents.translate({ord("("): None, ord(")"): None}))
    if values.size != 3 * count or not np.isfinite(values).all():
        raise FoamAsciiError("point count mismatch or non-finite native coordinates")
    return values.reshape(count, 3)


def read_faces(path: str | Path) -> list[np.ndarray]:
    """Read ordered polygon vertex indices; preserve native face numbering."""
    count, contents = _root_list(_text(path))
    faces = []
    cursor = 0
    for match in re.finditer(r"(\d+)\s*\(([^()]*)\)", contents):
        if contents[cursor:match.start()].strip():
            raise FoamAsciiError("unexpected token in native face list")
        indices = _numbers(match[2], dtype=np.int64)
        if len(indices) != int(match[1]) or len(indices) < 3 or np.any(indices < 0):
            raise FoamAsciiError("invalid native face vertex count or index")
        faces.append(indices)
        cursor = match.end()
    if contents[cursor:].strip() or len(faces) != count:
        raise FoamAsciiError("native face count mismatch")
    return faces


def read_boundary(path: str | Path) -> dict[str, dict]:
    """Native patch type, nFaces and startFace; no patch-name inference."""
    count, contents = _root_list(_text(path))
    patches = {}
    cursor = 0
    while contents[cursor:].strip():
        match = re.match(r'\s*([^\s{}"]+|"[^"]+")\s*\{', contents[cursor:])
        if match is None:
            raise FoamAsciiError("invalid native boundary entry")
        name = match[1].strip('"')
        opening = cursor + match.end() - 1
        body, cursor = _balanced(contents, opening)
        patch = {}
        for key in ("type", "nFaces", "startFace"):
            value = re.search(rf"\b{key}\s+([^;]+);", body)
            if value is None:
                raise FoamAsciiError(f"patch {name} missing {key}")
            if key == "type":
                patch[key] = value[1].strip()
            else:
                if re.fullmatch(r"\s*\d+\s*", value[1]) is None:
                    raise FoamAsciiError(f"patch {name} invalid {key}")
                patch[key] = int(value[1])
        if name in patches:
            raise FoamAsciiError("duplicate native patch")
        patches[name] = patch
    if len(patches) != count:
        raise FoamAsciiError("native boundary count mismatch")
    return patches


def _field_values(body: str, key: str, count: int | None) -> np.ndarray:
    nonuniform = re.search(rf"\b{key}\s+nonuniform\s+List<(scalar|vector)>\s+(\d+)\s*\(", body)
    if nonuniform:
        kind, declared = nonuniform[1], int(nonuniform[2])
        opening = body.index("(", nonuniform.start())
        contents, _ = _balanced(body, opening, "(", ")")
        values = _numbers(contents.translate({ord("("): None, ord(")"): None}))
        width = 3 if kind == "vector" else 1
        if (count is not None and declared != count) or len(values) != declared * width:
            raise FoamAsciiError("native field value count mismatch")
        values = values.reshape(declared, 3) if width == 3 else values
    else:
        uniform = re.search(rf"\b{key}\s+uniform\s+(\([^()]+\)|[^;]+)\s*;", body)
        if uniform is None:
            raise FoamAsciiError(f"no supported written {key}")
        if count is None:
            raise FoamAsciiError("uniform field expansion needs native addressing count")
        value = _numbers(uniform[1].strip("() "))
        if len(value) not in (1, 3):
            raise FoamAsciiError("uniform field must be scalar or vector")
        values = np.full(count, value[0]) if len(value) == 1 else np.tile(value, (count, 1))
    if not np.isfinite(values).all():
        raise FoamAsciiError("non-finite native field values")
    return values


def read_patch_field(path: str | Path, patch: str) -> tuple[np.ndarray, tuple[int, ...]]:
    """Read scalar/vector boundary values with native dimensions and face count.

    Uniform fields expand from the retained case's constant/polyMesh/boundary.
    For a value-less zeroGradient patch, read the exact owner-cell internal
    values. OpenCFD defines zeroGradient as the patch internal field value.
    Other value-less boundary types are refused, never inferred.
    """
    path = Path(path)
    text = _without_comments(_text(path))
    match = re.search(r"\bdimensions\s*\[([^]]+)\]\s*;", text)
    if match is None:
        raise FoamAsciiError("field has no dimensions")
    dimension_values = _numbers(match[1])
    if (len(dimension_values) not in (5, 7) or not np.isfinite(dimension_values).all()
            or np.any(dimension_values != np.floor(dimension_values))):
        raise FoamAsciiError("invalid native field dimensions")
    dimensions = tuple(int(value) for value in dimension_values)
    if len(dimensions) == 5:
        dimensions += (0, 0)
    body = _named_block(_named_block(text, "boundaryField"), patch)
    native_patch = read_boundary(path.parent.parent / "constant/polyMesh/boundary")[patch]
    count = native_patch["nFaces"]
    if not re.search(r"\bvalue\s+", body) and re.search(r"\btype\s+zeroGradient\s*;", body):
        owner_count, owner_contents = _root_list(_text(path.parent.parent / "constant/polyMesh/owner"))
        if re.fullmatch(r"[\d\s]+", owner_contents) is None:
            raise FoamAsciiError("invalid native owner labels")
        owners = _numbers(owner_contents, dtype=np.int64)
        if len(owners) != owner_count or not len(owners):
            raise FoamAsciiError("native owner count mismatch")
        # Owner labels alone do not reveal nCells: some cells occur only as a
        # neighbour. Preserve the written internal list length for nonuniform.
        internal_count = None if re.search(r"internalField\s+nonuniform", text) else int(owners.max()) + 1
        internal = _field_values(text, "internalField", internal_count)
        start = native_patch["startFace"]
        selected = owners[start:start + count]
        if len(selected) != count or (len(selected) and selected.max() >= len(internal)):
            raise FoamAsciiError("patch addressing exceeds native owner list")
        values = internal[selected]
    else:
        values = _field_values(body, "value", count)
    return values, dimensions


def face_centres_and_areas(points: np.ndarray, faces: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """OpenFOAM polygon method: fan about point mean, area-weighted centroid.

    Return centres in m and area vectors in m² with native fluid-domain winding.
    Triangle centres are exact point averages; nonplanar polygon fan weights use
    triangle area magnitudes, as required by MVP §4.3.
    """
    points = np.asarray(points, dtype=float)
    centres, areas = [], []
    for face in faces:
        vertices = points[face]
        mean = vertices.mean(axis=0)
        next_vertices = np.roll(vertices, -1, axis=0)
        cross = np.cross(next_vertices - vertices, mean - vertices)
        magnitude = np.linalg.norm(cross, axis=1)
        area = cross.sum(axis=0) / 2
        total = magnitude.sum()
        centre = mean if total == 0 else (magnitude[:, None] * (vertices + next_vertices + mean)).sum(axis=0) / (3 * total)
        centres.append(centre)
        areas.append(area)
    return np.asarray(centres, float).reshape(-1, 3), np.asarray(areas, float).reshape(-1, 3)


def _table(path, *, numeric_only: bool) -> tuple[list[str], np.ndarray]:
    text = _text(path)
    headers, rows = [], []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            header = stripped[1:].split()
            if header and header[0] in ("Time", "x", "y", "z"):
                headers = header
            continue
        tokens = stripped.translate({ord("("): " ", ord(")"): " "}).split()
        row = []
        for token in tokens:
            try:
                value = float(token)
            except ValueError:
                if token.lower() in ("true", "false"):
                    value = float(token.lower() == "true")
                elif numeric_only:
                    raise FoamAsciiError("non-numeric token in sampled output") from None
                else:
                    value = token
            if isinstance(value, float) and not np.isfinite(value):
                raise FoamAsciiError("non-finite native table value")
            row.append(value)
        rows.append(row)
    if not rows or any(len(row) != len(rows[0]) for row in rows):
        raise FoamAsciiError("empty or ragged native table")
    if headers and len(headers) != len(rows[0]):
        raise FoamAsciiError("native table header/column mismatch")
    dtype = object if any(isinstance(value, str) for row in rows for value in row) else float
    return headers, np.asarray(rows, dtype=dtype)


def read_function_object_table(path: str | Path) -> tuple[list[str], np.ndarray]:
    """Preserve actual native column headers, including solver names as strings."""
    return _table(path, numeric_only=False)


def read_raw_samples(path: str | Path) -> tuple[list[str], np.ndarray]:
    """Read numeric samples; an unheaded .xy returns no invented column names."""
    return _table(path, numeric_only=True)
