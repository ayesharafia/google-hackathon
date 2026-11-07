import math
import sys
from dataclasses import dataclass
from itertools import pairwise

import numpy as np


@dataclass(frozen=True)
class BeamSolution:
    """Physical nodal values; elements contains each element's four DOF indices."""
    L: float
    E: float
    second_moment_m4: float
    c: float
    scale: float
    n: int
    elements: tuple[tuple[int, int, int, int], ...]
    ndof: tuple[float, ...]
    nodes: tuple[float, ...]
    displacements: tuple[float, ...]
    rotations: tuple[float, ...]
    root_force_n: float
    root_moment_nm: float
    normalized_linear_residual: float


def _number(value, name, positive):
    if type(value) not in (int, float):
        raise TypeError(f"{name} must be a built-in int or float")
    try:
        value = float(value)
    except OverflowError:
        raise ValueError(f"{name} exceeds finite float support") from None
    if not math.isfinite(value) or (value <= 0 if positive else value < 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return value


def _normal(value):
    if not math.isfinite(value) or value < sys.float_info.min:
        raise ValueError("Derived overflow/underflow: conservative finite-normal support exceeded")
    return value


def _product(*values):
    result = 1.0
    for value in values:
        result = _normal(result * value)
    return result


def _quotient(a, b):
    return _normal(a / b)


def _scaled(value, factor):
    return math.copysign(_product(abs(float(value)), factor), value) if value else 0.0


def solve_beam(*, length_m, E_pa, I_m4, outer_fibre_m, tip_force_n,
               uniform_load_n_m, elements=8):
    """Experimental constant-EI, 1D, small-deflection Euler–Bernoulli cantilever.
    Same-direction nonnegative loads; assumptions are not physically validated.
    Cubic Hermite FEM: https://ceae.colorado.edu/~regueiro/courses/CVEN4511_5511_notes.pdf
    Equation 3.28. Extreme mathematically solvable cases may be refused.
    Residual = ||Kff*uf-ff||inf/(max|Kff|*max|uf|+max|ff|):
    a diagnostic, not an error bound or physical acceptance criterion.
    """
    L, E, second_moment_m4, c = (_number(v, name, True) for v, name in
                  ((length_m, "length_m"), (E_pa, "E_pa"),
                   (I_m4, "I_m4"), (outer_fibre_m, "outer_fibre_m")))
    P = _number(tip_force_n, "tip_force_n", False)
    q = _number(uniform_load_n_m, "uniform_load_n_m", False)
    if type(elements) is not int or not 1 <= elements <= 64:
        raise ValueError("elements must be a built-in int in 1..64, excluding bool")
    n = elements
    nodes = (0.0,) + tuple(_product(L, i / n) for i in range(1, n + 1))
    if any(b <= a for a, b in pairwise(nodes)):
        raise ValueError("Physical node positions must be distinct and increasing")
    dofs = tuple((2*i, 2*i+1, 2*i+2, 2*i+3) for i in range(n))
    if P == 0 and q == 0:
        zeros = (0.0,) * (n + 1)
        return BeamSolution(L, E, second_moment_m4, c, 0.0, n, dofs, (0.0,) * (2*n+2),
                            nodes, zeros, zeros, 0.0, 0.0, 0.0)
    qL = _product(q, L) if q else 0.0
    S = _normal(max(P, qL))
    scale = _quotient(_product(S, L, L, L), _product(E, second_moment_m4))
    pbar, qbar = (_quotient(P, S) if P else 0.0), (_quotient(qL, S) if qL else 0.0)
    h = 1.0 / n
    ke = np.array([[12, 6*h, -12, 6*h], [6*h, 4*h*h, -6*h, 2*h*h],
                   [-12, -6*h, 12, -6*h], [6*h, 2*h*h, -6*h, 4*h*h]]) / h**3
    a = _quotient(_product(qbar, h), 2.0) if qbar else 0.0
    b = _quotient(_product(a, h), 6.0) if a else 0.0
    K, f = np.zeros((2*n+2, 2*n+2)), np.zeros(2*n+2)
    for d in dofs:
        K[np.ix_(d, d)] += ke
        f[list(d)] += np.array([a, b, a, -b])
    f[-2] += pbar
    u = np.zeros_like(f)
    Kff = K[2:, 2:]
    try:
        u[2:] = np.linalg.solve(Kff, f[2:])
    except np.linalg.LinAlgError as exc:
        raise ValueError("FEM linear solve failed") from exc
    reaction = K @ u - f
    if not np.all(np.isfinite(u)) or not np.all(np.isfinite(reaction)):
        raise ValueError("Nonfinite FEM solution")
    residual = float(np.max(np.abs(Kff @ u[2:] - f[2:]))) / (
        float(np.max(np.abs(Kff))) * float(np.max(np.abs(u[2:]))) + float(np.max(np.abs(f[2:]))))
    w = tuple(_scaled(v, scale) for v in u[::2])
    theta = tuple(_scaled(v, _quotient(scale, L)) for v in u[1::2])
    return BeamSolution(L, E, second_moment_m4, c, scale, n, dofs, tuple(map(float, u)), nodes, w, theta,
                        _scaled(reaction[0], S), _scaled(reaction[1], _product(S, L)), residual)


@dataclass(frozen=True)
class BeamPoint:
    x_m: float
    deflection_m: float
    rotation_rad: float
    curvature_1_m: float
    nominal_bending_stress_pa: float


def evaluate_solution(sol: BeamSolution, element_index: int,
                      local_coordinate: float) -> BeamPoint:
    """Evaluate the FEM interpolant; cancellation can round to zero."""
    if type(element_index) is not int or not 0 <= element_index < sol.n:
        raise ValueError("element_index must be a built-in int in range")
    t = _number(local_coordinate, "local_coordinate", False)
    if t > 1:
        raise ValueError("local_coordinate must be in [0, 1]")
    x = _scaled((element_index + t) / sol.n, sol.L)
    if sol.scale == 0:
        return BeamPoint(x, 0.0, 0.0, 0.0, 0.0)

    def multiply(a, b):
        if not math.isfinite(a) or not math.isfinite(b):
            raise ValueError("Nonfinite interpolation operand")
        if a == 0 or b == 0:
            return 0.0
        return math.copysign(_product(abs(a), abs(b)),
                             -1.0 if (a < 0) != (b < 0) else 1.0)

    rotation_scale = _quotient(sol.scale, sol.L)
    curvature_scale = _quotient(rotation_scale, sol.L)
    u = [sol.ndof[dof] for dof in sol.elements[element_index]]
    h = 1.0 / sol.n
    t2 = multiply(t, t)
    t3 = multiply(t2, t)
    h2 = _product(h, h)
    N = (1 - 3*t2 + 2*t3, multiply(h, t - 2*t2 + t3),
         3*t2 - 2*t3, multiply(h, -t2 + t3))
    D = ((-6*t + 6*t2)/h, 1 - 4*t + 3*t2,
         (6*t - 6*t2)/h, -2*t + 3*t2)
    DD = ((-6 + 12*t)/h2, (-4 + 6*t)/h,
          (6 - 12*t)/h2, (-2 + 6*t)/h)

    def interpolate(coefficients):
        try:
            result = math.fsum(multiply(a, b) for a, b in zip(coefficients, u))
        except OverflowError:
            raise ValueError("Interpolation overflow") from None
        if not math.isfinite(result):
            raise ValueError("Nonfinite interpolated value")
        return result

    w = _scaled(interpolate(N), sol.scale)
    rotation = _scaled(interpolate(D), rotation_scale)
    curvature = _scaled(interpolate(DD), curvature_scale)
    stress = _scaled(curvature, _product(sol.E, sol.c)) if curvature else 0.0
    return BeamPoint(x, w, rotation, curvature, stress)
