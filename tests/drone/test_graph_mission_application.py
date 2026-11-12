import json

import pytest

from physimesh.drone.graph_mission import EVALUATION, evaluate_graph_mission
from physimesh.drone.provenance import sha256_record

from .test_graph_mission import mission
from .test_model_graph_application import client as client  # noqa: PLC0414 - pytest fixture reexport

PATH = "/api/drone/graph-mission/evaluate"
CATALOG = "/api/drone/graph-mission/catalog"


def test_graph_mission_evaluation_and_catalog(client):
    b = mission()
    direct = evaluate_graph_mission(b)
    response = client.post(PATH, json=b, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    for key, value in direct.items():
        assert result[key] == value
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["input_sha256"] == result["request_sha256"] == sha256_record(b)
    evaluation_sha256 = result.pop("evaluation_sha256")
    assert evaluation_sha256 == sha256_record(result)
    response = client.get(CATALOG, headers=client.auth_headers)
    assert response.status_code == 200
    catalog = response.json()
    assert catalog["evaluation"] == EVALUATION
    for key in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert catalog[key] == "NOT_ESTABLISHED"
    assert catalog["feasibility"] is None
    assert catalog["limits"]["body_bytes"] == 131072

@pytest.mark.parametrize('raw', [b'{"evaluation":1,"evaluation":2}', b'{"x":NaN}', b'\xff', b'[]'])
def test_graph_mission_malformed(client, raw):
    response = client.post(PATH, content=raw, headers=client.auth_headers)
    assert response.status_code == 422
    assert response.json() == {'detail': 'Invalid graph mission request.'}


def test_graph_mission_semantic_refusal(client):
    b = mission()
    b['segments'][-1]['conversion_efficiency'] = True
    response = client.post(PATH, json=b, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'GRAPH_INVALID'
    assert result['outputs'] == {} and result['segments'] == []
    assert all(k not in result for k in ('input_sha256', 'request_sha256', 'evaluation_sha256'))


def test_graph_mission_body_limit(client):
    raw = json.dumps(mission()).encode()
    boundary = raw + b' ' * (131072 - len(raw))
    assert client.post(PATH, content=boundary, headers=client.auth_headers).status_code == 200
    response = client.post(PATH, content=iter([boundary, b' ']), headers=client.auth_headers)
    assert response.status_code == 413
    assert response.json() == {'detail': 'Request byte budget exceeded.'}


def test_graph_mission_auth_and_suffixes(client):
    assert client.get(CATALOG).status_code in (401, 403)
    assert client.post(PATH, json=mission()).status_code in (401, 403)
    if client.hosted_test:
        for suffix in ('/', '/extra', '-extra'):
            assert client.get(CATALOG + suffix, headers=client.auth_headers,
                              follow_redirects=False).status_code == 403
            assert client.post(PATH + suffix, json=mission(), headers=client.auth_headers,
                               follow_redirects=False).status_code == 403


def test_mission_cookie_csrf(client):
    foreign = {"Origin": "https://untrusted.example"}
    same = {"Origin": "http://testserver"}
    bearer = {**client.auth_headers, **foreign}
    assert client.post(PATH, json=mission(), headers=bearer).status_code == 200
    if client.hosted_test:
        return
    session = {**client.auth_headers, **same}
    assert client.post("/api/session", headers=session).status_code == 200
    assert client.get(CATALOG).status_code == 200
    assert client.post(PATH, json=mission()).status_code == 403
    assert client.post(PATH, json=mission(), headers=foreign).status_code == 403
    assert client.post(PATH, json=mission(), headers=same).status_code == 200
