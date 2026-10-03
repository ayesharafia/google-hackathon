"""Completed demo reuse refuses stale inputs and tampered native evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('demo_run', Path(__file__).parents[2]/'scripts/demo_run.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def test_reuse_checks_inputs_and_outputs(tmp_path, monkeypatch):
    inputs = {'system/controlDict': b'approved'}
    monkeypatch.setattr(demo, 'external_steady_case', lambda _: inputs)
    output = tmp_path/'native'; output.write_bytes(b'retained')
    record = {'image_digest': demo.IMAGE,
              'inputs': {k: hashlib.sha256(v).hexdigest() for k, v in inputs.items()},
              'outputs': {'native': {'bytes': 8, 'sha256': hashlib.sha256(b'retained').hexdigest()}}}
    raw = json.dumps(record).encode(); (tmp_path/'run_record.json').write_bytes(raw)
    group = {'image_digest': demo.IMAGE, 'iteration_cap': 3000,
             'meshes': [{'level': 'fine', 'state': 'completed', 'case_dir': str(tmp_path),
                         'run_record_sha256': hashlib.sha256(raw).hexdigest()}]}
    demo.reuse_group(group, {'fine': None}, ['fine'], 3000)
    output.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='output hash differs'):
        demo.reuse_group(group, {'fine': None}, ['fine'], 3000)
    output.write_bytes(b'retained'); inputs['system/controlDict'] = b'changed'
    with pytest.raises(ValueError, match='input hashes differ'):
        demo.reuse_group(group, {'fine': None}, ['fine'], 3000)


def test_future_demo_registers_policy_in_generated_job_inputs(monkeypatch):
    from physimesh.postpro.slice_eligibility import REGISTRATION_INPUT, registration_input
    monkeypatch.setattr(demo, 'external_steady_case', lambda _: {'system/controlDict': b'original'})
    inputs = demo.registered_case_files(None)
    assert inputs[REGISTRATION_INPUT] == registration_input()
    assert json.loads(inputs[REGISTRATION_INPUT])['policy_sha256'] == '8744e2b764df40d4975b0cafc31c2dd7462099643f83a8b91eea69080abdd5b1'
