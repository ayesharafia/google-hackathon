"""Actual-child chronology, boundary policy and bounded JSON checks for V121."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from physimesh.drone import tabulated_electrothermal as bridge
from physimesh.drone.provenance import sha256_record
from tests.drone import test_tabulated_target_dc_energy as fixtures


def request(conductance):
    supplied = fixtures.request()
    return {
        "evaluation": bridge.EVALUATION, "energy_request": supplied,
        "thermal_body": {"mass_kg": 1, "specific_heat_j_kg_k": 500,
                         "initial_temperature_k": 300, "lumped_biot_number": 0.01,
                         "property_source": "synthetic"},
        "thermal_segments": [{"id": segment["id"], "ambient_temperature_k": 300,
                              "conductance_w_k": conductance}
                             for segment in supplied["segments"]],
    }


def capture_and_check(monkeypatch, supplied):
    encoded = fixtures.encoded
    original = encoded(supplied)
    direct_energy = bridge.energy.evaluate_tabulated_target_dc_energy(
        deepcopy(supplied["energy_request"]))
    assert direct_energy["status"] == "COMPUTED_EXPERIMENTAL", direct_energy["reasons"]
    rows = direct_energy["outputs"]["segments"]
    thermal_request = {
        "evaluation": "lumped_thermal_screening", **supplied["thermal_body"],
        "segments": [{"duration_s": row["duration_s"],
                      "ambient_temperature_k": declared["ambient_temperature_k"],
                      "heat_input_w": row["actual_power_result"]["outputs"]["power"]["total_heat_w"],
                      "conductance_w_k": declared["conductance_w_k"]}
                     for row, declared in zip(rows, supplied["thermal_segments"], strict=True)],
    }
    direct_thermal = bridge.thermal.screen_thermal(deepcopy(thermal_request))
    assert direct_thermal["status"] == "SCREENING_COMPUTED", direct_thermal["reasons"]
    calls = fixtures.fixtures.install_spies(monkeypatch)
    energy_call = Mock(wraps=bridge.energy.evaluate_tabulated_target_dc_energy)
    thermal_call = Mock(wraps=bridge.thermal.screen_thermal)
    integrator = Mock(wraps=bridge.thermal.integrate_segment)
    energy_guard = Mock(wraps=bridge.validate_tabulated_target_dc_energy_result)
    thermal_guard = Mock(wraps=bridge.validate_thermal_result)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    monkeypatch.setattr(bridge.thermal, "integrate_segment", integrator)
    monkeypatch.setattr(bridge, "validate_tabulated_target_dc_energy_result", energy_guard)
    monkeypatch.setattr(bridge, "validate_thermal_result", thermal_guard)
    actual = bridge.evaluate_tabulated_electrothermal(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL", actual["reasons"]
    assert actual["diagnostics_complete"] is True
    assert encoded(supplied) == original
    assert energy_call.call_count == thermal_call.call_count == 1
    assert energy_guard.call_count == thermal_guard.call_count == 1
    assert integrator.call_count == len(rows)
    assert actual["energy_result_count"] == actual["thermal_result_count"] == 1
    assert actual["point_result_count"] == len(rows)
    for key in bridge.energy._COUNTS:
        assert actual[key] == direct_energy[key]
    for name, expected in (
        ("assembly", len(rows)), ("air", len(rows)),
        ("inverse", direct_energy["assembly_inverse_result_count"]),
        ("trials", direct_energy["forward_evaluation_count"]),
        ("kernel", direct_energy["forward_evaluation_count"]),
        ("motor", direct_energy["motor_result_count"]),
        ("compute", direct_energy["motor_result_count"]),
    ):
        assert calls[name].call_count == expected, name
    assert actual["outputs"].keys() == {"energy", "thermal"}
    for name, direct in (("energy", direct_energy), ("thermal", direct_thermal)):
        retained = actual["outputs"][name]
        assert encoded(retained) == encoded(direct)
        assert sha256_record(retained) == sha256_record(direct)
        assert encoded(actual).count(encoded(direct)) == 1
        assert actual["output_units"][name] == {"outputs": direct["output_units"]}
    assert "request_sha256" not in actual["outputs"]["thermal"]
    assert "evaluation_sha256" not in actual["outputs"]["thermal"]
    assert actual["request_sha256"] == sha256_record(supplied)
    assert actual["evaluation_sha256"] == sha256_record({
        key: value for key, value in actual.items() if key != "evaluation_sha256"})
    assert actual["stages"] == [
        {"stage": "energy", "inputs": supplied["energy_request"],
         "inputs_sha256": sha256_record(supplied["energy_request"]),
         "result_sha256": sha256_record(direct_energy)},
        {"stage": "thermal", "inputs": thermal_request,
         "inputs_sha256": sha256_record(thermal_request),
         "result_sha256": sha256_record(direct_thermal)},
    ]
    assert len(actual["transfers"]) == 2 * len(rows)
    for index, (row, segment, thermal_row) in enumerate(zip(
            rows, thermal_request["segments"], direct_thermal["outputs"]["segments"], strict=True)):
        assert thermal_row["heat_input_j"] == row["energy_j"]["total_allocated_heat"]
        assert type(segment["duration_s"]) is type(row["duration_s"])
        for offset, (source, target, unit) in enumerate((
            ("actual_power_result.outputs.power.total_heat_w", "heat_input_w", "W"),
            ("duration_s", "duration_s", "s"),
        )):
            assert actual["transfers"][2 * index + offset] == {
                "from_stage": "energy", "from_field": f"outputs.segments[{index}].{source}",
                "to_stage": "thermal", "to_field": f"segments[{index}].{target}",
                "value": segment[target], "unit": unit,
                "producer_result_sha256": sha256_record(direct_energy),
                "consumer_request_sha256": sha256_record(thermal_request),
            }
    assert actual["aircraft_status"] is actual["feasibility"] is None
    for key in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert actual[key] == "NOT_ESTABLISHED"
    return actual


def test_actual_conducting_chronology_full_retention_and_calls(monkeypatch):
    actual = capture_and_check(monkeypatch, request(2))
    rows = actual["outputs"]["thermal"]["outputs"]["segments"]
    assert rows[1]["start_temperature_k"] == rows[0]["end_temperature_k"]


def test_actual_adiabatic_chronology_full_retention_and_calls(monkeypatch):
    actual = capture_and_check(monkeypatch, request(0))
    outputs = actual["outputs"]["thermal"]["outputs"]
    assert outputs["total_convective_exchange_j"] == 0.0
    assert outputs["final_temperature_k"] > 300


def assert_atomic(actual, reason, trusted=None, *, thermal_count=0, preflight=False):
    assert actual["status"] == "EXECUTION_FAILED"
    assert actual["reasons"] == [bridge._REASONS[reason]]
    assert actual["outputs"] == actual["output_units"] == {}
    assert actual["stages"] == actual["transfers"] == []
    assert actual["diagnostics_complete"] is False
    assert actual["energy_result_count"] == int(trusted is not None)
    assert actual["thermal_result_count"] == thermal_count
    for key in bridge.energy._COUNTS:
        assert actual[key] == (0 if trusted is None else trusted[key])
    assert "private injected" not in str(actual)
    if preflight:
        assert actual["request_sha256"] is actual["evaluation_sha256"] is None
    else:
        assert actual["request_sha256"] is not None
        assert actual["evaluation_sha256"] == sha256_record({
            key: value for key, value in actual.items() if key != "evaluation_sha256"})


def reseal(actual):
    actual["evaluation_sha256"] = sha256_record({
        key: value for key, value in actual.items() if key != "evaluation_sha256"})


@pytest.fixture(scope="module")
def actual_capture():
    supplied = request(2)
    energy = bridge.energy.evaluate_tabulated_target_dc_energy(deepcopy(supplied["energy_request"]))
    thermal_request = {"evaluation": "lumped_thermal_screening", **supplied["thermal_body"],
                       "segments": [
                           {"duration_s": row["duration_s"], "ambient_temperature_k": 300,
                            "conductance_w_k": 2,
                            "heat_input_w": row["actual_power_result"]["outputs"]["power"]["total_heat_w"]}
                           for row in energy["outputs"]["segments"]]}
    thermal = bridge.thermal.screen_thermal(deepcopy(thermal_request))
    assert energy["status"] == "COMPUTED_EXPERIMENTAL"
    assert thermal["status"] == "SCREENING_COMPUTED"
    return supplied, energy, thermal_request, thermal


@pytest.mark.parametrize("late", [False, True])
@pytest.mark.parametrize("case,status", [
    ("unbracketed", "TARGET_NOT_BRACKETED"), ("iteration", "ITERATION_LIMIT"),
    ("domain", "MODEL_INAPPLICABLE"), ("numerical", "NUMERICAL_LIMIT"),
    ("execution", "EXECUTION_FAILED"),
])
def test_actual_noncomputed_energy_boundary_discards_all_unvalidated_counts(monkeypatch, late, case, status):
    supplied = request(2)
    segments = supplied["energy_request"]["segments"]
    segments[1]["power_request"] = deepcopy(segments[0]["power_request"])
    target_request = segments[int(late)]["power_request"]
    target = target_request["assembly"]["rotors"][0]["target_template"]
    if case == "unbracketed":
        target["target_thrust_n"] = 1e12
    elif case == "iteration":
        target["max_evaluations"] = 2
    elif case == "domain":
        target["rotor_template"]["stations"][0]["chord_m"] = -1
    elif case == "numerical":
        fixtures.numerical_target(target_request)
    with monkeypatch.context() as patch:
        if case == "execution":
            compute, calls = fixtures.dc._compute, 0

            def fail_selected_motor(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2 * int(late) + 1:
                    raise RuntimeError("private injected execution")
                return compute(*args, **kwargs)

            patch.setattr(fixtures.dc, "_compute", fail_selected_motor)
        failed = bridge.energy.evaluate_tabulated_target_dc_energy(deepcopy(supplied["energy_request"]))
    assert failed["status"] == status
    energy_call = Mock(return_value=failed)
    thermal_call = Mock(side_effect=AssertionError("thermal must not be called"))
    guard = Mock(wraps=bridge.validate_tabulated_target_dc_energy_result)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    monkeypatch.setattr(bridge, "validate_tabulated_target_dc_energy_result", guard)
    actual = bridge.evaluate_tabulated_electrothermal(supplied)
    assert_atomic(actual, "energy")
    energy_call.assert_called_once()
    guard.assert_not_called()
    thermal_call.assert_not_called()


@pytest.mark.parametrize("case", ["hash", "metadata", "coherent_j", "point_mismatch"])
def test_computed_energy_must_pass_full_v120_before_any_counts(monkeypatch, actual_capture, case):
    supplied, energy, _, _ = deepcopy(actual_capture)
    if case == "hash":
        energy["evaluation_sha256"] = "0" * 64
    elif case == "metadata":
        energy["physical_validation"] = "private injected validation"
    elif case == "coherent_j":
        rows = energy["outputs"]["segments"]
        rows[0]["energy_j"]["total_allocated_heat"] += 1
        for row in rows:
            row["cumulative_energy_j"]["total_allocated_heat"] += 1
        energy["outputs"]["totals_j"]["total_allocated_heat"] += 1
        energy["outputs"]["totals_wh"]["total_allocated_heat"] = (
            energy["outputs"]["totals_j"]["total_allocated_heat"] / 3600)
    else:
        rows = energy["outputs"]["segments"]
        rows[0]["actual_power_result"] = deepcopy(rows[1]["actual_power_result"])
    if case != "hash":
        reseal(energy)
    energy_call, thermal_call = Mock(return_value=energy), Mock()
    guard = Mock(wraps=bridge.validate_tabulated_target_dc_energy_result)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    monkeypatch.setattr(bridge, "validate_tabulated_target_dc_energy_result", guard)
    assert_atomic(bridge.evaluate_tabulated_electrothermal(supplied), "energy")
    energy_call.assert_called_once()
    guard.assert_called_once()
    thermal_call.assert_not_called()


@pytest.mark.parametrize("case", ["exponential_underflow", "resolution", "product_underflow"])
def test_actual_noncomputed_thermal_is_sanitized_before_success_guard(monkeypatch, case):
    supplied = request(0)
    if case == "exponential_underflow":
        supplied["thermal_segments"][0]["conductance_w_k"] = 1e6
    elif case == "resolution":
        supplied["thermal_body"]["specific_heat_j_kg_k"] = 1e100
    else:
        supplied["thermal_segments"][0]["conductance_w_k"] = 5e-324
        supplied["energy_request"]["segments"][0]["duration_s"] = 0.5
    direct = bridge.energy.evaluate_tabulated_target_dc_energy(deepcopy(supplied["energy_request"]))
    assert direct["status"] == "COMPUTED_EXPERIMENTAL", direct["reasons"]
    energy_call = Mock(wraps=bridge.energy.evaluate_tabulated_target_dc_energy)
    thermal_call = Mock(wraps=bridge.thermal.screen_thermal)
    guard = Mock(wraps=bridge.validate_thermal_result)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    monkeypatch.setattr(bridge, "validate_thermal_result", guard)
    actual = bridge.evaluate_tabulated_electrothermal(supplied)
    assert_atomic(actual, "thermal", direct)
    energy_call.assert_called_once()
    thermal_call.assert_called_once()
    guard.assert_not_called()


def test_forged_thermal_temperature_and_repaired_ledger_fail_full_v119(monkeypatch, actual_capture):
    supplied, energy, thermal_request, _ = deepcopy(actual_capture)
    # A fully coherent trajectory for different declared initial temperature still cannot bind.
    forged_request = deepcopy(thermal_request)
    forged_request["initial_temperature_k"] += 1
    forged = bridge.thermal.screen_thermal(forged_request)
    assert forged["status"] == "SCREENING_COMPUTED"
    energy_call, thermal_call = Mock(return_value=energy), Mock(return_value=forged)
    guard = Mock(wraps=bridge.validate_thermal_result)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    monkeypatch.setattr(bridge, "validate_thermal_result", guard)
    assert_atomic(bridge.evaluate_tabulated_electrothermal(supplied), "thermal", energy)
    guard.assert_called_once()


@pytest.mark.parametrize("child", ["energy", "thermal"])
def test_guard_must_return_none_not_false(monkeypatch, actual_capture, child):
    supplied, energy, _, thermal = deepcopy(actual_capture)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", Mock(return_value=energy))
    screen = Mock(return_value=thermal)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", screen)
    guard_name = ("validate_tabulated_target_dc_energy_result" if child == "energy"
                  else "validate_thermal_result")
    monkeypatch.setattr(bridge, guard_name, Mock(return_value=False))
    assert_atomic(bridge.evaluate_tabulated_electrothermal(supplied), child,
                  None if child == "energy" else energy)
    assert screen.call_count == int(child == "thermal")


@pytest.mark.parametrize("child", ["energy", "thermal"])
@pytest.mark.parametrize("location", ["model", "guard"])
@pytest.mark.parametrize("exception", [RuntimeError, ValueError, KeyboardInterrupt])
def test_child_exceptions_follow_attempt_phase_and_baseexception_propagates(
        monkeypatch, actual_capture, child, location, exception):
    supplied, energy, _, thermal = deepcopy(actual_capture)
    energy_call, thermal_call = Mock(return_value=energy), Mock(return_value=thermal)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    fault = Mock(side_effect=exception("private injected boundary exception"))
    if location == "guard":
        monkeypatch.setattr(bridge, "validate_tabulated_target_dc_energy_result" if child == "energy"
                            else "validate_thermal_result", fault)
    else:
        (energy_call if child == "energy" else thermal_call).side_effect = fault.side_effect
    if exception is KeyboardInterrupt:
        with pytest.raises(KeyboardInterrupt, match="private injected"):
            bridge.evaluate_tabulated_electrothermal(supplied)
    else:
        assert_atomic(bridge.evaluate_tabulated_electrothermal(supplied), child,
                      None if child == "energy" else energy)
    assert energy_call.call_count == 1
    assert thermal_call.call_count == int(child == "thermal")


def test_postthermal_provenance_fault_retains_both_validated_counts(monkeypatch, actual_capture):
    supplied, energy, _, thermal = deepcopy(actual_capture)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", Mock(return_value=energy))
    monkeypatch.setattr(bridge.thermal, "screen_thermal", Mock(return_value=thermal))
    digest = bridge.sha256_record

    def fail_full_thermal_result(value):
        if type(value) is dict and value.get("model_id") == bridge.thermal.MODEL_ID:
            raise RuntimeError("private injected provenance fault")
        return digest(value)

    monkeypatch.setattr(bridge, "sha256_record", fail_full_thermal_result)
    assert_atomic(bridge.evaluate_tabulated_electrothermal(supplied), "execution", energy, thermal_count=1)


@pytest.mark.parametrize("child", ["energy", "thermal"])
def test_immediate_full_snapshots_detach_original_result_before_guard(monkeypatch, actual_capture, child):
    supplied, energy, _, thermal = deepcopy(actual_capture)
    expected_energy, expected_thermal = deepcopy(energy), deepcopy(thermal)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", Mock(return_value=energy))
    monkeypatch.setattr(bridge.thermal, "screen_thermal", Mock(return_value=thermal))
    guard_name = ("validate_tabulated_target_dc_energy_result" if child == "energy"
                  else "validate_thermal_result")
    guard = getattr(bridge, guard_name)

    def mutate_original_then_guard(retained, request):
        original = energy if child == "energy" else thermal
        original["outputs"].clear()
        original["limitations"].append("private injected later mutation")
        return guard(retained, request)

    monkeypatch.setattr(bridge, guard_name, mutate_original_then_guard)
    actual = bridge.evaluate_tabulated_electrothermal(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL", actual["reasons"]
    assert fixtures.encoded(actual["outputs"]["energy"]) == fixtures.encoded(expected_energy)
    assert fixtures.encoded(actual["outputs"]["thermal"]) == fixtures.encoded(expected_thermal)


@pytest.mark.parametrize("path,value", [
    (("thermal_body", "mass_kg"), True),
    (("thermal_body", "mass_kg"), 0),
    (("thermal_body", "specific_heat_j_kg_k"), 0),
    (("thermal_body", "initial_temperature_k"), -1),
    (("thermal_body", "lumped_biot_number"), True),
    (("thermal_body", "lumped_biot_number"), -0.01),
    (("thermal_body", "lumped_biot_number"), 0.10001),
    (("thermal_body", "property_source"), " \t"),
    (("thermal_body", "property_source"), None),
    (("thermal_body", "property_source"), "x" * 2001),
    (("thermal_segments", 1, "conductance_w_k"), -1),
    (("thermal_segments", 1, "conductance_w_k"), True),
    (("thermal_segments", 1, "conductance_w_k"), "2"),
    (("thermal_segments", 1, "ambient_temperature_k"), 0),
    (("thermal_segments", 1, "ambient_temperature_k"), False),
    (("thermal_segments", 1, "ambient_temperature_k"), float("inf")),
    (("thermal_segments", 1, "id"), "air"),
    (("thermal_segments", 1, "id"), "wrong"),
    (("thermal_segments", 1, "id"), True),
    (("energy_request", "segments", 1, "power_request", "motors", 1,
      "parameters", "motor_constant_si"), 0),
])
def test_late_invalid_declarations_preflight_before_any_calls(monkeypatch, path, value):
    supplied = request(2)
    owner = supplied
    for key in path[:-1]:
        owner = owner[key]
    owner[path[-1]] = value
    energy_call, thermal_call = Mock(), Mock()
    integrator, energy_guard, thermal_guard = Mock(), Mock(), Mock()
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    monkeypatch.setattr(bridge.thermal, "integrate_segment", integrator)
    monkeypatch.setattr(bridge, "validate_tabulated_target_dc_energy_result", energy_guard)
    monkeypatch.setattr(bridge, "validate_thermal_result", thermal_guard)
    actual = bridge.evaluate_tabulated_electrothermal(supplied)
    assert actual["status"] == "MODEL_INAPPLICABLE"
    assert actual["reasons"] == [bridge._REASONS["invalid"]]
    assert actual["request_sha256"] is actual["evaluation_sha256"] is None
    assert actual["outputs"] == actual["output_units"] == {}
    assert actual["stages"] == actual["transfers"] == []
    assert all(actual[key] == 0 for key in bridge._COUNTS)
    for call in (energy_call, thermal_call, integrator, energy_guard, thermal_guard):
        call.assert_not_called()


def test_actual_eight_segments_varied_conductance_cooling_and_exceeded_limits(monkeypatch):
    supplied = request(0)
    template = supplied["energy_request"]["segments"][0]
    supplied["energy_request"]["segments"] = [
        {**deepcopy(template), "id": str(index), "duration_s": index + 1} for index in range(8)]
    for segment in supplied["energy_request"]["segments"]:
        for motor in segment["power_request"]["motors"]:
            motor["declared_limits"]["maximum_current_a"] = 0.1
    supplied["thermal_body"]["initial_temperature_k"] = 400
    supplied["thermal_segments"] = [
        {"id": str(index), "ambient_temperature_k": 290 + index,
         "conductance_w_k": (0, 1e-5, 100)[index % 3]} for index in range(8)]
    actual = capture_and_check(monkeypatch, supplied)
    assert actual["outputs"]["energy"]["outputs"]["all_motors_within_declared_limits"] is False
    rows = actual["outputs"]["thermal"]["outputs"]["segments"]
    assert any(row["end_temperature_k"] < row["start_temperature_k"] for row in rows)
    assert actual["point_result_count"] == 8
    assert len(actual["transfers"]) == 16


def test_actual_native_large_integer_duration_and_subnormal_biot(monkeypatch):
    supplied = request(0)
    supplied["thermal_body"]["specific_heat_j_kg_k"] = 1e20
    supplied["thermal_body"]["lumped_biot_number"] = 5e-324
    for index, segment in enumerate(supplied["energy_request"]["segments"]):
        segment["duration_s"] = 2**53 + 1 + 2 * index
    actual = capture_and_check(monkeypatch, supplied)
    energy_rows = actual["outputs"]["energy"]["outputs"]["segments"]
    thermal_rows = actual["outputs"]["thermal"]["outputs"]["segments"]
    injected = actual["stages"][1]["inputs"]["segments"]
    for declared, row, segment, thermal_row in zip(
            supplied["energy_request"]["segments"], energy_rows, injected, thermal_rows, strict=True):
        assert type(row["duration_s"]) is type(segment["duration_s"]) is int
        assert row["duration_s"] == segment["duration_s"] == declared["duration_s"]
        assert type(thermal_row["duration_s"]) is float
        assert thermal_row["duration_s"] == float(declared["duration_s"])
        assert thermal_row["heat_input_j"] == row["energy_j"]["total_allocated_heat"]
    assert float(injected[0]["duration_s"]) != injected[0]["duration_s"]


@pytest.mark.parametrize("case", [
    "root_list", "root_extra", "root_missing", "evaluation_bool", "unsupported",
    "body_list", "body_extra", "body_missing", "thermal_list_empty", "thermal_list_short",
    "thermal_list_long", "thermal_list_dict", "thermal_segment_extra", "thermal_segment_missing",
    "thermal_segment_list", "thermal_order", "energy_extra", "energy_missing",
    "energy_evaluation", "energy_empty", "energy_nine", "aggregate_work",
])
def test_exact_shapes_unsupported_and_whole_energy_work_before_models(monkeypatch, case):
    supplied = request(2)
    if case == "root_list":
        supplied = []
    elif case == "root_extra":
        supplied["extra"] = 1
    elif case == "root_missing":
        supplied.pop("thermal_body")
    elif case == "evaluation_bool":
        supplied["evaluation"] = True
    elif case == "unsupported":
        supplied["evaluation"] = "other"
    elif case == "body_list":
        supplied["thermal_body"] = []
    elif case == "body_extra":
        supplied["thermal_body"]["extra"] = 1
    elif case == "body_missing":
        supplied["thermal_body"].pop("mass_kg")
    elif case.startswith("thermal_list"):
        supplied["thermal_segments"] = {
            "thermal_list_empty": [], "thermal_list_short": supplied["thermal_segments"][:1],
            "thermal_list_long": supplied["thermal_segments"] * 2, "thermal_list_dict": {},
        }[case]
    elif case == "thermal_segment_extra":
        supplied["thermal_segments"][1]["extra"] = 1
    elif case == "thermal_segment_missing":
        supplied["thermal_segments"][1].pop("conductance_w_k")
    elif case == "thermal_segment_list":
        supplied["thermal_segments"][1] = []
    elif case == "thermal_order":
        supplied["thermal_segments"].reverse()
    elif case == "energy_extra":
        supplied["energy_request"]["extra"] = 1
    elif case == "energy_missing":
        supplied["energy_request"].pop("segments")
    elif case == "energy_evaluation":
        supplied["energy_request"]["evaluation"] = bridge.EVALUATION
    elif case == "energy_empty":
        supplied["energy_request"]["segments"] = []
    elif case in ("energy_nine", "aggregate_work"):
        count = 9 if case == "energy_nine" else 3
        template = supplied["energy_request"]["segments"][0]
        supplied["energy_request"]["segments"] = [
            {**deepcopy(template), "id": str(index)} for index in range(count)]
        supplied["thermal_segments"] = [
            {"id": str(index), "ambient_temperature_k": 300, "conductance_w_k": 2}
            for index in range(count)]
        if case == "aggregate_work":
            for segment in supplied["energy_request"]["segments"]:
                for rotor in segment["power_request"]["assembly"]["rotors"]:
                    rotor["target_template"]["max_evaluations"] = 16
                    rotor["target_template"]["rotor_template"]["annuli"] = 1024
    energy_call, thermal_call = Mock(), Mock()
    calls = fixtures.fixtures.install_spies(monkeypatch)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    actual = bridge.evaluate_tabulated_electrothermal(supplied)
    expected = "SOLVER_UNSUPPORTED" if case == "unsupported" else "MODEL_INAPPLICABLE"
    assert actual["status"] == expected
    assert actual["request_sha256"] is actual["evaluation_sha256"] is None
    assert all(actual[key] == 0 for key in bridge._COUNTS)
    assert actual["outputs"] == actual["output_units"] == {}
    assert actual["stages"] == actual["transfers"] == []
    for call in (energy_call, thermal_call, *calls.values()):
        call.assert_not_called()


def test_actual_zero_heat_equilibrium_is_computed(monkeypatch):
    supplied = request(0)
    for segment in supplied["energy_request"]["segments"]:
        for motor in segment["power_request"]["motors"]:
            motor["heat_fraction_of_motor_loss"] = 0
        segment["power_request"]["auxiliary"]["power_w"] = 0
    actual = capture_and_check(monkeypatch, supplied)
    outputs = actual["outputs"]["thermal"]["outputs"]
    assert outputs["final_temperature_k"] == outputs["maximum_temperature_k"] == 300
    assert outputs["total_heat_input_j"] == 0
    assert all(row["heat_input_j"] == row["thermal_storage_change_j"] == 0
               for row in outputs["segments"])


@pytest.mark.parametrize("fraction", [0, 1])
def test_actual_allocation_endpoints_and_auxiliary_heat_once(monkeypatch, fraction):
    supplied = request(0)
    # Retain motor losses at both times; vary only the declared allocation fractions.
    supplied["energy_request"]["segments"][1]["power_request"] = deepcopy(
        supplied["energy_request"]["segments"][0]["power_request"])
    for segment in supplied["energy_request"]["segments"]:
        power_request = segment["power_request"]
        for motor in power_request["motors"]:
            motor["heat_fraction_of_motor_loss"] = fraction
        power_request["auxiliary"].update(power_w=16, heat_fraction=0.25)
    actual = capture_and_check(monkeypatch, supplied)
    for row, injected in zip(actual["outputs"]["energy"]["outputs"]["segments"],
                             actual["stages"][1]["inputs"]["segments"], strict=True):
        power = row["actual_power_result"]["outputs"]["power"]
        assert power["auxiliary_heat_w"] == 4
        assert power["total_allocated_motor_heat_w"] == fraction * power["total_motor_loss_w"]
        assert injected["heat_input_w"] == power["total_allocated_motor_heat_w"] + 4
        assert power["total_electrical_power_w"] > power["total_shaft_power_w"] > 0
        assert injected["heat_input_w"] != power["total_electrical_power_w"]
        assert injected["heat_input_w"] != power["total_shaft_power_w"]
        if fraction == 0:
            assert injected["heat_input_w"] == 4  # Auxiliary is not reallocated per motor.


def test_injection_walk_fault_after_energy_guard_is_execution_not_thermal_boundary(monkeypatch, actual_capture):
    supplied, energy, _, _ = deepcopy(actual_capture)
    energy_call, thermal_call = Mock(return_value=energy), Mock()
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    walk = bridge._json_walk

    def fail_injected_request(value, limits):
        if limits is bridge._LIMITS["thermal_input_json"]:
            raise ValueError("private injected preparation arithmetic fault")
        return walk(value, limits)

    monkeypatch.setattr(bridge, "_json_walk", fail_injected_request)
    assert_atomic(bridge.evaluate_tabulated_electrothermal(supplied), "execution", energy)
    energy_call.assert_called_once()
    thermal_call.assert_not_called()


_JSON_SCOPES = [
    ("input_json", 1048576, 24, 256), ("output_json", 8388608, 36, 2048),
    ("energy_input_json", 524288, 20, 256), ("energy_output_json", 4194304, 32, 2048),
    ("thermal_input_json", 8192, 8, 2048), ("thermal_output_json", 32768, 10, 2048),
]


def json_nodes(count, fanout):
    """Compact alias tree with exactly count JSON occurrences, including containers."""
    if count == 1:
        return None
    if count <= fanout + 1:
        return [None] * (count - 1)
    child_size = fanout + 1
    while 1 + fanout * child_size < count:
        child_size = 1 + fanout * child_size
    full, remainder = divmod(count - 1, child_size)
    children = [json_nodes(child_size, fanout)] * full
    if remainder:
        children.append(json_nodes(remainder, fanout))
    return children


@pytest.mark.parametrize("scope,nodes,depth,items", _JSON_SCOPES)
@pytest.mark.parametrize("boundary", ["nodes", "depth", "items", "string", "bits"])
def test_helper_only_exact_json_budgets_and_plus_one(scope, nodes, depth, items, boundary):
    limits = bridge._LIMITS[scope]
    assert limits == {
        "root_depth": 1, "max_nodes_including_keys": nodes, "max_depth": depth,
        "max_container_items": items, "max_string_characters": 2000,
        "max_integer_bits": 1023, "finite_floats_only": True, "valid_utf8_only": True,
    }
    if boundary == "nodes":
        exact, exceeded = json_nodes(nodes, items), json_nodes(nodes + 1, items)
    elif boundary == "depth":
        exact = None
        for _ in range(depth - 1):
            exact = [exact]
        exceeded = [exact]
    elif boundary == "items":
        exact, exceeded = [None] * items, [None] * (items + 1)
    elif boundary == "string":
        exact, exceeded = "x" * 2000, "x" * 2001
    else:
        exact, exceeded = (1 << 1023) - 1, 1 << 1023
    # Synthetic helper coverage only: this establishes no actual child success.
    bridge._json_walk(exact, limits)
    with pytest.raises(ValueError):
        bridge._json_walk(exceeded, limits)


@pytest.mark.parametrize("boundary", ["request", "energy", "thermal"])
@pytest.mark.parametrize("nested", [False, True])
def test_foreign_subclasses_rejected_before_copy_hooks(monkeypatch, actual_capture, boundary, nested):
    supplied, energy, _, thermal = deepcopy(actual_capture)
    hook = Mock(side_effect=AssertionError("foreign copy hook must never execute"))

    class ForeignDict(dict):
        def __deepcopy__(self, memo):
            return hook(memo)

    class ForeignList(list):
        def __deepcopy__(self, memo):
            return hook(memo)

    value = {"request": supplied, "energy": energy, "thermal": thermal}[boundary]
    if nested:
        if boundary == "request":
            value["thermal_segments"] = ForeignList(value["thermal_segments"])
        else:
            value["limitations"] = ForeignList(value["limitations"])
    else:
        value = ForeignDict(value)
        if boundary == "request":
            supplied = value
        elif boundary == "energy":
            energy = value
        else:
            thermal = value
    energy_call, thermal_call = Mock(return_value=energy), Mock(return_value=thermal)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    actual = bridge.evaluate_tabulated_electrothermal(supplied)
    hook.assert_not_called()
    if boundary == "request":
        assert actual["status"] == "MODEL_INAPPLICABLE"
        assert actual["request_sha256"] is actual["evaluation_sha256"] is None
        assert all(actual[key] == 0 for key in bridge._COUNTS)
        energy_call.assert_not_called()
        thermal_call.assert_not_called()
    else:
        assert_atomic(actual, boundary, None if boundary == "energy" else energy)
        energy_call.assert_called_once()
        assert thermal_call.call_count == int(boundary == "thermal")


@pytest.mark.parametrize("boundary", ["request", "energy", "thermal"])
@pytest.mark.parametrize("case", ["utf8", "cycle", "nonfinite"])
def test_full_walk_rejects_utf8_cycles_nonfinite_at_each_boundary(monkeypatch, actual_capture, boundary, case):
    supplied, energy, _, thermal = deepcopy(actual_capture)
    owner = {"request": supplied["thermal_body"], "energy": energy, "thermal": thermal}[boundary]
    invalid = "\ud800" if case == "utf8" else float("nan") if case == "nonfinite" else owner
    if boundary == "request":
        owner["property_source"] = invalid
    else:
        owner["limitations"].append(invalid)
    energy_call, thermal_call = Mock(return_value=energy), Mock(return_value=thermal)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    actual = bridge.evaluate_tabulated_electrothermal(supplied)
    if boundary == "request":
        assert actual["status"] == "MODEL_INAPPLICABLE"
        assert actual["request_sha256"] is actual["evaluation_sha256"] is None
        assert all(actual[key] == 0 for key in bridge._COUNTS)
        energy_call.assert_not_called()
        thermal_call.assert_not_called()
    else:
        assert_atomic(actual, boundary, None if boundary == "energy" else energy)
        assert energy_call.call_count == 1
        assert thermal_call.call_count == int(boundary == "thermal")


def test_actual_child_order_full_walk_copy_walk_then_full_guard(monkeypatch, actual_capture):
    supplied, energy, _, thermal = deepcopy(actual_capture)
    events = []
    originals = {"energy": energy, "thermal": thermal}
    copies = {}
    walk, copy = bridge._json_walk, bridge.deepcopy
    energy_guard, thermal_guard = bridge.validate_tabulated_target_dc_energy_result, bridge.validate_thermal_result

    def recorded_walk(value, limits):
        for child, original in originals.items():
            if value is original:
                events.append((child, "full_original_walk"))
            if value is copies.get(child):
                events.append((child, "full_snapshot_walk"))
        return walk(value, limits)

    def recorded_copy(value):
        retained = copy(value)
        for child, original in originals.items():
            if value is original:
                events.append((child, "full_copy"))
                copies[child] = retained
        return retained

    def returned(child):
        events.append((child, "model_return"))
        return originals[child]

    def guarded(child, value, request):
        assert value is copies[child]
        events.append((child, "full_guard"))
        return (energy_guard if child == "energy" else thermal_guard)(value, request)

    monkeypatch.setattr(bridge, "_json_walk", recorded_walk)
    monkeypatch.setattr(bridge, "deepcopy", recorded_copy)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", lambda _: returned("energy"))
    monkeypatch.setattr(bridge.thermal, "screen_thermal", lambda _: returned("thermal"))
    monkeypatch.setattr(bridge, "validate_tabulated_target_dc_energy_result", lambda v, r: guarded("energy", v, r))
    monkeypatch.setattr(bridge, "validate_thermal_result", lambda v, r: guarded("thermal", v, r))
    actual = bridge.evaluate_tabulated_electrothermal(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL", actual["reasons"]
    assert events == [(child, event) for child in ("energy", "thermal") for event in (
        "model_return", "full_original_walk", "full_copy", "full_snapshot_walk", "full_guard")]


def test_root_output_resource_failure_is_atomic_with_both_counts_retained(monkeypatch, actual_capture):
    supplied, energy, _, thermal = deepcopy(actual_capture)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", Mock(return_value=energy))
    monkeypatch.setattr(bridge.thermal, "screen_thermal", Mock(return_value=thermal))
    walk = bridge._json_walk

    def reject_success_root(value, limits):
        if limits is bridge._LIMITS["output_json"] and value["outputs"]:
            raise ValueError("private injected root resource failure")
        return walk(value, limits)

    monkeypatch.setattr(bridge, "_json_walk", reject_success_root)
    assert_atomic(bridge.evaluate_tabulated_electrothermal(supplied), "execution", energy, thermal_count=1)


def test_catalog_is_fresh_pure_full_units_and_does_not_pollute_later_calls(monkeypatch):
    initial = bridge.tabulated_electrothermal_catalog()
    energy_call, thermal_call, integrator = Mock(), Mock(), Mock()
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    monkeypatch.setattr(bridge.thermal, "integrate_segment", integrator)
    public = bridge.tabulated_electrothermal_catalog()
    public["energy_catalog"]["output_field_units"].clear()
    public["limits"]["thermal_input_json"]["max_depth"] = 0
    public["output_field_units"]["thermal"]["outputs"].clear()
    public["limitations"].append("private injected catalog mutation")
    fresh = bridge.tabulated_electrothermal_catalog()
    assert fixtures.encoded(fresh) == fixtures.encoded(initial)
    assert fresh["required_fields"] == list(bridge._ROOT)
    assert fresh["thermal_body_fields"] == list(bridge._BODY)
    assert fresh["thermal_segment_fields"] == list(bridge._SEGMENT)
    assert fresh["output_field_units"] == {
        "energy": {"outputs": fixtures.energy.tabulated_target_dc_energy_catalog()["output_field_units"]},
        "thermal": {"outputs": bridge._OUTPUT_UNITS},
    }
    assert fresh["stages"] == fresh["transfers"] == []
    assert fresh["outputs"] == fresh["output_units"] == {}
    for call in (energy_call, thermal_call, integrator):
        call.assert_not_called()


@pytest.mark.parametrize("location", ["root_copy", "preflight"])
@pytest.mark.parametrize("exception", [RuntimeError, KeyboardInterrupt])
def test_unexpected_root_copy_preflight_fault_lifecycle(monkeypatch, location, exception):
    supplied = request(2)
    energy_call, thermal_call = Mock(), Mock()
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    if location == "preflight":
        monkeypatch.setattr(bridge, "_preflight", Mock(side_effect=exception("private injected preflight")))
    else:
        copy = bridge.deepcopy

        def fail_request_copy(value):
            if value is supplied:
                raise exception("private injected root copy")
            return copy(value)

        monkeypatch.setattr(bridge, "deepcopy", fail_request_copy)
    if exception is KeyboardInterrupt:
        with pytest.raises(KeyboardInterrupt, match="private injected"):
            bridge.evaluate_tabulated_electrothermal(supplied)
    else:
        assert_atomic(bridge.evaluate_tabulated_electrothermal(supplied), "snapshot", preflight=True)
    energy_call.assert_not_called()
    thermal_call.assert_not_called()


@pytest.mark.parametrize("child", ["energy", "thermal"])
def test_argument_copy_failure_precedes_child_attempt_and_uses_execution_reason(monkeypatch, actual_capture, child):
    supplied, energy, _, thermal = deepcopy(actual_capture)
    energy_call, thermal_call = Mock(return_value=energy), Mock(return_value=thermal)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    copy = bridge.deepcopy
    evaluation = bridge.energy.EVALUATION if child == "energy" else "lumped_thermal_screening"

    def fail_arguments_copy(value):
        if type(value) is dict and value.get("evaluation") == evaluation:
            raise RuntimeError("private injected argument copy fault")
        return copy(value)

    monkeypatch.setattr(bridge, "deepcopy", fail_arguments_copy)
    assert_atomic(bridge.evaluate_tabulated_electrothermal(supplied), "execution",
                  None if child == "energy" else energy)
    assert energy_call.call_count == int(child == "thermal")
    thermal_call.assert_not_called()


@pytest.mark.parametrize("location", ["request", "result"])
def test_digest_infrastructure_fault_has_no_fabricated_underlying_result(monkeypatch, actual_capture, location):
    supplied, energy, _, thermal = deepcopy(actual_capture)
    energy_call, thermal_call = Mock(return_value=energy), Mock(return_value=thermal)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_target_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    digest = bridge.sha256_record

    def fail_selected_digest(value):
        if type(value) is dict and value.get("evaluation") == bridge.EVALUATION:
            if location == "request" and value.keys() == set(bridge._ROOT):
                raise RuntimeError("private injected request hash fault")
            if location == "result" and "status" in value:
                raise RuntimeError("private injected result hash fault")
        return digest(value)

    monkeypatch.setattr(bridge, "sha256_record", fail_selected_digest)
    actual = bridge.evaluate_tabulated_electrothermal(supplied)
    assert actual["status"] == "EXECUTION_FAILED"
    assert actual["reasons"] == [bridge._REASONS["execution"]]
    assert actual["diagnostics_complete"] is False
    assert actual["outputs"] == actual["output_units"] == {}
    assert actual["stages"] == actual["transfers"] == []
    assert actual["evaluation_sha256"] is None
    if location == "request":
        assert actual["request_sha256"] is None
        assert all(actual[key] == 0 for key in bridge._COUNTS)
        energy_call.assert_not_called()
        thermal_call.assert_not_called()
    else:
        assert actual["request_sha256"] == sha256_record(supplied)
        assert actual["energy_result_count"] == actual["thermal_result_count"] == 1
        assert all(actual[key] == energy[key] for key in bridge.energy._COUNTS)
        energy_call.assert_called_once()
        thermal_call.assert_called_once()
