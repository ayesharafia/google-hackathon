"""Focused actual-component checks for the coupled solve/DC bridge."""

import math
from copy import deepcopy
from unittest.mock import Mock

import pytest

from physimesh.drone import dc_motor as dc
from physimesh.drone import tabulated_hover_bemt_request as forward
from physimesh.drone import tabulated_rotor_assembly as assembly
from physimesh.drone import tabulated_solved_dc_power as bridge
from physimesh.drone import tabulated_static_wrench_solve as solve
from physimesh.drone import tabulated_target_dc_power as power
from physimesh.drone.provenance import sha256_record

from .test_tabulated_static_wrench_solve import request as solve_request
from .test_tabulated_target_dc_power import request as power_request


def request():
    supplied = power_request()
    return {"evaluation": bridge.EVALUATION, "solve": solve_request(),
            "motors": supplied["motors"], "auxiliary": supplied["auxiliary"]}


def spies(monkeypatch):
    calls = {}
    for key, module, name in (
        ("solve", solve, "evaluate_tabulated_static_wrench_solve"),
        ("assembly", assembly, "evaluate_tabulated_rotor_assembly"),
        ("air", assembly, "reference_air_properties"),
        ("forward", assembly, "evaluate_tabulated_hover_bemt"),
        ("core", forward, "solve_tabulated_hover"),
        ("motor", dc, "evaluate_dc_motor"), ("compute", dc, "_compute"),
        ("solve_guard", bridge, "_guard_solve_success"),
        ("assembly_guard", solve, "_guard_assembly_success"),
        ("motor_guard", power, "_validate_motor"),
    ):
        calls[key] = Mock(wraps=getattr(module, name))
        monkeypatch.setattr(module, name, calls[key])
    return calls


def assert_seal(result, supplied):
    assert result["request_sha256"] == sha256_record(supplied)
    assert result["evaluation_sha256"] == sha256_record({
        k: v for k, v in result.items() if k != "evaluation_sha256"})


def test_actual_met_chain_preserves_full_results_and_scalar_bindings(monkeypatch):
    supplied = request()
    original = deepcopy(supplied)
    direct = solve.evaluate_tabulated_static_wrench_solve(deepcopy(supplied["solve"]))
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    assert direct["outputs"]["outcome"] == "RESIDUAL_MET"
    rotor_rows = direct["outputs"]["actual_assembly_result"]["outputs"]["rotors"]
    injected, actual_motors = [], []
    for entry, row in zip(supplied["motors"], rotor_rows, strict=True):
        actual_request = {
            "evaluation": dc.EVALUATION, "parameters": deepcopy(entry["parameters"]),
            "declared_limits": deepcopy(entry["declared_limits"]),
            "operating_point": {
                "angular_speed_rad_s": row["actual_forward_request"]["angular_speed_rad_s"],
                "shaft_torque_nm": row["actual_forward_result"]["outputs"]["shaft_torque_nm"],
            },
        }
        injected.append(actual_request)
        actual_motors.append(dc.evaluate_dc_motor(deepcopy(actual_request)))
    calls = spies(monkeypatch)
    result = bridge.evaluate_tabulated_solved_dc_power(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL", result["reasons"]
    assert result["diagnostics_complete"] is True
    assert result["outputs"]["power_state"] == "COMPUTED"
    assert supplied == original
    assert result["outputs"]["solve"] == direct
    assert result["solve_result_count"] == 1
    n, count = len(rotor_rows), direct["evaluation_count"]
    assert result["assembly_evaluation_count"] == count
    assert result["forward_evaluation_count"] == direct["rotor_evaluation_count"] == count * n
    assert result["motor_result_count"] == n
    for key, expected in (("solve", 1), ("assembly", count), ("air", count),
                          ("forward", count * n), ("core", count * n),
                          ("motor", n), ("compute", n), ("solve_guard", 1),
                          ("assembly_guard", count + 1), ("motor_guard", n)):
        assert calls[key].call_count == expected, key
    calls["solve"].assert_called_once_with(supplied["solve"])
    assert result["stages"][0] == {
        "stage": "solve", "inputs": supplied["solve"],
        "inputs_sha256": sha256_record(supplied["solve"]), "result_sha256": sha256_record(direct),
    }
    assert len(result["stages"]) == n + 1
    assert len(result["transfers"]) == 2 * n
    rows = result["outputs"]["power"]["motors"]
    for i, (row, actual_request, actual) in enumerate(zip(rows, injected, actual_motors, strict=True)):
        assert actual["status"] == "COMPUTED_EXPERIMENTAL"
        assert row["id"] == supplied["motors"][i]["id"]
        assert row["actual_motor_request"] == actual_request
        assert row["actual_motor_result"] == actual
        assert "evaluation_sha256" not in row["actual_motor_result"]
        assert calls["motor"].call_args_list[i].args == (actual_request,)
        assert math.isclose(actual["outputs"]["shaft_power_w"],
                            rotor_rows[i]["actual_forward_result"]["outputs"]["shaft_power_w"],
                            rel_tol=1e-12, abs_tol=1e-12)
        stage = "motor:" + row["id"]
        assert result["stages"][i + 1] == {
            "stage": stage, "inputs": actual_request, "inputs_sha256": sha256_record(actual_request),
            "result_sha256": sha256_record(actual),
        }
        base = f"outputs.actual_assembly_result.outputs.rotors[{i}]."
        for j, (field, source, unit) in enumerate((
            ("angular_speed_rad_s", "actual_forward_request.angular_speed_rad_s", "rad/s"),
            ("shaft_torque_nm", "actual_forward_result.outputs.shaft_torque_nm", "N*m"),
        )):
            assert result["transfers"][2 * i + j] == {
                "from_stage": "solve", "from_field": base + source,
                "to_stage": stage, "to_field": "operating_point." + field,
                "value": actual_request["operating_point"][field], "unit": unit,
                "producer_result_sha256": sha256_record(direct),
                "consumer_request_sha256": sha256_record(actual_request),
            }
        loss = actual["outputs"]["total_loss_w"]
        assert row["allocated_heat_w"] == loss * supplied["motors"][i]["heat_fraction_of_motor_loss"]
        assert row["unallocated_loss_w"] == loss - row["allocated_heat_w"]
    totals = result["outputs"]["power"]
    expected = {
        "total_shaft_power_w": math.fsum(r["outputs"]["shaft_power_w"] for r in actual_motors),
        "total_motor_electrical_power_w": math.fsum(r["outputs"]["electrical_power_w"] for r in actual_motors),
        "total_motor_loss_w": math.fsum(r["outputs"]["total_loss_w"] for r in actual_motors),
        "total_allocated_motor_heat_w": math.fsum(r["allocated_heat_w"] for r in rows),
        "total_unallocated_motor_loss_w": math.fsum(r["unallocated_loss_w"] for r in rows),
        "auxiliary_electrical_power_w": supplied["auxiliary"]["power_w"],
        "auxiliary_heat_w": supplied["auxiliary"]["power_w"] * supplied["auxiliary"]["heat_fraction"],
    }
    expected["total_electrical_power_w"] = math.fsum([
        expected["total_motor_electrical_power_w"], expected["auxiliary_electrical_power_w"]])
    expected["total_heat_w"] = math.fsum([
        expected["total_allocated_motor_heat_w"], expected["auxiliary_heat_w"]])
    assert len(expected) == 9
    assert totals.keys() == expected.keys() | {"motors", "all_motors_within_declared_limits"}
    for name, value in expected.items():
        assert totals[name] == value
    assert totals["all_motors_within_declared_limits"] is True
    catalog = bridge.tabulated_solved_dc_power_catalog()
    assert result["output_units"] == catalog["output_field_units"]
    assert result["output_units"]["solve"] == {"outputs": direct["output_units"]}
    assert result["output_units"]["power"]["motors"]["actual_motor_result"] == {
        "outputs": actual_motors[0]["output_units"]}
    assert_seal(result, supplied)


def test_actual_unmet_budget_retains_solve_and_never_calls_dc(monkeypatch):
    supplied = request()
    supplied["solve"]["max_evaluations"] = 2
    supplied["solve"]["required_net_force_body_n"][0] = 100.0
    calls = spies(monkeypatch)
    result = bridge.evaluate_tabulated_solved_dc_power(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL", result["reasons"]
    assert result["diagnostics_complete"] is True
    assert result["outputs"].keys() == {"solve", "power_state", "power"}
    assert result["outputs"]["power_state"] == "NOT_RUN_RESIDUAL_UNMET"
    assert result["outputs"]["power"] is None
    retained = result["outputs"]["solve"]
    assert retained["outputs"]["outcome"] == "EVALUATION_LIMIT"
    assert result["solve_result_count"] == 1
    assert result["assembly_evaluation_count"] == retained["evaluation_count"] == 2
    assert result["forward_evaluation_count"] == retained["rotor_evaluation_count"] == 4
    assert result["motor_result_count"] == 0
    for key, count in (("solve", 1), ("assembly", 2), ("air", 2), ("forward", 4), ("core", 4)):
        assert calls[key].call_count == count
    for key in ("motor", "compute", "motor_guard"):
        calls[key].assert_not_called()
    assert result["transfers"] == []
    assert result["stages"] == [{
        "stage": "solve", "inputs": supplied["solve"],
        "inputs_sha256": sha256_record(supplied["solve"]), "result_sha256": sha256_record(retained),
    }]
    assert result["output_units"] == bridge.tabulated_solved_dc_power_catalog()[
        "output_field_units_residual_unmet"]
    assert result["output_units"]["power"] == "not_applicable"
    assert_seal(result, supplied)


def test_actual_exceeded_limits_stay_computed_and_heat_endpoints_count_aux_once(monkeypatch):
    supplied = request()
    for entry, fraction in zip(supplied["motors"], (0.0, 1.0), strict=True):
        entry["heat_fraction_of_motor_loss"] = fraction
        for name in power._DECLARED:
            if name != "limit_source":
                entry["declared_limits"][name] = 1e-12
    calls = spies(monkeypatch)
    result = bridge.evaluate_tabulated_solved_dc_power(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL", result["reasons"]
    assert result["outputs"]["power_state"] == "COMPUTED"
    assert result["motor_result_count"] == calls["motor"].call_count == calls["compute"].call_count == 2
    totals = result["outputs"]["power"]
    assert totals["all_motors_within_declared_limits"] is False
    rows = totals["motors"]
    for row in rows:
        values = row["actual_motor_result"]["outputs"]
        assert values["declared_limit_status"] == "EXCEEDS_DECLARED_LIMITS"
        assert all(value is False for value in values["limit_checks"].values())
    first_loss, second_loss = [r["actual_motor_result"]["outputs"]["total_loss_w"] for r in rows]
    assert rows[0]["allocated_heat_w"] == 0.0
    assert rows[0]["unallocated_loss_w"] == first_loss
    assert rows[1]["allocated_heat_w"] == second_loss
    assert rows[1]["unallocated_loss_w"] == 0.0
    assert totals["total_allocated_motor_heat_w"] == second_loss
    assert totals["total_unallocated_motor_loss_w"] == first_loss
    assert totals["auxiliary_electrical_power_w"] == 10.0
    assert totals["auxiliary_heat_w"] == 2.5
    assert totals["total_electrical_power_w"] == math.fsum([totals["total_motor_electrical_power_w"], 10.0])
    assert totals["total_heat_w"] == math.fsum([second_loss, 2.5])
    assert result["aircraft_status"] is result["feasibility"] is None
    assert_seal(result, supplied)


# Boundary cases use actual producer results; mutations test pure admission only.
def change(value, path, replacement):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


def reseal(value):
    value["evaluation_sha256"] = sha256_record({
        k: v for k, v in value.items() if k != "evaluation_sha256"})


@pytest.fixture(scope="module")
def actual_pair():
    supplied = request()
    actual = solve.evaluate_tabulated_static_wrench_solve(deepcopy(supplied["solve"]))
    assert actual["status"] == "COMPUTED_EXPERIMENTAL"
    assert len(actual["outputs"]["candidates"]) > 1
    return supplied, actual


@pytest.mark.parametrize(("path", "value"), [
    (("motors", 0, "id"), "wrong"), (("motors", 1, "id"), "air"),
    (("motors", 1, "parameters", "motor_constant_si"), 0.0),
    (("motors", 1, "parameters", "terminal_resistance_ohm"), -1.0),
    (("motors", 1, "parameters", "zero_torque_current_a"), True),
    (("motors", 1, "parameters", "parameter_source"), " "),
    (("motors", 1, "parameters", "applicability_declaration"), "qualified"),
    *[(("motors", 1, "declared_limits", key), 0.0) for key in power._DECLARED if key != "limit_source"],
    (("motors", 1, "declared_limits", "limit_source"), ""),
    (("motors", 1, "heat_fraction_of_motor_loss"), 1.1),
    (("motors", 1, "heat_source"), ""), (("motors", 1, "operating_point"), {}),
    (("auxiliary", "power_w"), -1.0), (("auxiliary", "heat_fraction"), True),
    (("auxiliary", "source"), " "), (("auxiliary", "extra"), None),
])
def test_malformed_preflight_calls_no_models(actual_pair, monkeypatch, path, value):
    supplied = deepcopy(actual_pair[0])
    change(supplied, path, value)
    calls = spies(monkeypatch)
    result = bridge.evaluate_tabulated_solved_dc_power(supplied)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["request_sha256"] is result["evaluation_sha256"] is None
    for call in calls.values():
        call.assert_not_called()


@pytest.mark.parametrize(("path", "value"), [
    (("evaluation_count",), True), (("rotor_evaluation_count",), True),
    (("physical_validation",), "ESTABLISHED"), (("limits", "input_json", "max_depth"), 99),
    (("output_units", "outcome"), "N"), (("request_sha256",), "0" * 64),
    (("outputs", "candidates", 0, "angular_speeds_rad_s", 0), 301.0),
    (("outputs", "candidates", 0, "request_sha256"), "0" * 64),
    (("outputs", "candidates", 0, "result_sha256"), "z" * 64),
    (("outputs", "candidates", 0, "force_residual_n", 0), 1.0),
    (("outputs", "candidates", 0, "scaled_residual", 0), 1.0),
    (("outputs", "candidates", 0, "max_scaled_residual"), 0.0),
    (("outputs", "candidates", 0, "net_force_body_n", 0), 0),
    (("outputs", "selected_index"), True), (("outputs", "outcome"), "SOLVER_STOPPED"),
    (("outputs", "actual_assembly_request", "rotors", 0, "rotor_template", "angular_speed_rad_s"), 250.0),
    (("outputs", "actual_assembly_result", "outputs", "rotors", 0, "force_body_n", 2), 0.0),
    (("outputs", "actual_assembly_result", "outputs", "rotors", 0,
      "actual_forward_result", "outputs", "shaft_torque_nm"), 0.0),
    (("evaluation_sha256",), "0" * 64),
])
def test_pure_guard_rejects_corruption(actual_pair, monkeypatch, path, value):
    supplied, authentic = actual_pair
    corrupted = deepcopy(authentic)
    change(corrupted, path, value)
    if path[:2] == ("outputs", "actual_assembly_result"):
        reseal(corrupted["outputs"]["actual_assembly_result"])
    if path != ("evaluation_sha256",):
        reseal(corrupted)
    calls = spies(monkeypatch)
    for key in ("solve", "assembly", "air", "forward", "core", "motor", "compute"):
        calls[key].side_effect = AssertionError("model rerun")
    assert bridge._guard_solve_success(authentic, supplied["solve"]) is None
    with pytest.raises(ValueError):
        bridge._guard_solve_success(corrupted, supplied["solve"])
    for key in ("solve", "assembly", "air", "forward", "core", "motor", "compute"):
        calls[key].assert_not_called()


def test_nonselected_digest_is_format_only(actual_pair, monkeypatch):
    supplied, authentic = actual_pair
    retained = deepcopy(authentic)
    nonselected = next(i for i in range(len(retained["outputs"]["candidates"]))
                       if i != retained["outputs"]["selected_index"])
    retained["outputs"]["candidates"][nonselected]["result_sha256"] = "0" * 64
    reseal(retained)
    calls = spies(monkeypatch)
    assert bridge._guard_solve_success(retained, supplied["solve"]) is None
    for key in ("solve", "assembly", "air", "forward", "core", "motor", "compute"):
        calls[key].assert_not_called()


@pytest.mark.parametrize("boundary", ["solve", "motor"])
@pytest.mark.parametrize("fault", ["exception", "noncomputed", "malformed"])
@pytest.mark.parametrize("prior", [0, 1])
def test_atomic_boundary_failures(actual_pair, monkeypatch, boundary, fault, prior):
    supplied, actual = actual_pair
    original = dc.evaluate_dc_motor
    calls = spies(monkeypatch)
    attempted = 0

    def faulty(actual_request):
        nonlocal attempted
        attempted += 1
        if boundary == "motor" and attempted <= prior:
            return original(actual_request)
        if fault == "exception":
            raise RuntimeError("PRIVATE CHILD CAUSE")
        return {"status": "MODEL_INAPPLICABLE" if fault == "noncomputed" else "COMPUTED_EXPERIMENTAL",
                "reasons": ["PRIVATE CHILD CAUSE"], "evaluation_count": 64}

    calls[boundary].side_effect = faulty
    result = bridge.evaluate_tabulated_solved_dc_power(deepcopy(supplied))
    assert result["status"] == "EXECUTION_FAILED"
    assert result["reasons"] == ["SOLVE_BOUNDARY_FAILED" if boundary == "solve" else "MOTOR_BOUNDARY_FAILED"]
    accepted = int(boundary == "motor")
    assert result["solve_result_count"] == accepted
    assert result["assembly_evaluation_count"] == accepted * actual["evaluation_count"]
    assert result["forward_evaluation_count"] == accepted * actual["rotor_evaluation_count"]
    assert result["motor_result_count"] == (prior if accepted else 0)
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == result["transfers"] == []
    assert result["diagnostics_complete"] is False
    assert "PRIVATE CHILD CAUSE" not in str(result)
    assert attempted == (prior + 1 if accepted else 1)
    if not accepted:
        calls["motor"].assert_not_called()
    assert_seal(result, supplied)


@pytest.mark.parametrize("boundary", ["solve", "motor"])
def test_baseexception_propagates(actual_pair, monkeypatch, boundary):
    calls = spies(monkeypatch)
    calls[boundary].side_effect = KeyboardInterrupt("stop")
    with pytest.raises(KeyboardInterrupt):
        bridge.evaluate_tabulated_solved_dc_power(deepcopy(actual_pair[0]))


def test_snapshot_walk_blocks_foreign_hooks_and_catalog_is_fresh(monkeypatch):
    class Foreign:
        def __deepcopy__(self, memo):
            raise AssertionError("copy hook")

        def __eq__(self, other):
            raise AssertionError("equality hook")

    for limit in ("input_json", "solve_output_json", "motor_output_json"):
        with pytest.raises(ValueError):
            bridge._snapshot({"late": [0.0, Foreign()]}, limit)
    calls = spies(monkeypatch)
    first = bridge.tabulated_solved_dc_power_catalog()
    pristine = deepcopy(first)
    first["solve_catalog"]["limits"]["input_json"]["max_depth"] = 99
    first["output_field_units"]["power"]["motors"]["actual_motor_result"]["outputs"].clear()
    first["limits"]["motor_input_json"].clear()
    assert bridge.tabulated_solved_dc_power_catalog() == pristine
    for call in calls.values():
        call.assert_not_called()
