import copy
import math

import pytest

from physimesh.drone.fixed_wing import screen_fixed_wing


def request(**changes):
    base = {
        'configuration': 'fixed_wing', 'evaluation': 'fixed_wing_aerodynamic_screening',
        'density_kg_m3': 1.2, 'airspeed_m_s': 50.0, 'wing_area_m2': 10.0,
        'span_m': 10.0, 'characteristic_length_m': 1.0,
        'dynamic_viscosity_pa_s': 1.8e-5, 'speed_of_sound_m_s': 340.0,
        'lift_coefficient': 0.5, 'zero_lift_drag_coefficient': 0.02, 'span_efficiency': 0.8,
        'coefficient_source': 'Synthetic analytic coefficient declaration, not measured.',
        'coefficient_envelope': {'mach_min': 0.0, 'mach_max': 0.3,
                                 'reynolds_min': 1e6, 'reynolds_max': 5e6,
                                 'lift_coefficient_min': -1.0, 'lift_coefficient_max': 1.0},
    }
    return base | changes


def refused(value, status='MODEL_INAPPLICABLE'):
    result = screen_fixed_wing(value)
    assert result['status'] == status
    assert result['outputs'] == {} and result['output_units'] == {}
    assert result['aircraft_status'] is None and result['feasibility'] is None
    assert result['evidence_level'] == 'unverified'
    return result


def test_independent_analytic_oracle_and_no_mutation():
    body = request()
    before = copy.deepcopy(body)
    result = screen_fixed_wing(body)
    assert body == before
    assert result['status'] == 'SCREENING_COMPUTED'
    expected = {'dynamic_pressure_pa': 1500.0, 'aspect_ratio': 10.0,
                'induced_drag_coefficient': 0.25 / (8 * math.pi),
                'drag_coefficient': 0.02 + 0.25 / (8 * math.pi),
                'lift_n': 7500.0, 'drag_n': 300 + 468.75 / math.pi,
                'drag_power_w': 15000 + 23437.5 / math.pi,
                'reynolds_number': 10e6 / 3, 'mach_number': 5 / 34}
    assert set(result['outputs']) == set(expected)
    for key, val in expected.items():
        assert result['outputs'][key] == pytest.approx(val, rel=2e-14)
    assert result['output_units']['drag_power_w'] == 'W'
    assert result['output_units']['lift_n'] == 'N'
    assert result['evidence_level'] == 'unverified'
    assert result['aircraft_status'] is None and result['feasibility'] is None
    assert result['limitations']


@pytest.mark.parametrize('value', [None, [], '', 1, True, {}, {'configuration': 'fixed_wing'}])
def test_malformed(value):
    refused(value)


@pytest.mark.parametrize('key', ['density_kg_m3', 'airspeed_m_s', 'wing_area_m2', 'span_m',
                                 'characteristic_length_m', 'dynamic_viscosity_pa_s',
                                 'speed_of_sound_m_s', 'span_efficiency'])
@pytest.mark.parametrize('value', [0, -1, True, '1', float('nan'), float('inf'), None])
def test_strict_positive_finite(key, value):
    refused(request(**{key: value}))


def test_missing_extra_and_config_never_substituted():
    for key in request():
        body = request(); del body[key]; refused(body)
    refused(request(extra=1))
    refused(request(configuration='multirotor'))
    refused(request(configuration='custom'))
    refused(request(evaluation='aircraft_feasibility'), 'SOLVER_UNSUPPORTED')
    refused(request(coefficient_source='  '))
    refused(request(coefficient_source='a' * 2001))
    refused(request(span_efficiency=1.01))
    refused(request(zero_lift_drag_coefficient=-0.1))


def test_signed_zero_and_scaling():
    original = screen_fixed_wing(request())['outputs']
    negative = screen_fixed_wing(request(lift_coefficient=-0.5))['outputs']
    assert negative['lift_n'] == -original['lift_n']
    assert negative['drag_n'] == original['drag_n']
    zero = screen_fixed_wing(request(lift_coefficient=0, zero_lift_drag_coefficient=0))['outputs']
    assert zero['lift_n'] == zero['drag_n'] == zero['drag_power_w'] == 0
    twice_area = screen_fixed_wing(request(wing_area_m2=20, span_m=math.sqrt(200)))['outputs']
    assert twice_area['lift_n'] == pytest.approx(2 * original['lift_n'])
    assert twice_area['drag_n'] == pytest.approx(2 * original['drag_n'])


def test_declared_coverage_exact_bounds_no_extrapolation():
    env = request()['coefficient_envelope']
    out = screen_fixed_wing(request())['outputs']
    exact = env | {'mach_min': out['mach_number'], 'mach_max': out['mach_number'],
                   'reynolds_min': out['reynolds_number'], 'reynolds_max': out['reynolds_number'],
                   'lift_coefficient_min': 0.5, 'lift_coefficient_max': 0.5}
    assert screen_fixed_wing(request(coefficient_envelope=exact))['status'] == 'SCREENING_COMPUTED'
    for key, value in [('mach_max', 0.1), ('reynolds_max', 2e6), ('lift_coefficient_max', 0.4)]:
        result = refused(request(coefficient_envelope=env | {key: value}))
        assert 'COEFFICIENT_OUTSIDE_DECLARED_ENVELOPE' in result['reasons']
    for invalid in [None, {}, env | {'extra': 1}, env | {'mach_min': True},
                    env | {'mach_min': 1}, env | {'reynolds_min': 0},
                    env | {'lift_coefficient_min': 2}, env | {'mach_max': float('inf')}]:
        refused(request(coefficient_envelope=invalid))


@pytest.mark.parametrize('change', [ {'airspeed_m_s': 1e308}, {'span_m': 1e-300},
                                    {'dynamic_viscosity_pa_s': 1e-320},
                                    {'wing_area_m2': 10 ** 10000}, {'lift_coefficient': 1e308}])
def test_derived_numeric_fail_closed(change):
    refused(request(**change))
