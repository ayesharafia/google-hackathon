#!/usr/bin/env python3
"""Run the labelled sphere verification study; no client aircraft inputs or claims."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

from physimesh.core.artifacts import ArtifactStore
from physimesh.core.jobs import Budgets, JobLedger
from physimesh.drone.demo_geometry import binary_stl_bytes, icosphere_triangles
from physimesh.solver.openfoam_cases import ExternalSteadySpec, external_steady_case, refinement_levels
from physimesh.solver.runner import run_case

IMAGE = "opencfd/openfoam-run@sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb"
ROOT = Path(__file__).resolve().parents[1]


def demo_spec(iterations: int) -> ExternalSteadySpec:
    """Explicit chosen SI verification inputs from MVP §4.2, not aircraft defaults."""
    return ExternalSteadySpec(binary_stl_bytes(icosphere_triangles(1.0, 5)), "sphere",
                              (-10., -10., -10.), (30., 10., 10.), (64, 32, 32), (4, 4),
                              (1., 0., 0.), 0.01, math.pi / 4, 1., (-9.731, 0.123, 0.137),
                              iterations, (0., 1., 0.), ((0.6, 0., 0.), (10., 0., 0.), 201),
                              stop_on_residuals=False)


def metrics(case: Path) -> dict:
    """Extract execution metrics from literal backend logs, without convergence claims."""
    mesh = (case / "checkMesh.log").read_text()
    solve = (case / "simpleFoam.log").read_text()
    record = json.loads((case / "run_record.json").read_text())
    matches = re.findall(r"Solving for (\w+), Initial residual = ([\deE.+-]+), Final residual = ([\deE.+-]+)", solve)
    final_residuals = {field: {"initial": float(initial), "final": float(final)}
                       for field, initial, final in matches}
    times = re.findall(r"^Time = ([\deE.+-]+)$", solve, flags=re.MULTILINE)
    return {"cells": int(re.search(r"cells:\s+(\d+)", mesh)[1]),
            "checkmesh": {"ok": "Mesh OK." in mesh,
                          "max_non_ortho": float(re.search(r"non-orthogonality Max:\s+([\deE.+-]+)", mesh)[1]),
                          "max_skewness": float(re.search(r"Max skewness =\s+([\deE.+-]+)", mesh)[1])},
            "wall_time_s": record["wall_time_s"],
            "peak_memory_bytes": max(item["peak_memory_bytes"] for item in record["stages"]
                                      if item["peak_memory_bytes"] is not None),
            "iterations": len(times), "final_time": times[-1], "final_residuals": final_residuals,
            "evidence": "unverified", "run_record_sha256": hashlib.sha256((case / "run_record.json").read_bytes()).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels", default="coarse,medium,fine")
    parser.add_argument("--iterations", type=int, default=3000)
    parser.add_argument("--output-root", type=Path, default=ROOT / ".backend/demo")
    args = parser.parse_args()
    levels = args.levels.split(",")
    allowed = ("coarse", "medium", "fine")
    if not levels or len(set(levels)) != len(levels) or any(level not in allowed for level in levels):
        parser.error("levels must be unique names from coarse,medium,fine")
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    specs = dict(zip(allowed, refinement_levels(demo_spec(args.iterations), 1.5, 3)))
    code_version = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                                  text=True, check=True).stdout.strip()
    ledger = JobLedger(output / "jobs.sqlite")
    store = ArtifactStore(output / "artifacts")
    group = {"label": "VERIFICATION CASE: sphere Re=100; no aircraft result",
             "image_digest": IMAGE, "code_version": code_version,
             "iteration_cap": args.iterations, "stop_on_residuals": False,
             "load_stopping": {"monitor_start_iteration": 400, "average_cd_window": 400, "absolute_tolerance": 1e-3,
                               "additional_iterations_after_trigger": 400},
             "Re": 100., "D_m": 1., "u_inf_m_s": [1., 0., 0.], "nu_m2_s": 0.01,
             "rho_ref_kg_m3": 1., "meshes": [], "evidence": "unverified"}
    group_path = output / "run_group.json"
    if group_path.exists():
        parser.error(f"{group_path} already exists; use a new output-root to retain prior evidence")
    for level in levels:
        print(f"{level}: preparing and running", flush=True)
        budgets = Budgets(2, 4, 5, 7200, 512)
        job_id = run_case(ledger, store, external_steady_case(specs[level]), IMAGE, budgets, output / "runs")
        job = ledger.get(job_id)
        entry = {"level": level, "job_id": job_id, "case_dir": job.payload["case_dir"],
                 "state": job.state, "reason": job.reason,
                 "background_divisions": specs[level].background_divisions}
        if job.state == "completed":
            entry.update(metrics(Path(job.payload["case_dir"])))
            print(f"{level}: completed {entry['iterations']} iterations, {entry['cells']} cells", flush=True)
        group["meshes"].append(entry)
        group_path.write_text(json.dumps(group, sort_keys=True, indent=2, allow_nan=False))
        if job.state != "completed":
            print(f"{level}: {job.state}: {job.reason}", file=sys.stderr, flush=True)
            return 1
    audit = ROOT / "docs/validation/sphere_re100_runs.md"
    audit.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Sphere Re=100 execution record", "", group["label"], "",
             f"Backend: `{IMAGE}`", "", f"Run group: `{group_path}`", "",
             "After 400 warm-up iterations, a vendor-derived drag-average controller waits for a 400-step window within",
             "an absolute range of 1e-3, then retains 400 further iterations. The cap is",
             f"{args.iterations}. Independent 200-step drift and mesh checks remain separate. Completion",
             "is recorded as unverified until post-processing gates run.", "",
             "| Mesh | Cells | Iterations | Wall seconds | Peak container bytes |", "|---|---:|---:|---:|---:|"]
    for entry in group["meshes"]:
        lines.append(f"| {entry['level']} | {entry['cells']} | {entry['iterations']} | {entry['wall_time_s']:.3f} | {entry['peak_memory_bytes']} |")
    for entry in group["meshes"]:
        case = Path(entry["case_dir"])
        excerpt = [line for line in (case / "checkMesh.log").read_text().splitlines()
                   if any(word in line for word in ("cells:", "non-orthogonality", "Max skewness", "Mesh OK."))]
        residuals = [line for line in (case / "simpleFoam.log").read_text().splitlines()
                     if "Solving for" in line][-4:]
        lines.extend(["", f"## {entry['level']}", "", f"Case: `{case}`", "", "```text", *excerpt, *residuals, "```"])
    audit.write_text("\n".join(lines) + "\n")
    print(group_path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
