import json

import pytest

from physimesh.drone.multi_rotor_mission import EVALUATION, evaluate_multi_rotor_mission
from physimesh.drone.provenance import sha256_record

from .test_graph_mission_application import CATALOG, PATH
from .test_model_graph_application import client as client  # noqa: PLC0414
from .test_multi_rotor_mission import mission as mission  # noqa: PLC0414


def assert_graph_invalid(response):
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "GRAPH_INVALID"
    assert result["outputs"] == {}
    assert not {"request_sha256", "input_sha256", "evaluation_sha256"} & result.keys()


def test_multi_rotor_application(client, mission):
    direct = evaluate_multi_rotor_mission(mission)
    response = client.post(PATH, json=mission, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    request_digest = sha256_record(mission)
    assert result == {
        **direct,
        "input_sha256": request_digest,
        "request_sha256": request_digest,
        "evaluation_sha256": result["evaluation_sha256"],
    }
    digest = result.pop("evaluation_sha256")
    assert digest == sha256_record(result)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    for key in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert result[key] == "NOT_ESTABLISHED"
    assert result["feasibility"] is None
    assert result.get("production_scope") in (None, "NOT_ESTABLISHED")
    assert result.get("verdict") is None

    response = client.get(CATALOG, headers=client.auth_headers)
    assert response.status_code == 200
    catalog = response.json()
    assert catalog["evaluation"] == "constant_condition_graph_mission_experimental"
    assert catalog["limits"]["json_values"] == 32768
    entry = catalog["evaluations"][EVALUATION]
    assert entry["json_values"] == 32768
    assert set(entry["required_fields"]) == set(mission)


@pytest.mark.parametrize(
    "evaluation",
    ["", " ", " " + EVALUATION, EVALUATION + " ", "unknown",
     "constant_condition_graph_mission_experimental"],
)
def test_multi_rotor_rejects_other_evaluation(client, mission, evaluation):
    mission["evaluation"] = evaluation
    assert_graph_invalid(client.post(PATH, json=mission, headers=client.auth_headers))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("rotors", 1, "conversion_efficiency"), True),
        (("duration_s",), -1),
        (("graph", "evaluation"), "unknown"),
    ],
)
def test_multi_rotor_rejects_late_invalid_segment(client, mission, path, value):
    target = mission["segments"][-1]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert_graph_invalid(client.post(PATH, json=mission, headers=client.auth_headers))


@pytest.mark.parametrize(
    "raw",
    [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}',
     b"\xff", b"[]", b"null", b'"text"'],
)
def test_multi_rotor_invalid_json(client, raw):
    response = client.post(PATH, content=raw, headers=client.auth_headers)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid graph mission request."}


def test_multi_rotor_byte_cap(client, mission):
    raw = json.dumps(mission).encode("utf-8")
    assert len(raw) <= 131072
    raw += b" " * (131072 - len(raw))
    response = client.post(PATH, content=raw, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "COMPUTED_EXPERIMENTAL"
    response = client.post(PATH, content=iter([raw, b" "]), headers=client.auth_headers)
    assert response.status_code == 413


def test_multi_rotor_cookie_auth_paths(client, mission):
    assert client.get(CATALOG).status_code in (401, 403)
    assert client.post(PATH, json=mission).status_code in (401, 403)

    bearer = {**client.auth_headers, "Origin": "https://foreign.example"}
    assert client.get(CATALOG, headers=bearer).status_code == 200
    assert client.post(PATH, json=mission, headers=bearer).status_code == 200

    if client.hosted_test:
        for suffix in ("/", "/extra", "-extra"):
            assert client.get(
                CATALOG + suffix, headers=bearer, follow_redirects=False
            ).status_code == 403
            assert client.post(
                PATH + suffix, json=mission, headers=bearer,
                follow_redirects=False,
            ).status_code == 403
    else:
        assert client.post(
            "/api/session",
            headers={**client.auth_headers, "Origin": "http://testserver"},
        ).status_code == 200
        assert client.get(CATALOG).status_code == 200
        assert client.post(PATH, json=mission).status_code == 403
        assert client.post(
            PATH, json=mission, headers={"Origin": "https://foreign.example"}
        ).status_code == 403
        assert client.post(
            PATH, json=mission, headers={"Origin": "http://testserver"}
        ).status_code == 200


def test_multi_rotor_execution_failure_hashes(client, mission):
    mission = json.loads(json.dumps(mission))
    mission["segments"][0]["rotors"][0]["conversion_efficiency"] = 1e-300
    direct = evaluate_multi_rotor_mission(mission)
    assert direct["request_sha256"] == sha256_record(mission)
    assert direct["status"] == "EXECUTION_FAILED"
    assert direct["segments"] == []
    assert direct["outputs"] == direct["output_units"] == {}

    response = client.post(PATH, json=mission, headers=client.auth_headers)
    assert response.status_code == 200
    record = response.json()
    evaluation_sha256 = record.pop("evaluation_sha256")
    assert evaluation_sha256 == sha256_record(record)
    assert record.pop("input_sha256") == direct["request_sha256"]
    assert record == direct
