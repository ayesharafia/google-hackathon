import copy
import json

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.drone.hover_bemt_request import evaluate_hover_bemt
from physimesh.drone.provenance import sha256_record

PATH = '/api/drone/hover-bemt/evaluate'
NUMERICS = ('radius_m', 'angular_speed_rad_s', 'density_kg_m3', 'blade_count',
            'chord_m', 'lift_curve_slope_per_rad', 'profile_drag_coefficient',
            'pitch_tip_rad', 'root_cutout_fraction', 'annuli', 'pitch_root_rad')


def request(law='constant', **changes):
    return {
        'evaluation': 'isolated_hover_bemt_experimental', 'radius_m': 0.5,
        'angular_speed_rad_s': 300.0, 'density_kg_m3': 1.225, 'blade_count': 2,
        'chord_m': 0.04, 'lift_curve_slope_per_rad': 5.7,
        'profile_drag_coefficient': 0.01, 'pitch_tip_rad': 0.12,
        'root_cutout_fraction': 0.2, 'twist_law': law, 'annuli': 8,
        'pitch_root_rad': 0.16 if law == 'linear' else None,
        'property_source': 'Supplier values, unverified',
        'applicability_declaration': 'Experimental isolated hover only',
    } | changes


@pytest.mark.parametrize('hosted', [False, True])
@pytest.mark.parametrize('law', ['constant', 'hyperbolic', 'linear'])
def test_auth_hash_component_refusal_nonmutation(tmp_path, hosted, law):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'synthetic-token', None,
                              hosted_mode=hosted))
    with TestClient(app) as c:
        assert c.post(PATH, json=request(law)).status_code == 401
        if hosted:
            app.state.identity.provision('hover@example.test', password='synthetic-fixture-password')
            token = app.state.identity.login('hover@example.test', 'synthetic-fixture-password')['token']
        else:
            token = 'synthetic-token'
        h = {'Authorization': 'Bearer '+token}
        body = request(law)
        before = copy.deepcopy(body)
        response = c.post(PATH, json=body, headers=h)
        assert response.status_code == 200
        r = response.json()
        assert r['schema_version'] == 'hover_bemt_request_v1'
        assert r['inputs'] == before == body
        assert r['input_sha256'] == sha256_record(body)
        digest = r.pop('evaluation_sha256')
        assert digest == sha256_record(r)
        component = json.loads(json.dumps(evaluate_hover_bemt(body)))
        assert all(r[k] == v for k, v in component.items())
        assert r['status'] == 'COMPUTED_EXPERIMENTAL'
        assert r['physical_validation'] == 'NOT_ESTABLISHED'
        assert r['evidence_level'] == 'unverified' and r['feasibility'] is None
        assert r['aircraft_status'] is None and r['limitations'] and r['sources']
        for key in ('radial_fraction', 'inflow_ratio', 'pitch_rad',
                    'approx_inflow_angle_rad', 'approx_angle_of_attack_rad'):
            assert type(r['outputs'][key]) is list and len(r['outputs'][key]) == body['annuli']
        assert c.post(PATH, json=body, headers=h).json() == response.json()
        changed = c.post(PATH, json=request(law, radius_m=0.6), headers=h).json()
        assert changed['input_sha256'] != r['input_sha256']
        assert changed['evaluation_sha256'] != digest
        for changes, status in [({'evaluation': 'aircraft_strength'}, 'SOLVER_UNSUPPORTED'),
                                ({'radius_m': 0}, 'MODEL_INAPPLICABLE'),
                                ({'root_cutout_fraction': 0}, 'MODEL_INAPPLICABLE'),
                                ({'twist_law': 'unknown'}, 'MODEL_INAPPLICABLE')]:
            refused = c.post(PATH, json=request(law, **changes), headers=h)
            assert refused.status_code == 200
            q = refused.json()
            assert q['status'] == status
            assert q['outputs'] == {} and q['output_units'] == {} and q['reasons']
            assert q['evidence_level'] == 'unverified' and q['feasibility'] is None
        assert c.get(PATH, headers=h).status_code == 405
        assert c.post(PATH, json=body, headers={'Authorization': 'Bearer wrong'}).status_code == 401
        if hosted:
            for suffix in ('/', '/extra', '-extra', 'evil'):
                assert c.post(PATH+suffix, json=body, headers=h, follow_redirects=False).status_code == 403
        assert app.state.projects.repository.page()['projects'] == []


@pytest.mark.parametrize('field,bad', [
    (field, bad) for field in NUMERICS
    for bad in (True, False, '2', None, float('nan'), float('inf'), -float('inf'), 10**400)
    if field != 'pitch_root_rad' or bad is not None
] + [(field, bad) for field in ('annuli', 'blade_count') for bad in (2.0, 2.5)])
def test_finite_numeric_shape(tmp_path, field, bad):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'synthetic-token', None))
    with TestClient(app) as c:
        result = c.post(PATH, content=json.dumps(request('linear', **{field: bad})),
                        headers={'Authorization': 'Bearer synthetic-token', 'Content-Type': 'application/json'})
        assert result.status_code == 422
        assert result.json() == {'detail': 'Invalid hover BEMT request.'}


def test_exact_shape_declarations_and_csrf(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path/'jobs.sqlite', 'synthetic-token', None))
    with TestClient(app) as c:
        h = {'Authorization': 'Bearer synthetic-token'}
        bodies = [request(extra=1)]
        for field in ('property_source', 'applicability_declaration'):
            bodies.extend(request(**{field: bad}) for bad in ('', ' \t\n ', 'x'*2001, None, True, 7, [], {}))
        for field in ('evaluation', 'twist_law'):
            bodies.extend(request(**{field: bad}) for bad in (None, True, 7, [], {}))
        for key in request():
            body = request()
            del body[key]
            bodies.append(body)
        for body in bodies:
            result = c.post(PATH, json=body, headers=h)
            assert result.status_code == 422
            assert result.json() == {'detail': 'Invalid hover BEMT request.'}
        for content in ('{broken', 'null', '[]', 'true', '1', '"text"'):
            result = c.post(PATH, content=content, headers=h | {'Content-Type': 'application/json'})
            assert result.status_code == 422
            assert result.json() == {'detail': 'Invalid hover BEMT request.'}
        hostile = request(property_source='<script>fetch(private)</script>',
                          applicability_declaration='  literal declaration  ')
        assert c.post(PATH, json=hostile, headers=h).json()['inputs'] == hostile
        assert c.post('/api/session', headers=h | {'Origin': 'http://testserver'}).status_code == 200
        assert c.post(PATH, json=request()).status_code == 403
        assert c.post(PATH, json=request(), headers={'Origin': 'https://wrong.test'}).status_code == 403
        assert c.post(PATH, json=request(), headers={'Origin': 'http://testserver'}).status_code == 200
