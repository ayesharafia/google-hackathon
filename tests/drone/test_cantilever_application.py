import copy
import json

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.drone.cantilever import screen_cantilever
from physimesh.drone.provenance import sha256_record

PATH = '/api/drone/cantilever/screen'


def request(**changes):
    return {
        'evaluation': 'rectangular_cantilever_screening',
        'length_m': 2,
        'width_m': 0.1,
        'depth_m': 0.2,
        'youngs_modulus_pa': 200000000000,
        'tip_load_n': 100,
        'uniform_load_n_m': 10,
        'property_source': 'Synthetic benchmark, not measured material data',
        'applicability_declaration': 'Ideal fixed prismatic rectangular beam only',
        'declared_min_slenderness': 5,
        'declared_max_deflection_ratio': 0.1,
        'declared_max_slope_rad': 0.1,
    } | changes


@pytest.mark.parametrize('hosted', [False, True])
def test_auth_hash_units_refusal_nonmutation(tmp_path, hosted):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'synthetic-token', None,
                              hosted_mode=hosted))
    with TestClient(app) as c:
        assert c.post(PATH, json=request()).status_code == 401
        if hosted:
            app.state.identity.provision('beam@example.test', password='synthetic-fixture-password')
            token = app.state.identity.login('beam@example.test', 'synthetic-fixture-password')['token']
        else:
            token = 'synthetic-token'
        h = {'Authorization': 'Bearer '+token}
        body = request(); before = copy.deepcopy(body)
        response = c.post(PATH, json=body, headers=h)
        assert response.status_code == 200
        r = response.json()
        assert r['schema_version'] == 'cantilever_screening_request_v1'
        assert r['inputs'] == before == body
        assert r['input_sha256'] == sha256_record(body)
        digest = r.pop('evaluation_sha256'); assert digest == sha256_record(r)
        component = screen_cantilever(body)
        assert all(r[k] == v for k, v in component.items())
        assert r['status'] == 'SCREENING_COMPUTED'
        assert r['outputs']['root_shear_magnitude_n'] == 120
        assert r['outputs']['root_moment_magnitude_n_m'] == 220
        assert r['outputs']['tip_deflection_m'] == pytest.approx(0.0000215)
        assert r['output_units']['root_outer_fiber_stress_magnitude_pa'] == 'Pa'
        assert r['evidence_level'] == 'unverified' and r['aircraft_status'] is None and r['feasibility'] is None
        assert c.post(PATH, json=body, headers=h).json() == response.json()
        changed = c.post(PATH, json=request(tip_load_n=101), headers=h).json()
        assert changed['input_sha256'] != r['input_sha256']
        for changes, status in [({'evaluation': 'aircraft_strength'}, 'SOLVER_UNSUPPORTED'),
                                ({'tip_load_n': -1}, 'MODEL_INAPPLICABLE'),
                                ({'declared_min_slenderness': 100}, 'MODEL_INAPPLICABLE'),
                                ({'length_m': 0}, 'MODEL_INAPPLICABLE'),
                                ({'depth_m': 1e-200}, 'MODEL_INAPPLICABLE')]:
            refused = c.post(PATH, json=request(**changes), headers=h)
            assert refused.status_code == 200
            q = refused.json(); assert q['status'] == status
            assert q['outputs'] == {} and q['output_units'] == {}
            assert q['evidence_level'] == 'unverified' and q['feasibility'] is None
        assert c.get(PATH, headers=h).status_code == 405
        assert c.post(PATH+'/extra', json=body, headers=h).status_code in (403, 404)
        assert c.post(PATH, json=body, headers={'Authorization': 'Bearer wrong'}).status_code == 401
        assert app.state.projects.repository.page()['projects'] == []


@pytest.mark.parametrize('field', ['length_m', 'width_m', 'depth_m', 'youngs_modulus_pa',
                                  'tip_load_n', 'uniform_load_n_m', 'declared_min_slenderness',
                                  'declared_max_deflection_ratio', 'declared_max_slope_rad'])
@pytest.mark.parametrize('bad', [True, '2', None, float('nan'), float('inf'), 10**400])
def test_finite_numeric_shape(tmp_path, field, bad):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'synthetic-token', None))
    with TestClient(app) as c:
        result = c.post(PATH, content=json.dumps(request(**{field: bad})),
                        headers={'Authorization': 'Bearer synthetic-token', 'Content-Type': 'application/json'})
        assert result.status_code == 422
        assert result.json() == {'detail': 'Invalid cantilever screening request.'}


def test_exact_shape_declarations_and_csrf(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'synthetic-token', None))
    with TestClient(app) as c:
        h = {'Authorization': 'Bearer synthetic-token'}
        bodies = [request(extra=1), request(property_source=' '), request(applicability_declaration=''),
                  request(property_source='x'*2001), request(applicability_declaration='x'*2001)]
        for key in request():
            body = request(); del body[key]; bodies.append(body)
        for body in bodies:
            result = c.post(PATH, json=body, headers=h)
            assert result.status_code == 422
            assert result.json() == {'detail': 'Invalid cantilever screening request.'}
        for content in ['{broken', 'null', '[]']:
            result = c.post(PATH, content=content, headers=h | {'Content-Type': 'application/json'})
            assert result.status_code == 422
            assert result.json() == {'detail': 'Invalid cantilever screening request.'}
        hostile = request(property_source='<script>fetch(private)</script>',
                          applicability_declaration='  literal declaration  ')
        assert c.post(PATH, json=hostile, headers=h).json()['inputs'] == hostile
        assert c.post('/api/session', headers=h | {'Origin': 'http://testserver'}).status_code == 200
        assert c.post(PATH, json=request()).status_code == 403
        assert c.post(PATH, json=request(), headers={'Origin': 'https://wrong.test'}).status_code == 403
        assert c.post(PATH, json=request(), headers={'Origin': 'http://testserver'}).status_code == 200
