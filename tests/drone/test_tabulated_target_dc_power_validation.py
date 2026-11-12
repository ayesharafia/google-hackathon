"""Capture actual V116 results before blocking every model and runtime catalog."""

import importlib
import math
import sys
from copy import deepcopy
from unittest.mock import Mock

import pytest

from physimesh.drone import tabulated_target_dc_power_validation as guard
from physimesh.drone.provenance import sha256_record
from tests.drone import test_tabulated_target_dc_power as fixtures

bridge, assembly, inverse, forward, dc = (
    fixtures.bridge, fixtures.assembly, fixtures.inverse, fixtures.forward, fixtures.dc,
)


def block_models(monkeypatch):
    calls = []
    for name in (
        "reference_air_properties", "standard_atmosphere", "reference_air_tabulated_hover", "hover_bemt",
        "reference_air_tabulated_hover_thrust_target", "tabulated_hover_bemt",
        "tabulated_hover_bemt_request", "tabulated_hover_thrust_target",
        "tabulated_rotor_assembly", "tabulated_thrust_target_assembly", "dc_motor",
        "tabulated_target_dc_power", "tabulated_thrust_target_assembly_validation",
        "tabulated_hover_thrust_target_validation",
    ):
        module = importlib.import_module("physimesh.drone." + name)
        for field in vars(module).copy():
            if (field.startswith("evaluate_") or field.endswith("_catalog") or
                    field in ("reference_air_properties", "standard_atmosphere",
                              "solve_tabulated_hover", "solve_hover", "_compute", "deepcopy",
                              "_response", "_seal", "_snapshot")):
                call = Mock(side_effect=AssertionError("runtime model/catalog: " + name + "." + field))
                monkeypatch.setattr(module, field, call)
                calls.append(call)
    return calls


def checked(monkeypatch, actual, supplied, *, rejects=False):
    before = deepcopy((actual, supplied))
    # Canonical JSON catches scalar type changes that ordinary equality misses.
    digests = sha256_record(actual), sha256_record(supplied)
    calls = block_models(monkeypatch)
    if rejects:
        with pytest.raises(ValueError):
            guard.validate_tabulated_target_dc_power_result(actual, supplied)
    else:
        assert guard.validate_tabulated_target_dc_power_result(actual, supplied) is None
    assert (actual, supplied) == before
    assert (sha256_record(actual), sha256_record(supplied)) == digests
    for call in calls:
        call.assert_not_called()


def rehash(actual):
    actual["evaluation_sha256"] = (None if actual["status"] == "MODEL_INAPPLICABLE" else
                                   sha256_record({k: v for k, v in actual.items()
                                                  if k != "evaluation_sha256"}))


def rebind(actual):
    """Test-side coherent child/stage/transfer hashes; never construct a valid child."""
    if actual["status"] != "COMPUTED_EXPERIMENTAL":
        rehash(actual)
        return
    retained = actual["outputs"]["assembly"]
    actual["stages"][0]["result_sha256"] = sha256_record(retained)
    for i, row in enumerate(actual["outputs"]["power"]["motors"]):
        request, result = row["actual_motor_request"], row["actual_motor_result"]
        digest = sha256_record(request)
        result["request_sha256"] = digest
        actual["stages"][i + 1].update(
            inputs=deepcopy(request), inputs_sha256=digest, result_sha256=sha256_record(result))
        for transfer in actual["transfers"][2 * i:2 * i + 2]:
            transfer.update(producer_result_sha256=sha256_record(retained),
                            consumer_request_sha256=digest)
    rehash(actual)


@pytest.fixture(scope="module", params=["standard", "ideal_integer"])
def capture(request):
    supplied = fixtures.request()
    if request.param == "ideal_integer":
        for motor in supplied["motors"]:
            motor["parameters"].update(motor_constant_si=1, terminal_resistance_ohm=0,
                                       zero_torque_current_a=0)
            motor["heat_fraction_of_motor_loss"] = 0
            for name in motor["declared_limits"]:
                if name != "limit_source":
                    motor["declared_limits"][name] = 1
        supplied["auxiliary"].update(power_w=0, heat_fraction=0)
    actual = bridge.evaluate_tabulated_target_dc_power(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL", actual["reasons"]
    return actual, supplied


def test_actual_two_rotor_capture(monkeypatch, capture):
    actual, supplied = capture
    rows = actual["outputs"]["power"]["motors"]
    assert len(rows) == actual["motor_result_count"] == 2
    for row, declaration in zip(rows, supplied["motors"], strict=True):
        assert "evaluation_sha256" not in row["actual_motor_result"]
        assert type(row["actual_motor_request"]["parameters"]["motor_constant_si"]) is type(
            declaration["parameters"]["motor_constant_si"])
    checked(monkeypatch, actual, supplied)


@pytest.mark.parametrize("field", list(bridge._MOTOR_STATIC) + [
    "request_sha256", "output_units", "evaluation_sha256", "extra", "missing",
])
def test_full_motor_envelope_rehashed(monkeypatch, capture, field):
    actual, supplied = deepcopy(capture)
    result = actual["outputs"]["power"]["motors"][0]["actual_motor_result"]
    if field == "missing":
        result.pop("runtime_identity")
    elif field == "request_sha256":
        result[field] = "0" * 64
        actual["stages"][1]["result_sha256"] = sha256_record(result)
        rehash(actual)
        checked(monkeypatch, actual, supplied, rejects=True)
        return
    elif field == "output_units":
        result[field]["current_a"] = "W"
    else:
        result[field] = "forged"
    rebind(actual)
    checked(monkeypatch, actual, supplied, rejects=True)


@pytest.mark.parametrize("field", list(bridge._MOTOR_UNITS))
@pytest.mark.parametrize("mode", ["value", "type"])
def test_motor_arithmetic_and_native_types(monkeypatch, capture, field, mode):
    actual, supplied = deepcopy(capture)
    values = actual["outputs"]["power"]["motors"][0]["actual_motor_result"]["outputs"]
    old = values[field]
    if field == "limit_checks":
        values[field]["current"] = (not old["current"]) if mode == "value" else int(old["current"])
    elif field == "declared_limit_status":
        values[field] = "forged" if mode == "value" else None
    else:
        values[field] = old + 0.25 if mode == "value" else (
            int(old) if type(old) is float else float(old))
    # Every enclosing motor digest is repaired; rejection must inspect content.
    rebind(actual)
    checked(monkeypatch, actual, supplied, rejects=True)


@pytest.mark.parametrize("field", ["current", "terminal_voltage", "angular_speed", "shaft_torque"])
@pytest.mark.parametrize("value", [False, True, 0, 1])
def test_all_inclusive_limit_checks(monkeypatch, capture, field, value):
    actual, supplied = deepcopy(capture)
    result = actual["outputs"]["power"]["motors"][0]["actual_motor_result"]
    original = result["outputs"]["limit_checks"][field]
    result["outputs"]["limit_checks"][field] = value
    rebind(actual)
    checked(monkeypatch, actual, supplied, rejects=type(value) is not bool or value != original)


@pytest.mark.parametrize("field", list(bridge._TOTAL_FIELDS) + ["all_motors_within_declared_limits"])
@pytest.mark.parametrize("mode", ["value", "type"])
def test_totals_and_limit_flag(monkeypatch, capture, field, mode):
    actual, supplied = deepcopy(capture)
    power = actual["outputs"]["power"]
    old = power[field]
    if type(old) is bool:
        power[field] = not old if mode == "value" else int(old)
    else:
        power[field] = old + 0.25 if mode == "value" else (
            int(old) if type(old) is float else float(old))
    rebind(actual)
    checked(monkeypatch, actual, supplied, rejects=True)


@pytest.mark.parametrize("case", ["id", "extra", "missing", "allocated", "unallocated", "rows",
                                  "extra_power", "extra_outputs", "motor_count", "inverse_count", "forwards"])
def test_rows_counts_allocation_and_shapes(monkeypatch, capture, case):
    actual, supplied = deepcopy(capture)
    power = actual["outputs"]["power"]
    row = power["motors"][0]
    if case in ("allocated", "unallocated"):
        row["allocated_heat_w" if case == "allocated" else "unallocated_loss_w"] += 1.0
    elif case == "id":
        row["id"] = "left"
    elif case == "extra":
        row["extra"] = None
    elif case == "missing":
        row.pop("unallocated_loss_w")
    elif case == "rows":
        power["motors"].reverse()
    elif case in ("extra_power", "extra_outputs"):
        (power if case == "extra_power" else actual["outputs"])["extra"] = None
    else:
        actual[{"motor_count": "motor_result_count", "inverse_count": "assembly_inverse_result_count",
                "forwards": "forward_evaluation_count"}[case]] += 1
    rebind(actual)
    checked(monkeypatch, actual, supplied, rejects=True)


@pytest.mark.parametrize("field", ["evaluation", "parameters", "declared_limits", "omega", "torque", "extra"])
def test_actual_motor_request_injection(monkeypatch, capture, field):
    actual, supplied = deepcopy(capture)
    arguments = actual["outputs"]["power"]["motors"][0]["actual_motor_request"]
    if field == "parameters":
        arguments[field]["motor_constant_si"] *= 2
    elif field == "declared_limits":
        arguments[field]["maximum_current_a"] *= 2
    elif field in ("omega", "torque"):
        arguments["operating_point"]["angular_speed_rad_s" if field == "omega" else "shaft_torque_nm"] *= 2
    else:
        arguments[field] = "forged"
    rebind(actual)
    checked(monkeypatch, actual, supplied, rejects=True)


@pytest.mark.parametrize("case", ["parameters", "limits", "motor_heat", "aux_power", "aux_heat", "target"])
@pytest.mark.parametrize("rebind_inputs", [False, True])
def test_request_changes_with_repaired_root_digest(monkeypatch, capture, case, rebind_inputs):
    actual, supplied = deepcopy(capture)
    motor = supplied["motors"][0]
    if case == "parameters":
        motor["parameters"]["motor_constant_si"] *= 2
    elif case == "limits":
        motor["declared_limits"]["maximum_current_a"] = (
            1e100 if actual["outputs"]["power"]["motors"][0]["actual_motor_result"]
            ["outputs"]["limit_checks"]["current"] is False else 0.01)
    elif case == "motor_heat":
        motor["heat_fraction_of_motor_loss"] = 0.25
        # Ideal zero loss is insensitive to the allocation fraction; use a declaration change too.
        if actual["outputs"]["power"]["total_motor_loss_w"] == 0:
            motor["parameters"]["terminal_resistance_ohm"] = 1
    elif case in ("aux_power", "aux_heat"):
        supplied["auxiliary"]["power_w"] += 3
        if case == "aux_heat":
            supplied["auxiliary"]["heat_fraction"] = 1
    else:
        supplied["assembly"]["rotors"][0]["target_template"]["target_thrust_n"] += 1
    actual["request_sha256"] = sha256_record(supplied)
    if rebind_inputs:
        row = actual["outputs"]["power"]["motors"][0]
        row["actual_motor_request"].update(parameters=deepcopy(motor["parameters"]),
                                          declared_limits=deepcopy(motor["declared_limits"]))
    rebind(actual)
    checked(monkeypatch, actual, supplied, rejects=True)


@pytest.mark.parametrize("field", ["from_stage", "from_field", "to_stage", "to_field", "value", "unit",
                                  "producer_result_sha256", "consumer_request_sha256", "extra"])
@pytest.mark.parametrize("offset", [0, 1])
def test_ordered_transfer_bindings(monkeypatch, capture, field, offset):
    actual, supplied = deepcopy(capture)
    transfer = actual["transfers"][offset]
    transfer[field] = transfer[field] + 0.25 if field == "value" else "forged"
    rehash(actual)
    checked(monkeypatch, actual, supplied, rejects=True)


@pytest.mark.parametrize("case", ["stages_order", "transfers_order", "stage_count", "transfer_count",
                                  "name", "inputs", "input_digest", "result_digest", "extra"])
@pytest.mark.parametrize("index", [0, 1])
def test_stage_contract(monkeypatch, capture, case, index):
    actual, supplied = deepcopy(capture)
    stage = actual["stages"][index]
    if case in ("stages_order", "transfers_order"):
        actual["stages" if case == "stages_order" else "transfers"].reverse()
    elif case in ("stage_count", "transfer_count"):
        actual["stages" if case == "stage_count" else "transfers"].pop()
    elif case == "inputs":
        stage["inputs"]["evaluation"] = "forged"
        stage["inputs_sha256"] = sha256_record(stage["inputs"])
    else:
        stage[{"name": "stage", "input_digest": "inputs_sha256",
               "result_digest": "result_sha256", "extra": "extra"}[case]] = "forged"
    rehash(actual)
    checked(monkeypatch, actual, supplied, rejects=True)


@pytest.mark.parametrize("field", sorted(guard._STATIC | guard._DYNAMIC) + ["extra", "missing"])
def test_root_contract_rehashed(monkeypatch, capture, field):
    actual, supplied = deepcopy(capture)
    if field == "missing":
        actual.pop("schema_version")
    elif field in ("assembly_inverse_result_count", "forward_evaluation_count", "motor_result_count"):
        actual[field] = float(actual[field])
    else:
        actual[field] = "forged"
    if field != "evaluation_sha256":
        rehash(actual)
    checked(monkeypatch, actual, supplied, rejects=True)


@pytest.mark.parametrize("scope", ["assembly", "assembly_outputs", "power", "motors", "motor_request",
                                  "parameters", "declared_limits", "operating_point", "motor_result",
                                  "motor_outputs"])
def test_exact_unit_scopes(monkeypatch, capture, scope):
    actual, supplied = deepcopy(capture)
    units = actual["output_units"]
    motor_units = units["power"]["motors"]
    request_units = motor_units["actual_motor_request"]
    owner = {"assembly": units["assembly"], "assembly_outputs": units["assembly"]["outputs"],
             "power": units["power"], "motors": motor_units, "motor_request": request_units,
             **{key: request_units[key] for key in ("parameters", "declared_limits", "operating_point")},
             "motor_result": motor_units["actual_motor_result"],
             "motor_outputs": motor_units["actual_motor_result"]["outputs"]}[scope]
    owner["extra"] = "1"
    rehash(actual)
    checked(monkeypatch, actual, supplied, rejects=True)


def test_duplicate_auxiliary_even_with_consistent_totals(monkeypatch):
    supplied = fixtures.request()
    actual = bridge.evaluate_tabulated_target_dc_power(supplied)
    power = actual["outputs"]["power"]
    for auxiliary, total in (("auxiliary_electrical_power_w", "total_electrical_power_w"),
                             ("auxiliary_heat_w", "total_heat_w")):
        power[total] = dc._power_sum([power[total], power[auxiliary]])
        power[auxiliary] *= 2
    rehash(actual)
    checked(monkeypatch, actual, supplied, rejects=True)


@pytest.mark.parametrize("case", ["air", "force", "forward_content", "selected_digest", "intermediate_digest"])
def test_assembly_and_selected_content_rebound(monkeypatch, capture, case):
    actual, supplied = deepcopy(capture)
    retained = actual["outputs"]["assembly"]
    row = retained["outputs"]["rotors"][0]
    target = row["actual_target_result"]
    if case == "air":
        retained["outputs"]["air"]["state"]["pressure_pa"] *= 1.01
        retained["outputs"]["air"]["state"]["density_kg_m3"] *= 1.01
        digest = sha256_record(retained["outputs"]["air"])
        retained["stages"][0]["result_sha256"] = digest
        for transfer in retained["transfers"]:
            transfer["producer_result_sha256"] = digest
    elif case == "force":
        row["force_body_n"][2] += 1.0
    elif case == "forward_content":
        child = target["outputs"]["actual_forward_result"]
        child["outputs"]["radii_m"][0] += 0.001
        rehash(child)
        target["trace"][-1]["full_actual_result_sha256"] = sha256_record(child)
    elif case == "selected_digest":
        target["trace"][-1]["full_actual_result_sha256"] = "0" * 64
    else:
        assert len(target["trace"]) > 2
        target["trace"][0]["full_actual_result_sha256"] = "0123456789abcdef" * 4
    rehash(target)
    retained["stages"][1]["result_sha256"] = sha256_record(target)
    rehash(retained)
    rebind(actual)
    checked(monkeypatch, actual, supplied, rejects=case != "intermediate_digest")


def test_actual_eight_rotor_maximum_work_capture(monkeypatch):
    supplied = fixtures.request()
    rotor = supplied["assembly"]["rotors"][0]
    template = rotor["target_template"]["rotor_template"]
    template.update(annuli=512, blade_count=32, stations=[
        {"radius_m": i / 255, "chord_m": 0.08 - 0.04 * i / 255,
         "blade_angle_rad": 0.12 - 0.04 * i / 255} for i in range(256)])
    air = assembly.reference_air_properties(**supplied["assembly"]["air"])
    endpoint = forward.evaluate_tabulated_hover_bemt({
        **deepcopy(template), "density_kg_m3": air.state.density_kg_m3, "angular_speed_rad_s": 50.0})
    assert endpoint["status"] == "COMPUTED_EXPERIMENTAL"
    rotor["target_template"].update(target_thrust_n=endpoint["outputs"]["thrust_n"], max_evaluations=8)
    supplied["assembly"]["rotors"] = [
        {**deepcopy(rotor), "id": f"r{i}", "rotation_sign": 1 if i % 2 else -1} for i in range(8)]
    supplied["motors"] = [{**deepcopy(supplied["motors"][0]), "id": f"r{i}"} for i in range(8)]
    assert sum(r["target_template"]["max_evaluations"] * r["target_template"]["rotor_template"]["annuli"]
               for r in supplied["assembly"]["rotors"]) == 32768
    actual = bridge.evaluate_tabulated_target_dc_power(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL", actual["reasons"]
    assert (actual["assembly_inverse_result_count"], actual["forward_evaluation_count"],
            actual["motor_result_count"]) == (8, 16, 8)
    checked(monkeypatch, actual, supplied)


@pytest.mark.parametrize("late", [False, True])
@pytest.mark.parametrize("case", ["unbracketed", "iteration", "domain", "numerical", "air_failure",
                                  "inverse_zero", "invalid_assembly", "assembly_guard", "motor_failure",
                                  "motor_guard", "heat_failure"])
def test_actual_failure_captures(monkeypatch, late, case):
    supplied = fixtures.request()
    target = supplied["assembly"]["rotors"][int(late)]["target_template"]
    if case == "unbracketed":
        target["target_thrust_n"] = 1e12
    elif case == "iteration":
        target["max_evaluations"] = 2
    elif case == "domain":
        target["rotor_template"]["stations"][0]["chord_m"] = -1.0
    elif case == "numerical":
        # Observe actual endpoint thrusts before invoking V116 and before blocking.
        lo, hi = 150.0, math.nextafter(150.0, math.inf)
        density = assembly.reference_air_properties(**supplied["assembly"]["air"]).state.density_kg_m3
        thrusts = [forward.evaluate_tabulated_hover_bemt({
            **deepcopy(target["rotor_template"]), "density_kg_m3": density,
            "angular_speed_rad_s": omega})["outputs"]["thrust_n"] for omega in (lo, hi)]
        midpoint = thrusts[0] + (thrusts[1] - thrusts[0]) / 2
        assert thrusts[0] < midpoint < thrusts[1]
        target.update(angular_speed_bracket_rad_s=[lo, hi], target_thrust_n=midpoint,
                      absolute_thrust_tolerance_n=sys.float_info.min)
    elif case == "heat_failure":
        supplied["motors"][int(late)]["parameters"].update(
            motor_constant_si=0.1, terminal_resistance_ohm=1e-5, zero_torque_current_a=0)
        supplied["motors"][int(late)]["heat_fraction_of_motor_loss"] = sys.float_info.min
    with monkeypatch.context() as patch:
        error = RuntimeError("injected capture fault")
        if case == "air_failure":
            patch.setattr(assembly, "reference_air_properties", Mock(side_effect=error))
        elif case == "inverse_zero":
            target["rotor_template"]["geometry_source"] = "fail_before_first_trial"
            walk = inverse._JSON

            def fail_before_first_trial(value, limits):
                if type(value) is dict and value.get("geometry_source") == "fail_before_first_trial":
                    raise error
                return walk(value, limits)

            patch.setattr(inverse, "_JSON", fail_before_first_trial)
        elif case == "invalid_assembly":
            patch.setattr(assembly, "evaluate_tabulated_thrust_target_assembly", Mock(return_value={}))
        elif case == "assembly_guard":
            patch.setattr(bridge, "validate_tabulated_thrust_target_assembly_result", Mock(side_effect=error))
        elif case in ("motor_failure", "motor_guard"):
            name = "evaluate_dc_motor" if case == "motor_failure" else "_validate_motor"
            owner = dc if case == "motor_failure" else bridge
            original = getattr(owner, name)
            count = 0

            def fail_motor(*args):
                nonlocal count
                count += 1
                if count == int(late) + 1:
                    raise error
                return original(*args)

            patch.setattr(owner, name, fail_motor)
        actual = bridge.evaluate_tabulated_target_dc_power(supplied)
    expected = {"unbracketed": "TARGET_NOT_BRACKETED", "iteration": "ITERATION_LIMIT",
                "domain": "MODEL_INAPPLICABLE", "numerical": "NUMERICAL_LIMIT"}.get(case, "EXECUTION_FAILED")
    assert actual["status"] == expected, actual
    assembly_reason = case in ("unbracketed", "iteration", "domain", "numerical", "air_failure", "inverse_zero")
    assert actual["reasons"] == [bridge._REASONS["assembly" if assembly_reason else "execution"]]
    if case == "inverse_zero":
        assert actual["assembly_inverse_result_count"] == int(late) + 1
        assert actual["forward_evaluation_count"] == 0 if not late else actual["forward_evaluation_count"] >= 2
    if case in ("invalid_assembly", "assembly_guard", "air_failure"):
        assert actual["assembly_inverse_result_count"] == actual["forward_evaluation_count"] == 0
    if case in ("motor_failure", "motor_guard", "heat_failure"):
        assert actual["assembly_inverse_result_count"] == 2
        assert actual["motor_result_count"] == int(late) + (case == "heat_failure")
    else:
        assert actual["motor_result_count"] == 0
    checked(monkeypatch, actual, supplied)


@pytest.fixture(scope="module")
def failure_capture():
    supplied = fixtures.request()
    supplied["assembly"]["rotors"][1]["target_template"]["target_thrust_n"] = 1e12
    actual = bridge.evaluate_tabulated_target_dc_power(supplied)
    assert actual["status"] == "TARGET_NOT_BRACKETED"
    return actual, supplied


@pytest.mark.parametrize("profile", ["MODEL_INAPPLICABLE", "TARGET_NOT_BRACKETED", "ITERATION_LIMIT",
                                     "NUMERICAL_LIMIT", "EXECUTION_FAILED", "V116_EXECUTION"])
def test_synthetic_failure_count_grid_necessary_bounds_only(monkeypatch, failure_capture, profile):
    # Synthetic outer envelopes only. No assertion that these histories occurred.
    original, supplied = deepcopy(failure_capture)
    status = "EXECUTION_FAILED" if profile == "V116_EXECUTION" else profile
    original.update(status=status, request_sha256=sha256_record(supplied),
                    reasons=[bridge._REASONS["execution" if profile == "V116_EXECUTION" else "assembly"]])
    allowed = set()
    if profile == "V116_EXECUTION":
        allowed.add((0, 0, 0))
        allowed.update((2, f, m) for f in range(4, 65) for m in range(3))
    else:
        if status == "EXECUTION_FAILED":
            allowed.add((0, 0, 0))
        for n in (1, 2):
            lower, upper = {
                "MODEL_INAPPLICABLE": (2 * (n - 1) + 1, 32 * n),
                "TARGET_NOT_BRACKETED": (2 * n, 32 * (n - 1) + 2),
                "ITERATION_LIMIT": (2 * (n - 1) + 32, 32 * n),
                "NUMERICAL_LIMIT": (2 * n, 32 * n - 1),
                "EXECUTION_FAILED": (2 * (n - 1), 32 * n),
            }[status]
            allowed.update((n, f, 0) for f in range(lower, upper + 1))
    calls = block_models(monkeypatch)
    before_request = sha256_record(supplied)
    tested = 0
    for n in range(4):
        for f in range(66):
            for m in range(4):
                actual = {**original, "assembly_inverse_result_count": n,
                          "forward_evaluation_count": f, "motor_result_count": m}
                rehash(actual)
                before_actual = sha256_record(actual)
                if (n, f, m) in allowed:
                    assert guard.validate_tabulated_target_dc_power_result(actual, supplied) is None
                else:
                    with pytest.raises(ValueError):
                        guard.validate_tabulated_target_dc_power_result(actual, supplied)
                assert sha256_record(actual) == before_actual
                tested += 1
    assert tested == 1056  # 6336 synthetic envelope checks across the six profiles.
    assert sha256_record(supplied) == before_request
    for call in calls:
        call.assert_not_called()


@pytest.mark.parametrize("field", ["assembly_inverse_result_count", "forward_evaluation_count", "motor_result_count"])
@pytest.mark.parametrize("value", [-1, True, 1.0, 513])
def test_failure_count_types_and_outer_bounds(monkeypatch, failure_capture, field, value):
    actual, supplied = deepcopy(failure_capture)
    actual[field] = value
    rehash(actual)
    checked(monkeypatch, actual, supplied, rejects=True)


@pytest.mark.parametrize("field,value", [
    ("outputs", {"assembly": {}}), ("output_units", {"power": {}}), ("stages", [{}]),
    ("transfers", [{}]), ("diagnostics_complete", 0), ("reasons", ["Request snapshot failed."]),
    ("request_sha256", None), ("evaluation_sha256", None), ("status", "COMPUTED_EXPERIMENTAL"),
])
def test_failure_atomicity_reasons_and_hashes(monkeypatch, failure_capture, field, value):
    actual, supplied = deepcopy(failure_capture)
    actual[field] = value
    if field != "evaluation_sha256":
        rehash(actual)
    checked(monkeypatch, actual, supplied, rejects=True)


@pytest.mark.parametrize("budget", [2, 3, 32])
@pytest.mark.parametrize("count", [2, 3, 4, 33, 34, 35, 63, 64])
def test_synthetic_numerical_last_budget_bounds(monkeypatch, failure_capture, budget, count):
    actual, supplied = deepcopy(failure_capture)
    supplied["assembly"]["rotors"][1]["target_template"]["max_evaluations"] = budget
    actual.update(status="NUMERICAL_LIMIT", reasons=[bridge._REASONS["assembly"]],
                  request_sha256=sha256_record(supplied), assembly_inverse_result_count=2,
                  forward_evaluation_count=count)
    rehash(actual)
    checked(monkeypatch, actual, supplied, rejects=not (budget >= 3 and 4 <= count <= 32 + budget - 1))


@pytest.mark.parametrize("case", ["unsupported", "unsupported_bad_shape", "missing", "extra", "air", "fraction",
                                  "motor_id", "bool_parameter", "overflow", "snapshot", "hash"])
def test_actual_admission_and_narrow_infrastructure_matrix(monkeypatch, case):
    supplied = fixtures.request()
    if case.startswith("unsupported"):
        supplied.update(evaluation="unsupported", assembly=None, motors=None)
        if case == "unsupported_bad_shape":
            supplied["extra"] = None
    elif case == "missing":
        supplied.pop("auxiliary")
    elif case == "extra":
        supplied["extra"] = None
    elif case == "air":
        supplied["assembly"]["air"]["altitude_m"] = 30001
    elif case == "fraction":
        supplied["motors"][1]["heat_fraction_of_motor_loss"] = 1.01
    elif case == "motor_id":
        supplied["motors"][1]["id"] = "wrong"
    elif case == "bool_parameter":
        supplied["motors"][1]["parameters"]["motor_constant_si"] = True
    elif case == "overflow":
        supplied["auxiliary"]["power_w"] = 1 << 1023
    with monkeypatch.context() as patch:
        if case == "snapshot":
            copy = bridge.deepcopy
            patch.setattr(bridge, "deepcopy", lambda value: (_ for _ in ()).throw(RuntimeError())
                          if value is supplied else copy(value))
        elif case == "hash":
            patch.setattr(bridge, "sha256_record", Mock(side_effect=RuntimeError()))
        actual = bridge.evaluate_tabulated_target_dc_power(supplied)
    if case not in ("snapshot", "hash"):
        assert actual["status"] == ("SOLVER_UNSUPPORTED" if case == "unsupported" else "MODEL_INAPPLICABLE")
        assert actual["request_sha256"] is actual["evaluation_sha256"] is None
        assert (actual["assembly_inverse_result_count"], actual["forward_evaluation_count"],
                actual["motor_result_count"]) == (0, 0, 0)
    checked(monkeypatch, actual, supplied, rejects=case in ("snapshot", "hash"))


@pytest.mark.parametrize("error", [ValueError("invalid"), OverflowError("overflow"),
                                  RuntimeError("unexpected"), KeyboardInterrupt("fatal")])
def test_actual_preflight_exception_contract(monkeypatch, error):
    supplied = fixtures.request()
    with monkeypatch.context() as patch:
        patch.setattr(bridge, "_preflight", Mock(side_effect=error))
        if isinstance(error, KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                bridge.evaluate_tabulated_target_dc_power(supplied)
            actual = None
        else:
            actual = bridge.evaluate_tabulated_target_dc_power(supplied)
    if actual is None:
        actual = bridge.evaluate_tabulated_target_dc_power(supplied)
    before = deepcopy((actual, supplied))
    calls = block_models(monkeypatch)
    monkeypatch.setattr(bridge, "_preflight", Mock(side_effect=error))
    if isinstance(error, (ValueError, OverflowError)):
        assert actual["status"] == "MODEL_INAPPLICABLE"
        assert guard.validate_tabulated_target_dc_power_result(actual, supplied) is None
    else:
        with pytest.raises(type(error)):
            guard.validate_tabulated_target_dc_power_result(actual, supplied)
    assert (actual, supplied) == before
    for call in calls:
        call.assert_not_called()


@pytest.mark.parametrize("dependency", ["hash", "assembly", "motor", "thermal", "sum"])
@pytest.mark.parametrize("error", [ValueError("pure rejection"), RuntimeError("unexpected"), KeyboardInterrupt()])
def test_pure_dependency_exceptions_propagate(monkeypatch, capture, dependency, error):
    actual, supplied = deepcopy(capture)
    before = deepcopy((actual, supplied))
    calls = block_models(monkeypatch)
    owner, name = {"hash": (guard, "sha256_record"),
                   "assembly": (guard, "validate_tabulated_thrust_target_assembly_result"),
                   "motor": (bridge, "_validate_motor"), "thermal": (bridge.th, "checked_product"),
                   "sum": (dc, "_power_sum")}[dependency]
    monkeypatch.setattr(owner, name, Mock(side_effect=error))
    with pytest.raises(type(error)):
        guard.validate_tabulated_target_dc_power_result(actual, supplied)
    assert (actual, supplied) == before
    for call in calls:
        call.assert_not_called()


def test_private_catalog_snapshot_unaffected_by_public_mutation(monkeypatch, capture):
    public = bridge.tabulated_target_dc_power_catalog()
    public["limits"]["output_json"]["max_nodes_including_keys"] = 0
    public["limitations"].clear()
    public["output_field_units"]["assembly"].clear()
    public["output_field_units"]["power"]["motors"]["actual_motor_result"].clear()
    actual, supplied = deepcopy(capture)
    checked(monkeypatch, actual, supplied)


def node_tree(nodes):
    """Helper-only resource fixture: small aliased storage, exact JSON occurrence count."""
    cache = {1: 0, 2: [0], 3: {"key": 0}}

    def build(count):
        if count not in cache:
            width = min(8, count - 1)
            quotient, remainder = divmod(count - 1, width)
            cache[count] = [build(quotient + (i < remainder)) for i in range(width)]
        return cache[count]

    return build(nodes)


@pytest.mark.parametrize("scope", ["input_json", "output_json"])
@pytest.mark.parametrize("dimension", ["nodes", "depth", "items", "string", "integer"])
def test_walker_only_exact_resource_boundaries(scope, dimension):
    # These are accepted-walker helper probes, not complete valid V116 envelopes.
    limits = guard._CATALOG["limits"][scope]
    if dimension == "nodes":
        accepted = node_tree(limits["max_nodes_including_keys"])
        rejected = node_tree(limits["max_nodes_including_keys"] + 1)
    elif dimension == "depth":
        accepted = 0
        for _ in range(limits["max_depth"] - 1):
            accepted = [accepted]
        rejected = [accepted]
    elif dimension == "items":
        accepted = [0] * limits["max_container_items"]
        rejected = [0] * (limits["max_container_items"] + 1)
    elif dimension == "string":
        accepted = "x" * limits["max_string_characters"]
        rejected = accepted + "x"
    else:
        accepted = (1 << limits["max_integer_bits"]) - 1
        rejected = 1 << limits["max_integer_bits"]
    assert guard._json_walk(accepted, limits) is None
    with pytest.raises(ValueError):
        guard._json_walk(rejected, limits)


def test_walker_only_keys_and_repeated_aliases_each_count():
    leaf = {"key": 0}  # mapping + key + value = three nodes
    limits = {**guard._CATALOG["limits"]["input_json"], "max_nodes_including_keys": 3}
    assert guard._json_walk(leaf, limits) is None
    with pytest.raises(ValueError):
        guard._json_walk(leaf, {**limits, "max_nodes_including_keys": 2})
    aliased = [leaf, leaf]  # list + two full occurrences of three nodes = seven
    assert aliased[0] is aliased[1]
    assert guard._json_walk(aliased, {**limits, "max_nodes_including_keys": 7}) is None
    with pytest.raises(ValueError):
        guard._json_walk(aliased, {**limits, "max_nodes_including_keys": 6})


@pytest.mark.parametrize("side", ["actual", "request"])
@pytest.mark.parametrize("kind", [dict, list, int, float, str])
def test_json_subclasses_rejected_without_any_hooks(monkeypatch, side, kind):
    hook = Mock(side_effect=AssertionError("foreign hook invoked"))
    foreign = type("Foreign", (kind,), {
        "__eq__": hook, "__iter__": hook, "__deepcopy__": hook, "__float__": hook,
        "__int__": hook, "items": hook, "encode": hook,
    })
    bad = foreign()
    supplied = fixtures.request() if side == "actual" else bad
    actual = bad if side == "actual" else bridge.evaluate_tabulated_target_dc_power(supplied)
    if side == "request":
        assert actual["status"] == "MODEL_INAPPLICABLE"
        assert actual["request_sha256"] is actual["evaluation_sha256"] is None
    calls = block_models(monkeypatch)
    hashing = Mock(side_effect=AssertionError("unbounded input hashed"))
    monkeypatch.setattr(guard, "sha256_record", hashing)
    if side == "actual":
        with pytest.raises(ValueError):
            guard.validate_tabulated_target_dc_power_result(actual, supplied)
    else:
        assert guard.validate_tabulated_target_dc_power_result(actual, supplied) is None
    hashing.assert_not_called()
    hook.assert_not_called()
    for call in calls:
        call.assert_not_called()


@pytest.mark.parametrize("side", ["actual", "request"])
@pytest.mark.parametrize("case", ["nan", "infinity", "utf8", "integer", "string", "depth", "items",
                                  "cycle", "nodes", "nonstring_key", "tuple"])
def test_outer_json_resources_before_hash_or_models(monkeypatch, side, case):
    limits = guard._CATALOG["limits"]["output_json" if side == "actual" else "input_json"]
    if case == "nodes":
        bad = node_tree(limits["max_nodes_including_keys"] + 1)
    elif case == "depth":
        bad = 0
        for _ in range(limits["max_depth"]):
            bad = [bad]
    elif case == "items":
        bad = [0] * (limits["max_container_items"] + 1)
    elif case == "cycle":
        bad = []
        bad.append(bad)
    else:
        bad = {"nan": math.nan, "infinity": math.inf, "utf8": "\ud800",
               "integer": 1 << 1023, "string": "x" * 2001, "nonstring_key": {1: 0},
               "tuple": (0,)}[case]
    supplied = fixtures.request() if side == "actual" else bad
    actual = bad if side == "actual" else bridge.evaluate_tabulated_target_dc_power(supplied)
    calls = block_models(monkeypatch)
    hashing = Mock(side_effect=AssertionError("unbounded input hashed"))
    preflight = Mock(side_effect=AssertionError("unbounded input preflighted"))
    monkeypatch.setattr(guard, "sha256_record", hashing)
    monkeypatch.setattr(bridge, "_preflight", preflight)
    if side == "actual":
        with pytest.raises(ValueError):
            guard.validate_tabulated_target_dc_power_result(actual, supplied)
    else:
        assert actual["status"] == "MODEL_INAPPLICABLE"
        assert guard.validate_tabulated_target_dc_power_result(actual, supplied) is None
    hashing.assert_not_called()
    preflight.assert_not_called()
    for call in calls:
        call.assert_not_called()


@pytest.mark.parametrize("scope", ["assembly_output_json", "motor_input_json", "motor_output_json"])
def test_independent_child_walks_precede_their_guard(monkeypatch, capture, scope):
    actual, supplied = deepcopy(capture)
    before = deepcopy((actual, supplied))
    row = actual["outputs"]["power"]["motors"][0]
    expected_values = [actual, supplied, actual["outputs"]["assembly"],
                       row["actual_motor_request"], row["actual_motor_result"]]
    expected_scopes = ["output_json", "input_json", "assembly_output_json",
                       "motor_input_json", "motor_output_json"]
    stop = expected_scopes.index(scope)
    walked = []
    walk = guard._json_walk

    def bounded_child_sentinel(value, limits):
        index = len(walked)
        assert value is expected_values[index]
        assert limits is guard._CATALOG["limits"][expected_scopes[index]]
        walked.append(value)
        if index == stop:
            raise ValueError("independent child resource boundary sentinel")
        return walk(value, limits)

    calls = block_models(monkeypatch)
    monkeypatch.setattr(guard, "_json_walk", bounded_child_sentinel)
    assembly_guard = Mock(wraps=guard.validate_tabulated_thrust_target_assembly_result)
    motor_guard = Mock(side_effect=AssertionError("motor guard before child walk"))
    monkeypatch.setattr(guard, "validate_tabulated_thrust_target_assembly_result", assembly_guard)
    monkeypatch.setattr(bridge, "_validate_motor", motor_guard)
    with pytest.raises(ValueError, match="independent child resource boundary sentinel"):
        guard.validate_tabulated_target_dc_power_result(actual, supplied)
    assert len(walked) == stop + 1
    assert assembly_guard.call_count == (scope != "assembly_output_json")
    if assembly_guard.call_count:
        args = assembly_guard.call_args.args
        assert args[0] is actual["outputs"]["assembly"] and args[1] is supplied["assembly"]
    motor_guard.assert_not_called()
    assert (actual, supplied) == before
    for call in calls:
        call.assert_not_called()
