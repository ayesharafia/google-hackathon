import threading

import pytest

from physimesh.core.jobs import Budgets, JobLedger

B = Budgets(cpu_cores=2, memory_gb=4, disk_gb=10, wall_time_s=3600, pids_limit=512)


def test_lifecycle_and_illegal_transition(tmp_path):
    led = JobLedger(tmp_path / "jobs.sqlite")
    jid = led.submit("mesh", {"x": 1}, B)
    assert led.get(jid).state == "queued"
    with pytest.raises(ValueError):
        led.transition(jid, "completed")              # queued -> completed is illegal
    led.transition(jid, "cancelled")
    assert led.get(jid).state == "cancelled"


def test_claim_is_atomic(tmp_path):
    led = JobLedger(tmp_path / "jobs.sqlite")
    led.submit("run", {}, B)
    got = []
    ts = [threading.Thread(target=lambda w=w: got.append(JobLedger(tmp_path / "jobs.sqlite").claim_next(w)))
          for w in ("w1", "w2", "w3")]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert sum(j is not None for j in got) == 1


def test_state_survives_restart(tmp_path):
    jid = JobLedger(tmp_path / "jobs.sqlite").submit("run", {}, B)
    assert JobLedger(tmp_path / "jobs.sqlite").get(jid).state == "queued"


def test_orphaned_running_job_marked_failed_interrupted(tmp_path):
    led = JobLedger(tmp_path / "jobs.sqlite")
    jid = led.submit("run", {}, B)
    led.claim_next("dead-worker")                     # -> preparing
    led.transition(jid, "running")
    assert led.mark_interrupted(live_worker_ids=set()) == [jid]
    j = led.get(jid)
    assert j.state == "failed" and j.reason == "interrupted"   # never silently resumed


@pytest.mark.parametrize("value", [None, 0, -1, float("nan"), float("inf"), True])
def test_invalid_resource_budget_is_rejected(value):
    with pytest.raises(ValueError):
        Budgets(value, 1, 1, 1, 64)


def test_events_require_existing_job(tmp_path):
    ledger = JobLedger(tmp_path / "jobs.sqlite")
    with pytest.raises(KeyError):
        ledger.append_event("missing", {"message": "orphan"})


def test_terminal_state_cannot_be_overwritten(tmp_path):
    ledger = JobLedger(tmp_path / "jobs.sqlite")
    jid = ledger.submit("run", {}, B)
    ledger.claim_next("worker")
    second = JobLedger(tmp_path / "jobs.sqlite")
    ledger.transition(jid, "cancelled")
    with pytest.raises(ValueError):
        second.transition(jid, "running")
    assert second.get(jid).state == "cancelled"
