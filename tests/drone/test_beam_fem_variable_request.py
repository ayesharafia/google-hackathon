"""Contract tests for the stateless experimental variable-inertia adapter."""
import math
from copy import deepcopy

import pytest

from physimesh.drone.beam_fem_variable_request import evaluate_variable_beam


@pytest.fixture
def request_data():
    return {
        'evaluation': 'variable_beam_fem_experimental',
        'length_m': 2.0, 'E_pa': 70e9,
        'second_moments_m4': [1e-6, 1.25e-6, 1.5e-6],
        'nodes_m': [0.0, 1.0, 2.0], 'outer_fibre_m': 0.01,
        'tip_force_n': 10.0, 'uniform_load_n_m': 0.0,
        'ramp_load_root_n_m': 0.0, 'ramp_load_tip_n_m': 0.0,
        'tip_moment_n_m': 0.0,
        'probes': [{'element_index': 0, 'local_coordinate': 0.5},
                   {'element_index': 1, 'local_coordinate': 1.0}],
        'property_source': 'Unverified supplier values',
        'applicability_declaration': 'Experimental static cantilever only',
    }


OUTPUT_KEYS = {
    'elements', 'nodes_m', 'second_moments_m4', 'displacements_m',
    'rotations_rad', 'root_force_n', 'root_moment_nm',
    'normalized_linear_residual', 'probes',
}
PROBE_KEYS = {
    'element_index', 'local_coordinate', 'x_m', 'deflection_m',
    'rotation_rad', 'curvature_1_m', 'nominal_bending_stress_pa',
}


def assert_refused(result, status='MODEL_INAPPLICABLE'):
    assert result['status'] == status
    assert result['outputs'] == {}
    assert result['output_units'] == {}
    assert result['reasons']


def test_success_contract_and_no_mutation(request_data):
    original = deepcopy(request_data)
    result = evaluate_variable_beam(request_data)
    assert request_data == original
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    assert result['model_id'] == 'variable_inertia_cantilever_fem_v1'
    assert result['physical_validation'] == 'NOT_ESTABLISHED'
    assert result['evidence_level'] == 'unverified'
    assert result['aircraft_status'] is None
    assert result['feasibility'] is None
    assert result['reasons'] == []
    assert result['limitations']
    assert result['sources']
    assert set(result['outputs']) == OUTPUT_KEYS
    assert set(result['output_units']) == OUTPUT_KEYS
    assert set(result['output_units']['probes']) == PROBE_KEYS
    output = result['outputs']
    assert output['elements'] == 2
    assert output['nodes_m'] == original['nodes_m']
    assert output['second_moments_m4'] == original['second_moments_m4']
    assert output['root_force_n'] == pytest.approx(-10)
    assert output['root_moment_nm'] == pytest.approx(-20)
    assert len(output['probes']) == 2
    for actual, expected in zip(output['probes'], original['probes'], strict=True):
        assert set(actual) == PROBE_KEYS
        assert actual['element_index'] == expected['element_index']
        assert actual['local_coordinate'] == expected['local_coordinate']


def test_constant_inertia_against_independent_tip_load_solution(request_data):
    request_data['second_moments_m4'] = [1e-6] * 3
    request_data['probes'] = [
        {'element_index': element, 'local_coordinate': coordinate}
        for element in (0, 1) for coordinate in (0.0, 0.5, 1.0)
    ]
    result = evaluate_variable_beam(request_data)
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    for probe in result['outputs']['probes']:
        x = probe['x_m']
        length, force, modulus, inertia, fibre = 2.0, 10.0, 70e9, 1e-6, 0.01
        assert probe['deflection_m'] == pytest.approx(
            force * x**2 * (3 * length - x) / (6 * modulus * inertia), abs=1e-12)
        assert probe['rotation_rad'] == pytest.approx(
            force * x * (2 * length - x) / (2 * modulus * inertia), abs=1e-12)
        assert probe['curvature_1_m'] == pytest.approx(
            force * (length - x) / (modulus * inertia), abs=1e-12)
        assert probe['nominal_bending_stress_pa'] == pytest.approx(
            force * fibre * (length - x) / inertia, abs=1e-6)


def test_zero_loads_and_one_sided_endpoints(request_data):
    request_data['tip_force_n'] = 0
    request_data['probes'] = [
        {'element_index': 0, 'local_coordinate': 1},
        {'element_index': 1, 'local_coordinate': 0},
    ]
    result = evaluate_variable_beam(request_data)
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    output = result['outputs']
    assert output['displacements_m'] == [0.0] * 3
    assert output['rotations_rad'] == [0.0] * 3
    for probe in output['probes']:
        assert probe['x_m'] == 1.0
        for key in PROBE_KEYS - {'element_index', 'local_coordinate', 'x_m'}:
            assert probe[key] == 0.0


@pytest.mark.parametrize('field', [
    'length_m', 'E_pa', 'outer_fibre_m', 'tip_force_n', 'uniform_load_n_m',
    'ramp_load_root_n_m', 'ramp_load_tip_n_m', 'tip_moment_n_m',
])
@pytest.mark.parametrize('value', [True, '1', None, math.nan, math.inf, -math.inf, 10**1000])
def test_reject_invalid_scalar_types(request_data, field, value):
    request_data[field] = value
    assert_refused(evaluate_variable_beam(request_data))


@pytest.mark.parametrize('field', [
    'evaluation', 'length_m', 'E_pa', 'second_moments_m4', 'nodes_m',
    'outer_fibre_m', 'tip_force_n', 'uniform_load_n_m',
    'ramp_load_root_n_m', 'ramp_load_tip_n_m', 'tip_moment_n_m',
    'probes', 'property_source', 'applicability_declaration',
])
def test_no_missing_field_defaults(request_data, field):
    del request_data[field]
    result = evaluate_variable_beam(request_data)
    assert result['status'] in {'MODEL_INAPPLICABLE', 'SOLVER_UNSUPPORTED'}
    assert result['outputs'] == {}
    assert result['output_units'] == {}


@pytest.mark.parametrize('field', ['nodes_m', 'second_moments_m4'])
@pytest.mark.parametrize('value', [(0, 1, 2), [], [1], [1] * 66, ['1', 2, 3], [True, 2, 3]])
def test_strict_array_contract(request_data, field, value):
    request_data[field] = value
    assert_refused(evaluate_variable_beam(request_data))


@pytest.mark.parametrize('probe', [
    {}, {'element_index': 0}, {'element_index': 0, 'local_coordinate': 0.5, 'extra': 1},
    {'element_index': 0.0, 'local_coordinate': 0.5},
    {'element_index': True, 'local_coordinate': 0.5},
    {'element_index': 2, 'local_coordinate': 0.5},
    {'element_index': -1, 'local_coordinate': 0.5},
    {'element_index': 0, 'local_coordinate': '0.5'},
    {'element_index': 0, 'local_coordinate': True},
    {'element_index': 0, 'local_coordinate': -0.01},
    {'element_index': 0, 'local_coordinate': 1.01},
    {'element_index': 0, 'local_coordinate': math.nan},
])
def test_probe_refusal_is_all_or_nothing(request_data, probe):
    request_data['probes'].append(probe)
    original = deepcopy(request_data)
    assert_refused(evaluate_variable_beam(request_data))
    assert request_data == original


@pytest.mark.parametrize('count', [1, 128])
def test_probe_count_inclusive_limits(request_data, count):
    request_data['probes'] = [deepcopy(request_data['probes'][0]) for _ in range(count)]
    result = evaluate_variable_beam(request_data)
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    assert len(result['outputs']['probes']) == count


@pytest.mark.parametrize('count', [0, 129])
def test_probe_count_outside_limits(request_data, count):
    request_data['probes'] = [deepcopy(request_data['probes'][0]) for _ in range(count)]
    assert_refused(evaluate_variable_beam(request_data))


@pytest.mark.parametrize('field', ['property_source', 'applicability_declaration'])
@pytest.mark.parametrize('value', ['', '  ', 'x' * 2001, 123, None])
def test_source_declaration_bounds(request_data, field, value):
    request_data[field] = value
    assert_refused(evaluate_variable_beam(request_data))


def test_unsupported_evaluation(request_data):
    request_data['evaluation'] = 'unknown'
    assert_refused(evaluate_variable_beam(request_data), 'SOLVER_UNSUPPORTED')


def test_source_text_is_literal_and_does_not_change_computation(request_data, tmp_path):
    baseline = evaluate_variable_beam(request_data)
    marker = tmp_path / 'executed'
    request_data['property_source'] = f"__import__('pathlib').Path({str(marker)!r}).touch()"
    request_data['applicability_declaration'] = '<script>alert(1)</script> https://example.invalid/'
    result = evaluate_variable_beam(request_data)
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    assert result['outputs'] == baseline['outputs']
    assert not marker.exists()
