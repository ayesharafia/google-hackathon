"""Captured actual V114 results, followed by validation with models blocked."""

import importlib
import math
import sys
from copy import deepcopy
from dataclasses import asdict
from unittest.mock import Mock

import pytest

from physimesh.drone import tabulated_thrust_target_assembly_validation as guard
from physimesh.drone.provenance import sha256_record
from tests.drone import test_tabulated_thrust_target_assembly as fixtures

workflow, inverse, forward = fixtures.workflow, fixtures.inverse, fixtures.forward


def blocked_check(monkeypatch, actual, supplied, *, rejects=False):
    before_actual, before_request = deepcopy(actual), deepcopy(supplied)
    calls = []
    for name in ("reference_air_properties", "standard_atmosphere", "reference_air_tabulated_hover",
                 "reference_air_tabulated_hover_thrust_target", "tabulated_hover_bemt",
                 "tabulated_hover_bemt_request", "tabulated_hover_thrust_target",
                 "tabulated_rotor_assembly", "tabulated_thrust_target_assembly"):
        module = importlib.import_module("physimesh.drone." + name)
        for field in vars(module).copy():
            if (field.startswith("evaluate_") or field.endswith("_catalog")
                    or field in ("reference_air_properties", "standard_atmosphere", "solve_tabulated_hover")):
                call = Mock(side_effect=AssertionError("runtime call: " + name + "." + field))
                monkeypatch.setattr(module, field, call)
                calls.append(call)
    if rejects:
        with pytest.raises(ValueError):
            guard.validate_tabulated_thrust_target_assembly_result(actual, supplied)
    else:
        assert guard.validate_tabulated_thrust_target_assembly_result(actual, supplied) is None
    assert actual == before_actual and supplied == before_request
    for call in calls:
        call.assert_not_called()


@pytest.mark.parametrize("maximum", [False, True])
def test_actual_success_without_model_calls(monkeypatch, maximum):
    supplied = fixtures.request()
    if maximum:
        rotor = supplied["rotors"][0]
        template = rotor["target_template"]["rotor_template"]
        template.update(annuli=512, blade_count=32, stations=[
            {"radius_m": i / 255, "chord_m": 0.08 - 0.04 * (i / 255),
             "blade_angle_rad": 0.12 - 0.04 * (i / 255)} for i in range(256)
        ])
        air = asdict(fixtures.reference_air_properties(**supplied["air"]))
        endpoint = forward.evaluate_tabulated_hover_bemt({
            **deepcopy(template), "density_kg_m3": air["state"]["density_kg_m3"],
            "angular_speed_rad_s": 50.0,
        })
        assert endpoint["status"] == "COMPUTED_EXPERIMENTAL"
        rotor["target_template"].update(target_thrust_n=endpoint["outputs"]["thrust_n"], max_evaluations=8)
        supplied["rotors"] = [deepcopy(rotor) for _ in range(8)]
        for i, entry in enumerate(supplied["rotors"]):
            entry.update(id="r" + str(i), rotation_sign=1 if i % 2 == 0 else -1)
        assert sum(r["target_template"]["max_evaluations"] * r["target_template"]["rotor_template"]["annuli"]
                   for r in supplied["rotors"]) == 32768
    actual = workflow.evaluate_tabulated_thrust_target_assembly(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL"
    assert actual["inverse_result_count"] == (8 if maximum else 2)
    blocked_check(monkeypatch, actual, supplied)


@pytest.fixture(scope="module")
def captured_success():
    supplied = fixtures.request()
    actual = workflow.evaluate_tabulated_thrust_target_assembly(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL"
    return actual, supplied


def rehash(actual):
    actual["evaluation_sha256"] = sha256_record({
        k: v for k, v in actual.items() if k != "evaluation_sha256"
    })


@pytest.mark.parametrize("case", ["force", "reaction", "moment", "cg_sign", "net_force", "net_moment",
                                  "gravity", "rows", "row_id", "stages", "stage_id", "stage_inputs",
                                  "stage_input_hash", "stage_result_hash", "producer", "consumer",
                                  "transfer_id", "transfer_value", "transfer_field", "extra_output",
                                  "extra_row", "injected", "inverse_hash", "selected", "selected_digest"])
def test_rehashed_values_and_bindings(monkeypatch, captured_success, case):
    actual, supplied = deepcopy(captured_success)
    outputs = actual["outputs"]
    row, stage, transfer = outputs["rotors"][0], actual["stages"][1], actual["transfers"][0]
    vectors = {"force": (row, "force_body_n"), "reaction": (row, "reaction_torque_body_nm"),
               "moment": (row, "moment_cg_body_nm"), "net_force": (outputs, "net_force_body_n"),
               "net_moment": (outputs, "net_moment_cg_body_nm"), "gravity": (outputs, "gravity_force_body_n")}
    if case in vectors:
        owner, field = vectors[case]
        owner[field][2] += 0.25
    elif case == "cg_sign":
        row["moment_cg_body_nm"] = [-v for v in row["moment_cg_body_nm"]]
    elif case in ("rows", "stages"):
        (outputs["rotors"] if case == "rows" else actual["stages"]).reverse()
    elif case == "row_id":
        row["id"] = "left"
    elif case == "stage_id":
        stage["stage"] = "air"
    elif case == "stage_inputs":
        stage["inputs"]["target_thrust_n"] += 1.0
        stage["inputs_sha256"] = sha256_record(stage["inputs"])
    elif case in ("stage_input_hash", "stage_result_hash"):
        stage["inputs_sha256" if case == "stage_input_hash" else "result_sha256"] = "0" * 64
    elif case in ("producer", "consumer"):
        transfer["producer_result_sha256" if case == "producer" else "consumer_request_sha256"] = "0" * 64
    elif case in ("transfer_id", "transfer_value", "transfer_field"):
        field, value = {"transfer_id": ("to_stage", "air"), "transfer_value": ("value", 1.0),
                        "transfer_field": ("from_field", "density_kg_m3")}[case]
        transfer[field] = value
    elif case in ("extra_output", "extra_row"):
        (outputs if case == "extra_output" else row)["extra"] = None
    elif case == "injected":
        row["actual_target_request"]["rotor_template"]["density_kg_m3"] *= 1.01
    else:
        child = row["actual_target_result"]
        selected = child["outputs"]["actual_forward_result"]
        if case == "inverse_hash":
            child["request_sha256"] = "0" * 64
        elif case == "selected":
            selected["outputs"]["radii_m"][0] += 0.001
            rehash(selected)
            child["trace"][-1]["full_actual_result_sha256"] = sha256_record(selected)
        else:
            child["trace"][-1]["full_actual_result_sha256"] = "0" * 64
        rehash(child)
        stage["result_sha256"] = sha256_record(child)
    rehash(actual)
    blocked_check(monkeypatch, actual, supplied, rejects=True)


@pytest.mark.parametrize("path", [*("state." + key for key in (
    "input_altitude_m", "altitude_kind", "geopotential_altitude_m", "pressure_pa", "temperature_k",
    "density_kg_m3", "model_id", "evidence_status")), "geometric_altitude_m", "dynamic_viscosity_pa_s",
    "speed_of_sound_m_s", "gravity_m_s2", "model_id", "viscosity_model", "sound_model", "gravity_model",
    "physical_qualification", "numerical_qualification", "coherent_pressure_density"])
@pytest.mark.parametrize("wrong_type", [False, True])
def test_raw_air_all_fields(monkeypatch, captured_success, path, wrong_type):
    actual, supplied = deepcopy(captured_success)
    air = actual["outputs"]["air"]
    if path == "coherent_pressure_density":
        for key in ("pressure_pa", "density_kg_m3"):
            air["state"][key] *= 1.01
    else:
        owner, key = (air["state"], path[6:]) if path.startswith("state.") else (air, path)
        value = owner[key]
        owner[key] = (int(value) if type(value) is float else None) if wrong_type else (
            value + 0.1 if type(value) is float else value + " forged")
    actual["stages"][0]["result_sha256"] = sha256_record(air)
    for transfer in actual["transfers"]:
        transfer["producer_result_sha256"] = sha256_record(air)
    rehash(actual)
    blocked_check(monkeypatch, actual, supplied, rejects=True)


@pytest.mark.parametrize("case", [*sorted(guard._ROOT_KEYS - guard._DYNAMIC), "status", "reasons",
    "diagnostics_complete", "inverse_result_count", "forward_evaluation_count", "request_sha256",
    "evaluation_sha256", "air_units", "state_units", "row_units", "request_units", "inverse_units",
    "forward_units", "root_extra"])
def test_rehashed_root_types_units_and_metadata(monkeypatch, captured_success, case):
    actual, supplied = deepcopy(captured_success)
    units = actual["output_units"]
    scopes = {"air_units": units["air"], "state_units": units["air"]["state"],
              "row_units": units["rotors"], "request_units": units["rotors"]["actual_target_request"],
              "inverse_units": units["rotors"]["actual_target_result"]["outputs"],
              "forward_units": units["rotors"]["actual_target_result"]["outputs"]["actual_forward_result"]}
    if case in scopes:
        scopes[case]["extra"] = "1"
    elif case == "root_extra":
        actual["extra"] = None
    else:
        actual[case] = {"status": "MODEL_INAPPLICABLE", "reasons": ["forged"],
                        "inverse_result_count": True, "forward_evaluation_count": 0}.get(case, "forged")
    if case != "evaluation_sha256":
        rehash(actual)
    blocked_check(monkeypatch, actual, supplied, rejects=True)


@pytest.mark.parametrize("dependency", ["_preflight", "hash", "inverse"])
@pytest.mark.parametrize("error", [RuntimeError("unexpected pure dependency"), KeyboardInterrupt()])
def test_unexpected_pure_exceptions_propagate(monkeypatch, captured_success, dependency, error):
    actual, supplied = deepcopy(captured_success)
    owner, name = {"_preflight": (workflow, "_preflight"), "hash": (guard, "sha256_record"),
                   "inverse": (guard, "validate_tabulated_hover_thrust_target_result")}[dependency]
    monkeypatch.setattr(owner, name, Mock(side_effect=error))
    with pytest.raises(type(error)):
        guard.validate_tabulated_thrust_target_assembly_result(actual, supplied)
    assert (actual, supplied) == captured_success


def test_private_catalog_snapshot(monkeypatch, captured_success):
    public = workflow.tabulated_thrust_target_assembly_catalog()
    public["limits"]["output_json"]["max_nodes_including_keys"] = 0
    public["output_field_units"]["air"]["state"].clear()
    public["limitations"].clear()
    actual, supplied = deepcopy(captured_success)
    blocked_check(monkeypatch, actual, supplied)


def test_intermediate_digest_format_only(monkeypatch, captured_success):
    actual, supplied = deepcopy(captured_success)
    child = actual["outputs"]["rotors"][0]["actual_target_result"]
    assert child["evaluation_count"] > 2
    child["trace"][0]["full_actual_result_sha256"] = "0123456789abcdef" * 4
    rehash(child)
    actual["stages"][1]["result_sha256"] = sha256_record(child)
    rehash(actual)
    blocked_check(monkeypatch, actual, supplied)


@pytest.fixture(scope="module")
def failure_captures():
    captures = {}
    for status in ("TARGET_NOT_BRACKETED", "ITERATION_LIMIT",
                   "MODEL_INAPPLICABLE", "EXECUTION_FAILED", "BEFORE_INVERSE"):
        supplied = fixtures.request()
        target = supplied["rotors"][1]["target_template"]
        if status == "TARGET_NOT_BRACKETED":
            for station in target["rotor_template"]["stations"]:
                station["blade_angle_rad"] = 0.0
        elif status == "ITERATION_LIMIT":
            target["max_evaluations"] = 2
        elif status == "MODEL_INAPPLICABLE":
            target["rotor_template"]["stations"][0]["chord_m"] = -1.0
        with pytest.MonkeyPatch.context() as patch:
            if status == "EXECUTION_FAILED":
                target["rotor_template"]["geometry_source"] = "zero_count_fault"
                walk = inverse._JSON

                def fail_before_trial(value, limits, walk=walk):
                    if value.get("geometry_source") == "zero_count_fault":
                        raise RuntimeError("fault after request hash, before trial count")
                    return walk(value, limits)

                patch.setattr(inverse, "_JSON", fail_before_trial)
            elif status == "BEFORE_INVERSE":
                patch.setattr(workflow, "reference_air_properties", Mock(side_effect=RuntimeError("air fault")))
            actual = workflow.evaluate_tabulated_thrust_target_assembly(supplied)
        assert actual["status"] == ("EXECUTION_FAILED" if status == "BEFORE_INVERSE" else status)
        captures[status] = actual, supplied
    return captures


@pytest.mark.parametrize("status", ["TARGET_NOT_BRACKETED", "ITERATION_LIMIT",
                                    "MODEL_INAPPLICABLE", "EXECUTION_FAILED", "BEFORE_INVERSE"])
@pytest.mark.parametrize("change", ["none", "negative", "bool", "inverse_over", "forward_over",
    "below_prefix", "last_bound", "reason", "partial", "computed", "request_null", "hash_null",
    "within_bounds_not_attestation"])
def test_failure_prefix_bounds(monkeypatch, failure_captures, status, change):
    actual, supplied = deepcopy(failure_captures[status])
    budgets = [r["target_template"]["max_evaluations"] for r in supplied["rotors"]]
    n = actual["inverse_result_count"]
    rejects = change not in ("none", "within_bounds_not_attestation")
    if change in ("negative", "bool", "inverse_over"):
        actual["inverse_result_count"] = {"negative": -1, "bool": True, "inverse_over": 3}[change]
    elif change == "forward_over":
        actual["forward_evaluation_count"] = sum(budgets[:n]) + 1
    elif change in ("below_prefix", "last_bound"):
        actual["forward_evaluation_count"] = -1 if n == 0 else (
            2 * (n - 1) - 1 if change == "below_prefix" else {
                "ITERATION_LIMIT": 2 * (n - 1) + budgets[n - 1] - 1,
                "TARGET_NOT_BRACKETED": sum(budgets[:n - 1]) + 3,
                "NUMERICAL_LIMIT": sum(budgets[:n]), "MODEL_INAPPLICABLE": 2 * (n - 1),
                "EXECUTION_FAILED": 2 * (n - 1) - 1,
            }[status])
    elif change in ("reason", "partial", "computed", "request_null"):
        field, value = {"reason": ("reasons", ["Request snapshot failed."]), "partial": ("outputs", {"air": {}}),
                        "computed": ("status", "COMPUTED_EXPERIMENTAL"),
                        "request_null": ("request_sha256", None)}[change]
        actual[field] = value
    elif change == "within_bounds_not_attestation":
        actual["forward_evaluation_count"] = 0 if n == 0 else sum(budgets[:n - 1]) + {
            "TARGET_NOT_BRACKETED": 2, "ITERATION_LIMIT": budgets[n - 1],
            "NUMERICAL_LIMIT": budgets[n - 1] - 1, "MODEL_INAPPLICABLE": 1, "EXECUTION_FAILED": 0,
        }[status]
    if actual["status"] != "MODEL_INAPPLICABLE":
        rehash(actual)
    if change == "hash_null":
        actual["evaluation_sha256"] = "0" * 64 if status == "MODEL_INAPPLICABLE" else None
    blocked_check(monkeypatch, actual, supplied, rejects=rejects)


@pytest.mark.parametrize("budget,count,valid", [(2, 4, False), (3, 3, False), (3, 4, True),
                                              (3, 34, True), (3, 35, False), (32, 63, True), (32, 64, False)])
def test_numerical_prefix_envelope_only(monkeypatch, failure_captures, budget, count, valid):
    # Rehashed envelope consistency only; this does not claim actual numerical-limit execution.
    actual, supplied = deepcopy(failure_captures["TARGET_NOT_BRACKETED"])
    supplied["rotors"][1]["target_template"]["max_evaluations"] = budget
    actual.update(status="NUMERICAL_LIMIT", forward_evaluation_count=count,
                  reasons=["Actual target reached a representable numerical limit."],
                  request_sha256=sha256_record(supplied))
    rehash(actual)
    blocked_check(monkeypatch, actual, supplied, rejects=not valid)


@pytest.mark.parametrize("side", ["actual", "request"])
@pytest.mark.parametrize("case", ["cycle", "depth", "nodes", "items", "utf8", "nan", "inf",
                                  "subclass", "integer", "string"])
def test_resource_walks_before_hooks_or_hash(monkeypatch, captured_success, side, case):
    actual, supplied = deepcopy(captured_success)
    hook = Mock(side_effect=AssertionError("foreign hook"))
    foreign = type("Foreign", (dict,), {"__deepcopy__": hook, "__eq__": hook})
    bad = {"items": [0] * 257, "utf8": "\ud800", "nan": math.nan, "inf": math.inf,
           "subclass": foreign(), "integer": 1 << 1023, "string": "x" * 2001}.get(case)
    if case == "cycle":
        bad = []
        bad.append(bad)
    elif case == "depth":
        bad = 0
        for _ in range(24 if side == "actual" else 14):
            bad = [bad]
    elif case == "nodes":
        bad = [[0] * 256] * 256
        if side == "actual":
            bad = [bad] * 8
    if side == "request":
        supplied = bad
        actual = workflow.evaluate_tabulated_thrust_target_assembly(supplied)
    else:
        actual = bad
    hashing = Mock(side_effect=AssertionError("unbounded data hashed"))
    monkeypatch.setattr(guard, "sha256_record", hashing)
    if side == "actual":
        with pytest.raises(ValueError):
            guard.validate_tabulated_thrust_target_assembly_result(actual, supplied)
    else:
        assert guard.validate_tabulated_thrust_target_assembly_result(actual, supplied) is None
    hashing.assert_not_called()
    hook.assert_not_called()


@pytest.mark.parametrize("case", ["unsupported", "missing", "extra", "overflow", "snapshot", "hash"])
def test_admission_and_infrastructure_hash_matrix(monkeypatch, case):
    supplied = fixtures.request()
    if case == "unsupported":
        supplied.update(evaluation="unsupported", rotors=None)
    elif case == "missing":
        supplied.pop("air")
    elif case == "extra":
        supplied["extra"] = None
    elif case == "overflow":
        supplied["mass_kg"] = 1 << 1023
    with monkeypatch.context() as patch:
        if case in ("snapshot", "hash"):
            original = workflow.deepcopy
            if case == "snapshot":
                patch.setattr(workflow, "deepcopy", lambda value: (_ for _ in ()).throw(RuntimeError())
                              if value is supplied else original(value))
            else:
                patch.setattr(workflow, "sha256_record", Mock(side_effect=RuntimeError()))
        actual = workflow.evaluate_tabulated_thrust_target_assembly(supplied)
    blocked_check(monkeypatch, actual, supplied, rejects=case in ("snapshot", "hash"))


@pytest.mark.parametrize("late", [False, True])
@pytest.mark.parametrize("case", ["zero_angle", "budget", "negative_chord", "inverse_execution",
                                  "air", "inverse", "guard", "invalid_child", "load", "gravity"])
def test_actual_failure_profiles_without_model_calls(monkeypatch, late, case):
    supplied = fixtures.request()
    target = supplied["rotors"][int(late)]["target_template"]
    if case == "zero_angle":
        for station in target["rotor_template"]["stations"]:
            station["blade_angle_rad"] = 0.0
    elif case == "budget":
        target["max_evaluations"] = 2
    elif case == "negative_chord":
        target["rotor_template"]["stations"][0]["chord_m"] = -1.0
    elif case == "load":
        supplied["rotors"][int(late)]["center_body_m"][0] = sys.float_info.max
    elif case == "gravity":
        supplied["mass_kg"] = sys.float_info.max
    with monkeypatch.context() as patch:
        if case in ("air", "inverse", "guard", "invalid_child", "inverse_execution"):
            _, _, direct = fixtures.baseline(supplied)
            error = RuntimeError("private infrastructure detail")
            if case == "inverse_execution":
                trial = inverse.evaluate_tabulated_hover_bemt
                prior = direct[0]["evaluation_count"] if late else 0
                spy = Mock(wraps=trial)
                spy.side_effect = lambda request: (_ for _ in ()).throw(error) if spy.call_count == prior + 1 else trial(request)
                patch.setattr(inverse, "evaluate_tabulated_hover_bemt", spy)
            elif case == "invalid_child":
                bad = deepcopy(direct[int(late)])
                bad["evaluation_count"] = True
                patch.setattr(workflow, "evaluate_tabulated_hover_thrust_target",
                              Mock(side_effect=[direct[0], bad] if late else [bad]))
            else:
                field = {"air": "reference_air_properties", "inverse": "evaluate_tabulated_hover_thrust_target",
                         "guard": "validate_tabulated_hover_thrust_target_result"}[case]
                responses = [None, error] if late and case == "guard" else [error]
                if late and case == "inverse":
                    responses = [direct[0], error]
                patch.setattr(workflow, field, Mock(side_effect=responses))
        actual = workflow.evaluate_tabulated_thrust_target_assembly(supplied)
    assert actual["status"] == {"zero_angle": "TARGET_NOT_BRACKETED", "budget": "ITERATION_LIMIT",
                                "negative_chord": "MODEL_INAPPLICABLE"}.get(case, "EXECUTION_FAILED")
    blocked_check(monkeypatch, actual, supplied)
