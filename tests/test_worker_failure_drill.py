"""Process exit during procfs inspection must not fail the recovery drill."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/qa/worker_failure_drill.py'
spec = importlib.util.spec_from_file_location('worker_failure_drill', SCRIPT)
drill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drill)


@pytest.mark.parametrize('error', [FileNotFoundError, ProcessLookupError])
def test_child_exit_during_stat_read(monkeypatch, error):
    def read(path):
        assert str(path) == '/proc/123/stat'
        raise error()

    monkeypatch.setattr(Path, 'read_text', read)
    assert drill.compute_child_stopped(123)


@pytest.mark.parametrize('state, stopped', [('Z', True), ('R', False), ('S', False)])
def test_child_state(monkeypatch, state, stopped):
    monkeypatch.setattr(Path, 'read_text', lambda path: f'123 (compute (child)) {state} 1 2')
    assert drill.compute_child_stopped(123) is stopped


def test_unexpected_proc_error_is_not_hidden(monkeypatch):
    def read(path):
        raise PermissionError()

    monkeypatch.setattr(Path, 'read_text', read)
    with pytest.raises(PermissionError):
        drill.compute_child_stopped(123)
