"""Synthetic test-only retained responses; arithmetic checks, no model evidence."""

import hashlib
import json
import math
import sys
from copy import deepcopy

import pytest

from physimesh.drone import polar_rotor as rotor
from physimesh.drone.polar_rotor_disk_pressure import derive_disk_pressure


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf-8")).hexdigest()


def _seal(value):
    value["evaluation_sha256"] = _digest({
        key: item for key, item in value.items() if key != "evaluation_sha256"})
    return value


@pytest.fixture
def synthetic_response():
    """Minimal consumed solver records only, never represented as actual solves."""
    # Borrow only unrelated envelope metadata; do not run any physical model.
    result = rotor._response("COMPUTED_EXPERIMENTAL", [], "a" * 64, 2, 2)
    rows, contributions = [], []
    for index, (inner, outer, thrust) in enumerate(((1.0, 2.0, 6.0), (2.0, 4.0, 10.0))):
        width = outer - inner
        rows.append({
            "annulus_index": index, "radial_inner_m": inner, "radial_outer_m": outer,
            "midpoint_radius_m": (inner + outer) / 2, "radial_width_m": width,
            "solve_result": {"outputs": {"solve_state": "CONVERGED",
                                          "solution": {"evaluation_index": 0}},
                             "output_units": {"solve_state": "label",
                                              "solution": {"evaluation_index": "index"}}},
        })
        contributions.append({
            "annulus_index": index, "selected_evaluation_index": 0,
            "thrust_density_n_m": thrust / width, "torque_density_nm_m": 0.0,
            "radial_width_m": width, "thrust_n": thrust, "torque_nm": 0.0,
        })
    result["outputs"] = {
        "rotor_state": "COMPUTED", "annuli": rows,
        "integrated": {"integration_method": "MIDPOINT_PRESCRIBED_ANNULI",
                       "contributions": contributions,
                       "totals": {"thrust_n": 16.0, "torque_nm": 0.0, "shaft_power_w": 0.0}},
    }
    result["output_units"] = rotor._output_units(rows, result["outputs"]["integrated"])
    result["diagnostics_complete"] = True
    return _seal(result)


def _assert_sealed(result):
    assert result["evaluation_sha256"] == _digest({
        key: value for key, value in result.items() if key != "evaluation_sha256"})


def _assert_refused(result, status="MODEL_INAPPLICABLE"):
    assert result["status"] == status
    assert result["reasons"] == ["INVALID_POLAR_ROTOR_RESPONSE" if status == "MODEL_INAPPLICABLE"
                                 else "DISK_PRESSURE_ARITHMETIC_FAILED"]
    assert result["disk_pressure_state"] == "NOT_RUN"
    assert result["outputs"] == result["output_units"] == {}
    assert result["diagnostics_complete"] is False
    for key in ("polar_rotor_result_count", "section_solve_result_count", "residual_result_count",
                "load_result_count", "lookup_result_count"):
        assert type(result[key]) is int and result[key] == 0
    _assert_sealed(result)


def test_independent_identity_and_input_immutability(synthetic_response):
    before = _digest(synthetic_response)
    retained = deepcopy(synthetic_response)
    result = derive_disk_pressure(synthetic_response)
    assert _digest(synthetic_response) == before
    assert synthetic_response == retained
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["schema_version"] == "polar_rotor_disk_pressure_v1"
    assert result["polar_rotor_result_count"] == 1
    output = result["outputs"]
    assert output["derivation"] == "ACTUATOR_DISK_IDENTITY_FROM_INTEGRATED_ANNULUS_THRUST"
    assert output["annuli"] == [
        {"annulus_index": 0, "disk_pressure_jump_pa": 6.0 / (math.pi * (2.0**2 - 1.0**2))},
        {"annulus_index": 1, "disk_pressure_jump_pa": 10.0 / (math.pi * (4.0**2 - 2.0**2))},
    ]
    assert output["rotor_mean_disk_loading_pa"] == (6.0 + 10.0) / (math.pi * 4.0**2)
    active_area = math.fsum((math.pi * (2.0**2 - 1.0**2), math.pi * (4.0**2 - 2.0**2)))
    assert active_area == 15.0 * math.pi
    assert output["rotor_active_annular_loading_pa"] == (6.0 + 10.0) / active_area
    assert output["input_digest"] == result["request_sha256"] == before
    assert "derived IDEALIZED ACTUATOR-DISK quantity from integrated annulus thrust" in result["state_text"]
    assert "NOT surface pressure, NOT a solved or CFD pressure field" in result["state_text"]
    assert "no spatial/vector information beyond the axisymmetric annulus" in result["state_text"]
    assert "full-disk mean spreads thrust over the whole disk including any inner hole" in result["state_text"]
    assert "active-annular mean spreads it only over the modeled annuli" in result["state_text"]
    assert "averaging areas differ whenever the innermost radius > 0" in result["state_text"]
    assert result["state_text"] in result["limitations"]
    _assert_sealed(result)
    output["annuli"][0]["disk_pressure_jump_pa"] = 999.0
    assert _digest(synthetic_response) == before


def test_inner_hole_distinguishes_full_disk_and_active_annular_means(synthetic_response):
    assert synthetic_response["outputs"]["annuli"][0]["radial_inner_m"] == 1.0
    output = derive_disk_pressure(synthetic_response)["outputs"]
    assert output["rotor_mean_disk_loading_pa"] == 16.0 / (16.0 * math.pi)
    assert output["rotor_active_annular_loading_pa"] == 16.0 / (15.0 * math.pi)
    assert output["rotor_active_annular_loading_pa"] > output["rotor_mean_disk_loading_pa"]


def test_units_cover_every_output_key(synthetic_response):
    result = derive_disk_pressure(synthetic_response)

    def check(values, units):
        if type(values) is dict:
            assert values.keys() == units.keys()
            for key in values:
                check(values[key], units[key])
        elif type(values) is list:
            assert len(values) == len(units)
            for value, unit in zip(values, units, strict=True):
                check(value, unit)
        else:
            assert type(units) is str and units

    check(result["outputs"], result["output_units"])
    assert result["output_units"]["rotor_mean_disk_loading_pa"] == "Pa"
    assert result["output_units"]["rotor_active_annular_loading_pa"] == "Pa"
    assert all(row["disk_pressure_jump_pa"] == "Pa" for row in result["output_units"]["annuli"])


@pytest.mark.parametrize("mutation", [
    "rotor_state", "integrated_none", "integrated_missing", "section_not_converged",
    "missing_thrust", "bad_index", "bool_index", "bool_thrust", "string_radius", "units",
    "missing_solution", "totals_shape", "root_extra", "bad_seal", "bad_count",
    "zero_area", "negative_area", "zero_outer", "negative_outer",
])
def test_refuses_malformed_and_unavailable_inputs(synthetic_response, mutation):
    output = synthetic_response["outputs"]
    row = output["annuli"][0]
    contribution = output["integrated"]["contributions"][0]
    if mutation == "rotor_state":
        output["rotor_state"] = "NOT_RUN_SECTION_NOT_CONVERGED"
    elif mutation == "integrated_none":
        output["integrated"] = None
    elif mutation == "integrated_missing":
        del output["integrated"]
    elif mutation == "section_not_converged":
        row["solve_result"]["outputs"]["solve_state"] = "EVALUATION_BUDGET_EXHAUSTED"
    elif mutation == "missing_thrust":
        del contribution["thrust_n"]
    elif mutation in ("bad_index", "bool_index"):
        contribution["annulus_index"] = 1 if mutation == "bad_index" else False
    elif mutation == "bool_thrust":
        contribution["thrust_n"] = True
    elif mutation == "string_radius":
        row["radial_outer_m"] = "2.0"
    elif mutation == "units":
        synthetic_response["output_units"]["rotor_state"] = "Pa"
    elif mutation == "missing_solution":
        del row["solve_result"]["outputs"]["solution"]
    elif mutation == "totals_shape":
        output["integrated"]["totals"] = []
    elif mutation == "root_extra":
        synthetic_response["extra"] = 0
    elif mutation == "bad_count":
        synthetic_response["section_solve_result_count"] = True
    elif mutation == "zero_area":
        row["radial_inner_m"] = row["radial_outer_m"]
    elif mutation == "negative_area":
        row["radial_inner_m"] = 3.0
    elif mutation in ("zero_outer", "negative_outer"):
        row["radial_outer_m"] = 0.0 if mutation == "zero_outer" else -2.0
    _seal(synthetic_response)
    if mutation == "bad_seal":
        synthetic_response["evaluation_sha256"] = "0" * 64
    before = _digest(synthetic_response)
    _assert_refused(derive_disk_pressure(synthetic_response))
    assert _digest(synthetic_response) == before


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("location", ["radius", "thrust", "torque", "hidden"])
def test_nonfinite_anywhere_is_refused(synthetic_response, value, location):
    output = synthetic_response["outputs"]
    if location == "radius":
        output["annuli"][0]["radial_outer_m"] = value
    elif location in ("thrust", "torque"):
        output["integrated"]["contributions"][0][location + ("_n" if location == "thrust" else "_nm")] = value
    else:
        synthetic_response["hidden"] = value
    _assert_refused(derive_disk_pressure(synthetic_response))


@pytest.mark.parametrize("payload", [None, [], {}, 1, True, "response"])
def test_malformed_root(payload):
    _assert_refused(derive_disk_pressure(payload))


def test_foreign_types_rejected_before_copy_hooks(synthetic_response):
    class Foreign(dict):
        def __deepcopy__(self, memo):
            pytest.fail("foreign deepcopy hook must not run")

        def items(self):
            pytest.fail("foreign iteration hook must not run")

    synthetic_response["outputs"]["hidden"] = Foreign()
    _assert_refused(derive_disk_pressure(synthetic_response))


@pytest.mark.parametrize("kind", ["area_overflow", "area_underflow", "pressure_underflow", "bad_total"])
def test_atomic_arithmetic_refusals(synthetic_response, kind):
    output = synthetic_response["outputs"]
    if kind in ("area_overflow", "area_underflow"):
        scale = 1e155 if kind == "area_overflow" else 1e-160
        for row, contribution in zip(output["annuli"], output["integrated"]["contributions"], strict=True):
            for key in ("radial_inner_m", "radial_outer_m", "midpoint_radius_m", "radial_width_m"):
                row[key] *= scale
            contribution["radial_width_m"] = row["radial_width_m"]
            contribution["thrust_density_n_m"] = contribution["thrust_n"] / row["radial_width_m"]
    elif kind == "pressure_underflow":
        for contribution in output["integrated"]["contributions"]:
            contribution["thrust_n"] = sys.float_info.min
            contribution["thrust_density_n_m"] = sys.float_info.min
        output["integrated"]["totals"]["thrust_n"] = 2 * sys.float_info.min
    else:
        output["integrated"]["totals"]["thrust_n"] = 17.0
    _seal(synthetic_response)
    _assert_refused(derive_disk_pressure(synthetic_response), "EXECUTION_FAILED")


def test_signed_thrust_and_zero_total(synthetic_response):
    integrated = synthetic_response["outputs"]["integrated"]
    integrated["contributions"][1].update(thrust_n=-6.0, thrust_density_n_m=-3.0)
    integrated["totals"]["thrust_n"] = 0.0
    result = derive_disk_pressure(_seal(synthetic_response))
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["annuli"][1]["disk_pressure_jump_pa"] == -6.0 / (math.pi * (4.0**2 - 2.0**2))
    assert result["outputs"]["rotor_mean_disk_loading_pa"] == 0.0
    assert result["outputs"]["rotor_active_annular_loading_pa"] == 0.0
