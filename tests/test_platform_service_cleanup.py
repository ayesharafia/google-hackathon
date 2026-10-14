"""The CI always-run cleanup must be safe when earlier setup did not run."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1]/'scripts/qa/platform_services.py'
spec = importlib.util.spec_from_file_location('platform_services', SCRIPT)
services = importlib.util.module_from_spec(spec)
spec.loader.exec_module(services)


def test_cleanup_without_prior_start_is_successful_and_repeatable(tmp_path):
    state = tmp_path/'service-state'
    for _ in range(2):
        result = subprocess.run([sys.executable, str(SCRIPT), 'stop', '--state', str(state)],
                                capture_output=True, text=True, timeout=10, check=False)
        assert result.returncode == 0, result.stderr
        assert 'nothing to stop' in result.stdout
        assert not result.stderr
        assert not (state/'private.json').exists()


def test_cleanup_failure_preserves_private_state_for_retry(tmp_path, monkeypatch):
    state = tmp_path/'private.json'
    record = {'container': 'physimesh-pg-fixture', 'url': 'synthetic-private-url'}
    state.write_text(json.dumps(record))
    monkeypatch.setattr(sys, 'argv', [str(SCRIPT), 'stop', '--state', str(tmp_path)])

    def fail(command, **kwargs):
        assert command == ['docker', 'rm', '-f', record['container']]
        assert kwargs == {'check': True, 'capture_output': True}
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(services.subprocess, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError):
        services.main()
    assert json.loads(state.read_text()) == record
