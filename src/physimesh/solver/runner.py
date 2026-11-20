"""Bounded stage execution with retained logs and honest execution state [M§26]."""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import time
import uuid
from pathlib import Path, PurePosixPath

from ..core.artifacts import ArtifactStore
from ..core.container import docker_run_args
from ..core.jobs import Budgets, JobLedger

STAGES = ("blockMesh", "snappyHexMesh -overwrite", "checkMesh", "simpleFoam")


def _disk_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _stop(process: subprocess.Popen, container_name: str | None) -> None:
    """Stop the Docker container as well as the client when a budget/cancel fires."""
    if container_name is not None:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True,
                       timeout=15, check=False)
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_case(ledger: JobLedger, store: ArtifactStore, case_files: dict[str, bytes],
             image_digest: str, budgets: Budgets, work_root: Path) -> str:
    """Run mesh/check/solve synchronously; completion never claims convergence.

    Wall time applies to the whole pipeline. Disk GB is monitored in decimal
    bytes every 0.2 s; Docker enforces CPU, memory and PID limits. Native outputs
    stay in the retained case directory and are hashed in the final run record.
    """
    if not case_files:
        raise ValueError("case_files must be nonempty")
    for name, raw in case_files.items():
        path = PurePosixPath(name)
        if (path.is_absolute() or ".." in path.parts or not path.parts
                or "\\" in name or not isinstance(raw, bytes)):
            raise ValueError("case files must have safe relative paths and bytes")
    if re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", image_digest) is None:
        raise ValueError("image must be pinned by digest")
    work_root = Path(work_root).resolve()
    if any(character in str(work_root) for character in (":", ",", "\n")):
        raise ValueError("work_root must be safe for a Docker bind mount")
    work_root.mkdir(parents=True, exist_ok=True)
    case = work_root / uuid.uuid4().hex
    job_id = ledger.submit("openfoam_steady", {"case_dir": str(case), "image_digest": image_digest}, budgets)
    ledger.claim_job(job_id, f"runner-{job_id}")
    pipeline_started = time.monotonic()
    deadline = pipeline_started + budgets.wall_time_s
    stage_records = []
    stage = "preparation"
    try:
        case.mkdir()
        if sum(map(len, case_files.values())) > budgets.disk_gb * 1_000_000_000:
            raise RuntimeError("input files exceed disk budget")
        input_hashes = {}
        for name, raw in case_files.items():
            target = case / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            input_hashes[name] = store.put_bytes(raw, kind="openfoam_input",
                                                meta={"job_id": job_id, "path": name})
        ledger.transition(job_id, "meshing")
        for index, stage in enumerate(STAGES):
            if stage == "simpleFoam":
                ledger.transition(job_id, "running")
            log_path = case / f"{stage.split()[0]}.log"
            # Fixed stage strings only. Vendor entrypoint changes cwd; re-enter /case.
            script = (f"cd /case; {stage}; stage_status=$?; "
                      "printf '\\nPHYSICORE_PEAK_MEMORY_BYTES='; "
                      "cat /sys/fs/cgroup/memory.peak; exit $stage_status")
            args = docker_run_args(image_digest, case, ["bash", "-lc", script], budgets)
            name = f"physicore-{job_id}-{index}" if args[:2] == ["docker", "run"] else None
            if name is not None:
                args[2:2] = ["--name", name]
            started = time.monotonic()
            refusal = None
            with log_path.open("wb") as output:
                process = subprocess.Popen(args, stdout=output, stderr=subprocess.STDOUT,
                                           start_new_session=True)
                while process.poll() is None:
                    if time.monotonic() >= deadline:
                        refusal = "wall time budget exceeded"
                    elif _disk_bytes(case) > budgets.disk_gb * 1_000_000_000:
                        refusal = "disk budget exceeded"
                    elif ledger.get(job_id).state == "cancelled":
                        refusal = "cancelled"
                    if refusal:
                        _stop(process, name)
                        break
                    time.sleep(0.2)
                exit_code = process.wait()
            log = log_path.read_text(errors="replace")
            log_sha = store.put_file(log_path, kind="stage_log", meta={"job_id": job_id, "stage": stage})
            peaks = re.findall(r"PHYSICORE_PEAK_MEMORY_BYTES=(\d+)", log)
            record = {"stage": stage, "exit_code": exit_code, "log_sha256": log_sha,
                      "wall_time_s": time.monotonic() - started,
                      "peak_memory_bytes": int(peaks[-1]) if peaks else None}
            stage_records.append(record)
            ledger.append_event(job_id, record)
            if refusal == "cancelled":
                return job_id
            if refusal or exit_code != 0 or (stage == "checkMesh" and "Mesh OK." not in log):
                tail = "\n".join(log.splitlines()[-40:])
                raise RuntimeError(f"{refusal or 'stage rejected'}\n{tail}")
            if _disk_bytes(case) > budgets.disk_gb * 1_000_000_000:
                raise RuntimeError("disk budget exceeded")
        ledger.transition(job_id, "postprocessing")
        output_hashes = {str(path.relative_to(case)): {"sha256": _sha_file(path), "bytes": path.stat().st_size}
                         for path in case.rglob("*") if path.is_file()
                         and str(path.relative_to(case)) not in input_hashes}
        if time.monotonic() >= deadline:
            raise RuntimeError("wall time budget exceeded during output hashing")
        record = {"job_id": job_id, "image_digest": image_digest, "case_dir": str(case),
                  "inputs": input_hashes, "outputs": output_hashes, "stages": stage_records,
                  "evidence": "unverified", "wall_time_s": time.monotonic() - pipeline_started,
                  "disk_bytes": _disk_bytes(case)}
        encoded = json.dumps(record, sort_keys=True, indent=2, allow_nan=False).encode()
        (case / "run_record.json").write_bytes(encoded)
        digest = store.put_bytes(encoded, kind="run_record", meta={"job_id": job_id})
        ledger.append_event(job_id, {"run_record_sha256": digest, "evidence": "unverified"})
        ledger.transition(job_id, "completed")
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        if ledger.get(job_id).state != "cancelled":
            ledger.transition(job_id, "failed", reason=f"{stage}: {exc}")
    return job_id
