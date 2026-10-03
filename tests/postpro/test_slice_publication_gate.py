import gzip
import hashlib
import json
import sys
from pathlib import Path

import pytest

from physimesh.postpro.slice_eligibility import native_slice_reports, validate_native_reports

FIXTURE = Path(__file__).parents[1]/'solver/fixtures/sphere_coarse'


def native(tmp_path):
    case = tmp_path/'native'
    outputs = {}
    for filename in ('U_yNormal.raw', 'p_yNormal.raw', 'vorticity_yNormal.raw'):
        name = 'postProcessing/cuttingPlane/812/'+filename
        raw = gzip.decompress((FIXTURE/(name+'.gz')).read_bytes())
        path = case/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        outputs[name] = {'sha256': hashlib.sha256(raw).hexdigest()}
    record = json.dumps({'outputs': outputs}).encode()
    (case/'run_record.json').write_bytes(record)
    return {'case_dir': str(case), 'final_time': '812', 'run_record_sha256': hashlib.sha256(record).hexdigest()}


def test_fabricated_status_cannot_override_native_sensitivity(tmp_path):
    mesh = native(tmp_path)
    report = native_slice_reports(mesh, rho=1, diameter_m=1)
    assert report['vorticity']['status'] == 'refused'
    report['vorticity']['status'] = 'eligible_visualization_only'
    report['vorticity']['reasons'] = []
    with pytest.raises(ValueError, match='reprocessed native'):
        validate_native_reports(mesh, report, rho=1, diameter_m=1)


def test_native_byte_mutation_refused_before_eligibility(tmp_path):
    mesh = native(tmp_path)
    report = native_slice_reports(mesh, rho=1, diameter_m=1)
    path = Path(mesh['case_dir'])/'postProcessing/cuttingPlane/812/p_yNormal.raw'
    path.write_bytes(path.read_bytes()+b'\n# changed\n')
    with pytest.raises(ValueError, match='source changed'):
        validate_native_reports(mesh, report, rho=1, diameter_m=1)


def test_assembly_refuses_unsupported_slice_even_with_matching_fabricated_recipe(tmp_path, monkeypatch):
    import scripts.demo_assemble as assembly

    mesh = native(tmp_path) | {'level': 'coarse'}
    group = {'meshes': [mesh], 'D_m': 1, 'rho_ref_kg_m3': 1}
    path = tmp_path/'run_group.json'
    path.write_text(json.dumps(group))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path/'load_results.json').write_text(json.dumps({'run_group_sha256': digest}))
    report = native_slice_reports(mesh, rho=1, diameter_m=1)
    report['vorticity']['status'] = 'eligible_visualization_only'
    report['vorticity']['reasons'] = []
    (tmp_path/'slice_eligibility.json').write_text(json.dumps({'coarse': report}))
    (tmp_path/'plots').mkdir()
    # Matching copied report cannot bless the corrupted eligibility.
    (tmp_path/'plots/index.json').write_text(json.dumps([{'slice_eligibility': report}]))
    monkeypatch.setattr(assembly, 'assemble_results', lambda *args, **kwargs: {'run_group_id': digest[:16], 'limitations': []})
    monkeypatch.setattr(assembly, 'interpret', lambda result: [])
    monkeypatch.setattr(sys, 'argv', ['demo_assemble', '--run-group', str(path), '--data-root', str(tmp_path/'published')])
    with pytest.raises(ValueError, match='reprocessed native'):
        assembly.main()
    assert not (tmp_path/'published/results').exists()


def test_registration_requires_exact_retained_pre_execution_input(tmp_path):
    from physimesh.postpro.slice_eligibility import (
        REGISTRATION_INPUT,
        registration_for_run,
        registration_input,
    )
    mesh = native(tmp_path)
    case = Path(mesh['case_dir'])
    record = json.loads((case/'run_record.json').read_bytes())
    assert registration_for_run(case, record)['state'] == 'retrospective'
    raw = registration_input()
    path = case/REGISTRATION_INPUT
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(raw)
    record['inputs'] = {REGISTRATION_INPUT: hashlib.sha256(raw).hexdigest()}
    assert registration_for_run(case, record)['state'] == 'pre_execution_input'
    path.write_bytes(raw.replace(b'sphere_slice_policy_v3', b'sphere_slice_policy_v9'))
    with pytest.raises(ValueError, match='pre-execution slice registration'):
        registration_for_run(case, record)


@pytest.mark.parametrize('version', ['sphere_slice_policy_v1', 'sphere_slice_policy_v2', 'sphere_slice_policy_v3'])
def test_historical_and_current_registered_policies_replay_with_original_version(tmp_path, version):
    from physimesh.postpro.slice_eligibility import REGISTRATION_INPUT, registration_input
    mesh = native(tmp_path)
    case = Path(mesh['case_dir'])
    record = json.loads((case/'run_record.json').read_bytes())
    raw = registration_input(version)
    path = case/REGISTRATION_INPUT
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(raw)
    record['inputs'] = {REGISTRATION_INPUT: hashlib.sha256(raw).hexdigest()}
    record_raw = json.dumps(record).encode()
    (case/'run_record.json').write_bytes(record_raw)
    mesh['run_record_sha256'] = hashlib.sha256(record_raw).hexdigest()
    reports = native_slice_reports(mesh, rho=1, diameter_m=1)
    assert all(report['policy']['schema_version'] == version for report in reports.values())
    assert all(report['registration']['policy_version'] == version for report in reports.values())
    validate_native_reports(mesh, reports, rho=1, diameter_m=1)
