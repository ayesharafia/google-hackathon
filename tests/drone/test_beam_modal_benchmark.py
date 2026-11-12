"""Independent continuum evidence and bounded observational helper contract."""

import copy
import inspect
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from physimesh.drone import beam_modal_benchmark as bench

BASE = {"length_m": 1.0, "E_pa": 1.0, "I_m4": 1.0, "mass_per_length_kg_m": 1.0,
        "element_counts": [2, 4, 8, 16, 32, 64], "modes": 4}
FIXTURE = json.loads(Path(__file__).with_name('beam_modal_continuum_reference.json').read_text())


def run(**updates):
    return bench.uniform_modal_refinement(**(BASE | updates))


def assert_closed(result):
    json.dumps(result, allow_nan=False)
    assert bench._finite_json(result)
    for key in ('physical_validation', 'numerical_qualification', 'mesh_accuracy'):
        assert result[key] == 'NOT_ESTABLISHED'
    assert result['schema_version'] == 'uniform_modal_refinement_v1'
    assert result['evidence_level'] == 'unverified'
    assert result['aircraft_status'] is result['feasibility'] is None
    if result['status'] == 'REFUSED':
        assert result['outputs'] == {}


def test_signature():
    signature = inspect.signature(bench.uniform_modal_refinement)
    assert len(signature.parameters) == 6
    for p in signature.parameters.values():
        assert p.kind == p.KEYWORD_ONLY
        assert p.default is p.empty


@pytest.mark.parametrize('counts', [None, (2, 4), [], [2], [2]*7, [4, 2], [2, 2],
                                   [1, 2], [2, 65], [True, 4], [2.0, 4], [np.int64(2), 4]])
def test_counts(counts):
    result = run(element_counts=counts)
    assert result['status'] == 'REFUSED'
    assert_closed(result)


@pytest.mark.parametrize('value', [True, np.int64(1), np.float64(1), '1', None, 0, -1,
                                  float('nan'), float('inf'), 5e-324, 10**1000])
@pytest.mark.parametrize('field', ['length_m', 'E_pa', 'I_m4', 'mass_per_length_kg_m'])
def test_scalars(field, value):
    result = run(**{field: value})
    assert result['status'] == 'REFUSED'
    assert_closed(result)


@pytest.mark.parametrize('modes', [True, np.int64(1), 1.0, 0, -1, 5, 7, None])
def test_modes(modes):
    result = run(modes=modes)
    assert result['status'] == 'REFUSED'
    assert_closed(result)


@pytest.mark.parametrize('counts,modes', [([2, 4, 8, 16, 32, 64], 4), ([3, 6, 12, 24, 48], 6),
                                         ([3, 7], 6)])
def test_nominal(counts, modes):
    result = run(element_counts=counts, modes=modes)
    assert result['status'] == 'SUCCESS'
    assert_closed(result)
    assert [m['elements'] for m in result['outputs']['meshes']] == counts
    for mesh in result['outputs']['meshes']:
        assert len(mesh['modes']) == modes
        for mode in mesh['modes']:
            assert all(mode[k] >= 0 for k in ('absolute_dimensionless_frequency_relative_error',
                       'max_abs_nodal_shape_error', 'max_abs_nodal_derivative_xi_error'))
    for ref, expected in zip(result['outputs']['reference'], FIXTURE['modes']):
        assert abs(ref['beta'] - float(expected['beta'])) < 4e-15
        assert abs(math.cos(ref['beta']) + 1/math.cosh(ref['beta'])) < 4e-15
        assert ref['dimensionless_omega'] == ref['beta']**2


def test_independent_all_six_shapes_and_derivatives():
    # Fixture uses high precision unscaled hyperbolics, not the runtime rearrangement.
    for mode in FIXTURE['modes']:
        beta = float(mode['beta'])
        for sample in mode['samples']:
            u, du = bench._reference(beta, sample['xi'])
            assert abs(u - float(sample['shape'])) <= 1e-11
            assert abs(du - float(sample['derivative_xi'])) <= 1e-11
        u0, du0 = bench._reference(beta, 0)
        assert abs(u0) < 1e-14
        assert abs(du0) < 1e-13
        assert bench._reference(beta, 1)[0] == 1.0
        # Independently differentiate the displacement by a centered difference.
        h = 1e-6
        fd = (bench._reference(beta, .37+h)[0]-bench._reference(beta, .37-h)[0])/(2*h)
        assert fd == pytest.approx(bench._reference(beta, .37)[1], abs=2e-8)


def test_scale_invariance():
    a = run(element_counts=[3, 6, 12], modes=6)
    b = run(element_counts=[3, 6, 12], modes=6, length_m=2, E_pa=7e9,
            I_m4=2e-7, mass_per_length_kg_m=3)
    assert a['status'] == b['status'] == 'SUCCESS'
    assert a['outputs'] == b['outputs']


def test_late_core_refusal_no_partial_or_mutation(monkeypatch):
    original = bench.solve_cantilever_modes
    refusal = {'code': 'UNRESOLVED_SPECTRUM', 'field': None, 'message': 'Injected late refusal.',
               'detail': {'nested': [1, None]}}
    failure = {'status': 'REFUSED', 'refusal': refusal}
    before = copy.deepcopy(failure)
    calls = []

    def core(**kwargs):
        calls.append(kwargs['elements'])
        return failure if kwargs['elements'] == 8 else original(**kwargs)

    monkeypatch.setattr(bench, 'solve_cantilever_modes', core)
    result = run()
    assert result['status'] == 'REFUSED'
    assert result['core_refusal'] == refusal
    assert result['core_refusal'] is not refusal
    assert calls == [2, 4, 8]
    assert failure == before
    assert_closed(result)


@pytest.mark.parametrize('payload', [None, {}, {'status': 'WHAT'},
    {'status': 'REFUSED', 'refusal': {'code': 'X'}},
    {'status': 'REFUSED', 'refusal': {'code': 'X', 'field': None, 'message': float('nan')}},
    {'status': 'SUCCESS', 'modes': []}])
def test_malformed_closed(monkeypatch, payload):
    monkeypatch.setattr(bench, 'solve_cantilever_modes', lambda **kwargs: payload)
    result = run()
    assert result['status'] == 'REFUSED'
    assert_closed(result)


def test_order_guard_and_increasing_error():
    assert bench._observed_order(0, 1, 2, 4) is None
    assert bench._observed_order(1, 0, 2, 4) is None
    assert bench._observed_order(math.inf, 1, 2, 4) is None
    assert bench._observed_order(1, 2, 2, 4) == pytest.approx(-1)
    assert math.isfinite(bench._observed_order(sys.float_info.max, 5e-324, 2, 4))


def test_injected_zero_and_increasing_error_flags(monkeypatch):
    original = bench.solve_cantilever_modes

    def core(**kwargs):
        result = original(**kwargs)
        # Use the same finite root calculation through a nominal observation.
        beta = float(FIXTURE['modes'][0]['beta'])
        result['modes'][0]['eigenvalue_dimensionless'] = beta**4 * (
            1 if kwargs['elements'] == 2 else 4)
        return result

    monkeypatch.setattr(bench, 'solve_cantilever_modes', core)
    result = run(element_counts=[2, 4], modes=1)
    observation = result['outputs']['adjacent'][0]['modes'][0]
    assert observation['frequency_error_decreased'] is False
    # Null at exactly zero; otherwise the near-zero binary error is finite and observed.
    coarse = result['outputs']['meshes'][0]['modes'][0]['absolute_dimensionless_frequency_relative_error']
    assert observation['observed_frequency_order'] is None if coarse == 0 else math.isfinite(
        observation['observed_frequency_order'])


@pytest.mark.parametrize('ratio', [0.75, 1.25])
def test_signed_frequency_error_against_core(monkeypatch, ratio):
    original = bench.solve_cantilever_modes
    core_results = []

    def core(**kwargs):
        result = original(**kwargs)
        beta = float(FIXTURE['modes'][0]['beta'])
        result['modes'][0]['eigenvalue_dimensionless'] = (ratio*beta**2)**2
        core_results.append(copy.deepcopy(result))
        return result

    monkeypatch.setattr(bench, 'solve_cantilever_modes', core)
    result = run(element_counts=[2, 4], modes=1)
    assert result['status'] == 'SUCCESS'
    beta = result['outputs']['reference'][0]['beta']
    for mesh, core_result in zip(result['outputs']['meshes'], core_results):
        expected = math.sqrt(core_result['modes'][0]['eigenvalue_dimensionless']) / beta**2 - 1
        observation = mesh['modes'][0]
        assert observation['dimensionless_frequency_relative_error'] == expected
        assert observation['absolute_dimensionless_frequency_relative_error'] == abs(expected)
        assert (expected > 0) == (ratio > 1)


def test_second_reference_root_failure_closed(monkeypatch):
    original = bench.brentq
    brackets = []

    def root(function, lo, hi, **kwargs):
        brackets.append((lo, hi))
        if len(brackets) == 2:
            raise RuntimeError('Injected root convergence failure')
        return original(function, lo, hi, **kwargs)

    def no_core(**kwargs):
        pytest.fail('Core must not run after reference failure')

    monkeypatch.setattr(bench, 'brentq', root)
    monkeypatch.setattr(bench, 'solve_cantilever_modes', no_core)
    result = run()
    assert result['status'] == 'REFUSED'
    assert result['refusal']['code'] == 'REFERENCE_FAILURE'
    assert brackets == [(1, 2), (4, 5)]
    assert_closed(result)
