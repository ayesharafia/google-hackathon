import json
import math
from itertools import pairwise

import pytest

from physimesh.drone.hover_bemt_benchmark import (
    benchmark_refinement,
)

BASE = {
    "radius_m": 1.0, "angular_speed_rad_s": 100.0, "density_kg_m3": 1.225, "blade_count": 2, "chord_m": 0.05,
    "lift_curve_slope_per_rad": 5.7, "profile_drag_coefficient": 0.01,
    "pitch_tip_rad": 0.08, "root_cutout_fraction": 0.2,
    "twist_law": "hyperbolic", "annuli_counts": (8, 16, 32, 64, 128),
}
REFERENCE = {
    "CT": 0.002057961800646661, "CPi": 6.737601945932155e-05,
    "CP0": 3.9725073795737075e-05,
}
ERRORS = ("CT_absolute_error", "CPi_absolute_error", "CP0_absolute_error")
ORDERS = ("CT_observed_order", "CPi_observed_order", "profile_observed_order")
OUTPUTS = (
    "CT", "CPi", "CP0", "CP", "thrust_N", "power_W", "torque_Nm",
    "thrust_balance_coefficient", "max_local_balance_coefficient",
)
KEYS = set(OUTPUTS + ERRORS + ORDERS + ("annuli", "CT_change", "CP_change"))


def run(**overrides):
    result = benchmark_refinement(**(BASE | overrides))
    assert result["status"] == "BENCHMARK_COMPUTED"
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    json.dumps(result, allow_nan=False)
    rows = result["rows"]
    assert isinstance(rows, list)
    assert [row["annuli"] for row in rows] == list(BASE["annuli_counts"])
    assert all(KEYS <= row.keys() for row in rows)
    assert rows[0]["CT_change"] is None and rows[0]["CP_change"] is None
    return result, rows


def test_hyperbolic_reference_and_midpoint_profile_order():
    result, rows = run()
    assert result["reference_kind"] == "ideal_hyperbolic_closed_form"
    for key, value in REFERENCE.items():
        assert result["reference"][key] == pytest.approx(value, rel=1e-12)
    for row in rows:
        for key in ("CT", "CPi"):
            assert row[key] == pytest.approx(REFERENCE[key], abs=1e-15, rel=0)
            assert 0 <= row[f"{key}_absolute_error"] < 1e-15
            assert row[f"{key}_observed_order"] is None
        assert row["CP0_absolute_error"] == pytest.approx(
            abs(row["CP0"] - REFERENCE["CP0"]), abs=1e-18, rel=0
        )
    assert rows[0]["profile_observed_order"] is None
    for coarse, fine in pairwise(rows):
        assert fine["annuli"] == 2 * coarse["annuli"]
        assert fine["profile_observed_order"] == pytest.approx(2, abs=1e-7)
    assert rows[0]["CP0_absolute_error"] == pytest.approx(
        1.909859317102662e-7, rel=1e-10, abs=0
    )
    assert rows[-1]["CP0_absolute_error"] == pytest.approx(
        7.460387957291983e-10, rel=1e-10, abs=0
    )


def test_constant_pitch_reports_mesh_changes_without_reference_accuracy():
    result, rows = run(twist_law="constant")
    assert result["reference_kind"] == "mesh_change_only"
    assert all(result["reference"][key] is None for key in REFERENCE)
    assert all(row[key] is None for row in rows for key in ERRORS + ORDERS)
    for coarse, fine in pairwise(rows):
        assert fine["annuli"] == 2 * coarse["annuli"]
        for key in ("CT_change", "CP_change"):
            assert math.isfinite(fine[key]) and fine[key] > 0


@pytest.mark.parametrize("drag", [0.0, 0.01])
def test_zero_pitch_profile_order_does_not_establish_physical_validation(drag):
    result, rows = run(pitch_tip_rad=0.0, profile_drag_coefficient=drag)
    assert result["reference_kind"] == "ideal_hyperbolic_closed_form"
    for index, row in enumerate(rows):
        assert row["CT"] == row["CPi"] == row["thrust_N"] == 0
        assert row["CT_absolute_error"] == row["CPi_absolute_error"] == 0
        assert row["CT_observed_order"] is row["CPi_observed_order"] is None
        if drag == 0:
            assert all(row[key] == 0 for key in OUTPUTS + ERRORS)
        else:
            assert row["CP0"] > 0 and row["CP"] > 0
        if index == 0 or drag == 0:
            assert row["profile_observed_order"] is None
        else:
            assert row["profile_observed_order"] == pytest.approx(2, abs=1e-7)


@pytest.mark.parametrize("mesh", [
    [8, 16, 32], (8, 8), (8, 24), (True, 2), (8.0, 16.0),
    (-8, -4), (0, 1), (2048, 4096), (8,), (), tuple(2**i for i in range(13)),
])
def test_invalid_mesh(mesh):
    with pytest.raises(ValueError):
        benchmark_refinement(**(BASE | {"annuli_counts": mesh}))


@pytest.mark.parametrize("key", tuple(BASE)[:-2])
@pytest.mark.parametrize("value", [True, "1", math.nan, math.inf, -math.inf])
def test_invalid_physical_values(key, value):
    with pytest.raises((ValueError, TypeError)):
        benchmark_refinement(**(BASE | {key: value}))
