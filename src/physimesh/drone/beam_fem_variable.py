import math
import sys
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from .beam_fem import BeamPoint, _normal, _number, _product, _quotient, _scaled


@dataclass(frozen=True)
class VariableBeamSolution:
    L: float
    E: float
    rigidity_root_n_m2: float
    c: float
    scale: float
    n: int
    elements: tuple[tuple[int, int, int, int], ...]
    ndof: tuple[float, ...]
    nodes: tuple[float, ...]
    displacements: tuple[float, ...]
    rotations: tuple[float, ...]
    second_moments_m4: tuple[float, ...]
    root_force_n: float
    root_moment_nm: float
    normalized_linear_residual: float
    physical_validation: str = "NOT_ESTABLISHED"


def _multiply(a, b):
    if not math.isfinite(a) or not math.isfinite(b):
        raise ValueError("Nonfinite arithmetic operand")
    if a == 0 or b == 0:
        return 0.0
    return math.copysign(_product(abs(a), abs(b)),
                         -1.0 if (a < 0) != (b < 0) else 1.0)


def _sum(values):
    try:
        result = math.fsum(values)
    except (OverflowError, ValueError):
        raise ValueError("Nonfinite arithmetic sum") from None
    if result:
        _normal(abs(result))
    return result


def _check_array(values):
    if (not np.all(np.isfinite(values))
            or np.any((values != 0) & (np.abs(values) < sys.float_info.min))):
        raise ValueError("FEM arithmetic exceeds finite-normal support")


def _shapes(t, h):
    t2 = _multiply(t, t)
    t3 = _multiply(t2, t)
    h2 = _product(h, h)
    N = (1 - 3*t2 + 2*t3, _multiply(h, t - 2*t2 + t3),
         3*t2 - 2*t3, _multiply(h, -t2 + t3))
    D = ((-6*t + 6*t2)/h, 1 - 4*t + 3*t2,
         (6*t - 6*t2)/h, -2*t + 3*t2)
    B = ((-6 + 12*t)/h2, (-4 + 6*t)/h,
         (6 - 12*t)/h2, (-2 + 6*t)/h)
    return N, D, B


def solve_beam_variable(*, length_m, E_pa, second_moments_m4, nodes_m,
                        outer_fibre_m, tip_force_n=0., uniform_load_n_m=0.,
                        ramp_load_root_n_m=0., ramp_load_tip_n_m=0.,
                        tip_moment_n_m=0.):
    L = _number(length_m, "length_m", True)
    E = _number(E_pa, "E_pa", True)
    c = _number(outer_fibre_m, "outer_fibre_m", True)
    P, q, qr, qt, M = (
        _number(value, name, False) for value, name in (
            (tip_force_n, "tip_force_n"), (uniform_load_n_m, "uniform_load_n_m"),
            (ramp_load_root_n_m, "ramp_load_root_n_m"),
            (ramp_load_tip_n_m, "ramp_load_tip_n_m"),
            (tip_moment_n_m, "tip_moment_n_m")))
    if type(nodes_m) is not tuple or type(second_moments_m4) is not tuple:
        raise TypeError("nodes_m and second_moments_m4 must be built-in tuples")
    if not 2 <= len(nodes_m) <= 65 or len(second_moments_m4) != len(nodes_m):
        raise ValueError("Node and inertia tuples must have equal lengths in 2..65")
    nodes = tuple(_number(v, "nodes_m entry", False) for v in nodes_m)
    moments = tuple(_number(v, "second_moments_m4 entry", True)
                    for v in second_moments_m4)
    if nodes[0] != 0.0 or nodes[-1] != L:
        raise ValueError("nodes_m must start at zero and end at length_m")
    if any(b <= a for a, b in pairwise(nodes)):
        raise ValueError("nodes_m must be strictly increasing")
    lengths = tuple(_normal(b - a) for a, b in pairwise(nodes))
    if min(lengths) < _product(L, 2.0**-20):
        raise ValueError("Minimum element length must be at least length_m * 2**-20")
    if _quotient(max(lengths), min(lengths)) > 1024:
        raise ValueError("Element length ratio must not exceed 1024")
    if _quotient(max(moments), min(moments)) > 1e12:
        raise ValueError("Second moment ratio must not exceed 1e12")
    hs = tuple(_quotient(length, L) for length in lengths)
    zs = tuple(_quotient(x, L) if x else 0.0 for x in nodes)
    rhos = tuple(_quotient(value, moments[0]) for value in moments)
    rigidity = _product(E, moments[0])
    n = len(lengths)
    elements = tuple((2*i, 2*i+1, 2*i+2, 2*i+3) for i in range(n))
    if P == q == qr == qt == M == 0:
        zeros = (0.0,) * (n + 1)
        return VariableBeamSolution(
            L, E, rigidity, c, 0.0, n, elements, (0.0,) * (2*n+2),
            nodes, zeros, zeros, moments, 0.0, 0.0, 0.0)

    qL = _product(q, L) if q else 0.0
    ramp_force = _product(0.5, _sum((qr, qt)), L) if qr or qt else 0.0
    S = _normal(max(P, qL, ramp_force, _quotient(M, L) if M else 0.0))
    scale = _quotient(_product(S, L, L, L), rigidity)
    rotation_scale = _quotient(scale, L)
    _quotient(rotation_scale, L)
    SL = _product(S, L)
    pbar = _quotient(P, S) if P else 0.0
    mbar = _quotient(M, SL) if M else 0.0
    qbar, qrbar, qtbar = (
        _quotient(_product(load, L), S) if load else 0.0
        for load in (q, qr, qt))
    gauss = ((0.5 * (1 - math.sqrt(3/5)), 5/9),
             (0.5, 8/9), (0.5 * (1 + math.sqrt(3/5)), 5/9))
    K = np.zeros((2*n+2, 2*n+2))
    f = np.zeros(2*n+2)
    try:
        with np.errstate(over="raise", under="raise", invalid="raise", divide="raise"):
            for i, (dofs, h) in enumerate(zip(elements, hs)):
                ke, fe = np.zeros((4, 4)), np.zeros(4)
                for t, weight in gauss:
                    N, _, B = _shapes(t, h)
                    rho = _sum((_multiply(1-t, rhos[i]),
                                _multiply(t, rhos[i+1])))
                    z = _sum((zs[i], _multiply(h, t)))
                    load = _sum((qbar, _multiply(qrbar, 1-z),
                                 _multiply(qtbar, z)))
                    factor = _product(h, 0.5, weight)
                    ke += _product(factor, rho) * np.outer(B, B)
                    if load:
                        fe += _product(factor, load) * np.asarray(N)
                K[np.ix_(dofs, dofs)] += ke
                f[list(dofs)] += fe
            f[-2] += pbar
            f[-1] += mbar
            _check_array(K)
            _check_array(f)
            Kff, ff = K[2:, 2:], f[2:]
            u = np.zeros_like(f)
            u[2:] = np.linalg.solve(Kff, ff)
            _check_array(u)
            reaction = K @ u - f
            error = Kff @ u[2:] - ff
            _check_array(reaction)
            _check_array(error)
            max_k = float(np.max(np.abs(Kff)))
            max_u = float(np.max(np.abs(u[2:])))
            max_f = float(np.max(np.abs(ff)))
            numerator = float(np.max(np.abs(error)))
            denominator = _sum((_multiply(max_k, max_u), max_f))
            residual = _quotient(numerator, _normal(denominator)) if numerator else 0.0
    except np.linalg.LinAlgError as exc:
        raise ValueError("FEM linear solve failed") from exc
    except (FloatingPointError, OverflowError) as exc:
        raise ValueError("FEM arithmetic exceeds finite-normal support") from exc
    displacements = tuple(_scaled(v, scale) for v in u[::2])
    rotations = tuple(_scaled(v, rotation_scale) for v in u[1::2])
    return VariableBeamSolution(
        L, E, rigidity, c, scale, n, elements, tuple(map(float, u)), nodes,
        displacements, rotations, moments, _scaled(reaction[0], S),
        _scaled(reaction[1], SL), residual)


def evaluate_variable_solution(sol: VariableBeamSolution, element_index: int,
                               local_coordinate: float) -> BeamPoint:
    if type(element_index) is not int or not 0 <= element_index < sol.n:
        raise ValueError("element_index must be a built-in int in range")
    t = _number(local_coordinate, "local_coordinate", False)
    if t > 1:
        raise ValueError("local_coordinate must be in [0, 1]")
    left, right = sol.nodes[element_index:element_index+2]
    length = _normal(right - left)
    x = _sum((left, _multiply(t, length)))
    if sol.scale == 0:
        return BeamPoint(x, 0.0, 0.0, 0.0, 0.0)
    h = _quotient(length, sol.L)
    N, D, B = _shapes(t, h)
    values = tuple(sol.ndof[dof] for dof in sol.elements[element_index])

    def interpolate(coefficients):
        return _sum(_multiply(a, b) for a, b in zip(coefficients, values))

    rotation_scale = _quotient(sol.scale, sol.L)
    curvature_scale = _quotient(rotation_scale, sol.L)
    w = _scaled(interpolate(N), sol.scale)
    rotation = _scaled(interpolate(D), rotation_scale)
    curvature = _scaled(interpolate(B), curvature_scale)
    stress = _scaled(curvature, _product(sol.E, sol.c)) if curvature else 0.0
    return BeamPoint(x, w, rotation, curvature, stress)
