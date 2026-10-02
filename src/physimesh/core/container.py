"""Hardened docker run arguments (plan Task 1.2). Mirrors the existing PhysiMesh SU2
container safeguards: read-only root, no network, dropped capabilities, process
limit, writable case mount."""
from __future__ import annotations

import os
import pathlib
import re

from .jobs import Budgets


def docker_run_args(image_digest: str, workdir: pathlib.Path, cmd: list[str], budgets: Budgets) -> list[str]:
    """Build isolated argv with explicit cores/GB/PID limits [plan Task 1.2].

    Disk GB and wall seconds are enforced by the worker [M§26]; argv alone
    cannot enforce those budgets for bind-mounted storage. POSIX UID/GID match
    the host caller so generated cases stay writable with all capabilities dropped.
    The pinned vendor entrypoint supports numeric --user through nss-wrapper.
    """
    if re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", image_digest) is None:
        raise ValueError("image must be referenced by immutable digest (name@sha256:...)")
    if not workdir.is_absolute() or any(c in str(workdir) for c in (":", ",", "\n")):
        raise ValueError("case directory must be absolute and safe for a Docker bind mount")
    if not cmd or any(not isinstance(arg, str) or "\0" in arg for arg in cmd):
        raise ValueError("command must contain valid argv strings")
    return ["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--pids-limit", str(budgets.pids_limit), "--cpus", f"{budgets.cpu_cores:g}",
            "--memory", f"{budgets.memory_gb:g}g", "--tmpfs", "/tmp",
            "-v", f"{workdir}:/case:rw", "-w", "/case", image_digest, *cmd]
