"""Bounded orchestration, not a second ledger or self-issued review."""
import copy
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("workflow_gates", Path(__file__).parents[1] / "scripts/qa/workflow_gates.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture
def scoped(tmp_path):
    source = tmp_path / "source.py"
    source.write_text("pass\n")
    queue = tmp_path / ".physicore/ops/TASKS.json"
    queue.parent.mkdir(parents=True)
    queue.write_text(json.dumps({"tasks": [{"id": "TASK-001", "status": "in_progress", "started_at": "test-start"}]}))
    return tmp_path, {"schema_version": 1, "sources": {"source.py": hashlib.sha256(source.read_bytes()).hexdigest()},
                      "gates": [{"id": "test", "argv": ["python", "-m", "pytest"], "timeout_seconds": 1}],
                      "max_repair_attempts": 2, "review_required": True}


def runner(root, manifest, rc=0, outer_rc=None):
    def run(argv, **kwargs):
        assert "workflow.py" in argv[1]
        if "reserve-gate-attempt" in argv:
            return SimpleNamespace(returncode=0, stdout=json.dumps({"attempt": 0, "started_at": "test-start", "max_repair_attempts": 2}))
        assert kwargs["timeout"] == 31
        receipt = root / ".physicore/evidence/result.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({"id": "TASK-001", "argv": manifest["gates"][0]["argv"], "returncode": rc, "repo": str(root), "started_at": "test-start"}))
        return SimpleNamespace(returncode=(0 if rc == 0 else 1) if outer_rc is None else outer_rc,
                               stdout="TEST " + ("PASS" if rc == 0 else "FAIL") + " .physicore/evidence/result.json\n")
    return run


def test_pass_still_requires_review(scoped):
    root, manifest = scoped
    result = MODULE.evaluate(root, manifest, "TASK-001", run=runner(root, manifest))
    assert result["status"] == "blocked"
    assert result["ready_for_review"] is True
    assert result["completion_allowed"] is False
    assert result["gates"][0]["status"] == "passed"


@pytest.mark.parametrize("rc", [1, 124])
def test_failure_and_timeout_stop(scoped, rc):
    root, manifest = scoped
    manifest["gates"].append({"id": "later", "argv": ["python", "-m", "ruff"], "timeout_seconds": 1})
    result = MODULE.evaluate(root, manifest, "TASK-001", run=runner(root, manifest, rc))
    assert result["status"] == "failed"
    assert len(result["gates"]) == 1
    assert result["gates"][0]["timed_out"] is (rc == 124)


@pytest.mark.parametrize("change", ["stale", "missing", "budget"])
def test_preflight_blocks_without_running(scoped, change):
    root, manifest = scoped
    if change == "stale":
        (root / "source.py").write_text("changed")
    elif change == "missing":
        (root / "source.py").unlink()
    result = MODULE.evaluate(root, manifest, "TASK-001", attempt=3 if change == "budget" else 0,
                             run=lambda *a, **kw: pytest.fail("blocked run executed"))
    assert result["status"] == "blocked"
    assert result["gates"] == []


@pytest.mark.parametrize("change", ["version", "review", "path", "command", "timeout", "unknown"])
def test_bad_manifest_refused(scoped, change):
    root, initial = scoped
    manifest = copy.deepcopy(initial)
    if change == "version":
        manifest["schema_version"] = True
    elif change == "review":
        manifest["review_required"] = False
    elif change == "path":
        manifest["sources"] = {"../escape": "a" * 64}
    elif change == "command":
        manifest["gates"][0]["argv"] = ["bash", "-c", "anything"]
    elif change == "timeout":
        manifest["gates"][0]["timeout_seconds"] = 0
    else:
        manifest["skip"] = True
    if change == "path":
        assert MODULE.evaluate(root, manifest, "TASK-001")["status"] == "blocked"
    else:
        with pytest.raises(ValueError):
            MODULE.evaluate(root, manifest, "TASK-001")


def test_missing_receipt_blocked(scoped):
    root, manifest = scoped
    assert MODULE.evaluate(root, manifest, "TASK-001", run=lambda *a, **kw: SimpleNamespace(returncode=0, stdout=""))["status"] == "blocked"


def test_outer_timeout_blocked(scoped):
    root, manifest = scoped
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("workflow", 16)
    assert MODULE.evaluate(root, manifest, "TASK-001", run=timeout)["status"] == "blocked"


def test_source_mutation_after_check_blocks(scoped):
    root, manifest = scoped
    original = runner(root, manifest)
    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        (root / "source.py").write_text("mutation")
        return result
    result = MODULE.evaluate(root, manifest, "TASK-001", run=mutate)
    assert result["status"] == "blocked"
    assert result["reason"] == "source changed during verification"


def test_wrong_task_receipt_blocks(scoped):
    root, manifest = scoped
    original = runner(root, manifest)
    def mismatch(*args, **kwargs):
        result = original(*args, **kwargs)
        receipt = root / ".physicore/evidence/result.json"
        obj = json.loads(receipt.read_text())
        obj["id"] = "OTHER-001"
        receipt.write_text(json.dumps(obj))
        return result
    assert MODULE.evaluate(root, manifest, "TASK-001", run=mismatch)["status"] == "blocked"


@pytest.mark.parametrize("manifest", [None, [], True, 5, "manifest"])
def test_scalar_manifest_refused(manifest):
    with pytest.raises(ValueError):
        MODULE.validate(manifest)


def test_old_receipt_replay_blocks(scoped):
    root, manifest = scoped
    original = runner(root, manifest)
    original(["python", "workflow.py"], timeout=31)
    assert MODULE.evaluate(root, manifest, "TASK-001", run=original)["status"] == "blocked"


def test_wrong_repository_receipt_blocks(scoped):
    root, manifest = scoped
    original = runner(root, manifest)
    def mismatch(*args, **kwargs):
        result = original(*args, **kwargs)
        receipt = root / ".physicore/evidence/result.json"
        obj = json.loads(receipt.read_text())
        obj["repo"] = "/other/repository"
        receipt.write_text(json.dumps(obj))
        return result
    assert MODULE.evaluate(root, manifest, "TASK-001", run=mismatch)["status"] == "blocked"


@pytest.mark.parametrize("command,expected,timed_out", [
    (["python", "-c", "raise SystemExit(7)"], "failed", False),
    (["python", "-c", "import time; time.sleep(3)"], "failed", True),
    (["python", "-c", "print('safe fixture')"], "blocked", False),
])
def test_real_existing_collector_failure_timeout_and_review(scoped, command, expected, timed_out):
    root, manifest = scoped
    workflow = root / ".physicore/tools/workflow.py"
    workflow.parent.mkdir(parents=True)
    workflow.write_bytes((Path(__file__).parents[1] / ".physicore/tools/workflow.py").read_bytes())
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture", "-c", "user.email=fixture@invalid.test",
                    "commit", "--allow-empty", "-qm", "fixture"], check=True)
    queue = {"schema_version": 2, "tasks": [{"id": "TASK-001", "title": "Fixture verification",
             "done_when": "Real existing collector records the bounded fixture result.", "kind": "regression",
             "priority": 3, "status": "in_progress", "zone": "green", "depends_on": [],
             "started_at": "test-start", "started_head": "fixture", "evidence": []}]}
    (root / ".physicore/ops/TASKS.json").write_text(json.dumps(queue))
    manifest["gates"][0]["argv"] = command
    result = MODULE.evaluate(root, manifest, "TASK-001")
    assert result["status"] == expected
    assert result["gates"][0]["timed_out"] is timed_out
    assert result["completion_allowed"] is False


@pytest.mark.parametrize("name", ["TASK-lint-old.json", "nested/old.data"])
def test_nonstandard_old_receipt_replay_blocks(scoped, name):
    root, manifest = scoped
    receipt = root / ".physicore/evidence" / name
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"id": "TASK-001", "argv": manifest["gates"][0]["argv"],
                                  "returncode": 0, "repo": str(root), "started_at": "test-start"}))
    def replay(argv, **kwargs):
        if "reserve-gate-attempt" in argv:
            return SimpleNamespace(returncode=0, stdout=json.dumps({"attempt": 0, "started_at": "test-start", "max_repair_attempts": 2}))
        return SimpleNamespace(returncode=0, stdout="TEST PASS " + str(receipt.relative_to(root)))
    result = MODULE.evaluate(root, manifest, "TASK-001", run=replay)
    assert result["status"] == "blocked"
    assert result["gates"][0]["status"] == "blocked"


def test_started_at_mismatch_blocks(scoped):
    root, manifest = scoped
    original = runner(root, manifest)
    def mismatch(*args, **kwargs):
        result = original(*args, **kwargs)
        receipt = root / ".physicore/evidence/result.json"
        obj = json.loads(receipt.read_text())
        obj["started_at"] = "other-start"
        receipt.write_text(json.dumps(obj))
        return result
    assert MODULE.evaluate(root, manifest, "TASK-001", run=mismatch)["status"] == "blocked"


@pytest.fixture
def budget_collector(scoped):
    root, _manifest = scoped
    workflow = root / ".physicore/tools/workflow.py"
    workflow.parent.mkdir(parents=True)
    workflow.write_bytes((Path(__file__).parents[1] / ".physicore/tools/workflow.py").read_bytes())
    queue = {"schema_version": 2, "tasks": [{"id": "TASK-001", "title": "Fixture verification",
             "done_when": "Existing ledger records persistent bounded gate attempts.", "kind": "regression",
             "priority": 3, "status": "in_progress", "zone": "green", "depends_on": [],
             "started_at": "test-start", "evidence": []}]}
    (root / ".physicore/ops/TASKS.json").write_text(json.dumps(queue))
    return root, workflow


def reserve(workflow, attempt, budget=2):
    import sys
    return subprocess.run([sys.executable, str(workflow), "reserve-gate-attempt", "TASK-001",
                           "--attempt", str(attempt), "--budget", str(budget)], capture_output=True, text=True, check=False)


def test_restart_replay_and_budget_exhaustion(budget_collector):
    root, workflow = budget_collector
    assert reserve(workflow, 0).returncode == 0
    assert reserve(workflow, 0).returncode == 2
    assert reserve(workflow, 2).returncode == 2
    assert reserve(workflow, 1).returncode == 0
    assert reserve(workflow, 2).returncode == 0
    assert reserve(workflow, 3).returncode == 2
    state = json.loads((root / ".physicore/ops/TASKS.json").read_text())["tasks"][0]["gate_attempts"]
    assert state["next_attempt"] == 3


def test_manifest_budget_cannot_expand_or_reset(budget_collector):
    root, workflow = budget_collector
    assert reserve(workflow, 0, 0).returncode == 0
    assert reserve(workflow, 1, 2).returncode == 2
    queue = root / ".physicore/ops/TASKS.json"
    obj = json.loads(queue.read_text())
    obj["tasks"][0]["started_at"] = "new-start"
    queue.write_text(json.dumps(obj))
    assert reserve(workflow, 0, 0).returncode == 2


def test_concurrent_same_attempt_reserves_once(budget_collector):
    from concurrent.futures import ThreadPoolExecutor
    root, workflow = budget_collector
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: reserve(workflow, 0).returncode, range(8)))
    assert results.count(0) == 1
    assert results.count(2) == 7
    state = json.loads((root / ".physicore/ops/TASKS.json").read_text())["tasks"][0]["gate_attempts"]
    assert state["next_attempt"] == 1


def test_concurrent_refresh_preserves_reservation(budget_collector):
    import sys
    from concurrent.futures import ThreadPoolExecutor
    root, workflow = budget_collector
    def refresh(_):
        return subprocess.run([sys.executable, str(workflow), "refresh"], capture_output=True, check=False).returncode
    with ThreadPoolExecutor(max_workers=8) as pool:
        future = pool.submit(reserve, workflow, 0)
        refreshes = list(pool.map(refresh, range(7)))
        assert future.result().returncode == 0
    assert refreshes == [0] * 7
    state = json.loads((root / ".physicore/ops/TASKS.json").read_text())["tasks"][0]["gate_attempts"]
    assert state["next_attempt"] == 1


def test_crashed_lock_holder_does_not_leave_stale_lock(budget_collector):
    import sys
    root, workflow = budget_collector
    lock = root / ".physicore/ops/GATE_ATTEMPTS.lock"
    program = "import fcntl,sys,time;f=open(sys.argv[1],'a');fcntl.flock(f,fcntl.LOCK_EX);print('locked',flush=True);time.sleep(60)"
    process = subprocess.Popen([sys.executable, "-c", program, str(lock)], stdout=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == "locked"
        process.kill()
        process.wait(timeout=5)
        assert lock.exists()
        assert reserve(workflow, 0).returncode == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()


def test_concurrent_block_cannot_erase_reserved_attempt(budget_collector):
    import sys
    from concurrent.futures import ThreadPoolExecutor
    root, workflow = budget_collector
    with ThreadPoolExecutor(max_workers=2) as pool:
        reserved = pool.submit(reserve, workflow, 0)
        blocked = pool.submit(subprocess.run, [sys.executable, str(workflow), "block", "TASK-001", "--reason", "fixture"],
                              capture_output=True, check=False)
        reservation_rc = reserved.result().returncode
        assert blocked.result().returncode == 0
    task = json.loads((root / ".physicore/ops/TASKS.json").read_text())["tasks"][0]
    assert task["status"] == "blocked"
    if reservation_rc == 0:
        assert task["gate_attempts"]["next_attempt"] == 1
    else:
        assert reservation_rc == 2
        assert "gate_attempts" not in task


def test_reservation_outer_timeout_allows_busy_response(scoped):
    root, manifest = scoped
    def busy(argv, **kwargs):
        assert "reserve-gate-attempt" in argv
        assert kwargs["timeout"] == 30  # inner workflow lock budget is15seconds
        return SimpleNamespace(returncode=2, stdout="", stderr="workflow queue busy")
    result = MODULE.evaluate(root, manifest, "TASK-001", run=busy)
    assert result["reason"] == "durable gate attempt unavailable, replayed or exhausted"
    assert result["gates"] == []


@pytest.mark.parametrize("change", ["blocked", "done", "new-start", "new-attempt"])
def test_reserved_check_revalidates_before_launch(budget_collector, change):
    import sys
    root, workflow = budget_collector
    assert reserve(workflow, 0).returncode == 0
    queue = root / ".physicore/ops/TASKS.json"
    data = json.loads(queue.read_text())
    task = data["tasks"][0]
    if change in {"blocked", "done"}:
        task["status"] = change
        if change == "done":
            task["evidence"] = ["fixture"]
    elif change == "new-start":
        task["started_at"] = "new-start"
    else:
        assert reserve(workflow, 1).returncode == 0
        data = json.loads(queue.read_text())
    queue.write_text(json.dumps(data))
    marker = root / "MUST_NOT_EXIST"
    completed = subprocess.run(
        [sys.executable, str(workflow), "check", "--gate-start", "test-start", "--gate-attempt", "0",
         "TASK-001", "--", "python", "-c", "from pathlib import Path;Path('MUST_NOT_EXIST').touch()"],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 2
    assert not marker.exists()
