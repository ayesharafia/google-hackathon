"""HTTP contract and inherited authorization for dedicated modal routes."""
import json

import pytest
from fastapi.testclient import TestClient

from physimesh.drone.beam_modal_request import beam_modal_catalog, evaluate_modal_beam
from physimesh.drone.provenance import sha256_record

from .test_beam_modal_request import modal_request

PATH = '/api/drone/beam-modal/evaluate'
CATALOG = '/api/drone/beam-modal/catalog'


@pytest.fixture(params=[False, True], ids=['local', 'hosted'])
def client(tmp_path, request):
    from physimesh.api.app import create_app
    from physimesh.api.settings import Settings

    app = create_app(Settings(tmp_path, tmp_path / 'jobs.sqlite', 'synthetic-token', None,
                              hosted_mode=request.param))
    token = 'synthetic-token'
    if request.param:
        app.state.identity.provision('modal@example.test', password='synthetic-fixture-password')
        token = app.state.identity.login(
            'modal@example.test', password='synthetic-fixture-password')['token']
    with TestClient(app) as test_client:
        test_client.auth_headers = {'Authorization': f'Bearer {token}'}
        test_client.hosted_test = request.param
        yield test_client


def test_routes_require_auth(client):
    for headers in ({}, {'Authorization': 'Bearer wrong-token'}):
        assert client.get(CATALOG, headers=headers).status_code in (401, 403)
        assert client.post(PATH, json=modal_request(), headers=headers).status_code in (401, 403)


@pytest.mark.parametrize('elements,modes', [(2, 4), (8, 3), (64, 6)])
def test_success_direct_equality_and_hashes(client, elements, modes):
    request = modal_request() | {'elements': elements, 'modes': modes}
    response = client.post(PATH, json=request, headers=client.auth_headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['inputs'] == request
    for key, value in evaluate_modal_beam(request).items():
        assert result[key] == value
    assert result['input_sha256'] == sha256_record(request)
    digest = result.pop('evaluation_sha256')
    assert digest == sha256_record(result)
    assert client.get(CATALOG, headers=client.auth_headers).json() == beam_modal_catalog()


@pytest.mark.parametrize('field', list(modal_request()))
def test_all_required(client, field):
    request = modal_request()
    del request[field]
    response = client.post(PATH, json=request, headers=client.auth_headers)
    assert response.status_code == 422
    assert response.json() == {'detail': 'Invalid modal beam request.'}


@pytest.mark.parametrize('change', [
    {'extra': 'do-not-echo'}, {'length_m': True}, {'length_m': 'secret'},
    {'E_pa': None}, {'I_m4': []}, {'mass_per_length_kg_m': {}},
    {'elements': 2.0}, {'modes': True}, {'modes': '3'},
    {'evaluation': 1}, {'property_source': ' '},
    {'applicability_declaration': 'x' * 2001}, {'E_pa': 10**1000},
])
def test_sanitized_structural_errors(client, change):
    response = client.post(PATH, json=modal_request() | change, headers=client.auth_headers)
    assert response.status_code == 422
    assert response.json() == {'detail': 'Invalid modal beam request.'}


@pytest.mark.parametrize('raw', ['{', 'null', '[]', '{"secret":',
                                      '{"length_m": NaN}', '{"length_m": Infinity}'])
def test_malformed_json_constant(client, raw):
    response = client.post(PATH, content=raw, headers=dict(client.auth_headers, **{'Content-Type': 'application/json'}))
    assert response.status_code == 422
    assert response.json() == {'detail': 'Invalid modal beam request.'}


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', '1e9999'])
def test_nonfinite_full_request(client, value):
    raw = json.dumps(modal_request()).replace('2.0', value, 1)
    response = client.post(PATH, content=raw, headers=dict(client.auth_headers, **{'Content-Type': 'application/json'}))
    assert response.status_code == 422
    assert response.json() == {'detail': 'Invalid modal beam request.'}


@pytest.mark.parametrize('change', [
    {'length_m': 0}, {'I_m4': 5e-324}, {'elements': 65},
    {'elements': 2, 'modes': 5}, {'length_m': 1e300}, {'evaluation': 'unsupported'},
])
def test_refusal_mapping_and_hashes(client, change):
    request = modal_request() | change
    response = client.post(PATH, json=request, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    direct = evaluate_modal_beam(request)
    for key, value in direct.items():
        assert result[key] == value
    assert result['outputs'] == result['output_units'] == {}
    assert result['input_sha256'] == sha256_record(request)
    digest = result.pop('evaluation_sha256')
    assert digest == sha256_record(result)


def test_bearer_origin_and_cookie_csrf(client):
    assert client.post(PATH, json=modal_request(), headers=dict(
        client.auth_headers, Origin='https://untrusted.example')).status_code == 200
    if client.hosted_test:
        return
    response = client.post('/api/session', headers=dict(client.auth_headers, Origin='http://testserver'))
    assert response.status_code == 200
    assert client.get(CATALOG).status_code == 200
    for headers in ({}, {'Origin': 'https://untrusted.example'}):
        assert client.post(PATH, json=modal_request(), headers=headers).status_code == 403
    assert client.post(PATH, json=modal_request(), headers={'Origin': 'http://testserver'}).status_code == 200


@pytest.mark.parametrize('suffix', ['/', '/extra', '-extra', 'evil'])
def test_hosted_allowlist_exact(client, suffix):
    if not client.hosted_test:
        return
    assert client.post(PATH + suffix, json=modal_request(), headers=client.auth_headers,
                       follow_redirects=False).status_code == 403
    assert client.get(CATALOG + suffix, headers=client.auth_headers, follow_redirects=False).status_code == 403
