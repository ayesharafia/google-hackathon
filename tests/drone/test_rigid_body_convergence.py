"""Analytic numerical convergence checks; physical validation NOT_ESTABLISHED.

No aircraft feasibility is established. Only math and pytest supplement the
kernel's own dependencies; the oracle does not use SciPy or kernel internals.
"""

import math
from itertools import pairwise

import pytest

from physimesh.drone.rigid_body import RigidBodyState, propagate_rigid_body


def _add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def _scale(s, a):
    return tuple(s * x for x in a)


def _hamilton(a, b):
    w, x, y, z = a
    v, i, j, k = b
    return (w*v - x*i - y*j - z*k,
            w*i + x*v + y*k - z*j,
            w*j - x*k + y*v + z*i,
            w*k + x*j - y*i + z*v)


def _rotate(q, v):
    # Quaternion sandwich provides an independent rotation oracle.
    conjugate = (q[0], -q[1], -q[2], -q[3])
    return _hamilton(_hamilton(q, (0., *v)), conjugate)[1:]


def _exact(t, rate, q0, p0, v0, force, mass, gravity):
    # Spherical I and zero moment imply omega = rate*n, constant in body.
    # Hence q(t)=q0*(cos(rate*t/2), n*sin(rate*t/2)). Write F=A+B,
    # A=n(n.F), C=n cross F. Rodrigues gives R_n(rate*t)F=A+B cos+C sin.
    # Integrate once: A*t+B*sin/rate+C*(1-cos)/rate.
    # Integrate twice: A*t^2/2+B*(1-cos)/rate^2
    #                         +C*(t/rate-sin/rate^2).
    # Premultiply both force integrals by R(q0)/mass; add ballistic terms.
    n = (2./3., -1./3., 2./3.)
    a = _scale(sum(x*y for x, y in zip(n, force)), n)
    b = _add(force, _scale(-1., a))
    c = (n[1]*force[2] - n[2]*force[1],
         n[2]*force[0] - n[0]*force[2],
         n[0]*force[1] - n[1]*force[0])
    sine, cosine = math.sin(rate*t), math.cos(rate*t)
    impulse = _add(_scale(t, a), _add(_scale(sine/rate, b),
                                     _scale((1.-cosine)/rate, c)))
    displacement = _add(_scale(.5*t*t, a),
                        _add(_scale((1.-cosine)/rate**2, b),
                             _scale(t/rate-sine/rate**2, c)))
    velocity = _add(v0, _add(_scale(t, gravity), _scale(1./mass, _rotate(q0, impulse))))
    position = _add(p0, _add(_scale(t, v0),
                            _add(_scale(.5*t*t, gravity),
                                 _scale(1./mass, _rotate(q0, displacement)))))
    q = _hamilton(q0, (math.cos(.5*rate*t), *_scale(math.sin(.5*rate*t), n)))
    return {'position_enu_m': position, 'velocity_enu_m_s': velocity,
            'quaternion_body_to_enu': q}


@pytest.mark.parametrize('rate', [1.3, -1.3])
def test_rotating_body_force_coupled_closed_form_fourth_order(rate):
    # Nonidentity attitude, oblique body axis, transverse AND axial force,
    # nonzero initial translation and gravity exercise every translation axis.
    # A noninteger phase (3.51 radians) avoids full-turn cancellation.
    duration = 2.7
    q0 = (.5, .5, -.5, .5)
    p0, v0 = (1.1, -2.3, .7), (-.4, .6, .2)
    force, gravity, mass = (2.2, -.7, 1.3), (.15, -.2, -9.4), 2.3
    omega = _scale(rate, (2./3., -1./3., 2./3.))
    exact = _exact(duration, rate, q0, p0, v0, force, mass, gravity)
    errors = {field: [] for field in exact}
    for steps in (12, 24, 48, 96):
        result = propagate_rigid_body(
            initial_state=RigidBodyState(p0, v0, q0, omega),
            mass_kg=mass,
            inertia_body_kg_m2=((2., 0., 0.), (0., 2., 0.), (0., 0., 2.)),
            force_body_n=force, moment_cg_body_nm=(0., 0., 0.),
            gravity_enu_m_s2=gravity, dt_s=duration/steps, steps=steps)
        assert result['status'] == 'COMPUTED_EXPERIMENTAL', result['reasons']
        assert result['physical_validation'] == 'NOT_ESTABLISHED'
        assert result['aircraft_status'] is None and result['feasibility'] is None
        output = result['outputs']
        assert output['elapsed_s'] == pytest.approx(duration, abs=1e-14, rel=0.)
        final = output['final_state']
        assert final['angular_velocity_body_rad_s'] == pytest.approx(omega, abs=2e-14, rel=0.)
        for field, expected in exact.items():
            error = math.dist(final[field], expected)
            errors[field].append(error)
    # Each observable must converge independently; a combined norm could hide
    # a broken translation channel behind the attitude error (or vice versa).
    for field, values in errors.items():
        orders = [math.log2(a/b) for a, b in pairwise(values)]
        assert all(3.7 < order < 4.3 for order in orders), (field, values, orders)
        assert values[-1] < 2e-7, (field, values)
