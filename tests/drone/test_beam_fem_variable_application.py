"""HTTP contract tests for authenticated variable-inertia beam evaluation."""
import pytest
from fastapi.testclient import TestClient

PATH = '/api/drone/beam-fem-variable/evaluate'


@pytest.fixture
def request_data():
    return {
        'evaluation': 'variable_beam_fem_experimental',
        'length_m': 2.0, 'E_pa': 70e9,
        'second_moments_m4': [1e-6, 1.25e-6, 1.5e-6],
        'nodes_m': [0.0, 1.0, 2.0], 'outer_fibre_m': 0.01,
        'tip_force_n': 10.0, 'uniform_load_n_m': 0.0,
        'ramp_load_root_n_m': 0.0, 'ramp_load_tip_n_m': 0.0,
        'tip_moment_n_m': 0.0,
        'probes': [{'element_index': 0, 'local_coordinate': 0.5},
                   {'element_index': 1, 'local_coordinate': 1.0}],
        'property_source': 'Unverified supplier values',
        'applicability_declaration': 'Experimental static cantilever only',
    }


@pytest.fixture(params=[False, True], ids=['local', 'hosted'])
def client(tmp_path, request):
    from physimesh.api.app import create_app
    from physimesh.api.settings import Settings

    app = create_app(Settings(tmp_path, tmp_path / 'jobs.sqlite', 'synthetic-token', None,
                              hosted_mode=request.param))
    token = 'synthetic-token'
    if request.param:
        app.state.identity.provision(
            'beam@example.test', password='synthetic-fixture-password')
        token = app.state.identity.login(
            'beam@example.test', password='synthetic-fixture-password')['token']
    with TestClient(app) as test_client:
        test_client.valid_test_token = token
        test_client.hosted_test = bool(request.param)
        yield test_client


@pytest.fixture
def headers(client):
    return {'Authorization': f'Bearer {client.valid_test_token}'}


def test_auth_required(client, request_data):
    for auth in ({}, {'Authorization': 'Bearer wrong-token'}):
        response = client.post(PATH, json=request_data, headers=auth)
        assert response.status_code in (401, 403)


def test_success_and_deterministic_hashes(client, request_data, headers):
    first = client.post(PATH, json=request_data, headers=headers)
    assert first.status_code == 200, first.text
    result = first.json()
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    assert result['schema_version'] == 'variable_beam_request_v1'
    assert result['inputs'] == request_data
    from physimesh.drone.provenance import sha256_record
    assert result['input_sha256'] == sha256_record(result['inputs'])
    unhashed = dict(result)
    evaluation_hash = unhashed.pop('evaluation_sha256')
    assert evaluation_hash == sha256_record(unhashed)
    assert client.post(PATH, json=request_data, headers=headers).json() == result
    from physimesh.drone.beam_fem_variable_request import evaluate_variable_beam
    direct = evaluate_variable_beam(request_data)
    for key, value in direct.items():
        assert result[key] == value


@pytest.mark.parametrize('change', [
    {'extra': 1}, {'length_m': '2'}, {'length_m': True}, {'E_pa': None},
    {'nodes_m': [0, '1', 2]}, {'second_moments_m4': [1e-6] * 66},
    {'probes': []},
    {'probes': [{'element_index': 0, 'local_coordinate': 0}] * 129},
    {'probes': [{'element_index': 0.0, 'local_coordinate': 0.5}]},
    {'probes': [{'element_index': True, 'local_coordinate': 0.5}]},
    {'probes': [{'element_index': 0, 'local_coordinate': '0.5'}]},
    {'probes': [{'element_index': 0, 'local_coordinate': 0.5, 'extra': 1}]},
    {'probes': [{'element_index': 0}]},
    {'property_source': 'x' * 2001},
])
def test_structural_errors_are_generic(client, request_data, headers, change):
    request_data.update(change)
    response = client.post(PATH, json=request_data, headers=headers)
    assert response.status_code == 422
    assert response.json() == {'detail': 'Invalid variable beam request.'}


@pytest.mark.parametrize('field', [
    'evaluation', 'length_m', 'E_pa', 'nodes_m', 'second_moments_m4',
    'outer_fibre_m', 'tip_force_n', 'uniform_load_n_m',
    'ramp_load_root_n_m', 'ramp_load_tip_n_m', 'tip_moment_n_m',
    'probes', 'property_source', 'applicability_declaration',
])
def test_required_fields(client, request_data, headers, field):
    del request_data[field]
    response = client.post(PATH, json=request_data, headers=headers)
    assert response.status_code == 422
    assert response.json() == {'detail': 'Invalid variable beam request.'}


@pytest.mark.parametrize('change', [
    {'length_m': -2.0}, {'E_pa': 0.0},
    {'nodes_m': [0, 1, 1]}, {'second_moments_m4': [1e-6, 1e-6]},
    {'probes': [{'element_index': 42, 'local_coordinate': 0.5}]},
])
def test_core_domain_refusal_is_200(client, request_data, headers, change):
    request_data.update(change)
    response = client.post(PATH, json=request_data, headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['status'] == 'MODEL_INAPPLICABLE'
    assert result['outputs'] == {}
    assert result['output_units'] == {}


def test_authenticated_bearer_not_cookie_csrf(client, request_data, headers):
    response = client.post(
        PATH, json=request_data,
        headers=dict(headers, Origin='https://untrusted.example'))
    assert response.status_code == 200, response.text


def test_cookie_csrf_requires_same_origin(client, request_data, headers):
    if client.hosted_test:
        pytest.skip(
            'This fixture has no hosted browser sign-in provider; hosted bearer auth is covered separately')
    response = client.post(
        '/api/session', headers=dict(headers, Origin='http://testserver'))
    assert response.status_code == 200, response.text
    assert response.cookies, 'Session creation must set a cookie'
    response = client.post(PATH, json=request_data)
    assert response.status_code == 403, response.text
    response = client.post(
        PATH, json=request_data, headers={'Origin': 'https://untrusted.example'})
    assert response.status_code == 403, response.text
    response = client.post(
        PATH, json=request_data, headers={'Origin': 'http://testserver'})
    assert response.status_code == 200, response.text


@pytest.mark.parametrize('suffix', ['/', '/extra', '-extra', 'evil'])
def test_hosted_allowlist_is_exact(client, request_data, headers, suffix):
    if not client.hosted_test:
        pytest.skip('Exact allowlist applies only in hosted mode')
    response = client.post(
        PATH + suffix, json=request_data, headers=headers, follow_redirects=False)
    assert response.status_code == 403, response.text
