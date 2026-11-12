"""Contract checks for the isolated V103 tabulated-hover request adapter."""

import math
import sys
from copy import deepcopy
from dataclasses import asdict, replace
from inspect import Parameter, signature
from unittest.mock import Mock

import pytest

from physimesh.drone import tabulated_hover_bemt_request as adapter
from physimesh.drone.provenance import sha256_record
from physimesh.drone.tabulated_hover_bemt import solve_tabulated_hover
from tests.drone.test_tabulated_hover_bemt import inputs

EXPECTED_UNITS = {
    "radius_m": "m", "root_cutout_m": "m", "geometry_source": "text",
    "geometry_kind": "label", "uncertainty_status": "text",
    "stations": {"radius_m": "m", "chord_m": "m", "blade_angle_rad": "rad"},
    "radii_m": "m", "chord_m": "m", "blade_angle_rad": "rad",
    "radial_fraction": "1", "local_solidity": "1", "inflow_ratio": "1",
    "approx_inflow_angle_rad": "rad", "approx_angle_of_attack_rad": "rad",
    "thrust_coefficient": "1", "blade_thrust_coefficient": "1",
    "induced_power_coefficient": "1", "profile_power_coefficient": "1",
    "shaft_power_coefficient": "1", "thrust_n": "N", "shaft_power_w": "W",
    "shaft_torque_nm": "N*m", "thrust_balance_coefficient": "1",
    "local_balance_coefficient": "1", "max_local_balance_coefficient": "1", "annuli": "1",
}


def assert_plain_json_and_count_nodes(value):
    """Count keys too, independently of the adapter's walker."""
    kind = type(value)
    if kind is dict:
        assert all(type(key) is str for key in value)
        return 1 + sum(1 + assert_plain_json_and_count_nodes(child) for child in value.values())
    if kind is list:
        return 1 + sum(assert_plain_json_and_count_nodes(child) for child in value)
    assert kind in (str, int, float, bool, type(None))
    return 1


def assert_response_hashes(response, request):
    assert response["request_sha256"] == sha256_record(request)
    assert response["request_sha256"] is not None
    unhashed = {key: value for key, value in response.items() if key != "evaluation_sha256"}
    assert unhashed["request_sha256"] == response["request_sha256"]
    assert response["evaluation_sha256"] == sha256_record(unhashed)


def test_actual_core_equivalence_full_units_hashes_and_one_call(monkeypatch):
    core_request = inputs()
    request = {"evaluation": adapter.EVALUATION, **core_request}
    original_request = deepcopy(request)
    actual = solve_tabulated_hover(**core_request)
    expected = asdict(actual)
    for name in ("model", "version", "status", "physical_validation"):
        del expected[name]
    expected = {name: list(value) if type(value) is tuple else value
                for name, value in expected.items()}

    # The baseline above is outside evaluation. Every core invocation made by
    # the adapter, including any attempted validation rerun, reaches this spy.
    core_spy = Mock(side_effect=solve_tabulated_hover)
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)
    response = adapter.evaluate_tabulated_hover_bemt(request)

    core_spy.assert_called_once_with(**core_request)
    assert request == original_request
    assert response["status"] == "COMPUTED_EXPERIMENTAL"
    assert response["diagnostics_complete"] is True
    assert response["reasons"] == []
    assert response["evaluation"] == "tabulated_geometry_hover_experimental"
    assert response["model_id"] == "tabulated_geometry_hover_v0_1"
    assert response["schema_version"] == "tabulated_hover_request_v1"
    assert response["core_model"] == actual.model
    assert response["core_version"] == actual.version
    assert response["core_status"] == actual.status
    assert response["physical_validation"] == actual.physical_validation == "NOT_ESTABLISHED"
    assert response["evidence_level"] == "unverified"
    assert response["numerical_qualification"] == response["runtime_identity"] == "NOT_ESTABLISHED"
    assert response["aircraft_status"] is response["feasibility"] is None
    assert response["outputs"] == expected
    assert response["output_units"] == EXPECTED_UNITS
    assert response["outputs"].keys() == response["output_units"].keys()
    assert not {"model", "version", "status", "physical_validation"} & response["outputs"].keys()
    for station in response["outputs"]["stations"]:
        assert station.keys() == response["output_units"]["stations"].keys()
    assert_plain_json_and_count_nodes(response)
    assert_response_hashes(response, original_request)


def test_maximum_stations_annuli_and_blades_fit_separate_output_budget(monkeypatch):
    stations = [
        {"radius_m": index / 255, "chord_m": 0.05, "blade_angle_rad": 0.08}
        for index in range(256)
    ]
    core_request = inputs(stations=stations, annuli=2048, blade_count=32)
    request = {"evaluation": adapter.EVALUATION, **core_request}
    core_spy = Mock(side_effect=solve_tabulated_hover)
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)

    response = adapter.evaluate_tabulated_hover_bemt(request)

    core_spy.assert_called_once_with(**core_request)
    assert response["status"] == "COMPUTED_EXPERIMENTAL"
    assert response["diagnostics_complete"] is True
    outputs = response["outputs"]
    adapter._validate_output_values(outputs, request)
    core_spy.assert_called_once_with(**core_request)
    assert outputs["annuli"] == 2048
    assert len(outputs["stations"]) == 256
    for name in ("radii_m", "chord_m", "blade_angle_rad", "radial_fraction", "local_solidity",
                 "inflow_ratio", "approx_inflow_angle_rad", "approx_angle_of_attack_rad",
                 "local_balance_coefficient"):
        assert type(outputs[name]) is list
        assert len(outputs[name]) == 2048
    assert response["output_units"] == EXPECTED_UNITS
    assert_response_hashes(response, request)
    # Count the entire final envelope, including units, limits and both hashes.
    assert assert_plain_json_and_count_nodes(request) <= 8192
    output_nodes = assert_plain_json_and_count_nodes(response)
    assert 8192 < output_nodes <= 32768
    assert response["limits"]["output_json"]["max_nodes_including_keys"] == 32768
    assert response["limits"]["output_json"]["max_container_items"] == 2048
    assert response["limits"]["input_json"]["max_nodes_including_keys"] == 8192
    assert response["limits"]["input_json"]["max_container_items"] == 256


def test_catalog_returns_fresh_nested_copies_and_exact_kernel_fields():
    first = adapter.tabulated_hover_bemt_catalog()
    baseline = deepcopy(first)
    parameters = signature(solve_tabulated_hover).parameters
    assert len(parameters) == 12
    assert all(parameter.kind is Parameter.KEYWORD_ONLY and parameter.default is Parameter.empty
               for parameter in parameters.values())
    assert first["required_core_kwargs"] == list(parameters)
    assert first["required_fields"] == ["evaluation", *parameters]
    assert len(first["required_fields"]) == 13
    assert first["input_units"].keys() == set(first["required_fields"])
    assert first["output_field_units"] == EXPECTED_UNITS
    assert first["request_contract"]["defaults"] == {}
    assert first["limits"]["input_json"]["root_depth"] == 1
    assert first["limits"]["input_json"]["max_depth"] == 10
    assert first["limits"]["input_json"]["max_nodes_including_keys"] == 8192
    assert first["request_sha256"] is first["evaluation_sha256"] is None

    def poison_nested(value):
        if type(value) is dict:
            for child in list(value.values()):
                poison_nested(child)
            value["caller_mutation"] = True
        elif type(value) is list:
            for child in value:
                poison_nested(child)
            value.append("caller_mutation")

    poison_nested(first)
    assert first != baseline
    assert adapter.tabulated_hover_bemt_catalog() == baseline


def assert_atomic_execution_failure(response, request):
    assert response["status"] == "EXECUTION_FAILED"
    assert response["outputs"] == response["output_units"] == {}
    assert response["diagnostics_complete"] is False
    assert response["reasons"]
    assert response["core_model"] is response["core_version"] is response["core_status"] is None
    assert response["physical_validation"] == "NOT_ESTABLISHED"
    assert response["numerical_qualification"] == response["runtime_identity"] == "NOT_ESTABLISHED"
    assert response["evidence_level"] == "unverified"
    assert response["aircraft_status"] is response["feasibility"] is None
    assert_response_hashes(response, request)


@pytest.mark.parametrize(("field", "changed_value"), [
    pytest.param("model", lambda result: "another_model", id="wrong-model"),
    pytest.param("version", lambda result: "9.9", id="wrong-version"),
    pytest.param("status", lambda result: "VALIDATED", id="wrong-status"),
    pytest.param("physical_validation", lambda result: "ESTABLISHED", id="false-physical-marker"),
    pytest.param("blade_angle_rad", lambda result: (True, *result.blade_angle_rad[1:]), id="theta-bool"),
    pytest.param("blade_angle_rad", lambda result: result.blade_angle_rad[:-1], id="theta-length"),
    pytest.param("blade_angle_rad", lambda result: (float("nan"), *result.blade_angle_rad[1:]),
                 id="theta-nonfinite"),
    pytest.param("inflow_ratio", lambda result: (False, *result.inflow_ratio[1:]), id="inflow-bool"),
    pytest.param("inflow_ratio", lambda result: result.inflow_ratio[:-1], id="inflow-length"),
    pytest.param("inflow_ratio", lambda result: (float("inf"), *result.inflow_ratio[1:]),
                 id="inflow-nonfinite"),
    pytest.param("stations", lambda result: (
        replace(result.stations[0], chord_m=result.stations[0].chord_m * 1.25), *result.stations[1:]),
        id="station-request-binding"),
    pytest.param("geometry_source", lambda result: "different unverified caller source", id="source-binding"),
    pytest.param("radius_m", lambda result: result.radius_m * 2.0, id="radius-binding"),
    pytest.param("root_cutout_m", lambda result: result.root_cutout_m / 2.0, id="cutout-binding"),
])
def test_forged_actual_dataclass_fails_atomically_without_mutation(monkeypatch, field, changed_value):
    core_request = inputs()
    request = {"evaluation": adapter.EVALUATION, **core_request}
    original_request = deepcopy(request)
    actual = solve_tabulated_hover(**core_request)
    original_result = asdict(actual)
    forged = replace(actual, **{field: changed_value(actual)})
    core_spy = Mock(return_value=forged)
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)

    response = adapter.evaluate_tabulated_hover_bemt(request)

    core_spy.assert_called_once_with(**core_request)
    assert_atomic_execution_failure(response, original_request)
    assert request == original_request
    assert asdict(actual) == original_result


def test_coherently_scaled_thrust_power_torque_fail_input_normalization(monkeypatch):
    core_request = inputs()
    request = {"evaluation": adapter.EVALUATION, **core_request}
    original_request = deepcopy(request)
    actual = solve_tabulated_hover(**core_request)
    original_result = asdict(actual)
    forged = replace(actual, thrust_n=actual.thrust_n * 2.0,
                     shaft_power_w=actual.shaft_power_w * 2.0,
                     shaft_torque_nm=actual.shaft_torque_nm * 2.0)
    # Internal P/Q consistency alone would accept these forged dimensional loads.
    assert forged.shaft_torque_nm == forged.shaft_power_w / core_request["angular_speed_rad_s"]
    core_spy = Mock(return_value=forged)
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)

    response = adapter.evaluate_tabulated_hover_bemt(request)

    core_spy.assert_called_once_with(**core_request)
    assert_atomic_execution_failure(response, original_request)
    assert request == original_request
    assert asdict(actual) == original_result


def test_independently_valid_altered_geometry_is_not_the_declared_geometry(monkeypatch):
    core_request = inputs()
    request = {"evaluation": adapter.EVALUATION, **core_request}
    original_request = deepcopy(request)
    altered_request = deepcopy(core_request)
    for station in altered_request["stations"]:
        station["chord_m"] *= 1.25
        station["blade_angle_rad"] *= 1.10
    # This is a genuine internally consistent core solution for a different
    # geometry. It retains the original source labels, radius and cutout.
    actual = solve_tabulated_hover(**altered_request)
    original_result = asdict(actual)
    forged = replace(actual)
    assert list(asdict(forged)["stations"]) != core_request["stations"]
    core_spy = Mock(return_value=forged)
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)

    response = adapter.evaluate_tabulated_hover_bemt(request)

    core_spy.assert_called_once_with(**core_request)
    assert_atomic_execution_failure(response, original_request)
    assert request == original_request
    assert asdict(actual) == original_result


def test_core_runtime_error_is_atomic_hashed_and_does_not_export_exception_text(monkeypatch):
    core_request = inputs()
    request = {"evaluation": adapter.EVALUATION, **core_request}
    original_request = deepcopy(request)
    exception_text = "private-core-failure-detail-DO-NOT-EXPORT"
    core_spy = Mock(side_effect=RuntimeError(exception_text))
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)

    response = adapter.evaluate_tabulated_hover_bemt(request)

    core_spy.assert_called_once_with(**core_request)
    assert_atomic_execution_failure(response, original_request)
    assert exception_text not in repr(response)
    assert "RuntimeError" not in repr(response)
    assert request == original_request


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit])
def test_core_base_exceptions_propagate(monkeypatch, exception_type):
    core_request = inputs()
    request = {"evaluation": adapter.EVALUATION, **core_request}
    original_request = deepcopy(request)
    exception = exception_type("core interruption")
    core_spy = Mock(side_effect=exception)
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)

    with pytest.raises(exception_type) as caught:
        adapter.evaluate_tabulated_hover_bemt(request)

    assert caught.value is exception
    core_spy.assert_called_once_with(**core_request)
    assert request == original_request


def test_core_argument_mutation_preserves_caller_and_hashed_snapshot(monkeypatch):
    core_request = inputs()
    request = {"evaluation": adapter.EVALUATION, **core_request}
    original_request = deepcopy(request)
    computed = []
    received = []

    def compute_then_mutate(**arguments):
        received.append(deepcopy(arguments))
        actual = solve_tabulated_hover(**arguments)
        computed.append(actual)
        assert arguments["stations"] is not request["stations"]
        assert arguments["stations"][0] is not request["stations"][0]
        arguments["stations"][0]["chord_m"] = 99.0
        arguments["stations"].clear()
        arguments["geometry_source"] = "mutated core argument"
        return actual

    core_spy = Mock(side_effect=compute_then_mutate)
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)

    response = adapter.evaluate_tabulated_hover_bemt(request)

    core_spy.assert_called_once()
    assert received == [core_request]
    assert request == original_request
    assert response["status"] == "COMPUTED_EXPERIMENTAL"
    assert response["diagnostics_complete"] is True
    assert response["outputs"]["stations"] == original_request["stations"]
    assert response["outputs"]["geometry_source"] == original_request["geometry_source"]
    assert response["outputs"]["thrust_n"] == computed[0].thrust_n
    assert_response_hashes(response, original_request)


class CustomDict(dict):
    def __deepcopy__(self, memo):
        raise AssertionError("private-custom-dict-copy-hook")


class CustomList(list):
    def __deepcopy__(self, memo):
        raise AssertionError("private-custom-list-copy-hook")


def assert_empty_refusal(response, status):
    assert response["status"] == status
    assert response["outputs"] == response["output_units"] == {}
    assert response["diagnostics_complete"] is False
    assert response["core_model"] is response["core_version"] is response["core_status"] is None
    assert response["physical_validation"] == "NOT_ESTABLISHED"
    assert response["evidence_level"] == "unverified"
    assert response["evaluation_sha256"] is None
    assert response["reasons"]


@pytest.mark.parametrize("change", [
    pytest.param(lambda request: {key: value for key, value in request.items() if key != "density_kg_m3"},
                 id="missing-density"),
    pytest.param(lambda request: {key: value for key, value in request.items() if key != "stations"},
                 id="missing-geometry"),
    pytest.param(lambda request: {**request, "extra": "not-allowed"}, id="extra-root-field"),
    pytest.param(lambda request: list(request.values()), id="wrong-root-list"),
    pytest.param(lambda request: None, id="wrong-root-null"),
    pytest.param(CustomDict, id="custom-root-dict-before-copy"),
    pytest.param(lambda request: {**request, "stations": CustomList(request["stations"])},
                 id="custom-station-list-before-copy"),
    pytest.param(lambda request: {**request, "stations": [CustomDict(request["stations"][0]),
                                                        *request["stations"][1:]]},
                 id="custom-nested-dict-before-copy"),
    pytest.param(lambda request: {**request, 7: "non-string-key"}, id="non-string-root-key"),
    pytest.param(lambda request: {**request, "density_kg_m3": float("nan")}, id="nan"),
    pytest.param(lambda request: {**request, "angular_speed_rad_s": float("inf")}, id="infinity"),
    pytest.param(lambda request: {**request, "angular_speed_rad_s": -float("inf")}, id="negative-infinity"),
    pytest.param(lambda request: {**request, "uncertainty_status": "\ud800"}, id="surrogate"),
])
def test_strict_invalid_request_has_no_core_call_digest_or_exception_leak(monkeypatch, change):
    request = change({"evaluation": adapter.EVALUATION, **inputs(
        geometry_source="private-invalid-request-detail",
    )})
    core_spy = Mock(side_effect=AssertionError("private-unexpected-core-call"))
    hash_spy = Mock(side_effect=AssertionError("private-unexpected-hash-call"))
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)
    monkeypatch.setattr(adapter, "sha256_record", hash_spy)

    response = adapter.evaluate_tabulated_hover_bemt(request)

    assert_empty_refusal(response, "MODEL_INAPPLICABLE")
    assert response["request_sha256"] is None
    core_spy.assert_not_called()
    hash_spy.assert_not_called()
    assert "private-" not in repr(response)
    assert "UnicodeEncodeError" not in repr(response)
    assert "AssertionError" not in repr(response)


@pytest.mark.parametrize(("evaluation", "status"), [
    ("another-valid-evaluation-string", "SOLVER_UNSUPPORTED"),
    (123, "MODEL_INAPPLICABLE"),
    (True, "MODEL_INAPPLICABLE"),
    (None, "MODEL_INAPPLICABLE"),
])
def test_wrong_identifier_and_wrong_evaluation_type_are_distinct_without_execution(
    monkeypatch, evaluation, status,
):
    request = {"evaluation": evaluation, **inputs()}
    core_spy = Mock()
    hash_spy = Mock()
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)
    monkeypatch.setattr(adapter, "sha256_record", hash_spy)

    response = adapter.evaluate_tabulated_hover_bemt(request)

    assert_empty_refusal(response, status)
    assert response["request_sha256"] is None
    core_spy.assert_not_called()
    hash_spy.assert_not_called()


def test_private_json_walk_depth_ten_includes_root_at_one():
    limits = adapter.tabulated_hover_bemt_catalog()["limits"]["input_json"]
    assert limits["root_depth"] == 1 and limits["max_depth"] == 10
    allowed = 0
    for _ in range(9):
        allowed = [allowed]
    adapter._json_walk(allowed, limits)
    with pytest.raises(ValueError):
        adapter._json_walk([allowed], limits)


def test_private_json_walk_exact_node_budget_includes_keys():
    limits = adapter.tabulated_hover_bemt_catalog()["limits"]["input_json"]
    allowed = [{"key": [0] * 253} for _ in range(31)] + [[0] * 254]
    assert assert_plain_json_and_count_nodes(allowed) == 8192
    adapter._json_walk(allowed, limits)
    allowed[-1].append(0)
    assert assert_plain_json_and_count_nodes(allowed) == 8193
    with pytest.raises(ValueError):
        adapter._json_walk(allowed, limits)


@pytest.mark.parametrize("container", [list, dict])
def test_private_json_walk_container_item_boundary(container):
    limits = adapter.tabulated_hover_bemt_catalog()["limits"]["input_json"]
    allowed = list(range(256)) if container is list else {str(index): 0 for index in range(256)}
    adapter._json_walk(allowed, limits)
    if container is list:
        allowed.append(0)
    else:
        allowed["256"] = 0
    assert len(allowed) == 257
    with pytest.raises(ValueError):
        adapter._json_walk(allowed, limits)


def test_private_json_walk_string_boundary_counts_characters_and_requires_utf8():
    limits = adapter.tabulated_hover_bemt_catalog()["limits"]["input_json"]
    allowed = "🛠" * 2000
    assert len(allowed) == 2000 and len(allowed.encode("utf-8")) > 2000
    adapter._json_walk(allowed, limits)
    with pytest.raises(ValueError):
        adapter._json_walk(allowed + "x", limits)
    assert issubclass(UnicodeEncodeError, ValueError)
    with pytest.raises(UnicodeEncodeError):
        adapter._json_walk("\ud800", limits)


def test_private_json_walk_integer_bit_boundary_and_builtin_json_scalars():
    limits = adapter.tabulated_hover_bemt_catalog()["limits"]["input_json"]
    maximum = (1 << 1023) - 1
    assert maximum.bit_length() == 1023
    adapter._json_walk([maximum, -maximum, True, False, None, 0, 0.0], limits)
    for rejected in (1 << 1023, -(1 << 1023)):
        assert rejected.bit_length() == 1024
        with pytest.raises(ValueError):
            adapter._json_walk(rejected, limits)


def test_outer_request_node_overflow_is_refused_before_core_or_hash(monkeypatch):
    request = {"evaluation": adapter.EVALUATION, **inputs(
        stations=[{"key": [0] * 253} for _ in range(31)],
    )}
    remaining = 8193 - assert_plain_json_and_count_nodes(request) - 1
    assert 0 <= remaining <= 256
    request["stations"].append([0] * remaining)
    assert assert_plain_json_and_count_nodes(request) == 8193
    core_spy = Mock()
    hash_spy = Mock()
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)
    monkeypatch.setattr(adapter, "sha256_record", hash_spy)

    response = adapter.evaluate_tabulated_hover_bemt(request)

    assert_empty_refusal(response, "MODEL_INAPPLICABLE")
    assert response["request_sha256"] is None
    core_spy.assert_not_called()
    hash_spy.assert_not_called()


@pytest.mark.parametrize("overrides", [
    pytest.param({"density_kg_m3": -1.0}, id="negative-density"),
    pytest.param({"density_kg_m3": True}, id="bool-physical-scalar"),
    pytest.param({"blade_count": True}, id="bool-integer-count"),
    pytest.param({"annuli": 2049}, id="annuli-work-limit"),
    pytest.param({"root_cutout_m": 0.0}, id="invalid-cutout"),
    pytest.param({"angular_speed_rad_s": 1e200}, id="finite-input-derived-overflow"),
    pytest.param({"angular_speed_rad_s": 5e-324}, id="finite-input-subnormal"),
    pytest.param({"stations": [
        {"radius_m": 0.5, "chord_m": 0.05, "blade_angle_rad": 0.08},
        {"radius_m": 1.0, "chord_m": 0.05, "blade_angle_rad": 0.08},
    ]}, id="invalid-station-root-coverage"),
    pytest.param({"stations": [
        {"radius_m": 0.0, "blade_angle_rad": 0.08},
        {"radius_m": 1.0, "chord_m": 0.05, "blade_angle_rad": 0.08},
    ]}, id="missing-station-chord-no-default"),
])
def test_actual_core_domain_refusal_retains_only_request_digest(monkeypatch, overrides):
    core_request = inputs(**overrides)
    request = {"evaluation": adapter.EVALUATION, **core_request}
    original_request = deepcopy(request)
    core_spy = Mock(side_effect=solve_tabulated_hover)
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)

    response = adapter.evaluate_tabulated_hover_bemt(request)

    core_spy.assert_called_once_with(**core_request)
    assert_empty_refusal(response, "MODEL_INAPPLICABLE")
    assert response["request_sha256"] == sha256_record(original_request)
    assert response["request_sha256"] is not None
    assert request == original_request


@pytest.mark.parametrize("boundary", ["typed", "values"])
def test_coherent_inflow_forgery_fails_governing_balance_not_summary_binding(monkeypatch, boundary):
    core_request = inputs()
    request = {"evaluation": adapter.EVALUATION, **core_request}
    original_request = deepcopy(request)
    actual = solve_tabulated_hover(**core_request)
    original_result = asdict(actual)
    inflows = tuple(inflow * 1.05 for inflow in actual.inflow_ratio)
    angles, attacks, balances = [], [], []
    momentum_terms, blade_terms, induced_terms, profile_terms = [], [], [], []
    width = ((actual.radius_m - actual.root_cutout_m) / float(actual.annuli)) / actual.radius_m
    operand_scales = []
    for x, theta, sigma, inflow in zip(
        actual.radial_fraction, actual.blade_angle_rad, actual.local_solidity, inflows, strict=True,
    ):
        phi = inflow / x
        alpha = theta - phi
        assert alpha > 0.0
        angles.append(phi)
        attacks.append(alpha)
        x_squared = x * x
        blade_factor = (sigma * core_request["lift_curve_slope_per_rad"]) / 2.0
        theta_term, inflow_term = theta * x_squared, inflow * x
        momentum = (4.0 * (inflow * inflow)) * x
        blade = blade_factor * (theta_term - inflow_term)
        profile_factor = (sigma * core_request["profile_drag_coefficient"]) / 2.0
        profile = profile_factor * (x_squared * x)
        balances.append(blade - momentum)
        operand_scales.append(max(abs(blade_factor * theta_term),
                                  abs(blade_factor * inflow_term), abs(momentum)))
        momentum_terms.append(momentum * width)
        blade_terms.append(blade * width)
        induced_terms.append((momentum * inflow) * width)
        profile_terms.append(profile * width)

    ct, ct_blade = math.fsum(momentum_terms), math.fsum(blade_terms)
    cp_induced, cp_profile = math.fsum(induced_terms), math.fsum(profile_terms)
    cp = math.fsum([cp_induced, cp_profile])
    tip_speed = core_request["angular_speed_rad_s"] * actual.radius_m
    area = math.pi * (actual.radius_m * actual.radius_m)
    thrust_scale = (core_request["density_kg_m3"] * area) * (tip_speed * tip_speed)
    power = (thrust_scale * tip_speed) * cp
    forged = replace(
        actual, inflow_ratio=inflows, approx_inflow_angle_rad=tuple(angles),
        approx_angle_of_attack_rad=tuple(attacks), thrust_coefficient=ct,
        blade_thrust_coefficient=ct_blade, induced_power_coefficient=cp_induced,
        profile_power_coefficient=cp_profile, shaft_power_coefficient=cp,
        thrust_n=thrust_scale * ct, shaft_power_w=power,
        shaft_torque_nm=power / core_request["angular_speed_rad_s"],
        local_balance_coefficient=tuple(balances), thrust_balance_coefficient=ct_blade - ct,
        max_local_balance_coefficient=max(abs(balance) for balance in balances),
    )
    assert forged.stations == actual.stations
    assert forged.inflow_ratio != actual.inflow_ratio
    assert forged.profile_power_coefficient == actual.profile_power_coefficient
    assert all(abs(balance) > (64.0 * sys.float_info.epsilon) * scale
               for balance, scale in zip(balances, operand_scales, strict=True))
    core_spy = Mock(return_value=forged)
    equality_spy = Mock(wraps=adapter._same)
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)
    monkeypatch.setattr(adapter, "_same", equality_spy)

    if boundary == "typed":
        response = adapter.evaluate_tabulated_hover_bemt(request)
        core_spy.assert_called_once_with(**core_request)
        assert_atomic_execution_failure(response, original_request)
    else:
        # Only the actual returned result is copied and mutated for this
        # negative. The direct helper must reject the same coherent forgery.
        values = adapter._export_solution(forged)
        with pytest.raises(ValueError):
            adapter._validate_output_values(values, request)
        core_spy.assert_not_called()
    assert request == original_request
    assert asdict(actual) == original_result
    # The last exact equality succeeds on the first recomputed local residual.
    # Rejection must occur at the following governing balance guard, rather
    # than an earlier malformed type, geometry, angle, or residual binding.
    assert equality_spy.call_args.args == (balances[0], balances[0])
    assert all(call.args[0] == call.args[1] for call in equality_spy.call_args_list)


ARRAY_FIELDS = (
    "radii_m", "chord_m", "blade_angle_rad", "radial_fraction", "local_solidity",
    "inflow_ratio", "approx_inflow_angle_rad", "approx_angle_of_attack_rad",
    "local_balance_coefficient",
)
SCALAR_FIELDS = (
    "radius_m", "root_cutout_m", "thrust_coefficient", "blade_thrust_coefficient",
    "induced_power_coefficient", "profile_power_coefficient", "shaft_power_coefficient",
    "thrust_n", "shaft_power_w", "shaft_torque_nm", "thrust_balance_coefficient",
    "max_local_balance_coefficient",
)


def zero_stations():
    return [
        {"radius_m": 0.0, "chord_m": 0.05, "blade_angle_rad": 0.0},
        {"radius_m": 1.0, "chord_m": 0.05, "blade_angle_rad": 0.0},
    ]


def actual_output_slice(monkeypatch, **overrides):
    """Every valid slice comes from one actual V103 evaluation."""
    request = {"evaluation": adapter.EVALUATION, **inputs(**overrides)}
    core_spy = Mock(wraps=solve_tabulated_hover)
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)
    response = adapter.evaluate_tabulated_hover_bemt(request)
    assert response["status"] == "COMPUTED_EXPERIMENTAL"
    core_spy.assert_called_once()
    return request, response["outputs"], core_spy


@pytest.mark.parametrize("overrides", [
    {}, {"annuli": 1}, {"profile_drag_coefficient": 0.0},
    {"stations": zero_stations()},
    {"stations": zero_stations(), "profile_drag_coefficient": 0.0},
    {"annuli": 2048, "blade_count": 32, "stations": [
        {"radius_m": index / 255, "chord_m": 0.05, "blade_angle_rad": 0.08}
        for index in range(256)
    ]},
])
def test_direct_output_values_accept_actual_outputs_without_rerun_or_mutation(monkeypatch, overrides):
    request, values, core_spy = actual_output_slice(monkeypatch, **overrides)
    before_request, before_values = deepcopy(request), deepcopy(values)
    export_spy = Mock(side_effect=AssertionError("direct helper must not export a dataclass"))
    monkeypatch.setattr(adapter, "_export_solution", export_spy)
    assert adapter._validate_output_values(values, request) is None
    assert request == before_request and values == before_values
    core_spy.assert_called_once()
    export_spy.assert_not_called()


@pytest.mark.parametrize("field", [*ARRAY_FIELDS, *SCALAR_FIELDS])
@pytest.mark.parametrize("bad", [True, 1, float("nan"), float("inf"), 5e-324, 1e308])
def test_direct_output_numeric_types_normality_and_exact_bindings(monkeypatch, field, bad):
    request, values, core_spy = actual_output_slice(monkeypatch)
    if field in ARRAY_FIELDS:
        values[field][0] = bad
    else:
        values[field] = bad
    before_request = deepcopy(request)
    # NaN requires a representation comparison when checking nonmutation.
    before_values = repr(values)
    with pytest.raises(ValueError):
        adapter._validate_output_values(values, request)
    assert request == before_request and repr(values) == before_values
    core_spy.assert_called_once()


@pytest.mark.parametrize("change", [
    pytest.param(lambda v: {k: x for k, x in v.items() if k != "thrust_n"}, id="missing-key"),
    pytest.param(lambda v: {**v, "extra": 0.0}, id="extra-key"),
    pytest.param(lambda v: {**v, "model": "tabulated_geometry_hover_experimental"}, id="marker-in-slice"),
    pytest.param(CustomDict, id="foreign-root"),
    pytest.param(lambda v: list(v.values()), id="list-root"),
    pytest.param(lambda v: {**v, "radii_m": tuple(v["radii_m"])}, id="tuple-array"),
    pytest.param(lambda v: {**v, "radii_m": CustomList(v["radii_m"])}, id="foreign-array"),
    pytest.param(lambda v: {**v, "radii_m": v["radii_m"][:-1]}, id="array-length"),
    pytest.param(lambda v: {**v, "stations": tuple(v["stations"])}, id="tuple-stations"),
    pytest.param(lambda v: {**v, "stations": [CustomDict(v["stations"][0]), *v["stations"][1:]]},
                 id="foreign-station"),
    pytest.param(lambda v: {**v, "stations": [object(), *v["stations"][1:]]}, id="station-object"),
    pytest.param(lambda v: {**v, "stations": [{**v["stations"][0], "extra": 0.0}, *v["stations"][1:]]},
                 id="station-extra-key"),
    pytest.param(lambda v: {**v, "stations": [{"radius_m": 0.0}, *v["stations"][1:]]},
                 id="station-missing-keys"),
    pytest.param(lambda v: {**v, "annuli": True}, id="bool-count"),
    pytest.param(lambda v: {**v, "annuli": 24.0}, id="float-count"),
    pytest.param(lambda v: {**v, "annuli": 0}, id="zero-count"),
    pytest.param(lambda v: {**v, "annuli": 2049}, id="oversized-count"),
    pytest.param(lambda v: {**v, "geometry_source": " "}, id="blank-declaration"),
    pytest.param(lambda v: {**v, "uncertainty_status": True}, id="bool-declaration"),
    pytest.param(lambda v: {**v, "geometry_kind": "verified"}, id="unknown-kind"),
    pytest.param(lambda v: {**v, "geometry_source": "x" * 2001}, id="oversized-text"),
    pytest.param(lambda v: {**v, "geometry_source": "\ud800"}, id="invalid-utf8"),
    pytest.param(lambda v: {**v, "radii_m": [0.0] * 2049}, id="oversized-array"),
    pytest.param(lambda v: {**v, "stations": v["stations"] * 86}, id="oversized-stations"),
    pytest.param(lambda v: {**v, "radii_m": v["inflow_ratio"]}, id="incorrect-array-alias"),
    pytest.param(lambda v: {**v, "stations": [v["stations"][0]] * 3}, id="incorrect-station-alias"),
    pytest.param(lambda v: {**v, "annuli": 1 << 1023}, id="oversized-integer"),
])
def test_direct_output_shape_declarations_and_limits(monkeypatch, change):
    request, values, core_spy = actual_output_slice(monkeypatch)
    bad = change(values)
    before_request, before_values = deepcopy(request), repr(bad)
    with pytest.raises(ValueError):
        adapter._validate_output_values(bad, request)
    assert request == before_request and repr(bad) == before_values
    core_spy.assert_called_once()


@pytest.mark.parametrize("field", ["radius_m", "chord_m", "blade_angle_rad"])
@pytest.mark.parametrize("bad", [True, 0, 5e-324, float("nan"), -1.0])
def test_direct_station_numbers_are_builtin_normal_floats(monkeypatch, field, bad):
    request, values, core_spy = actual_output_slice(monkeypatch)
    values["stations"][0][field] = bad
    with pytest.raises(ValueError):
        adapter._validate_output_values(values, request)
    core_spy.assert_called_once()


@pytest.mark.parametrize("cycle", [False, True])
def test_direct_output_walk_rejects_cycles_and_counts_every_alias(monkeypatch, cycle):
    request, values, core_spy = actual_output_slice(monkeypatch)
    values["radii_m"] = [values] if cycle else [[0.0] * 2048] * 16
    governing_spy = Mock(wraps=adapter._validate_governing)
    monkeypatch.setattr(adapter, "_validate_governing", governing_spy)
    with pytest.raises(ValueError):
        adapter._validate_output_values(values, request)
    governing_spy.assert_not_called()
    core_spy.assert_called_once()


def test_direct_valid_zero_array_aliases_keep_json_value_semantics(monkeypatch):
    request, values, core_spy = actual_output_slice(monkeypatch, stations=zero_stations())
    values["approx_inflow_angle_rad"] = values["inflow_ratio"]
    adapter._validate_output_values(values, request)
    assert values["approx_inflow_angle_rad"] is values["inflow_ratio"]
    core_spy.assert_called_once()


@pytest.mark.parametrize(("field", "bad"), [
    ("density_kg_m3", 1.3), ("density_kg_m3", True), ("density_kg_m3", 5e-324),
    ("density_kg_m3", float("nan")), ("density_kg_m3", 1e308),
    ("angular_speed_rad_s", 101.0), ("angular_speed_rad_s", False),
    ("angular_speed_rad_s", 5e-324), ("angular_speed_rad_s", 1e308),
    ("lift_curve_slope_per_rad", 5.8), ("profile_drag_coefficient", 0.02),
    ("blade_count", 3), ("blade_count", True), ("blade_count", 33),
    ("annuli", 25), ("annuli", True), ("annuli", 24.0),
    ("radius_m", 1.1), ("root_cutout_m", 0.2),
    ("geometry_source", "another source"), ("geometry_kind", "measured"),
    ("uncertainty_status", "known"),
])
def test_direct_output_request_binding(monkeypatch, field, bad):
    request, values, core_spy = actual_output_slice(monkeypatch)
    request[field] = bad
    before_values, before_request = deepcopy(values), repr(request)
    with pytest.raises(ValueError):
        adapter._validate_output_values(values, request)
    assert values == before_values and repr(request) == before_request
    core_spy.assert_called_once()


@pytest.mark.parametrize("change", [
    lambda r: r["stations"][0].update(chord_m=0.041),
    lambda r: r["stations"][0].update(radius_m=True),
    lambda r: r["stations"][0].update(blade_angle_rad=0.11),
    lambda r: r["stations"].pop(),
    lambda r: r.update(stations=tuple(r["stations"])),
    lambda r: r["stations"][0].update(extra=1.0),
    lambda r: r.pop("density_kg_m3"),
])
def test_direct_output_geometry_binding_and_required_used_fields(monkeypatch, change):
    request, values, core_spy = actual_output_slice(monkeypatch)
    change(request)
    with pytest.raises(ValueError):
        adapter._validate_output_values(values, request)
    core_spy.assert_called_once()


def test_direct_output_slice_does_not_admit_whole_request_or_envelope(monkeypatch):
    request, values, core_spy = actual_output_slice(monkeypatch)
    del request["evaluation"]
    request["unrelated_future_field"] = object()
    adapter._validate_output_values(values, request)
    core_spy.assert_called_once()


@pytest.mark.parametrize("change", [
    lambda s: replace(s, stations=list(s.stations)),
    lambda s: replace(s, stations=(asdict(s.stations[0]), *s.stations[1:])),
    lambda s: replace(s, radii_m=list(s.radii_m)),
    lambda s: replace(s, thrust_n=True),
    lambda s: replace(s, stations=(replace(s.stations[0], chord_m=True), *s.stations[1:])),
    lambda s: replace(s, model="forged"),
    lambda s: asdict(s),
])
def test_typed_guards_reject_before_actual_export(monkeypatch, change):
    actual = solve_tabulated_hover(**inputs())
    forged = change(actual)
    core_spy = Mock(return_value=forged)
    export_spy = Mock(wraps=adapter._export_solution)
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)
    monkeypatch.setattr(adapter, "_export_solution", export_spy)
    request = {"evaluation": adapter.EVALUATION, **inputs()}
    assert_atomic_execution_failure(adapter.evaluate_tabulated_hover_bemt(request), request)
    export_spy.assert_not_called()
    core_spy.assert_called_once()


@pytest.mark.parametrize("station", [False, True])
@pytest.mark.parametrize("corruption", ["extra-vars", "missing-vars", "fields", "frozen"])
def test_typed_exact_fields_and_frozen_declarations_precede_export(monkeypatch, station, corruption):
    actual = solve_tabulated_hover(**inputs())
    target = actual.stations[0] if station else actual
    if corruption == "extra-vars":
        vars(target)["extra"] = 0.0
    elif corruption == "missing-vars":
        del vars(target)["radius_m"]
    elif corruption == "fields":
        monkeypatch.setattr(type(target), "__dataclass_fields__", {})
    else:
        monkeypatch.setattr(type(target).__dataclass_params__, "frozen", False)
    export_spy = Mock(wraps=adapter._export_solution)
    monkeypatch.setattr(adapter, "_export_solution", export_spy)
    with pytest.raises(ValueError):
        adapter._validate_solution(actual, inputs())
    export_spy.assert_not_called()
