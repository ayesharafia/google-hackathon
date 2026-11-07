import json
import math

import pytest

from physimesh.drone.beam_fem_benchmark import benchmark_refinement

BASE = {
    "length_m": 2,
    "E_pa": 70e9,
    "I_m4": 1e-6,
    "outer_fibre_m": 0.01,
    "tip_force_n": 10,
    "uniform_load_n_m": 100,
}
ELEMENTS = (1, 2, 4, 8, 16)
NUMERIC_KEYS = (
    "numeric_rms_displacement_error_m",
    "numeric_rms_nominal_stress_error_pa",
    "tip_deflection_m",
    "root_force_n",
    "root_moment_nm",
    "force_balance_residual_n",
    "moment_balance_residual_nm",
    "linear_residual",
)


def run(**overrides):
    result = benchmark_refinement(**(BASE | overrides))
    assert result["status"] == "BENCHMARK_COMPUTED"
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    json.dumps(result, allow_nan=False)
    rows = result["rows"]
    assert len(rows) == len(ELEMENTS)
    for row in rows:
        for key in NUMERIC_KEYS:
            assert isinstance(row[key], (int, float))
            assert not isinstance(row[key], bool)
            assert math.isfinite(row[key])
        for key in ("observed_displacement_order", "observed_stress_order"):
            assert key in row
            assert row[key] is None or (
                isinstance(row[key], (int, float))
                and not isinstance(row[key], bool)
                and math.isfinite(row[key])
            )
    return rows


def test_default_refinement_against_independent_closed_forms():
    L, E, second_moment_m4, c, P, q = (BASE[k] for k in BASE)
    tip = P * L**3 / (3 * E * second_moment_m4) + q * L**4 / (8 * E * second_moment_m4)
    for i, (n, row) in enumerate(zip(ELEMENTS, run())):
        h = L / n
        # Allow floating-point matrix-solve error and reference cancellation in
        # the fine-field RMS check independently of analytic expected orders.
        # This is numerical verification tolerance, not physical qualification.
        displacement_rel = 2e-5 if n >= 8 else 1e-8
        assert row["numeric_rms_displacement_error_m"] == pytest.approx(
            q * h**4 / (24 * E * second_moment_m4 * math.sqrt(630)),
            rel=displacement_rel,
            abs=0,
        )
        assert row["numeric_rms_nominal_stress_error_pa"] == pytest.approx(
            q * c * h**2 / (second_moment_m4 * math.sqrt(720)), rel=1e-8, abs=0
        )
        for key, order in (("observed_displacement_order", 4),
                           ("observed_stress_order", 2)):
            assert row[key] is None if i == 0 else (
                row[key] == pytest.approx(order, abs=1e-4, rel=0)
            )
        assert row["tip_deflection_m"] == pytest.approx(tip, rel=1e-8, abs=0)
        assert abs(row["root_force_n"]) == pytest.approx(P + q * L, rel=1e-8)
        assert abs(row["root_moment_nm"]) == pytest.approx(
            P * L + q * L**2 / 2, rel=1e-8
        )
        for key in NUMERIC_KEYS[-3:]:
            assert abs(row[key]) < 1e-7


def test_zero_load_has_zero_errors_and_no_orders():
    for row in run(tip_force_n=0, uniform_load_n_m=0):
        assert all(row[key] == 0 for key in NUMERIC_KEYS)
        assert row["observed_displacement_order"] is None
        assert row["observed_stress_order"] is None


def test_pure_tip_load_allows_roundoff_errors():
    for row in run(uniform_load_n_m=0):
        assert 0 <= row["numeric_rms_displacement_error_m"] < 1e-10
        assert 0 <= row["numeric_rms_nominal_stress_error_pa"] < 1e-2
        assert row["observed_displacement_order"] is None
        assert row["observed_stress_order"] is None


@pytest.mark.parametrize("key", tuple(BASE))
@pytest.mark.parametrize("bad", [True, "1", float("nan")])
def test_invalid_solver_inputs_are_refused(key, bad):
    with pytest.raises((TypeError, ValueError)):
        benchmark_refinement(**(BASE | {key: bad}))


@pytest.mark.parametrize("mesh", [[1, 2, 4, 8, 16], (1, 2, 2), (1, 3),
                                  (0,), (-1,), (2**31,), (), True])
def test_invalid_meshes_are_refused(mesh):
    with pytest.raises((TypeError, ValueError)):
        benchmark_refinement(**BASE, mesh_elements=mesh)
