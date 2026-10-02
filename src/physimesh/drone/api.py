"""STL intake with declared units and honest geometry readiness [M§11, M§26]."""
from __future__ import annotations

import json
import math
from typing import Annotated

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from ..core.artifacts import ArtifactStore
from .frames import rotation_matrix_zyx
from .geometry import topology, weld
from .provenance import canonical_json, sha256_record
from .stl_import import StlError, parse_stl
from .units import UnitsError, to_si_length

router = APIRouter(prefix="/api/drone")
NOTE = "Import success means the file was read; it does not mean a valid CFD case was created."


@router.post("/import")
async def import_stl(request: Request, source_units: Annotated[str, Form()],
                     files: Annotated[list[UploadFile], File()],
                     transform_json: Annotated[str | None, Form()] = None) -> dict:
    """Retain original STL bytes, then convert coordinates to SI for diagnostics."""
    settings = request.app.state.settings
    if not files:
        raise HTTPException(422, "at least one STL file is required")
    transform = {"scale": 1.0, "rotation_deg_zyx": [0.0, 0.0, 0.0],
                 "translation_m": [0.0, 0.0, 0.0]}
    if transform_json is not None:
        try:
            supplied = json.loads(transform_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(422, "transform_json must be JSON") from exc
        if not isinstance(supplied, dict) or set(supplied) != set(transform):
            raise HTTPException(422, "transform_json needs scale, rotation_deg_zyx, translation_m")
        transform = supplied
    scale_transform = transform["scale"]
    try:
        rotation = np.asarray(transform["rotation_deg_zyx"], dtype=float)
        translation = np.asarray(transform["translation_m"], dtype=float)
        finite_scale = math.isfinite(float(scale_transform))
    except (TypeError, ValueError, OverflowError) as exc:
        raise HTTPException(422, "transform must contain finite SI quantities") from exc
    if (not isinstance(scale_transform, (int, float)) or isinstance(scale_transform, bool)
            or not finite_scale or scale_transform <= 0
            or rotation.shape != (3,) or translation.shape != (3,)
            or not np.issubdtype(rotation.dtype, np.number)
            or not np.issubdtype(translation.dtype, np.number)
            or not np.isfinite(rotation).all() or not np.isfinite(translation).all()):
        raise HTTPException(422, "transform must contain finite rotation and translation vectors and positive scale")
    rotation = rotation.astype(float)
    translation = translation.astype(float)
    transform = {"scale": float(scale_transform), "rotation_deg_zyx": rotation.tolist(),
                 "translation_m": translation.tolist()}
    transform_sha = sha256_record(transform)
    rotation_matrix = rotation_matrix_zyx(*np.deg2rad(rotation))
    store = ArtifactStore(settings.data_root / "artifacts")
    components = []
    all_triangles = []
    issues = []
    hashes = []
    scale = None
    total_bytes = 0
    total_triangles = 0
    for file in files:
        raw = await file.read(settings.max_upload_bytes + 1)
        total_bytes += len(raw)
        if total_bytes > settings.max_upload_bytes:
            raise HTTPException(413, "total STL upload exceeds configured byte limit")
        try:
            mesh = parse_stl(raw, max_bytes=settings.max_upload_bytes,
                             max_triangles=settings.max_triangles)
            triangles_m, conversion = to_si_length(mesh.triangles, source_units)
        except (StlError, UnitsError) as exc:
            raise HTTPException(422, f"{file.filename}: {exc}") from exc
        scale = conversion.factor
        total_triangles += len(mesh.triangles)
        if total_triangles > settings.max_triangles:
            raise HTTPException(413, "total STL upload exceeds configured triangle limit")
        triangles_m = (triangles_m * scale_transform) @ rotation_matrix.T + translation
        if not np.isfinite(triangles_m).all():
            raise HTTPException(422, "transform produced non-finite coordinates")
        original_sha = store.put_bytes(raw, kind="original_stl",
                                       meta={"filename": file.filename or "unnamed.stl",
                                             "source_units": source_units})
        hashes.append(original_sha)
        all_triangles.append(triangles_m)
        # Scale-relative tolerance makes mm and m declarations comparable after conversion.
        span = float(np.ptp(triangles_m.reshape(-1, 3), axis=0).max())
        tol = max(span * 1e-8, 1e-12)
        vertices, faces = weld(triangles_m, tol)
        report = topology(vertices, faces, area_tol_m2=tol * tol)
        component_id = "cmp_" + sha256_record({"stl": original_sha, "units": source_units})[:12]
        components.append({"component_id": component_id, "filename": file.filename,
                           "source_sha256": original_sha, "role": None,
                           "requires_user_tag": True,
                           "triangle_count": report.n_triangles,
                           "shell_count": report.n_shells,
                           "surface_area_m2": report.surface_area_m2})
        for kind, edges in (("boundary_edge", report.boundary_edges),
                            ("nonmanifold_edge", report.nonmanifold_edges),
                            ("inconsistent_winding_edge", report.inconsistent_winding_edges)):
            if edges:
                issues.append({"component_id": component_id, "kind": kind,
                               "count": len(edges),
                               "locations_m": [((vertices[a] + vertices[b]) / 2).tolist()
                                               for a, b in edges[:100]]})
        for kind, indices in (("degenerate_face", report.degenerate_faces),
                              ("duplicate_face", report.duplicate_faces)):
            if indices:
                issues.append({"component_id": component_id, "kind": kind,
                               "count": len(indices),
                               "locations_m": [triangles_m[i].mean(axis=0).tolist()
                                               for i in indices[:100]]})
    triangles = np.concatenate(all_triangles)
    revision_record = {"original_sha256": hashes, "source_units": source_units,
                       "transform": transform, "schema": "geometry_import_v1"}
    revision = store.put_bytes(canonical_json(revision_record).encode(), kind="geometry_revision",
                               meta={"source_sha256": hashes})
    return {"status": "read_ok", "geometry_revision_sha256": revision,
            "unit_scale_to_m": scale,
            "conversion": {"from": source_units, "to": "m", "factor": scale},
            "transform": {**transform, "sha256": transform_sha},
            "bounding_box_m": {"min": triangles.min(axis=(0, 1)).tolist(),
                               "max": triangles.max(axis=(0, 1)).tolist()},
            "triangle_count": len(triangles),
            "shell_count": sum(c["shell_count"] for c in components),
            "surface_area_m2": sum(c["surface_area_m2"] for c in components),
            "topology_issues": issues,
            "proposed_repairs": ["orient_consistently"] if any(
                i["kind"] == "inconsistent_winding_edge" for i in issues) else [],
            "components": components,
            "unresolved_inputs": [*(f"assembly.components[{c['component_id']}].role" for c in components),
                                  "rotors"],
            "note": NOTE}
