"""Task 1.4: real v2606 tutorial meshing under the hardened runner [M§26]."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from physimesh.core.container import docker_run_args
from physimesh.core.jobs import Budgets

# Vendor image inspected locally, 2026-10-02; see docs/audit/backend_pin.md.
IMAGE = "opencfd/openfoam-run@sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb"


@pytest.mark.backend
def test_v2606_tutorial_mesh_in_hardened_container():
    tutorials = os.environ.get("PHYSIMESH_OPENFOAM_TUTORIALS")
    if not tutorials:
        pytest.fail("Set PHYSIMESH_OPENFOAM_TUTORIALS to the hash-verified v2606 source tutorials")
    source = Path(tutorials) / "incompressible/simpleFoam/squareBend"
    assert source.is_dir(), f"Missing vendor tutorial: {source}"
    # Colima shares the home/workspace tree, not macOS /private/var [ASSUMPTION].
    shared_root = Path(os.environ.get("PHYSIMESH_BACKEND_WORK_ROOT",
                                     str(Path(__file__).resolve().parents[2] / ".backend/tests")))
    shared_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=shared_root) as temporary_case:
        case = Path(temporary_case) / "case"
        shutil.copytree(source, case)
        # Resource limits are fixture choices, not vehicle inputs [ASSUMPTION].
        budgets = Budgets(2, 4, 2, 120, 512)
        # Vendor entrypoint resets cwd, so explicitly enter the writable case mount.
        cmd = ["bash", "-lc", "set -e; cd /case; blockMesh; checkMesh"]
        result = subprocess.run(docker_run_args(IMAGE, case, cmd, budgets),
                                capture_output=True, text=True, timeout=budgets.wall_time_s, check=False)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "version=2606" in result.stdout
        assert "Mesh OK." in result.stdout
        assert (case / "constant/polyMesh/points").is_file()


def profile_tutorial(tutorials: Path, output_root: Path, refinement: int) -> dict:
    """Measure a vendor tutorial for Task 1.4; bytes, seconds, cells [ASSUMPTION].

    Twenty iterations are a controlled profiling window, not convergence or
    aircraft evidence. Resource numbers come from retained real container runs.
    """
    import hashlib
    import json
    import re
    import time
    import uuid

    if refinement not in (1, 2):
        raise ValueError("profiling supports the original tutorial or 2x refinement")
    case = output_root / f"squareBend-{refinement}x-{uuid.uuid4().hex}"
    shutil.copytree(tutorials / "incompressible/simpleFoam/squareBend", case)
    shutil.copytree(case / "0.orig", case / "0")
    geometry = case / "constant/triSurface"
    geometry.mkdir()
    shutil.copy2(tutorials / "resources/geometry/angledPlane.obj.gz", geometry)
    # Explicit versioned fixture edits; do not change physical inputs [ASSUMPTION].
    control = case / "system/controlDict"
    control.write_text(control.read_text().replace("endTime         500;", "endTime         20;"))
    mesh = case / "system/blockMeshDict"
    text = mesh.read_text()
    for key in ("nxin", "nxout", "nxbend", "ny", "nz"):
        text = re.sub(rf"(?m)^({key}\s+)(\d+);",
                      lambda m: f"{m[1]}{int(m[2]) * refinement};", text)
    mesh.write_text(text)
    budgets = Budgets(2, 4, 5, 600, 512)  # Development fixture limits [ASSUMPTION].
    prep = ["bash", "-lc", "set -e; cd /case; blockMesh; checkMesh; topoSet"]
    prepared = subprocess.run(docker_run_args(IMAGE, case, prep, budgets),
                              capture_output=True, text=True, timeout=budgets.wall_time_s, check=False)
    (case / "mesh.log").write_text(prepared.stdout + prepared.stderr)
    if prepared.returncode:
        raise RuntimeError(f"mesh fixture failed: {case / 'mesh.log'}")
    cells = int(re.search(r"cells:\s+(\d+)", prepared.stdout)[1])
    solve = ["bash", "-lc", ("set -e; cd /case; simpleFoam; "
             "printf '\\nPROFILE_PEAK_BYTES='; cat /sys/fs/cgroup/memory.peak")]
    started = time.perf_counter()
    solved = subprocess.run(docker_run_args(IMAGE, case, solve, budgets),
                            capture_output=True, text=True, timeout=budgets.wall_time_s, check=False)
    wall_s = time.perf_counter() - started
    (case / "solver.log").write_text(solved.stdout + solved.stderr)
    if solved.returncode:
        raise RuntimeError(f"solver fixture failed: {case / 'solver.log'}")
    times = re.findall(r"^Time = (\d+)$", solved.stdout, re.MULTILINE)
    if times != [str(i) for i in range(1, 21)]:
        raise RuntimeError("profiling window did not complete exactly 20 iterations")
    record = {
        "image": IMAGE, "refinement_per_direction": refinement, "cells": cells,
        "iterations": len(times), "cpu_limit_cores": budgets.cpu_cores, "solver_processes": 1,
        "memory_limit_bytes": int(budgets.memory_gb * 1024**3),  # Docker g means GiB [STD].
        "peak_container_memory_bytes": int(re.search(r"PROFILE_PEAK_BYTES=(\d+)", solved.stdout)[1]),
        "host_elapsed_solver_container_s": wall_s,
        "solver_clock_s": float(re.findall(r"ClockTime = ([\d.]+) s", solved.stdout)[-1]),
        "solver_cpu_s": float(re.findall(r"ExecutionTime = ([\d.]+) s", solved.stdout)[-1]),
        "case_disk_bytes": sum(p.stat().st_size for p in case.rglob("*") if p.is_file()),
        "setting_changes": {"endTime": {"original": 500, "profile": 20}, "mesh_count_factor": refinement},
        "case": str(case),
    }
    record["input_hashes"] = {str(p.relative_to(case)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for folder in ("system", "0", "constant") for p in (case / folder).rglob("*")
                              if p.is_file() and "polyMesh" not in p.parts}
    (case / "profile.json").write_text(json.dumps(record, indent=2, sort_keys=True))
    return record
