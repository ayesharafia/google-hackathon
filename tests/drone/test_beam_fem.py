import math
from itertools import pairwise

import numpy as np
import pytest

from physimesh.drone.beam_fem import (
    BeamPoint,
    BeamSolution,
    evaluate_solution,
    solve_beam,
)

KEY = {
    "L": "length_m",
    "E": "E_pa",
    "I": "I_m4",
    "c": "outer_fibre_m",
    "P": "tip_force_n",
    "q": "uniform_load_n_m",
    "n": "elements",
}
BASE = {
    "L": 3.2,
    "E": 70e9,
    "I": 8e-6,
    "c": 0.04,
    "P": 900.0,
    "q": 1200.0,
    "n": 4,
}
L, E, second_moment_m4, C, P, Q = (BASE[k] for k in ("L", "E", "I", "c", "P", "q"))


def solve(**changes):
    return solve_beam(**{KEY[k]: v for k, v in (BASE | changes).items()})


def close(actual, expected):
    assert actual == pytest.approx(expected, rel=3e-8, abs=2e-10)


def point(s, n, j, t):
    p = evaluate_solution(s, j, t)
    assert isinstance(p, BeamPoint)
    close(p.x_m, (j + t) * L / n)
    close(p.nominal_bending_stress_pa, E * C * p.curvature_1_m)
    return p


@pytest.mark.parametrize("n", [1, 2, 4, 8, 16])
def test_zero_and_pure_tip(n):
    zero, tip = solve(n=n, P=0.0, q=0.0), solve(n=n, q=0.0)
    for j in range(n):
        for t in (0.0, 0.17, 0.5, 0.83, 1.0):
            z, p = point(zero, n, j, t), point(tip, n, j, t)
            assert (
                z.deflection_m,
                z.rotation_rad,
                z.curvature_1_m,
                z.nominal_bending_stress_pa,
            ) == (0.0,) * 4
            x = (j + t) * L / n
            close(p.deflection_m, P * x**2 * (3 * L - x) / (6 * E * second_moment_m4))
            close(p.rotation_rad, P * x * (2 * L - x) / (2 * E * second_moment_m4))
            close(p.curvature_1_m, P * (L - x) / (E * second_moment_m4))
    assert len(zero.ndof) == 2 * (n + 1)
    assert all(value == 0.0 for value in zero.ndof)


@pytest.mark.parametrize("n", [1, 2, 4, 8, 16])
def test_uniform_nodal_exactness_and_reactions(n):
    s = solve(n=n, P=0.0)
    for j in range(n + 1):
        p = point(s, n, min(j, n - 1), float(j == n))
        x = j * L / n
        close(
            p.deflection_m,
            Q * x**2 * (6 * L**2 - 4 * L * x + x**2) / (24 * E * second_moment_m4),
        )
    tip = point(s, n, n - 1, 1.0)
    close(tip.deflection_m, Q * L**4 / (8 * E * second_moment_m4))
    close(tip.rotation_rad, Q * L**3 / (6 * E * second_moment_m4))
    close(s.root_force_n, -Q * L)
    close(s.root_moment_nm, -Q * L**2 / 2)


def test_midpoint_field_errors():
    errors = []
    for n in (1, 2, 4, 8, 16):
        samples = [point(solve(n=n, P=0.0), n, j, 0.5) for j in range(n)]
        exact_w = [
            Q * p.x_m**2 * (6 * L**2 - 4 * L * p.x_m + p.x_m**2)
            / (24 * E * second_moment_m4)
            for p in samples
        ]
        exact_k = [Q * (L - p.x_m)**2 / (2 * E * second_moment_m4) for p in samples]
        ew = max(abs(p.deflection_m - w) for p, w in zip(samples, exact_w))
        ek = max(abs(p.curvature_1_m - k) for p, k in zip(samples, exact_k))
        errors.append((ew, ek, ew / max(exact_w), ek / max(exact_k)))
    for a, b in pairwise(errors):
        assert all(0 < new < old for old, new in zip(a, b))
        assert math.log2(a[0] / b[0]) == pytest.approx(4, abs=0.03)
        assert math.log2(a[1] / b[1]) == pytest.approx(2, abs=0.03)


def test_linearity_and_storage():
    total, tip, uniform = solve(), solve(q=0.0), solve(P=0.0)
    assert isinstance(total, BeamSolution)
    assert len(total.displacements) == BASE["n"] + 1
    assert len(total.ndof) == 2 * (BASE["n"] + 1)
    assert total.ndof[:2] == (0.0, 0.0)
    for v in (
        total.elements,
        total.ndof,
        total.nodes,
        total.displacements,
        total.rotations,
    ):
        if v:
            with pytest.raises(TypeError):
                v[0] = v[0]
    for j in range(BASE["n"]):
        for t in (0.0, 0.29, 0.71, 1.0):
            points = [point(s, BASE["n"], j, t) for s in (total, tip, uniform)]
            for field in (
                "deflection_m",
                "rotation_rad",
                "curvature_1_m",
                "nominal_bending_stress_pa",
            ):
                close(
                    getattr(points[0], field),
                    getattr(points[1], field) + getattr(points[2], field),
                )


@pytest.mark.parametrize("key", ["L", "E", "I", "c", "P", "q", "n"])
def test_invalid_inputs(key):
    bad = [None, True, False, "1", float("inf"), float("nan"), np.float64(1)]
    bad += (
        [0, -1]
        if key in ("L", "E", "I", "c")
        else ([-1] if key in ("P", "q") else [0, 65, 2.0])
    )
    for value in bad:
        with pytest.raises((TypeError, ValueError)):
            solve(**{key: value})
    if key in ("L", "E", "I", "c"):
        with pytest.raises((TypeError, ValueError)):
            solve_beam(**{KEY[k]: v for k, v in BASE.items() if k != key})


def test_element_limits_and_invalid_local_evaluation():
    for n in (1, 64):
        assert isinstance(solve(n=n), BeamSolution)
    s = solve()
    invalid = [
        (-1, 0.5),
        (4, 0.5),
        (True, 0.5),
        (2.0, 0.5),
    ] + [
        (0, t)
        for t in (
            -0.1,
            1.1,
            True,
            "0.5",
            float("inf"),
            float("nan"),
            np.float64(0.5),
        )
    ]
    for j, t in invalid:
        with pytest.raises((TypeError, ValueError, IndexError)):
            evaluate_solution(s, j, t)
