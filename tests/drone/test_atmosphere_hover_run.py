"""Run-record integrity and strict stdin/stdout contract checks."""

import io
import json
import os
import platform
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import numpy
import pytest
import scipy

from physimesh.drone import atmosphere_hover_run as runner
from physimesh.drone.provenance import canonical_json, sha256_record
from tests.drone.test_atmosphere_hover_workflow import workflow_request


def assert_closed(record):
    assert record['status'] == 'NUMERICAL_FAILED'
    assert record['result']['outputs'] == {}
    assert record['result']['stages'] == []
    assert record['result']['transfers'] == []
    assert 'request' not in record
    assert 'request_sha256' not in record
    assert 'inputs_sha256' not in record['result']


@pytest.mark.parametrize('annuli', [8, 2048])
def test_nominal_record_matches_workflow_and_hashes(annuli):
    request = workflow_request()
    request['rotor']['annuli'] = annuli
    original = deepcopy(request)
    expected = runner.workflow.evaluate_atmosphere_hover(request)
    record = runner.run_record(request)
    assert record['status'] == 'COMPUTED_EXPERIMENTAL'
    assert record['result'] == expected
    assert record['request'] == original == request
    assert record['request_sha256'] == expected['inputs_sha256'] == sha256_record(original)
    assert record['result_sha256'] == sha256_record(expected)
    for stage in record['result']['stages']:
        assert stage['inputs_sha256'] == sha256_record(stage['inputs'])
        assert stage['result_sha256'] == sha256_record(stage['result'])
    assert record['environment'] == {
        'python_version': platform.python_version(),
        'numpy_version': numpy.__version__,
        'scipy_version': scipy.__version__,
        'runtime_code_identity': 'NOT_ESTABLISHED',
        'portability': 'NOT_ESTABLISHED',
        'replay': 'NOT_ESTABLISHED',
    }
    assert set(record) == {
        'schema_version', 'kind', 'status', 'evidence_level', 'physical_validation',
        'numerical_qualification', 'aircraft_status', 'feasibility', 'bindings',
        'environment', 'hash_semantics', 'result', 'result_sha256', 'request', 'request_sha256',
    }
    assert record['physical_validation'] == record['numerical_qualification'] == 'NOT_ESTABLISHED'
    assert record['evidence_level'] == 'unverified'
    assert record['aircraft_status'] is record['feasibility'] is None
    assert json.loads(canonical_json(record)) == record


def test_component_refusal_retains_atmosphere_and_admitted_request():
    request = workflow_request()
    request['rotor']['annuli'] = 0
    record = runner.run_record(request)
    assert record['status'] == 'MODEL_INAPPLICABLE'
    assert record['result']['outputs'] == {}
    assert [stage['stage_id'] for stage in record['result']['stages']] == ['atmosphere']
    assert record['request'] == request
    assert record['request_sha256'] == sha256_record(request)


def test_schema_refusal_does_not_echo_request():
    record = runner.run_record({'private_marker': 'do-not-echo'})
    assert record['status'] == 'MODEL_INAPPLICABLE'
    assert 'request' not in record
    assert 'do-not-echo' not in canonical_json(record)


def test_arbitrary_object_hooks_are_never_called():
    class Trap:
        def __repr__(self):
            raise AssertionError('repr called')

        def __deepcopy__(self, memo):
            raise AssertionError('deepcopy called')

    for request in (Trap(), {'private_marker': Trap()}):
        record = runner.run_record(request)
        assert record['status'] == 'MODEL_INAPPLICABLE'
        assert 'request' not in record


def test_workflow_mutation_isolated_before_and_after_computation(monkeypatch):
    request = workflow_request()
    original = deepcopy(request)
    actual = runner.workflow.evaluate_atmosphere_hover

    def mutate_after(received):
        result = actual(received)
        received['rotor']['annuli'] = 999
        return result

    monkeypatch.setattr(runner.workflow, 'evaluate_atmosphere_hover', mutate_after)
    record = runner.run_record(request)
    assert record['status'] == 'COMPUTED_EXPERIMENTAL'
    assert request == original == record['request']
    assert record['request_sha256'] == sha256_record(original)
    request['rotor']['annuli'] = 777
    assert record['request'] == original
    record['request']['rotor']['annuli'] = 666
    assert record['result']['stages'][1]['inputs']['annuli'] == 8

    def mutate_before(received):
        received['rotor']['annuli'] = 9
        return actual(received)

    monkeypatch.setattr(runner.workflow, 'evaluate_atmosphere_hover', mutate_before)
    assert_closed(runner.run_record(original))
    assert original['rotor']['annuli'] == 8


@pytest.mark.parametrize('corruption', [
    'root_hash', 'stage_input_hash', 'stage_result_hash', 'stage_id', 'stage_model', 'stage_order',
])
def test_corrupt_workflow_record_fails_closed(monkeypatch, corruption):
    result = runner.workflow.evaluate_atmosphere_hover(workflow_request())
    if corruption == 'root_hash':
        result['inputs_sha256'] = '0' * 64
    elif corruption == 'stage_order':
        result['stages'].reverse()
    else:
        key = {'stage_input_hash': 'inputs_sha256', 'stage_result_hash': 'result_sha256',
               'stage_id': 'stage_id', 'stage_model': 'model_id'}[corruption]
        result['stages'][0][key] = '0' * 64
    monkeypatch.setattr(runner.workflow, 'evaluate_atmosphere_hover', lambda request: result)
    assert_closed(runner.run_record(workflow_request()))


@pytest.mark.parametrize('case', ['nominal', 'schema', 'refusal'])
def test_main_logical_outcomes(case):
    request = workflow_request()
    expected = 0
    if case == 'schema':
        request = {'private_marker': 'do-not-echo'}
        expected = 1
    elif case == 'refusal':
        request['rotor']['annuli'] = 0
        expected = 1
    output = io.StringIO()
    assert runner.main(io.BytesIO(json.dumps(request).encode()), output) == expected
    line = output.getvalue()
    record = json.loads(line)
    assert line == canonical_json(record) + '\n'
    assert 'do-not-echo' not in line
    assert line.count('\n') == 1


@pytest.mark.parametrize('raw', [
    b'{', b'{} {}', b'{"x":{"secret":1,"secret":2}}', b'NaN', b'Infinity',
    b'-Infinity', b'1e999', b'\xff', b'\xef\xbb\xbf{}', b' ' * 65537,
    b'1' * 1025, b'[' * 2000 + b']' * 2000,
])
def test_main_strict_parse_errors(raw):
    output = io.StringIO()
    assert runner.main(io.BytesIO(raw), output) == 2
    line = output.getvalue()
    record = json.loads(line)
    assert record['status'] == 'INPUT_ERROR'
    assert 'request' not in record
    assert 'secret' not in line
    assert line == canonical_json(record) + '\n'
    assert line.count('\n') == 1


@pytest.mark.parametrize('valid', [True, False])
def test_real_module_stdin_stdout(valid):
    source = str(Path(__file__).resolve().parents[2] / 'src')
    env = dict(os.environ, PYTHONPATH=source, PYTHONDONTWRITEBYTECODE='1')
    payload = json.dumps(workflow_request()).encode() if valid else b'{"secret":'
    completed = subprocess.run(
        [sys.executable, '-m', 'physimesh.drone.atmosphere_hover_run'],
        input=payload, capture_output=True, env=env, check=False, timeout=15,
    )
    assert completed.returncode == (0 if valid else 2)
    assert completed.stderr == b''
    record = json.loads(completed.stdout)
    assert completed.stdout == (canonical_json(record) + '\n').encode()
    assert 'secret' not in completed.stdout.decode()
