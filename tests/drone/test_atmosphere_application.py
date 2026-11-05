"""Real create_app and SQLite identity tests, no application-module stubs."""
import json

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.drone.standard_atmosphere import MODEL_ID

BODY = {'model_id': MODEL_ID, 'altitude_m': 20000.0, 'altitude_kind': 'geometric'}
PATH = '/api/drone/atmosphere/evaluate'


@pytest.mark.parametrize('hosted', [False, True])
def test_real_app_auth_reference_and_no_project_mutation(tmp_path, hosted):
    app = create_app(Settings(tmp_path, tmp_path / 'jobs.sqlite', 'test-token', None, hosted_mode=hosted))
    with TestClient(app) as client:
        assert client.post(PATH, json=BODY).status_code == 401
        if hosted:
            # Real local test identity, no project grant or organization required.
            app.state.identity.provision('atmosphere@example.test', password='synthetic-test-password')
            token = app.state.identity.login('atmosphere@example.test', 'synthetic-test-password')['token']
        else:
            token = 'test-token'
        headers = {'Authorization': 'Bearer ' + token}
        response = client.post(PATH, json=BODY, headers=headers)
        assert response.status_code == 200
        assert response.json()['aircraft_status'] is None
        assert app.state.projects.repository.page()['projects'] == []
        if hosted:
            assert client.post('/api/drone/screening', json={}, headers=headers).status_code == 403
            assert client.post(PATH+'/', json=BODY, headers=headers, follow_redirects=False).status_code == 403
        for value in ['NaN', 'Infinity', '-Infinity']:
            raw = json.dumps(BODY).replace('20000.0', value)
            rejected = client.post(PATH, content=raw, headers=headers | {'Content-Type': 'application/json'})
            assert rejected.status_code == 422
            assert rejected.json() == {'detail': 'Invalid atmosphere request.'}
        assert client.post(PATH, json=BODY, headers={'Authorization':'Bearer wrong'}).status_code == 401
