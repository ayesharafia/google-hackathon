"""HTTP graph contract, bounded parsing, and inherited authorization."""

import json

import pytest
from fastapi.testclient import TestClient

from physimesh.drone.model_graph_execution import adapter_metadata, evaluate_model_graph
from physimesh.drone.provenance import sha256_record

from .test_model_graph_execution import edge, node, request, wing

PATH = '/api/drone/model-graph/evaluate'
CATALOG = '/api/drone/model-graph/catalog'
LIMIT = 128 * 1024
INVALID = {'detail': 'Invalid model graph request.'}


@pytest.fixture(params=[False, True], ids=['local', 'hosted'])
def client(tmp_path, request, monkeypatch):
    from physimesh.api import app as app_module
    from physimesh.api.app import create_app
    from physimesh.api.settings import Settings

    # This API-only checkout omits the static web bundle.
    (tmp_path / 'web').mkdir()
    monkeypatch.setattr(app_module, '__file__', str(tmp_path / 'src/physimesh/api/app.py'))
    app = create_app(Settings(tmp_path, tmp_path / 'jobs.sqlite', 'synthetic-token', None,
                              hosted_mode=request.param))
    token = 'synthetic-token'
    if request.param:
        app.state.identity.provision('graph@example.test', password='synthetic-fixture-password')
        token = app.state.identity.login(
            'graph@example.test', password='synthetic-fixture-password')['token']
    with TestClient(app) as test_client:
        test_client.auth_headers = {'Authorization': f'Bearer {token}'}
        test_client.hosted_test = request.param
        yield test_client


def assert_core_result(response, body):
    assert response.status_code == 200, response.text
    result = response.json()
    direct = evaluate_model_graph(body)
    for key, value in direct.items():
        assert result[key] == value
    if 'request_sha256' in direct:
        assert result['request_sha256'] == result['input_sha256'] == sha256_record(body)
        digest = result.pop('evaluation_sha256')
        assert digest == sha256_record(result)
    else:
        for key in ('request_sha256', 'input_sha256', 'evaluation_sha256'):
            assert key not in result
    return result


def test_catalog_and_branch_direct_equality(client):
    body = request()
    result = assert_core_result(client.post(PATH, json=body, headers=client.auth_headers), body)
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    assert result['stage_order'] == ['a', 'b', 'h', 'w']
    assert set(result['outputs']) == {'h', 'w', 'b'}
    response = client.get(CATALOG, headers=client.auth_headers)
    assert response.status_code == 200
    catalog = response.json()
    assert catalog['evaluation'] == body['evaluation']
    assert catalog['schema_version'] == 'bounded_model_graph_v1'
    assert catalog['adapters'] == adapter_metadata()
    assert catalog['limits']['body_bytes'] == LIMIT
    assert catalog['evidence_level'] == 'unverified'
    for key in ('physical_validation', 'numerical_qualification', 'runtime_identity'):
        assert catalog[key] == 'NOT_ESTABLISHED'
    assert catalog['aircraft_status'] is catalog['feasibility'] is None


def test_routes_require_auth(client):
    for headers in ({}, {'Authorization': 'Bearer wrong-token'}):
        assert client.get(CATALOG, headers=headers).status_code in (401, 403)
        assert client.post(PATH, json=request(), headers=headers).status_code in (401, 403)


@pytest.mark.parametrize('defect', ['duplicate', 'nan', 'infinity', 'overflow', 'malformed', 'shape'])
def test_generic_structural_errors(client, defect):
    raw = json.dumps(request())
    if defect == 'duplicate':
        raw = raw[:-1] + ', "evaluation": "PRIVATE_SECRET"}'
    elif defect in ('nan', 'infinity', 'overflow'):
        raw = raw.replace('1000', {'nan': 'NaN', 'infinity': 'Infinity',
                                   'overflow': '1e9999'}[defect], 1)
    elif defect == 'malformed':
        raw = '{"PRIVATE_SECRET":'
    else:
        raw = json.dumps(request() | {'PRIVATE_SECRET': True})
    response = client.post(PATH, content=raw, headers=dict(
        client.auth_headers, **{'Content-Type': 'application/json'}))
    assert response.status_code == 422
    assert response.json() == INVALID


@pytest.mark.parametrize('defect', ['unknown_adapter', 'cycle'])
def test_graph_refusals(client, defect):
    body = request()
    if defect == 'unknown_adapter':
        body['nodes'][0]['model'] = 'caller.unknown'
    else:
        for name in ('c', 'd'):
            inputs = wing()
            del inputs['lift_coefficient']
            body['nodes'].append(node(name, body['nodes'][3]['model'], inputs))
        body['connections'] += [edge('c', 'mach_number', 'd', 'lift_coefficient'),
                                edge('d', 'mach_number', 'c', 'lift_coefficient')]
    result = assert_core_result(client.post(PATH, json=body, headers=client.auth_headers), body)
    assert result['status'] == 'GRAPH_INVALID'
    assert result['outputs'] == result['output_units'] == {}
    assert result['stages'] == result['transfers'] == []


@pytest.mark.parametrize('streamed', [False, True], ids=['declared', 'streamed'])
def test_body_byte_limit(client, streamed):
    # Whitespace leaves a valid request at the exact byte boundary.
    raw = json.dumps(request()).encode()
    bounded = raw + b' ' * (LIMIT - len(raw))
    assert client.post(PATH, content=bounded, headers=client.auth_headers).status_code == 200
    oversized = bounded + b' '
    content = iter((oversized[:LIMIT], oversized[LIMIT:])) if streamed else oversized
    response = client.post(PATH, content=content, headers=client.auth_headers)
    assert response.status_code == 413
    assert response.json() == {'detail': 'request byte budget exceeded'}


def test_bearer_origin_and_cookie_csrf(client):
    assert client.post(PATH, json=request(), headers=dict(
        client.auth_headers, Origin='https://untrusted.example')).status_code == 200
    if client.hosted_test:
        return
    response = client.post('/api/session', headers=dict(
        client.auth_headers, Origin='http://testserver'))
    assert response.status_code == 200
    assert client.get(CATALOG).status_code == 200
    for headers in ({}, {'Origin': 'https://untrusted.example'}):
        assert client.post(PATH, json=request(), headers=headers).status_code == 403
    assert client.post(PATH, json=request(), headers={
        'Origin': 'http://testserver'}).status_code == 200


@pytest.mark.parametrize('suffix', ['/', '/extra', '-extra', 'evil'])
def test_hosted_allowlist_exact(client, suffix):
    if not client.hosted_test:
        return
    assert client.post(PATH + suffix, json=request(), headers=client.auth_headers,
                       follow_redirects=False).status_code == 403
    assert client.get(CATALOG + suffix, headers=client.auth_headers,
                      follow_redirects=False).status_code == 403
