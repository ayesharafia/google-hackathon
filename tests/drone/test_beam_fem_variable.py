"""Independent beam arithmetic tests; physical validation is NOT_ESTABLISHED."""
import itertools
import math
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from physimesh.drone.beam_fem_variable import (
    evaluate_variable_solution,
    solve_beam_variable,
)

L, E, I0, C = 2.0, 70e9, 1e-6, 0.01


def solve(nodes=(0.0, 0.1, 0.35, 1.0, 2.0), **changes):
    nodes = changes.get('nodes_m', nodes)
    args = {'length_m': L, 'E_pa': E, 'nodes_m': nodes,
                'second_moments_m4': tuple(I0 * (1 - x / (2 * L)) for x in nodes),
                'outer_fibre_m': C, 'tip_force_n': 10.0, 'uniform_load_n_m': 100.0}
    args.update(changes)
    return solve_beam_variable(**args)


def field(sol, i, t):
    """Independent physical Hermite field from the documented scaled DOFs."""
    h = (sol.nodes[i + 1] - sol.nodes[i]) / sol.L
    u = sol.ndof[2 * i:2 * i + 4]
    N = (1 - 3*t*t + 2*t**3, h*(t - 2*t*t + t**3),
         3*t*t - 2*t**3, h*(-t*t + t**3))
    D = ((-6*t + 6*t*t)/h, 1 - 4*t + 3*t*t,
         (6*t - 6*t*t)/h, -2*t + 3*t*t)
    B = ((-6 + 12*t)/h**2, (-4 + 6*t)/h,
         (6 - 12*t)/h**2, (-2 + 6*t)/h)
    return (sol.scale * math.fsum(a*b for a, b in zip(N, u)),
            sol.scale / sol.L * math.fsum(a*b for a, b in zip(D, u)),
            sol.E * sol.c * sol.scale / sol.L**2
            * math.fsum(a*b for a, b in zip(B, u)))


def test_constant_regression():
    # The V39 constant-EI nodal baseline has these closed-form P/q values.
    for n in (1, 4, 16):
        nodes = tuple(L*i/n for i in range(n + 1))
        for P, q in ((10.0, 0.0), (0.0, 100.0), (10.0, 100.0)):
            s = solve(nodes, second_moments_m4=(I0,)*(n + 1),
                      tip_force_n=P, uniform_load_n_m=q)
            w = tuple((P*x*x*(3*L-x)/6 + q*x*x*(6*L*L-4*L*x+x*x)/24)
                      / (E*I0) for x in nodes)
            theta = tuple((P*x*(2*L-x)/2 + q*x*(3*L*L-3*L*x+x*x)/6)
                          / (E*I0) for x in nodes)
            assert s.displacements == pytest.approx(w, rel=1e-7, abs=1e-12)
            assert s.rotations == pytest.approx(theta, rel=1e-7, abs=1e-12)


def test_statics_ramp_tip_moment_and_linear_I_tip_force():
    P, q, qr, qt, M = 10.0, 100.0, 30.0, 75.0, 12.0
    s = solve(ramp_load_root_n_m=qr, ramp_load_tip_n_m=qt, tip_moment_n_m=M)
    assert s.root_force_n == pytest.approx(-(P + q*L + (qr+qt)*L/2), rel=1e-9)
    assert s.root_moment_nm == pytest.approx(
        -(P*L + q*L*L/2 + (qr+2*qt)*L*L/6 + M), rel=1e-9)
    s = solve(tuple(L*i/64 for i in range(65)), uniform_load_n_m=0.0)
    assert s.displacements[-1] == pytest.approx(4.4147926985130356e-4, rel=1e-6)
    assert s.rotations[-1] == pytest.approx(3.5068893650291965e-4, rel=1e-5)
    assert math.isfinite(s.normalized_linear_residual)
    assert 0 <= s.normalized_linear_residual < 1e-12


def test_zero_and_strict_validation():
    zero = {'tip_force_n': 0.0, 'uniform_load_n_m': 0.0}
    s = solve(**zero)
    assert s.displacements == s.rotations == (0.0,)*5
    assert s.ndof == (0.0,)*10
    assert (s.root_force_n, s.root_moment_nm, s.normalized_linear_residual) == (0, 0, 0)
    for name in ('length_m', 'E_pa', 'outer_fibre_m', 'tip_force_n',
                 'uniform_load_n_m', 'ramp_load_root_n_m', 'ramp_load_tip_n_m',
                 'tip_moment_n_m'):
        for bad in (True, '1', float('nan'), float('inf'), 10**1000, np.float64(1)):
            with pytest.raises((TypeError, ValueError, OverflowError)):
                solve(**(zero | {name: bad}))
        with pytest.raises((TypeError, ValueError)):
            solve(**(zero | {name: -1.0}))
    invalid = [{'nodes_m': [0.0, L]}, {'nodes_m': (0.0,)},
               {'nodes_m': (0.1, L)}, {'nodes_m': (0.0, 1.9)},
               {'nodes_m': (0.0, 1.0, 1.0, L)}, {'nodes_m': (0.0, 1.5, 1.0, L)},
               {'nodes_m': (0.0, L*2**-21, L)},
               {'nodes_m': (0.0, L/2048, L)},
               {'nodes_m': tuple(L*i/65 for i in range(66))},
               {'second_moments_m4': [I0]*5}, {'second_moments_m4': (I0,)*4}]
    invalid += [{'second_moments_m4': (I0, I0, I0, I0, v)}
                for v in (0.0, -I0, True, '1', math.nan, math.inf, 10**1000, I0*1e-13)]
    invalid += [{'length_m': 0}, {'E_pa': 0}, {'outer_fibre_m': 0}]
    for changes in invalid:
        with pytest.raises((TypeError, ValueError, OverflowError)):
            solve(**(zero | changes))
    with pytest.raises(TypeError):
        solve(unknown_load_n=1.0)


def test_evaluator_validation_and_exact_statics_edge():
    for s in (
        solve((0.0, L), second_moments_m4=(I0, I0)),
        solve((0.0, L), second_moments_m4=(I0, I0),
              tip_force_n=0.0, uniform_load_n_m=0.0),
    ):
        for i in (True, False, -1, s.n, 0.0, '0'):
            with pytest.raises((TypeError, ValueError)):
                evaluate_variable_solution(s, i, 0.5)
        for t in (True, False, '0.5', math.nan, math.inf, -math.inf, -0.1, 1.1):
            with pytest.raises((TypeError, ValueError)):
                evaluate_variable_solution(s, 0, t)
    for name, value, force, moment in (
        ('tip_force_n', 10.0, -10.0, -10.0*L),
        ('uniform_load_n_m', 100.0, -100.0*L, -100.0*L**2/2),
        ('ramp_load_root_n_m', 30.0, -30.0*L/2, -30.0*L**2/6),
        ('ramp_load_tip_n_m', 75.0, -75.0*L/2, -75.0*L**2/3),
        ('tip_moment_n_m', 12.0, 0.0, -12.0),
    ):
        loads = {'tip_force_n': 0.0, 'uniform_load_n_m': 0.0, name: value}
        s = solve((0.0, L), second_moments_m4=(I0, I0), **loads)
        assert s.root_force_n == pytest.approx(force, rel=1e-11, abs=1e-11)
        assert s.root_moment_nm == pytest.approx(moment, rel=1e-11, abs=1e-11)


def test_mms_field_order():
    errors = []
    for n in (4, 8, 16):
        nodes = tuple(L*i/n for i in range(n + 1))
        s = solve(nodes, second_moments_m4=tuple(I0*(1+x/(2*L)) for x in nodes),
                  tip_force_n=0.0, uniform_load_n_m=0.0, ramp_load_tip_n_m=157.5)
        ew, es = [], []
        for j in range(1600):
            z = (j + 0.5)/1600
            i = min(int(z*n), n - 1)
            t = z*n-i
            w, rotation, stress = field(s, i, t)
            actual = evaluate_variable_solution(s, i, t)
            assert actual.deflection_m == pytest.approx(w, rel=1e-10, abs=1e-14)
            assert actual.rotation_rad == pytest.approx(rotation, rel=1e-10, abs=1e-14)
            assert actual.nominal_bending_stress_pa == pytest.approx(
                stress, rel=1e-10, abs=1e-9)
            ew.append((actual.deflection_m - .001*z*z*(6-4*z+z*z))**2)
            es.append((actual.nominal_bending_stress_pa
                       - E*C*.001/L**2*(12-24*z+12*z*z))**2)
        errors.append((math.sqrt(math.fsum(ew)/1600), math.sqrt(math.fsum(es)/1600)))
        assert s.displacements[-1] == pytest.approx(.003, rel=0.002)
    for coarse, fine in itertools.pairwise(errors):
        assert fine[0] > 1e-14 and fine[1] > 1e-6
        assert 3.7 < math.log2(coarse[0]/fine[0]) < 4.3
        assert 1.8 < math.log2(coarse[1]/fine[1]) < 2.2


def test_scaling_continuity_and_immutability():
    for n in (8, 16):
        nodes = tuple(L*(i/n)**1.5 for i in range(n + 1))
        s = solve(nodes, uniform_load_n_m=0.0)
        before = (s.nodes, s.ndof, s.displacements, s.rotations, s.second_moments_m4)
        assert s.physical_validation == 'NOT_ESTABLISHED'
        assert s.elements == tuple((2*i, 2*i+1, 2*i+2, 2*i+3) for i in range(n))
        for i in range(n - 1):
            a = evaluate_variable_solution(s, i, 1.0)
            b = evaluate_variable_solution(s, i + 1, 0.0)
            assert (a.x_m, a.deflection_m, a.rotation_rad) == pytest.approx(
                (b.x_m, b.deflection_m, b.rotation_rad), abs=1e-12)
        variants = [({'E_pa': 2*E}, (.5, .5, 1), 1),
                    ({'second_moments_m4': tuple(2*v for v in s.second_moments_m4)},
                     (.5, .5, .5), 1), ({'tip_force_n': 20.0}, (2, 2, 2), 2),
                    ({'length_m': 2*L, 'nodes_m': tuple(2*x for x in nodes),
                          'second_moments_m4': s.second_moments_m4}, (8, 4, 2), 1)]
        for changes, factors, reaction_factor in variants:
            v = solve(nodes, **({'uniform_load_n_m': 0.0} | changes))
            assert v.displacements == pytest.approx(tuple(factors[0]*x for x in s.displacements))
            assert v.rotations == pytest.approx(tuple(factors[1]*x for x in s.rotations))
            for i in range(n):
                assert field(v, i, .37)[2] == pytest.approx(factors[2]*field(s, i, .37)[2])
            assert v.root_force_n == pytest.approx(reaction_factor*s.root_force_n, rel=1e-8)
            length_factor = v.L/s.L
            assert v.root_moment_nm == pytest.approx(reaction_factor*length_factor*s.root_moment_nm, rel=1e-8)
        with pytest.raises((FrozenInstanceError, AttributeError)):
            s.scale = 0.0
        with pytest.raises(TypeError):
            s.ndof[0] = 1.0
        assert before == (s.nodes, s.ndof, s.displacements, s.rotations, s.second_moments_m4)
