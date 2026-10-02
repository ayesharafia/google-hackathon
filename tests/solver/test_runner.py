import json
from pathlib import Path

from physimesh.core.artifacts import ArtifactStore
from physimesh.core.jobs import Budgets, JobLedger
from physimesh.solver.runner import run_case

IMAGE = "fixture/openfoam@sha256:" + "a" * 64


def _resources(tmp_path):
    return JobLedger(tmp_path / "jobs.sqlite"), ArtifactStore(tmp_path / "store")


def test_mesh_failure_stops_pipeline_and_retains_log(tmp_path, monkeypatch):
    ledger, store = _resources(tmp_path)
    calls = []

    def fake_args(image, workdir, command, budgets):
        calls.append(command[-1])
        if "snappyHexMesh" in command[-1]:
            return ["sh", "-c", "echo mesh-failed; exit 1"]
        return ["sh", "-c", "echo passed"]

    monkeypatch.setattr("physimesh.solver.runner.docker_run_args", fake_args)
    job_id = run_case(ledger, store, {"system/controlDict": b"fixture"}, IMAGE,
                      Budgets(1, 1, 1, 10, 64), tmp_path / "runs")
    job = ledger.get(job_id)
    assert job.state == "failed"
    assert "snappyHexMesh" in job.reason and "mesh-failed" in job.reason
    assert len(calls) == 2
    events = [json.loads(row[0]) for row in ledger.db.execute(
        "SELECT event FROM events WHERE job_id=?", (job_id,))]
    with store.open(events[-1]["log_sha256"]) as log:
        assert b"mesh-failed" in log.read()


def test_success_retains_four_logs_without_claiming_physics(tmp_path, monkeypatch):
    ledger, store = _resources(tmp_path)
    older_job = ledger.submit("other", {}, Budgets(1, 1, 1, 10, 64))
    monkeypatch.setattr("physimesh.solver.runner.docker_run_args",
                        lambda *args: ["sh", "-c", "echo 'Mesh OK.'"])
    job_id = run_case(ledger, store, {"system/controlDict": b"fixture"}, IMAGE,
                      Budgets(1, 1, 1, 10, 64), tmp_path / "runs")
    assert ledger.get(job_id).state == "completed"
    assert ledger.get(older_job).state == "queued"
    events = [json.loads(row[0]) for row in ledger.db.execute(
        "SELECT event FROM events WHERE job_id=?", (job_id,))]
    assert len([event for event in events if "log_sha256" in event]) == 4
    assert events[-1]["evidence"] == "unverified"
    assert (Path(ledger.get(job_id).payload["case_dir"]) / "run_record.json").is_file()


def test_wall_time_budget_stops_process(tmp_path, monkeypatch):
    ledger, store = _resources(tmp_path)
    monkeypatch.setattr("physimesh.solver.runner.docker_run_args",
                        lambda *args: ["sh", "-c", "sleep 10"])
    job_id = run_case(ledger, store, {"system/controlDict": b"fixture"}, IMAGE,
                      Budgets(1, 1, 1, 1, 64), tmp_path / "runs")
    assert ledger.get(job_id).state == "failed"
    assert "wall time budget" in ledger.get(job_id).reason
