"""End-to-end checks of the bounded numerical candidate."""

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import optimize

SPEC = importlib.util.spec_from_file_location(
    "beam_modal_candidate", Path(__file__).parents[2] / "src/physimesh/drone/beam_modal.py"
)
assert SPEC is not None and SPEC.loader is not None
bm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bm)

BASE = {"length_m": 1.0, "E_pa": 1.0, "I_m4": 1.0, "mass_per_length_kg_m": 1.0}
SUCCESS = {"status", "inputs", "modes", "diagnostics", "limits", "physical_validation"}
REFUSED = {"status", "refusal", "limits", "physical_validation"}
LIMITS = {"contract_version", "elements_min", "elements_max", "modes_min", "modes_max",
          "modes_free_dof_cap", "scalar_policy", "eps_condition_mass_max",
          "eps_condition_whitened_max", "numerical_qualification", "mesh_accuracy", "model_scope"}


def solve(**kwargs):
    return bm.solve_cantilever_modes(**(BASE | kwargs))


def envelope(result):
    assert set(result) == (SUCCESS if result["status"] == "SUCCESS" else REFUSED)
    assert set(result["limits"]) == LIMITS
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["limits"]["numerical_qualification"] == "NOT_ESTABLISHED"
    assert result["limits"]["mesh_accuracy"] == "NOT_ESTABLISHED"
    assert result["limits"] == solve(length_m=0)["limits"]
    json.dumps(result, allow_nan=False)

    def builtin(value):
        assert type(value) in (dict, list, str, float, int, bool, type(None))
        if isinstance(value, dict):
            for key, item in value.items():
                assert type(key) is str
                builtin(item)
        elif isinstance(value, list):
            for item in value:
                builtin(item)
        elif type(value) is float:
            assert math.isfinite(value)
    builtin(result)
    if result["status"] == "REFUSED":
        assert set(result["refusal"]) == {"code", "field", "message"}
    else:
        assert set(result["inputs"]) == {*BASE, "elements", "modes"}
        diagnostics = result["diagnostics"]
        assert set(diagnostics) == {
            "frequency_scale_rad_s", "free_dofs", "condition_mass_2", "condition_whitened_2",
            "symmetry_relative", "residual_whitened", "residual_generalized",
            "orthogonality_whitened_2", "orthogonality_mass_2", "uncertainty_radius",
            "minimum_selected_gap", "tip_relative_magnitudes", "thresholds",
        }
        assert set(diagnostics["symmetry_relative"]) == {"stiffness", "mass", "whitened"}
        assert set(diagnostics["thresholds"]) == {
            "symmetry_relative", "residual_whitened", "residual_generalized",
            "orthogonality_whitened_2", "orthogonality_mass_2", "tip_relative_min",
            "eigenvalue_min", "gap_min",
        }
        for mode in result["modes"]:
            assert set(mode) == {"mode_index", "eigenvalue_dimensionless", "omega_rad_s", "frequency_hz",
                                 "xi", "normalized_deflection", "normalized_deflection_derivative_xi"}


class IntSubclass(int):
    pass


class FloatSubclass(float):
    pass


@pytest.mark.parametrize("field", list(BASE))
@pytest.mark.parametrize(("value", "code"), [
    (True, "INVALID_TYPE"), (None, "INVALID_TYPE"), ("1", "INVALID_TYPE"),
    (np.float64(1), "INVALID_TYPE"), (IntSubclass(1), "INVALID_TYPE"),
    (FloatSubclass(1), "INVALID_TYPE"), (-1, "INVALID_VALUE"),
    (0, "INVALID_VALUE"), (-0.0, "INVALID_VALUE"),
    (float("nan"), "NONFINITE_OR_UNDERFLOW"),
    (float("inf"), "NONFINITE_OR_UNDERFLOW"),
    (math.ulp(0.0), "NONFINITE_OR_UNDERFLOW"),
    (math.nextafter(sys.float_info.min, 0), "NONFINITE_OR_UNDERFLOW"),
    (10**10000, "NONFINITE_OR_UNDERFLOW"),
    (-(10**10000), "NONFINITE_OR_UNDERFLOW"),
], ids=lambda v: type(v).__name__)
def test_scalar_refusals(field, value, code):
    result = solve(**{field: value})
    envelope(result)
    assert result["refusal"]["code"] == code
    assert result["refusal"]["field"] == field


@pytest.mark.parametrize(("field", "value", "code"), [
    ("elements", True, "INVALID_TYPE"), ("elements", 2.0, "INVALID_TYPE"),
    ("elements", np.int64(8), "INVALID_TYPE"), ("elements", 1, "UNSUPPORTED_RANGE"),
    ("elements", 65, "UNSUPPORTED_RANGE"), ("elements", 10**10000, "UNSUPPORTED_RANGE"),
    ("modes", False, "INVALID_TYPE"), ("modes", 1.0, "INVALID_TYPE"),
    ("modes", 0, "UNSUPPORTED_RANGE"), ("modes", -1, "UNSUPPORTED_RANGE"),
    ("modes", 5, "UNSUPPORTED_RANGE"), ("modes", 10**10000, "UNSUPPORTED_RANGE"),
], ids=lambda v: type(v).__name__)
def test_count_refusals(field, value, code):
    result = solve(**({"elements": 2} | {field: value}))
    envelope(result)
    assert result["refusal"]["code"] == code
    assert result["refusal"]["field"] == field


@pytest.mark.parametrize("n", range(2, 65))
@pytest.mark.parametrize("maximum", [False, True])
def test_all_meshes(n, maximum):
    count = min(6, 2*n) if maximum else 1
    result = solve(elements=n, modes=count)
    envelope(result)
    assert result["status"] == "SUCCESS", result
    d = result["diagnostics"]
    t = d["thresholds"]
    assert d["free_dofs"] == 2*n
    assert max(d["residual_whitened"]) <= t["residual_whitened"]
    assert max(d["residual_generalized"]) <= t["residual_generalized"]
    for name in ("orthogonality_whitened_2", "orthogonality_mass_2"):
        assert d[name] <= t[name]
    assert max(d["symmetry_relative"].values()) <= t["symmetry_relative"]
    assert d["minimum_selected_gap"] > t["gap_min"]
    assert min(d["tip_relative_magnitudes"]) > t["tip_relative_min"]
    for mode in result["modes"]:
        assert mode["normalized_deflection"][0] == 0
        assert mode["normalized_deflection"][-1] == 1
        assert mode["normalized_deflection_derivative_xi"][0] == 0
        assert len(mode["xi"]) == n+1
        assert mode["omega_rad_s"] == pytest.approx(2*math.pi*mode["frequency_hz"])
        assert mode["eigenvalue_dimensionless"] > t["eigenvalue_min"]


@pytest.mark.parametrize(("changes", "ratio"), [
    ({"length_m": 2}, 0.25), ({"E_pa": 4}, 2),
    ({"I_m4": 4}, 2), ({"mass_per_length_kg_m": 4}, 0.5),
    ({"E_pa": 2.0**1000, "I_m4": 2.0**1000,
      "mass_per_length_kg_m": 2.0**1000, "length_m": 2.0**250}, 1),
])
def test_scaling(changes, ratio):
    reference, result = solve(), solve(**changes)
    envelope(result)
    assert result["status"] == "SUCCESS"
    for before, after in zip(reference["modes"], result["modes"], strict=True):
        assert after["frequency_hz"] == pytest.approx(before["frequency_hz"]*ratio)
        assert after["normalized_deflection"] == before["normalized_deflection"]


@pytest.mark.parametrize("changes", [
    {"E_pa": sys.float_info.max, "I_m4": sys.float_info.max},
    {"E_pa": sys.float_info.min, "I_m4": sys.float_info.min},
    {"length_m": sys.float_info.min}, {"length_m": sys.float_info.max},
])
def test_extreme_scale(changes):
    result = solve(**changes)
    envelope(result)
    assert result["refusal"]["code"] == "NONFINITE_OR_UNDERFLOW"


@pytest.mark.parametrize("operation", ["cholesky", "eigh", "solve_triangular"])
def test_numerical_exception(monkeypatch, operation):
    def fail(*args, **kwargs):
        raise bm.linalg.LinAlgError("private internals")
    monkeypatch.setattr(bm.linalg, operation, fail)
    result = solve()
    envelope(result)
    assert result["status"] == "REFUSED"
    assert "private" not in result["refusal"]["message"]


@pytest.mark.parametrize("fault", ["shape", "nan", "negative", "cluster", "residual", "zero_tip", "rank"])
def test_bad_solver_outputs(monkeypatch, fault):
    original = bm.linalg.eigh
    calls = 0

    def fake(*args, **kwargs):
        nonlocal calls
        calls += 1
        values, vectors = original(*args, **kwargs)
        if calls == 2:
            if fault == "shape":
                return values[:-1], vectors
            if fault == "nan":
                values[0] = np.nan
            if fault == "negative":
                values[0] = -1
            if fault == "cluster":
                values[1] = values[0]
            if fault == "residual":
                vectors[:, 0] = np.arange(len(values))
            if fault == "rank":
                vectors[:, 1] = vectors[:, 0]
        return values, vectors

    monkeypatch.setattr(bm.linalg, "eigh", fake)
    if fault == "zero_tip":
        # A dynamically decoupled tip has exact eigenvectors with zero tip displacement.
        def diagonal_assembly(n):
            return np.diag(np.arange(1, 2*n+1, dtype=float)), np.eye(2*n)
        monkeypatch.setattr(bm, "_assemble", diagonal_assembly)
    result = solve()
    envelope(result)
    assert result["status"] == "REFUSED"
    if fault == "zero_tip":
        assert result["refusal"]["code"] == "TIP_NORMALIZATION_FAILURE"


def test_analytical_convergence():
    # First root of cosh(beta)*cos(beta)+1=0; comparison is a test, not an accuracy promise.
    exact = optimize.brentq(lambda beta: math.cosh(beta)*math.cos(beta)+1, 1.8, 1.9)**2
    errors = []
    for n in (2, 4, 8, 16, 32, 64):
        result = solve(elements=n, modes=1)
        errors.append(abs(result["modes"][0]["omega_rad_s"] / exact - 1))
    assert errors[0] < 1e-3
    assert max(errors[-2:]) < 1e-6
    assert errors[3] < errors[0]


@pytest.mark.parametrize(("n", "count"), [(n, c) for n in range(2, 65) for c in range(1, min(6, 2*n)+1)])
def test_every_valid_count_pair(n, count):
    result = solve(elements=n, modes=count)
    envelope(result)
    assert result["status"] == "SUCCESS", result
    assert len(result["modes"]) == count


def test_first_refusal_order():
    fields = [*BASE, "elements", "modes"]
    for i, field in enumerate(fields):
        invalid = dict.fromkeys(fields[i:], None)
        result = solve(**invalid)
        envelope(result)
        assert result["refusal"]["field"] == field
        assert result["refusal"]["code"] == "INVALID_TYPE"


def test_metadata_freshness():
    first, refusal = solve(), solve(length_m=0)
    original = dict(first["limits"])
    first["limits"]["elements_max"] = 1
    refusal["limits"]["numerical_qualification"] = "changed"
    first["diagnostics"]["thresholds"]["gap_min"] = -1
    first["modes"][0]["xi"][0] = 7
    for result in (solve(), solve(length_m=0)):
        envelope(result)
        assert result["limits"] == original
    fresh = solve()
    assert fresh["diagnostics"]["thresholds"]["gap_min"] > 0
    assert fresh["modes"][0]["xi"][0] == 0


@pytest.mark.parametrize(("fault", "expected"), [
    ("zero", "DIAGNOSTIC_FAILURE"), ("rank", "NOT_SPD"),
    ("indefinite", "NOT_SPD"), ("nonfinite", "NONFINITE_OR_UNDERFLOW"),
    ("asymmetric", "DIAGNOSTIC_FAILURE"), ("mass_condition", "ILL_CONDITIONED"),
    ("whitened_condition", "ILL_CONDITIONED"),
    ("radius", "UNRESOLVED_SPECTRUM"), ("omitted_gap", "UNRESOLVED_SPECTRUM"),
])
def test_assembly_gates(monkeypatch, fault, expected):
    original = bm._assemble

    def assembly(n):
        k, m = original(n)
        if fault == "zero":
            k[:] = 0
        elif fault == "rank":
            k[:] = 1
        elif fault == "indefinite":
            k[0, 0] = -1
        elif fault == "nonfinite":
            m[0, 0] = np.inf
        elif fault == "asymmetric":
            k[0, 1] += 100
        else:
            k, m = np.eye(2*n), np.eye(2*n)
            if fault == "mass_condition":
                m[0, 0] = 1e-10
            elif fault == "whitened_condition":
                k[-1, -1] = 1e12
            elif fault == "radius":
                k[-1, -1] = 1e11
            elif fault == "omitted_gap":
                k = np.diag(np.array([1., 2., 3., 3., *range(5, 2*n+1)]))
        return k, m

    monkeypatch.setattr(bm, "_assemble", assembly)
    result = solve(modes=3)
    envelope(result)
    assert result["refusal"]["code"] == expected


@pytest.mark.parametrize(
    "fault", ["norm", "whitened_symmetry", "mass_orthogonality", "whitened_orthogonality"]
)
def test_diagnostic_budgets(monkeypatch, fault):
    original = bm.linalg.norm
    calls = 0

    def norm(value, *args, **kwargs):
        nonlocal calls
        calls += 1
        # First six calls check K, M, A norms and symmetry defects.
        if fault == "norm" and calls == 1:
            return np.inf
        if fault == "whitened_symmetry" and calls == 6:
            return 1e20
        # With modes=3, orthogonality matrices are the only 3x3 norm arguments.
        if np.shape(value) == (3, 3):
            if fault == "mass_orthogonality" and calls == 20:
                return 1
            if fault == "whitened_orthogonality" and calls == 19:
                return 1
        return original(value, *args, **kwargs)

    monkeypatch.setattr(bm.linalg, "norm", norm)
    result = solve()
    envelope(result)
    assert result["refusal"]["code"] == "DIAGNOSTIC_FAILURE"


@pytest.mark.parametrize(("fault", "expected_status"), [
    ("subnormal", "REFUSED"), ("lost_to_zero", "REFUSED"),
    ("overflow", "REFUSED"), ("nonfinite", "REFUSED"),
    ("structural_zeros", "SUCCESS"), ("normal", "SUCCESS"),
])
def test_normalization_snapshot(monkeypatch, fault, expected_status):
    # Synthetic snapshot after genuine earlier public gates, not a reachable-input claim.
    # Only root insertion is replaced: diagnostics still run on genuine nominal eigenpairs.
    original_concatenate = bm.np.concatenate
    original_norm = bm.linalg.norm
    snapshots = []

    def concatenate(arrays, *args, **kwargs):
        full = original_concatenate(arrays, *args, **kwargs)
        if len(full) == 18:
            full = np.zeros(18)
            full[-2] = 2.
            if fault == "subnormal":
                full[2] = 2*math.ulp(0.)
            elif fault == "lost_to_zero":
                full[2] = math.ulp(0.)
            elif fault == "overflow":
                full[-2], full[2] = 0.5, sys.float_info.max
            elif fault == "nonfinite":
                full[2] = np.inf
            elif fault == "normal":
                full[2] = 0.5
            snapshots.append(full.copy())
        return full

    def norm(value, *args, **kwargs):
        # Allow artificial overflow/nonfinite snapshots to reach the division guard.
        # Real earlier diagnostics and finite representability cases use actual norms.
        if np.shape(value) == (18,) and fault in ("overflow", "nonfinite"):
            return 1.
        return original_norm(value, *args, **kwargs)

    monkeypatch.setattr(bm.np, "concatenate", concatenate)
    monkeypatch.setattr(bm.linalg, "norm", norm)
    result = solve()
    envelope(result)
    assert snapshots  # Normalization was reached after all diagnostic gates.
    full = snapshots[0]
    with np.errstate(under="ignore", over="ignore", invalid="ignore"):
        computed = full/full[-2]
    if fault == "subnormal":
        assert full[2] != 0 and 0 < abs(computed[2]) < sys.float_info.min
    elif fault == "lost_to_zero":
        assert full[2] != 0 and computed[2] == 0
    elif fault in ("overflow", "nonfinite"):
        assert not np.isfinite(computed).all()
    assert result["status"] == expected_status
    if expected_status == "REFUSED":
        assert result["refusal"]["code"] == "TIP_NORMALIZATION_FAILURE"
    else:
        assert result["modes"][0]["normalized_deflection"][1] == (0.25 if fault == "normal" else 0)


def gauss_matrices(n):
    """Independently integrate polynomial shape/curvature products; no module helpers."""
    h = 1/n
    nodes, weights = np.polynomial.legendre.leggauss(4)
    stiffness, mass = np.zeros((2*n+2, 2*n+2)), np.zeros((2*n+2, 2*n+2))
    for element in range(n):
        local_k, local_m = np.zeros((4, 4)), np.zeros((4, 4))
        for node, weight in zip(nodes, weights, strict=True):
            t = (node+1)/2
            shape = np.array([1-3*t*t+2*t**3, h*(t-2*t*t+t**3),
                              3*t*t-2*t**3, h*(-t*t+t**3)])
            curvature = np.array([-6+12*t, h*(-4+6*t), 6-12*t, h*(-2+6*t)])/h**2
            local_m += weight*h/2*np.outer(shape, shape)
            local_k += weight*h/2*np.outer(curvature, curvature)
        indices = slice(2*element, 2*element+4)
        stiffness[indices, indices] += local_k
        mass[indices, indices] += local_m
    return stiffness[2:, 2:], mass[2:, 2:]


@pytest.mark.parametrize("n", [2, 4, 8, 16])
def test_independent_gauss_generalized_reference(n):
    k, m = gauss_matrices(n)
    values, vectors = bm.linalg.eigh(k, m, driver="gvd")
    result = solve(elements=n, modes=min(6, 2*n))
    envelope(result)
    for i, mode in enumerate(result["modes"]):
        expected = np.r_[0., 0., vectors[:, i]/vectors[-2, i]]
        assert mode["omega_rad_s"] == pytest.approx(math.sqrt(values[i]), rel=1e-7)
        np.testing.assert_allclose(mode["normalized_deflection"], expected[::2], rtol=1e-7, atol=1e-8)
        np.testing.assert_allclose(mode["normalized_deflection_derivative_xi"], expected[1::2],
                                   rtol=1e-7, atol=1e-7)
        # Independently reconstructed vectors satisfy the assembled generalized problem.
        u = np.empty(2*n)
        u[::2] = mode["normalized_deflection"][1:]
        u[1::2] = mode["normalized_deflection_derivative_xi"][1:]
        residual = np.linalg.norm(k@u-mode["eigenvalue_dimensionless"]*(m@u))
        denominator = (np.linalg.norm(k, 2)+mode["eigenvalue_dimensionless"]*np.linalg.norm(m, 2))
        assert residual/(denominator*np.linalg.norm(u)) < 1e-10


# Supplied rational-Hermite 80-digit DISCRETE RQI record, not a physical or certified reference.
_REFERENCE = json.loads(Path(__file__).with_name("beam_modal_discrete_reference.json").read_text())


@pytest.mark.parametrize("record", _REFERENCE["records"],
                         ids=lambda r: f"n{r['elements']}-mode{r['mode']}")
def test_high_precision_discrete_record(record):
    result = solve(elements=record["elements"], modes=record["mode"])
    envelope(result)
    mode = result["modes"][-1]
    # Conservative finite regression tolerance; no universal frequency accuracy guarantee.
    assert mode["omega_rad_s"] == pytest.approx(float(record["omega"]), rel=1e-7)
    vector = np.array(record["vector"], dtype=float)
    vector /= vector[-2]
    np.testing.assert_allclose(mode["normalized_deflection"][1:], vector[::2], rtol=1e-6, atol=1e-7)
    np.testing.assert_allclose(mode["normalized_deflection_derivative_xi"][1:], vector[1::2],
                               rtol=1e-6, atol=1e-7)
