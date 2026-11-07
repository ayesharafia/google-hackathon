import copy
import math
from dataclasses import FrozenInstanceError

import pytest

from physimesh.drone.rigid_body import RigidBodyState, propagate_rigid_body


def test_freefall():
    state = RigidBodyState((0., 0., 0.), (0., 0., 0.), (1., 0., 0., 0.), (0., 0., 0.))
    result = propagate_rigid_body(initial_state=state, mass_kg=2., inertia_body_kg_m2=((1., 0., 0.), (0., 2., 0.), (0., 0., 3.)), force_body_n=(0., 0., 0.), moment_cg_body_nm=(0., 0., 0.), gravity_enu_m_s2=(0., 0., -9.8), dt_s=0.01, steps=100)
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    final = result['outputs']['final_state']
    assert abs(final['position_enu_m'][2] + 4.9) < 1e-12
    assert abs(final['velocity_enu_m_s'][2] + 9.8) < 1e-12


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
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    return result['outputs']


def test_constant_velocity_free_motion():
    kwargs = _zero_gravity_kwargs()
    kwargs['initial_state'] = RigidBodyState((1., -2., 3.), (2., -3., 4.), (1., 0., 0., 0.), (0., 0., 0.))
    final = _computed(kwargs)['final_state']
    assert final['position_enu_m'] == pytest.approx((3., -5., 7.), abs=1e-12)
    assert final['velocity_enu_m_s'] == pytest.approx((2., -3., 4.), abs=1e-12)


def test_identity_body_force_cancels_gravity():
    kwargs = _zero_gravity_kwargs()
    kwargs.update(force_body_n=(0., 0., 19.6), gravity_enu_m_s2=(0., 0., -9.8))
    final = _computed(kwargs)['final_state']
    assert final['position_enu_m'] == pytest.approx((0., 0., 0.), abs=1e-12)
    assert final['velocity_enu_m_s'] == pytest.approx((0., 0., 0.), abs=1e-12)


def test_rotated_body_force_accelerates_world_y():
    kwargs = _zero_gravity_kwargs()
    h = math.sqrt(0.5)
    kwargs['initial_state'] = RigidBodyState((0., 0., 0.), (0., 0., 0.), (h, 0., 0., h), (0., 0., 0.))
    kwargs['force_body_n'] = (2., 0., 0.)
    final = _computed(kwargs)['final_state']
    assert final['position_enu_m'] == pytest.approx((0., 0.5, 0.), abs=1e-12)
    assert final['velocity_enu_m_s'] == pytest.approx((0., 1., 0.), abs=1e-12)


def test_spherical_inertia_constant_body_moment():
    kwargs = _zero_gravity_kwargs()
    kwargs.update(inertia_body_kg_m2=((2.5, 0., 0.), (0., 2.5, 0.), (0., 0., 2.5)), moment_cg_body_nm=(0., 0., 0.7), steps=400)
    final = _computed(kwargs)['final_state']
    assert final['angular_velocity_body_rad_s'] == pytest.approx((0., 0., 1.12), abs=1e-10)
    assert final['quaternion_body_to_enu'] == pytest.approx((math.cos(1.12), 0., 0., math.sin(1.12)), abs=1e-9)


def test_zero_energy_and_angular_momentum_drifts():
    outputs = _computed(_zero_gravity_kwargs())
    drifts = [value for key, value in outputs.items() if 'drift' in key]
    assert len(drifts) == 2
    assert drifts == [0., 0.]


def test_forced_drifts_are_none():
    kwargs = _zero_gravity_kwargs()
    kwargs.update(force_body_n=(1., 0., 0.), moment_cg_body_nm=(0., 0., 0.7))
    outputs = _computed(kwargs)
    drifts = [value for key, value in outputs.items() if 'drift' in key]
    assert len(drifts) == 2
    assert drifts == [None, None]


@pytest.mark.parametrize('inertia', [
    ((1., 1e-15, 0.), (0., 2., 0.), (0., 0., 3.)),
    ((0., 0., 0.), (0., 2., 0.), (0., 0., 3.)),
    ((-1., 0., 0.), (0., 2., 0.), (0., 0., 3.)),
    ((1., 2., 0.), (2., 1., 0.), (0., 0., 3.)),
    ((1., 0., 0.), (0., 2., 0.), (0., 0., -3.)),
])
def test_inertia_must_be_exactly_symmetric_positive_definite(inertia):
    kwargs = _zero_gravity_kwargs()
    kwargs['inertia_body_kg_m2'] = inertia
    result = propagate_rigid_body(**kwargs)
    assert result['status'] == 'MODEL_INAPPLICABLE'
    assert result['outputs'] == {}


@pytest.mark.parametrize('key,value', [
    ('mass_kg', 0.), ('mass_kg', -1.),
    ('steps', 0), ('steps', -1),
    ('dt_s', 0.), ('dt_s', -0.01),
    ('initial_state', RigidBodyState((0., 0., 0.), (0., 0., 0.), (0., 0., 0., 0.), (0., 0., 0.))),
    ('initial_state', RigidBodyState((0., 0., 0.), (0., 0., 0.), (2., 0., 0., 0.), (0., 0., 0.))),
])
def test_wrong_domain_is_model_inapplicable(key, value):
    kwargs = _zero_gravity_kwargs()
    kwargs[key] = value
    result = propagate_rigid_body(**kwargs)
    assert result['status'] == 'MODEL_INAPPLICABLE'
    assert result['outputs'] == {}


@pytest.mark.parametrize('key,value', [
    ('initial_state', None),
    ('initial_state', ((0., 0., 0.), (0., 0., 0.), (1., 0., 0., 0.), (0., 0., 0.))),
    ('mass_kg', '2'), ('mass_kg', True),
    ('dt_s', '0.01'), ('dt_s', True),
    ('steps', 1.5), ('steps', True),
    ('force_body_n', (0., 0.)), ('force_body_n', (0., 0., '0')),
    ('moment_cg_body_nm', (0., 0.)), ('moment_cg_body_nm', (0., 0., None)),
    ('gravity_enu_m_s2', (0., 0.)), ('gravity_enu_m_s2', (0., 0., True)),
    ('inertia_body_kg_m2', ((1., 0.), (0., 1.))),
    ('inertia_body_kg_m2', ((1., 0., 0.), (0., '2', 0.), (0., 0., 3.))),
])
def test_invalid_shapes_and_types(key, value):
    kwargs = _zero_gravity_kwargs()
    kwargs[key] = value
    result = propagate_rigid_body(**kwargs)
    assert result['status'] == 'MODEL_INAPPLICABLE'
    assert result['outputs'] == {}


def test_state_is_frozen_and_inputs_are_not_mutated():
    kwargs = _zero_gravity_kwargs()
    before = copy.deepcopy(kwargs)
    state = kwargs['initial_state']
    with pytest.raises(FrozenInstanceError):
        state.position_enu_m = (1., 2., 3.)
    _computed(kwargs)
    assert kwargs == before


def test_quaternion_sign_is_preserved_with_physical_equivalence():
    results = []
    h = math.sqrt(0.5)
    for sign in (1., -1.):
        kwargs = _zero_gravity_kwargs()
        kwargs['initial_state'] = RigidBodyState((0., 0., 0.), (0., 0., 0.), (sign * h, 0., 0., sign * h), (0., 0., 0.))
        kwargs['force_body_n'] = (2., 0., 0.)
        results.append(_computed(kwargs)['final_state'])
    assert results[0]['position_enu_m'] == pytest.approx(results[1]['position_enu_m'], abs=1e-12)
    assert results[0]['velocity_enu_m_s'] == pytest.approx(results[1]['velocity_enu_m_s'], abs=1e-12)
    assert results[0]['quaternion_body_to_enu'] == pytest.approx(tuple(-x for x in results[1]['quaternion_body_to_enu']), abs=1e-12)
    assert results[0]['quaternion_body_to_enu'][0] > 0.
    assert results[1]['quaternion_body_to_enu'][0] < 0.
