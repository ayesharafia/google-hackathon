import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from physimesh.postpro.result_contract import ResultsV1, assemble_results


def inputs():
    group = {'label': 'VERIFICATION CASE: sphere Re=100; no aircraft result', 'code_version': 'a'*40,
             'image_digest': 'opencfd/openfoam-run@sha256:'+'b'*64, 'Re': 100, 'D_m': 1,
             'rho_ref_kg_m3': 1, 'nu_m2_s': .01, 'u_inf_m_s': [1, 0, 0]}
    loads = {'run_group_sha256': 'c'*64, 'runs': [{'level': level, 'cd': 1.1,
              'reconciliation': {'status': 'accepted'}, 'convergence': {'passed': True}} for level in ('coarse', 'medium', 'fine')],
             'mesh_study': {'behaviour': 'monotonic'}}
    return group, loads


def test_diagnostic_status_cannot_be_upgraded_by_assembly():
    group, loads = inputs()
    loads['runs'][1]['reconciliation']['status'] = 'diagnostic_only'
    result = assemble_results(group, loads, [])
    assert result['status'] == 'diagnostic_only'
    assert result['evidence'] == 'unverified'
    assert result['runs'][1]['reconciliation']['status'] == 'diagnostic_only'


def test_results_contract_round_trip_and_published_schema():
    result = assemble_results(*inputs(), [])
    assert ResultsV1.model_validate_json(json.dumps(result)).model_dump(mode='json') == result
    path = Path(__file__).parents[2] / 'src/physimesh/postpro/schema/results_v1.schema.json'
    assert json.loads(path.read_text()) == ResultsV1.model_json_schema()


def test_contract_refuses_missing_provenance_and_nonfinite_nested_numbers():
    result = assemble_results(*inputs(), [])
    result['provenance']['run_group_sha256'] = 'not-a-hash'
    with pytest.raises(ValidationError):
        ResultsV1.model_validate(result)
    result = assemble_results(*inputs(), [])
    result['runs'][0]['cd'] = float('nan')
    with pytest.raises(ValueError):
        ResultsV1.model_validate(result)
