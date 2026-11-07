"""Bounded algebraic MMS; physical validation NOT_ESTABLISHED.

The two quaternion signs are a paired representation check, not independent
experiments. Mathematical loads convey no aircraft feasibility evidence.
"""
import math
import unittest

from physimesh.drone.rigid_body import RigidBodyState
from physimesh.drone.rigid_body_stage_loads import propagate_rigid_body_stage_loads

HS = (0.1, 0.05, 0.025, 0.0125)
MASS = 2.0
INERTIA = ((2.0, 0.2, 0.1), (0.2, 3.0, 0.15), (0.1, 0.15, 4.0))
GRAVITY = (0.0, 0.0, -9.81)
FIELDS = ('position_enu_m', 'velocity_enu_m_s',
          'quaternion_body_to_enu', 'angular_velocity_body_rad_s')
# Finite-case absolute bounds in m, m/s, dimensionless chord, rad/s.
ERROR_LIMITS = (2e-5, 2e-5, 2e-6, 2e-6)
ORDER_BOUNDS = (3.7, 4.3)
# Conservative binary64 reference/arithmetic resolution gate, per field.
# Orders below this gate are reported but do not constitute resolved evidence.
FLOORS = (2e-13, 2e-13, 2e-13, 2e-13)
RESIDUAL_TOL = 2e-14
SIGN_TOL = 2e-14
UNIT_TOL = 8e-16


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def scale(k, a):
    return tuple(float(k*x) for x in a)


def mv(a, x):
    return tuple(sum(v*w for v, w in zip(row, x)) for row in a)


def cross(a, b):
    x, y, z = a
    u, v, w = b
    return (y*w-z*v, z*u-x*w, x*v-y*u)


def product(a, b):
    s, x, y, z = a
    r, u, v, w = b
    return (s*r-x*u-y*v-z*w, s*u+x*r+y*w-z*v,
            s*v-x*w+y*r+z*u, s*w+x*v-y*u+z*r)


def rotation(q):
    s, x, y, z = q
    return ((s*s+x*x-y*y-z*z, 2*(x*y-s*z), 2*(x*z+s*y)),
            (2*(x*y+s*z), s*s-x*x+y*y-z*z, 2*(y*z-s*x)),
            (2*(x*z-s*y), 2*(y*z+s*x), s*s-x*x-y*y+z*z))


def exact(t, branch=1):
    phi = 0.2*t + 0.05*t*t + 0.01*math.sin(t)
    q = scale(branch, (math.cos(phi/2), 0.0, 0.0, math.sin(phi/2)))
    return RigidBodyState(
        (math.sin(t), math.cos(t), t*t/4),
        (math.cos(t), -math.sin(t), t/2), q,
        (0.0, 0.0, 0.2+0.1*t+0.01*math.cos(t)))


def loads(t, state, branch):
    ref = exact(t, branch)
    qr = ref.quaternion_body_to_enu
    eq = product((qr[0], -qr[1], -qr[2], -qr[3]),
                 state.quaternion_body_to_enu)[1:]
    a = (-math.sin(t), -math.cos(t), 0.5)
    target = sub(sub(sub(a, GRAVITY),
                     sub(state.position_enu_m, ref.position_enu_m)),
                 scale(0.5, sub(state.velocity_enu_m_s, ref.velocity_enu_m_s)))
    r = rotation(state.quaternion_body_to_enu)
    force = scale(MASS, mv(tuple(zip(*r)), target))
    w = state.angular_velocity_body_rad_s
    wd = (0.0, 0.0, 0.1-0.01*math.sin(t))
    angular = sub(sub(wd, scale(0.5, sub(w, ref.angular_velocity_body_rad_s))),
                  scale(0.2, eq))
    moment = add(mv(INERTIA, angular), cross(w, mv(INERTIA, w)))
    return tuple(float(x) for x in force), tuple(float(x) for x in moment)


def norm(x):
    return math.hypot(*x)


def errors(actual, reference):
    result = []
    for field in FIELDS:
        a, b = actual[field], getattr(reference, field)
        e = norm(sub(a, b))
        if field == 'quaternion_body_to_enu':
            e = min(e, norm(add(a, b)))
        result.append(e)
    return tuple(result)


class ManufacturedSolutionTests(unittest.TestCase):
    def test_algebraic_substitution_and_paired_sign_loads(self):
        for branch in (1, -1):
            for i in range(41):
                t = i/20
                s = exact(t, branch)
                force, moment = loads(t, s, branch)
                a = add(scale(1/MASS, mv(rotation(s.quaternion_body_to_enu), force)), GRAVITY)
                self.assertLess(norm(sub(a, (-math.sin(t), -math.cos(t), 0.5))), RESIDUAL_TOL)
                w = s.angular_velocity_body_rad_s
                residual = sub(moment, cross(w, mv(INERTIA, w)))
                self.assertLess(norm(sub(residual, mv(INERTIA, (0.0, 0.0, 0.1-0.01*math.sin(t))))), RESIDUAL_TOL)
                qdot = scale(0.5, product(s.quaternion_body_to_enu, (0.0, *w)))
                phi = 0.2*t+0.05*t*t+0.01*math.sin(t)
                expected = scale(branch*0.5*w[2], (-math.sin(phi/2), 0.0, 0.0, math.cos(phi/2)))
                self.assertLess(norm(sub(qdot, expected)), RESIDUAL_TOL)
        s = exact(0.7)
        q = add(s.quaternion_body_to_enu, (0.0, 0.01, -0.015, 0.005))
        q = scale(1/norm(q), q)
        p = add(s.position_enu_m, (0.1, -0.02, 0.03))
        v = add(s.velocity_enu_m_s, (0.02, 0.01, -0.03))
        w = add(s.angular_velocity_body_rad_s, (0.01, -0.02, 0.03))
        plus = loads(0.7, RigidBodyState(p, v, q, w), 1)
        minus = loads(0.7, RigidBodyState(p, v, scale(-1, q), w), -1)
        for a, b in zip(plus, minus):
            self.assertLess(norm(sub(a, b)), SIGN_TOL)

    def test_four_field_refinement_and_paired_sign(self):
        paired = {}
        for branch in (1, -1):
            rows = []
            finals = []
            for h in HS:
                calls = []
                def callback(t, state):
                    calls.append(t)
                    self.assertIs(type(t), float)
                    self.assertIs(type(state), RigidBodyState)
                    for field, size in zip(FIELDS, (3, 3, 4, 3)):
                        value = getattr(state, field)
                        self.assertIs(type(value), tuple)
                        self.assertEqual(len(value), size)
                        self.assertTrue(all(type(x) is float and math.isfinite(x) for x in value))
                    self.assertLessEqual(abs(norm(state.quaternion_body_to_enu)-1), UNIT_TOL)
                    return loads(t, state, branch)
                steps = round(2/h)
                result = propagate_rigid_body_stage_loads(
                    initial_state=exact(0.0, branch), mass_kg=MASS,
                    inertia_body_kg_m2=INERTIA, gravity_enu_m_s2=GRAVITY,
                    dt_s=h, steps=steps, load_function=callback)
                self.assertEqual(result['status'], 'COMPUTED_EXPERIMENTAL', result['reasons'])
                self.assertEqual(result['physical_validation'], 'NOT_ESTABLISHED')
                self.assertIsNone(result['aircraft_status'])
                self.assertIsNone(result['feasibility'])
                output = result['outputs']
                self.assertEqual(len(calls), 4*steps)
                self.assertEqual(output['load_evaluations'], len(calls))
                self.assertEqual(output['elapsed_s'], 2.0)
                for i in range(steps):
                    expected = (i*h, i*h+h/2, i*h+h/2, (i+1)*h)
                    self.assertEqual(tuple(calls[4*i:4*i+4]), expected)
                final = output['final_state']
                finals.append(final)
                row = errors(final, exact(2.0, branch))
                self.assertTrue(all(math.isfinite(e) and 0 < e < lim for e, lim in zip(row, ERROR_LIMITS)))
                rows.append(row)
            for j, field in enumerate(FIELDS):
                es = [row[j] for row in rows]
                orders = [math.log2(a/b) for a, b in zip(es, es[1:])]
                resolved = [min(a, b) > FLOORS[j] for a, b in zip(es, es[1:])]
                self.assertTrue(all(resolved[:2]), (field, es))
                for order, use in zip(orders, resolved):
                    if use:
                        self.assertTrue(ORDER_BOUNDS[0] <= order <= ORDER_BOUNDS[1], (field, es, orders))
                print('paired branch', branch, field, 'errors', es, 'orders', orders, 'resolved', resolved)
            paired[branch] = finals
        for plus, minus in zip(paired[1], paired[-1]):
            for field in FIELDS:
                b = scale(-1, minus[field]) if field == 'quaternion_body_to_enu' else minus[field]
                self.assertLess(norm(sub(plus[field], b)), SIGN_TOL)


if __name__ == '__main__':
    unittest.main(verbosity=2)
