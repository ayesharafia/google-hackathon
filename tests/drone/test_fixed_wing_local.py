"""Fixed-wing integration with the retained local bearer-only application."""
import runpy
from pathlib import Path

from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.drone.provenance import sha256_record

request = runpy.run_path(str(Path(__file__).with_name('test_fixed_wing.py')))['request']


def test_local_fixed_wing_button_contract(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path / 'jobs.sqlite', 'synthetic-token', None))
    headers = {'Authorization': 'Bearer synthetic-token'}
    path = '/api/drone/fixed-wing/screen'
    with TestClient(app) as client:
        for endpoint in ['/api/drone/fixed-wing/access', path]:
            assert client.get(endpoint).status_code == 401
            assert client.get(endpoint, headers={'Authorization': 'Bearer wrong'}).status_code == 401
        assert client.get('/api/drone/fixed-wing/access', headers=headers).json() == {'connected': True}
        assert client.post(path, json=request()).status_code == 401
        response = client.post(path, json=request(), headers=headers)
        assert response.status_code == 200
        result = response.json()
        assert result['status'] == 'SCREENING_COMPUTED'
        assert result['outputs']['lift_n'] == 7500
        assert result['inputs'] == request()
        assert result['input_sha256'] == sha256_record(request())
        digest = result.pop('evaluation_sha256')
        assert digest == sha256_record(result)
        assert result['aircraft_status'] is None and result['feasibility'] is None
        refused = client.post(path, json=request(span_efficiency=0), headers=headers).json()
        assert refused['status'] == 'MODEL_INAPPLICABLE' and refused['outputs'] == {}
        assert client.post(path, json=request(airspeed_m_s=True), headers=headers).status_code == 422
        assert app.state.projects.repository.list_projects() == []
        assert client.get('/web/simple-workflow.html').status_code == 200


def test_token_free_local_calculation(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path / 'jobs.sqlite', '', None, local_no_auth=True))
    with TestClient(app, base_url='http://127.0.0.1:8768') as client:
        assert client.get('/api/drone/fixed-wing/access').json() == {'connected': True}
        response = client.post('/api/drone/fixed-wing/screen', json=request(),
                               headers={'Origin': 'http://127.0.0.1:8768'})
        assert response.status_code == 200
        assert response.json()['outputs']['lift_n'] == 7500
        assert client.post('/api/drone/fixed-wing/screen', json=request(airspeed_m_s=True)).status_code == 422
        assert client.get('/api/drone/fixed-wing/access', headers={'Origin': 'https://elsewhere.test'}).status_code == 403
        assert client.get('/api/drone/fixed-wing/access', headers={'Host': 'elsewhere.test'}).status_code == 403
        assert client.get('/api/drone/fixed-wing/access', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
