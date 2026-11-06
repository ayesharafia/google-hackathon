import copy
import json

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.drone.provenance import sha256_record

PATH = '/api/drone/dependencies/plan'


def request():
    port = {'name': 'value', 'unit': 'N', 'frame': 'beam_axis'}
    return {'graph': {'models': [{'id': 'A', 'inputs': [], 'outputs': [port]},
                                 {'id': 'B', 'inputs': [port], 'outputs': [port]}],
                      'connections': [{'from_model': 'A', 'from_port': 'value',
                                       'to_model': 'B', 'to_port': 'value'}]},
            'targets': [{'model': 'B', 'port': 'value'}]}


@pytest.mark.parametrize('hosted', [False, True])
def test_auth_nonmutation_hash_and_refusals(tmp_path, hosted):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'synthetic-token', None,
                              hosted_mode=hosted))
    with TestClient(app) as client:
        body = request()
        before = copy.deepcopy(body)
        assert client.post(PATH, json=body).status_code == 401
        if hosted:
            app.state.identity.provision('plan@example.test', password='synthetic-fixture-password')
            token = app.state.identity.login('plan@example.test', 'synthetic-fixture-password')['token']
        else:
            token = 'synthetic-token'
        headers = {'Authorization': 'Bearer '+token}
        response = client.post(PATH, json=body, headers=headers)
        assert response.status_code == 200
        result = response.json()
        assert result['status'] == 'PLAN_PROPOSED' and result['order'] == ['A', 'B']
        assert result['inputs'] == body == before
        assert result['input_sha256'] == sha256_record(body)
        assert result.pop('evaluation_sha256') == sha256_record(result)
        assert result['execution_authorized'] is False and result['evidence_level'] == 'unverified'
        assert 'no_physical_validation' in result['limitations']
        body['graph']['connections'].clear()
        refused = client.post(PATH, json=body, headers=headers).json()
        assert refused['status'] == 'INPUT_INCOMPLETE' and refused['order'] == []
        assert refused['execution_authorized'] is False
        assert client.post(PATH, json=before, headers={'Authorization': 'Bearer wrong'}).status_code == 401
        assert client.get(PATH, headers=headers).status_code == 405
        assert app.state.projects.repository.page()['projects'] == []


@pytest.mark.parametrize('mutate', [
    lambda b: b.update(extra=True),
    lambda b: b['graph'].update(extra=True),
    lambda b: b['graph']['models'][0].update(extra=True),
    lambda b: b['graph']['models'][0]['outputs'][0].update(extra=True),
    lambda b: b['graph']['connections'][0].update(extra=True),
    lambda b: b['targets'][0].update(extra=True),
    lambda b: b.update(targets=[]),
    lambda b: b.update(targets=[{'model': True, 'port': 'value'}]),
    lambda b: b['graph']['models'][0].update(id=7),
    lambda b: b['graph']['models'][0]['outputs'][0].update(unit='x'*81),
    lambda b: b['graph']['models'][0].update(inputs=[{}]*129),
    lambda b: b['graph'].update(models=[{}]*129),
    lambda b: b['graph'].update(connections=[{}]*4097),
    lambda b: b.update(targets=[{}]*129),
])
def test_strict_nested_shape_and_sanitized_errors(tmp_path, mutate):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'synthetic-token', None))
    body = request()
    mutate(body)
    with TestClient(app) as client:
        response = client.post(PATH, content=json.dumps(body),
                               headers={'Authorization': 'Bearer synthetic-token', 'Content-Type': 'application/json'})
        assert response.status_code == 422
        assert response.json() == {'detail': 'Invalid dependency plan request.'}


@pytest.mark.parametrize('raw', ['{broken', 'null', '[]', 'true'])
def test_invalid_json_sanitized(tmp_path, raw):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'synthetic-token', None))
    with TestClient(app) as client:
        response = client.post(PATH, content=raw, headers={'Authorization': 'Bearer synthetic-token',
                                                          'Content-Type': 'application/json'})
        assert response.status_code == 422
        assert response.json() == {'detail': 'Invalid dependency plan request.'}


def test_session_csrf_and_text_is_metadata(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'synthetic-token', None))
    with TestClient(app) as client:
        headers = {'Authorization': 'Bearer synthetic-token'}
        assert client.post('/api/session', headers=headers).status_code == 200
        assert client.post(PATH, json=request()).status_code == 403
        body = request()
        for model in body['graph']['models']:
            for port in model['inputs']+model['outputs']:
                port['frame'] = '<script>not executed</script>'
        response = client.post(PATH, json=body, headers={'Origin': 'http://testserver'})
        assert response.status_code == 200
        assert response.json()['inputs'] == body
        assert response.json()['execution_authorized'] is False


@pytest.mark.parametrize('field', ['unit', 'frame'])
@pytest.mark.parametrize('codepoint', [0xD800, 0xDFFF])
def test_invalid_unicode_scalar_raw_json_is_sanitized_before_hash(tmp_path, field, codepoint):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'synthetic-token', None))
    body = request()
    for model in body['graph']['models']:
        for port in model['inputs']+model['outputs']:
            port[field] = chr(codepoint)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(PATH, content=json.dumps(body, ensure_ascii=True),
                               headers={'Authorization': 'Bearer synthetic-token', 'Content-Type': 'application/json'})
        assert response.status_code == 422
        assert response.json() == {'detail': 'Invalid dependency plan request.'}


@pytest.mark.parametrize('field', ['unit', 'frame'])
def test_valid_nonbmp_metadata_preserved_and_hashed(tmp_path, field):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'synthetic-token', None))
    body = request()
    for model in body['graph']['models']:
        for port in model['inputs']+model['outputs']:
            port[field] = 'declared_\U0001f680'
    with TestClient(app) as client:
        response = client.post(PATH, content=json.dumps(body, ensure_ascii=True),
                               headers={'Authorization': 'Bearer synthetic-token', 'Content-Type': 'application/json'})
        assert response.status_code == 200
        result = response.json()
        assert result['status'] == 'PLAN_PROPOSED' and result['inputs'] == body
        assert result['input_sha256'] == sha256_record(body)
        assert result.pop('evaluation_sha256') == sha256_record(result)
