from copy import deepcopy

from physimesh.drone.model_graph_execution import adapter_metadata
from physimesh.drone.provenance import sha256_record
from physimesh.drone.reference_air_graph import (
    EVALUATION,
    evaluate_reference_air_graph,
)
from physimesh.drone.reference_air_graph import (
    adapter_metadata as air_metadata,
)

from .test_model_graph_application import CATALOG, PATH
from .test_model_graph_application import client as client  # noqa: PLC0414 - pytest fixture re-export
from .test_model_graph_execution import edge, node, target, wing


def body():
    w = wing()
    props = ("density_kg_m3", "dynamic_viscosity_pa_s", "speed_of_sound_m_s")
    for prop in props:
        w.pop(prop)
    return {
        "evaluation": EVALUATION,
        "nodes": [
            node("air", "reference_air_properties",
                 {"altitude_m": 1000, "altitude_kind": "geometric"}),
            node("wing", "fixed_wing_aerodynamic_screening", w),
        ],
        "connections": [edge("air", prop, "wing", prop) for prop in props],
        "targets": [target("wing", prop) for prop in
                    ("reynolds_number", "mach_number", "drag_n")],
    }


def test_air_graph_http_dispatch(client):
    http, auth_headers = client, client.auth_headers
    request = body()
    original = deepcopy(request)
    direct = evaluate_reference_air_graph(request)
    response = http.post(PATH, json=request, headers=auth_headers)
    assert response.status_code == 200
    result = response.json()
    for key, value in direct.items():
        assert result[key] == value
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    assert len(direct["transfers"]) == 3
    assert direct["stage_order"] == ["air", "wing"]
    assert request == original
    assert result["input_sha256"] == result["request_sha256"] == sha256_record(original)
    evaluation_sha256 = result.pop("evaluation_sha256")
    assert evaluation_sha256 == sha256_record(result)


def test_air_graph_catalog(client):
    http, auth_headers = client, client.auth_headers
    response = http.get(CATALOG, headers=auth_headers)
    assert response.status_code == 200
    catalog = response.json()
    assert catalog["adapters"] == adapter_metadata()
    evaluation = catalog["evaluations"][EVALUATION]
    assert evaluation["adapters"] == air_metadata()
    assert catalog["physical_validation"] == "NOT_ESTABLISHED"
    assert catalog["numerical_qualification"] == "NOT_ESTABLISHED"
    assert catalog["runtime_identity"] == "NOT_ESTABLISHED"
    assert catalog["feasibility"] is None

import pytest


def _assert_air_graph_invalid(response):
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "GRAPH_INVALID"
    assert result["outputs"] == {}
    assert result["output_units"] == {}
    assert result["stages"] == []
    assert result["transfers"] == []
    assert not {
        "request_sha256", "input_sha256", "evaluation_sha256"
    }.intersection(result)


@pytest.mark.parametrize("defect", ["bool_altitude", "extra_input", "blank_kind"])
def test_air_structural_defects(client, defect):
    payload = body()
    inputs = payload["nodes"][0]["inputs"]
    if defect == "bool_altitude":
        inputs["altitude_m"] = True
    elif defect == "extra_input":
        inputs["private_marker"] = "private"
    else:
        inputs["altitude_kind"] = ""
    response = client.post(PATH, json=payload, headers=client.auth_headers)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid model graph request."}


@pytest.mark.parametrize("defect", ["missing_kind", "unknown_model", "self_edge"])
def test_air_semantic_defects(client, defect):
    payload = body()
    if defect == "missing_kind":
        payload["nodes"][0]["inputs"].pop("altitude_kind")
    elif defect == "unknown_model":
        payload["nodes"][0]["model"] = "__unknown_model__"
    else:
        payload["connections"].append({"from_node":"air","from_port":"gravity_m_s2","to_node":"air","to_port":"altitude_m"})
    _assert_air_graph_invalid(
        client.post(PATH, json=payload, headers=client.auth_headers)
    )


@pytest.mark.parametrize("evaluation", [
    "", " " + EVALUATION, EVALUATION + " ", "bounded_model_graph_experimental",
])
def test_air_invalid_evaluation(client, evaluation):
    payload = body()
    payload["evaluation"] = evaluation
    _assert_air_graph_invalid(client.post(PATH, json=payload, headers=client.auth_headers))


def test_air_authentication_and_stream_limit(client):
    assert client.post(PATH, json=body()).status_code in (401, 403)
    assert client.post(PATH, content=iter([b" " * 131072, b" "]), headers=client.auth_headers).status_code == 413
