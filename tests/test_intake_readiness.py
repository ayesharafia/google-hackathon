"""Intake declarations never establish scientific/flight acceptance."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('intake_readiness', ROOT / 'scripts/qa/intake_readiness.py')
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)
FIXTURES = ROOT / 'tests/fixtures/intake_readiness'


def complete():
    return qa.load_packet(FIXTURES / 'complete.json')


def test_complete_declarations_are_not_acceptance():
    report = qa.inspect_packet(complete())
    assert report['inventory_state'] == 'complete_declarations'
    assert report['model_acceptance'] == report['engineering_acceptance'] == report['flight_readiness'] == 'not_assessed'
    assert report['source_verification'] == 'not_performed'
    assert report['purpose_input_readiness']['feasibility']['state'] == 'inputs_incomplete'
    assert len(report['canonical_packet_sha256']) == 64


def test_incomplete_has_all_three_gap_kinds():
    report = qa.inspect_packet(qa.load_packet(FIXTURES / 'incomplete.json'))
    assert report['inventory_state'] == 'incomplete_declarations'
    assert {'missing', 'unknown', 'unsupported'} <= {entry['state'] for entry in report['findings']}


@pytest.mark.parametrize('group,field', [('geometry','revision_sha256'), ('geometry','body_frame'),
                                      ('geometry','transforms'), ('geometry','component_roles'),
                                      ('mission','case_ids'), ('mission','segment_ids'), ('electrical','pack_mode')])
def test_metadata_must_bind_snapshot(group, field):
    packet = complete()
    packet['inventory'][group][field] = 'incorrect-secret-value'
    report = qa.inspect_packet(packet)
    assert report['inventory_state'] == 'incomplete_declarations'
    assert 'incorrect-secret-value' not in json.dumps(report)


@pytest.mark.parametrize('field', ['rotor_id', 'map_ref'])
def test_rotor_binding(field):
    packet = complete()
    packet['inventory']['rotors'][0][field] = 'wrong'
    assert qa.inspect_packet(packet)['inventory_state'] == 'incomplete_declarations'


@pytest.mark.parametrize('value', [True, 123, {}, {'source':'secret'}])
def test_source_must_be_string(value):
    packet = complete()
    packet['inventory']['rotors'][0]['raw_source_ref'] = value
    assert qa.inspect_packet(packet)['inventory_state'] == 'incomplete_declarations'


def test_source_refs_are_opaque_and_no_secret_output(tmp_path):
    packet = complete()
    packet['inventory']['rotors'][0]['raw_source_ref'] = '/missing/client-secret.csv'
    packet['project']['rotors'][0]['client_secret_key'] = 'confidential-token'
    report = qa.inspect_packet(packet)
    assert report['inventory_state'] == 'complete_declarations'
    assert 'confidential-token' not in json.dumps(report)
    assert 'client_secret_key' not in json.dumps(report)
    assert '/missing/' not in json.dumps(report)


def test_malformed_nested_inputs_sanitized():
    packet = complete()
    packet['project']['assembly']['components'] = 42
    report = qa.inspect_packet(packet)
    assert report['purpose_input_readiness']['cfd_run']['state'] == 'unsupported_input_structure'


@pytest.mark.parametrize('raw', ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e999}', '['*40+']'*40])
def test_bad_json_rejected(tmp_path, raw):
    path = tmp_path / 'bad.json'
    path.write_text(raw)
    with pytest.raises((ValueError, RecursionError)):
        qa.load_packet(path)


def test_size_and_symlink_rejected(tmp_path):
    path = tmp_path / 'large.json'
    path.write_bytes(b' ' * (qa.MAX_BYTES + 1))
    with pytest.raises(ValueError):
        qa.load_packet(path)
    link = tmp_path / 'link'
    link.symlink_to(FIXTURES / 'complete.json')
    with pytest.raises(OSError):
        qa.load_packet(link)


def test_cli_exit_codes_receipts_and_preservation(tmp_path, capsys):
    receipt = tmp_path / 'receipt.json'
    assert qa.main(['--input', str(FIXTURES/'complete.json'), '--output', str(receipt)]) == 0
    previous = receipt.read_bytes()
    assert qa.main(['--input', str(FIXTURES/'incomplete.json'), '--output', str(receipt)]) == 2
    assert receipt.read_bytes() == previous
    assert qa.main(['--input', str(FIXTURES/'incomplete.json'), '--output', str(tmp_path/'gaps.json')]) == 1
    captured = capsys.readouterr()
    assert str(tmp_path) not in captured.err


def test_invalid_schema_never_creates_receipt(tmp_path, capsys):
    path = tmp_path / 'input.json'
    path.write_text('{"secret-key":"secret-value"}')
    output = tmp_path / 'output.json'
    assert qa.main(['--input', str(path), '--output', str(output)]) == 2
    assert not output.exists()
    assert 'secret' not in capsys.readouterr().err


def test_mission_condition_binding_and_hash():
    packet = complete()
    original = qa.inspect_packet(packet)
    altered = copy.deepcopy(packet)
    altered['project']['mission']['cases'][0]['velocity_world_m_s'][0] = 2
    report = qa.inspect_packet(altered)
    assert report['mission_contract'] == 'missing_or_invalid_bound_declaration'
    assert report['canonical_packet_sha256'] != original['canonical_packet_sha256']
