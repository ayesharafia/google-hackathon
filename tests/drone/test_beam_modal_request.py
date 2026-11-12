"""Contract checks for the separate uniform modal request adapter."""
import json
import math
from copy import deepcopy

import pytest

from physimesh.drone.beam_modal import solve_cantilever_modes
from physimesh.drone.beam_modal_request import beam_modal_catalog, evaluate_modal_beam


def modal_request():
    return {
        'evaluation': 'uniform_cantilever_modal_experimental',
        'length_m': 2.0, 'E_pa': 70e9, 'I_m4': 1e-6,
        'mass_per_length_kg_m': 2.0, 'elements': 8, 'modes': 3,
        'property_source': 'Unverified example',
        'applicability_declaration': 'Research uniform ideal cantilever only',
    }


def assert_refused(result, status='MODEL_INAPPLICABLE'):
    assert result['status'] == status
    assert result['outputs'] == result['output_units'] == {}
    assert result['physical_validation'] == 'NOT_ESTABLISHED'
    assert result['evidence_level'] == 'unverified'
    assert result['aircraft_status'] is result['feasibility'] is None
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('elements,modes', [(2, 4), (8, 6), (64, 6)])
def test_core_mapping_and_no_mutation(elements, modes):
    request = modal_request() | {'elements': elements, 'modes': modes}
    original = deepcopy(request)
    core = solve_cantilever_modes(**{k: request[k] for k in (
        'length_m', 'E_pa', 'I_m4', 'mass_per_length_kg_m', 'elements', 'modes')})
    result = evaluate_modal_beam(request)
    assert request == original
    assert core['status'] == 'SUCCESS'
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    assert result['schema_version'] == 'beam_modal_request_v1'
    assert result['model_id'] == 'uniform_cantilever_modal_v1'
    for key in ('inputs', 'modes', 'diagnostics'):
        assert result['outputs'][key] == core[key]
    assert result['limits'] == core['limits']
    assert result['output_units']['modes']['omega_rad_s'] == 'rad/s'
    assert result['output_units']['modes']['frequency_hz'] == 'Hz'
    assert result['output_units']['modes']['normalized_deflection_derivative_xi'] == '1'
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('field', list(modal_request()))
def test_missing(field):
    request = modal_request()
    del request[field]
    assert_refused(evaluate_modal_beam(request))


@pytest.mark.parametrize('field', ['length_m', 'E_pa', 'I_m4', 'mass_per_length_kg_m'])
@pytest.mark.parametrize('value', [True, '1', None, [], math.nan, math.inf, -math.inf, 10**1000])
def test_bad_scalars(field, value):
    assert_refused(evaluate_modal_beam(modal_request() | {field: value}))


@pytest.mark.parametrize('field', ['elements', 'modes'])
@pytest.mark.parametrize('value', [True, 2.0, '2', None, [], math.nan, math.inf, 10**1000])
def test_bad_counts(field, value):
    assert_refused(evaluate_modal_beam(modal_request() | {field: value}))


@pytest.mark.parametrize('field', ['property_source', 'applicability_declaration'])
@pytest.mark.parametrize('value', ['', ' \t\n', 'x' * 2001, 1, True, None, []])
def test_bad_declarations(field, value):
    assert_refused(evaluate_modal_beam(modal_request() | {field: value}))


@pytest.mark.parametrize('change', [
    {'length_m': 0}, {'E_pa': -1}, {'I_m4': 5e-324},
    {'elements': 1}, {'elements': 65}, {'modes': 0}, {'modes': 7},
    {'elements': 2, 'modes': 5}, {'length_m': 1e300},
    {'length_m': 1e-300},
])
def test_exact_core_refusals(change):
    request = modal_request() | change
    core = solve_cantilever_modes(**{k: request[k] for k in (
        'length_m', 'E_pa', 'I_m4', 'mass_per_length_kg_m', 'elements', 'modes')})
    assert core['status'] == 'REFUSED'
    result = evaluate_modal_beam(request)
    assert_refused(result)
    assert result['core_refusal'] == core['refusal']
    assert result['limits'] == core['limits']


def test_closed_structure_and_unsupported():
    for request in (None, [], {}, modal_request() | {'extra': 'secret'},
                    modal_request() | {'evaluation': True}):
        assert_refused(evaluate_modal_beam(request))
    assert_refused(evaluate_modal_beam(modal_request() | {'evaluation': 'unknown'}), 'SOLVER_UNSUPPORTED')


def test_catalog_is_fresh_and_explicit():
    catalog = beam_modal_catalog()
    baseline = deepcopy(catalog)
    assert set(catalog['required_fields']) == set(modal_request())
    assert catalog['request_contract']['defaults'] == {}
    assert catalog['limits']['elements_min'] == 2
    assert catalog['limits']['elements_max'] == 64
    assert catalog['limits']['modes_max'] == 6
    assert catalog['limits']['modes_free_dof_cap'] is True
    assert catalog['physical_validation'] == catalog['numerical_qualification'] == 'NOT_ESTABLISHED'
    assert catalog['mesh_accuracy'] == 'NOT_ESTABLISHED'
    catalog['limits']['elements_max'] = 999
    catalog['required_fields'].clear()
    catalog['input_units']['E_pa'] = 'wrong'
    catalog['limitations'].clear()
    assert beam_modal_catalog() == baseline
    assert evaluate_modal_beam(modal_request())['limits'] == baseline['limits']


def test_declarations_are_literal_unverified_text():
    request = modal_request()
    baseline = evaluate_modal_beam(request)
    request.update(property_source='x' * 2000, applicability_declaration='<script>not evidence</script>')
    result = evaluate_modal_beam(request)
    assert result['outputs'] == baseline['outputs']
    assert result['evidence_level'] == 'unverified'
