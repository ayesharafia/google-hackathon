"""Focused composition checks against the accepted component models."""

from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from physimesh.drone.atmosphere_hover_workflow import evaluate_atmosphere_hover
from physimesh.drone.hover_bemt_request import evaluate_hover_bemt
from physimesh.drone.provenance import sha256_record
from physimesh.drone.standard_atmosphere import standard_atmosphere
from tests.drone.test_hover_bemt_request import valid_request


@pytest.mark.parametrize("annuli", [8, 32, 2048])
def test_reference_density_composition(annuli):
    rotor = valid_request()
    del rotor["density_kg_m3"]
    rotor["annuli"] = annuli
    request = {
        "evaluation": "standard_atmosphere_isolated_hover_experimental",
        "atmosphere": {"altitude_m": 20000, "altitude_kind": "geopotential"},
        "rotor": rotor,
    }
    original = deepcopy(request)
    result = evaluate_atmosphere_hover(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert request == original
    state = asdict(standard_atmosphere(20000, altitude_kind="geopotential"))
    direct_request = deepcopy(rotor)
    direct_request["density_kg_m3"] = state["density_kg_m3"]
    direct_result = evaluate_hover_bemt(direct_request)
    assert result["outputs"] == {"atmosphere": state, "hover": direct_result["outputs"]}
    assert result["inputs_sha256"] == sha256_record(original)
    assert [stage["stage_id"] for stage in result["stages"]] == ["atmosphere", "hover"]
    assert result["stages"][0]["inputs"] == request["atmosphere"]
    assert result["stages"][0]["result"] == state
    assert result["stages"][1]["inputs"] == direct_request
    assert result["stages"][1]["result"] == direct_result
    assert result["transfers"][0]["value"] == state["density_kg_m3"]
    for stage in result["stages"]:
        assert stage["inputs_sha256"] == sha256_record(stage["inputs"])
        assert stage["result_sha256"] == sha256_record(stage["result"])


def workflow_request():
    rotor = valid_request()
    rotor.pop("density_kg_m3")
    return {
        "evaluation": "standard_atmosphere_isolated_hover_experimental",
        "atmosphere": {"altitude_m": 20000, "altitude_kind": "geopotential"},
        "rotor": rotor,
    }


@pytest.mark.parametrize(
    "altitude", [True, "20000", None, float("nan"), float("inf"), 10**1000, -1, 30001]
)
def test_bad_workflow_altitudes(altitude):
    request = workflow_request()
    request["atmosphere"]["altitude_m"] = altitude
    result = evaluate_atmosphere_hover(request)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["outputs"] == {}
    assert result["stages"] == []
    assert "inputs_sha256" not in result


@pytest.mark.parametrize("extra_key", ["density_kg_m3", "unexpected"])
def test_workflow_rejects_extra_rotor_keys(extra_key):
    request = workflow_request()
    request["rotor"][extra_key] = 1.225
    result = evaluate_atmosphere_hover(request)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["outputs"] == {}
    assert result["stages"] == []
    assert "inputs_sha256" not in result


def test_workflow_component_rejection_records_atmosphere():
    request = workflow_request()
    request["rotor"]["annuli"] = 0
    result = evaluate_atmosphere_hover(request)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["failed_stage"] == "hover"
    assert len(result["stages"]) == 1
    assert result["outputs"] == {}
    stage = result["stages"][0]
    assert stage["stage_id"] == "atmosphere"
    assert stage["inputs"] == request["atmosphere"]
    assert stage["result"] == asdict(
        standard_atmosphere(20000, altitude_kind="geopotential")
    )
    assert stage["inputs_sha256"] == sha256_record(stage["inputs"])
    assert stage["result_sha256"] == sha256_record(stage["result"])


def test_workflow_atmosphere_runtime_failure(monkeypatch):
    def fail_atmosphere(*args, **kwargs):
        raise RuntimeError("secret")

    monkeypatch.setattr(
        "physimesh.drone.atmosphere_hover_workflow.standard_atmosphere", fail_atmosphere
    )
    result = evaluate_atmosphere_hover(workflow_request())
    assert result["status"] == "NUMERICAL_FAILED"
    assert result["failed_stage"] == "atmosphere"
    assert "secret" not in repr(result)
    assert result["outputs"] == {}


def test_workflow_malformed_hover_result(monkeypatch):
    monkeypatch.setattr(
        "physimesh.drone.atmosphere_hover_workflow.evaluate_hover_bemt",
        lambda *args, **kwargs: {},
    )
    result = evaluate_atmosphere_hover(workflow_request())
    assert result["status"] == "NUMERICAL_FAILED"
    assert result["failed_stage"] == "hover"
    assert len(result["stages"]) == 1
    assert result["outputs"] == {}


def test_workflow_nominal_qualifications_unverified():
    result = evaluate_atmosphere_hover(workflow_request())
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["numerical_qualification"] == "NOT_ESTABLISHED"
    assert result["evidence_level"] == "unverified"
    assert result["aircraft_status"] is None
    assert result["feasibility"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("density_kg_m3", float("nan")),
        ("pressure_pa", -1.0),
        ("model_id", "wrong-model"),
        ("evidence_status", "VALIDATED"),
        ("altitude_kind", "geometric"),
    ],
)
def test_workflow_corrupt_atmosphere_state(monkeypatch, field, value):
    state = standard_atmosphere(20000, altitude_kind="geopotential")
    corrupted = replace(state, **{field: value})
    monkeypatch.setattr(
        "physimesh.drone.atmosphere_hover_workflow.standard_atmosphere",
        lambda *args, **kwargs: corrupted,
    )
    result = evaluate_atmosphere_hover(workflow_request())
    assert result["status"] == "NUMERICAL_FAILED"
    assert result["failed_stage"] == "atmosphere"
    assert result["stages"] == []
    assert result["outputs"] == {}
    assert result["output_units"] == {}


def test_workflow_refuses_plain_dict_atmosphere_state(monkeypatch):
    state = asdict(standard_atmosphere(20000, altitude_kind="geopotential"))
    monkeypatch.setattr(
        "physimesh.drone.atmosphere_hover_workflow.standard_atmosphere",
        lambda *args, **kwargs: state,
    )
    result = evaluate_atmosphere_hover(workflow_request())
    assert result["status"] == "NUMERICAL_FAILED"
    assert result["failed_stage"] == "atmosphere"
    assert result["stages"] == []
    assert result["outputs"] == {}


@pytest.mark.parametrize(
    "path,value",
    [
        (("model_id",), "wrong-model"),
        (("status",), "NUMERICAL_FAILED"),
        (("physical_validation",), "ESTABLISHED"),
        (("output_units", "thrust_n"), "kg"),
        (("outputs", "annuli"), 9),
        (("outputs", "radial_fraction"), [0.5]),
        (("outputs", "thrust_n"), float("nan")),
        (("outputs", "shaft_power_w"), float("inf")),
    ],
)
def test_workflow_corrupt_hover_component(monkeypatch, path, value):
    request = workflow_request()
    direct_request = deepcopy(request["rotor"])
    direct_request["density_kg_m3"] = standard_atmosphere(
        20000, altitude_kind="geopotential"
    ).density_kg_m3
    component = evaluate_hover_bemt(direct_request)
    assert component["status"] == "COMPUTED_EXPERIMENTAL"
    target = component
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    monkeypatch.setattr(
        "physimesh.drone.atmosphere_hover_workflow.evaluate_hover_bemt",
        lambda *args, **kwargs: component,
    )
    result = evaluate_atmosphere_hover(request)
    assert result["status"] == "NUMERICAL_FAILED"
    assert result["failed_stage"] == "hover"
    assert len(result["stages"]) == 1
    assert result["stages"][0]["stage_id"] == "atmosphere"
    assert result["outputs"] == {}
    assert result["output_units"] == {}


@pytest.mark.parametrize("altitude", [0, 11000, 20000, 30000])
@pytest.mark.parametrize("kind", ["geometric", "geopotential"])
def test_workflow_altitude_density_transfer_matches_direct_components(altitude, kind):
    request = workflow_request()
    request["atmosphere"] = {"altitude_m": altitude, "altitude_kind": kind}
    state = asdict(standard_atmosphere(altitude, altitude_kind=kind))
    direct_request = deepcopy(request["rotor"])
    direct_request["density_kg_m3"] = state["density_kg_m3"]
    direct_result = evaluate_hover_bemt(direct_request)
    assert direct_result["status"] == "COMPUTED_EXPERIMENTAL"
    result = evaluate_atmosphere_hover(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["atmosphere"] == state
    assert result["transfers"][0]["value"] == state["density_kg_m3"]
    assert result["stages"][1]["inputs"] == direct_request
    assert result["stages"][1]["result"] == direct_result
    assert result["outputs"]["hover"] == direct_result["outputs"]


def test_workflow_records_inputs_before_hover_adapter_mutation(monkeypatch):
    request = workflow_request()
    original = deepcopy(request)
    captured = []

    def mutating_adapter(received):
        captured.append(deepcopy(received))
        nominal = evaluate_hover_bemt(received)
        received["annuli"] = 9999
        return nominal

    monkeypatch.setattr(
        "physimesh.drone.atmosphere_hover_workflow.evaluate_hover_bemt",
        mutating_adapter,
    )
    result = evaluate_atmosphere_hover(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert request == original
    assert len(captured) == 1
    assert captured[0]["annuli"] == 8
    assert result["inputs_sha256"] == sha256_record(original)
    assert result["stages"][1]["inputs"] == captured[0]
    assert result["stages"][1]["inputs"]["annuli"] == 8
    for stage in result["stages"]:
        assert stage["inputs_sha256"] == sha256_record(stage["inputs"])
        assert stage["result_sha256"] == sha256_record(stage["result"])


def test_workflow_returned_records_and_outputs_are_independent_copies():
    request = workflow_request()
    original = deepcopy(request)
    prior = evaluate_atmosphere_hover(request)
    baseline = deepcopy(prior)
    result = evaluate_atmosphere_hover(request)
    assert result == baseline
    result["stages"][0]["inputs"]["altitude_m"] = 0
    result["stages"][1]["inputs"]["annuli"] = 9999
    result["stages"][0]["result"]["density_kg_m3"] = -1
    result["stages"][1]["result"]["outputs"]["radial_fraction"][0] = -1
    assert result["outputs"] == baseline["outputs"]
    result["outputs"]["atmosphere"]["pressure_pa"] = -1
    result["outputs"]["hover"]["inflow_ratio"][0] = -1
    assert result["stages"][0]["result"]["pressure_pa"] == (
        baseline["stages"][0]["result"]["pressure_pa"]
    )
    assert result["stages"][1]["result"]["outputs"]["inflow_ratio"] == (
        baseline["stages"][1]["result"]["outputs"]["inflow_ratio"]
    )
    assert request == original
    assert prior == baseline
    assert evaluate_atmosphere_hover(request) == baseline


def forbid_component_calls(monkeypatch):
    def unexpected_call(*args, **kwargs):
        raise AssertionError("Invalid workflow input reached a component")

    for component in ("standard_atmosphere", "evaluate_hover_bemt"):
        monkeypatch.setattr(
            f"physimesh.drone.atmosphere_hover_workflow.{component}", unexpected_call
        )


def assert_schema_refusal(result):
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["stages"] == []
    assert result["outputs"] == {}
    assert result["output_units"] == {}
    assert "inputs_sha256" not in result
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["numerical_qualification"] == "NOT_ESTABLISHED"
    assert result["evidence_level"] == "unverified"
    assert result["aircraft_status"] is None
    assert result["feasibility"] is None


@pytest.mark.parametrize("field", tuple(workflow_request()["rotor"]))
def test_workflow_missing_each_rotor_field_refuses_before_components(monkeypatch, field):
    forbid_component_calls(monkeypatch)
    request = workflow_request()
    del request["rotor"][field]
    assert_schema_refusal(evaluate_atmosphere_hover(request))


@pytest.mark.parametrize("case", ["cycle", "deep", "overlong"])
def test_workflow_bounded_json_refuses_before_components(monkeypatch, case):
    forbid_component_calls(monkeypatch)
    request = workflow_request()
    if case == "cycle":
        request["rotor"]["property_source"] = request
    elif case == "deep":
        nested = "source"
        for _ in range(9):
            nested = [nested]
        request["rotor"]["property_source"] = nested
    else:
        request["rotor"]["property_source"] = "s" * 2001
    assert_schema_refusal(evaluate_atmosphere_hover(request))


@pytest.mark.parametrize("case", ["dict_subclass", "float_subclass"])
def test_workflow_refuses_builtin_subclasses_before_components(monkeypatch, case):
    class DictSubclass(dict):
        pass

    class FloatSubclass(float):
        pass

    forbid_component_calls(monkeypatch)
    request = workflow_request()
    if case == "dict_subclass":
        request = DictSubclass(request)
    else:
        request["atmosphere"]["altitude_m"] = FloatSubclass(20000)
    assert_schema_refusal(evaluate_atmosphere_hover(request))


def test_workflow_transfer_and_unit_metadata():
    result = evaluate_atmosphere_hover(workflow_request())
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert len(result["transfers"]) == 1
    transfer = result["transfers"][0]
    assert transfer["source"] == "atmosphere.density_kg_m3"
    assert transfer["target"] == "hover.density_kg_m3"
    assert transfer["unit"] == "kg/m^3"
    assert transfer["operation"] == "scalar_value_copy"
    assert transfer["direction"] == "one_way"
    assert transfer["interpolation"] is False
    assert transfer["feedback"] is False
    assert transfer["value"] == result["outputs"]["atmosphere"]["density_kg_m3"]
    assert result["output_units"]["atmosphere"] == {
        "input_altitude_m": "m",
        "altitude_kind": "not_applicable",
        "geopotential_altitude_m": "m",
        "pressure_pa": "Pa",
        "temperature_k": "K",
        "density_kg_m3": "kg/m^3",
        "model_id": "not_applicable",
        "evidence_status": "not_applicable",
    }
    assert result["output_units"]["hover"] == result["stages"][1]["result"]["output_units"]
