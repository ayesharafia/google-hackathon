"""Check real storage failure recovery, receipt privacy, and disposable cleanup."""
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/qa/disk_pressure_drill.py'
spec = importlib.util.spec_from_file_location('disk_pressure_drill', SCRIPT)
drill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drill)


def test_real_artifact_and_sqlite_recovery_receipt():
    original = os.link
    result = drill.run_drill()
    assert os.link is original
    assert result['disposable_directory_cleanup'] == 'passed'
    assert [s['partial_object_after_failure'] for s in result['scenarios']] == [False, True]
    for scenario in result['scenarios']:
        assert scenario['attempt_states'] == ['failed', 'expired', 'accepted']
        assert scenario['job_result_after_failure'] is None
        assert scenario['stale_publication_rejected'] == 'passed'
        assert scenario['sqlite_reopen'] == 'passed'
    raw = json.dumps(result)
    assert not re.search(r'(job|attempt)_[0-9a-f]{32}', raw)
    for private in ('worker_id', 'jobs.sqlite', '/tmp/', 'token', 'password'):
        assert private not in raw
    assert 'no actual filesystem exhaustion' in raw
    assert 'cross-store atomic transaction' in result['not_verified']


def test_temp_directory_cleanup_on_unexpected_scenario_failure():
    created = []

    def fail(root, stage):
        created.append(root.parent)
        (root / 'partial').write_bytes(b'bounded')
        raise RuntimeError('synthetic unexpected failure')

    original = os.link
    with patch.object(drill, '_scenario', side_effect=fail), pytest.raises(RuntimeError, match='unexpected'):
        drill.run_drill()
    assert created and not created[0].exists()
    assert os.link is original


def test_injection_patch_restored_on_unexpected_storage_failure(tmp_path):
    original = os.link
    with (patch.object(drill.ArtifactStore, 'put_bytes', side_effect=RuntimeError('unexpected')),
          pytest.raises(RuntimeError, match='unexpected')):
        drill._scenario(tmp_path, 'object')
    assert os.link is original


def test_cli_receipt_and_stdout_match(tmp_path):
    receipt = tmp_path / 'receipt.json'
    result = subprocess.run([sys.executable, str(SCRIPT), '--receipt', str(receipt)],
                            capture_output=True, text=True, timeout=30, check=True,
                            env={**os.environ, 'PYTHONPATH': str(SCRIPT.parents[2] / 'src')})
    assert json.loads(result.stdout) == json.loads(receipt.read_text())
    assert not result.stderr


def test_cli_refuses_to_replace_prior_receipt(tmp_path):
    receipt = tmp_path / 'prior.json'
    receipt.write_text('prior evidence\n')
    result = subprocess.run([sys.executable, str(SCRIPT), '--receipt', str(receipt)],
                            capture_output=True, text=True, timeout=30, check=False,
                            env={**os.environ, 'PYTHONPATH': str(SCRIPT.parents[2] / 'src')})
    assert result.returncode != 0
    assert receipt.read_text() == 'prior evidence\n'
    assert 'receipt already exists' in result.stderr


def test_database_close_when_initial_setup_fails(tmp_path):
    closed = []
    original_close = drill.MetadataDB.close

    def observed_close(database):
        closed.append(database.path)
        original_close(database)

    with (patch.object(drill.Jobs, '__init__', side_effect=RuntimeError('setup failed')),
          patch.object(drill.MetadataDB, 'close', observed_close),
          pytest.raises(RuntimeError, match='setup failed')):
        drill._scenario(tmp_path, 'object')
    assert closed == [tmp_path / 'jobs.sqlite']
