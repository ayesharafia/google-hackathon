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
