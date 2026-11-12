"""Actual solved DC points and chronological energy contract checks."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from physimesh.drone import dc_motor as dc
from physimesh.drone import tabulated_solved_dc_energy as energy
from physimesh.drone import tabulated_solved_dc_power as point
from physimesh.drone.provenance import sha256_record

from .test_tabulated_solved_dc_power import request as point_request


def request(count=2):
    return {"evaluation": energy.EVALUATION, "segments": [
        {"id": f"segment-{i}", "duration_s": i + 1, "power_request": point_request()}
        for i in range(count)]}


def assert_seal(actual, supplied):
    assert actual["request_sha256"] == sha256_record(supplied)
    assert actual["evaluation_sha256"] == sha256_record({
        key: value for key, value in actual.items() if key != "evaluation_sha256"})


def test_actual_two_point_met_energy_and_full_provenance(monkeypatch):
    supplied = request()
    supplied["segments"][1]["power_request"]["auxiliary"]["source"] = "second declaration"
    original = deepcopy(supplied)
    direct = [point.evaluate_tabulated_solved_dc_power(deepcopy(s["power_request"]))
              for s in supplied["segments"]]
    calls = Mock(wraps=point.evaluate_tabulated_solved_dc_power)
    monkeypatch.setattr(point, "evaluate_tabulated_solved_dc_power", calls)
    actual = energy.evaluate_tabulated_solved_dc_energy(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL", actual["reasons"]
    assert actual["diagnostics_complete"] is True
    assert actual["outputs"]["energy_state"] == "COMPUTED"
    assert supplied == original
    assert calls.call_count == actual["point_result_count"] == 2
    rows = actual["outputs"]["points"]
    integrated = actual["outputs"]["energy"]
    assert integrated["elapsed_s"] == 3.0
    assert integrated["all_motors_within_declared_limits"] is True
    for key in ("solve_result_count", "assembly_evaluation_count",
                "forward_evaluation_count", "motor_result_count"):
        assert actual[key] == sum(p[key] for p in direct)
    assert len(actual["transfers"]) == 18
    assert len(actual["stages"]) == 2
    for i, (segment, row, child) in enumerate(zip(supplied["segments"], rows, direct, strict=True)):
        assert row == {"segment_id": segment["id"], "duration_s": segment["duration_s"],
                       "actual_power_result": child}
        assert calls.call_args_list[i].args == (segment["power_request"],)
        stage = "segment:" + segment["id"]
        assert actual["stages"][i] == {
            "stage": stage, "inputs": segment["power_request"],
            "inputs_sha256": sha256_record(segment["power_request"]),
            "result_sha256": sha256_record(child)}
        assert actual["output_units"]["points"][i]["actual_power_result"] == {
            "outputs": child["output_units"]}
        erow = integrated["segments"][i]
        assert erow.keys() == {"segment_id", "start_time_s", "end_time_s",
                              "energy_j", "cumulative_energy_j"}
        assert erow["start_time_s"] == (0.0 if i == 0 else 1.0)
        assert erow["end_time_s"] == (1.0 if i == 0 else 3.0)
        for j, (key, field) in enumerate(energy._POWER_FIELDS.items()):
            watts = child["outputs"]["power"][field]
            assert erow["energy_j"][key] == watts * segment["duration_s"]
            prefix = [p["outputs"]["power"][field] * s["duration_s"]
                      for p, s in zip(direct[:i + 1], supplied["segments"][:i + 1], strict=True)]
            assert erow["cumulative_energy_j"][key] == dc._power_sum(prefix)
            assert actual["transfers"][i * 9 + j] == {
                "from_stage": stage, "from_field": "outputs.power." + field,
                "to_stage": "energy", "to_field": f"outputs.energy.segments[{i}].energy_j.{key}",
                "value": watts, "unit": "W", "producer_result_sha256": sha256_record(child),
                "consumer_request_sha256": sha256_record(supplied)}
    assert len(integrated["totals_j"]) == len(integrated["totals_wh"]) == 9
    for key in energy._POWER_FIELDS:
        assert integrated["totals_j"][key] == integrated["segments"][-1]["cumulative_energy_j"][key]
        assert integrated["totals_wh"][key] == integrated["totals_j"][key] / 3600
    assert_seal(actual, supplied)


@pytest.mark.parametrize("unmet_index", [0, 1])
def test_actual_mixed_unmet_preserves_both_points_and_runs_met_motors(monkeypatch, unmet_index):
    supplied = request()
    solve = supplied["segments"][unmet_index]["power_request"]["solve"]
    solve["max_evaluations"] = 2
    solve["required_net_force_body_n"][0] = 100.0
    calls = Mock(wraps=point.evaluate_tabulated_solved_dc_power)
    motors = Mock(wraps=dc.evaluate_dc_motor)
    monkeypatch.setattr(point, "evaluate_tabulated_solved_dc_power", calls)
    monkeypatch.setattr(dc, "evaluate_dc_motor", motors)
    actual = energy.evaluate_tabulated_solved_dc_energy(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL", actual["reasons"]
    assert actual["diagnostics_complete"] is True
    assert actual["outputs"].keys() == {"points", "energy_state", "energy"}
    assert actual["outputs"]["energy_state"] == "NOT_RUN_RESIDUAL_UNMET"
    assert actual["outputs"]["energy"] is None
    assert actual["transfers"] == []
    assert len(actual["stages"]) == calls.call_count == actual["point_result_count"] == 2
    rows = actual["outputs"]["points"]
    for i, row in enumerate(rows):
        child = row["actual_power_result"]
        assert child["status"] == "COMPUTED_EXPERIMENTAL"
        expected = "NOT_RUN_RESIDUAL_UNMET" if i == unmet_index else "COMPUTED"
        assert child["outputs"]["power_state"] == expected
        assert actual["output_units"]["points"][i]["actual_power_result"]["outputs"] == child["output_units"]
    assert rows[unmet_index]["actual_power_result"]["motor_result_count"] == 0
    assert rows[unmet_index]["actual_power_result"]["outputs"]["power"] is None
    assert motors.call_count == actual["motor_result_count"] == len(
        supplied["segments"][1 - unmet_index]["power_request"]["motors"])
    assert actual["output_units"]["energy"] == "not_applicable"
    assert_seal(actual, supplied)


def test_actual_native_large_integer_duration_is_retained():
    supplied = request(1)
    supplied["segments"][0]["duration_s"] = 9007199254740993
    actual = energy.evaluate_tabulated_solved_dc_energy(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL", actual["reasons"]
    duration = actual["outputs"]["points"][0]["duration_s"]
    assert type(duration) is int and duration == 9007199254740993
    assert actual["outputs"]["energy_state"] == "COMPUTED"
    assert_seal(actual, supplied)


@pytest.fixture(scope="module")
def actual_point():
    supplied = point_request()
    actual = point.evaluate_tabulated_solved_dc_power(deepcopy(supplied))
    assert actual["status"] == "COMPUTED_EXPERIMENTAL"
    assert actual["outputs"]["power_state"] == "COMPUTED"
    return supplied, actual


def reseal(actual):
    actual["evaluation_sha256"] = sha256_record({
        key: value for key, value in actual.items() if key != "evaluation_sha256"})


_FORGERIES = [
    (("status",), "MODEL_INAPPLICABLE"),
    (("physical_validation",), "ESTABLISHED"),
    (("diagnostics_complete",), 1),
    (("output_units", "power", "total_heat_w"), "J"),
    (("solve_result_count",), True),
    (("motor_result_count",), 0),
    (("outputs", "power", "total_electrical_power_w"), 0.0),
    (("outputs", "power", "all_motors_within_declared_limits"), 1),
    (("stages", 0, "inputs_sha256"), "0" * 64),
    (("transfers", 0, "from_field"), "outputs.invented"),
    (("outputs", "power", "motors", 0, "id"), "different-id"),
    (("outputs", "power", "motors", 0, "actual_motor_request", "operating_point",
      "angular_speed_rad_s"), 1.0),
    (("outputs", "power", "motors", 0, "actual_motor_result", "outputs", "current_a"), 0.0),
    (("outputs", "solve", "evaluation_count"), 0),
    (("outputs", "solve", "outputs", "candidates", 0, "request_sha256"), "0" * 64),
    (("outputs", "solve", "outputs", "outcome"), "EVALUATION_LIMIT"),
    (("outputs", "power"), None),
]


def mutate_path(actual, path, value):
    target = actual
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


@pytest.mark.parametrize("path,value", _FORGERIES)
def test_rehashed_point_forgery_rejected_without_models(monkeypatch, actual_point, path, value):
    supplied, baseline = actual_point
    forged = deepcopy(baseline)
    mutate_path(forged, path, value)
    reseal(forged["outputs"]["solve"])
    reseal(forged)
    forbidden = Mock(side_effect=AssertionError("model rerun"))
    monkeypatch.setattr(point.solve, "evaluate_tabulated_static_wrench_solve", forbidden)
    monkeypatch.setattr(point.solve._assembly, "evaluate_tabulated_rotor_assembly", forbidden)
    monkeypatch.setattr(point.solve._assembly, "evaluate_tabulated_hover_bemt", forbidden)
    monkeypatch.setattr(dc, "evaluate_dc_motor", forbidden)
    monkeypatch.setattr(dc, "_compute", forbidden)
    with pytest.raises(ValueError):
        energy._guard_point_success(forged, supplied)
    forbidden.assert_not_called()
    child = Mock(return_value=forged)
    monkeypatch.setattr(point, "evaluate_tabulated_solved_dc_power", child)
    root = {"evaluation": energy.EVALUATION, "segments": [
        {"id": "forged", "duration_s": 1, "power_request": deepcopy(supplied)}]}
    actual = energy.evaluate_tabulated_solved_dc_energy(root)
    assert actual["status"] == "EXECUTION_FAILED"
    assert actual["reasons"] == ["POINT_BOUNDARY_FAILED"]
    assert all(actual[key] == 0 for key in energy._COUNTS)
    assert all(actual[key] == {} for key in ("outputs", "output_units"))
    assert actual["stages"] == actual["transfers"] == []
    child.assert_called_once()
    forbidden.assert_not_called()


def test_full_success_guard_is_pure(monkeypatch, actual_point):
    supplied, actual = actual_point
    forbidden = Mock(side_effect=AssertionError("model rerun"))
    monkeypatch.setattr(point, "evaluate_tabulated_solved_dc_power", forbidden)
    monkeypatch.setattr(point.solve, "evaluate_tabulated_static_wrench_solve", forbidden)
    monkeypatch.setattr(point.solve._assembly, "evaluate_tabulated_rotor_assembly", forbidden)
    monkeypatch.setattr(point.solve._assembly, "evaluate_tabulated_hover_bemt", forbidden)
    monkeypatch.setattr(dc, "evaluate_dc_motor", forbidden)
    monkeypatch.setattr(dc, "_compute", forbidden)
    assert energy._guard_point_success(deepcopy(actual), supplied) is None
    forbidden.assert_not_called()


@pytest.mark.parametrize("failure", ["noncomputed", "exception", "malformed"])
def test_bad_second_point_preserves_only_guarded_prefix(monkeypatch, actual_point, failure):
    _, baseline = actual_point
    bad = deepcopy(baseline) if failure == "noncomputed" else {}
    if failure == "noncomputed":
        bad.update(status="MODEL_INAPPLICABLE", reasons=["private raw cause"])
        reseal(bad)
    child = Mock(side_effect=[deepcopy(baseline), RuntimeError("private raw cause")
                             if failure == "exception" else bad])
    monkeypatch.setattr(point, "evaluate_tabulated_solved_dc_power", child)
    supplied = request()
    actual = energy.evaluate_tabulated_solved_dc_energy(supplied)
    assert child.call_count == 2
    assert actual["reasons"] == ["POINT_BOUNDARY_FAILED"]
    assert actual["point_result_count"] == 1
    for key in energy._COUNTS.keys() - {"point_result_count"}:
        assert actual[key] == baseline[key]
    assert actual["diagnostics_complete"] is False
    assert actual["outputs"] == actual["output_units"] == {}
    assert actual["stages"] == actual["transfers"] == []
    assert "private raw cause" not in repr(actual)
    assert_seal(actual, supplied)


@pytest.mark.parametrize("fault", ["motor", "duplicate", "duration", "unknown", "unsupported"])
def test_whole_request_preflight_before_first_call(monkeypatch, fault):
    supplied = request()
    if fault == "motor":
        supplied["segments"][1]["power_request"]["motors"][0]["parameters"]["motor_constant_si"] = 0
    elif fault == "duplicate":
        supplied["segments"][1]["id"] = supplied["segments"][0]["id"]
    elif fault == "duration":
        supplied["segments"][1]["duration_s"] = float.fromhex("0x0.0000000000001p-1022")
    elif fault == "unknown":
        supplied["unknown"] = None
    else:
        supplied["evaluation"] = "unsupported"
    child = Mock(side_effect=AssertionError("unexpected call"))
    monkeypatch.setattr(point, "evaluate_tabulated_solved_dc_power", child)
    actual = energy.evaluate_tabulated_solved_dc_energy(supplied)
    assert actual["status"] == ("SOLVER_UNSUPPORTED" if fault == "unsupported" else "MODEL_INAPPLICABLE")
    assert all(actual[key] == 0 for key in energy._COUNTS)
    child.assert_not_called()


def test_aggregate_work_rejects_two_individually_legal_points(monkeypatch):
    supplied = request()
    for segment in supplied["segments"]:
        power = segment["power_request"]
        spec = power["solve"]
        rotor, bound, motor = (deepcopy(spec["assembly_template"]["rotors"][0]),
                               deepcopy(spec["rotor_speed_bounds"][0]), deepcopy(power["motors"][0]))
        spec["assembly_template"]["rotors"], spec["rotor_speed_bounds"], power["motors"] = [], [], []
        spec["max_evaluations"] = 64
        for i in range(8):
            r, b, m = deepcopy(rotor), deepcopy(bound), deepcopy(motor)
            r["id"] = b["id"] = m["id"] = f"rotor_{i}"
            r["rotor_template"]["annuli"] = 128
            spec["assembly_template"]["rotors"].append(r)
            spec["rotor_speed_bounds"].append(b)
            power["motors"].append(m)
        assert point._preflight(power) is None
        assert 64 * sum(r["rotor_template"]["annuli"] for r in spec["assembly_template"]["rotors"]) == 65536
    child = Mock(side_effect=AssertionError("unexpected call"))
    monkeypatch.setattr(point, "evaluate_tabulated_solved_dc_power", child)
    actual = energy.evaluate_tabulated_solved_dc_energy(supplied)
    assert actual["status"] == "MODEL_INAPPLICABLE"
    child.assert_not_called()


@pytest.mark.parametrize("exc", [KeyboardInterrupt, SystemExit])
def test_base_exception_propagates(monkeypatch, exc):
    supplied = request(1)
    child = Mock(side_effect=exc)
    monkeypatch.setattr(point, "evaluate_tabulated_solved_dc_power", child)
    with pytest.raises(exc):
        energy.evaluate_tabulated_solved_dc_energy(supplied)
    child.assert_called_once()


def test_post_guard_energy_failure_keeps_all_guarded_counts(monkeypatch, actual_point):
    _, baseline = actual_point
    supplied = request()
    child = Mock(return_value=deepcopy(baseline))
    monkeypatch.setattr(point, "evaluate_tabulated_solved_dc_power", child)
    monkeypatch.setattr(energy, "_energy_units", Mock(side_effect=ValueError("private energy cause")))
    actual = energy.evaluate_tabulated_solved_dc_energy(supplied)
    assert child.call_count == actual["point_result_count"] == 2
    for key in energy._COUNTS.keys() - {"point_result_count"}:
        assert actual[key] == 2 * baseline[key]
    assert actual["reasons"] == ["ENERGY_EXECUTION_FAILED"]
    assert actual["outputs"] == actual["output_units"] == {}
    assert actual["stages"] == actual["transfers"] == []
    assert actual["diagnostics_complete"] is False
    assert_seal(actual, supplied)


def test_catalog_fresh_nested_policy_and_units_without_calls(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("unexpected model call"))
    monkeypatch.setattr(point, "evaluate_tabulated_solved_dc_power", forbidden)
    first = energy.tabulated_solved_dc_energy_catalog()
    expected = deepcopy(first)
    first["limits"]["point_input_json"]["max_depth"] = 0
    first["point_catalog"]["limits"]["output_json"]["max_depth"] = 0
    first["output_field_units"]["points"]["row_variants"]["COMPUTED"]["actual_power_result"]["outputs"].clear()
    first["limitations"].clear()
    first["power_fields"].clear()
    assert energy.tabulated_solved_dc_energy_catalog() == expected
    forbidden.assert_not_called()


class HookDict(dict):
    def __deepcopy__(self, memo):
        raise AssertionError("foreign copy hook invoked")

    def __eq__(self, other):
        raise AssertionError("foreign equality hook invoked")


@pytest.mark.parametrize("fault", ["subclass", "depth"])
def test_child_walk_rejects_nested_foreign_or_deep_json_before_hooks(monkeypatch, actual_point, fault):
    _, baseline = actual_point
    supplied = request(1)
    forged = deepcopy(baseline)
    value = HookDict() if fault == "subclass" else None
    if fault == "depth":
        for _ in range(40):
            value = [value]
    forged["outputs"]["foreign"] = value
    child = Mock(return_value=forged)
    monkeypatch.setattr(point, "evaluate_tabulated_solved_dc_power", child)
    actual = energy.evaluate_tabulated_solved_dc_energy(supplied)
    assert actual["reasons"] == ["POINT_BOUNDARY_FAILED"]
    assert actual["point_result_count"] == 0
    assert actual["outputs"] == {}
    child.assert_called_once()


@pytest.fixture(scope="module")
def actual_unmet_point():
    supplied = point_request()
    supplied["solve"]["max_evaluations"] = 2
    supplied["solve"]["required_net_force_body_n"][0] = 100.0
    actual = point.evaluate_tabulated_solved_dc_power(deepcopy(supplied))
    assert actual["outputs"]["power_state"] == "NOT_RUN_RESIDUAL_UNMET"
    return supplied, actual


@pytest.mark.parametrize("fault", ["state", "power", "count", "stage", "transfers", "units"])
def test_rehashed_unmet_point_cannot_claim_met_or_partial_power(monkeypatch, actual_unmet_point, fault):
    supplied, baseline = actual_unmet_point
    forged = deepcopy(baseline)
    if fault == "state":
        forged["outputs"]["power_state"] = "COMPUTED"
    elif fault == "power":
        forged["outputs"]["power"] = {}
    elif fault == "count":
        forged["motor_result_count"] = 1
    elif fault == "stage":
        forged["stages"] = []
    elif fault == "transfers":
        forged["transfers"] = [{}]
    else:
        forged["output_units"]["power"] = "W"
    reseal(forged)
    forbidden = Mock(side_effect=AssertionError("unexpected model call"))
    monkeypatch.setattr(point.solve, "evaluate_tabulated_static_wrench_solve", forbidden)
    monkeypatch.setattr(dc, "evaluate_dc_motor", forbidden)
    monkeypatch.setattr(dc, "_compute", forbidden)
    with pytest.raises(ValueError):
        energy._guard_point_success(forged, supplied)
    child = Mock(return_value=forged)
    monkeypatch.setattr(point, "evaluate_tabulated_solved_dc_power", child)
    root = {"evaluation": energy.EVALUATION, "segments": [
        {"id": "unmet", "duration_s": 1, "power_request": deepcopy(supplied)}]}
    actual = energy.evaluate_tabulated_solved_dc_energy(root)
    assert actual["reasons"] == ["POINT_BOUNDARY_FAILED"]
    assert actual["point_result_count"] == 0
    assert actual["outputs"] == {}
    forbidden.assert_not_called()


@pytest.mark.parametrize("count", range(1, 9))
def test_actual_one_through_eight_ordered_points(monkeypatch, count):
    supplied = request(count)
    child = Mock(wraps=point.evaluate_tabulated_solved_dc_power)
    monkeypatch.setattr(point, "evaluate_tabulated_solved_dc_power", child)
    actual = energy.evaluate_tabulated_solved_dc_energy(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL", actual["reasons"]
    assert actual["outputs"]["energy_state"] == "COMPUTED"
    assert actual["point_result_count"] == child.call_count == count
    assert [row["segment_id"] for row in actual["outputs"]["points"]] == [
        segment["id"] for segment in supplied["segments"]]
    integrated = actual["outputs"]["energy"]
    assert integrated["elapsed_s"] == sum(range(1, count + 1))
    assert len(integrated["segments"]) == len(actual["output_units"]["points"]) == count
    assert len(actual["transfers"]) == 9 * count
    assert_seal(actual, supplied)


def test_actual_zero_energy_increments_may_keep_prefix_unchanged(monkeypatch):
    supplied = request()
    for segment in supplied["segments"]:
        segment["power_request"]["auxiliary"]["power_w"] = 0
        for motor in segment["power_request"]["motors"]:
            motor["heat_fraction_of_motor_loss"] = 0
    child = Mock(wraps=point.evaluate_tabulated_solved_dc_power)
    monkeypatch.setattr(point, "evaluate_tabulated_solved_dc_power", child)
    actual = energy.evaluate_tabulated_solved_dc_energy(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL", actual["reasons"]
    assert actual["point_result_count"] == child.call_count == 2
    integrated = actual["outputs"]["energy"]
    for key in ("allocated_motor_heat", "auxiliary_electrical", "auxiliary_heat", "total_allocated_heat"):
        assert integrated["totals_j"][key] == integrated["totals_wh"][key] == 0
        for row in integrated["segments"]:
            assert row["energy_j"][key] == row["cumulative_energy_j"][key] == 0
    assert_seal(actual, supplied)


@pytest.mark.parametrize("fault", ["duration", "energy"])
def test_actual_positive_increment_absorption_fails_only_after_all_points(monkeypatch, fault):
    supplied = request()
    if fault == "duration":
        supplied["segments"][0]["duration_s"] = 2**54
        supplied["segments"][1]["duration_s"] = 1
    else:
        for segment in supplied["segments"]:
            segment["duration_s"] = 1
            segment["power_request"]["auxiliary"]["heat_fraction"] = 0
        supplied["segments"][0]["power_request"]["auxiliary"]["power_w"] = 2**54
        supplied["segments"][1]["power_request"]["auxiliary"]["power_w"] = 1
    direct = [point.evaluate_tabulated_solved_dc_power(deepcopy(s["power_request"]))
              for s in supplied["segments"]]
    assert all(p["status"] == "COMPUTED_EXPERIMENTAL" for p in direct)
    child = Mock(wraps=point.evaluate_tabulated_solved_dc_power)
    monkeypatch.setattr(point, "evaluate_tabulated_solved_dc_power", child)
    actual = energy.evaluate_tabulated_solved_dc_energy(supplied)
    assert actual["status"] == "EXECUTION_FAILED"
    assert actual["reasons"] == ["ENERGY_EXECUTION_FAILED"]
    assert actual["point_result_count"] == child.call_count == 2
    for key in energy._COUNTS.keys() - {"point_result_count"}:
        assert actual[key] == sum(p[key] for p in direct)
    assert actual["outputs"] == actual["output_units"] == {}
    assert actual["stages"] == actual["transfers"] == []
    assert actual["diagnostics_complete"] is False
    assert_seal(actual, supplied)
