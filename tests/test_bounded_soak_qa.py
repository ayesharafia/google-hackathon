"""Independent QA of bounded-soak stop accounting and actual ledger fences."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from physimesh.platform.database import MetadataDB
from physimesh.platform.identity import Identity
from physimesh.platform.jobs import Jobs, StaleAttempt

SPEC = importlib.util.spec_from_file_location(
    'bounded_soak_qa_target', Path(__file__).resolve().parents[1]/'scripts/qa/bounded_soak.py')
soak = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = soak
SPEC.loader.exec_module(soak)


@pytest.mark.parametrize('seconds', [float('nan'), float('inf'), -1, 0, 60.001])
def test_nonfinite_and_out_of_range_duration(seconds):
    with pytest.raises(ValueError):
        soak.Budgets(seconds=seconds).validate()


def test_request_exception_is_counted_without_secret_retention():
    class Client:
        def request(self, *args, **kwargs):
            raise RuntimeError('Bearer synthetic-secret password=synthetic-password')

    runner = soak.Runner(Client(), lambda: None, soak.Budgets(requests=1))
    with pytest.raises(soak.StopRun, match='request_exception'):
        runner.request('POST', '/private-secret-path')
    with pytest.raises(soak.StopRun, match='request_budget'):
        runner.request('POST', '/other')
    raw = json.dumps(runner.report)
    assert runner.report['requests'] == 1
    assert len(runner.report['request_observations']) == 1
    assert 'synthetic-secret' not in raw and 'password' not in raw and 'private-secret-path' not in raw


def test_cleanup_cancels_queued_running_but_preserves_completed(tmp_path):
    database = MetadataDB(tmp_path/'projects.sqlite')
    identity = Identity(database)
    owner = identity.provision('qa@example.test', password='qa-synthetic-password-123')
    org = identity.organization(owner, 'QA synthetic')
    principal = identity.session(identity.login('qa@example.test', 'qa-synthetic-password-123')['token'])
    identity.claim_project(principal, org, 'qa_project')
    jobs = Jobs(database)
    done = jobs.submit('qa_project', 'study', {'revision': 'done'})
    completed_claim = jobs.claim('qa-worker')
    jobs.complete(completed_claim, {'artifact': 'retained'})
    active = jobs.submit('qa_project', 'study', {'revision': 'running'})
    active_claim = jobs.claim('qa-worker')
    queued = jobs.submit('qa_project', 'study', {'revision': 'queued'})
    result = soak.cleanup_jobs(tmp_path)
    assert result['cleanup_error'] is None
    assert result['cancelled_unfinished'] == 2
    assert result['stale_completion_checks'] == 1
    for job in (active, queued):
        retained = jobs.get('qa_project', job['job_id'])
        assert retained['state'] == 'cancelled'
        assert retained['result_json'] is None
    with pytest.raises(StaleAttempt):
        jobs.complete(active_claim, {'artifact': 'must-never-publish'})
    assert jobs.get('qa_project', done['job_id'])['result_json'] == json.dumps({'artifact': 'retained'}, sort_keys=True)
    assert soak.cleanup_jobs(tmp_path)['cancelled_unfinished'] == 0
    database.close()


def test_pid_reuse_and_unrelated_processes_are_not_owned():
    table = {10: (1, 999, 10, 20), 11: (10, 200, 10, 20), 12: (1, 300, 10, 20)}
    owned = {10: 100}
    soak.discover(table, owned)
    assert owned == {10: 100}


def test_namespace_mismatch_fails_before_process_creation(monkeypatch):
    monkeypatch.setattr(soak, 'compatible_process_namespace', lambda: False)

    def forbidden(*args, **kwargs):
        pytest.fail('must not create or signal any subprocess on namespace mismatch')

    monkeypatch.setattr(soak.subprocess, 'Popen', forbidden)
    monkeypatch.setattr(soak.os, 'kill', forbidden)
    report = soak.run(soak.Budgets())
    assert report['stop_reason'] == 'incompatible_proc_pid_namespace'
    assert report['processes_started'] == 0
    assert report['completed_journeys'] == 0
    assert report['samples'] == []


@pytest.mark.parametrize('wait_recovers', [True, False])
def test_process_wait_timeout_still_retains_ledger_cleanup_and_receipt(monkeypatch, wait_recovers):
    """A delayed reap must not skip cancellation/fencing or lose observations."""
    class Process:
        pid = 987654
        returncode = None

        def __init__(self):
            self.waits = 0
            self.killed = False

        def poll(self):
            return 0  # Monitor has ended; exercise the cleanup path directly.

        def kill(self):
            self.killed = True

        def wait(self, timeout):
            self.waits += 1
            if self.waits == 1 or not wait_recovers:
                raise soak.subprocess.TimeoutExpired('synthetic process', timeout)
            self.returncode = -9
            return self.returncode

    process, cleanups = Process(), []
    monkeypatch.setattr(soak, 'compatible_process_namespace', lambda: True)
    monkeypatch.setattr(soak.subprocess, 'Popen', lambda *a, **k: process)
    monkeypatch.setattr(soak, 'processes', dict)
    monkeypatch.setattr(soak, 'cleanup_jobs', lambda root: cleanups.append(root) or {'cleanup_error': None})
    report = soak.run(soak.Budgets(journeys=1))
    assert process.killed and process.waits == 2
    assert len(cleanups) == 1
    assert report['disposable_directory_removed']
    assert report['process_cleanup_error'] == (None if wait_recovers else 'process_wait_timeout')
    assert report['child_exit_code'] == (-9 if wait_recovers else None)


def test_cli_retains_process_cleanup_failure_and_exits_nonzero(monkeypatch, tmp_path):
    report = {'stop_reason': 'journey_budget', 'completed_journeys': 1, 'requests': 13,
              'failures': 0, 'cleanup_error': None, 'child_exit_code': 0,
              'owned_process_survivors_after_kill': 0, 'process_cleanup_error': 'process_wait_timeout'}
    monkeypatch.setattr(soak, 'run', lambda budgets: report)
    receipt = tmp_path/'receipt.json'
    assert soak.main(['--journeys', '1', '--receipt', str(receipt)]) == 1
    assert json.loads(receipt.read_text()) == report
