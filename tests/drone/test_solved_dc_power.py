import math
from copy import deepcopy

import pytest

from physimesh.drone import solved_dc_power as m
from physimesh.drone.provenance import sha256_record

from .test_dc_motor import request as motor_request
from .test_static_wrench_solve import request as solve_request


@pytest.fixture
def bridge_request():
    motor = motor_request()
    motor["parameters"].update(motor_constant_si=.1, terminal_resistance_ohm=.2,
                               zero_torque_current_a=1)
    for key in motor["declared_limits"]:
        if key != "limit_source":
            motor["declared_limits"][key] = 1e6
    solve = solve_request()
    return {
        "evaluation": m.EVALUATION, "solve": solve,
        "motors": [{"node": rotor["node"], "parameters": deepcopy(motor["parameters"]),
                    "declared_limits": deepcopy(motor["declared_limits"]),
                    "heat_fraction_of_motor_loss": fraction, "heat_source": "Synthetic capture"}
                   for rotor, fraction in zip(solve["assembly_template"]["rotors"], (.25, .75))],
        "auxiliary": {"power_w": 11, "heat_fraction": .5, "source": "Synthetic auxiliary"},
    }


@pytest.fixture
def observed(monkeypatch, bridge_request):
    calls = {key: [] for key in ("shaft", "solve", "graph", "motor")}

    def spy(key, evaluate):
        def wrapped(request):
            saved = deepcopy(request)
            raw = evaluate(request)
            calls[key].append((saved, raw))
            return raw
        return wrapped

    for key, owner, name in (
        ("shaft", m.sp, "evaluate_solved_wrench_power"),
        ("solve", m.sp.ws, "evaluate_static_wrench_solve"),
        ("graph", m.sp.rg, "evaluate_reference_air_graph"),
        ("motor", m.dc, "evaluate_dc_motor"),
    ):
        monkeypatch.setattr(owner, name, spy(key, getattr(owner, name)))
    return bridge_request, calls


def test_actual_selected_point_motor_power_and_provenance(observed):
    request, calls = observed
    before = deepcopy(request)
    result = m.evaluate_solved_dc_power(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert request == before
    assert {key: len(value) for key, value in calls.items()} == {
        "shaft": 1, "solve": 1, "graph": 1, "motor": 2,
    }
    shaftreq, shaft = calls["shaft"][0]
    out, power = result["outputs"], result["outputs"]["power"]
    selected = out["solve"]["selected_candidate"]["angular_speeds_rad_s"]
    assert any(speed != bound["initial_angular_speed_rad_s"]
               for speed, bound in zip(selected, request["solve"]["rotor_speed_bounds"]))
    assert out["solve"] == calls["solve"][0][1]["outputs"]
    assert result["output_units"]["solve"] == shaft["output_units"]["solve"]
    assert result["request_sha256"] == sha256_record(before)
    stage = result["stages"][0]
    assert stage["request_sha256"] == sha256_record(shaftreq)
    assert stage["result_sha256"] == sha256_record(shaft)
    assert stage["stages"] == shaft["stages"]
    for nested, key in zip(stage["stages"], ("solve", "graph")):
        req, raw = calls[key][0]
        assert nested["request_sha256"] == sha256_record(req)
        assert nested["result_sha256"] == sha256_record(raw)
    graph_outputs = calls["graph"][0][1]["outputs"]
    for i, (row, entry, captured) in enumerate(zip(power["motors"], request["motors"], calls["motor"])):
        req, raw = captured
        shaftrow = shaft["outputs"]["power"]["rotors"][i]
        omega, torque = selected[i], graph_outputs[entry["node"]]["shaft_torque_nm"]
        assert row["node"] == entry["node"] == shaftrow["node"]
        assert row["angular_speed_rad_s"] == omega == shaftrow["angular_speed_rad_s"]
        assert row["shaft_torque_nm"] == torque == shaftrow["shaft_torque_nm"]
        assert req["operating_point"] == {"angular_speed_rad_s": omega, "shaft_torque_nm": torque}
        assert row["motor"] == raw["outputs"] == m.dc._compute(req)
        current = torque / .1 + 1
        assert row["motor"]["electrical_power_w"] == pytest.approx((omega * .1 + current * .2) * current)
        loss = row["motor"]["total_loss_w"]
        assert loss == pytest.approx(current * current * .2 + omega * .1)
        assert row["allocated_heat_w"] == loss * entry["heat_fraction_of_motor_loss"]
        assert row["unallocated_loss_w"] == loss - row["allocated_heat_w"]
        assert result["stages"][i + 1]["request_sha256"] == sha256_record(req)
        assert result["stages"][i + 1]["result_sha256"] == sha256_record(raw)
        assert result["transfers"]["motors"][i]["operating_point"] == req["operating_point"]
    for total, field in (("total_shaft_power_w", "shaft_power_w"),
                         ("total_motor_electrical_power_w", "electrical_power_w"),
                         ("total_motor_loss_w", "total_loss_w")):
        assert power[total] == pytest.approx(math.fsum(r["motor"][field] for r in power["motors"]))
    assert power["total_electrical_power_w"] == power["total_motor_electrical_power_w"] + 11
    assert power["auxiliary_electrical_power_w"] == 11 and power["auxiliary_heat_w"] == 5.5
    assert power["total_allocated_motor_heat_w"] == sum(r["allocated_heat_w"] for r in power["motors"])
    assert power["total_unallocated_motor_loss_w"] == sum(r["unallocated_loss_w"] for r in power["motors"])
    assert power["total_allocated_heat_w"] == power["total_allocated_motor_heat_w"] + 5.5
    assert result["output_units"]["power"]["motors"][0]["motor"] == m.dc._units()
    assert result["feasibility"] is None and result["aircraft_status"] is None
    saved = deepcopy(result)
    request["motors"][0]["parameters"]["motor_constant_si"] = 99
    calls["shaft"][0][1]["outputs"]["solve"]["assembly"]["rotors"][0]["force_body_n"][0] = 99
    calls["motor"][0][1]["outputs"]["current_a"] = 99
    assert result == saved
    result["outputs"]["power"]["motors"][1]["motor"]["current_a"] = 99
    assert calls["motor"][1][1]["outputs"]["current_a"] != 99


def test_actual_unmet_solve_skips_motors(observed):
    request, calls = observed
    request["solve"].update(max_evaluations=2, required_net_force_body_n=[1e9, 0, 0])
    result = m.evaluate_solved_dc_power(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["power_state"] == "NOT_RUN_RESIDUAL_UNMET"
    assert result["outputs"]["power"] is None and result["output_units"]["power"] is None
    assert len(calls["shaft"]) == len(calls["solve"]) == 1
    assert calls["motor"] == calls["graph"] == []
    assert result["outputs"]["solve"] == calls["solve"][0][1]["outputs"]
    assert result["stages"][0]["stages"] == calls["shaft"][0][1]["stages"]


def test_ideal_zero_loss_auxiliary_and_fractions(observed):
    request, calls = observed
    request["auxiliary"].update(power_w=0, heat_fraction=0)
    for entry in request["motors"]:
        entry["parameters"].update(terminal_resistance_ohm=0, zero_torque_current_a=0)
        entry["heat_fraction_of_motor_loss"] = 0
    result = m.evaluate_solved_dc_power(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL" and len(calls["motor"]) == 2
    power = result["outputs"]["power"]
    assert power["total_motor_loss_w"] == power["total_allocated_heat_w"] == 0
    assert power["total_unallocated_motor_loss_w"] == power["auxiliary_electrical_power_w"] == 0
    assert power["auxiliary_heat_w"] == 0
    assert power["total_electrical_power_w"] == power["total_motor_electrical_power_w"]
    assert all(r["motor"]["efficiency"] == 1 for r in power["motors"])


def test_exceeded_declared_limits_retain_actual_results(observed):
    request, calls = observed
    for entry in request["motors"]:
        entry["declared_limits"]["maximum_current_a"] = .001
    result = m.evaluate_solved_dc_power(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL" and len(calls["motor"]) == 2
    for row, (_, raw) in zip(result["outputs"]["power"]["motors"], calls["motor"]):
        assert row["motor"] == raw["outputs"]
        assert row["motor"]["declared_limit_status"] == "EXCEEDS_DECLARED_LIMITS"
        assert row["motor"]["limit_checks"]["current"] is False
    assert result["feasibility"] is None and result["aircraft_status"] is None


@pytest.mark.parametrize("path,value", [
    ("evaluation", True), ("evaluation", "wrong"), ("extra", 0), ("motors", {}),
    ("motors.0.extra", 0), ("auxiliary.extra", 0),
    ("motors.0.heat_fraction_of_motor_loss", True),
    ("motors.0.heat_fraction_of_motor_loss", float("nan")),
    ("motors.0.heat_fraction_of_motor_loss", float("inf")),
    ("motors.0.heat_fraction_of_motor_loss", -.1),
    ("motors.0.heat_fraction_of_motor_loss", 1.1),
    ("motors.0.heat_source", " "), ("motors.0.heat_source", "x" * 2001),
    ("motors.0.node", True), ("motors.0.node", "missing"),
    ("motors.0.parameters", {}), ("motors.0.declared_limits", {}),
    ("motors.0.parameters.motor_constant_si", True),
    ("motors.0.parameters.motor_constant_si", 0),
    ("motors.0.parameters.terminal_resistance_ohm", True),
    ("motors.0.parameters.terminal_resistance_ohm", -1),
    ("motors.0.parameters.zero_torque_current_a", True),
    ("motors.0.parameters.zero_torque_current_a", float("inf")),
    ("motors.0.parameters.parameter_source", ""),
    ("motors.0.parameters.applicability_declaration", "wrong"),
    ("motors.0.declared_limits.maximum_current_a", True),
    ("motors.0.declared_limits.maximum_terminal_voltage_v", 0),
    ("motors.0.declared_limits.maximum_angular_speed_rad_s", -1),
    ("motors.0.declared_limits.maximum_shaft_torque_nm", float("nan")),
    ("motors.0.declared_limits.limit_source", " "),
    ("motors.0.operating_point", {"angular_speed_rad_s": 100, "shaft_torque_nm": 2}),
    ("operating_point", {"angular_speed_rad_s": 100, "shaft_torque_nm": 2}),
    ("auxiliary.power_w", True), ("auxiliary.power_w", -1),
    ("auxiliary.power_w", float("nan")), ("auxiliary.power_w", float("inf")),
    ("auxiliary.heat_fraction", True), ("auxiliary.heat_fraction", -.1),
    ("auxiliary.heat_fraction", 1.1), ("auxiliary.heat_fraction", float("nan")),
    ("auxiliary.source", ""), ("auxiliary.source", "x" * 2001),
])
def test_strict_preflight_never_calls_models(observed, path, value):
    request, calls = observed
    parts = [int(p) if p.isdigit() else p for p in path.split(".")]
    parent = request
    for part in parts[:-1]:
        parent = parent[part]
    parent[parts[-1]] = value
    result = m.evaluate_solved_dc_power(request)
    assert result["status"] == "GRAPH_INVALID"
    assert result["diagnostics_complete"] is False
    assert "request_sha256" not in result
    assert all(records == [] for records in calls.values())
    assert result["outputs"] == result["output_units"] == result["transfers"] == {}
    assert result["stages"] == []


@pytest.mark.parametrize("defect", ["order", "duplicate", "count", "workbudget"])
def test_structural_preflight_never_calls_models(observed, defect):
    request, calls = observed
    if defect == "order":
        request["motors"].reverse()
    elif defect == "duplicate":
        request["motors"][1]["node"] = request["motors"][0]["node"]
    elif defect == "count":
        request["motors"].pop()
    else:
        request["solve"]["max_evaluations"] = 64
        for node in request["solve"]["assembly_template"]["graph"]["nodes"]:
            if node["model"] == "isolated_hover_bemt_experimental":
                node["inputs"]["annuli"] = 256
    assert m.evaluate_solved_dc_power(request)["status"] == "GRAPH_INVALID"
    assert all(records == [] for records in calls.values())


@pytest.mark.parametrize("target,defect", [
    ("shaft", "raise"), ("motor1", "raise"), ("motor2", "raise"),
    ("shaft", "hash"), ("shaft", "qualifier"), ("shaft", "shaftrow"),
    ("shaft", "selected"), ("shaft", "units"), ("shaft", "stage"),
    ("motor1", "hash"), ("motor2", "hash"), ("motor1", "qualifier"),
    ("motor1", "diagnostic"), ("motor1", "number"), ("motor2", "number"),
    ("motor1", "boolnumber"), ("motor1", "efficiency"), ("motor1", "units"),
    ("motor1", "checks"), ("motor1", "status"),
    ("motor1", "stage"), ("motor2", "transfers"),
])
def test_runtime_and_forged_results_fail_atomically(observed, monkeypatch, target, defect):
    request, calls = observed
    expected_hash = sha256_record(request)
    original_shaft, original_motor = m.sp.evaluate_solved_wrench_power, m.dc.evaluate_dc_motor
    attempts = []

    def corrupt(raw):
        raw = deepcopy(raw)
        if defect == "hash":
            raw["request_sha256"] = "0" * 64
        elif defect == "qualifier":
            raw["physical_validation"] = True
        elif defect == "diagnostic":
            raw["diagnostics_complete"] = 1
        elif defect == "shaftrow":
            raw["outputs"]["power"]["rotors"][0]["shaft_torque_nm"] *= 1.1
        elif defect == "selected":
            raw["outputs"]["solve"]["selected_candidate"]["max_scaled_residual"] = True
        elif defect == "number":
            raw["outputs"]["electrical_power_w"] += 1
        elif defect == "boolnumber":
            raw["outputs"]["current_a"] = True
        elif defect == "efficiency":
            raw["outputs"]["efficiency"] = True
        elif defect == "units":
            if target == "shaft":
                raw["output_units"]["power"]["rotors"][0]["shaft_power_w"] = "J"
            else:
                raw["output_units"]["electrical_power_w"] = "J"
        elif defect == "checks":
            raw["outputs"]["limit_checks"]["current"] = 1
        elif defect == "status":
            raw["outputs"]["declared_limit_status"] = "EXCEEDS_DECLARED_LIMITS"
        elif defect == "stage":
            raw["stages"] = [{"stage_id": "forged"}]
        elif defect == "transfers":
            raw["transfers"] = ["forged"]
        return raw

    def shaft(req):
        if target == "shaft" and defect == "raise":
            raise RuntimeError("private shaft detail")
        raw = original_shaft(req)
        return corrupt(raw) if target == "shaft" else raw

    def motor(req):
        attempts.append(deepcopy(req))
        affected = target == f"motor{len(attempts)}"
        if affected and defect == "raise":
            raise RuntimeError("private motor detail")
        raw = original_motor(req)
        return corrupt(raw) if affected else raw

    monkeypatch.setattr(m.sp, "evaluate_solved_wrench_power", shaft)
    monkeypatch.setattr(m.dc, "evaluate_dc_motor", motor)
    result = m.evaluate_solved_dc_power(request)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == expected_hash
    assert result["diagnostics_complete"] is False
    assert result["outputs"] == result["output_units"] == result["transfers"] == {}
    assert type(result["stages"]) is list and result["stages"] == []
    assert "private" not in str(result["reasons"])
    assert len(attempts) == {"shaft": 0, "motor1": 1, "motor2": 2}[target]
    assert len(calls["motor"]) == len(attempts) - (defect == "raise" and target != "shaft")


@pytest.mark.parametrize("target", ["shaft", "motor"])
def test_baseexception_propagates(observed, monkeypatch, target):
    request, _ = observed

    def interrupted(_request):
        raise KeyboardInterrupt("interrupt")

    owner, name = (m.sp, "evaluate_solved_wrench_power") if target == "shaft" else (m.dc, "evaluate_dc_motor")
    monkeypatch.setattr(owner, name, interrupted)
    with pytest.raises(KeyboardInterrupt):
        m.evaluate_solved_dc_power(request)


@pytest.mark.parametrize("path", [
    ("auxiliary", "power_w"),
    ("auxiliary", "heat_fraction"),
    ("motors", 0, "heat_fraction_of_motor_loss"),
])
def test_subnormal_preflight_never_calls_models(observed, path):
    request, calls = observed
    parent = request
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = 5e-324
    result = m.evaluate_solved_dc_power(request)
    assert result["status"] == "GRAPH_INVALID"
    assert result["diagnostics_complete"] is False
    assert "request_sha256" not in result
    assert all(records == [] for records in calls.values())


@pytest.mark.parametrize("case", ["auxiliary_resolution", "motor_overflow", "heat_subnormal"])
def test_derived_arithmetic_fails_atomically(observed, case):
    request, _ = observed
    if case == "auxiliary_resolution":
        request["auxiliary"]["power_w"] = 1e308
    elif case == "motor_overflow":
        request["motors"][0]["parameters"]["terminal_resistance_ohm"] = 1e308
    else:
        for entry in request["motors"]:
            entry["parameters"].update(terminal_resistance_ohm=0, zero_torque_current_a=1e-4)
            entry["heat_fraction_of_motor_loss"] = 2.2250738585072014e-308
    expected_hash = sha256_record(request)
    result = m.evaluate_solved_dc_power(request)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["diagnostics_complete"] is False
    assert result["request_sha256"] == expected_hash
    for key in ("outputs", "output_units", "transfers"):
        assert type(result[key]) is dict and result[key] == {}
    assert type(result["stages"]) is list and result["stages"] == []
