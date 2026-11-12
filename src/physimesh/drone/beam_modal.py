"""Bounded research-grade uniform cantilever modes; physical validation unestablished."""

import math
import sys

import numpy as np
from scipy import linalg

_EPS = sys.float_info.epsilon
_MIN = sys.float_info.min
_LIMITS = {
    "contract_version": "uniform-cantilever-modal-v1",
    "elements_min": 2,
    "elements_max": 64,
    "modes_min": 1,
    "modes_max": 6,
    "modes_free_dof_cap": True,
    "scalar_policy": "builtin-int-or-float-positive-normal-binary64",
    "eps_condition_mass_max": 1e-8,
    "eps_condition_whitened_max": 1e-4,
    "numerical_qualification": "NOT_ESTABLISHED",
    "mesh_accuracy": "NOT_ESTABLISHED",
    "model_scope": "uniform-undamped-Euler-Bernoulli-cantilever",
}


class _Refusal(Exception):
    def __init__(self, code, message, field=None):
        super().__init__(message)
        self.code = code
        self.field = field
        self.message = message


def _require(ok, code, message):
    if not ok:
        raise _Refusal(code, message)


def _scalar(value, field):
    if type(value) not in (int, float):
        raise _Refusal("INVALID_TYPE", "Expected an exact builtin int or float.", field)
    try:
        result = float(value)
    except OverflowError:
        raise _Refusal("NONFINITE_OR_UNDERFLOW", "Scalar conversion overflow.", field) from None
    if not math.isfinite(result):
        raise _Refusal("NONFINITE_OR_UNDERFLOW", "Scalar must be finite.", field)
    if result <= 0:
        raise _Refusal("INVALID_VALUE", "Scalar must be positive.", field)
    if result < _MIN:
        raise _Refusal("NONFINITE_OR_UNDERFLOW", "Scalar must be normal binary64.", field)
    return result


def _count(value, field, maximum):
    if type(value) is not int:
        raise _Refusal("INVALID_TYPE", "Expected an exact builtin int.", field)
    minimum = 2 if field == "elements" else 1
    if not minimum <= value <= maximum:
        raise _Refusal("UNSUPPORTED_RANGE", "Count is outside supported bounds.", field)
    return value


def _normal(value):
    _require(math.isfinite(value) and value >= _MIN,
             "NONFINITE_OR_UNDERFLOW", "Required scale or frequency is not finite normal.")
    return value


def _frequency_scale(e, inertia, mu, length):
    em, ee = math.frexp(e)
    im, ie = math.frexp(inertia)
    mm, me = math.frexp(mu)
    lm, le = math.frexp(length)
    exponent, remainder = divmod(ee + ie - me - 4 * le, 2)
    try:
        return _normal(math.ldexp(math.sqrt(math.ldexp(
            em * im / (mm * lm**4), remainder)), exponent))
    except OverflowError:
        raise _Refusal("NONFINITE_OR_UNDERFLOW", "Physical frequency scale overflow.") from None


def _assemble(elements):
    h = 1.0 / elements
    k = np.array([[12, 6*h, -12, 6*h], [6*h, 4*h*h, -6*h, 2*h*h],
                  [-12, -6*h, 12, -6*h], [6*h, 2*h*h, -6*h, 4*h*h]]) / h**3
    m = np.array([[156, 22*h, 54, -13*h], [22*h, 4*h*h, 13*h, -3*h*h],
                  [54, 13*h, 156, -22*h], [-13*h, -3*h*h, -22*h, 4*h*h]]) * (h/420)
    size = 2 * (elements + 1)
    stiffness = np.zeros((size, size))
    mass = np.zeros((size, size))
    for i in range(elements):
        block = slice(2*i, 2*i+4)
        stiffness[block, block] += k
        mass[block, block] += m
    return stiffness[2:, 2:], mass[2:, 2:]


def _symmetric(matrix, q, bound):
    _require(matrix.shape == (q, q) and np.isfinite(matrix).all(),
             "NONFINITE_OR_UNDERFLOW", "Invalid matrix shape or nonfinite assembly.")
    norm = float(linalg.norm(matrix, 2))
    _require(math.isfinite(norm) and norm > 0,
             "DIAGNOSTIC_FAILURE", "Matrix norm is invalid.")
    defect = float(linalg.norm(matrix - matrix.T, 2) / norm)
    _require(math.isfinite(defect) and defect <= bound,
             "DIAGNOSTIC_FAILURE", "Matrix symmetry budget exceeded.")
    return (matrix + matrix.T) * 0.5, norm, defect


def _eigenpairs(matrix, q):
    values, vectors = linalg.eigh(matrix, driver="evd")
    _require(values.shape == (q,) and vectors.shape == (q, q),
             "SOLVER_FAILURE", "Eigensolver returned invalid shapes.")
    _require(np.isfinite(values).all() and np.isfinite(vectors).all(),
             "SOLVER_FAILURE", "Eigensolver returned nonfinite values.")
    order = np.argsort(values)
    return values[order], vectors[:, order]


def _compute(inputs):
    n, count = inputs["elements"], inputs["modes"]
    q = 2 * n
    k, m = _assemble(n)
    scale = _frequency_scale(inputs["E_pa"], inputs["I_m4"],
                             inputs["mass_per_length_kg_m"], inputs["length_m"])
    symmetry_bound = 32 * q * _EPS
    k, kn, ks = _symmetric(k, q, symmetry_bound)
    m, mn, ms = _symmetric(m, q, symmetry_bound)
    try:
        linalg.cholesky(k, lower=True)
        c = linalg.cholesky(m, lower=True)
    except linalg.LinAlgError:
        raise _Refusal("NOT_SPD", "Matrix Cholesky factorization failed.") from None
    _require(c.shape == (q, q) and np.isfinite(c).all() and np.all(np.diag(c) > 0),
             "NOT_SPD", "Mass factor is invalid.")
    left = linalg.solve_triangular(c, k, lower=True)
    a = linalg.solve_triangular(c, left.T, lower=True).T
    a, an, asym = _symmetric(a, q, symmetry_bound)
    mv, _ = _eigenpairs(m, q)
    av, yall = _eigenpairs(a, q)
    _require(mv[0] > 0 and av[0] > 0, "ILL_CONDITIONED",
             "Nonpositive spectral condition estimate.")
    cm, ca = float(mv[-1] / mv[0]), float(av[-1] / av[0])
    _require(math.isfinite(cm) and math.isfinite(ca)
             and _EPS * cm <= 1e-8 and _EPS * ca <= 1e-4,
             "ILL_CONDITIONED", "Spectral condition budget exceeded.")
    delta = 128 * q * _EPS * an
    gaps = np.diff(av)[:min(count, q-1)]
    gap = float(np.min(gaps))
    _require(av[0] > delta and gap > 2 * delta,
             "UNRESOLVED_SPECTRUM", "Selected spectrum is unresolved.")
    values, y = av[:count], yall[:, :count]
    u = linalg.solve_triangular(c.T, y, lower=False)
    _require(u.shape == (q, count) and np.isfinite(u).all(),
             "DIAGNOSTIC_FAILURE", "Recovered vectors are invalid.")
    rb = 128 * q * _EPS
    gb = min(1e-6, 256 * q * _EPS * math.sqrt(cm))
    mb = min(1e-6, 256 * q * _EPS * cm)
    rw, rg = [], []
    for j, value in enumerate(values):
        yn, un = float(linalg.norm(y[:, j])), float(linalg.norm(u[:, j]))
        wd, gd = (an + float(value)) * yn, (kn + float(value) * mn) * un
        _require(math.isfinite(wd) and math.isfinite(gd) and wd > 0 and gd > 0,
                 "DIAGNOSTIC_FAILURE", "Residual denominator is invalid.")
        rw.append(float(linalg.norm(a @ y[:, j] - value * y[:, j]) / wd))
        rg.append(float(linalg.norm(k @ u[:, j] - value * (m @ u[:, j])) / gd))
    ow = float(linalg.norm(y.T @ y - np.eye(count), 2))
    om = float(linalg.norm(u.T @ m @ u - np.eye(count), 2))
    _require(all(math.isfinite(v) for v in [*rw, *rg, ow, om])
             and max(rw) <= rb and max(rg) <= gb and ow <= rb and om <= mb,
             "DIAGNOSTIC_FAILURE", "Residual or orthogonality budget exceeded.")
    results, tips = [], []
    for j, value in enumerate(values):
        full = np.concatenate((np.zeros(2), u[:, j]))
        tip = float(full[-2])
        relative = abs(tip) / float(linalg.norm(full))
        _require(math.isfinite(relative) and relative > rb,
                 "TIP_NORMALIZATION_FAILURE", "Tip displacement is unresolved.")
        with np.errstate(over="ignore", invalid="ignore", divide="ignore", under="ignore"):
            shape = full / tip
        _require(np.isfinite(shape).all()
                 and not np.any((full != 0) & (shape == 0))
                 and not np.any((shape != 0) & (np.abs(shape) < _MIN)),
                 "TIP_NORMALIZATION_FAILURE", "Normalized shape is not representable.")
        omega = _normal(scale * math.sqrt(float(value)))
        hz = _normal(omega / (2 * math.pi))
        tips.append(relative)
        results.append({"mode_index": j+1, "eigenvalue_dimensionless": float(value),
                        "omega_rad_s": omega, "frequency_hz": hz,
                        "xi": [i/n for i in range(n+1)],
                        "normalized_deflection": shape[::2].tolist(),
                        "normalized_deflection_derivative_xi": shape[1::2].tolist()})
    diagnostics = {
        "frequency_scale_rad_s": scale, "free_dofs": q,
        "condition_mass_2": cm, "condition_whitened_2": ca,
        "symmetry_relative": {"stiffness": ks, "mass": ms, "whitened": asym},
        "residual_whitened": rw, "residual_generalized": rg,
        "orthogonality_whitened_2": ow, "orthogonality_mass_2": om,
        "uncertainty_radius": delta, "minimum_selected_gap": gap,
        "tip_relative_magnitudes": tips,
        "thresholds": {"symmetry_relative": symmetry_bound, "residual_whitened": rb,
                       "residual_generalized": gb, "orthogonality_whitened_2": rb,
                       "orthogonality_mass_2": mb, "tip_relative_min": rb,
                       "eigenvalue_min": delta, "gap_min": 2*delta},
    }
    return {"status": "SUCCESS", "inputs": inputs, "modes": results,
            "diagnostics": diagnostics, "limits": dict(_LIMITS),
            "physical_validation": "NOT_ESTABLISHED"}


def solve_cantilever_modes(*, length_m, E_pa, I_m4, mass_per_length_kg_m, elements=8, modes=3):
    """Return finite builtin JSON data or a closed refusal, without physical claims.

    Supports 2..64 elements and 1..min(6, 2*elements) modes. Numerical gates
    measure backward consistency; they imply no frequency or mesh error bound.
    """
    try:
        inputs = {name: _scalar(value, name) for name, value in (
            ("length_m", length_m), ("E_pa", E_pa), ("I_m4", I_m4),
            ("mass_per_length_kg_m", mass_per_length_kg_m))}
        inputs["elements"] = _count(elements, "elements", 64)
        inputs["modes"] = _count(modes, "modes", min(6, 2*elements))
        with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
            return _compute(inputs)
    except _Refusal as exc:
        refusal = {"code": exc.code, "field": exc.field, "message": exc.message}
    except (linalg.LinAlgError, ValueError, FloatingPointError, OverflowError, ZeroDivisionError):
        refusal = {"code": "SOLVER_FAILURE", "field": None,
                   "message": "Numerical computation failed."}
    return {"status": "REFUSED", "refusal": refusal, "limits": dict(_LIMITS),
            "physical_validation": "NOT_ESTABLISHED"}
