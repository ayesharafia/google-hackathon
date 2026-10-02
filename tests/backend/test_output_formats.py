"""D1.3: verify actual v2606 output paths, formats and headers before readers."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import numpy as np
import pytest

from physimesh.core.container import docker_run_args
from physimesh.core.jobs import Budgets

IMAGE = "opencfd/openfoam-run@sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb"


def prepare_probe(tutorials: Path, case: Path) -> dict:
    """Copy retained vendor dictionaries; all geometry changes are probe choices."""
    base = tutorials / "incompressible/simpleFoam"
    shutil.copytree(base / "squareBend", case)
    shutil.copytree(case / "0.orig", case / "0")
    sources = {}

    def vendor(relative: str) -> str:
        raw = (tutorials / relative).read_bytes()
        sources[relative] = hashlib.sha256(raw).hexdigest()
        return f"// Probe source: v2606 tutorials/{relative}\n" + raw.decode()

    plane = vendor("incompressible/simpleFoam/motorBike/system/cuttingPlane")
    plane = plane.replace("surfaceFormat   vtk;", "surfaceFormat   raw;")
    plane = plane.replace("normal      (0 1 0);", "normal      (0 0 1);")
    streams = vendor("incompressible/simpleFoam/motorBike/system/streamLines")
    streams = streams.replace("setFormat   vtk;", "setFormat   raw;")
    streams = streams.replace("(-1.001 -0.05 0.0011)", "(-0.04 0.05 -0.01)")
    streams = streams.replace("(-1.001 -0.05 1.0011)", "(-0.04 0.05 0.01)")
    coeffs = vendor("incompressible/simpleFoam/motorBike/system/forceCoeffs")
    coeffs = coeffs.split("/*\nbinField1")[0]
    coeffs = coeffs.replace("(motorBikeGroup)", "(walls)")
    forces = vendor("incompressible/pimpleFoam/RAS/wingMotion/wingMotion2D_simpleFoam/system/forces")
    forces = forces.replace("(wing)", "(walls)").replace("writeInterval   10;", "writeInterval   1;")
    solver = vendor("incompressible/simpleFoam/motorBike/system/solverInfo")
    line_source = vendor("incompressible/simpleFoam/rotatingCylinders/system/controlDict")
    line = line_source[line_source.index("    sample1\n"):line_source.rindex("\n}")]
    line = line.replace("(U p U:Transformed)", "(U p)")
    line = line.replace("(1 0 0)", "(-0.025 0.03 0)")
    line = line.replace("(2 0 0)", "(-0.025 0.07 0)").replace("axis        x;", "axis        y;")
    shear_source = vendor("incompressible/simpleFoam/bump2D/setups.orig/common/system/controlDict")
    shear = shear_source[shear_source.index("    wallShearStress\n"):shear_source.index("    yPlus\n")]
    shear = shear.replace("(bump)", "(walls)")
    snippets = {"probePlane": plane, "probeStreams": streams, "probeCoeffs": coeffs,
                "probeForces": forces, "probeSolver": solver, "probeLine": line,
                "probeShear": shear}
    for name, body in snippets.items():
        (case / "system" / name).write_text(body)
    control = vendor("incompressible/simpleFoam/squareBend/system/controlDict")
    control = control.replace("endTime         500;", "endTime         5;")
    control = control.replace("writeInterval   50;", "writeInterval   5;")
    control = control.replace("writeFormat     binary;", "writeFormat     ascii;")
    control = re.sub(r"functions\s*\{.*?\n\}", "functions\n{\n" + "\n".join(
        f'    #include "{name}"' for name in snippets) + "\n}", control, flags=re.DOTALL)
    (case / "system/controlDict").write_text(control)
    return sources


@pytest.mark.backend
def test_v2606_text_output_formats():
    configured = os.environ.get("PHYSIMESH_OPENFOAM_TUTORIALS")
    assert configured, "Set PHYSIMESH_OPENFOAM_TUTORIALS to retained v2606 tutorials"
    root = Path(__file__).resolve().parents[2]
    case = root / ".backend/output-format-probe" / uuid.uuid4().hex
    case.parent.mkdir(parents=True, exist_ok=True)
    sources = prepare_probe(Path(configured), case)
    budgets = Budgets(2, 4, 5, 600, 512)
    command = ["bash", "-lc", "set -e; cd /case; blockMesh; checkMesh; simpleFoam"]
    result = subprocess.run(docker_run_args(IMAGE, case, command, budgets),
                            capture_output=True, text=True, timeout=budgets.wall_time_s, check=False)
    (case / "probe.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, f"Backend probe failed; retained log: {case / 'probe.log'}\n{result.stdout[-4000:]}"
    output_files = [p for p in (case / "postProcessing").rglob("*") if p.is_file()]
    raw_files = [p for p in output_files if p.suffix in (".raw", ".xy")]
    assert raw_files, f"No raw text outputs: {case}"
    records = []
    for path in output_files:
        text = path.read_text()
        headers = [line for line in text.splitlines() if line.startswith("#")]
        if path in raw_files:
            numeric = np.loadtxt(path, comments="#", ndmin=2)
            assert numeric.size and np.isfinite(numeric).all(), path
        records.append({"path": str(path.relative_to(case)), "headers": headers,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    assert any("cuttingPlane" in str(p) for p in raw_files)
    assert any("streamLines" in str(p) for p in raw_files)
    assert any("sample1" in str(p) for p in raw_files)
    assert any("forceCoeffs1" in str(p) and p.suffix == ".dat" for p in output_files)
    assert any("forces" in str(p) and p.suffix == ".dat" for p in output_files)
    assert (case / "5/wallShearStress").is_file()
    report = {"image": IMAGE, "case": str(case), "source_sha256": sources,
              "outputs": records, "iterations": 5, "format": "raw",
              "purpose": "output-format verification; no convergence or aircraft claim"}
    (case / "output_manifest.json").write_text(json.dumps(report, indent=2))
    audit = root / "docs/audit/output_formats_v2606.md"
    lines = ["# OpenCFD v2606 output-format probe", "", f"Image: `{IMAGE}`", "",
             f"Retained run: `{case}`", "", "Five iterations verify format support only.", "",
             "Raw plane, line and streamLine outputs contain finite numeric text.", "",
             "`5/wallShearStress` exists; fields use ASCII with compression off.", "",
             "## Actual output paths and literal headers", ""]
    for record in records:
        lines.extend([f"### `{record['path']}`", "", "```text", *record["headers"], "```", ""])
    lines.extend(["## Vendor input hashes", "", "```json", json.dumps(sources, indent=2), "```", ""])
    audit.write_text("\n".join(lines))
