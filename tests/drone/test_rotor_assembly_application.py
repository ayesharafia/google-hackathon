import json

import pytest

from physimesh.drone.provenance import sha256_record
from physimesh.drone.rotor_assembly import EVALUATION, evaluate_rotor_assembly

from .test_model_graph_application import client as client  # noqa: PLC0414
from .test_rotor_assembly import request as assembly_request

PATH = "/api/drone/rotor-assembly/evaluate"
CATALOG = "/api/drone/rotor-assembly/catalog"


def test_evaluate(client):
    body = assembly_request()
    direct = evaluate_rotor_assembly(body)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    for key, value in direct.items():
        assert result[key] == value
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["request_sha256"] == result["input_sha256"] == sha256_record(body)
    assert result.pop("evaluation_sha256") == sha256_record(result)


def test_catalog(client):
    response = client.get(CATALOG, headers=client.auth_headers)
    assert response.status_code == 200
    catalog = response.json()
    assert catalog["evaluation"] == EVALUATION
    assert catalog["frame"] == "body_forward_left_up"
    assert catalog["physical_validation"] == "NOT_ESTABLISHED"
    assert catalog["numerical_qualification"] == "NOT_ESTABLISHED"
    assert catalog["runtime_identity"] == "NOT_ESTABLISHED"
    assert catalog["feasibility"] is None
    assert catalog["limits"]["body_bytes"] == 131072


@pytest.mark.parametrize("raw", [b'{"evaluation":1,"evaluation":2}', b'{"evaluation":NaN}', b"\xff", b"[]"])
def test_invalid_json(client, raw):
    response = client.post(
        PATH, content=raw, headers={**client.auth_headers, "Content-Type": "application/json"}
    )
    assert response.status_code == 422 and response.json() == {"detail": "Invalid rotor assembly request."}


def test_invalid_rotation_sign(client):
    body = json.loads(json.dumps(assembly_request()))
    body["rotors"][0]["rotation_sign"] = True
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "GRAPH_INVALID"
    assert result["outputs"] == {}
    assert result["stages"] == []
    assert "request_sha256" not in result
    assert "input_sha256" not in result
    assert "evaluation_sha256" not in result


def test_body_cap(client):
    raw = json.dumps(assembly_request()).encode()
    boundary = raw + b" " * (131072 - len(raw))
    headers = {**client.auth_headers, "Content-Type": "application/json"}
    assert client.post(PATH, content=boundary, headers=headers).status_code == 200
    response = client.post(PATH, content=iter((boundary, b" ")), headers=headers)
    assert response.status_code == 413
    assert response.json()["detail"] == "request byte budget exceeded"
    assert client.post(PATH, content=boundary + b" ", headers=headers).status_code == 413


def test_auth_csrf(client):
    assert client.get(CATALOG).status_code in (401, 403)
    assert client.post(PATH, json=assembly_request()).status_code in (401, 403)
    foreign = {"Origin": "https://foreign.example"}
    same = {"Origin": "http://testserver"}
    assert (
        client.post(PATH, json=assembly_request(), headers={**client.auth_headers, **foreign}).status_code
        == 200
    )
    if client.hosted_test:
        for suffix in ("/", "/extra", "-extra"):
            assert (
                client.get(CATALOG + suffix, headers=client.auth_headers, follow_redirects=False).status_code
                == 403
            )
            assert (
                client.post(
                    PATH + suffix,
                    json=assembly_request(),
                    headers=client.auth_headers,
                    follow_redirects=False,
                ).status_code
                == 403
            )
        return
    session = client.post("/api/session", headers={**client.auth_headers, **same})
    assert session.status_code == 200
    assert client.get(CATALOG).status_code == 200
    assert client.post(PATH, json=assembly_request()).status_code == 403
    assert client.post(PATH, json=assembly_request(), headers=foreign).status_code == 403
    assert client.post(PATH, json=assembly_request(), headers=same).status_code == 200
