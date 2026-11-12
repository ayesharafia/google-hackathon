"""Actual-point chronology, provenance and bounded failure tests for V118."""

import json
from copy import deepcopy
from decimal import Decimal, localcontext
from unittest.mock import Mock

import pytest

from physimesh.drone import tabulated_target_dc_energy as energy
from physimesh.drone.provenance import sha256_record
from tests.drone import test_tabulated_target_dc_power as fixtures

point, dc = fixtures.bridge, fixtures.dc


def request():
    first, second = fixtures.request(), fixtures.request()
    second["assembly"]["air"]["altitude_m"] = 2500
    for rotor in second["assembly"]["rotors"]:
        rotor["target_template"]["target_thrust_n"] = 120
    for motor in second["motors"]:
        motor["parameters"].update(motor_constant_si=1, terminal_resistance_ohm=0,
                                   zero_torque_current_a=0)
        motor["heat_fraction_of_motor_loss"] = 0
    return {"evaluation": energy.EVALUATION, "segments": [
        {"id": "air", "duration_s": 3, "power_request": first},
        {"id": "second", "duration_s": 7.5, "power_request": second},
    ]}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def test_actual_two_segments_once_full_content_and_transfers(monkeypatch):
    supplied = request()
    original = encoded(supplied)
    direct = [point.evaluate_tabulated_target_dc_power(deepcopy(s["power_request"]))
              for s in supplied["segments"]]
    assert all(p["status"] == "COMPUTED_EXPERIMENTAL" for p in direct)
    calls = fixtures.install_spies(monkeypatch)
    evaluate = Mock(wraps=point.evaluate_tabulated_target_dc_power)
    guard = Mock(wraps=energy.validate_tabulated_target_dc_power_result)
    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", evaluate)
    monkeypatch.setattr(energy, "validate_tabulated_target_dc_power_result", guard)
    result = energy.evaluate_tabulated_target_dc_energy(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL", result["reasons"]
    assert encoded(supplied) == original
    assert evaluate.call_count == guard.call_count == 2
    expected_forwards = sum(p["forward_evaluation_count"] for p in direct)
    for name, expected in (("assembly", 2), ("air", 2), ("inverse", 4),
                           ("trials", expected_forwards), ("kernel", expected_forwards),
                           ("motor", 4), ("compute", 4), ("assembly_guard", 2), ("motor_guard", 8)):
        assert calls[name].call_count == expected, name
    assert result["point_result_count"] == 2
    assert result["assembly_inverse_result_count"] == result["motor_result_count"] == 4
    assert result["forward_evaluation_count"] == expected_forwards
    assert result["request_sha256"] == sha256_record(supplied)
    assert result["evaluation_sha256"] == sha256_record({
        k: v for k, v in result.items() if k != "evaluation_sha256"})
    rows = result["outputs"]["segments"]
    assert len(result["stages"]) == 2 and len(result["transfers"]) == 18
    for i, (segment, actual, row) in enumerate(zip(supplied["segments"], direct, rows, strict=True)):
        assert encoded(row["actual_power_result"]) == encoded(actual)
        assert sha256_record(row["actual_power_result"]) == sha256_record(actual)
        assert encoded(result).count(encoded(actual)) == 1
        assert row.keys() == {"segment_id", "duration_s", "start_time_s", "end_time_s",
                              "actual_power_result", "energy_j", "cumulative_energy_j"}
        assert type(row["duration_s"]) is type(segment["duration_s"])
        assert result["stages"][i] == {
            "stage": "segment:" + segment["id"], "inputs": segment["power_request"],
            "inputs_sha256": sha256_record(segment["power_request"]),
            "result_sha256": sha256_record(actual),
        }
        for j, (key, field) in enumerate(energy._POWER_FIELDS.items()):
            assert result["transfers"][9 * i + j] == {
                "from_stage": "segment:" + segment["id"], "from_field": "outputs.power." + field,
                "to_stage": "energy", "to_field": f"outputs.segments[{i}].energy_j.{key}",
                "value": actual["outputs"]["power"][field], "unit": "W",
                "producer_result_sha256": sha256_record(actual),
                "consumer_request_sha256": sha256_record(supplied),
            }
    ideal = rows[1]["actual_power_result"]["outputs"]["power"]
    for motor in ideal["motors"]:
        assert type(motor["actual_motor_request"]["parameters"]["terminal_resistance_ohm"]) is int
        assert motor["actual_motor_result"]["outputs"]["total_loss_w"] == 0
    assert result["outputs"]["elapsed_s"] == 10.5
    assert [(r["start_time_s"], r["end_time_s"]) for r in rows] == [(0, 3), (3, 10.5)]
    assert result["output_units"] == energy.tabulated_target_dc_energy_catalog()["output_field_units"]


def test_actual_decimal80_individual_cumulative_totals_and_wh():
    supplied = request()
    result = energy.evaluate_tabulated_target_dc_energy(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    with localcontext() as context:
        context.prec = 80
        cumulative = dict.fromkeys(energy._POWER_FIELDS, Decimal(0))
        for segment, row in zip(supplied["segments"], result["outputs"]["segments"], strict=True):
            for key, field in energy._POWER_FIELDS.items():
                watts = Decimal.from_float(float(row["actual_power_result"]["outputs"]["power"][field]))
                joules = watts * Decimal.from_float(float(segment["duration_s"]))
                cumulative[key] += joules
                assert row["energy_j"][key] == pytest.approx(float(joules), rel=3e-16, abs=0)
                assert row["cumulative_energy_j"][key] == pytest.approx(float(cumulative[key]), rel=3e-16, abs=0)
        for key, joules in cumulative.items():
            assert result["outputs"]["totals_j"][key] == pytest.approx(float(joules), rel=3e-16, abs=0)
            assert result["outputs"]["totals_wh"][key] == pytest.approx(float(joules / 3600), rel=4e-16, abs=0)


def assert_atomic(result, status, trusted=(), *, preflight=False):
    assert result["status"] == status
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == result["transfers"] == []
    assert result["diagnostics_complete"] is False
    assert result["point_result_count"] == len(trusted)
    for key in ("assembly_inverse_result_count", "forward_evaluation_count", "motor_result_count"):
        assert result[key] == sum(p[key] for p in trusted)
    if preflight:
        assert result["request_sha256"] is result["evaluation_sha256"] is None
    elif status == "MODEL_INAPPLICABLE":
        assert result["request_sha256"] is not None and result["evaluation_sha256"] is None
    else:
        assert result["evaluation_sha256"] == sha256_record({
            k: v for k, v in result.items() if k != "evaluation_sha256"})
    assert "private injected" not in str(result)


_BAD_FIELDS = [
    (("segments", 1, "duration_s"), value)
    for value in (True, False, None, "3", [], {}, 0, -1, float("inf"), float("nan"), 5e-324, 1 << 1023)
] + [
    (("segments", 1, "id"), value) for value in (None, True, 2, [], {}, "", " \t", "air", "x" * 1993)
] + [
    (("segments", 1, "power_request"), value) for value in (None, [], {}, True)
] + [
    (("segments", 1, "power_request", "evaluation"), value) for value in (False, None, "other")
] + [
    (("segments", 1, "power_request", "motors", 1, "parameters", "motor_constant_si"), value)
    for value in (True, 0, -1, None, "1", 5e-324)
] + [
    (("segments", 1, "power_request", "motors", 1, "id"), "wrong"),
    (("segments", 1, "power_request", "motors", 1, "heat_source"), " "),
    (("segments", 1, "power_request", "motors", 1, "heat_fraction_of_motor_loss"), 1.1),
    (("segments", 1, "power_request", "motors", 1, "declared_limits", "limit_source"), ""),
    (("segments", 1, "power_request", "motors", 1, "declared_limits", "maximum_current_a"), 0),
    (("segments", 1, "power_request", "motors", 1, "parameters", "parameter_source"), ""),
    (("segments", 1, "power_request", "auxiliary", "source"), ""),
    (("segments", 1, "power_request", "assembly", "rotors", 1, "id"), "air"),
    (("segments", 1, "power_request", "assembly", "air", "altitude_m"), True),
]


@pytest.mark.parametrize("path,value", _BAD_FIELDS)
def test_late_preflight_invalid_zero_all_calls(monkeypatch, path, value):
    supplied = request()
    owner = supplied
    for key in path[:-1]:
        owner = owner[key]
    owner[path[-1]] = value
    calls = fixtures.install_spies(monkeypatch)
    evaluator = Mock(wraps=point.evaluate_tabulated_target_dc_power)
    guard = Mock(wraps=energy.validate_tabulated_target_dc_power_result)
    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", evaluator)
    monkeypatch.setattr(energy, "validate_tabulated_target_dc_power_result", guard)
    actual = energy.evaluate_tabulated_target_dc_energy(supplied)
    assert_atomic(actual, "MODEL_INAPPLICABLE", preflight=True)
    for call in (*calls.values(), evaluator, guard):
        call.assert_not_called()


@pytest.mark.parametrize("case", ["root_list", "root_extra", "root_missing", "evaluation_type", "unsupported",
                                  "segments_dict", "segments_empty", "segments_nine", "segment_extra",
                                  "segment_missing", "segment_list", "point_extra", "point_missing"])
def test_exact_shapes_zero_calls(monkeypatch, case):
    supplied = request()
    if case == "root_list":
        supplied = []
    elif case == "root_extra":
        supplied["extra"] = 1
    elif case == "root_missing":
        supplied.pop("segments")
    elif case in ("evaluation_type", "unsupported"):
        supplied["evaluation"] = None if case == "evaluation_type" else "other"
    elif case == "segments_dict":
        supplied["segments"] = {}
    elif case == "segments_empty":
        supplied["segments"] = []
    elif case == "segments_nine":
        supplied["segments"] = [{**deepcopy(supplied["segments"][0]), "id": str(i)} for i in range(9)]
    elif case == "segment_list":
        supplied["segments"][1] = []
    else:
        owner = supplied["segments"][1]
        if case.startswith("point"):
            owner = owner["power_request"]
        if case.endswith("extra"):
            owner["extra"] = 1
        else:
            owner.pop("duration_s" if case.startswith("segment") else "auxiliary")
    calls = fixtures.install_spies(monkeypatch)
    evaluator = Mock(wraps=point.evaluate_tabulated_target_dc_power)
    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", evaluator)
    actual = energy.evaluate_tabulated_target_dc_energy(supplied)
    assert_atomic(actual, "SOLVER_UNSUPPORTED" if case == "unsupported" else "MODEL_INAPPLICABLE",
                  preflight=True)
    for call in (*calls.values(), evaluator):
        call.assert_not_called()


def test_id_1992_boundary_and_catalog():
    supplied = request()
    supplied["segments"][0]["id"] = "x" * 1992
    actual = energy.evaluate_tabulated_target_dc_energy(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL"
    assert len(actual["stages"][0]["stage"]) == 2000
    assert "1992" in energy.tabulated_target_dc_energy_catalog()["request_contract"]["shape"]


def test_actual_eight_segments_counts(monkeypatch):
    supplied = request()
    supplied["segments"] = [{**deepcopy(supplied["segments"][0]), "id": str(i), "duration_s": i + 1}
                            for i in range(8)]
    calls = fixtures.install_spies(monkeypatch)
    evaluator = Mock(wraps=point.evaluate_tabulated_target_dc_power)
    guard = Mock(wraps=energy.validate_tabulated_target_dc_power_result)
    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", evaluator)
    monkeypatch.setattr(energy, "validate_tabulated_target_dc_power_result", guard)
    actual = energy.evaluate_tabulated_target_dc_energy(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL"
    assert actual["point_result_count"] == evaluator.call_count == guard.call_count == 8
    assert actual["assembly_inverse_result_count"] == actual["motor_result_count"] == 16
    assert calls["air"].call_count == calls["assembly"].call_count == 8
    assert calls["inverse"].call_count == calls["motor"].call_count == calls["compute"].call_count == 16
    assert calls["kernel"].call_count == calls["trials"].call_count == actual["forward_evaluation_count"]
    assert actual["outputs"]["elapsed_s"] == 36
    assert len(actual["transfers"]) == 72
    for row in actual["outputs"]["segments"]:
        assert row["end_time_s"] > row["start_time_s"]


def test_limit_exceedance_still_computed():
    supplied = request()
    for motor in supplied["segments"][1]["power_request"]["motors"]:
        motor["declared_limits"]["maximum_angular_speed_rad_s"] = 1
    actual = energy.evaluate_tabulated_target_dc_energy(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL"
    assert actual["outputs"]["all_motors_within_declared_limits"] is False
    assert actual["diagnostics_complete"] is True
    assert actual["aircraft_status"] is actual["feasibility"] is None
    for key in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert actual[key] == "NOT_ESTABLISHED"


def numerical_target(supplied):
    import math
    import sys

    target = supplied["assembly"]["rotors"][0]["target_template"]
    lo, hi = 150.0, math.nextafter(150.0, math.inf)
    density = fixtures.assembly.reference_air_properties(**supplied["assembly"]["air"]).state.density_kg_m3
    thrusts = [fixtures.forward.evaluate_tabulated_hover_bemt({
        **deepcopy(target["rotor_template"]), "density_kg_m3": density,
        "angular_speed_rad_s": omega})["outputs"]["thrust_n"] for omega in (lo, hi)]
    middle = thrusts[0] + (thrusts[1] - thrusts[0]) / 2
    assert thrusts[0] < middle < thrusts[1]
    target.update(angular_speed_bracket_rad_s=[lo, hi], target_thrust_n=middle,
                  absolute_thrust_tolerance_n=sys.float_info.min)


@pytest.mark.parametrize("late", [False, True])
@pytest.mark.parametrize("case,status", [("unbracketed", "TARGET_NOT_BRACKETED"),
                                        ("iteration", "ITERATION_LIMIT"),
                                        ("domain", "MODEL_INAPPLICABLE"),
                                        ("numerical", "NUMERICAL_LIMIT"),
                                        ("execution", "EXECUTION_FAILED")])
def test_actual_noncomputed_point_inclusive_counts_and_stop(monkeypatch, late, case, status):
    supplied = request()
    # Use the same known adjacent-speed fixture at either chronological position.
    supplied["segments"][1]["power_request"] = deepcopy(supplied["segments"][0]["power_request"])
    index = int(late)
    failed_request = supplied["segments"][index]["power_request"]
    target = failed_request["assembly"]["rotors"][0]["target_template"]
    if case == "unbracketed":
        target["target_thrust_n"] = 1e12
    elif case == "iteration":
        target["max_evaluations"] = 2
    elif case == "domain":
        target["rotor_template"]["stations"][0]["chord_m"] = -1
    elif case == "numerical":
        numerical_target(failed_request)
    prefix = [point.evaluate_tabulated_target_dc_power(deepcopy(s["power_request"]))
              for s in supplied["segments"][:index]]
    with monkeypatch.context() as patch:
        if case == "execution":
            patch.setattr(dc, "_compute", Mock(side_effect=RuntimeError("private injected motor fault")))
        failure = point.evaluate_tabulated_target_dc_power(deepcopy(failed_request))
    assert failure["status"] == status
    assert energy.validate_tabulated_target_dc_power_result(failure, failed_request) is None
    supplied["segments"].append({**deepcopy(supplied["segments"][0]), "id": "never_called"})
    returned = prefix + [failure]
    evaluator = Mock(side_effect=deepcopy(returned))
    guard = Mock(wraps=energy.validate_tabulated_target_dc_power_result)
    calls = fixtures.install_spies(monkeypatch)
    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", evaluator)
    monkeypatch.setattr(energy, "validate_tabulated_target_dc_power_result", guard)
    actual = energy.evaluate_tabulated_target_dc_energy(supplied)
    assert_atomic(actual, status, returned)
    assert actual["request_sha256"] == sha256_record(supplied)
    assert actual["reasons"] == [energy._REASONS["point"]]
    assert evaluator.call_count == guard.call_count == index + 1
    for call in calls.values():
        # Pure V117 validation reuses arithmetic guards but executes no model.
        if call is not calls["motor_guard"]:
            call.assert_not_called()


@pytest.fixture(scope="module")
def actual_capture():
    supplied = request()
    return supplied, [point.evaluate_tabulated_target_dc_power(deepcopy(s["power_request"]))
                      for s in supplied["segments"]]


@pytest.mark.parametrize("late", [False, True])
@pytest.mark.parametrize("case", ["missing", "extra", "hash", "count", "total", "units", "assembly",
                                  "motor", "stage", "transfer", "guard_non_none"])
def test_invalid_actual_point_atomic_excludes_point(monkeypatch, actual_capture, late, case):
    supplied, captured = deepcopy(actual_capture)
    index = int(late)
    malformed = captured[index]
    if case == "missing":
        malformed.pop("runtime_identity")
    elif case == "extra":
        malformed["extra"] = 1
    elif case == "hash":
        malformed["evaluation_sha256"] = "0" * 64
    elif case == "count":
        malformed["motor_result_count"] = float(malformed["motor_result_count"])
    elif case == "total":
        malformed["outputs"]["power"]["total_electrical_power_w"] += 1
    elif case == "units":
        malformed["output_units"]["power"]["total_heat_w"] = "J"
    elif case == "assembly":
        malformed["outputs"]["assembly"]["outputs"]["air"]["state"]["pressure_pa"] += 1
    elif case == "motor":
        malformed["outputs"]["power"]["motors"][0]["actual_motor_result"]["outputs"]["current_a"] += 1
    elif case == "stage":
        malformed["stages"][0]["inputs"]["mass_kg"] += 1
    elif case == "transfer":
        malformed["transfers"][0]["value"] += 1
    if case not in ("hash", "guard_non_none"):
        malformed["evaluation_sha256"] = sha256_record({
            k: v for k, v in malformed.items() if k != "evaluation_sha256"})
    evaluator = Mock(side_effect=captured)
    original = energy.validate_tabulated_target_dc_power_result
    count = 0

    def guard(actual, expected):
        nonlocal count
        count += 1
        if case == "guard_non_none" and count == index + 1:
            original(actual, expected)
            return False
        return original(actual, expected)

    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", evaluator)
    monkeypatch.setattr(energy, "validate_tabulated_target_dc_power_result", guard)
    actual = energy.evaluate_tabulated_target_dc_energy(supplied)
    assert_atomic(actual, "EXECUTION_FAILED", captured[:index])
    assert actual["reasons"] == [energy._REASONS["execution"]]
    assert evaluator.call_count == count == index + 1


@pytest.mark.parametrize("late", [False, True])
@pytest.mark.parametrize("dependency", ["model", "guard"])
@pytest.mark.parametrize("error_type", [RuntimeError, ValueError, KeyboardInterrupt])
def test_dependency_exceptions_preserve_trusted_counts(monkeypatch, actual_capture, late, dependency, error_type):
    supplied, captured = deepcopy(actual_capture)
    index, model_calls, guard_calls = int(late), 0, 0
    original = energy.validate_tabulated_target_dc_power_result

    def evaluate(_request):
        nonlocal model_calls
        current = model_calls
        model_calls += 1
        if dependency == "model" and current == index:
            raise error_type("private injected exception")
        return captured[current]

    def guard(actual, expected):
        nonlocal guard_calls
        current = guard_calls
        guard_calls += 1
        if dependency == "guard" and current == index:
            raise error_type("private injected exception")
        return original(actual, expected)

    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", evaluate)
    monkeypatch.setattr(energy, "validate_tabulated_target_dc_power_result", guard)
    if error_type is KeyboardInterrupt:
        with pytest.raises(KeyboardInterrupt, match="private injected"):
            energy.evaluate_tabulated_target_dc_energy(supplied)
    else:
        actual = energy.evaluate_tabulated_target_dc_energy(supplied)
        assert_atomic(actual, "EXECUTION_FAILED", captured[:index])
        assert actual["request_sha256"] == sha256_record(supplied)
        assert actual["reasons"] == [energy._REASONS["execution"]]
    assert model_calls == index + 1
    assert guard_calls == index + int(dependency == "guard")


def test_immediate_full_snapshot_before_guard_detaches_actual(monkeypatch, actual_capture):
    supplied, captured = deepcopy(actual_capture)
    saved = deepcopy(captured)
    evaluator = Mock(side_effect=captured)
    original, seen = energy.validate_tabulated_target_dc_power_result, []

    def guard(actual, expected):
        index = len(seen)
        assert actual is not captured[index]
        assert actual["outputs"] is not captured[index]["outputs"]
        assert encoded(actual) == encoded(saved[index])
        # Mutating the external returned object during the guard cannot change the retained snapshot.
        captured[index]["outputs"].clear()
        seen.append(actual)
        return original(actual, expected)

    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", evaluator)
    monkeypatch.setattr(energy, "validate_tabulated_target_dc_power_result", guard)
    result = energy.evaluate_tabulated_target_dc_energy(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert len(seen) == 2
    for row, actual in zip(result["outputs"]["segments"], saved, strict=True):
        assert encoded(row["actual_power_result"]) == encoded(actual)


@pytest.mark.parametrize("case", ["multiply_overflow", "wh_underflow", "elapsed_resolution", "sum_resolution"])
def test_actual_point_arithmetic_failures_after_guard(monkeypatch, case):
    import sys

    supplied = request()
    if case == "multiply_overflow":
        supplied["segments"][0]["duration_s"] = 1e308
        expected_count = 1
    elif case == "wh_underflow":
        supplied["segments"] = supplied["segments"][:1]
        # Actual auxiliary demand of 1 W and min-normal duration: normal J, subnormal Wh.
        supplied["segments"][0]["duration_s"] = sys.float_info.min
        supplied["segments"][0]["power_request"]["auxiliary"].update(power_w=1, heat_fraction=0)
        expected_count = 1
    else:
        supplied["segments"][0]["duration_s"] = 1e16
        supplied["segments"][1]["duration_s"] = 1 if case == "elapsed_resolution" else 1e-10
        expected_count = 2
    captured = [point.evaluate_tabulated_target_dc_power(deepcopy(s["power_request"]))
                for s in supplied["segments"]]
    assert all(p["status"] == "COMPUTED_EXPERIMENTAL" for p in captured)
    evaluator = Mock(side_effect=deepcopy(captured))
    guard = Mock(wraps=energy.validate_tabulated_target_dc_power_result)
    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", evaluator)
    monkeypatch.setattr(energy, "validate_tabulated_target_dc_power_result", guard)
    actual = energy.evaluate_tabulated_target_dc_energy(supplied)
    assert_atomic(actual, "EXECUTION_FAILED", captured[:expected_count])
    assert evaluator.call_count == guard.call_count == expected_count
    assert actual["reasons"] == [energy._REASONS["execution"]]


def endpoint_power_request(rotors=8, budget=8):
    supplied = fixtures.request()
    rotor = supplied["assembly"]["rotors"][0]
    template = rotor["target_template"]["rotor_template"]
    template["annuli"] = 512
    density = fixtures.assembly.reference_air_properties(**supplied["assembly"]["air"]).state.density_kg_m3
    actual = fixtures.forward.evaluate_tabulated_hover_bemt({
        **deepcopy(template), "density_kg_m3": density, "angular_speed_rad_s": 50.0})
    assert actual["status"] == "COMPUTED_EXPERIMENTAL"
    rotor["target_template"].update(target_thrust_n=actual["outputs"]["thrust_n"], max_evaluations=budget)
    supplied["assembly"]["rotors"] = [{**deepcopy(rotor), "id": f"r{i}"} for i in range(rotors)]
    supplied["motors"] = [{**deepcopy(supplied["motors"][0]), "id": f"r{i}"} for i in range(rotors)]
    return supplied


def test_actual_two_points_maximum_declared_work(monkeypatch):
    power_request = endpoint_power_request()
    supplied = {"evaluation": energy.EVALUATION, "segments": [
        {"id": str(i), "duration_s": i + 1, "power_request": deepcopy(power_request)} for i in range(2)]}
    calls = fixtures.install_spies(monkeypatch)
    evaluator = Mock(wraps=point.evaluate_tabulated_target_dc_power)
    guard = Mock(wraps=energy.validate_tabulated_target_dc_power_result)
    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", evaluator)
    monkeypatch.setattr(energy, "validate_tabulated_target_dc_power_result", guard)
    actual = energy.evaluate_tabulated_target_dc_energy(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL", actual["reasons"]
    assert actual["point_result_count"] == evaluator.call_count == guard.call_count == 2
    assert actual["assembly_inverse_result_count"] == actual["motor_result_count"] == 16
    assert actual["forward_evaluation_count"] == calls["kernel"].call_count == 32
    assert sum(r["target_template"]["max_evaluations"] * r["target_template"]["rotor_template"]["annuli"]
               for s in supplied["segments"] for r in s["power_request"]["assembly"]["rotors"]) == 65536


@pytest.mark.parametrize("excess", [0, 1])
def test_global_work_exact_boundary_preflight_only_probe(monkeypatch, excess):
    # Declared work admission probe, not a claim of executing this maximum fixture.
    first = endpoint_power_request()
    second = deepcopy(first)
    # Six 8*512 rotors + 2*511 + 64*112 = 32766.
    for rotor, annuli, budget in zip(second["assembly"]["rotors"],
                                    [512] * 6 + [511, 112], [8] * 6 + [2, 64], strict=True):
        rotor["target_template"]["rotor_template"]["annuli"] = annuli
        rotor["target_template"]["max_evaluations"] = budget
    last = fixtures.request()
    last["assembly"]["rotors"] = last["assembly"]["rotors"][:1]
    last["motors"] = last["motors"][:1]
    last["assembly"]["rotors"][0]["target_template"].update(max_evaluations=2 + excess)
    last["assembly"]["rotors"][0]["target_template"]["rotor_template"]["annuli"] = 1
    supplied = {"evaluation": energy.EVALUATION, "segments": [
        {"id": str(i), "duration_s": 1, "power_request": p} for i, p in enumerate((first, second, last))]}
    total = sum(r["target_template"]["max_evaluations"] * r["target_template"]["rotor_template"]["annuli"]
                for s in supplied["segments"] for r in s["power_request"]["assembly"]["rotors"])
    assert total == 65536 + excess
    calls = fixtures.install_spies(monkeypatch)
    evaluator = Mock(side_effect=RuntimeError("private injected admission endpoint"))
    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", evaluator)
    actual = energy.evaluate_tabulated_target_dc_energy(supplied)
    assert_atomic(actual, "MODEL_INAPPLICABLE" if excess else "EXECUTION_FAILED", preflight=bool(excess))
    assert evaluator.call_count == int(not excess)
    for call in calls.values():
        call.assert_not_called()


def test_late_point_own_work_limit_precedes_any_call(monkeypatch):
    supplied = request()
    supplied["segments"][1]["power_request"] = endpoint_power_request()
    supplied["segments"][1]["power_request"]["assembly"]["rotors"][0]["target_template"]["max_evaluations"] = 9
    calls = fixtures.install_spies(monkeypatch)
    evaluator = Mock(wraps=point.evaluate_tabulated_target_dc_power)
    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", evaluator)
    assert_atomic(energy.evaluate_tabulated_target_dc_energy(supplied), "MODEL_INAPPLICABLE", preflight=True)
    for call in (*calls.values(), evaluator):
        call.assert_not_called()


def node_tree(nodes, fanout, cache=None):
    """Small aliased builtin tree with exact expanded node count for walker-only probes."""
    cache = {} if cache is None else cache
    if nodes == 1:
        return 0
    if nodes not in cache:
        size = min(fanout, nodes - 1)
        quotient, remainder = divmod(nodes - 1, size)
        cache[nodes] = [node_tree(quotient + int(i < remainder), fanout, cache) for i in range(size)]
    return cache[nodes]


@pytest.mark.parametrize("scope", ["input_json", "output_json", "point_input_json", "point_output_json"])
@pytest.mark.parametrize("resource", ["nodes", "depth", "container", "string", "integer"])
def test_walker_only_exact_resource_boundaries(scope, resource):
    # Helper probes only: these values are not fabricated valid request/result envelopes.
    limits = energy._LIMITS[scope]
    if resource == "nodes":
        admitted = node_tree(limits["max_nodes_including_keys"], limits["max_container_items"])
        refused = node_tree(limits["max_nodes_including_keys"] + 1, limits["max_container_items"])
    elif resource == "depth":
        admitted = 0
        for _ in range(limits["max_depth"] - 1):
            admitted = [admitted]
        refused = [admitted]
    elif resource == "container":
        admitted = [0] * limits["max_container_items"]
        refused = admitted + [0]
    elif resource == "string":
        admitted = "x" * limits["max_string_characters"]
        refused = admitted + "x"
    else:
        admitted = (1 << limits["max_integer_bits"]) - 1
        refused = admitted + 1
    assert energy._json_walk(admitted, limits) is None
    with pytest.raises(ValueError):
        energy._json_walk(refused, limits)


def test_walker_only_keys_and_repeated_aliases_count():
    limits = {**energy._LIMITS["input_json"], "max_nodes_including_keys": 7}
    child = [0, 0]
    assert energy._json_walk([child, child], limits) is None
    with pytest.raises(ValueError):
        energy._json_walk({"key": [child, child]}, limits)


@pytest.mark.parametrize("case", ["nan", "infinity", "utf8", "integer", "string", "depth", "container", "cycle"])
def test_input_resource_refusal_before_copy_and_models(monkeypatch, case):
    import math

    supplied = request()
    values = {"nan": math.nan, "infinity": math.inf, "utf8": "\ud800", "integer": 1 << 1023,
              "string": "x" * 2001, "container": [0] * 257}
    value = values.get(case)
    if case == "depth":
        value = 0
        for _ in range(20):
            value = [value]
    elif case == "cycle":
        value = []
        value.append(value)
    supplied["segments"][1]["power_request"]["auxiliary"]["source"] = value
    copied, original_copy = [], energy.deepcopy

    def copy(actual):
        if actual is supplied:
            copied.append(actual)
        return original_copy(actual)

    evaluator = Mock(wraps=point.evaluate_tabulated_target_dc_power)
    monkeypatch.setattr(energy, "deepcopy", copy)
    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", evaluator)
    assert_atomic(energy.evaluate_tabulated_target_dc_energy(supplied), "MODEL_INAPPLICABLE", preflight=True)
    assert copied == []
    evaluator.assert_not_called()


@pytest.mark.parametrize("builtin", [dict, list, int, float, str])
@pytest.mark.parametrize("scope", ["request", "actual"])
def test_foreign_builtin_subclasses_no_hooks(monkeypatch, actual_capture, builtin, scope):
    supplied, captured = deepcopy(actual_capture)
    hooks = []

    def forbidden(self, *args, **kwargs):
        hooks.append("called")
        raise AssertionError("foreign hook called")

    foreign = type("Foreign", (builtin,), {name: forbidden for name in (
        "__deepcopy__", "__eq__", "__iter__", "__float__", "__int__", "items", "bit_length", "encode")})
    value = foreign({}) if builtin is dict else foreign([]) if builtin is list else foreign(1)
    guard = Mock(wraps=energy.validate_tabulated_target_dc_power_result)
    if scope == "request":
        supplied["segments"][1]["power_request"]["auxiliary"]["source"] = value
        evaluator = Mock(wraps=point.evaluate_tabulated_target_dc_power)
    else:
        captured[0]["outputs"]["power"]["total_heat_w"] = value
        evaluator = Mock(side_effect=captured)
    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", evaluator)
    monkeypatch.setattr(energy, "validate_tabulated_target_dc_power_result", guard)
    actual = energy.evaluate_tabulated_target_dc_energy(supplied)
    assert_atomic(actual, "MODEL_INAPPLICABLE" if scope == "request" else "EXECUTION_FAILED",
                  preflight=scope == "request")
    assert hooks == []
    guard.assert_not_called()
    assert evaluator.call_count == int(scope == "actual")


@pytest.mark.parametrize("scope", ["point_input_json", "point_output_json"])
def test_independent_point_budgets_before_guard(monkeypatch, actual_capture, scope):
    supplied, captured = deepcopy(actual_capture)
    walker, events = energy._json_walk, []

    def walk(actual, limits):
        name = next(name for name, value in energy._LIMITS.items() if value is limits)
        events.append(name)
        if name == scope:
            raise ValueError("private injected independent budget refusal")
        return walker(actual, limits)

    guard = Mock(wraps=energy.validate_tabulated_target_dc_power_result)
    evaluator = Mock(side_effect=captured)
    monkeypatch.setattr(energy, "_json_walk", walk)
    monkeypatch.setattr(energy, "validate_tabulated_target_dc_power_result", guard)
    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", evaluator)
    actual = energy.evaluate_tabulated_target_dc_energy(supplied)
    assert_atomic(actual, "MODEL_INAPPLICABLE" if scope == "point_input_json" else "EXECUTION_FAILED",
                  preflight=scope == "point_input_json")
    assert events[:2] == ["input_json", "input_json"]
    assert scope in events
    assert evaluator.call_count == int(scope == "point_output_json")
    guard.assert_not_called()


def test_full_actual_walk_copy_walk_guard_order(monkeypatch, actual_capture):
    supplied, captured = deepcopy(actual_capture)
    events, walker, copier = [], energy._json_walk, energy.deepcopy
    original_guard = energy.validate_tabulated_target_dc_power_result

    def walk(actual, limits):
        if limits is energy._LIMITS["point_output_json"]:
            events.append("walk")
        return walker(actual, limits)

    def copy(actual):
        if any(actual is item for item in captured):
            events.append("copy")
        return copier(actual)

    def guard(actual, expected):
        events.append("guard")
        return original_guard(actual, expected)

    monkeypatch.setattr(energy, "_json_walk", walk)
    monkeypatch.setattr(energy, "deepcopy", copy)
    monkeypatch.setattr(energy, "validate_tabulated_target_dc_power_result", guard)
    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", Mock(side_effect=captured))
    assert energy.evaluate_tabulated_target_dc_energy(supplied)["status"] == "COMPUTED_EXPERIMENTAL"
    assert events == ["walk", "copy", "walk", "guard"] * 2


def test_catalog_fresh_import_snapshot_no_runtime_models(monkeypatch):
    before = energy.tabulated_target_dc_energy_catalog()
    calls = fixtures.install_spies(monkeypatch)
    blocked = Mock(side_effect=AssertionError("runtime catalog/model forbidden"))
    monkeypatch.setattr(point, "tabulated_target_dc_power_catalog", blocked)
    monkeypatch.setattr(point, "evaluate_tabulated_target_dc_power", blocked)
    changed = energy.tabulated_target_dc_energy_catalog()
    changed["point_catalog"]["input_units"].clear()
    changed["limits"]["point_output_json"]["max_depth"] = 0
    changed["output_field_units"]["totals_j"].clear()
    changed["power_fields"].clear()
    assert energy.tabulated_target_dc_energy_catalog() == before
    blocked.assert_not_called()
    for call in calls.values():
        call.assert_not_called()
