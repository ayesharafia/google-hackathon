import json

import pytest

from physimesh.drone.ledger_rotor_dynamics import EVALUATION, evaluate_ledger_rotor_dynamics
from physimesh.drone.provenance import sha256_record

from .test_ledger_rotor_dynamics import request as assembly_request
from .test_model_graph_application import client as client  # noqa: PLC0414

PATH = "/api/drone/ledger-rotor-dynamics/evaluate"
CATALOG = "/api/drone/ledger-rotor-dynamics/catalog"


def test_evaluate(client):
    body = assembly_request()
    direct = evaluate_ledger_rotor_dynamics(body)
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
    assert catalog["limits"]["json_values"] == 49152
    assert catalog["provenance_boundaries"]["nested_result_sha256"] == "syntax only, not independently rebound"


@pytest.mark.parametrize("raw", [b'{"evaluation":1,"evaluation":2}', b'{"evaluation":NaN}', b"\xff", b"[]"])
def test_invalid_json(client, raw):
    response = client.post(
        PATH, content=raw, headers={**client.auth_headers, "Content-Type": "application/json"}
    )
    assert response.status_code == 422 and response.json() == {"detail": "Invalid ledger rotor dynamics request."}


def test_invalid_rotation_sign(client):
    body = json.loads(json.dumps(assembly_request()))
    body["initial_state"]["quaternion_body_to_enu"] = [0,1,0,0]
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


def test_execution_atomic(client, monkeypatch):
    import physimesh.drone.ledger_rotor_dynamics as core

    def fail(*args, **kwargs):
        raise RuntimeError("private failure marker")

    monkeypatch.setattr(core.ml, "evaluate_mass_ledger", fail)
    body = assembly_request()
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "EXECUTION_FAILED"
    assert result["diagnostics_complete"] is False
    assert result["stages"] == []
    assert result["transfers"] == {}
    assert result["outputs"] == {}
    assert result["output_units"] == {}
    assert result["request_sha256"] == sha256_record(body)
    assert result["input_sha256"] == sha256_record(body)
    unsigned = dict(result)
    evaluation_hash = unsigned.pop("evaluation_sha256")
    assert evaluation_hash == sha256_record(unsigned)
    assert "private failure marker" not in response.text


def test_badjsonbudgets(client):
    nested = {}
    cursor = nested
    for _ in range(12):
        cursor["x"] = {}
        cursor = cursor["x"]
    oversized = {"x": [[0] * 256 for _ in range(193)]}
    for body in (nested, oversized):
        raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
        assert len(raw) <= 131072
        response = client.post(PATH, content=raw, headers={**client.auth_headers, "Content-Type": "application/json"})
        assert response.status_code == 422
        assert response.json()["detail"] == (
            "Invalid ledger rotor dynamics request."
        )
