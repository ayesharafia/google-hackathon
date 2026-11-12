"""Actual-component smoke checks for the prescribed target DC power bridge."""

import math
import sys
from copy import deepcopy
from unittest.mock import Mock

import pytest

from physimesh.drone import dc_motor as dc
from physimesh.drone import tabulated_hover_bemt_request as forward
from physimesh.drone import tabulated_hover_thrust_target as inverse
from physimesh.drone import tabulated_target_dc_power as bridge
from physimesh.drone import tabulated_thrust_target_assembly as assembly
from physimesh.drone.provenance import sha256_record


def assembly_request():
    """Caller-prescribed fixed 100 N; no forward model generates this target."""
    template = {
        "evaluation": inverse.EVALUATION,
        "rotor_template": {
            "evaluation": forward.EVALUATION, "radius_m": 1.0, "blade_count": 2,
            "root_cutout_m": 0.2, "annuli": 12, "lift_curve_slope_per_rad": 5.7,
            "profile_drag_coefficient": 0.012,
            "stations": [
                {"radius_m": 0.0, "chord_m": 0.08, "blade_angle_rad": 0.12},
                {"radius_m": 0.5, "chord_m": 0.06, "blade_angle_rad": 0.10},
                {"radius_m": 1.0, "chord_m": 0.04, "blade_angle_rad": 0.08},
            ],
            "geometry_source": "explicit synthetic variable chord and twist",
            "geometry_kind": "synthetic", "uncertainty_status": "unknown",
        },
        "target_thrust_n": 100.0, "angular_speed_bracket_rad_s": [50.0, 300.0],
        "absolute_thrust_tolerance_n": 0.001, "max_evaluations": 32,
    }
    return {
        "evaluation": assembly.EVALUATION,
        "air": {"altitude_m": 1000.0, "altitude_kind": "geometric"},
        "rotors": [
            {"id": "air", "target_template": deepcopy(template),
             "center_body_m": [1.0, 0.0, 0.0], "axis_body": [0.0, 0.0, 1.0], "rotation_sign": 1},
            {"id": "left", "target_template": deepcopy(template),
             "center_body_m": [-1.0, 0.0, 0.0], "axis_body": [0.0, 0.0, 1.0], "rotation_sign": -1},
        ],
        "mass_kg": 3.0, "cg_body_m": [0.0, 0.0, 0.0],
        "gravity_direction_body": [0.0, 0.0, -1.0], "property_source": "unverified explicit fixture",
    }

def request():
    supplied = assembly_request()
    return {
        "evaluation": bridge.EVALUATION, "assembly": supplied,
        "motors": [{
            "id": rotor["id"],
            "parameters": {
                "motor_constant_si": 0.1, "terminal_resistance_ohm": 0.2,
                "zero_torque_current_a": 0.5, "parameter_source": "synthetic, not measured",
                "applicability_declaration": "constant_parameter_dc_equivalent_only",
            },
            "declared_limits": {
                "maximum_current_a": 10000.0, "maximum_terminal_voltage_v": 10000.0,
                "maximum_angular_speed_rad_s": 10000.0, "maximum_shaft_torque_nm": 10000.0,
                "limit_source": "synthetic generous declarations, not ratings",
            },
            "heat_fraction_of_motor_loss": 0.5, "heat_source": "synthetic allocation",
        } for rotor in supplied["rotors"]],
        "auxiliary": {"power_w": 10.0, "heat_fraction": 0.25, "source": "synthetic auxiliary"},
    }


def direct_components(supplied):
    actual = assembly.evaluate_tabulated_thrust_target_assembly(deepcopy(supplied["assembly"]))
    assert actual["status"] == "COMPUTED_EXPERIMENTAL"
    motor_requests, results = [], []
    for motor, rotor in zip(supplied["motors"], actual["outputs"]["rotors"], strict=True):
        selected = rotor["actual_target_result"]["outputs"]
        injected = {
            "evaluation": dc.EVALUATION, "parameters": deepcopy(motor["parameters"]),
            "declared_limits": deepcopy(motor["declared_limits"]),
            "operating_point": {
                "angular_speed_rad_s": selected["actual_forward_request"]["angular_speed_rad_s"],
                "shaft_torque_nm": selected["actual_forward_result"]["outputs"]["shaft_torque_nm"],
            },
        }
        motor_requests.append(injected)
        results.append(dc.evaluate_dc_motor(deepcopy(injected)))
    return actual, motor_requests, results


def install_spies(monkeypatch):
    calls = {}
    for key, module, name in (
        ("assembly", assembly, "evaluate_tabulated_thrust_target_assembly"),
        ("air", assembly, "reference_air_properties"),
        ("inverse", assembly, "evaluate_tabulated_hover_thrust_target"),
        ("trials", inverse, "evaluate_tabulated_hover_bemt"),
        ("kernel", forward, "solve_tabulated_hover"),
        ("motor", dc, "evaluate_dc_motor"), ("compute", dc, "_compute"),
        ("assembly_guard", bridge, "validate_tabulated_thrust_target_assembly_result"),
        ("motor_guard", bridge, "_validate_motor"),
    ):
        calls[key] = Mock(wraps=getattr(module, name))
        monkeypatch.setattr(module, name, calls[key])
    return calls


def assert_actual(supplied, result, direct, motor_requests, motor_results, calls):
    assert result["status"] == "COMPUTED_EXPERIMENTAL", result["reasons"]
    assert result["diagnostics_complete"] is True
    assert result["request_sha256"] == sha256_record(supplied)
    assert result["evaluation_sha256"] == sha256_record({
        k: v for k, v in result.items() if k != "evaluation_sha256"})
    assert result["assembly_inverse_result_count"] == 2
    assert result["forward_evaluation_count"] == direct["forward_evaluation_count"]
    assert result["motor_result_count"] == 2
    assert result["outputs"]["assembly"] == direct
    assert sha256_record(result["outputs"]["assembly"]) == sha256_record(direct)
    assert result["output_units"]["assembly"] == {"outputs": direct["output_units"]}
    assert result["stages"][0] == {
        "stage": "assembly", "inputs": supplied["assembly"],
        "inputs_sha256": direct["request_sha256"], "result_sha256": sha256_record(direct),
    }
    power = result["outputs"]["power"]
    assert len(power["motors"]) == len(motor_results) == 2
    assert len(result["stages"]) == 3
    assert len(result["transfers"]) == 4
    for i, (row, injected, actual_motor) in enumerate(zip(
        power["motors"], motor_requests, motor_results, strict=True
    )):
        assert actual_motor["status"] == "COMPUTED_EXPERIMENTAL"
        assert row["id"] == supplied["motors"][i]["id"]
        assert row["actual_motor_request"] == injected
        assert row["actual_motor_result"] == actual_motor
        assert sha256_record(row["actual_motor_result"]) == sha256_record(actual_motor)
        assert "evaluation_sha256" not in row["actual_motor_result"]
        assert row.keys() == {"id", "actual_motor_request", "actual_motor_result",
                              "allocated_heat_w", "unallocated_loss_w"}
        assert injected["operating_point"]["angular_speed_rad_s"] > 0
        assert injected["operating_point"]["shaft_torque_nm"] >= 0
        stage = "motor:" + row["id"]
        assert result["stages"][i + 1] == {
            "stage": stage, "inputs": injected, "inputs_sha256": sha256_record(injected),
            "result_sha256": sha256_record(actual_motor),
        }
        base = f"outputs.rotors[{i}].actual_target_result.outputs."
        for j, (field, producer, unit) in enumerate((
            ("angular_speed_rad_s", "actual_forward_request.angular_speed_rad_s", "rad/s"),
            ("shaft_torque_nm", "actual_forward_result.outputs.shaft_torque_nm", "N*m"),
        )):
            assert result["transfers"][2 * i + j] == {
                "from_stage": "assembly", "from_field": base + producer,
                "to_stage": stage, "to_field": "operating_point." + field,
                "value": injected["operating_point"][field], "unit": unit,
                "producer_result_sha256": sha256_record(direct),
                "consumer_request_sha256": sha256_record(injected),
            }
        motor_units = result["output_units"]["power"]["motors"]
        assert motor_units["actual_motor_result"] == {"outputs": actual_motor["output_units"]}
        assert motor_units["actual_motor_request"].keys() == injected.keys()
        for section in ("parameters", "declared_limits", "operating_point"):
            assert motor_units["actual_motor_request"][section].keys() == injected[section].keys()
        loss = actual_motor["outputs"]["total_loss_w"]
        assert row["allocated_heat_w"] == loss * supplied["motors"][i]["heat_fraction_of_motor_loss"]
        assert row["unallocated_loss_w"] == loss - row["allocated_heat_w"]
        assert bridge._validate_motor(row["actual_motor_result"], injected) is None
    for total, field in (
        ("total_shaft_power_w", "shaft_power_w"),
        ("total_motor_electrical_power_w", "electrical_power_w"),
        ("total_motor_loss_w", "total_loss_w"),
    ):
        assert power[total] == math.fsum(m["outputs"][field] for m in motor_results)
    assert power["total_allocated_motor_heat_w"] == math.fsum(r["allocated_heat_w"] for r in power["motors"])
    assert power["total_unallocated_motor_loss_w"] == math.fsum(r["unallocated_loss_w"] for r in power["motors"])
    assert power["auxiliary_electrical_power_w"] == supplied["auxiliary"]["power_w"]
    assert power["auxiliary_heat_w"] == supplied["auxiliary"]["power_w"] * supplied["auxiliary"]["heat_fraction"]
    assert power["total_electrical_power_w"] == power["total_motor_electrical_power_w"] + power["auxiliary_electrical_power_w"]
    assert power["total_heat_w"] == power["total_allocated_motor_heat_w"] + power["auxiliary_heat_w"]
    for key, expected in (("assembly", 1), ("air", 1), ("inverse", 2),
                          ("trials", direct["forward_evaluation_count"]),
                          ("kernel", direct["forward_evaluation_count"]),
                          ("motor", 2), ("compute", 2), ("assembly_guard", 1), ("motor_guard", 4)):
        assert calls[key].call_count == expected, key


def test_actual_two_rotor_power_heat_and_full_component_preservation(monkeypatch):
    supplied = request()
    original = deepcopy(supplied)
    direct, injected, motors = direct_components(supplied)
    calls = install_spies(monkeypatch)
    result = bridge.evaluate_tabulated_target_dc_power(supplied)
    assert_actual(supplied, result, direct, injected, motors, calls)
    assert supplied == original
    power = result["outputs"]["power"]
    assert power["all_motors_within_declared_limits"] is True
    assert power["auxiliary_heat_w"] == 2.5
    assert power["total_heat_w"] == power["total_motor_loss_w"] * 0.5 + 2.5
    assert power["total_heat_w"] < power["total_electrical_power_w"]


@pytest.mark.parametrize("integer_parameters", [False, True])
def test_actual_ideal_zero_heat_and_declared_exceedance_remains_computed(monkeypatch, integer_parameters):
    supplied = request()
    for motor in supplied["motors"]:
        motor["parameters"].update(
            motor_constant_si=1 if integer_parameters else 1.0,
            terminal_resistance_ohm=0 if integer_parameters else 0.0,
            zero_torque_current_a=0 if integer_parameters else 0.0,
        )
        motor["heat_fraction_of_motor_loss"] = 0
        for field in motor["declared_limits"]:
            if field != "limit_source":
                motor["declared_limits"][field] = 1 if integer_parameters else 1.0
    supplied["auxiliary"].update(power_w=0, heat_fraction=0)
    direct, injected, motors = direct_components(supplied)
    calls = install_spies(monkeypatch)
    result = bridge.evaluate_tabulated_target_dc_power(supplied)
    assert_actual(supplied, result, direct, injected, motors, calls)
    power = result["outputs"]["power"]
    assert power["all_motors_within_declared_limits"] is False
    assert power["total_motor_loss_w"] == power["total_heat_w"] == 0
    assert power["total_electrical_power_w"] == power["total_shaft_power_w"]
    for row in power["motors"]:
        values = row["actual_motor_result"]["outputs"]
        assert values["efficiency"] == 1.0
        assert values["declared_limit_status"] == "EXCEEDS_DECLARED_LIMITS"
        assert values["limit_checks"]["angular_speed"] is False
        assert values["power_balance_residual_w"] == 0
        assert row["allocated_heat_w"] == row["unallocated_loss_w"] == 0
        if integer_parameters:
            assert all(type(v) is int for k, v in row["actual_motor_request"]["parameters"].items()
                       if k not in ("parameter_source", "applicability_declaration"))
            assert all(type(v) is int for k, v in row["actual_motor_request"]["declared_limits"].items()
                       if k != "limit_source")


@pytest.mark.parametrize("section,field,value", [
    ("parameters", "motor_constant_si", 0), ("parameters", "terminal_resistance_ohm", -1),
    ("parameters", "zero_torque_current_a", True), ("parameters", "parameter_source", " "),
    ("parameters", "applicability_declaration", "other"),
    ("declared_limits", "maximum_current_a", 0), ("declared_limits", "maximum_terminal_voltage_v", float("inf")),
    ("declared_limits", "maximum_angular_speed_rad_s", True), ("declared_limits", "maximum_shaft_torque_nm", 1e-320),
    ("declared_limits", "limit_source", ""), (None, "id", "wrong"),
    (None, "heat_fraction_of_motor_loss", 1.01), (None, "heat_source", " "),
    ("auxiliary", "power_w", -1), ("auxiliary", "heat_fraction", True), ("auxiliary", "source", ""),
    ("work", "max_evaluations", 64),
])
def test_global_preflight_before_all_calls(monkeypatch, section, field, value):
    supplied = request()
    if section == "work":
        for rotor in supplied["assembly"]["rotors"]:
            rotor["target_template"][field] = value
            rotor["target_template"]["rotor_template"]["annuli"] = 512
    else:
        destination = supplied["auxiliary"] if section == "auxiliary" else supplied["motors"][-1]
        destination = destination[section] if section in ("parameters", "declared_limits") else destination
        destination[field] = value
    calls = install_spies(monkeypatch)
    result = bridge.evaluate_tabulated_target_dc_power(supplied)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["request_sha256"] is result["evaluation_sha256"] is None
    assert not any(call.call_count for call in calls.values())


@pytest.mark.parametrize("case", ["foreign", "cycle", "utf8", "string", "integer", "items", "depth", "nodes"])
def test_strict_outer_json_resources(monkeypatch, case):
    supplied = request()
    values = {"foreign": type("Foreign", (dict,), {"__deepcopy__": lambda *_: pytest.fail("copy hook")})(),
              "cycle": supplied, "utf8": "\ud800", "string": "x" * 2001, "integer": 1 << 1023,
              "items": [0] * 257, "depth": [[[[[[[[[[[[[[[[0]]]]]]]]]]]]]]]],
              "nodes": [[0] * 256 for _ in range(256)] * 2}
    supplied["extra"] = values[case]
    calls = install_spies(monkeypatch)
    assert bridge.evaluate_tabulated_target_dc_power(supplied)["status"] == "MODEL_INAPPLICABLE"
    assert not any(call.call_count for call in calls.values())


def test_actual_maximum_payload_and_output_budgets(monkeypatch):
    supplied = request()
    rotor = supplied["assembly"]["rotors"][0]
    template = rotor["target_template"]["rotor_template"]
    template.update(annuli=512, blade_count=32, stations=[
        {"radius_m": i / 255, "chord_m": 0.08 - 0.04 * i / 255,
         "blade_angle_rad": 0.12 - 0.04 * i / 255} for i in range(256)])
    air = assembly.reference_air_properties(**supplied["assembly"]["air"])
    known = forward.evaluate_tabulated_hover_bemt({**deepcopy(template),
        "density_kg_m3": air.state.density_kg_m3, "angular_speed_rad_s": 50.0})
    assert known["status"] == "COMPUTED_EXPERIMENTAL"
    rotor["target_template"].update(target_thrust_n=known["outputs"]["thrust_n"], max_evaluations=8)
    supplied["assembly"]["rotors"] = [{**deepcopy(rotor), "id": f"r{i}"} for i in range(8)]
    supplied["motors"] = [{**deepcopy(supplied["motors"][0]), "id": f"r{i}"} for i in range(8)]
    calls = install_spies(monkeypatch)
    result = bridge.evaluate_tabulated_target_dc_power(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL", result["reasons"]
    assert (result["assembly_inverse_result_count"], result["forward_evaluation_count"], result["motor_result_count"]) == (8, 16, 8)
    assert [calls[k].call_count for k in ("assembly", "air", "inverse", "trials", "motor", "compute")] == [1, 1, 8, 16, 8, 8]
    for actual, key in ((supplied, "input_json"), (result, "output_json"),
                        (supplied["assembly"], "assembly_input_json"), (result["outputs"]["assembly"], "assembly_output_json")):
        bridge._json_walk(actual, bridge._LIMITS[key])


def test_catalog_fresh_and_model_free(monkeypatch):
    calls = install_spies(monkeypatch)
    original = bridge.tabulated_target_dc_power_catalog()
    changed = bridge.tabulated_target_dc_power_catalog()
    changed["assembly_catalog"]["output_field_units"].clear()
    changed["input_units"]["motors"]["parameters"].clear()
    assert bridge.tabulated_target_dc_power_catalog() == original
    assert original["output_field_units"]["assembly"] == {"outputs": original["assembly_catalog"]["output_field_units"]}
    assert not any(call.call_count for call in calls.values())


@pytest.fixture(scope="module")
def captured_components():
    supplied = request()
    return supplied, *direct_components(supplied)


def assert_atomic(result, supplied, status, inverses, forwards, motors):
    assert result["status"] == status
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == result["transfers"] == []
    assert result["diagnostics_complete"] is False
    assert (result["assembly_inverse_result_count"], result["forward_evaluation_count"], result["motor_result_count"]) == (inverses, forwards, motors)
    assert result["request_sha256"] == sha256_record(supplied)
    assert result["evaluation_sha256"] == (None if status == "MODEL_INAPPLICABLE" else sha256_record({
        k: v for k, v in result.items() if k != "evaluation_sha256"}))
    assert "private detail" not in str(result)


@pytest.mark.parametrize("late", [False, True])
@pytest.mark.parametrize("status", ["TARGET_NOT_BRACKETED", "ITERATION_LIMIT", "MODEL_INAPPLICABLE", "EXECUTION_FAILED"])
def test_actual_noncomputed_assembly_stops_before_motors(monkeypatch, captured_components, late, status):
    supplied, direct, _, _ = deepcopy(captured_components)
    target = supplied["assembly"]["rotors"][int(late)]["target_template"]
    if status == "TARGET_NOT_BRACKETED":
        for station in target["rotor_template"]["stations"]:
            station["blade_angle_rad"] = 0.0
    elif status == "ITERATION_LIMIT":
        target["max_evaluations"] = 2
    elif status == "MODEL_INAPPLICABLE":
        target["rotor_template"]["stations"][0]["chord_m"] = -1.0
    calls = install_spies(monkeypatch)
    if status == "EXECUTION_FAILED":
        def trial(arguments):
            if calls["inverse"].call_count == int(late) + 1:
                raise RuntimeError("private detail")
            return calls["trials"]._mock_wraps(arguments)
        calls["trials"].side_effect = trial
    result = bridge.evaluate_tabulated_target_dc_power(supplied)
    prior = direct["outputs"]["rotors"][0]["actual_target_result"]["evaluation_count"] if late else 0
    forwards = prior + (1 if status in ("MODEL_INAPPLICABLE", "EXECUTION_FAILED") else 2)
    assert_atomic(result, supplied, status, int(late) + 1, forwards, 0)
    assert [calls[k].call_count for k in ("assembly", "air", "inverse", "trials", "motor", "compute")] == [1, 1, int(late) + 1, forwards, 0, 0]


@pytest.mark.parametrize("case", ["counts", "air", "selected", "stages", "units"])
def test_rehashed_actual_assembly_forgery_discards_counts(monkeypatch, captured_components, case):
    supplied, damaged, _, _ = deepcopy(captured_components)
    if case == "counts":
        damaged["inverse_result_count"] = 1
    elif case == "air":
        damaged["outputs"]["air"]["gravity_m_s2"] += 0.1
    elif case == "selected":
        child = damaged["outputs"]["rotors"][0]["actual_target_result"]
        selected = child["outputs"]["actual_forward_result"]
        selected["outputs"]["radii_m"][0] += 0.01
        selected["evaluation_sha256"] = sha256_record({k: v for k, v in selected.items() if k != "evaluation_sha256"})
        child["trace"][-1]["full_actual_result_sha256"] = sha256_record(selected)
        child["evaluation_sha256"] = sha256_record({k: v for k, v in child.items() if k != "evaluation_sha256"})
        damaged["stages"][1]["result_sha256"] = sha256_record(child)
    elif case == "stages":
        damaged["stages"][0]["result_sha256"] = "0" * 64
    else:
        damaged["output_units"]["net_force_body_n"] = "kg"
    damaged["evaluation_sha256"] = sha256_record({k: v for k, v in damaged.items() if k != "evaluation_sha256"})
    calls = install_spies(monkeypatch)
    calls["assembly"].return_value = damaged
    assert_atomic(bridge.evaluate_tabulated_target_dc_power(supplied), supplied, "EXECUTION_FAILED", 0, 0, 0)
    assert calls["assembly_guard"].call_count == 1 and calls["motor"].call_count == 0


@pytest.mark.parametrize("field", ["current_a", "back_emf_v", "terminal_voltage_v", "shaft_power_w", "electrical_power_w", "copper_loss_w", "friction_equivalent_loss_w", "total_loss_w", "power_balance_residual_w", "efficiency"])
@pytest.mark.parametrize("wrong_type", [False, True])
def test_second_actual_motor_scalar_forgery(monkeypatch, captured_components, field, wrong_type):
    def damage(actual):
        value = actual["outputs"][field]
        actual["outputs"][field] = int(value) if wrong_type else value + 0.01
    motor_forgery(monkeypatch, captured_components, damage)


@pytest.mark.parametrize("case", ["units", "sources", "limitations", "request_hash", "evaluation_sha256", "checks", "limit_status", "null_efficiency", "wrong_operating_point", "execution_failed", *bridge._MOTOR_STATIC])
def test_second_actual_motor_contract_forgery(monkeypatch, captured_components, case):
    def damage(actual):
        if case == "units":
            actual["output_units"]["current_a"] = "W"
        elif case in ("sources", "limitations"):
            actual[case].clear()
        elif case == "request_hash":
            actual["request_sha256"] = "0" * 64
        elif case == "evaluation_sha256":
            actual[case] = "0" * 64
        elif case == "checks":
            actual["outputs"]["limit_checks"]["current"] = 1
        elif case == "limit_status":
            actual["outputs"]["declared_limit_status"] = "EXCEEDS_DECLARED_LIMITS"
        elif case == "null_efficiency":
            actual["outputs"]["efficiency"] = None
        elif case == "wrong_operating_point":
            return
        else:
            actual["status" if case == "execution_failed" else case] = "forged"
    motor_forgery(monkeypatch, captured_components, damage, case)


def motor_forgery(monkeypatch, captured_components, damage, case=None):
    supplied, direct, _, _ = deepcopy(captured_components)
    calls = install_spies(monkeypatch)
    def evaluate(arguments):
        if calls["motor"].call_count == 2 and case == "wrong_operating_point":
            arguments["operating_point"]["angular_speed_rad_s"] *= 1.01
        if calls["motor"].call_count == 2 and case == "execution_failed":
            calls["compute"].side_effect = RuntimeError("private detail")
        actual = calls["motor"]._mock_wraps(arguments)
        if calls["motor"].call_count == 2 and case != "execution_failed":
            damage(actual)
        return actual
    calls["motor"].side_effect = evaluate
    result = bridge.evaluate_tabulated_target_dc_power(supplied)
    assert_atomic(result, supplied, "EXECUTION_FAILED", 2, direct["forward_evaluation_count"], 1)
    assert calls["motor"].call_count == calls["compute"].call_count == 2


@pytest.mark.parametrize("component", ["assembly", "motor"])
@pytest.mark.parametrize("fatal", [False, True])
def test_component_exceptions_and_base_exceptions(monkeypatch, captured_components, component, fatal):
    supplied, direct, _, _ = deepcopy(captured_components)
    calls = install_spies(monkeypatch)
    calls[component].side_effect = KeyboardInterrupt("private detail") if fatal else RuntimeError("private detail")
    if fatal:
        with pytest.raises(KeyboardInterrupt):
            bridge.evaluate_tabulated_target_dc_power(supplied)
    else:
        assert_atomic(bridge.evaluate_tabulated_target_dc_power(supplied), supplied, "EXECUTION_FAILED",
                      0 if component == "assembly" else 2, 0 if component == "assembly" else direct["forward_evaluation_count"], 0)


def test_actual_snapshots_and_argument_mutations_are_isolated(monkeypatch, captured_components):
    supplied, direct, _, motors = deepcopy(captured_components)
    raw_assembly, raw_motors = [], []
    calls = install_spies(monkeypatch)
    def evaluate_assembly(arguments):
        actual = calls["assembly"]._mock_wraps(arguments)
        raw_assembly.append(actual)
        arguments.clear()
        return actual
    def evaluate_motor(arguments):
        if raw_motors:
            raw_motors[0].clear()
        raw_assembly[0].clear()
        actual = calls["motor"]._mock_wraps(arguments)
        raw_motors.append(actual)
        arguments.clear()
        return actual
    calls["assembly"].side_effect = evaluate_assembly
    calls["motor"].side_effect = evaluate_motor
    original = deepcopy(supplied)
    result = bridge.evaluate_tabulated_target_dc_power(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["assembly"] == direct
    assert [r["actual_motor_result"] for r in result["outputs"]["power"]["motors"]] == motors
    assert supplied == original and calls["compute"].call_count == 2
    before = deepcopy(result)
    supplied.clear()
    raw_motors[-1].clear()
    assert result == before


@pytest.mark.parametrize("resistance,idle", [(0, 0), (0, 1), (1, 0), (1, 1)])
@pytest.mark.parametrize("fraction", [0, 1])
def test_actual_loss_components_heat_endpoints_and_inclusive_limits(monkeypatch, resistance, idle, fraction):
    supplied = request()
    for motor in supplied["motors"]:
        motor["parameters"].update(motor_constant_si=1, terminal_resistance_ohm=resistance, zero_torque_current_a=idle)
        motor["heat_fraction_of_motor_loss"] = fraction
    supplied["auxiliary"].update(power_w=10 if fraction else 0, heat_fraction=fraction)
    direct, injected, motors = direct_components(supplied)
    for motor, arguments, actual in zip(supplied["motors"], injected, motors, strict=True):
        values, op = actual["outputs"], arguments["operating_point"]
        motor["declared_limits"].update(maximum_current_a=values["current_a"],
            maximum_terminal_voltage_v=values["terminal_voltage_v"],
            maximum_angular_speed_rad_s=op["angular_speed_rad_s"], maximum_shaft_torque_nm=op["shaft_torque_nm"])
    calls = install_spies(monkeypatch)
    result = bridge.evaluate_tabulated_target_dc_power(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    power = result["outputs"]["power"]
    assert power["all_motors_within_declared_limits"] is True
    for row in power["motors"]:
        actual, arguments = row["actual_motor_result"], row["actual_motor_request"]
        values = actual["outputs"]
        assert arguments["operating_point"]["shaft_torque_nm"] > 0
        assert values["copper_loss_w"] > 0 if resistance else values["copper_loss_w"] == 0
        assert values["friction_equivalent_loss_w"] > 0 if idle else values["friction_equivalent_loss_w"] == 0
        assert all(value is True for value in values["limit_checks"].values())
        assert row["allocated_heat_w"] == (values["total_loss_w"] if fraction else 0)
        assert row["unallocated_loss_w"] == (0 if fraction else values["total_loss_w"])
        assert "evaluation_sha256" not in actual
        with monkeypatch.context() as patch:
            patch.setattr(dc, "_compute", Mock(side_effect=AssertionError("guard rerun")))
            assert bridge._validate_motor(actual, arguments) is None
    assert power["total_heat_w"] == (power["total_motor_loss_w"] + 10 if fraction else 0)
    assert power["total_electrical_power_w"] == power["total_motor_electrical_power_w"] + supplied["auxiliary"]["power_w"]
    assert calls["motor"].call_count == calls["compute"].call_count == 2
    assert result["output_units"]["assembly"] == {"outputs": direct["output_units"]}
    assert result["output_units"]["power"]["motors"]["actual_motor_result"] == {"outputs": motors[0]["output_units"]}


@pytest.mark.parametrize("case", ["motor_overflow", "motor_subnormal", "motor_underflow", "heat_underflow"])
def test_actual_arithmetic_failures_are_atomic_and_count_only_guarded(monkeypatch, captured_components, case):
    supplied, direct, _, _ = deepcopy(captured_components)
    parameters = supplied["motors"][1]["parameters"]
    if case == "motor_overflow":
        parameters["terminal_resistance_ohm"] = 1e308
    elif case in ("motor_subnormal", "motor_underflow"):
        parameters.update(motor_constant_si=1e305,
                          terminal_resistance_ohm=1e-10 if case == "motor_subnormal" else 1e-300,
                          zero_torque_current_a=0)
    elif case == "heat_underflow":
        parameters.update(motor_constant_si=0.1, terminal_resistance_ohm=1e-5, zero_torque_current_a=0)
        supplied["motors"][1]["heat_fraction_of_motor_loss"] = sys.float_info.min
    calls = install_spies(monkeypatch)
    products = Mock(wraps=bridge.th.checked_product)
    monkeypatch.setattr(bridge.th, "checked_product", products)
    returned = []
    def evaluate(arguments):
        actual = calls["motor"]._mock_wraps(arguments)
        returned.append(deepcopy(actual))
        return actual
    calls["motor"].side_effect = evaluate
    result = bridge.evaluate_tabulated_target_dc_power(supplied)
    guarded = 2 if case == "heat_underflow" else 1
    assert_atomic(result, supplied, "EXECUTION_FAILED", 2, direct["forward_evaluation_count"], guarded)
    assert calls["motor"].call_count == calls["compute"].call_count == 2
    assert returned[1]["status"] == ("COMPUTED_EXPERIMENTAL" if guarded == 2 else "EXECUTION_FAILED")
    if case == "heat_underflow":
        assert 0 < returned[1]["outputs"]["total_loss_w"] < 1
    assert returned[0]["status"] == "COMPUTED_EXPERIMENTAL"
    outcomes = [a * b for call in products.call_args_list for a, b in [call.args] if a != 0 and b != 0]
    assert any(not math.isfinite(v) for v in outcomes) if case == "motor_overflow" else (
        any(v == 0 for v in outcomes) if case == "motor_underflow" else
        any(0 < abs(v) < sys.float_info.min for v in outcomes))


def test_cross_binding_tolerance_is_explicit_arithmetic_metadata():
    catalog = bridge.tabulated_target_dc_power_catalog()
    assert "rel_tol=1e-12 abs_tol=1e-12 W" in catalog["bindings"]["shaft_cross_binding"]
    assert "not a physical threshold" in catalog["bindings"]["shaft_cross_binding"]


def test_power_sum_overflow_helper_probe_only():
    """Helper arithmetic probe; no claim that the standard assembly reaches it."""
    with pytest.raises(OverflowError):
        dc._power_sum([1e308, 1e308])
