"""D1.5 real coarse-sphere execution and retained stage evidence."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from physimesh.core.artifacts import ArtifactStore
from physimesh.core.jobs import Budgets, JobLedger
from physimesh.solver.openfoam_cases import external_steady_case
from physimesh.solver.runner import run_case
from tests.solver.test_external_case import demo_spec

IMAGE = "opencfd/openfoam-run@sha256:4229997e74defb81548222d511b8e3b95b98305e5df41b8e88b031813fe47eeb"


@pytest.mark.backend
def test_coarse_sphere_stage_runner_retains_four_logs():
    root = Path(__file__).resolve().parents[2] / ".backend/sphere-smoke"
    root.mkdir(parents=True, exist_ok=True)
    ledger = JobLedger(root / "jobs.sqlite")
    store = ArtifactStore(root / "artifacts")
    files = external_steady_case(replace(demo_spec(), iterations=20))
    job_id = run_case(ledger, store, files, IMAGE, Budgets(2, 4, 5, 600, 512), root / "runs")
    job = ledger.get(job_id)
    assert job.state == "completed", job.reason
    events = [json.loads(row[0]) for row in ledger.db.execute(
        "SELECT event FROM events WHERE job_id=?", (job_id,))]
    assert len([event for event in events if "log_sha256" in event]) == 4
    for event in events:
        if "log_sha256" in event:
            with store.open(event["log_sha256"]) as log:
                assert log.read()
    case = Path(job.payload["case_dir"])
    record = json.loads((case / "run_record.json").read_text())
    assert "20/p" in record["outputs"] and "20/wallShearStress" in record["outputs"]
    assert record["evidence"] == "unverified"
