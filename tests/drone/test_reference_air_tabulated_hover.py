"""Actual evaluator smoke and contract checks for the fixed V106 workflow."""

from copy import deepcopy
from dataclasses import asdict, replace
from unittest.mock import Mock

import pytest

from physimesh.drone import reference_air_tabulated_hover as workflow
from physimesh.drone import tabulated_hover_bemt_request as child
from physimesh.drone.provenance import sha256_record
from tests.drone.test_tabulated_hover_bemt import inputs


def request(altitude=0.0, kind="geometric", **overrides):
    rotor = {"evaluation": child.EVALUATION, **inputs(**overrides)}
    del rotor["density_kg_m3"]
    return {"evaluation": workflow.EVALUATION,
            "air": {"altitude_m": altitude, "altitude_kind": kind}, "rotor_template": rotor}


@pytest.mark.parametrize("altitude,kind", [(0.0, "geometric"), (10000.0, "geometric"),
                                         (20000.0, "geometric"), (11000.0, "geopotential"),
                                         (20000.0, "geopotential"), (30000.0, "geopotential")])
def test_actual_smoke_exact_results_and_calls(monkeypatch, altitude, kind):
    supplied = request(altitude, kind)
    before = deepcopy(supplied)
    air = workflow.reference_air_properties(**supplied["air"])
    injected = {**supplied["rotor_template"], "density_kg_m3": air.state.density_kg_m3}
    expected = child.evaluate_tabulated_hover_bemt(injected)
    air_spy = Mock(wraps=workflow.reference_air_properties)
    child_spy = Mock(wraps=workflow.evaluate_tabulated_hover_bemt)
    core_spy = Mock(wraps=child.solve_tabulated_hover)
    monkeypatch.setattr(workflow, "reference_air_properties", air_spy)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    monkeypatch.setattr(child, "solve_tabulated_hover", core_spy)
    result = workflow.evaluate_reference_air_tabulated_hover(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"] == {"air": asdict(air), "rotor": expected}
    assert result["request_sha256"] == sha256_record(before)
    assert result["evaluation_sha256"] == sha256_record({
        k: v for k, v in result.items() if k != "evaluation_sha256"
    })
    assert supplied == before
    air_spy.assert_called_once_with(**supplied["air"])
    child_spy.assert_called_once_with(injected)
    core_spy.assert_called_once()


def assert_atomic(result, status, supplied=None):
    assert result["status"] == status
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == result["transfers"] == []
    assert result["diagnostics_complete"] is False
    assert result["feasibility"] is result["aircraft_status"] is None
    for name in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert result[name] == "NOT_ESTABLISHED"
    assert result["evidence_level"] == "unverified"
    assert result["request_sha256"] == (sha256_record(supplied) if supplied is not None else None)
    if status == "EXECUTION_FAILED" and supplied is not None:
        assert result["evaluation_sha256"] == sha256_record({
            k: v for k, v in result.items() if k != "evaluation_sha256"
        })
    else:
        assert result["evaluation_sha256"] is None


def test_actual_stage_digests_full_units_and_scalar_transfer(monkeypatch):
    supplied = request(10000.0)
    actual_air = workflow.reference_air_properties(**supplied["air"])
    injected = {**supplied["rotor_template"], "density_kg_m3": actual_air.state.density_kg_m3}
    actual_child = child.evaluate_tabulated_hover_bemt(injected)
    air_spy, child_spy = Mock(return_value=actual_air), Mock(return_value=actual_child)
    monkeypatch.setattr(workflow, "reference_air_properties", air_spy)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    result = workflow.evaluate_reference_air_tabulated_hover(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    raw = asdict(actual_air)
    assert result["outputs"]["air"] == raw
    assert result["outputs"]["rotor"] is actual_child
    assert result["outputs"]["rotor"]["evaluation_sha256"] == actual_child["evaluation_sha256"]
    assert result["stages"] == [
        {"stage": "air", "inputs": supplied["air"], "inputs_sha256": sha256_record(supplied["air"]),
         "result_sha256": sha256_record(raw)},
        {"stage": "rotor", "inputs": injected, "inputs_sha256": sha256_record(injected),
         "result_sha256": sha256_record(actual_child)},
    ]
    assert result["transfers"] == [{
        "from_stage": "air", "from_field": "state.density_kg_m3", "to_stage": "rotor",
        "to_field": "density_kg_m3", "value": actual_air.state.density_kg_m3, "unit": "kg/m^3",
        "producer_result_sha256": sha256_record(raw), "consumer_request_sha256": sha256_record(injected),
    }]
    assert result["output_units"]["air"] == {
        "state": {"input_altitude_m": "m", "altitude_kind": "label", "geopotential_altitude_m": "m",
                  "pressure_pa": "Pa", "temperature_k": "K", "density_kg_m3": "kg/m^3",
                  "model_id": "label", "evidence_status": "label"},
        "geometric_altitude_m": "m", "dynamic_viscosity_pa_s": "Pa*s", "speed_of_sound_m_s": "m/s",
        "gravity_m_s2": "m/s^2", "model_id": "label", "viscosity_model": "text", "sound_model": "text",
        "gravity_model": "text", "physical_qualification": "label", "numerical_qualification": "label",
    }
    assert result["output_units"]["air"].keys() == raw.keys()
    assert result["output_units"]["air"]["state"].keys() == raw["state"].keys()
    assert result["output_units"]["rotor"] == actual_child["output_units"]
    assert result["output_units"]["rotor"].keys() == actual_child["outputs"].keys()
    air_spy.assert_called_once()
    child_spy.assert_called_once_with(injected)


def test_actual_maximum_shape_fits_independent_output_budget(monkeypatch):
    stations = [{"radius_m": i / 255, "chord_m": 0.05, "blade_angle_rad": 0.08} for i in range(256)]
    supplied = request(20000, annuli=2048, blade_count=32, stations=stations)
    core_spy = Mock(wraps=child.solve_tabulated_hover)
    monkeypatch.setattr(child, "solve_tabulated_hover", core_spy)
    result = workflow.evaluate_reference_air_tabulated_hover(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    core_spy.assert_called_once()
    assert len(result["outputs"]["rotor"]["outputs"]["radii_m"]) == 2048
    assert len(result["stages"][1]["inputs"]["stations"]) == 256
    limits = result["limits"]["output_json"]
    assert limits["max_nodes_including_keys"] == 65536 and limits["max_depth"] == 16
    workflow._JSON(result, limits)

    def nodes(value):
        if type(value) is dict:
            return 1 + sum(1 + nodes(v) for v in value.values())
        if type(value) is list:
            return 1 + sum(nodes(v) for v in value)
        return 1

    assert 18000 < nodes(result) < 65536
    assert all(set(stage) == {"stage", "inputs", "inputs_sha256", "result_sha256"}
               for stage in result["stages"])


def test_catalog_is_fresh_including_deep_metadata():
    baseline = workflow.reference_air_tabulated_hover_catalog()
    changed = workflow.reference_air_tabulated_hover_catalog()
    changed["limits"]["input_json"]["max_depth"] = 0
    changed["output_field_units"]["air"]["state"]["density_kg_m3"] = "bad"
    changed["input_units"]["rotor_template"]["stations"]["chord_m"] = "bad"
    changed["bindings"]["air"] = "bad"
    changed["limitations"].clear()
    changed["required_fields"].clear()
    assert workflow.reference_air_tabulated_hover_catalog() == baseline
    assert child.tabulated_hover_bemt_catalog()["input_units"]["stations"]["chord_m"] == "m"
    assert workflow.evaluate_reference_air_tabulated_hover(request())["status"] == "COMPUTED_EXPERIMENTAL"


@pytest.mark.parametrize("change", [
    lambda r: r.update(extra=True),
    lambda r: r["rotor_template"].update(density_kg_m3=1.225),
    lambda r: r["air"].update(altitude_m=True),
    lambda r: r["air"].update(altitude_kind="pressure"),
    lambda r: r["rotor_template"].update(annuli=2049),
    lambda r: r["rotor_template"].update(blade_count=33),
    lambda r: r["rotor_template"].update(stations=[]),
    lambda r: r["rotor_template"].update(geometry_source=" "),
    lambda r: r["rotor_template"].update(geometry_kind="verified"),
    lambda r: r["rotor_template"].update(uncertainty_status="\ud800"),
])
def test_preflight_rejects_before_any_evaluator(monkeypatch, change):
    supplied = request()
    change(supplied)
    air_spy, child_spy = Mock(), Mock()
    monkeypatch.setattr(workflow, "reference_air_properties", air_spy)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    assert_atomic(workflow.evaluate_reference_air_tabulated_hover(supplied), "MODEL_INAPPLICABLE")
    air_spy.assert_not_called()
    child_spy.assert_not_called()


@pytest.mark.parametrize("change", [
    lambda r: r["rotor_template"].update(radius_m=-1.0),
    lambda r: r["rotor_template"]["stations"][0].update(chord_m=-0.01),
    lambda r: r["rotor_template"].update(root_cutout_m=0.0),
])
def test_physical_domain_is_actual_child_owned(monkeypatch, change):
    supplied = request()
    change(supplied)
    air_spy = Mock(wraps=workflow.reference_air_properties)
    child_spy = Mock(wraps=workflow.evaluate_tabulated_hover_bemt)
    core_spy = Mock(wraps=child.solve_tabulated_hover)
    monkeypatch.setattr(workflow, "reference_air_properties", air_spy)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    monkeypatch.setattr(child, "solve_tabulated_hover", core_spy)
    assert_atomic(workflow.evaluate_reference_air_tabulated_hover(supplied), "MODEL_INAPPLICABLE", supplied)
    air_spy.assert_called_once()
    child_spy.assert_called_once()
    core_spy.assert_called_once()


@pytest.mark.parametrize("change", [
    pytest.param(lambda a: replace(a, state=replace(
        a.state, pressure_pa=a.state.pressure_pa * 1.01, density_kg_m3=a.state.density_kg_m3 * 1.01,
    )), id="coherent-pressure-density-forgery"),
    pytest.param(lambda a: replace(a, state=replace(a.state, input_altitude_m=9000.0)), id="input-altitude"),
    pytest.param(lambda a: replace(a, state=replace(a.state, altitude_kind="geopotential")), id="convention"),
    pytest.param(lambda a: replace(a, state=replace(a.state, geopotential_altitude_m=10000.0)), id="converted-h"),
    pytest.param(lambda a: replace(a, state=replace(a.state, model_id="forged")), id="state-model"),
    pytest.param(lambda a: replace(a, state=replace(a.state, evidence_status="VERIFIED")), id="state-evidence"),
    pytest.param(lambda a: replace(a, state=replace(a.state, temperature_k=a.state.temperature_k + 1)),
                 id="temperature"),
    pytest.param(lambda a: replace(a, state=replace(a.state, density_kg_m3=True)), id="bool-density"),
    pytest.param(lambda a: replace(a, state=replace(a.state, pressure_pa=float("nan"))), id="nan-pressure"),
    pytest.param(lambda a: replace(a, dynamic_viscosity_pa_s=a.dynamic_viscosity_pa_s * 1.01), id="mu"),
    pytest.param(lambda a: replace(a, dynamic_viscosity_pa_s=(
        1.716e-5 * (273.15 + 110.4) / (a.state.temperature_k + 110.4)
        * (a.state.temperature_k / 273.15) ** 1.5
    )), id="legacy-sutherland-110-4"),
    pytest.param(lambda a: replace(a, speed_of_sound_m_s=a.speed_of_sound_m_s * 1.01), id="sound"),
    pytest.param(lambda a: replace(a, gravity_m_s2=a.gravity_m_s2 * 1.01), id="gravity"),
    pytest.param(lambda a: replace(a, geometric_altitude_m=a.geometric_altitude_m + 1.0), id="geometric-z"),
    pytest.param(lambda a: replace(a, dynamic_viscosity_pa_s=True), id="bool-mu"),
    pytest.param(lambda a: replace(a, speed_of_sound_m_s=float("inf")), id="infinite-sound"),
    pytest.param(lambda a: replace(a, gravity_m_s2=0.0), id="zero-gravity"),
    pytest.param(lambda a: replace(a, model_id="forged"), id="air-model"),
    pytest.param(lambda a: replace(a, viscosity_model="legacy"), id="viscosity-marker"),
    pytest.param(lambda a: replace(a, sound_model="forged"), id="sound-marker"),
    pytest.param(lambda a: replace(a, gravity_model="forged"), id="gravity-marker"),
    pytest.param(lambda a: replace(a, physical_qualification="VERIFIED"), id="physical-qualification"),
    pytest.param(lambda a: replace(a, numerical_qualification="VERIFIED"), id="numerical-qualification"),
    pytest.param(lambda a: replace(a, state=asdict(a.state)), id="dict-state"),
    pytest.param(asdict, id="dict-air"),
])
def test_actual_air_negative_fixtures_fail_before_export_or_child(monkeypatch, change):
    supplied = request(10000.0)
    actual = workflow.reference_air_properties(**supplied["air"])
    baseline = asdict(actual)
    forged = change(actual)
    air_spy, child_spy = Mock(return_value=forged), Mock()
    export_spy = Mock(wraps=workflow.asdict)
    monkeypatch.setattr(workflow, "reference_air_properties", air_spy)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    monkeypatch.setattr(workflow, "asdict", export_spy)
    assert_atomic(workflow.evaluate_reference_air_tabulated_hover(supplied), "EXECUTION_FAILED", supplied)
    air_spy.assert_called_once_with(**supplied["air"])
    child_spy.assert_not_called()
    export_spy.assert_not_called()
    assert asdict(actual) == baseline


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("corruption", ["extra-vars", "missing-vars", "fields", "frozen"])
def test_actual_air_typed_shape_checks_precede_asdict(monkeypatch, nested, corruption):
    supplied = request()
    actual = workflow.reference_air_properties(**supplied["air"])
    target = actual.state if nested else actual
    if corruption == "extra-vars":
        vars(target)["extra"] = 1.0
    elif corruption == "missing-vars":
        del vars(target)["pressure_pa" if nested else "geometric_altitude_m"]
    elif corruption == "fields":
        monkeypatch.setattr(type(target), "__dataclass_fields__", {})
    else:
        monkeypatch.setattr(type(target).__dataclass_params__, "frozen", False)
    air_spy, child_spy = Mock(return_value=actual), Mock()
    export_spy = Mock(wraps=workflow.asdict)
    monkeypatch.setattr(workflow, "reference_air_properties", air_spy)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    monkeypatch.setattr(workflow, "asdict", export_spy)
    assert_atomic(workflow.evaluate_reference_air_tabulated_hover(supplied), "EXECUTION_FAILED", supplied)
    air_spy.assert_called_once()
    child_spy.assert_not_called()
    export_spy.assert_not_called()


@pytest.mark.parametrize("error_type", [ValueError, TypeError, ArithmeticError, RuntimeError])
def test_air_ordinary_exceptions_are_atomic_and_sanitized(monkeypatch, error_type):
    supplied = request()
    air_spy, child_spy = Mock(side_effect=error_type("private-air-error")), Mock()
    monkeypatch.setattr(workflow, "reference_air_properties", air_spy)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    result = workflow.evaluate_reference_air_tabulated_hover(supplied)
    assert_atomic(result, "EXECUTION_FAILED", supplied)
    assert "private-air-error" not in repr(result)
    air_spy.assert_called_once()
    child_spy.assert_not_called()


@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit, GeneratorExit])
def test_air_base_exceptions_propagate(monkeypatch, error_type):
    supplied = request()
    air_spy, child_spy = Mock(side_effect=error_type("private-base-error")), Mock()
    monkeypatch.setattr(workflow, "reference_air_properties", air_spy)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    with pytest.raises(error_type):
        workflow.evaluate_reference_air_tabulated_hover(supplied)
    air_spy.assert_called_once()
    child_spy.assert_not_called()


def actual_child_baseline(supplied):
    air = workflow.reference_air_properties(**supplied["air"])
    injected = {**deepcopy(supplied["rotor_template"]), "density_kg_m3": air.state.density_kg_m3}
    actual = child.evaluate_tabulated_hover_bemt(injected)
    return injected, actual


def rehash_child(actual):
    actual["evaluation_sha256"] = sha256_record({k: v for k, v in actual.items() if k != "evaluation_sha256"})


@pytest.mark.parametrize("field,bad", [
    ("evaluation", "other"), ("model_id", "other"), ("schema_version", "other"),
    ("status", "EXECUTION_FAILED"), ("status", "SOLVER_UNSUPPORTED"), ("status", True),
    ("core_model", "other"), ("core_version", "0.2"), ("core_status", "other"),
    ("evidence_level", "verified"), ("physical_validation", "ESTABLISHED"),
    ("numerical_qualification", "ESTABLISHED"), ("runtime_identity", "ESTABLISHED"),
    ("aircraft_status", "SAFE"), ("feasibility", True), ("diagnostics_complete", 1),
    ("diagnostics_complete", False), ("reasons", ["unexpected"]), ("limitations", []),
    ("limits", {}), ("request_sha256", "0" * 64), ("request_sha256", None),
    ("output_units", {}), ("outputs", {}),
])
def test_actual_child_full_envelope_guards_with_recomputed_hash(monkeypatch, field, bad):
    supplied = request(10000.0)
    injected, actual = actual_child_baseline(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL"
    actual[field] = bad
    rehash_child(actual)
    air_spy = Mock(wraps=workflow.reference_air_properties)
    child_spy = Mock(return_value=actual)
    monkeypatch.setattr(workflow, "reference_air_properties", air_spy)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    with pytest.raises(ValueError):
        workflow._validate_child(actual, injected)
    assert_atomic(workflow.evaluate_reference_air_tabulated_hover(supplied), "EXECUTION_FAILED", supplied)
    air_spy.assert_called_once()
    child_spy.assert_called_once_with(injected)


@pytest.mark.parametrize("change", [
    pytest.param(lambda a: a.update(extra=True), id="extra-envelope-field"),
    pytest.param(lambda a: a.pop("model_id"), id="missing-envelope-field"),
    pytest.param(lambda a: a["output_units"].update(thrust_n="kg"), id="wrong-unit"),
    pytest.param(lambda a: a["limits"]["input_json"].update(root_depth=True), id="bool-metadata"),
    pytest.param(lambda a: a["outputs"].update(geometry_source="other"), id="source-binding"),
    pytest.param(lambda a: a["outputs"].update(radius_m=2.0), id="radius-binding"),
    pytest.param(lambda a: a["outputs"]["stations"][0].update(chord_m=0.1), id="chord-binding"),
    pytest.param(lambda a: a["outputs"]["inflow_ratio"].__setitem__(0, 0.0), id="inflow-binding"),
    pytest.param(lambda a: a["outputs"].update(thrust_n=True), id="bool-output"),
    pytest.param(lambda a: a["outputs"].update(thrust_n=1), id="int-output"),
    pytest.param(lambda a: a["outputs"].update(radii_m=tuple(a["outputs"]["radii_m"])), id="tuple-array"),
    pytest.param(lambda a: a["outputs"]["radii_m"].pop(), id="short-array"),
    pytest.param(lambda a: a["outputs"].update(core_model="forged"), id="marker-in-slice"),
])
def test_actual_child_nested_corruptions_survive_hash_but_fail_contract(monkeypatch, change):
    supplied = request()
    injected, actual = actual_child_baseline(supplied)
    change(actual)
    rehash_child(actual)
    before = repr(actual)
    child_spy = Mock(return_value=actual)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    with pytest.raises(ValueError):
        workflow._validate_child(actual, injected)
    assert_atomic(workflow.evaluate_reference_air_tabulated_hover(supplied), "EXECUTION_FAILED", supplied)
    assert repr(actual) == before
    child_spy.assert_called_once_with(injected)


def test_child_density_scaled_loads_rejected_despite_coherent_units_and_digest(monkeypatch):
    supplied = request(20000.0)
    injected, actual = actual_child_baseline(supplied)
    coefficients = {k: v for k, v in actual["outputs"].items() if "coefficient" in k}
    for name in ("thrust_n", "shaft_power_w", "shaft_torque_nm"):
        actual["outputs"][name] *= 1.01
    assert {k: v for k, v in actual["outputs"].items() if "coefficient" in k} == coefficients
    rehash_child(actual)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", Mock(return_value=actual))
    with pytest.raises(ValueError):
        workflow._validate_child(actual, injected)
    assert_atomic(workflow.evaluate_reference_air_tabulated_hover(supplied), "EXECUTION_FAILED", supplied)


@pytest.mark.parametrize("bad", [None, "0" * 64, True])
def test_actual_child_wrong_evaluation_digest_is_rejected(monkeypatch, bad):
    supplied = request()
    _, actual = actual_child_baseline(supplied)
    actual["evaluation_sha256"] = bad
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", Mock(return_value=actual))
    assert_atomic(workflow.evaluate_reference_air_tabulated_hover(supplied), "EXECUTION_FAILED", supplied)


@pytest.mark.parametrize("change", [
    lambda a: a.update(outputs={"partial": 1.0}),
    lambda a: a.update(output_units={"partial": "1"}),
    lambda a: a.update(core_model="tabulated_geometry_hover_experimental"),
    lambda a: a.update(core_status="COMPUTED_EXPERIMENTAL"),
    lambda a: a.update(core_version="0.1"),
    lambda a: a.update(diagnostics_complete=True),
    lambda a: a.update(reasons=[]),
    lambda a: a.update(evaluation_sha256="0" * 64),
    lambda a: a.update(request_sha256=None),
    lambda a: a.update(limits={}),
])
def test_actual_child_refusal_must_be_exact_atomic_contract(monkeypatch, change):
    supplied = request(radius_m=-1.0)
    _, actual = actual_child_baseline(supplied)
    assert actual["status"] == "MODEL_INAPPLICABLE"
    change(actual)
    air_spy = Mock(wraps=workflow.reference_air_properties)
    child_spy = Mock(return_value=actual)
    monkeypatch.setattr(workflow, "reference_air_properties", air_spy)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    assert_atomic(workflow.evaluate_reference_air_tabulated_hover(supplied), "EXECUTION_FAILED", supplied)
    air_spy.assert_called_once()
    child_spy.assert_called_once()


@pytest.mark.parametrize("error_type", [ValueError, TypeError, ArithmeticError, RuntimeError])
def test_child_ordinary_exceptions_are_atomic_and_sanitized(monkeypatch, error_type):
    supplied = request()
    air_spy = Mock(wraps=workflow.reference_air_properties)
    child_spy = Mock(side_effect=error_type("private-child-error"))
    monkeypatch.setattr(workflow, "reference_air_properties", air_spy)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    result = workflow.evaluate_reference_air_tabulated_hover(supplied)
    assert_atomic(result, "EXECUTION_FAILED", supplied)
    assert "private-child-error" not in repr(result)
    air_spy.assert_called_once()
    child_spy.assert_called_once()


@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit, GeneratorExit])
def test_child_base_exceptions_propagate(monkeypatch, error_type):
    supplied = request()
    air_spy = Mock(wraps=workflow.reference_air_properties)
    child_spy = Mock(side_effect=error_type("private-child-base-error"))
    monkeypatch.setattr(workflow, "reference_air_properties", air_spy)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    with pytest.raises(error_type):
        workflow.evaluate_reference_air_tabulated_hover(supplied)
    air_spy.assert_called_once()
    child_spy.assert_called_once()


def test_actual_child_failure_from_actual_core_is_outer_execution_failure(monkeypatch):
    supplied = request()
    air_spy = Mock(wraps=workflow.reference_air_properties)
    child_spy = Mock(wraps=workflow.evaluate_tabulated_hover_bemt)
    core_spy = Mock(side_effect=RuntimeError("private-core-error"))
    monkeypatch.setattr(workflow, "reference_air_properties", air_spy)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    monkeypatch.setattr(child, "solve_tabulated_hover", core_spy)
    result = workflow.evaluate_reference_air_tabulated_hover(supplied)
    assert_atomic(result, "EXECUTION_FAILED", supplied)
    assert "private-core-error" not in repr(result)
    air_spy.assert_called_once()
    child_spy.assert_called_once()
    core_spy.assert_called_once()


@pytest.mark.parametrize("return_changed", [False, True])
def test_child_argument_mutation_isolated_from_bound_snapshot_and_caller(monkeypatch, return_changed):
    supplied = request()
    before = deepcopy(supplied)
    injected, actual = actual_child_baseline(supplied)
    baseline = deepcopy(actual)
    real_adapter = workflow.evaluate_tabulated_hover_bemt

    def mutating_adapter(arguments):
        arguments["stations"][0]["chord_m"] *= 1.2
        arguments["geometry_source"] = "changed inside child"
        arguments["density_kg_m3"] *= 1.01
        return real_adapter(arguments) if return_changed else actual

    child_spy = Mock(side_effect=mutating_adapter)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    result = workflow.evaluate_reference_air_tabulated_hover(supplied)
    assert supplied == before and actual == baseline
    child_spy.assert_called_once()
    if return_changed:
        assert_atomic(result, "EXECUTION_FAILED", supplied)
    else:
        assert result["status"] == "COMPUTED_EXPERIMENTAL"
        assert result["stages"][1]["inputs"] == injected
        assert result["outputs"]["rotor"] is actual


def test_caller_aliases_and_fresh_response_mutations_are_isolated():
    supplied = request(stations=[
        {"radius_m": 0.0, "chord_m": 0.05, "blade_angle_rad": 0.0},
        {"radius_m": 1.0, "chord_m": 0.05, "blade_angle_rad": 0.0},
    ])
    source = "same caller assertion"
    supplied["rotor_template"]["geometry_source"] = source
    supplied["rotor_template"]["uncertainty_status"] = source
    station_alias = supplied["rotor_template"]["stations"][0]
    before = deepcopy(supplied)
    first = workflow.evaluate_reference_air_tabulated_hover(supplied)
    second = workflow.evaluate_reference_air_tabulated_hover(supplied)
    assert first == second and first["status"] == "COMPUTED_EXPERIMENTAL"
    assert supplied == before and supplied["rotor_template"]["stations"][0] is station_alias
    first["stages"][1]["inputs"]["stations"][0]["chord_m"] = 1.0
    first["outputs"]["air"]["state"]["pressure_pa"] = 1.0
    first["outputs"]["rotor"]["outputs"]["stations"][0]["chord_m"] = 1.0
    first["output_units"]["air"]["state"]["pressure_pa"] = "bad"
    first["output_units"]["rotor"]["stations"]["chord_m"] = "bad"
    first["limits"]["output_json"]["max_depth"] = 0
    first["transfers"][0]["value"] = 0.0
    assert workflow.evaluate_reference_air_tabulated_hover(supplied) == second
    assert supplied == before and station_alias["chord_m"] == 0.05
    assert workflow.reference_air_tabulated_hover_catalog()["output_field_units"]["air"]["state"][
        "pressure_pa"
    ] == "Pa"


class ForeignDict(dict):
    def __deepcopy__(self, memo):
        raise AssertionError("foreign copy hook must never execute")


class ForeignFloat(float):
    pass


def nested_list(depth):
    value = 0
    for _ in range(depth - 1):
        value = [value]
    return value


def cycle_request():
    supplied = request()
    supplied["air"]["altitude_m"] = supplied
    return supplied


@pytest.mark.parametrize("make_bad", [
    pytest.param(lambda: ForeignDict(request()), id="foreign-root"),
    pytest.param(lambda: {**request(), "air": object()}, id="foreign-object"),
    pytest.param(lambda: request(ForeignFloat(0.0)), id="float-subclass"),
    pytest.param(cycle_request, id="cycle"),
    pytest.param(lambda: request(float("nan")), id="nan"),
    pytest.param(lambda: request(float("inf")), id="infinity"),
    pytest.param(lambda: request(True), id="bool-altitude"),
    pytest.param(lambda: request(1 << 1023), id="integer-1024-bits"),
    pytest.param(lambda: request(geometry_source="\ud800"), id="invalid-utf8"),
    pytest.param(lambda: request(geometry_source="x" * 2001), id="string-2001"),
    pytest.param(lambda: request(stations=[{}] * 257), id="container-257"),
    pytest.param(lambda: request(radius_m=nested_list(12)), id="depth-over-11"),
    pytest.param(lambda: request(radius_m=[[0] * 63] * 256), id="nodes-over-16384"),
    pytest.param(lambda: request(annuli=True), id="bool-count"),
    pytest.param(lambda: request(blade_count=2.0), id="float-count"),
    pytest.param(lambda: request(stations=[{"radius_m": True, "chord_m": 0.05, "blade_angle_rad": 0.08}] * 2),
                 id="bool-station-number"),
])
def test_strict_request_walk_and_types_reject_with_zero_evaluations(monkeypatch, make_bad):
    supplied = make_bad()
    air_spy, child_spy = Mock(), Mock()
    monkeypatch.setattr(workflow, "reference_air_properties", air_spy)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    assert_atomic(workflow.evaluate_reference_air_tabulated_hover(supplied), "MODEL_INAPPLICABLE")
    air_spy.assert_not_called()
    child_spy.assert_not_called()


@pytest.mark.parametrize("bad", [ForeignDict({}), object(), "\ud800", float("nan"), 1 << 1023,
                                 nested_list(12), [0] * 257, [[0] * 63] * 256, "x" * 2001])
def test_invalid_json_is_rejected_before_any_copy(monkeypatch, bad):
    supplied = request(radius_m=bad)
    copy_spy = Mock(side_effect=AssertionError("copy must follow the bounded input walk"))
    monkeypatch.setattr(workflow, "deepcopy", copy_spy)
    # Metadata construction also uses deepcopy; observe entry without preventing
    # creation of the fresh atomic response after the walk has rejected input.
    real_copy = deepcopy

    def copy_only_response_metadata(value):
        if value is supplied:
            return copy_spy(value)
        return real_copy(value)

    monkeypatch.setattr(workflow, "deepcopy", copy_only_response_metadata)
    assert_atomic(workflow.evaluate_reference_air_tabulated_hover(supplied), "MODEL_INAPPLICABLE")
    copy_spy.assert_not_called()


def test_exact_2000_unicode_characters_are_accepted_as_actual_declarations(monkeypatch):
    text = "\U0001f680" * 2000
    assert len(text) == 2000 and len(text.encode("utf-8")) == 8000
    supplied = request(geometry_source=text, uncertainty_status=text)
    air_spy = Mock(wraps=workflow.reference_air_properties)
    child_spy = Mock(wraps=workflow.evaluate_tabulated_hover_bemt)
    monkeypatch.setattr(workflow, "reference_air_properties", air_spy)
    monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", child_spy)
    result = workflow.evaluate_reference_air_tabulated_hover(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["rotor"]["outputs"]["geometry_source"] == text
    assert result["request_sha256"] == sha256_record(supplied)
    air_spy.assert_called_once()
    child_spy.assert_called_once()


def test_direct_walk_exact_depth_node_boundaries_and_alias_semantics():
    catalog = workflow.reference_air_tabulated_hover_catalog()
    outer = catalog["limits"]["input_json"]
    output = catalog["limits"]["output_json"]
    workflow._JSON(nested_list(11), outer)
    with pytest.raises(ValueError):
        workflow._JSON(nested_list(12), outer)
    workflow._JSON(nested_list(16), output)
    with pytest.raises(ValueError):
        workflow._JSON(nested_list(17), output)
    # 1 root + 256 containers + their 16127 leaves = exactly 16384 nodes.
    at_limit = [[0] * 63] * 255 + [[0] * 62]
    workflow._JSON(at_limit, outer)
    with pytest.raises(ValueError):
        workflow._JSON([[0] * 63] * 256, outer)
    # Same check at the independent 65536-node outer output budget.
    workflow._JSON([[0] * 31] * 2047 + [[0] * 30], output)
    with pytest.raises(ValueError):
        workflow._JSON([[0] * 31] * 2048, output)
    workflow._JSON((1 << 1023) - 1, outer)
    with pytest.raises(ValueError):
        workflow._JSON(1 << 1023, outer)
    # bool is valid JSON; the request's numeric schema separately rejects it.
    workflow._JSON(True, outer)
    cycle = []
    cycle.append(cycle)
    with pytest.raises(ValueError):
        workflow._JSON(cycle, outer)
