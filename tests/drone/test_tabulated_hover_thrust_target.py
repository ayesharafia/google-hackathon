"""Actual-forward inverse safety checks; no physical qualification claim."""

import math
import sys
from copy import deepcopy
from unittest.mock import Mock

import pytest

from physimesh.drone import reference_air_tabulated_hover as reference
from physimesh.drone import tabulated_hover_bemt_request as child
from physimesh.drone import tabulated_hover_thrust_target as inverse
from physimesh.drone.provenance import sha256_record
from tests.drone.test_tabulated_hover_bemt import inputs


def request(omega=100.0, **overrides):
    """Generate a target with the actual accepted forward, before installing spies."""
    forward_request = {"evaluation": child.EVALUATION, **inputs(angular_speed_rad_s=omega)}
    actual = child.evaluate_tabulated_hover_bemt(forward_request)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL"
    template = deepcopy(forward_request)
    del template["angular_speed_rad_s"]
    return {
        "evaluation": inverse.EVALUATION, "rotor_template": template,
        "target_thrust_n": actual["outputs"]["thrust_n"],
        "angular_speed_bracket_rad_s": [50.0, 150.0],
        "absolute_thrust_tolerance_n": 1e-10, "max_evaluations": 32,
        **overrides,
    }


def actual_spies(monkeypatch):
    records = []

    def actual_forward(supplied):
        before = deepcopy(supplied)
        actual = child.evaluate_tabulated_hover_bemt(supplied)
        records.append((before, actual))
        return actual

    forward = Mock(side_effect=actual_forward)
    core = Mock(wraps=child.solve_tabulated_hover)
    air = Mock(side_effect=AssertionError("Reference air must not run"))
    monkeypatch.setattr(inverse, "evaluate_tabulated_hover_bemt", forward)
    monkeypatch.setattr(child, "solve_tabulated_hover", core)
    monkeypatch.setattr(reference, "reference_air_properties", air)
    return records, forward, core, air


def assert_digest(result):
    assert result["evaluation_sha256"] == sha256_record({
        key: value for key, value in result.items() if key != "evaluation_sha256"
    })


def assert_atomic(result, status, count, supplied=None):
    assert result["status"] == status
    assert result["outputs"] == result["output_units"] == {}
    assert result["trace"] == []
    assert result["diagnostics_complete"] is False
    assert type(result["evaluation_count"]) is int and result["evaluation_count"] == count
    assert result["evidence_level"] == "unverified"
    assert result["aircraft_status"] is result["feasibility"] is None
    for name in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert result[name] == "NOT_ESTABLISHED"
    assert result["request_sha256"] == (sha256_record(supplied) if supplied is not None else None)
    if supplied is not None and status != "MODEL_INAPPLICABLE":
        assert_digest(result)
    else:
        assert result["evaluation_sha256"] is None


@pytest.mark.parametrize("omega,expected_speeds", [
    (100.0, [50.0, 150.0, 100.0]), (50.0, [50.0, 150.0]), (150.0, [50.0, 150.0]),
])
def test_actual_smoke_midpoint_and_endpoints(monkeypatch, omega, expected_speeds):
    supplied = request(omega)
    before = deepcopy(supplied)
    records, forward, core, air = actual_spies(monkeypatch)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["diagnostics_complete"] is True
    assert result["evaluation_count"] == len(expected_speeds)
    assert forward.call_count == core.call_count == len(expected_speeds)
    air.assert_not_called()
    assert [record[0]["angular_speed_rad_s"] for record in records] == expected_speeds
    outputs = result["outputs"]
    assert outputs["angular_speed_rad_s"] == omega
    assert outputs["evaluations"] == len(expected_speeds)
    selected_request, selected_actual = next(pair for pair in records if pair[0]["angular_speed_rad_s"] == omega)
    assert outputs["actual_forward_request"] == selected_request
    assert outputs["actual_forward_result"] == selected_actual
    assert outputs["actual_forward_result"] is not selected_actual
    assert outputs["actual_forward_result"]["evaluation_sha256"] == selected_actual["evaluation_sha256"]
    assert outputs["achieved_thrust_n"] == selected_actual["outputs"]["thrust_n"]
    assert outputs["thrust_residual_n"] == outputs["achieved_thrust_n"] - supplied["target_thrust_n"]
    assert abs(outputs["thrust_residual_n"]) <= supplied["absolute_thrust_tolerance_n"]
    assert result["output_units"]["actual_forward_result"] == selected_actual["output_units"]
    assert result["trace"] == [
        {"angular_speed_rad_s": injected["angular_speed_rad_s"],
         "thrust_n": actual["outputs"]["thrust_n"],
         "thrust_residual_n": actual["outputs"]["thrust_n"] - supplied["target_thrust_n"],
         "request_sha256": sha256_record(injected), "full_actual_result_sha256": sha256_record(actual)}
        for injected, actual in records
    ]
    assert result["request_sha256"] == sha256_record(before)
    assert_digest(result)
    assert supplied == before


def test_actual_smoke_zero_angle_not_bracketed(monkeypatch):
    supplied = request()
    for station in supplied["rotor_template"]["stations"]:
        station["blade_angle_rad"] = 0.0
    records, forward, core, air = actual_spies(monkeypatch)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "TARGET_NOT_BRACKETED", 2, supplied)
    assert forward.call_count == core.call_count == 2
    assert [actual["outputs"]["thrust_n"] for _, actual in records] == [0.0, 0.0]
    air.assert_not_called()


def test_actual_smoke_two_call_budget(monkeypatch):
    supplied = request(max_evaluations=2)
    _, forward, core, air = actual_spies(monkeypatch)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "ITERATION_LIMIT", 2, supplied)
    assert forward.call_count == core.call_count == 2
    air.assert_not_called()


def test_actual_smoke_negative_chord_core_refusal(monkeypatch):
    supplied = request()
    supplied["rotor_template"]["stations"][0]["chord_m"] = -0.04
    records, forward, core, air = actual_spies(monkeypatch)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "MODEL_INAPPLICABLE", 1, supplied)
    assert forward.call_count == core.call_count == 1
    assert records[0][1]["status"] == "MODEL_INAPPLICABLE"
    air.assert_not_called()


@pytest.mark.parametrize("change", [
    lambda r: r.update(extra=1),
    lambda r: r.pop("max_evaluations"),
    lambda r: r.update(evaluation=True),
    lambda r: r.update(rotor_template=[]),
    lambda r: r["rotor_template"].update(angular_speed_rad_s=100.0),
    lambda r: r["rotor_template"].pop("density_kg_m3"),
    lambda r: r["rotor_template"].update(evaluation="another_child"),
    lambda r: r["rotor_template"].update(evaluation=False),
    lambda r: r["rotor_template"].update(radius_m=True),
    lambda r: r["rotor_template"].update(density_kg_m3="1.225"),
    lambda r: r["rotor_template"].update(geometry_source=" \t"),
    lambda r: r["rotor_template"].update(uncertainty_status=None),
    lambda r: r["rotor_template"].update(geometry_kind="verified"),
    lambda r: r["rotor_template"].update(geometry_kind=1),
    lambda r: r["rotor_template"].update(annuli=0),
    lambda r: r["rotor_template"].update(annuli=513),
    lambda r: r["rotor_template"].update(annuli=512.0),
    lambda r: r["rotor_template"].update(blade_count=True),
    lambda r: r["rotor_template"].update(blade_count=33),
    lambda r: r["rotor_template"].update(blade_count=0),
    lambda r: r["rotor_template"].update(stations=[]),
    lambda r: r["rotor_template"].update(stations=[r["rotor_template"]["stations"][0]]),
    lambda r: r["rotor_template"].update(stations=r["rotor_template"]["stations"] * 86),
    lambda r: r["rotor_template"]["stations"][0].update(extra=0),
    lambda r: r["rotor_template"]["stations"][0].update(chord_m=False),
    lambda r: r.update(max_evaluations=True),
    lambda r: r.update(max_evaluations=2.0),
    lambda r: r.update(max_evaluations=1),
    lambda r: r.update(max_evaluations=65),
    lambda r: r.update(target_thrust_n=0.0),
    lambda r: r.update(target_thrust_n=-1.0),
    lambda r: r.update(target_thrust_n=True),
    lambda r: r.update(target_thrust_n=math.nextafter(0.0, 1.0)),
    lambda r: r.update(absolute_thrust_tolerance_n=0.0),
    lambda r: r.update(absolute_thrust_tolerance_n=False),
    lambda r: r.update(absolute_thrust_tolerance_n=math.nextafter(0.0, 1.0)),
    lambda r: r.update(absolute_thrust_tolerance_n=r["target_thrust_n"]),
    lambda r: r.update(absolute_thrust_tolerance_n=r["target_thrust_n"] * 2),
    lambda r: r.update(angular_speed_bracket_rad_s=(50.0, 150.0)),
    lambda r: r.update(angular_speed_bracket_rad_s=[50.0]),
    lambda r: r.update(angular_speed_bracket_rad_s=[50.0, 100.0, 150.0]),
    lambda r: r.update(angular_speed_bracket_rad_s=[150.0, 50.0]),
    lambda r: r.update(angular_speed_bracket_rad_s=[50.0, 50.0]),
    lambda r: r.update(angular_speed_bracket_rad_s=[0.0, 150.0]),
    lambda r: r.update(angular_speed_bracket_rad_s=[True, 150.0]),
    lambda r: r.update(angular_speed_bracket_rad_s=[math.nextafter(0.0, 1.0), 150.0]),
])
def test_preflight_invalid_no_actual_calls(monkeypatch, change):
    supplied = request()
    change(supplied)
    _, forward, core, air = actual_spies(monkeypatch)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "MODEL_INAPPLICABLE", 0)
    forward.assert_not_called()
    core.assert_not_called()
    air.assert_not_called()


class ForeignDict(dict):
    def __deepcopy__(self, memo):
        raise AssertionError("Foreign copy hook must not run")


def nested(depth):
    value = 0
    for _ in range(depth):
        value = [value]
    return value


@pytest.mark.parametrize("bad", [
    ForeignDict(), (1, 2), b"bytes", {1: 2}, {"bad": float("nan")},
    {"bad": float("inf")}, {"bad": "\ud800"}, {"bad": "x" * 2001},
    {"bad": 1 << 1023}, [0] * 257, nested(11),
    [[0] * 256] * 65,
])
def test_strict_json_walk_rejects_before_any_copy(monkeypatch, bad):
    copy = Mock(side_effect=AssertionError("Input must be rejected before copying"))
    forward = Mock(side_effect=AssertionError("No calls allowed"))
    monkeypatch.setattr(inverse, "deepcopy", copy)
    monkeypatch.setattr(inverse, "evaluate_tabulated_hover_bemt", forward)
    # _response needs deepcopy for fresh limit metadata, so distinguish the
    # rejected input from that permitted small metadata copy.
    copy.side_effect = lambda value: deepcopy(value) if value is inverse._LIMITS else pytest.fail("Input copied")
    result = inverse.evaluate_tabulated_hover_thrust_target(bad)
    assert_atomic(result, "MODEL_INAPPLICABLE", 0)
    assert copy.call_count == 1
    assert copy.call_args.args[0] is inverse._LIMITS
    forward.assert_not_called()


def test_unsupported_and_snapshot_exception_have_no_hashes(monkeypatch):
    supplied = request(evaluation="unsupported")
    _, forward, core, air = actual_spies(monkeypatch)
    assert_atomic(inverse.evaluate_tabulated_hover_thrust_target(supplied), "SOLVER_UNSUPPORTED", 0)
    forward.assert_not_called()
    core.assert_not_called()
    air.assert_not_called()
    original_copy = inverse.deepcopy

    def fail_snapshot(value):
        if value is supplied:
            raise RuntimeError("private snapshot exception")
        return original_copy(value)

    monkeypatch.setattr(inverse, "deepcopy", fail_snapshot)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "EXECUTION_FAILED", 0)
    assert "private snapshot exception" not in str(result)


def test_actual_maximum_work_shape_endpoint_and_output_budget(monkeypatch):
    supplied = request(50.0, max_evaluations=64)
    template = supplied["rotor_template"]
    template.update(annuli=512, blade_count=32, stations=[
        {"radius_m": index / 255, "chord_m": 0.05, "blade_angle_rad": 0.08}
        for index in range(256)
    ])
    expected_request = {**deepcopy(template), "angular_speed_rad_s": 50.0}
    expected = child.evaluate_tabulated_hover_bemt(expected_request)
    assert expected["status"] == "COMPUTED_EXPERIMENTAL"
    supplied["target_thrust_n"] = expected["outputs"]["thrust_n"]
    _, forward, core, air = actual_spies(monkeypatch)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["actual_forward_result"] == expected
    assert result["outputs"]["actual_forward_request"] == expected_request
    assert result["evaluation_count"] == forward.call_count == core.call_count == 2
    assert supplied["max_evaluations"] * template["annuli"] == 32768
    assert len(result["outputs"]["actual_forward_result"]["outputs"]["radii_m"]) == 512
    assert len(result["outputs"]["actual_forward_request"]["stations"]) == 256
    inverse._JSON(result, result["limits"]["output_json"])
    assert_digest(result)
    air.assert_not_called()


@pytest.mark.parametrize("omega", [25.0, 175.0])
def test_actual_outside_both_bracket_sides_no_expansion(monkeypatch, omega):
    supplied = request(omega)
    records, forward, core, air = actual_spies(monkeypatch)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "TARGET_NOT_BRACKETED", 2, supplied)
    assert [injected["angular_speed_rad_s"] for injected, _ in records] == [50.0, 150.0]
    assert forward.call_count == core.call_count == 2
    air.assert_not_called()


def test_actual_three_call_budget_discards_midpoint_trace(monkeypatch):
    supplied = request(87.5, max_evaluations=3)
    records, forward, core, air = actual_spies(monkeypatch)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "ITERATION_LIMIT", 3, supplied)
    assert [injected["angular_speed_rad_s"] for injected, _ in records] == [50.0, 150.0, 100.0]
    assert forward.call_count == core.call_count == 3
    air.assert_not_called()


def test_actual_several_bisections_each_trial_calls_core(monkeypatch):
    supplied = request(87.5, absolute_thrust_tolerance_n=sys.float_info.min)
    records, forward, core, air = actual_spies(monkeypatch)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    speeds = [50.0, 150.0, 100.0, 75.0, 87.5]
    assert [injected["angular_speed_rad_s"] for injected, _ in records] == speeds
    assert forward.call_count == core.call_count == result["evaluation_count"] == 5
    assert len(result["trace"]) == 5
    assert result["outputs"]["thrust_residual_n"] == 0.0
    assert result["outputs"]["actual_forward_result"] == records[-1][1]
    assert result["trace"][-1]["full_actual_result_sha256"] == sha256_record(records[-1][1])
    assert_digest(result)
    air.assert_not_called()


@pytest.mark.parametrize("call_at", [1, 2, 3])
def test_ordinary_forward_exception_counts_attempt_and_clears(monkeypatch, call_at):
    supplied = request()
    core = Mock(wraps=child.solve_tabulated_hover)

    def forward(arguments):
        if spy.call_count == call_at:
            raise RuntimeError("private forward exception text")
        return child.evaluate_tabulated_hover_bemt(arguments)

    spy = Mock(side_effect=forward)
    monkeypatch.setattr(inverse, "evaluate_tabulated_hover_bemt", spy)
    monkeypatch.setattr(child, "solve_tabulated_hover", core)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "EXECUTION_FAILED", call_at, supplied)
    assert spy.call_count == call_at and core.call_count == call_at - 1
    assert "private forward exception text" not in str(result)


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
def test_forward_base_exception_propagates_after_one_actual_attempt(monkeypatch, exception):
    supplied = request()
    spy = Mock(side_effect=exception("private BaseException"))
    core = Mock(wraps=child.solve_tabulated_hover)
    monkeypatch.setattr(inverse, "evaluate_tabulated_hover_bemt", spy)
    monkeypatch.setattr(child, "solve_tabulated_hover", core)
    with pytest.raises(exception):
        inverse.evaluate_tabulated_hover_thrust_target(supplied)
    spy.assert_called_once()
    core.assert_not_called()


def test_catalog_fresh_closed_fields_units_hashes_and_limits():
    baseline = inverse.tabulated_hover_thrust_target_catalog()
    changed = inverse.tabulated_hover_thrust_target_catalog()
    assert set(baseline["required_fields"]) == {
        "evaluation", "rotor_template", "target_thrust_n", "angular_speed_bracket_rad_s",
        "absolute_thrust_tolerance_n", "max_evaluations",
    }
    assert set(baseline["rotor_template_fields"]) == set(child._REQUEST_KEYS) - {"angular_speed_rad_s"}
    assert "density_kg_m3" in baseline["rotor_template_fields"]
    assert baseline["response_contract"]["bounded_refusals"] == [
        "TARGET_NOT_BRACKETED", "ITERATION_LIMIT", "NUMERICAL_LIMIT",
    ]
    assert baseline["input_units"]["rotor_template"]["density_kg_m3"] == "kg/m^3"
    assert baseline["output_field_units"]["actual_forward_result"] == child._OUTPUT_UNITS
    assert baseline["output_field_units"]["actual_forward_request"] == child._INPUT_UNITS
    assert baseline["limits"]["input_json"] == {
        "max_depth": 11, "max_nodes_including_keys": 16384, "max_container_items": 256,
        "max_string_characters": 2000, "max_integer_bits": 1023, "finite_floats_only": True,
        "valid_utf8_only": True, "root_depth": 1,
    }
    assert baseline["limits"]["output_json"]["max_depth"] == 16
    assert baseline["limits"]["output_json"]["max_nodes_including_keys"] == 65536
    changed["limits"]["input_json"]["max_depth"] = 0
    changed["limits"]["child_input_json"].clear()
    changed["input_units"]["rotor_template"]["stations"]["chord_m"] = "bad"
    changed["output_field_units"]["actual_forward_result"]["stations"].clear()
    changed["required_fields"].clear()
    changed["rotor_template_fields"].clear()
    changed["limitations"].clear()
    changed["trace_field_units"].clear()
    changed["response_contract"]["bounded_refusals"].clear()
    assert inverse.tabulated_hover_thrust_target_catalog() == baseline


def rehash_actual(actual):
    actual["evaluation_sha256"] = sha256_record({
        key: value for key, value in actual.items() if key != "evaluation_sha256"
    })


def forge_inflow_and_residual(actual):
    values = actual["outputs"]
    values["inflow_ratio"][0] *= 1.01
    values["approx_inflow_angle_rad"][0] = values["inflow_ratio"][0] / values["radial_fraction"][0]
    values["approx_angle_of_attack_rad"][0] = (
        values["blade_angle_rad"][0] - values["approx_inflow_angle_rad"][0]
    )
    values["local_balance_coefficient"][0] = 0.0


def forge_coherent_load_scale(actual):
    values = actual["outputs"]
    for name in ("thrust_n", "shaft_power_w", "shaft_torque_nm"):
        values[name] *= 2.0


@pytest.mark.parametrize("failure_at", [2, 3])
@pytest.mark.parametrize("forge", [
    lambda a: a.update(extra="forbidden"),
    lambda a: a.pop("core_version"),
    lambda a: a.update(evaluation="another_evaluation"),
    lambda a: a.update(model_id="another_model"),
    lambda a: a.update(schema_version="another_schema"),
    lambda a: a.update(evidence_level="validated"),
    lambda a: a.update(physical_validation="ESTABLISHED"),
    lambda a: a.update(numerical_qualification="ESTABLISHED"),
    lambda a: a.update(runtime_identity="ESTABLISHED"),
    lambda a: a.update(aircraft_status="feasible"),
    lambda a: a.update(feasibility=True),
    lambda a: a.update(status="EXECUTION_FAILED"),
    lambda a: a.update(status="MODEL_INAPPLICABLE"),
    lambda a: a.update(diagnostics_complete=1),
    lambda a: a.update(reasons=["unexpected reason"]),
    lambda a: a.update(core_model="forged_core"),
    lambda a: a.update(core_version=0.1),
    lambda a: a.update(core_status="CONVERGED"),
    lambda a: a["limitations"].pop(),
    lambda a: a["limits"]["core_work"].update(annuli_max=512),
    lambda a: a["limits"]["input_json"].update(root_depth=True),
    lambda a: a["output_units"].update(thrust_n="kg"),
    lambda a: a["outputs"].update(extra=0),
    lambda a: a["outputs"].update(annuli=float(a["outputs"]["annuli"])),
    lambda a: a["outputs"].update(geometry_source="changed source"),
    lambda a: a["outputs"]["stations"][0].update(chord_m=0.05),
    lambda a: a["outputs"]["chord_m"].__setitem__(0, 0.5),
    lambda a: a["outputs"]["radial_fraction"].__setitem__(0, 0.5),
    lambda a: a["outputs"].update(thrust_coefficient=a["outputs"]["thrust_coefficient"] * 1.01),
    lambda a: a.update(request_sha256="0" * 64),
    forge_inflow_and_residual,
    forge_coherent_load_scale,
])
def test_coherently_rehashed_actual_forgeries_are_atomic(monkeypatch, failure_at, forge):
    supplied = request()
    core = Mock(wraps=child.solve_tabulated_hover)
    guard = Mock(wraps=inverse._validate_child)

    def forward(arguments):
        actual = child.evaluate_tabulated_hover_bemt(arguments)
        assert actual["status"] == "COMPUTED_EXPERIMENTAL"
        if spy.call_count == failure_at:
            forge(actual)
            rehash_actual(actual)
        return actual

    spy = Mock(side_effect=forward)
    monkeypatch.setattr(inverse, "evaluate_tabulated_hover_bemt", spy)
    monkeypatch.setattr(inverse, "_validate_child", guard)
    monkeypatch.setattr(child, "solve_tabulated_hover", core)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "EXECUTION_FAILED", failure_at, supplied)
    assert spy.call_count == core.call_count == guard.call_count == failure_at


@pytest.mark.parametrize("failure_at", [1, 2, 3])
def test_actual_child_evaluation_hash_must_match_full_envelope(monkeypatch, failure_at):
    supplied = request()

    def forward(arguments):
        actual = child.evaluate_tabulated_hover_bemt(arguments)
        if spy.call_count == failure_at:
            actual["evaluation_sha256"] = "0" * 64
        return actual

    spy = Mock(side_effect=forward)
    monkeypatch.setattr(inverse, "evaluate_tabulated_hover_bemt", spy)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "EXECUTION_FAILED", failure_at, supplied)
    assert spy.call_count == failure_at


@pytest.mark.parametrize("omega", [50.0, 87.5])
def test_reused_mutated_child_objects_preserve_original_snapshots(monkeypatch, omega):
    supplied = request(omega)
    before = deepcopy(supplied)
    shared, original_actuals = {}, []
    core = Mock(wraps=child.solve_tabulated_hover)

    def forward(arguments):
        if shared:
            # Deliberately mutate the previous result before returning the next
            # actual result using the very same outer object.
            shared["outputs"]["stations"][0]["chord_m"] = 999.0
            shared["outputs"]["inflow_ratio"][0] = 999.0
        actual = child.evaluate_tabulated_hover_bemt(arguments)
        original_actuals.append((deepcopy(arguments), deepcopy(actual)))
        shared.clear()
        shared.update(actual)
        return shared

    spy = Mock(side_effect=forward)
    monkeypatch.setattr(inverse, "evaluate_tabulated_hover_bemt", spy)
    monkeypatch.setattr(child, "solve_tabulated_hover", core)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    expected_calls = 2 if omega == 50.0 else 5
    assert spy.call_count == core.call_count == expected_calls
    selected_request, selected_actual = next(
        pair for pair in original_actuals if pair[0]["angular_speed_rad_s"] == omega
    )
    outputs = result["outputs"]
    assert outputs["actual_forward_request"] == selected_request
    assert outputs["actual_forward_result"] == selected_actual
    assert outputs["actual_forward_result"] is not shared
    assert [entry["full_actual_result_sha256"] for entry in result["trace"]] == [
        sha256_record(actual) for _, actual in original_actuals
    ]
    retained = deepcopy(result)
    shared["outputs"]["stations"][0]["chord_m"] = -123.0
    shared["output_units"].clear()
    assert result == retained
    # Also check the inverse-to-child alias boundary in the other direction.
    outputs["actual_forward_result"]["outputs"]["radii_m"].clear()
    assert shared["outputs"]["radii_m"]
    assert supplied == before


def test_argument_and_caller_mutation_preserve_bound_injected_snapshots(monkeypatch):
    supplied = request(87.5)
    before = deepcopy(supplied)
    arguments_kept, original_actuals = [], []

    def forward(arguments):
        injected = deepcopy(arguments)
        actual = child.evaluate_tabulated_hover_bemt(arguments)
        original_actuals.append((injected, deepcopy(actual)))
        arguments_kept.append(arguments)
        arguments["density_kg_m3"] = -1.0
        arguments["stations"][0]["chord_m"] = -1.0
        arguments["stations"].reverse()
        # Changes made after the outer copy must not steer later trial requests.
        supplied["rotor_template"]["density_kg_m3"] = 8.0
        supplied["rotor_template"]["stations"][0]["blade_angle_rad"] = 9.0
        supplied["angular_speed_bracket_rad_s"][:] = [1.0, 2.0]
        supplied["target_thrust_n"] = 999.0
        return actual

    spy = Mock(side_effect=forward)
    monkeypatch.setattr(inverse, "evaluate_tabulated_hover_bemt", spy)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["request_sha256"] == sha256_record(before)
    assert spy.call_count == 5
    assert result["outputs"]["actual_forward_request"] == original_actuals[-1][0]
    assert result["outputs"]["actual_forward_result"] == original_actuals[-1][1]
    assert [entry["request_sha256"] for entry in result["trace"]] == [
        sha256_record(injected) for injected, _ in original_actuals
    ]
    assert all(injected["density_kg_m3"] == before["rotor_template"]["density_kg_m3"]
               for injected, _ in original_actuals)
    assert_digest(result)
    unchanged = deepcopy(result)
    arguments_kept[-1]["stations"].clear()
    supplied["rotor_template"]["stations"].clear()
    assert result == unchanged


@pytest.mark.parametrize("failure_at", [1, 2, 3])
def test_argument_mutation_with_actual_changed_return_fails_original_request_binding(monkeypatch, failure_at):
    supplied = request()
    before = deepcopy(supplied)
    core = Mock(wraps=child.solve_tabulated_hover)

    def forward(arguments):
        if spy.call_count == failure_at:
            arguments["density_kg_m3"] *= 1.01
        # The response is a genuine, valid child response for its actual input,
        # but that changed input is not the inverse's bound injected snapshot.
        return child.evaluate_tabulated_hover_bemt(arguments)

    spy = Mock(side_effect=forward)
    monkeypatch.setattr(inverse, "evaluate_tabulated_hover_bemt", spy)
    monkeypatch.setattr(child, "solve_tabulated_hover", core)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "EXECUTION_FAILED", failure_at, before)
    assert spy.call_count == core.call_count == failure_at
    assert supplied == before


def test_real_adjacent_speed_bracket_stagnation_no_invented_call(monkeypatch):
    lo, hi = 50.0, math.nextafter(50.0, math.inf)
    supplied = request(angular_speed_bracket_rad_s=[lo, hi],
                       absolute_thrust_tolerance_n=sys.float_info.min)
    endpoint_actuals = [child.evaluate_tabulated_hover_bemt({
        **deepcopy(supplied["rotor_template"]), "angular_speed_rad_s": omega,
    }) for omega in (lo, hi)]
    left, right = [actual["outputs"]["thrust_n"] for actual in endpoint_actuals]
    target = left + (right - left) / 2
    assert 0 < left < target < right
    supplied["target_thrust_n"] = target
    records, forward, core, air = actual_spies(monkeypatch)
    result = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "NUMERICAL_LIMIT", 2, supplied)
    assert forward.call_count == core.call_count == 2
    assert [injected["angular_speed_rad_s"] for injected, _ in records] == [lo, hi]
    assert [actual for _, actual in records] == endpoint_actuals
    air.assert_not_called()


def test_input_walker_exact_depth_nodes_items_utf8_integer_and_float_bounds():
    limits = inverse.tabulated_hover_thrust_target_catalog()["limits"]["input_json"]
    inverse._JSON(nested(10), limits)
    with pytest.raises(ValueError):
        inverse._JSON(nested(11), limits)
    # 1 list node + 127 occurrences of (1 dict + 64 keys + 64 values).
    # Aliased occurrences consume the same node count as repeated JSON text.
    shared = {str(index): 0 for index in range(64)}
    exactly_16384_nodes = [shared] * 127
    inverse._JSON(exactly_16384_nodes, limits)
    with pytest.raises(ValueError):
        inverse._JSON([*exactly_16384_nodes, 0], limits)
    inverse._JSON([0] * 256, limits)
    inverse._JSON({str(index): 0 for index in range(256)}, limits)
    with pytest.raises(ValueError):
        inverse._JSON({str(index): 0 for index in range(257)}, limits)
    inverse._JSON("\U0001f680" * 2000, limits)
    with pytest.raises(ValueError):
        inverse._JSON("\U0001f680" * 2001, limits)
    inverse._JSON((1 << 1023) - 1, limits)
    inverse._JSON(-((1 << 1023) - 1), limits)
    with pytest.raises(ValueError):
        inverse._JSON(-(1 << 1023), limits)
    inverse._JSON([0.0, math.nextafter(0.0, 1.0), sys.float_info.max], limits)
    for nonfinite in (math.inf, -math.inf, math.nan):
        with pytest.raises(ValueError):
            inverse._JSON(nonfinite, limits)


def test_cycle_and_foreign_scalar_hooks_rejected_before_copy(monkeypatch):
    class ForeignFloat(float):
        def __float__(self):
            pytest.fail("Foreign conversion hook invoked")

        def __deepcopy__(self, memo):
            pytest.fail("Foreign copy hook invoked")

    cyclic = []
    cyclic.append(cyclic)
    forward = Mock(side_effect=AssertionError("No calls allowed"))
    monkeypatch.setattr(inverse, "evaluate_tabulated_hover_bemt", forward)
    for bad in (cyclic, ForeignFloat(1.0)):
        assert_atomic(inverse.evaluate_tabulated_hover_thrust_target(bad), "MODEL_INAPPLICABLE", 0)
    forward.assert_not_called()
