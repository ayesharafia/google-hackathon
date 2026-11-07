"""Independent analytic, frame, convergence, and public-contract oracles."""

import math
from itertools import pairwise

import numpy
import pytest
from scipy.spatial.transform import Rotation
from scipy.special import ellipj, ellipkinc

from physimesh.drone.rigid_body import RigidBodyState, propagate_rigid_body


def _zero_gravity_kwargs():
    return {
        'initial_state': RigidBodyState((0., 0., 0.), (0., 0., 0.), (1., 0., 0., 0.), (0., 0., 0.)),
        'mass_kg': 2.,
        'inertia_body_kg_m2': ((1., 0., 0.), (0., 2., 0.), (0., 0., 3.)),
        'force_body_n': (0., 0., 0.),
        'moment_cg_body_nm': (0., 0., 0.),
        'gravity_enu_m_s2': (0., 0., 0.),
        'dt_s': 0.01,
        'steps': 100,
    }


def _computed(kwargs):
    result = propagate_rigid_body(**kwargs)
    assert result['status'] == 'COMPUTED_EXPERIMENTAL', result['reasons']
    return result['outputs']


def _state(omega, quaternion=(1., 0., 0., 0.)):
    return RigidBodyState((0., 0., 0.), (0., 0., 0.), tuple(quaternion), tuple(omega))


def _tuple_vector(vector):
    return tuple(float(x) for x in vector)


def _tuple_matrix(matrix):
    return tuple(_tuple_vector(row) for row in matrix)


@pytest.mark.parametrize('transverse,axial', [(1., 3.), (3., 1.)])
def test_signed_axisymmetric_precession(transverse, axial):
    kwargs = _zero_gravity_kwargs()
    kwargs.update(initial_state=_state((.1, 0., 2.)),
                  inertia_body_kg_m2=((transverse, 0., 0.), (0., transverse, 0.), (0., 0., axial)),
                  dt_s=.002, steps=500)
    frequency = (axial - transverse) * 2. / transverse
    expected = (.1 * math.cos(frequency), .1 * math.sin(frequency), 2.)
    assert _computed(kwargs)['final_state']['angular_velocity_body_rad_s'] == pytest.approx(expected, abs=2e-11, rel=0.)


def test_asymmetric_jacobi_exact_phase_fourth_order():
    # For I=(1,2,3), the high-axis solution is (A cn(u), B sn(u), C dn(u)).
    # Energy and squared momentum determine amplitudes; the initial amplitude
    # determines u0 by the incomplete elliptic integral, without fitting phase.
    twice_energy = .2**2 + 2 * .1**2 + 3 * 1.2**2
    momentum_squared = .2**2 + (2 * .1)**2 + (3 * 1.2)**2
    amplitude_a = math.sqrt((3 * twice_energy - momentum_squared) / 2)
    amplitude_b = math.sqrt((3 * twice_energy - momentum_squared) / 2)
    amplitude_c = math.sqrt((momentum_squared - twice_energy) / 6)
    parameter = (3 * twice_energy - momentum_squared) / (momentum_squared - twice_energy)
    phase = ellipkinc(math.atan2(.1 / amplitude_b, .2 / amplitude_a), parameter)
    sn, cn, dn, _ = ellipj(phase + amplitude_c * 10., parameter)
    expected = numpy.array((amplitude_a * cn, amplitude_b * sn, amplitude_c * dn))
    errors = []
    for dt in (.08, .04, .02, .01):
        kwargs = _zero_gravity_kwargs()
        kwargs.update(initial_state=_state((.2, .1, 1.2)), dt_s=dt, steps=round(10 / dt))
        actual = _computed(kwargs)['final_state']['angular_velocity_body_rad_s']
        errors.append(float(numpy.linalg.norm(numpy.array(actual) - expected)))
    orders = [math.log2(coarse / fine) for coarse, fine in pairwise(errors)]
    assert all(3.9 <= order <= 4.1 for order in orders), (errors, orders)


def test_general_rotation_constant_force_exact_acceleration():
    rotation = Rotation.from_rotvec((.4, -.6, .2))
    xyzw = rotation.as_quat()
    quaternion = _tuple_vector((xyzw[3], *xyzw[:3]))
    kwargs = _zero_gravity_kwargs()
    position = numpy.array((1., -2., 3.))
    velocity = numpy.array((-.2, .5, 1.))
    kwargs.update(initial_state=RigidBodyState(_tuple_vector(position), _tuple_vector(velocity), quaternion, (0., 0., 0.)),
                  force_body_n=(1.3, -2.1, .7), gravity_enu_m_s2=(.2, -.1, -9.8), dt_s=.002, steps=500)
    acceleration = rotation.apply(kwargs['force_body_n']) / kwargs['mass_kg'] + kwargs['gravity_enu_m_s2']
    final = _computed(kwargs)['final_state']
    assert final['velocity_enu_m_s'] == pytest.approx(velocity + acceleration, abs=2e-12, rel=0.)
    assert final['position_enu_m'] == pytest.approx(position + velocity + .5 * acceleration, abs=2e-12, rel=0.)


def test_full_spd_nonzero_torque_omega_covariance():
    rotation = Rotation.from_rotvec((.4, -.6, .2)).as_matrix()
    principal = numpy.diag((1.1, 2.2, 2.8))
    transformed = rotation @ principal @ rotation.T
    # Reuse precisely the same floats on both sides of the diagonal.
    transformed[1, 0] = transformed[0, 1]
    transformed[2, 0] = transformed[0, 2]
    transformed[2, 1] = transformed[1, 2]
    omega = numpy.array((.3, 2., 1.5))
    moment = numpy.array((.2, -.1, .3))
    finals = []
    for tensor, initial, torque in ((principal, omega, moment), (transformed, rotation @ omega, rotation @ moment)):
        kwargs = _zero_gravity_kwargs()
        kwargs.update(initial_state=_state(_tuple_vector(initial)), inertia_body_kg_m2=_tuple_matrix(tensor),
                      moment_cg_body_nm=_tuple_vector(torque), dt_s=.002, steps=500)
        finals.append(numpy.array(_computed(kwargs)['final_state']['angular_velocity_body_rad_s']))
    numpy.testing.assert_allclose(finals[1], rotation @ finals[0], atol=1e-10, rtol=0.)


def _right_hamilton_rhs(quaternion, omega):
    scalar = -.5 * sum(a * b for a, b in zip(quaternion[1:], omega))
    vector = .5 * (quaternion[0] * numpy.array(omega) + numpy.cross(quaternion[1:], omega))
    return numpy.array((scalar, *vector))


def test_quaternion_rhs_refinement_and_body_frame_source():
    rotation = Rotation.from_rotvec((.4, -.6, .2))
    xyzw = rotation.as_quat()
    quaternion = numpy.array((xyzw[3], *xyzw[:3]))
    omega = (.3, -.7, 1.1)
    derivative = _right_hamilton_rhs(quaternion, omega)
    errors = []
    for dt in (.02, .01, .005):
        kwargs = _zero_gravity_kwargs()
        kwargs.update(initial_state=_state(omega, _tuple_vector(quaternion)),
                      inertia_body_kg_m2=((2., 0., 0.), (0., 2., 0.), (0., 0., 2.)), dt_s=dt, steps=1)
        actual = numpy.array(_computed(kwargs)['final_state']['quaternion_body_to_enu'])
        errors.append(numpy.linalg.norm((actual - quaternion) / dt - derivative))
        expected = (rotation * Rotation.from_rotvec(numpy.array(omega) * dt)).as_quat()
        numpy.testing.assert_allclose(actual, (expected[3], *expected[:3]), atol=3e-11, rtol=0.)
    assert all(1.95 < coarse / fine < 2.05 for coarse, fine in pairwise(errors)), errors


def test_metadata_units_and_exact_output_keys():
    result = propagate_rigid_body(**_zero_gravity_kwargs())
    assert set(result) == {'model_id', 'status', 'physical_validation', 'evidence_level', 'aircraft_status', 'feasibility', 'inertia_physical_admissibility', 'reasons', 'limitations', 'sources', 'outputs', 'output_units'}
    assert result['model_id'] == 'rigid_body_constant_body_wrench_rk4_v1'
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    assert result['physical_validation'] == 'NOT_ESTABLISHED'
    assert result['evidence_level'] == 'unverified'
    assert result['aircraft_status'] is None
    assert result['feasibility'] is None
    assert result['inertia_physical_admissibility'] == 'NOT_ASSESSED'
    assert result['reasons'] == []
    assert result['limitations'] and all(isinstance(x, str) and x for x in result['limitations'])
    assert result['sources'] and all(x.startswith('https://') for x in result['sources'])
    state_units = {'position_enu_m': 'm', 'velocity_enu_m_s': 'm/s', 'quaternion_body_to_enu': '1', 'angular_velocity_body_rad_s': 'rad/s'}
    units = {'elapsed_s': 's', 'steps': '1', 'initial_state': state_units, 'final_state': state_units,
             'input_quaternion_norm_correction': '1', 'max_preprojection_quaternion_norm_error': '1', 'final_quaternion_norm': '1',
             'initial_rotational_kinetic_energy_j': 'J', 'final_rotational_kinetic_energy_j': 'J',
             'initial_angular_momentum_enu_kg_m2_s': 'kg*m^2/s', 'final_angular_momentum_enu_kg_m2_s': 'kg*m^2/s',
             'torque_free_relative_energy_drift': '1', 'torque_free_relative_angular_momentum_drift': '1'}
    assert result['output_units'] == units
    assert set(result['outputs']) == set(units)
    for key in ('initial_state', 'final_state'):
        assert set(result['outputs'][key]) == set(state_units)
    assert result['outputs']['steps'] == 100
    assert result['outputs']['elapsed_s'] == 1.


def _refused(kwargs):
    result = propagate_rigid_body(**kwargs)
    assert result['status'] == 'MODEL_INAPPLICABLE'
    assert result['outputs'] == {}
    assert result['output_units'] == {}
    assert result['reasons']


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -float('inf'), 5e-324])
@pytest.mark.parametrize('field', ['mass_kg', 'dt_s', 'force_body_n', 'moment_cg_body_nm', 'gravity_enu_m_s2', 'inertia_body_kg_m2', 'position_enu_m', 'velocity_enu_m_s', 'quaternion_body_to_enu', 'angular_velocity_body_rad_s'])
def test_nonfinite_and_subnormal_refusals(field, bad):
    kwargs = _zero_gravity_kwargs()
    if field in ('mass_kg', 'dt_s'):
        kwargs[field] = bad
    elif field == 'inertia_body_kg_m2':
        kwargs[field] = ((bad, 0., 0.), (0., 2., 0.), (0., 0., 3.))
    elif field in ('force_body_n', 'moment_cg_body_nm', 'gravity_enu_m_s2'):
        kwargs[field] = (bad, 0., 0.)
    else:
        state = kwargs['initial_state']
        values = dict(vars(state))
        values[field] = (bad, *values[field][1:])
        kwargs['initial_state'] = RigidBodyState(**values)
    _refused(kwargs)


@pytest.mark.parametrize('field,value', [('dt_s', 1e308), ('mass_kg', 10**1000), ('steps', 10001)])
def test_huge_numeric_and_step_limit_refusals(field, value):
    kwargs = _zero_gravity_kwargs()
    kwargs[field] = value
    _refused(kwargs)


def test_huge_state_arithmetic_refusal():
    kwargs = _zero_gravity_kwargs()
    kwargs['initial_state'] = _state((1e308, 1e308, 1e308))
    _refused(kwargs)


def test_near_unit_quaternion_normalization_is_reported():
    kwargs = _zero_gravity_kwargs()
    value = 1. + 5e-13
    kwargs['initial_state'] = _state((0., 0., 0.), (value, 0., 0., 0.))
    outputs = _computed(kwargs)
    assert outputs['input_quaternion_norm_correction'] == abs(value - 1.)
    assert outputs['initial_state']['quaternion_body_to_enu'] == [1., 0., 0., 0.]
    assert outputs['final_state']['quaternion_body_to_enu'] == [1., 0., 0., 0.]
    assert outputs['final_quaternion_norm'] == 1.


class _FloatSubclass(float):
    pass


class _IntSubclass(int):
    pass


class _TupleSubclass(tuple):
    pass


class _StateSubclass(RigidBodyState):
    pass


@pytest.mark.parametrize('field,value', [('mass_kg', _FloatSubclass(2.)), ('dt_s', _FloatSubclass(.01)),
                                        ('steps', _IntSubclass(100)), ('force_body_n', _TupleSubclass((0., 0., 0.))),
                                        ('force_body_n', (_FloatSubclass(0.), 0., 0.)),
                                        ('inertia_body_kg_m2', _TupleSubclass(((1., 0., 0.), (0., 2., 0.), (0., 0., 3.)))),
                                        ('inertia_body_kg_m2', ((_TupleSubclass((1., 0., 0.))), (0., 2., 0.), (0., 0., 3.))),
                                        ('initial_state', _StateSubclass((0., 0., 0.), (0., 0., 0.), (1., 0., 0., 0.), (0., 0., 0.)))])
def test_exact_type_subclass_refusals(field, value):
    kwargs = _zero_gravity_kwargs()
    kwargs[field] = value
    _refused(kwargs)


def test_tiny_normal_energy_with_zero_diagnostic_difference_is_allowed():
    kwargs = _zero_gravity_kwargs()
    kwargs.update(initial_state=_state((0., 0., 1e-150)), dt_s=.01, steps=100)
    outputs = _computed(kwargs)
    assert outputs['final_state']['angular_velocity_body_rad_s'] == [0., 0., 1e-150]
    assert outputs['torque_free_relative_angular_momentum_drift'] == 0.
    assert outputs['torque_free_relative_energy_drift'] == 0.
    assert 0. < outputs['initial_rotational_kinetic_energy_j'] < 1e-290
