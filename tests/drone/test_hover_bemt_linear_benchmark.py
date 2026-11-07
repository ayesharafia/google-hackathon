import json
import math
from dataclasses import asdict, is_dataclass

import pytest

from physimesh.drone.hover_bemt import solve_hover
from physimesh.drone.hover_bemt_benchmark import benchmark_refinement

INPUTS = {
    "radius_m": 1., "angular_speed_rad_s": 100., "density_kg_m3": 1.225,
    "blade_count": 2, "chord_m": .05, "lift_curve_slope_per_rad": 5.7,
    "profile_drag_coefficient": .01, "pitch_tip_rad": .08,
    "root_cutout_fraction": .2, "twist_law": "linear", "pitch_root_rad": .16,
}
ANNULI = (8, 16, 32, 64, 128)
FIELDS = {
    "CT": "thrust_coefficient",
    "CPi": "induced_power_coefficient",
    "CP0": "profile_power_coefficient",
    "CP": "shaft_power_coefficient",
    "thrust_N": "thrust_n",
    "power_W": "shaft_power_w",
    "torque_Nm": "shaft_torque_nm",
    "thrust_balance_coefficient": "thrust_balance_coefficient",
    "max_local_balance_coefficient": "max_local_balance_coefficient",
}
UNAVAILABLE = (
    "CT_absolute_error", "CPi_absolute_error", "CP0_absolute_error",
    "CT_observed_order", "CPi_observed_order", "profile_observed_order",
)
ROW_KEYS = {"annuli", *FIELDS, *UNAVAILABLE, "CT_change", "CP_change"}


def check_linear_benchmark(inputs):
    result = benchmark_refinement(**inputs, annuli_counts=ANNULI)
    assert isinstance(result, dict)
    assert result["status"] == "BENCHMARK_COMPUTED"
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["reference_kind"] == "mesh_change_only"
    # Linear twist must never inherit the hyperbolic exact reference or orders.
    assert result["reference"] == {"CT": None, "CPi": None, "CP0": None}
    json.dumps(result, allow_nan=False)
    rows = result["rows"]
    assert len(rows) == len(ANNULI)
    for index, (annuli, row) in enumerate(zip(ANNULI, rows)):
        assert ROW_KEYS <= row.keys()
        assert row["annuli"] == annuli
        assert all(row[key] is None for key in UNAVAILABLE)
        solution = solve_hover(**inputs, annuli=annuli)
        assert is_dataclass(solution)
        metadata = asdict(solution)
        assert metadata["physical_validation"] == "NOT_ESTABLISHED"
        json.dumps(metadata, allow_nan=False)
        for key, field in FIELDS.items():
            assert math.isfinite(row[key])
            assert row[key] == pytest.approx(getattr(solution, field))
        for coefficient in ("CT", "CP"):
            change = row[coefficient + "_change"]
            if index == 0:
                assert change is None
            else:
                assert math.isfinite(change) and change >= 0
                # Mesh changes are successive differences, not accuracy claims.
                assert change == abs(row[coefficient] - rows[index - 1][coefficient])
    return result


@pytest.mark.parametrize("cutout", [.2, .6])
def test_linear_refinement_matches_solver(cutout):
    # At .6 the root pitch still belongs to the active-span root, not the hub.
    check_linear_benchmark({**INPUTS, "root_cutout_fraction": cutout})


@pytest.mark.parametrize("root,tip", [(0., .08), (.16, 0.), (0., 0.)])
@pytest.mark.parametrize("drag", [.01, 0.])
def test_zero_endpoint_branches(root, tip, drag):
    result = check_linear_benchmark({
        **INPUTS, "pitch_root_rad": root, "pitch_tip_rad": tip,
        "profile_drag_coefficient": drag,
    })
    for row in result["rows"]:
        if drag == 0.:
            assert row["CP0"] == 0.
        if root == tip == 0.:
            assert row["CT"] == row["CPi"] == row["thrust_N"] == 0.
            assert row["CP"] == pytest.approx(row["CP0"])


@pytest.mark.parametrize("root", [None, True, False, "0.16", math.nan, math.inf, -.1])
def test_invalid_linear_root(root):
    with pytest.raises((TypeError, ValueError)):
        benchmark_refinement(**{**INPUTS, "pitch_root_rad": root}, annuli_counts=ANNULI)


@pytest.mark.parametrize("law", ["constant", "hyperbolic"])
def test_nonlinear_law_rejects_explicit_zero_root(law):
    with pytest.raises((TypeError, ValueError)):
        benchmark_refinement(
            **{**INPUTS, "twist_law": law, "pitch_root_rad": 0.},
            annuli_counts=ANNULI,
        )


def test_equal_endpoints_match_constant_rows():
    linear = check_linear_benchmark({**INPUTS, "pitch_root_rad": .08})
    constant_inputs = {**INPUTS, "twist_law": "constant"}
    del constant_inputs["pitch_root_rad"]
    constant = benchmark_refinement(**constant_inputs, annuli_counts=ANNULI)
    assert len(constant["rows"]) == len(linear["rows"])
    for linear_row, constant_row in zip(linear["rows"], constant["rows"]):
        assert linear_row["annuli"] == constant_row["annuli"]
        for key in (*FIELDS, "CT_change", "CP_change"):
            if linear_row[key] is None:
                assert constant_row[key] is None
            else:
                assert linear_row[key] == pytest.approx(constant_row[key])
