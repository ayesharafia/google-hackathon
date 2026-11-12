"""Actual V128 chronology to one-way thermal screening and bounded boundary guards."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from physimesh.drone import tabulated_solved_electrothermal as bridge
from physimesh.drone.provenance import sha256_record

from .test_tabulated_solved_dc_energy import request as energy_request


def request(count=2, conductance=0.2, biot=0.01):
    supplied = energy_request(count)
    return {
        "evaluation": bridge.EVALUATION, "energy_request": supplied,
        "thermal_body": {"mass_kg": 1, "specific_heat_j_kg_k": 500,
                         "initial_temperature_k": 300, "lumped_biot_number": biot,
                         "property_source": "synthetic unverified declaration"},
        "thermal_segments": [{"id": row["id"], "ambient_temperature_k": 300 + i * 2,
                              "conductance_w_k": conductance}
                             for i, row in enumerate(supplied["segments"])],
    }


def thermal_request(supplied, retained):
    return {"evaluation": "lumped_thermal_screening", **supplied["thermal_body"],
            "segments": [{"duration_s": row["duration_s"],
                          "heat_input_w": row["actual_power_result"]["outputs"]["power"]["total_heat_w"],
                          "ambient_temperature_k": declared["ambient_temperature_k"],
                          "conductance_w_k": declared["conductance_w_k"]}
                         for row, declared in zip(retained["outputs"]["points"],
                                                  supplied["thermal_segments"], strict=True)]}


def assert_seal(actual, supplied):
    assert actual["request_sha256"] == sha256_record(supplied)
    assert actual["evaluation_sha256"] == sha256_record({
        key: value for key, value in actual.items() if key != "evaluation_sha256"})


@pytest.mark.parametrize("conductance,biot", [(0, 0), (0.2, 0.1), (0.001, 0.01)])
def test_actual_two_point_chronology_and_direct_children(monkeypatch, conductance, biot):
    supplied = request(conductance=conductance, biot=biot)
    original = deepcopy(supplied)
    direct_energy = bridge.energy.evaluate_tabulated_solved_dc_energy(deepcopy(supplied["energy_request"]))
    injected = thermal_request(supplied, direct_energy)
    direct_thermal = bridge.thermal.screen_thermal(deepcopy(injected))
    energy_call = Mock(wraps=bridge.energy.evaluate_tabulated_solved_dc_energy)
    thermal_call = Mock(wraps=bridge.thermal.screen_thermal)
    point_call = Mock(wraps=bridge.energy.point.evaluate_tabulated_solved_dc_power)
    motor_call = Mock(wraps=bridge.energy.dc.evaluate_dc_motor)
    compute_call = Mock(wraps=bridge.energy.dc._compute)
    solve_call = Mock(wraps=bridge.energy.point.solve.evaluate_tabulated_static_wrench_solve)
    assembly_call = Mock(wraps=bridge.energy.point.solve._assembly.evaluate_tabulated_rotor_assembly)
    forward_call = Mock(wraps=bridge.energy.point.solve._assembly.evaluate_tabulated_hover_bemt)
    integrator = Mock(wraps=bridge.thermal.integrate_segment)
    energy_guard = Mock(wraps=bridge._guard_energy_success)
    point_guard = Mock(wraps=bridge.energy._guard_point_success)
    thermal_guard = Mock(wraps=bridge.validate_thermal_result)
    for owner, name, spy in (
        (bridge.energy, "evaluate_tabulated_solved_dc_energy", energy_call),
        (bridge.thermal, "screen_thermal", thermal_call),
        (bridge.energy.point, "evaluate_tabulated_solved_dc_power", point_call),
        (bridge.energy.dc, "evaluate_dc_motor", motor_call),
        (bridge.energy.dc, "_compute", compute_call),
        (bridge.energy.point.solve, "evaluate_tabulated_static_wrench_solve", solve_call),
        (bridge.energy.point.solve._assembly, "evaluate_tabulated_rotor_assembly", assembly_call),
        (bridge.energy.point.solve._assembly, "evaluate_tabulated_hover_bemt", forward_call),
        (bridge.thermal, "integrate_segment", integrator),
        (bridge, "_guard_energy_success", energy_guard),
        (bridge.energy, "_guard_point_success", point_guard),
        (bridge, "validate_thermal_result", thermal_guard),
    ):
        monkeypatch.setattr(owner, name, spy)
    actual = bridge.evaluate_tabulated_solved_electrothermal(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL", actual["reasons"]
    assert actual["diagnostics_complete"] is True
    assert supplied == original
    assert actual["outputs"] == {"energy": direct_energy, "thermal_state": "COMPUTED",
                                 "thermal": direct_thermal}
    assert actual["output_units"] == {"energy": {"outputs": direct_energy["output_units"]},
                                      "thermal_state": "label",
                                      "thermal": {"outputs": direct_thermal["output_units"]}}
    assert energy_call.call_count == thermal_call.call_count == 1
    assert energy_guard.call_count == thermal_guard.call_count == 1
    assert point_guard.call_count == 4  # V128 admission plus V129 full re-admission, once per point each.
    assert point_call.call_count == solve_call.call_count == 2
    assert motor_call.call_count == compute_call.call_count == direct_energy["motor_result_count"]
    assert assembly_call.call_count == direct_energy["assembly_evaluation_count"]
    assert forward_call.call_count == direct_energy["forward_evaluation_count"]
    assert integrator.call_count == 2
    assert actual["energy_result_count"] == actual["thermal_result_count"] == 1
    for key in bridge.energy._COUNTS:
        assert actual[key] == direct_energy[key]
    assert thermal_call.call_args.args == (injected,)
    assert actual["stages"] == [
        {"stage": name, "inputs": inputs, "inputs_sha256": sha256_record(inputs),
         "result_sha256": sha256_record(retained)}
        for name, inputs, retained in (("energy", supplied["energy_request"], direct_energy),
                                      ("thermal", injected, direct_thermal))]
    assert len(actual["transfers"]) == 4
    for i, (row, trow) in enumerate(zip(direct_energy["outputs"]["energy"]["segments"],
                                       direct_thermal["outputs"]["segments"], strict=True)):
        assert trow["heat_input_j"] == row["energy_j"]["total_allocated_heat"]
        if i:
            assert trow["start_temperature_k"] == direct_thermal["outputs"]["segments"][i - 1]["end_temperature_k"]
        for offset, (source, target, unit) in enumerate((
            ("actual_power_result.outputs.power.total_heat_w", "heat_input_w", "W"),
            ("duration_s", "duration_s", "s"),
        )):
            assert actual["transfers"][i * 2 + offset] == {
                "from_stage": "energy", "from_field": f"outputs.points[{i}].{source}",
                "to_stage": "thermal", "to_field": f"segments[{i}].{target}",
                "value": injected["segments"][i][target], "unit": unit,
                "producer_result_sha256": sha256_record(direct_energy),
                "consumer_request_sha256": sha256_record(injected)}
    assert actual["aircraft_status"] is actual["feasibility"] is None
    assert_seal(actual, supplied)


@pytest.mark.parametrize("unmet_index", [0, 1])
def test_actual_mixed_unmet_preserves_all_points_without_thermal(monkeypatch, unmet_index):
    supplied = request()
    solve = supplied["energy_request"]["segments"][unmet_index]["power_request"]["solve"]
    solve["max_evaluations"] = 2
    solve["required_net_force_body_n"][0] = 100.0
    direct = bridge.energy.evaluate_tabulated_solved_dc_energy(deepcopy(supplied["energy_request"]))
    energy_call = Mock(wraps=bridge.energy.evaluate_tabulated_solved_dc_energy)
    point_call = Mock(wraps=bridge.energy.point.evaluate_tabulated_solved_dc_power)
    thermal_call = Mock(side_effect=AssertionError("thermal must not run"))
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_solved_dc_energy", energy_call)
    monkeypatch.setattr(bridge.energy.point, "evaluate_tabulated_solved_dc_power", point_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    actual = bridge.evaluate_tabulated_solved_electrothermal(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL", actual["reasons"]
    assert actual["diagnostics_complete"] is True
    assert actual["outputs"] == {"energy": direct, "thermal_state": "NOT_RUN_RESIDUAL_UNMET",
                                 "thermal": None}
    assert len(direct["outputs"]["points"]) == len(direct["stages"]) == 2
    assert direct["outputs"]["points"][unmet_index]["actual_power_result"]["outputs"]["power"] is None
    assert actual["output_units"] == {"energy": {"outputs": direct["output_units"]},
                                      "thermal_state": "label", "thermal": "not_applicable"}
    assert len(actual["stages"]) == 1
    assert actual["stages"][0]["inputs"] == supplied["energy_request"]
    assert actual["stages"][0]["result_sha256"] == sha256_record(direct)
    assert actual["transfers"] == []
    assert actual["energy_result_count"] == energy_call.call_count == 1
    assert actual["point_result_count"] == point_call.call_count == 2
    assert actual["thermal_result_count"] == 0
    thermal_call.assert_not_called()
    for key in bridge.energy._COUNTS:
        assert actual[key] == direct[key]
    assert_seal(actual, supplied)


def test_native_integer_duration_is_retained_before_thermal_float_conversion():
    supplied = request(count=1, conductance=0)
    supplied["energy_request"]["segments"][0]["duration_s"] = 9007199254740993
    supplied["thermal_body"]["mass_kg"] = 10**16
    actual = bridge.evaluate_tabulated_solved_electrothermal(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL", actual["reasons"]
    native = actual["outputs"]["energy"]["outputs"]["points"][0]["duration_s"]
    injected = actual["stages"][1]["inputs"]["segments"][0]["duration_s"]
    converted = actual["outputs"]["thermal"]["outputs"]["segments"][0]["duration_s"]
    assert type(native) is type(injected) is int
    assert native == injected == 9007199254740993
    assert type(converted) is float and converted == float(native)
    assert actual["transfers"][1]["value"] == native
    assert type(actual["transfers"][1]["value"]) is int
    assert_seal(actual, supplied)


@pytest.fixture(scope="module")
def actual_energy():
    supplied = request()
    retained = bridge.energy.evaluate_tabulated_solved_dc_energy(deepcopy(supplied["energy_request"]))
    assert retained["status"] == "COMPUTED_EXPERIMENTAL", retained["reasons"]
    assert retained["outputs"]["energy_state"] == "COMPUTED"
    return supplied, retained


def reseal(actual):
    actual["evaluation_sha256"] = sha256_record({
        key: value for key, value in actual.items() if key != "evaluation_sha256"})


def mutate(actual, path, value):
    target = actual
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def forbid_models(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("model rerun"))
    for owner, name in (
        (bridge.energy, "evaluate_tabulated_solved_dc_energy"),
        (bridge.energy.point, "evaluate_tabulated_solved_dc_power"),
        (bridge.energy.point.solve, "evaluate_tabulated_static_wrench_solve"),
        (bridge.energy.point.solve._assembly, "evaluate_tabulated_rotor_assembly"),
        (bridge.energy.point.solve._assembly, "evaluate_tabulated_hover_bemt"),
        (bridge.energy.dc, "evaluate_dc_motor"), (bridge.energy.dc, "_compute"),
        (bridge.thermal, "screen_thermal"), (bridge.thermal, "integrate_segment"),
    ):
        monkeypatch.setattr(owner, name, forbidden)
    return forbidden


def assert_atomic(actual, phase, retained=None, thermal_count=0):
    assert actual["status"] == "EXECUTION_FAILED"
    assert actual["reasons"] == [bridge._REASONS[phase]]
    assert actual["outputs"] == actual["output_units"] == {}
    assert actual["stages"] == actual["transfers"] == []
    assert actual["diagnostics_complete"] is False
    assert actual["energy_result_count"] == int(retained is not None)
    assert actual["thermal_result_count"] == thermal_count
    for key in bridge.energy._COUNTS:
        assert actual[key] == (retained[key] if retained is not None else 0)
    assert "private injected" not in str(actual)


_ENERGY_FORGERIES = [
    (("status",), "MODEL_INAPPLICABLE"),
    (("schema_version",), "invented"),
    (("physical_validation",), "ESTABLISHED"),
    (("diagnostics_complete",), 1),
    (("reasons",), ["private injected child reason"]),
    (("limits", "input_json", "max_depth"), 100),
    (("point_result_count",), True),
    (("assembly_evaluation_count",), 0),
    (("motor_result_count",), 0),
    (("request_sha256",), "0" * 64),
    (("output_units", "energy", "totals_wh", "shaft"), "J"),
    (("output_units", "points", 0, "duration_s"), "W"),
    (("outputs", "points", 0, "segment_id"), "wrong-id"),
    (("outputs", "points", 0, "duration_s"), 1.0),
    (("outputs", "energy_state"), "NOT_RUN_RESIDUAL_UNMET"),
    (("outputs", "energy", "segments", 0, "energy_j", "total_allocated_heat"), 0.0),
    (("outputs", "energy", "segments", 1, "cumulative_energy_j", "shaft"), 0.0),
    (("outputs", "energy", "segments", 1, "start_time_s"), 0.0),
    (("outputs", "energy", "elapsed_s"), 0.0),
    (("outputs", "energy", "totals_j", "motor_loss"), 0.0),
    (("outputs", "energy", "totals_wh", "total_electrical"), 0.0),
    (("outputs", "energy", "all_motors_within_declared_limits"), 1),
    (("stages", 0, "inputs_sha256"), "0" * 64),
    (("stages", 1, "inputs", "auxiliary", "source"), "invented"),
    (("transfers", 0, "from_field"), "outputs.invented"),
    (("transfers", 8, "consumer_request_sha256"), "0" * 64),
    (("outputs", "points", 0, "actual_power_result", "outputs", "power"), None),
    (("outputs", "points", 0, "actual_power_result", "physical_validation"), "ESTABLISHED"),
]


@pytest.mark.parametrize("path,value", _ENERGY_FORGERIES)
def test_rehashed_energy_forgery_pure_guard_and_atomic_boundary(monkeypatch, actual_energy, path, value):
    supplied, baseline = actual_energy
    forged = deepcopy(baseline)
    mutate(forged, path, value)
    for row in forged["outputs"]["points"]:
        reseal(row["actual_power_result"])
    reseal(forged)
    forbidden = forbid_models(monkeypatch)
    with pytest.raises(ValueError):
        bridge._guard_energy_success(forged, supplied["energy_request"])
    forbidden.assert_not_called()
    energy_call = Mock(return_value=forged)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_solved_dc_energy", energy_call)
    actual = bridge.evaluate_tabulated_solved_electrothermal(deepcopy(supplied))
    assert_atomic(actual, "energy")
    assert_seal(actual, supplied)
    energy_call.assert_called_once()
    forbidden.assert_not_called()


def test_full_energy_guard_is_pure_and_guards_each_point_once(monkeypatch, actual_energy):
    supplied, retained = actual_energy
    forbidden = forbid_models(monkeypatch)
    guard = Mock(wraps=bridge.energy._guard_point_success)
    monkeypatch.setattr(bridge.energy, "_guard_point_success", guard)
    before = deepcopy(retained)
    assert bridge._guard_energy_success(retained, supplied["energy_request"]) is None
    assert guard.call_count == len(retained["outputs"]["points"])
    assert retained == before
    forbidden.assert_not_called()


@pytest.mark.parametrize("phase", ["energy", "thermal"])
@pytest.mark.parametrize("fault", ["malformed", "noncomputed", "exception"])
def test_bad_actual_children_sanitize_by_phase(monkeypatch, actual_energy, phase, fault):
    supplied, retained = actual_energy
    energy_call = Mock(return_value=deepcopy(retained))
    thermal_call = Mock(side_effect=AssertionError("thermal should not run"))
    bad = {} if fault == "malformed" else {"status": "MODEL_INAPPLICABLE",
                                             "reasons": ["private injected raw cause"]}
    failing = Mock(side_effect=RuntimeError("private injected exception")) if fault == "exception" else Mock(return_value=bad)
    if phase == "energy":
        energy_call = failing
    else:
        thermal_call = failing
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_solved_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    actual = bridge.evaluate_tabulated_solved_electrothermal(deepcopy(supplied))
    assert_atomic(actual, phase, retained if phase == "thermal" else None)
    assert_seal(actual, supplied)
    energy_call.assert_called_once()
    assert thermal_call.call_count == int(phase == "thermal")


_PREFLIGHT_FORGERIES = [
    (("thermal_segments", 1, "id"), "wrong-order"),
    (("thermal_segments", 1, "ambient_temperature_k"), 0),
    (("thermal_segments", 1, "conductance_w_k"), -1),
    (("thermal_body", "mass_kg"), 0),
    (("thermal_body", "specific_heat_j_kg_k"), True),
    (("thermal_body", "initial_temperature_k"), 0),
    (("thermal_body", "lumped_biot_number"), 0.10000001),
    (("thermal_body", "property_source"), " "),
    (("energy_request", "evaluation"), "wrong-energy-evaluation"),
    (("energy_request", "segments", 1, "power_request", "motors", 0,
      "heat_fraction_of_motor_loss"), 2),
]


@pytest.mark.parametrize("path,value", _PREFLIGHT_FORGERIES)
def test_all_later_preflight_fields_checked_before_any_model(monkeypatch, path, value):
    supplied = request()
    mutate(supplied, path, value)
    forbidden = forbid_models(monkeypatch)
    actual = bridge.evaluate_tabulated_solved_electrothermal(supplied)
    assert actual["status"] == "MODEL_INAPPLICABLE"
    assert all(actual[key] == 0 for key in bridge._COUNTS)
    assert actual["outputs"] == actual["output_units"] == {}
    assert actual["request_sha256"] is actual["evaluation_sha256"] is None
    forbidden.assert_not_called()


def test_post_thermal_guard_failure_keeps_both_trusted_counts(monkeypatch, actual_energy):
    supplied, retained = actual_energy
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_solved_dc_energy", Mock(return_value=deepcopy(retained)))
    stage = bridge._stage

    def fail_thermal_stage(name, inputs, result):
        if name == "thermal":
            raise RuntimeError("private injected postguard failure")
        return stage(name, inputs, result)

    monkeypatch.setattr(bridge, "_stage", fail_thermal_stage)
    actual = bridge.evaluate_tabulated_solved_electrothermal(deepcopy(supplied))
    assert_atomic(actual, "execution", retained, thermal_count=1)
    assert_seal(actual, supplied)


@pytest.mark.parametrize("count", range(1, 9))
def test_actual_one_to_eight_points_use_one_thermal_sequence(monkeypatch, count):
    supplied = request(count=count)
    thermal_call = Mock(wraps=bridge.thermal.screen_thermal)
    integrator = Mock(wraps=bridge.thermal.integrate_segment)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    monkeypatch.setattr(bridge.thermal, "integrate_segment", integrator)
    actual = bridge.evaluate_tabulated_solved_electrothermal(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL", actual["reasons"]
    assert actual["point_result_count"] == count
    assert actual["energy_result_count"] == actual["thermal_result_count"] == 1
    thermal_call.assert_called_once()
    assert integrator.call_count == count
    assert len(actual["outputs"]["energy"]["outputs"]["points"]) == count
    rows = actual["outputs"]["thermal"]["outputs"]["segments"]
    assert len(rows) == count
    for i in range(1, count):
        assert rows[i]["start_temperature_k"] == rows[i - 1]["end_temperature_k"]
    assert len(actual["transfers"]) == 2 * count
    assert_seal(actual, supplied)


@pytest.mark.parametrize("phase", ["energy", "thermal"])
def test_baseexception_propagates_from_child(monkeypatch, actual_energy, phase):
    supplied, retained = actual_energy
    energy_call = Mock(return_value=deepcopy(retained))
    thermal_call = Mock(side_effect=KeyboardInterrupt("must propagate"))
    if phase == "energy":
        energy_call = Mock(side_effect=KeyboardInterrupt("must propagate"))
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_solved_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    with pytest.raises(KeyboardInterrupt, match="must propagate"):
        bridge.evaluate_tabulated_solved_electrothermal(deepcopy(supplied))
    energy_call.assert_called_once()
    assert thermal_call.call_count == int(phase == "thermal")


@pytest.mark.parametrize("location", ["input", "energy", "thermal"])
def test_snapshot_rejects_foreign_hooks_before_copy(monkeypatch, actual_energy, location):
    supplied, retained = actual_energy
    hooks = Mock(side_effect=AssertionError("foreign hook ran"))

    class Foreign(dict):
        def __deepcopy__(self, memo):
            return hooks(memo)

    energy_call = Mock(return_value=deepcopy(retained))
    thermal_call = Mock(return_value=Foreign())
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_solved_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    argument = deepcopy(supplied)
    if location == "input":
        argument = Foreign(argument)
    elif location == "energy":
        energy_call.return_value = Foreign(retained)
    actual = bridge.evaluate_tabulated_solved_electrothermal(argument)
    if location == "input":
        assert actual["status"] == "MODEL_INAPPLICABLE"
        energy_call.assert_not_called()
        thermal_call.assert_not_called()
    else:
        assert_atomic(actual, location, retained if location == "thermal" else None)
        energy_call.assert_called_once()
        assert thermal_call.call_count == int(location == "thermal")
    hooks.assert_not_called()


def test_snapshot_rejects_excess_depth_before_models(monkeypatch):
    supplied = request()
    nested = None
    for _ in range(29):
        nested = [nested]
    supplied["thermal_body"]["property_source"] = nested
    forbidden = forbid_models(monkeypatch)
    actual = bridge.evaluate_tabulated_solved_electrothermal(supplied)
    assert actual["status"] == "MODEL_INAPPLICABLE"
    assert actual["request_sha256"] is actual["evaluation_sha256"] is None
    assert all(actual[key] == 0 for key in bridge._COUNTS)
    forbidden.assert_not_called()


@pytest.fixture(scope="module")
def actual_unmet_energy():
    supplied = request()
    solve = supplied["energy_request"]["segments"][0]["power_request"]["solve"]
    solve["max_evaluations"] = 2
    solve["required_net_force_body_n"][0] = 100.0
    retained = bridge.energy.evaluate_tabulated_solved_dc_energy(deepcopy(supplied["energy_request"]))
    assert retained["status"] == "COMPUTED_EXPERIMENTAL", retained["reasons"]
    assert retained["outputs"]["energy_state"] == "NOT_RUN_RESIDUAL_UNMET"
    return supplied, retained


@pytest.mark.parametrize("path,value", [
    (("outputs", "energy_state"), "COMPUTED"),
    (("outputs", "energy"), {}),
    (("transfers",), [{"invented": True}]),
    (("output_units", "energy"), {}),
    (("motor_result_count",), 0),
    (("stages",), []),
])
def test_mixed_unmet_rehashed_forgeries_rejected_without_thermal(monkeypatch, actual_unmet_energy,
                                                               path, value):
    supplied, retained = actual_unmet_energy
    forged = deepcopy(retained)
    mutate(forged, path, value)
    reseal(forged)
    forbidden = forbid_models(monkeypatch)
    with pytest.raises(ValueError):
        bridge._guard_energy_success(forged, supplied["energy_request"])
    forbidden.assert_not_called()
    energy_call = Mock(return_value=forged)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_solved_dc_energy", energy_call)
    actual = bridge.evaluate_tabulated_solved_electrothermal(deepcopy(supplied))
    assert_atomic(actual, "energy")
    energy_call.assert_called_once()
    forbidden.assert_not_called()
    assert_seal(actual, supplied)


def test_catalog_is_fresh_and_has_both_dynamic_unit_variants(monkeypatch):
    forbidden = forbid_models(monkeypatch)
    original = bridge.tabulated_solved_electrothermal_catalog()
    altered = bridge.tabulated_solved_electrothermal_catalog()
    for catalog in (original, altered):
        assert catalog["required_fields"] == list(bridge._ROOT)
        assert catalog["count_units"] == dict.fromkeys(bridge._COUNTS, "1")
        assert catalog["output_field_units"]["thermal"] == {"outputs": bridge._OUTPUT_UNITS}
        assert catalog["output_field_units_residual_unmet"]["thermal"] == "not_applicable"
        assert catalog["output_field_units_residual_unmet"]["energy"]["outputs"]["energy"] == "not_applicable"
        for units in (catalog["output_field_units"], catalog["output_field_units_residual_unmet"]):
            variants = units["energy"]["outputs"]["points"]["row_variants"]
            assert set(variants) == {"COMPUTED", "NOT_RUN_RESIDUAL_UNMET"}
    altered["limits"]["input_json"]["max_depth"] = 0
    altered["energy_catalog"]["point_catalog"]["limits"]["input_json"]["max_depth"] = 0
    altered["output_field_units"]["thermal"]["outputs"]["segments"]["duration_s"] = "W"
    altered["output_field_units_residual_unmet"]["energy"]["outputs"]["points"]["row_variants"].clear()
    altered["status_reason_matrix"]["EXECUTION_FAILED"].clear()
    altered["limitations"].clear()
    assert bridge.tabulated_solved_electrothermal_catalog() == original
    forbidden.assert_not_called()


def test_actual_thermal_refusal_preserves_guarded_energy_only(monkeypatch):
    supplied = request(count=1, conductance=1e100)
    supplied["energy_request"]["segments"][0]["duration_s"] = 1e100
    evaluate_energy = bridge.energy.evaluate_tabulated_solved_dc_energy
    retained = []

    def capture_energy(argument):
        result = evaluate_energy(argument)
        retained.append(deepcopy(result))
        return result

    energy_call = Mock(side_effect=capture_energy)
    thermal_call = Mock(wraps=bridge.thermal.screen_thermal)
    integrator = Mock(wraps=bridge.thermal.integrate_segment)
    monkeypatch.setattr(bridge.energy, "evaluate_tabulated_solved_dc_energy", energy_call)
    monkeypatch.setattr(bridge.thermal, "screen_thermal", thermal_call)
    monkeypatch.setattr(bridge.thermal, "integrate_segment", integrator)
    actual = bridge.evaluate_tabulated_solved_electrothermal(supplied)
    assert retained[0]["status"] == "COMPUTED_EXPERIMENTAL"
    assert_atomic(actual, "thermal", retained[0])
    assert actual["assembly_evaluation_count"] > 0
    assert actual["forward_evaluation_count"] > 0
    energy_call.assert_called_once()
    thermal_call.assert_called_once()
    integrator.assert_called_once()
    assert_seal(actual, supplied)
