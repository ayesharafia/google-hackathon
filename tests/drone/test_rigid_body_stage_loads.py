"""Bounded numerical contract checks; physical validation NOT_ESTABLISHED."""
import math
import sys
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from physimesh.drone.rigid_body import RigidBodyState
from physimesh.drone.rigid_body_stage_loads import propagate_rigid_body_stage_loads

ZERO = (0.0, 0.0, 0.0)
IDENTITY = (1.0, 0.0, 0.0, 0.0)
STATE = RigidBodyState(ZERO, ZERO, IDENTITY, ZERO)
INERTIA = ((1.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 3.0))
OUTPUTS = {'elapsed_s', 'steps', 'final_state', 'load_evaluations',
           'input_quaternion_norm_correction',
           'max_preprojection_quaternion_norm_error', 'final_quaternion_norm'}
FIELDS = ('position_enu_m', 'velocity_enu_m_s', 'quaternion_body_to_enu',
          'angular_velocity_body_rad_s')


def run(callback, **overrides):
    args = {'initial_state': STATE, 'mass_kg': 1.0, 'inertia_body_kg_m2': INERTIA,
                'gravity_enu_m_s2': ZERO, 'dt_s': 0.1, 'steps': 2, 'load_function': callback}
    args.update(overrides)
    return propagate_rigid_body_stage_loads(**args)


def metadata(result):
    assert result['model_id'] == 'rigid_body_stage_loads_normalized_attitude_rk4_v1'
    assert result['physical_validation'] == 'NOT_ESTABLISHED'
    assert result['evidence_level'] == 'unverified'
    assert result['aircraft_status'] is None and result['feasibility'] is None
    assert result['inertia_physical_admissibility'] == 'NOT_ASSESSED'
    assert result['limitations'] and result['sources']


def refused(result, callback_failure=False):
    metadata(result)
    assert result['status'] == 'MODEL_INAPPLICABLE'
    assert result['outputs'] == {} and result['output_units'] == {}
    reason = ('Load callback failed or returned unsupported data.' if callback_failure
              else 'Input or numerical arithmetic is outside the supported domain.')
    assert result['reasons'] == [reason]


BAD_NUMBERS = [True, np.float64(1.0), np.int64(1), float('nan'),
               float('inf'), -float('inf'), 10**1000, float.fromhex('0x0.0000000000001p-1022')]
BAD_INPUTS = [('mass_kg', x) for x in BAD_NUMBERS + [0.0, -1.0]] + [
    ('steps', x) for x in [True, np.int64(2), 2.0, 0, -1, 10001]] + [
    ('dt_s', x) for x in BAD_NUMBERS + [0.0, -1.0, sys.float_info.min]] + [
    ('gravity_enu_m_s2', [0.0, 0.0, 0.0]),
    ('gravity_enu_m_s2', (True, 0.0, 0.0)),
    ('inertia_body_kg_m2', list(INERTIA)),
    ('inertia_body_kg_m2', ((1., 0., 0.), (0., -1., 0.), (0., 0., 1.))),
    ('inertia_body_kg_m2', ((1., 0.1, 0.), (0., 2., 0.), (0., 0., 3.))),
    ('initial_state', RigidBodyState(ZERO, ZERO, (0., 0., 0., 0.), ZERO)),
    ('initial_state', RigidBodyState(list(ZERO), ZERO, IDENTITY, ZERO)),
]


@pytest.mark.parametrize('field,value', BAD_INPUTS)
def test_invalid_inputs_precede_callback(field, value):
    calls = []
    result = run(lambda *args: calls.append(args) or (ZERO, ZERO), **{field: value})
    refused(result)
    assert calls == []


@pytest.mark.parametrize('bad', [None, [ZERO, ZERO], (ZERO,), (ZERO, ZERO, ZERO),
    ([0., 0., 0.], ZERO), (np.zeros(3), ZERO), ((0., 0.), ZERO)] +
    [((x, 0., 0.), ZERO) for x in BAD_NUMBERS] +
    [(ZERO, (x, 0., 0.)) for x in BAD_NUMBERS])
def test_malformed_return_stops_first_call(bad):
    calls = []
    refused(run(lambda *args: calls.append(args) or bad), True)
    assert len(calls) == 1


def test_noncallable_has_zero_calls():
    refused(run(None), True)


@pytest.mark.parametrize('failure', ['exception', 'malformed'])
def test_third_stage_failure_is_atomic(failure):
    calls = []
    def loads(t, state):
        calls.append((t, state))
        if len(calls) == 3:
            if failure == 'exception':
                raise RuntimeError('PRIVATE_SENTINEL')
            return ('PRIVATE_SENTINEL', ZERO)
        return ZERO, ZERO
    result = run(loads)
    refused(result, True)
    assert len(calls) == 3
    assert 'PRIVATE_SENTINEL' not in repr(result)


@pytest.mark.parametrize('exception', [KeyboardInterrupt, SystemExit, GeneratorExit])
def test_baseexception_propagates(exception):
    calls = []
    def loads(*args):
        calls.append(args)
        raise exception('PRIVATE_SENTINEL')
    with pytest.raises(exception):
        run(loads)
    assert len(calls) == 1


def test_canonical_snapshots_and_output():
    calls = []
    def loads(t, state):
        calls.append((t, state))
        assert type(t) is float and math.isfinite(t)
        assert type(state) is RigidBodyState
        for field, size in zip(FIELDS, (3, 3, 4, 3)):
            value = getattr(state, field)
            assert type(value) is tuple and len(value) == size
            assert all(type(x) is float and math.isfinite(x) for x in value)
        assert math.hypot(*state.quaternion_body_to_enu) == pytest.approx(1., abs=1e-15)
        with pytest.raises(FrozenInstanceError):
            state.position_enu_m = ZERO
        with pytest.raises(TypeError):
            state.position_enu_m[0] = 1.0
        return ZERO, ZERO
    result = run(loads)
    metadata(result)
    assert result['status'] == 'COMPUTED_EXPERIMENTAL' and result['reasons'] == []
    assert len(calls) == 8 and len({id(s) for _, s in calls}) == 8
    assert [t for t, _ in calls] == [0., .05, .05, .1, .1, .1 + .05, .1 + .05, .2]
    assert all(s == STATE for _, s in calls)
    out = result['outputs']
    assert set(out) == OUTPUTS and set(result['output_units']) == OUTPUTS
    assert out['elapsed_s'] == .2 and out['steps'] == 2 and out['load_evaluations'] == 8
    assert out['final_state'] == {f: list(getattr(STATE, f)) for f in FIELDS}
    assert out['final_quaternion_norm'] == 1.
    assert out['input_quaternion_norm_correction'] == 0.
    assert out['max_preprojection_quaternion_norm_error'] == 0.
