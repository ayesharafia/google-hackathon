"""Hardened docker run arguments (plan Task 1.2). Mirrors the existing PhysiMesh SU2
container safeguards: read-only root, no network, dropped capabilities, process
limit, writable case mount."""
from __future__ import annotations

import pathlib
from typing import List

from .jobs import Budgets


def docker_run_args(image_digest: str, workdir: pathlib.Path, cmd: List[str], budgets: Budgets) -> List[str]:
    if "@sha256:" not in image_digest:
        raise ValueError("image must be referenced by immutable digest (name@sha256:...)")
    return ["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--pids-limit", str(budgets.pids_limit), "--cpus", f"{budgets.cpu_cores:g}",
            "--memory", f"{budgets.memory_gb:g}g", "--tmpfs", "/tmp",
            "-v", f"{workdir}:/case:rw", "-w", "/case", image_digest, *cmd]
