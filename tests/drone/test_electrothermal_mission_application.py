import pytest

from physimesh.drone.electrothermal_mission import EVALUATION, evaluate_electrothermal_mission
from physimesh.drone.provenance import sha256_record

from .test_electrothermal_mission import request as electrothermal_request
from .test_graph_mission_application import CATALOG, PATH
from .test_model_graph_application import client as client  # noqa: PLC0414


def test_electrothermal_application(client):
    b = electrothermal_request()
    direct = evaluate_electrothermal_mission(b)
    response = client.post(PATH, json=b, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    assert all(result[key] == value for key, value in direct.items())
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["input_sha256"] == result["request_sha256"] == sha256_record(b)
    digest = result.pop("evaluation_sha256")
    assert digest == sha256_record(result)
    rows = result["outputs"]["thermal"]["segments"]
    assert rows[1]["start_temperature_k"] == rows[0]["end_temperature_k"]
    for key in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert result[key] == "NOT_ESTABLISHED"
    assert result["feasibility"] is None
    catalog = client.get(CATALOG, headers=client.auth_headers).json()
    assert (
        catalog["evaluation"] == "constant_condition_graph_mission_experimental"
        and catalog["limits"]["json_values"] == 32768
    )
    assert catalog["evaluations"][EVALUATION]["json_values"] == 49152 and set(
        catalog["evaluations"][EVALUATION]["required_fields"]
    ) == set(b)


@pytest.mark.parametrize(
    "evaluation", ["", " " + EVALUATION, EVALUATION + " ", "constant_condition_graph_mission_experimental"]
)
def test_electrothermal_rejects_other_evaluation(client, evaluation):
    b = electrothermal_request()
    b["evaluation"] = evaluation
    response = client.post(PATH, json=b, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    assert (
        result["status"] == "GRAPH_INVALID" and result["outputs"] == {} and "evaluation_sha256" not in result
    )


def test_boolean(client):
    b = electrothermal_request()
    b["thermal_segments"][-1]["heat_fraction_of_electrical_input"] = True
    response = client.post(PATH, json=b, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "GRAPH_INVALID"
    assert result["outputs"] == {}
    assert not {"request_sha256", "input_sha256", "evaluation_sha256"} & result.keys()


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b"\xff", b"[]"])
def test_invalid_json(client, raw):
    response = client.post(PATH, content=raw, headers=client.auth_headers)
    assert response.status_code == 422
    result = response.json()
    assert result == {"detail": "Invalid graph mission request."}


def test_byte_cap(client):
    import json

    raw = json.dumps(electrothermal_request()).encode("utf-8")
    assert len(raw) <= 131072
    raw += b" " * (131072 - len(raw))
    response = client.post(PATH, content=raw, headers=client.auth_headers)
    assert response.status_code == 200
    response = client.post(PATH, content=iter([raw, b" "]), headers=client.auth_headers)
    assert response.status_code == 413
