"""Vendor-derived v2606 stationary sphere verification cases [M§26; MVP D1.4]."""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

TEMPLATES = Path(__file__).parent / "openfoam_templates/v2606/external_steady"


@dataclass(frozen=True)
class ExternalSteadySpec:
    stl_bytes: bytes
    body_patch: str
    domain_min_m: tuple[float, float, float]
    domain_max_m: tuple[float, float, float]
    background_divisions: tuple[int, int, int]
    surface_level: tuple[int, int]
    u_inf_m_s: tuple[float, float, float]
    nu_m2_s: float
    a_ref_m2: float
    l_ref_m: float
    location_in_mesh_m: tuple[float, float, float]
    iterations: int
    slice_normal: tuple[float, float, float]
    wake_line: tuple[tuple[float, float, float], tuple[float, float, float], int]
    stop_on_residuals: bool = True


def _vector(value) -> str:
    return "(" + " ".join(f"{float(v):.17g}" for v in value) + ")"


def _entry(text: str, key: str, value: str) -> str:
    pattern = rf"(?m)^(\s*{re.escape(key)}\s+)[^;\n]+;"
    changed, count = re.subn(pattern, lambda match: match[1] + value + ";", text)
    if not count:
        raise ValueError(f"vendor template entry missing: {key}")
    return changed


def _block(text: str, name: str, contents: str, delimiters=("{", "}")) -> str:
    """Replace a named balanced vendor block, retaining its outside context."""
    opening, closing = delimiters
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s*{re.escape(opening)}", text)
    if match is None:
        raise ValueError(f"vendor template block missing: {name}")
    start = text.index(opening, match.start())
    depth = 1
    end = start + 1
    while depth:
        if end >= len(text):
            raise ValueError(f"unbalanced vendor block: {name}")
        depth += (text[end] == opening) - (text[end] == closing)
        end += 1
    return text[:start + 1] + "\n" + contents + "\n" + text[end - 1:]


def _validate(spec: ExternalSteadySpec) -> None:
    if not isinstance(spec.stop_on_residuals, bool):
        raise TypeError("stop_on_residuals must be an explicit boolean")
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", spec.body_patch) is None:
        raise ValueError("body_patch must be a safe OpenFOAM word")
    lo, hi, keep = (np.asarray(v, float) for v in
                    (spec.domain_min_m, spec.domain_max_m, spec.location_in_mesh_m))
    for value in (lo, hi, keep, np.asarray(spec.u_inf_m_s), np.asarray(spec.slice_normal)):
        if value.shape != (3,) or not np.isfinite(value).all():
            raise ValueError("spec vectors must be finite 3-vectors")
    if not np.all(hi > lo) or not np.all((keep > lo) & (keep < hi)):
        raise ValueError("location_in_mesh must lie strictly inside the domain")
    for value in (spec.nu_m2_s, spec.a_ref_m2, spec.l_ref_m):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError("viscosity and reference area/length must be finite positive SI values")
    if len(spec.background_divisions) != 3 or any(
        isinstance(n, bool) or not isinstance(n, int) or n <= 0 for n in spec.background_divisions
    ):
        raise ValueError("background_divisions must be three positive integers")
    if len(spec.surface_level) != 2 or any(
        isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in spec.surface_level
    ) or spec.surface_level[1] < spec.surface_level[0]:
        raise ValueError("surface_level must be ordered nonnegative integers")
    if isinstance(spec.iterations, bool) or not isinstance(spec.iterations, int) or spec.iterations <= 0:
        raise ValueError("iterations must be a positive integer")
    if np.linalg.norm(spec.u_inf_m_s) == 0 or np.linalg.norm(spec.slice_normal) == 0:
        raise ValueError("freestream and slice_normal must be nonzero")
    if spec.u_inf_m_s[0] <= 0 or any(value != 0 for value in spec.u_inf_m_s[1:]):
        raise ValueError("MVP sphere boundary layout requires positive world-x freestream")
    if not isinstance(spec.stl_bytes, bytes) or not spec.stl_bytes:
        raise ValueError("stl_bytes must be supplied SI geometry")
    # The caller must verify an origin-centred sphere of diameter l_ref_m.
    # Solver adapters do not import the application geometry layer [plan §6.1].
    radius = spec.l_ref_m / 2
    if np.linalg.norm(keep) <= radius:
        raise ValueError("location_in_mesh must lie outside the sphere")
    if not np.all(-radius > lo) or not np.all(radius < hi):
        raise ValueError("sphere must lie strictly inside the domain")
    start, end, n = spec.wake_line
    for value in (start, end):
        array = np.asarray(value, float)
        if array.shape != (3,) or not np.isfinite(array).all():
            raise ValueError("wake_line endpoints must be finite 3-vectors")
    if isinstance(n, bool) or not isinstance(n, int) or n < 2 or start == end:
        raise ValueError("wake_line needs distinct endpoints and at least two points")


def translated_settings(spec: ExternalSteadySpec) -> dict:
    """Every caller-controlled input maps to an output file/key; no guessed values."""
    mapping = {
        "stl_bytes": (f"constant/triSurface/{spec.body_patch}.stl", "bytes", hashlib.sha256(spec.stl_bytes).hexdigest()),
        "body_patch": ("system/snappyHexMeshDict", "geometry/name", spec.body_patch),
        "domain_min_m": ("system/blockMeshDict", "vertices/min", spec.domain_min_m),
        "domain_max_m": ("system/blockMeshDict", "vertices/max", spec.domain_max_m),
        "background_divisions": ("system/blockMeshDict", "blocks/divisions", spec.background_divisions),
        "surface_level": ("system/snappyHexMeshDict", "refinementSurfaces/level", spec.surface_level),
        "u_inf_m_s": ("0/include/initialConditions", "flowVelocity", spec.u_inf_m_s),
        "nu_m2_s": ("constant/transportProperties", "nu", spec.nu_m2_s),
        "a_ref_m2": ("system/forceCoeffs", "Aref", spec.a_ref_m2),
        "l_ref_m": ("system/forceCoeffs", "lRef", spec.l_ref_m),
        "location_in_mesh_m": ("system/snappyHexMeshDict", "locationInMesh", spec.location_in_mesh_m),
        "iterations": ("system/controlDict", "endTime", spec.iterations),
        "slice_normal": ("system/cuttingPlane", "surfaces/yNormal/normal", spec.slice_normal),
        "wake_line": ("system/wakeLine", "sets/centreLine", spec.wake_line),
        "stop_on_residuals": ("system/fvSolution", "SIMPLE/residualControl/enabled", spec.stop_on_residuals),
    }
    return {name: {"file": f, "key": key, "value": value} for name, (f, key, value) in mapping.items()}


def external_steady_case(spec: ExternalSteadySpec) -> dict[str, bytes]:
    """Translate vendor syntax for a laminar sphere; backend smoke is still required."""
    _validate(spec)
    source_files = {str(p.relative_to(TEMPLATES)): p.read_text()
                    for p in TEMPLATES.rglob("*") if p.is_file() and p.name != "SOURCES.json"}
    text = dict(source_files)
    lo, hi = spec.domain_min_m, spec.domain_max_m
    vertices = [(lo[0], lo[1], lo[2]), (hi[0], lo[1], lo[2]),
                (hi[0], hi[1], lo[2]), (lo[0], hi[1], lo[2]),
                (lo[0], lo[1], hi[2]), (hi[0], lo[1], hi[2]),
                (hi[0], hi[1], hi[2]), (lo[0], hi[1], hi[2])]
    block = _block(text["system/blockMeshDict"], "vertices", "\n".join(_vector(v) for v in vertices), ("(", ")"))
    block = block.replace("(20 8 8)", "(" + " ".join(map(str, spec.background_divisions)) + ")")
    block = block.replace("type wall;", "type patch;")
    text["system/blockMeshDict"] = block
    snappy = text["system/snappyHexMeshDict"]
    snappy = _entry(snappy, "addLayers", "false")
    snappy = _block(snappy, "geometry", f"    {spec.body_patch}.stl\n    {{\n        type triSurfaceMesh;\n        name {spec.body_patch};\n    }}")
    snappy = _block(snappy, "features", "", ("(", ")"))
    snappy = _block(snappy, "refinementRegions", "")
    snappy = snappy.replace("motorBike", spec.body_patch).replace("(5 6)", "(" + " ".join(map(str, spec.surface_level)) + ")")
    snappy = _entry(snappy, "locationInMesh", _vector(spec.location_in_mesh_m))
    snappy = _entry(snappy, "explicitFeatureSnap", "false")
    snappy = _entry(snappy, "maxLocalCells", "2000000")
    text["system/snappyHexMeshDict"] = snappy
    text["0/include/initialConditions"] = _entry(text["0/include/initialConditions"], "flowVelocity", _vector(spec.u_inf_m_s))
    for field in ("U", "p"):
        text[f"0/{field}"] = text[f"0/{field}"].replace("motorBikeGroup", spec.body_patch)
    text["0/U"] = _block(text["0/U"], "lowerWall", "        type slip;")
    text["constant/transportProperties"] = _entry(text["constant/transportProperties"], "nu", f"{spec.nu_m2_s:.17g}")
    text["constant/turbulenceProperties"] = _block(_entry(text["constant/turbulenceProperties"], "simulationType", "laminar"), "RAS", "")
    residual_source = text.pop("system/residualSource")
    residual = re.search(r"residualControl\s*\{[^}]+\}", residual_source).group(0)
    residual = re.sub(r'(?m)^\s*"\(k[^\n]+\n', "", residual)
    # Chosen solver stopping tolerance; the independent force-drift gate still applies.
    residual = _entry(_entry(residual, "p", "1e-6"), "U", "1e-6")
    provenance = "\n".join(residual_source.splitlines()[:2])
    if spec.stop_on_residuals:
        text["system/fvSolution"] = text["system/fvSolution"].replace(
            "    consistent yes;", "    consistent yes;\n" + provenance + "\n    " + residual)
        text.pop("system/runTimeControls")
    else:
        controls = text["system/runTimeControls"].split("/*\n    runTimeControl3")[0]
        controls = _entry(_entry(controls, "window", "400"), "duration", "400")
        # Inherited timeStart entry is retained in the vorticity source template.
        # It guarantees warm-up history even before the average condition fills.
        controls = controls.replace("runTimeControl1\n{", "runTimeControl1\n{\n    timeStart       400;")
        text["system/runTimeControls"] = controls
    control = text["system/controlDict"]
    for key, value in (("endTime", str(spec.iterations)), ("writeInterval", str(spec.iterations)),
                       ("purgeWrite", "1"), ("writeFormat", "ascii"), ("writePrecision", "12")):
        control = _entry(control, key, value)
    includes = ("vorticity", "wallShearStress", "cuttingPlane", "wakeLine", "forceCoeffs", "forces", "solverInfo")
    if not spec.stop_on_residuals:
        includes += ("runTimeControls",)
    text["system/controlDict"] = _block(control, "functions", "\n".join(f'    #include "{name}"' for name in includes))
    plane = _entry(text["system/cuttingPlane"], "surfaceFormat", "raw")
    plane = _entry(plane, "normal", _vector(spec.slice_normal))
    text["system/cuttingPlane"] = _entry(plane, "fields", "(p U vorticity)")
    coeffs = text["system/forceCoeffs"].split("/*\nbinField1")[0].replace("motorBikeGroup", spec.body_patch)
    for key, value in (("CofR", "(0 0 0)"), ("magUInf", f"{np.linalg.norm(spec.u_inf_m_s):.17g}"),
                       ("lRef", f"{spec.l_ref_m:.17g}"), ("Aref", f"{spec.a_ref_m2:.17g}")):
        coeffs = _entry(coeffs, key, value)
    text["system/forceCoeffs"] = coeffs
    forces = text["system/forces"].replace("(wing)", f"({spec.body_patch})")
    text["system/forces"] = _entry(_entry(forces, "CofR", "(0 0 0)"), "writeInterval", "1")
    line_source = text.pop("system/lineSource")
    header = "\n".join(line_source.splitlines()[:2]) + "\n"
    line = line_source[line_source.index("    sample1\n"):line_source.rindex("\n}")]
    start, end, count = spec.wake_line
    line = line.replace("(U p U:Transformed)", "(U p)")
    line = _entry(_entry(_entry(line, "start", _vector(start)), "end", _vector(end)), "nPoints", str(count))
    text["system/wakeLine"] = header + line
    shear_source = text.pop("system/shearSource")
    header = "\n".join(shear_source.splitlines()[:2]) + "\n"
    text["system/wallShearStress"] = header + shear_source[shear_source.index("    wallShearStress\n"):shear_source.index("    yPlus\n")].replace("(bump)", f"({spec.body_patch})")
    vort = text["system/vorticity"]
    for key, value in (("result", "vorticity"), ("timeStart", "0"), ("timeEnd", str(spec.iterations)),
                       ("executeInterval", "1"), ("writeControl", "writeTime"), ("writeInterval", "1")):
        vort = _entry(vort, key, value)
    text["system/vorticity"] = vort
    files = {path: value.encode() for path, value in text.items()}
    files[f"constant/triSurface/{spec.body_patch}.stl"] = spec.stl_bytes
    files["translated_settings.json"] = json.dumps(translated_settings(spec), sort_keys=True,
                                                   separators=(",", ":"), allow_nan=False).encode()
    return files


def refinement_levels(spec: ExternalSteadySpec, ratio: float, n: int) -> list[ExternalSteadySpec]:
    """Only background divisions change; actual mesh ratios must be measured later."""
    if not math.isfinite(ratio) or ratio <= 1 or isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError("refinement ratio must exceed 1 and count must be a positive integer")
    return [replace(spec, background_divisions=tuple(round(v * ratio**i) for v in spec.background_divisions))
            for i in range(n)]
