"""Independent numerical oracles; physical validation NOT_ESTABLISHED."""

import math
from itertools import pairwise

import pytest

from physimesh.drone.rigid_body_stage_loads import (
    RigidBodyState,
    propagate_rigid_body_stage_loads,
)

DTS = (0.2, 0.1, 0.05, 0.025)
ZERO = (0.0, 0.0, 0.0)
Q0 = (0.5, 0.5, 0.5, 0.5)
INERTIA = ((3.0, 0.0, 0.0), (0.0, 4.0, 0.0), (0.0, 0.0, 2.0))
FIELDS = ("position_enu_m", "velocity_enu_m_s",
          "quaternion_body_to_enu", "angular_velocity_body_rad_s")


def floats(values):
    return tuple(float(x) for x in values)


def hamilton(a, b):
    w, x, y, z = a
    s, u, v, r = b
    return (w*s-x*u-y*v-z*r, w*u+x*s+y*r-z*v,
            w*v-x*r+y*s+z*u, w*r+x*v-y*u+z*s)


def rotate(q, v):
    conjugate = (q[0], -q[1], -q[2], -q[3])
    return hamilton(hamilton(q, (0.0, *v)), conjugate)[1:]


def solve(initial, callback, dt, steps=None):
    result = propagate_rigid_body_stage_loads(
        initial_state=initial, mass_kg=2.0, inertia_body_kg_m2=INERTIA,
        gravity_enu_m_s2=ZERO, dt_s=dt,
        steps=round(2.0 / dt) if steps is None else steps,
        load_function=callback)
    assert result["status"] == "COMPUTED_EXPERIMENTAL", result["reasons"]
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["aircraft_status"] is None and result["feasibility"] is None
    assert result["outputs"]["load_evaluations"] == 4 * result["outputs"]["steps"]
    return result["outputs"]["final_state"]


def check_refinement(states, exact):
    for field, expected in zip(FIELDS, exact):
        for component, reference in enumerate(expected):
            errors = [abs(state[field][component] - reference) for state in states]
            assert errors[-1] < 2e-7, (field, component, errors)
            for coarse, fine in pairwise(errors):
                if min(coarse, fine) > 5e-13:
                    order = math.log2(coarse / fine)
                    assert 3.7 <= order <= 4.4, (field, component, errors, order)


def test_time_quadratic_force_exact_polynomial():
    initial = RigidBodyState(ZERO, ZERO, (1.0, 0.0, 0.0, 0.0), ZERO)

    def loads(t, state):
        return floats((t*t, 0, 0)), floats(ZERO)

    exact = ((2.0**4 / 24, 0, 0), (2.0**3 / 6, 0, 0),
             initial.quaternion_body_to_enu, ZERO)
    states = [solve(initial, loads, dt) for dt in DTS]
    check_refinement(states, exact)
    for state in states:
        for field, expected in zip(FIELDS, exact):
            assert state[field] == pytest.approx(expected, rel=0, abs=2e-14)


def test_enu_velocity_damping_translated_nonidentity_attitude():
    p0, v0 = (3.0, -2.0, 1.0), (2.0, -1.0, 0.5)
    initial = RigidBodyState(p0, v0, Q0, ZERO)

    def loads(t, state):
        q = state.quaternion_body_to_enu
        inverse = (q[0], -q[1], -q[2], -q[3])
        force = rotate(inverse, tuple(-1.4*v for v in state.velocity_enu_m_s))
        return floats(force), floats(ZERO)

    decay = math.exp(-0.7 * 2.0)
    exact = (tuple(p + v*(1-decay)/0.7 for p, v in zip(p0, v0)),
             tuple(v*decay for v in v0), Q0, ZERO)
    check_refinement([solve(initial, loads, dt) for dt in DTS], exact)


def test_independent_one_step_rk4_snapshots():
    initial = RigidBodyState((3.0, -2.0, 1.0), (2.0, -1.0, 0.5),
                             Q0, (0.0, 0.0, 1.2))
    captured = []

    def loads(t, state):
        captured.append((t, state))
        q = state.quaternion_body_to_enu
        inverse = (q[0], -q[1], -q[2], -q[3])
        force = [-1.4*v for v in state.velocity_enu_m_s]
        force[0] += t*t
        return floats(rotate(inverse, force)), floats(
            -1.6*w for w in state.angular_velocity_body_rad_s)

    def rhs(t, y):
        qdot = tuple(x/2 for x in hamilton(y[6:10], (0.0, *y[10:13])))
        return (*y[3:6], t*t/2-0.7*y[3], -0.7*y[4], -0.7*y[5],
                *qdot, 0.0, 0.0, -0.8*y[12])

    def shifted(y, k, scale):
        return tuple(a+scale*b for a, b in zip(y, k))

    h = 0.2
    y = tuple(x for field in FIELDS for x in getattr(initial, field))
    k1 = rhs(0.0, y)
    y2 = shifted(y, k1, h/2)
    k2 = rhs(h/2, y2)
    y3 = shifted(y, k2, h/2)
    k3 = rhs(h/2, y3)
    y4 = shifted(y, k3, h)
    k4 = rhs(h, y4)
    final = solve(initial, loads, h, steps=1)
    assert len(captured) == 4
    for (time, state), expected_time, raw in zip(
            captured, (0.0, h/2, h/2, h), (y, y2, y3, y4)):
        assert time == expected_time
        norm = math.sqrt(sum(x*x for x in raw[6:10]))
        expected = (*raw[:6], *(x/norm for x in raw[6:10]), *raw[10:])
        actual = tuple(x for field in FIELDS for x in getattr(state, field))
        assert actual == pytest.approx(expected, rel=0, abs=3e-14)
    end = tuple(a+h*(b+2*c+2*d+e)/6 for a, b, c, d, e in zip(y, k1, k2, k3, k4))
    norm = math.sqrt(sum(x*x for x in end[6:10]))
    expected = (*end[:6], *(x/norm for x in end[6:10]), *end[10:])
    actual = tuple(x for field in FIELDS for x in final[field])
    assert actual == pytest.approx(expected, rel=0, abs=3e-14)


def test_principal_axis_angular_damping_and_integrated_attitude():
    initial = RigidBodyState(ZERO, ZERO, Q0, (0.0, 0.0, 1.2))

    def loads(t, state):
        return floats(ZERO), floats(tuple(-1.6*w for w in state.angular_velocity_body_rad_s))

    decay = math.exp(-0.8 * 2.0)
    angle = 1.2 * (1-decay) / 0.8
    q = hamilton(Q0, (math.cos(angle/2), 0.0, 0.0, math.sin(angle/2)))
    exact = (ZERO, ZERO, q, (0.0, 0.0, 1.2*decay))
    check_refinement([solve(initial, loads, dt) for dt in DTS], exact)
