"""Actual accepted component baselines for the fixed reference-air target."""

from copy import deepcopy
from dataclasses import asdict
from unittest.mock import Mock

import pytest

from physimesh.drone import reference_air_tabulated_hover_thrust_target as workflow
from physimesh.drone import tabulated_hover_bemt_request as forward
from physimesh.drone import tabulated_hover_thrust_target as inverse
from physimesh.drone.provenance import sha256_record
from physimesh.drone.reference_air_properties import reference_air_properties
from tests.drone.test_tabulated_hover_bemt import inputs


def actual_baseline(altitude=0, kind="geometric", omega=100.0):
    """Actual known-speed target and direct inverse, outside measured execution."""
    air_request = {"altitude_m": altitude, "altitude_kind": kind}
    air = asdict(reference_air_properties(**air_request))
    rotor = {"evaluation": forward.EVALUATION, **inputs(angular_speed_rad_s=omega)}
    rotor["density_kg_m3"] = air["state"]["density_kg_m3"]
    known = forward.evaluate_tabulated_hover_bemt(rotor)
    assert known["status"] == "COMPUTED_EXPERIMENTAL"
    del rotor["angular_speed_rad_s"]
    injected = {
        "evaluation": inverse.EVALUATION, "rotor_template": rotor,
        "target_thrust_n": known["outputs"]["thrust_n"],
        "angular_speed_bracket_rad_s": [50.0, 150.0],
        "absolute_thrust_tolerance_n": 1e-10, "max_evaluations": 32,
    }
    direct = inverse.evaluate_tabulated_hover_thrust_target(deepcopy(injected))
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    target = deepcopy(injected)
    del target["rotor_template"]["density_kg_m3"]
    supplied = {"evaluation": workflow.EVALUATION, "air": air_request, "target_template": target}
    return supplied, air, injected, direct


def actual_spies(monkeypatch):
    air = Mock(wraps=workflow.reference_air_properties)
    target = Mock(wraps=workflow.evaluate_tabulated_hover_thrust_target)
    trial = Mock(wraps=inverse.evaluate_tabulated_hover_bemt)
    core = Mock(wraps=forward.solve_tabulated_hover)
    guard = Mock(wraps=workflow.validate_tabulated_hover_thrust_target_result)
    monkeypatch.setattr(workflow, "reference_air_properties", air)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_thrust_target", target)
    monkeypatch.setattr(inverse, "evaluate_tabulated_hover_bemt", trial)
    monkeypatch.setattr(forward, "solve_tabulated_hover", core)
    monkeypatch.setattr(workflow, "validate_tabulated_hover_thrust_target_result", guard)
    return air, target, trial, core, guard


def assert_digest(result):
    assert result["evaluation_sha256"] == sha256_record({
        key: value for key, value in result.items() if key != "evaluation_sha256"
    })


def assert_success(result, supplied, air, injected, direct):
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["diagnostics_complete"] is True
    assert result["outputs"] == {"air": air, "target": direct}
    assert result["request_sha256"] == sha256_record(supplied)
    assert_digest(result)
    assert result["inverse_evaluation_count"] == direct["evaluation_count"]
    assert type(result["inverse_evaluation_count"]) is int
    assert result["output_units"] == {
        "air": workflow.reference_air_tabulated_hover_thrust_target_catalog()["output_field_units"]["air"],
        "target": direct["output_units"],
    }
    assert result["stages"] == [
        {"stage": "air", "inputs": supplied["air"], "inputs_sha256": sha256_record(supplied["air"]),
         "result_sha256": sha256_record(air)},
        {"stage": "target", "inputs": injected, "inputs_sha256": sha256_record(injected),
         "result_sha256": sha256_record(direct)},
    ]
    assert result["transfers"] == [{
        "from_stage": "air", "from_field": "state.density_kg_m3", "to_stage": "target",
        "to_field": "rotor_template.density_kg_m3", "value": air["state"]["density_kg_m3"],
        "unit": "kg/m^3", "producer_result_sha256": sha256_record(air),
        "consumer_request_sha256": sha256_record(injected),
    }]
    assert result["evidence_level"] == "unverified"
    assert result["aircraft_status"] is result["feasibility"] is None
    for name in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert result[name] == "NOT_ESTABLISHED"


@pytest.mark.parametrize("altitude,kind", [
    (0, "geometric"), (10000, "geometric"), (20000, "geometric"),
    (11000, "geopotential"), (20000, "geopotential"), (30000, "geopotential"),
])
def test_actual_air_direct_inverse_full_equality(monkeypatch, altitude, kind):
    supplied, air, injected, direct = actual_baseline(altitude, kind)
    before = deepcopy(supplied)
    air_call, target_call, trial, core, guard = actual_spies(monkeypatch)
    result = workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)
    assert_success(result, supplied, air, injected, direct)
    assert supplied == before
    air_call.assert_called_once_with(**supplied["air"])
    target_call.assert_called_once_with(injected)
    assert trial.call_count == core.call_count == direct["evaluation_count"] == 3
    guard.assert_called_once_with(result["outputs"]["target"], injected)


def assert_atomic(result, status, count, supplied=None):
    assert result["status"] == status
    assert result["diagnostics_complete"] is False
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == result["transfers"] == []
    assert type(result["inverse_evaluation_count"]) is int
    assert result["inverse_evaluation_count"] == count
    assert result["request_sha256"] == (sha256_record(supplied) if supplied is not None else None)
    if supplied is not None and status != "MODEL_INAPPLICABLE":
        assert_digest(result)
    else:
        assert result["evaluation_sha256"] is None
    assert result["evidence_level"] == "unverified"
    assert result["aircraft_status"] is result["feasibility"] is None
    for name in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert result[name] == "NOT_ESTABLISHED"


def direct_for(supplied):
    air = asdict(reference_air_properties(**supplied["air"]))
    injected = deepcopy(supplied["target_template"])
    injected["rotor_template"]["density_kg_m3"] = air["state"]["density_kg_m3"]
    return air, injected, inverse.evaluate_tabulated_hover_thrust_target(deepcopy(injected))


@pytest.mark.parametrize("omega", [50.0, 150.0])
def test_actual_endpoint_full_equality(monkeypatch, omega):
    supplied, air, injected, direct = actual_baseline(omega=omega)
    spies = actual_spies(monkeypatch)
    result = workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)
    assert_success(result, supplied, air, injected, direct)
    assert result["outputs"]["target"]["outputs"]["angular_speed_rad_s"] == omega
    assert [spy.call_count for spy in spies] == [1, 1, 2, 2, 1]


@pytest.mark.parametrize("case,status,count", [
    ("zero", "TARGET_NOT_BRACKETED", 2),
    ("budget", "ITERATION_LIMIT", 2),
    ("chord", "MODEL_INAPPLICABLE", 1),
])
def test_actual_atomic_refusals(monkeypatch, case, status, count):
    supplied, _, _, _ = actual_baseline()
    if case == "zero":
        for station in supplied["target_template"]["rotor_template"]["stations"]:
            station["blade_angle_rad"] = 0.0
    elif case == "budget":
        supplied["target_template"]["max_evaluations"] = 2
    else:
        supplied["target_template"]["rotor_template"]["stations"][0]["chord_m"] = -1.0
    _, _, direct = direct_for(supplied)
    assert direct["status"] == status and direct["evaluation_count"] == count
    spies = actual_spies(monkeypatch)
    result = workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, status, count, supplied)
    assert result["reasons"] == [workflow.reference_air_tabulated_hover_thrust_target_catalog()[
        "status_reason_matrix"][status][-1]]
    assert [spy.call_count for spy in spies] == [1, 1, count, count, 1]


class ForeignDict(dict):
    def __deepcopy__(self, memo):
        raise AssertionError("Foreign copy hook was invoked")


class ForeignNumber(float):
    def __float__(self):
        raise AssertionError("Foreign numeric hook was invoked")


class ForeignValue:
    def __deepcopy__(self, memo):
        raise AssertionError("Foreign copy hook was invoked")


def malformed(supplied, case):
    target = supplied["target_template"]
    rotor = target["rotor_template"]
    if case == "negative_air":
        supplied["air"]["altitude_m"] = -1
    elif case == "air_bool":
        supplied["air"]["altitude_m"] = True
    elif case == "air_kind":
        supplied["air"]["altitude_kind"] = "weather"
    elif case == "air_missing":
        supplied["air"].pop("altitude_kind")
    elif case == "air_extra":
        supplied["air"]["extra"] = 0
    elif case in ("density_kg_m3", "angular_speed_rad_s"):
        rotor[case] = 1.0
    elif case == "target_missing":
        target.pop("absolute_thrust_tolerance_n")
    elif case == "target_extra":
        target["extra"] = 0
    elif case == "rotor_missing":
        rotor.pop("radius_m")
    elif case == "target_evaluation":
        target["evaluation"] = "other"
    elif case == "rotor_evaluation":
        rotor["evaluation"] = "other"
    elif case == "blank_source":
        rotor["geometry_source"] = " \t"
    elif case == "blank_uncertainty":
        rotor["uncertainty_status"] = " "
    elif case == "classification":
        rotor["geometry_kind"] = "verified"
    elif case == "numeric_bool":
        rotor["radius_m"] = True
    elif case == "station_bool":
        rotor["stations"][0]["chord_m"] = False
    elif case == "station_fields":
        rotor["stations"][0]["extra"] = 0
    elif case == "stations257":
        rotor["stations"] = [deepcopy(rotor["stations"][0]) for _ in range(257)]
    elif case == "stations1":
        rotor["stations"] = rotor["stations"][:1]
    elif case in ("annuli0", "annuli513", "blades33", "count1", "count65", "count_bool", "work"):
        if case.startswith("annuli"):
            rotor["annuli"] = 0 if case == "annuli0" else 513
        elif case == "blades33":
            rotor["blade_count"] = 33
        elif case == "work":
            rotor["annuli"], target["max_evaluations"] = 512, 65
        else:
            target["max_evaluations"] = {"count1": 1, "count65": 65, "count_bool": True}[case]
    elif case in ("target_zero", "tolerance_zero", "tolerance_equal", "bracket_equal", "bracket_tuple",
                  "bracket_bool", "bracket_reverse", "subnormal"):
        if case == "target_zero":
            target["target_thrust_n"] = 0
        elif case == "tolerance_zero":
            target["absolute_thrust_tolerance_n"] = 0
        elif case == "tolerance_equal":
            target["absolute_thrust_tolerance_n"] = target["target_thrust_n"]
        elif case == "bracket_equal":
            target["angular_speed_bracket_rad_s"] = [50, 50]
        elif case == "bracket_tuple":
            target["angular_speed_bracket_rad_s"] = (50, 150)
        elif case == "bracket_bool":
            target["angular_speed_bracket_rad_s"] = [True, 150]
        elif case == "bracket_reverse":
            target["angular_speed_bracket_rad_s"] = [150, 50]
        else:
            target["absolute_thrust_tolerance_n"] = 5e-324
    elif case == "cycle":
        supplied["extra"] = supplied
    elif case == "foreign_dict":
        return ForeignDict(supplied)
    elif case == "foreign_number":
        supplied["air"]["altitude_m"] = ForeignNumber(0)
    elif case == "foreign_value":
        supplied["extra"] = ForeignValue()
    elif case == "utf8":
        rotor["geometry_source"] = "\ud800"
    elif case == "nan":
        rotor["radius_m"] = float("nan")
    elif case == "infinity":
        rotor["radius_m"] = float("inf")
    elif case == "integer":
        rotor["annuli"] = 1 << 1023
    elif case == "string":
        rotor["geometry_source"] = "\U0001f680" * 2001
    elif case == "depth":
        value = []
        for _ in range(12):
            value = [value]
        supplied["extra"] = value
    elif case == "nodes":
        supplied["extra"] = [[0] * 256 for _ in range(128)]
    elif case == "root_fields":
        supplied["extra"] = 0
    elif case == "root_list":
        return [supplied]
    else:
        raise AssertionError(case)
    return supplied


@pytest.mark.parametrize("case", [
    "negative_air", "air_bool", "air_kind", "air_missing", "air_extra",
    "density_kg_m3", "angular_speed_rad_s", "target_missing", "target_extra", "rotor_missing",
    "target_evaluation", "rotor_evaluation", "blank_source", "blank_uncertainty", "classification",
    "numeric_bool", "station_bool", "station_fields", "stations257", "stations1",
    "annuli0", "annuli513", "blades33", "count1", "count65", "count_bool", "work",
    "target_zero", "tolerance_zero", "tolerance_equal", "bracket_equal", "bracket_tuple",
    "bracket_bool", "bracket_reverse", "subnormal", "cycle", "foreign_dict", "foreign_number",
    "foreign_value", "utf8", "nan", "infinity", "integer", "string", "depth", "nodes",
    "root_fields", "root_list",
])
def test_preflight_rejects_before_any_component_or_foreign_hook(monkeypatch, case):
    supplied, _, _, _ = actual_baseline()
    supplied = malformed(supplied, case)
    spies = actual_spies(monkeypatch)
    result = workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "MODEL_INAPPLICABLE", 0)
    assert result["reasons"] == ["Invalid bounded reference-air target request."]
    for spy in spies:
        spy.assert_not_called()


def test_unsupported_evaluation_has_no_calls_or_hashes(monkeypatch):
    supplied, _, _, _ = actual_baseline()
    supplied["evaluation"] = "other"
    spies = actual_spies(monkeypatch)
    result = workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "SOLVER_UNSUPPORTED", 0)
    assert result["reasons"] == ["Unsupported evaluation."]
    for spy in spies:
        spy.assert_not_called()


def test_maximum_station_annuli_budget_endpoint_and_no_payload_duplicates(monkeypatch):
    supplied, _, _, _ = actual_baseline(omega=50.0)
    rotor = supplied["target_template"]["rotor_template"]
    rotor["stations"] = [
        {"radius_m": index / 255, "chord_m": 0.04, "blade_angle_rad": 0.08}
        for index in range(256)
    ]
    rotor["annuli"] = 512
    supplied["target_template"]["max_evaluations"] = 64
    air = asdict(reference_air_properties(**supplied["air"]))
    known = forward.evaluate_tabulated_hover_bemt({
        **rotor, "density_kg_m3": air["state"]["density_kg_m3"], "angular_speed_rad_s": 50.0,
    })
    assert known["status"] == "COMPUTED_EXPERIMENTAL"
    supplied["target_template"]["target_thrust_n"] = known["outputs"]["thrust_n"]
    air, injected, direct = direct_for(supplied)
    spies = actual_spies(monkeypatch)
    result = workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)
    assert_success(result, supplied, air, injected, direct)
    assert [spy.call_count for spy in spies] == [1, 1, 2, 2, 1]
    forward._json_walk(result, result["limits"]["output_json"])

    def occurrences(value, wanted):
        count = int(type(value) is dict and value == wanted)
        if type(value) is dict:
            count += sum(occurrences(child, wanted) for child in value.values())
        elif type(value) is list:
            count += sum(occurrences(child, wanted) for child in value)
        return count

    assert occurrences(result, air) == occurrences(result, direct) == 1
    assert occurrences(result, direct["outputs"]["actual_forward_result"]) == 1
    for stage in result["stages"]:
        assert stage.keys() == {"stage", "inputs", "inputs_sha256", "result_sha256"}
    assert len(result["outputs"]["target"]["outputs"]["actual_forward_result"]["outputs"]["radii_m"]) == 512


def test_adjacent_actual_speeds_numerical_limit(monkeypatch):
    import math
    import sys

    supplied, air, injected, _ = actual_baseline()
    # Find a fixed adjacent-speed pair with a representable interior thrust.
    # These actual forward fixture calls all precede the measured workflow.
    for lo in (50.0, 75.0, 100.0, 125.0, 150.0, 200.0, 250.0, 300.0):
        hi = math.nextafter(lo, math.inf)
        thrusts = [forward.evaluate_tabulated_hover_bemt({
            **injected["rotor_template"], "angular_speed_rad_s": speed,
        })["outputs"]["thrust_n"] for speed in (lo, hi)]
        target = thrusts[0] + (thrusts[1] - thrusts[0]) / 2
        if thrusts[0] < target < thrusts[1]:
            break
    else:
        pytest.fail("Actual adjacent-speed fixture has no representable interior thrust")
    supplied["target_template"].update(
        target_thrust_n=target, angular_speed_bracket_rad_s=[lo, hi],
        absolute_thrust_tolerance_n=sys.float_info.min,
    )
    actual_air, _, direct = direct_for(supplied)
    assert actual_air == air
    assert direct["status"] == "NUMERICAL_LIMIT" and direct["evaluation_count"] == 2
    spies = actual_spies(monkeypatch)
    result = workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "NUMERICAL_LIMIT", 2, supplied)
    assert result["reasons"] == ["Actual target reached a representable numerical limit."]
    assert [spy.call_count for spy in spies] == [1, 1, 2, 2, 1]


def test_fresh_catalog_nested_metadata():
    catalog = workflow.reference_air_tabulated_hover_thrust_target_catalog()
    before = deepcopy(catalog)
    catalog["limits"]["core_work"]["annuli_max"] = 0
    catalog["input_units"]["target_template"]["rotor_template"]["stations"]["chord_m"] = "wrong"
    catalog["output_field_units"]["air"]["state"]["density_kg_m3"] = "wrong"
    catalog["status_reason_matrix"]["MODEL_INAPPLICABLE"].clear()
    catalog["limitations"].clear()
    catalog["required_fields"].clear()
    assert workflow.reference_air_tabulated_hover_thrust_target_catalog() == before
    assert before["required_fields"] == ["evaluation", "air", "target_template"]
    assert before["target_template_fields"] == list(inverse._REQUEST_KEYS)
    assert "density_kg_m3" not in before["rotor_template_fields"]
    assert "angular_speed_rad_s" not in before["rotor_template_fields"]
    assert before["limits"]["input_json"] == {
        "root_depth": 1, "max_depth": 12, "max_nodes_including_keys": 32768,
        "max_container_items": 256, "max_string_characters": 2000, "max_integer_bits": 1023,
        "finite_floats_only": True, "valid_utf8_only": True,
    }
    assert before["limits"]["inverse_input_json"] == inverse._LIMITS["input_json"]
    assert before["limits"]["inverse_output_json"] == inverse._LIMITS["output_json"]
    assert before["limits"]["forward_input_json"] == forward._LIMITS["input_json"]
    assert before["limits"]["forward_output_json"] == forward._LIMITS["output_json"]
    assert before["limits"]["output_json"]["max_nodes_including_keys"] == 131072
    assert before["limits"]["output_json"]["max_depth"] == 20
    assert before["limits"]["output_json"]["max_container_items"] == 2048


@pytest.mark.parametrize("forge", [
    "coherent_pressure_density", "viscosity", "state_type", "air_type", "air_marker",
    "state_marker", "altitude", "sound", "gravity", "extra_field", "density_type",
])
def test_actual_air_corruption_stops_before_inverse(monkeypatch, forge):
    supplied, _, _, _ = actual_baseline()
    actual = reference_air_properties(**supplied["air"])
    if forge == "coherent_pressure_density":
        for name in ("pressure_pa", "density_kg_m3"):
            object.__setattr__(actual.state, name, getattr(actual.state, name) * 1.01)
    elif forge == "viscosity":
        object.__setattr__(actual, "dynamic_viscosity_pa_s", actual.dynamic_viscosity_pa_s * 1.01)
    elif forge == "state_type":
        object.__setattr__(actual, "state", asdict(actual.state))
    elif forge == "air_type":
        actual = asdict(actual)
    elif forge == "air_marker":
        object.__setattr__(actual, "physical_qualification", "ESTABLISHED")
    elif forge == "state_marker":
        object.__setattr__(actual.state, "evidence_status", "verified")
    elif forge == "altitude":
        object.__setattr__(actual.state, "input_altitude_m", 1.0)
    elif forge == "sound":
        object.__setattr__(actual, "speed_of_sound_m_s", actual.speed_of_sound_m_s * 1.01)
    elif forge == "gravity":
        object.__setattr__(actual, "gravity_m_s2", actual.gravity_m_s2 * 1.01)
    elif forge == "extra_field":
        vars(actual)["extra"] = 0
    elif forge == "density_type":
        object.__setattr__(actual.state, "density_kg_m3", True)
    air, target, trial, core, guard = actual_spies(monkeypatch)
    air.side_effect = lambda **kwargs: actual
    result = workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "EXECUTION_FAILED", 0, supplied)
    air.assert_called_once()
    for spy in (target, trial, core, guard):
        spy.assert_not_called()


def rehash(actual):
    actual["evaluation_sha256"] = sha256_record({
        key: value for key, value in actual.items() if key != "evaluation_sha256"
    })


def forge_inverse(actual, case):
    outputs = actual["outputs"]
    if case == "root_extra":
        actual["extra"] = 0
    elif case == "root_missing":
        actual.pop("runtime_identity")
    elif case == "marker":
        actual["physical_validation"] = "ESTABLISHED"
    elif case == "diagnostics":
        actual["diagnostics_complete"] = 1
    elif case == "units":
        actual["output_units"]["achieved_thrust_n"] = "kg"
    elif case == "nested_units":
        actual["output_units"]["actual_forward_result"]["thrust_n"] = "kg"
    elif case == "request_hash":
        actual["request_sha256"] = "0" * 64
    elif case == "count_bool":
        actual["evaluation_count"] = True
    elif case == "count_high":
        actual["evaluation_count"] = 65
    elif case == "count_plausible":
        actual["evaluation_count"] = 2
    elif case == "selected_request":
        outputs["actual_forward_request"]["angular_speed_rad_s"] = 101.0
    elif case == "selected_density":
        outputs["actual_forward_request"]["density_kg_m3"] *= 1.01
    elif case == "selected_child":
        child_result = outputs["actual_forward_result"]
        child_result["outputs"]["radii_m"][0] += 0.001
        rehash(child_result)
        actual["trace"][-1]["full_actual_result_sha256"] = sha256_record(child_result)
    elif case == "child_marker":
        child_result = outputs["actual_forward_result"]
        child_result["physical_validation"] = "ESTABLISHED"
        rehash(child_result)
        actual["trace"][-1]["full_actual_result_sha256"] = sha256_record(child_result)
    elif case == "trace_speed":
        actual["trace"][0]["angular_speed_rad_s"] = 51.0
    elif case == "trace_residual":
        actual["trace"][0]["thrust_residual_n"] += 1.0
    elif case == "trace_hash":
        actual["trace"][0]["request_sha256"] = "0" * 64
    elif case == "trace_digest_format":
        actual["trace"][0]["full_actual_result_sha256"] = "G" * 64
    elif case == "selected_digest":
        actual["trace"][-1]["full_actual_result_sha256"] = "0" * 64
    elif case == "residual":
        outputs["thrust_residual_n"] = 1.0
    elif case == "achieved":
        outputs["achieved_thrust_n"] *= 1.01
    elif case == "outputs_count":
        outputs["evaluations"] = 2
    elif case == "failure_with_payload":
        actual["status"] = "TARGET_NOT_BRACKETED"
        actual["reasons"] = ["Target is outside the observed endpoint thrust range."]
        actual["evaluation_count"] = 2
    else:
        raise AssertionError(case)
    rehash(actual)


@pytest.mark.parametrize("case", [
    "root_extra", "root_missing", "marker", "diagnostics", "units", "nested_units", "request_hash",
    "count_bool", "count_high", "count_plausible", "selected_request", "selected_density",
    "selected_child", "child_marker", "trace_speed", "trace_residual", "trace_hash",
    "trace_digest_format", "selected_digest", "residual", "achieved", "outputs_count", "failure_with_payload",
])
def test_rehashed_actual_inverse_forgeries_never_supply_trusted_count(monkeypatch, case):
    supplied, _, _, actual = actual_baseline()
    forge_inverse(actual, case)
    air, target, trial, core, guard = actual_spies(monkeypatch)
    target.side_effect = lambda arguments: actual
    result = workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "EXECUTION_FAILED", 0, supplied)
    assert result["reasons"] == ["Reference-air target execution or returned contract failed."]
    air.assert_called_once()
    target.assert_called_once()
    guard.assert_called_once()
    trial.assert_not_called()
    core.assert_not_called()


def test_intermediate_producer_digest_format_only_is_preserved(monkeypatch):
    supplied, air, injected, actual = actual_baseline()
    actual["trace"][0]["full_actual_result_sha256"] = "0123456789abcdef" * 4
    rehash(actual)
    _, target, trial, core, guard = actual_spies(monkeypatch)
    target.side_effect = lambda arguments: actual
    result = workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)
    assert_success(result, supplied, air, injected, actual)
    assert any("FORMAT-ONLY" in limitation for limitation in result["limitations"])
    guard.assert_called_once()
    trial.assert_not_called()
    core.assert_not_called()


def test_air_snapshot_and_density_detach_before_actual_inverse(monkeypatch):
    supplied, air, injected, direct = actual_baseline()
    actual_air = reference_air_properties(**supplied["air"])
    real_inverse = workflow.evaluate_tabulated_hover_thrust_target
    air_call, target, trial, core, guard = actual_spies(monkeypatch)
    air_call.side_effect = lambda **kwargs: actual_air

    def mutate_retained_air(arguments):
        object.__setattr__(actual_air.state, "density_kg_m3", 999.0)
        vars(actual_air.state)["pressure_pa"] = -1.0
        object.__setattr__(actual_air, "dynamic_viscosity_pa_s", -1.0)
        return real_inverse(arguments)

    target.side_effect = mutate_retained_air
    result = workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)
    assert_success(result, supplied, air, injected, direct)
    assert actual_air.state.density_kg_m3 == 999.0
    assert [spy.call_count for spy in (air_call, target, trial, core, guard)] == [1, 1, 3, 3, 1]


def test_actual_inverse_result_is_detached_before_guard_and_after_return(monkeypatch):
    supplied, air, injected, actual = actual_baseline()
    pristine = deepcopy(actual)
    real_guard = workflow.validate_tabulated_hover_thrust_target_result
    _, target, trial, core, guard = actual_spies(monkeypatch)
    target.side_effect = lambda arguments: actual

    def mutate_original_during_guard(retained, request):
        assert retained is not actual
        actual["outputs"]["actual_forward_result"]["outputs"]["radii_m"][0] = -999.0
        actual["trace"].clear()
        return real_guard(retained, request)

    guard.side_effect = mutate_original_during_guard
    result = workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)
    assert_success(result, supplied, air, injected, pristine)
    before = deepcopy(result)
    actual.clear()
    assert result == before
    trial.assert_not_called()
    core.assert_not_called()


@pytest.mark.parametrize("change_result", [False, True])
def test_inverse_argument_mutation_cannot_change_original_binding(monkeypatch, change_result):
    supplied, air, injected, original_result = actual_baseline()
    before = deepcopy(supplied)
    _, target, trial, core, _ = actual_spies(monkeypatch)
    real_inverse = inverse.evaluate_tabulated_hover_thrust_target

    def mutate_arguments(arguments):
        arguments["rotor_template"]["density_kg_m3"] *= 1.01
        arguments["absolute_thrust_tolerance_n"] *= 2
        if change_result:
            return real_inverse(arguments)
        return original_result

    target.side_effect = mutate_arguments
    result = workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)
    assert supplied == before
    if change_result:
        assert_atomic(result, "EXECUTION_FAILED", 0, supplied)
        assert 2 <= trial.call_count == core.call_count <= supplied["target_template"]["max_evaluations"]
    else:
        assert_success(result, supplied, air, injected, original_result)
        trial.assert_not_called()
        core.assert_not_called()


@pytest.mark.parametrize("component", ["air", "inverse"])
def test_ordinary_component_exception_is_sanitized(monkeypatch, component):
    supplied, _, _, _ = actual_baseline()
    spies = actual_spies(monkeypatch)
    spies[0 if component == "air" else 1].side_effect = RuntimeError("private payload secret")
    result = workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "EXECUTION_FAILED", 0, supplied)
    assert "private payload secret" not in str(result)
    assert spies[0].call_count == 1
    assert spies[1].call_count == (component == "inverse")
    for spy in spies[2:]:
        spy.assert_not_called()


@pytest.mark.parametrize("component", ["air", "inverse", "guard"])
def test_component_base_exception_propagates(monkeypatch, component):
    supplied, _, _, _ = actual_baseline()
    spies = actual_spies(monkeypatch)
    spies[{"air": 0, "inverse": 1, "guard": 4}[component]].side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)


def test_actual_inverse_execution_failed_retains_only_accepted_count(monkeypatch):
    supplied, _, injected, _ = actual_baseline()
    with monkeypatch.context() as patch:
        patch.setattr(inverse, "evaluate_tabulated_hover_bemt", Mock(side_effect=RuntimeError("private")))
        failed = inverse.evaluate_tabulated_hover_thrust_target(deepcopy(injected))
    assert failed["status"] == "EXECUTION_FAILED" and failed["evaluation_count"] == 1
    assert workflow.validate_tabulated_hover_thrust_target_result(failed, injected) is None
    _, target, trial, core, guard = actual_spies(monkeypatch)
    target.side_effect = lambda arguments: failed
    result = workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "EXECUTION_FAILED", 1, supplied)
    assert "private" not in str(result)
    guard.assert_called_once()
    trial.assert_not_called()
    core.assert_not_called()


@pytest.mark.parametrize("reason", ["Request snapshot failed.", "unexpected private infrastructure fault"])
def test_unexpected_actual_inverse_fault_envelope_is_not_accepted(monkeypatch, reason):
    supplied, _, injected, _ = actual_baseline()
    with monkeypatch.context() as patch:
        patch.setattr(inverse, "evaluate_tabulated_hover_bemt", Mock(side_effect=RuntimeError))
        actual = inverse.evaluate_tabulated_hover_thrust_target(deepcopy(injected))
    actual["reasons"] = [reason]
    rehash(actual)
    _, target, _, _, _ = actual_spies(monkeypatch)
    target.side_effect = lambda arguments: actual
    result = workflow.evaluate_reference_air_tabulated_hover_thrust_target(supplied)
    assert_atomic(result, "EXECUTION_FAILED", 0, supplied)
    assert reason not in str(result)
