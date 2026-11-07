"""Additional strict-input, isolation, and browser-session beam contracts."""

import json
import math
from copy import deepcopy
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.drone.beam_fem_variable import (
    evaluate_variable_solution,
    solve_beam_variable,
)
from physimesh.drone.beam_fem_variable_request import evaluate_variable_beam
from physimesh.platform.identity import token_hash

PATH = '/api/drone/beam-fem-variable/evaluate'
SCALARS = (
    'length_m', 'E_pa', 'outer_fibre_m', 'tip_force_n', 'uniform_load_n_m',
    'ramp_load_root_n_m', 'ramp_load_tip_n_m', 'tip_moment_n_m',
)
NONFINITE = [math.nan, math.inf, -math.inf, 10**400]
INVALID_NUMBERS = NONFINITE + [True, '1.0', None]
NUMBER_IDS = ['nan', 'positive-inf', 'negative-inf', 'huge-int', 'bool', 'numeric-string', 'none']


@pytest.fixture
def request_data():
    """A complete request, independent of fixtures in other test modules."""
    return {
        'evaluation': 'variable_beam_fem_experimental',
        'length_m': 2.0,
        'E_pa': 70e9,
        'second_moments_m4': [1e-6, 1.25e-6, 1.5e-6],
        'nodes_m': [0.0, 1.0, 2.0],
        'outer_fibre_m': 0.01,
        'tip_force_n': 10.0,
        'uniform_load_n_m': 2.0,
        'ramp_load_root_n_m': +1.0,
        'ramp_load_tip_n_m': 3.0,
        'tip_moment_n_m': 0.5,
        'probes': [
            {'element_index': 0, 'local_coordinate': 0.5},
            {'element_index': 0, 'local_coordinate': 1.0},
            {'element_index': 1, 'local_coordinate': 0.0},
            {'element_index': 1, 'local_coordinate': 1.0},
        ],
        'property_source': 'Synthetic unverified variable inertia fixture',
        'applicability_declaration': 'Experimental static cantilever only',
    }


@pytest.fixture
def local_client(tmp_path):
    app = create_app(Settings(tmp_path, tmp_path / 'jobs.sqlite', 'synthetic-token', None))
    with TestClient(app) as client:
        yield client


def post_raw(client, payload):
    # TestClient's json= encoder refuses nonfinite floats before reaching the API.
    return client.post(
        PATH, content=json.dumps(payload),
        headers={'Authorization': 'Bearer synthetic-token', 'Content-Type': 'application/json'},
    )


def assert_generic_422(response):
    assert response.status_code == 422, response.text
    assert response.json() == {'detail': 'Invalid variable beam request.'}


def assert_refused(result, status='MODEL_INAPPLICABLE'):
    assert result['status'] == status
    assert result['outputs'] == {}
    assert result['output_units'] == {}
    assert result['reasons']


@pytest.mark.parametrize('field', SCALARS)
@pytest.mark.parametrize('value', INVALID_NUMBERS, ids=NUMBER_IDS)
def test_api_all_scalar_finite_shape_matrix(local_client, request_data, field, value):
    request_data[field] = value
    assert_generic_422(post_raw(local_client, request_data))


@pytest.mark.parametrize('field', ['nodes_m', 'second_moments_m4'])
@pytest.mark.parametrize('value', NONFINITE, ids=NUMBER_IDS[:4])
def test_array_nonfinite_rejected(local_client, request_data, field, value):
    request_data[field][1] = value
    assert_generic_422(post_raw(local_client, request_data))
    assert_refused(evaluate_variable_beam(request_data))


@pytest.mark.parametrize('field', ['element_index', 'local_coordinate'])
@pytest.mark.parametrize('value', NONFINITE, ids=NUMBER_IDS[:4])
def test_probe_nonfinite_rejected(local_client, request_data, field, value):
    request_data['probes'][1][field] = value
    assert_generic_422(post_raw(local_client, request_data))
    assert_refused(evaluate_variable_beam(request_data))


@pytest.mark.parametrize('index', [0, 1, 2, 3])
def test_nested_extra_fields_rejected(local_client, request_data, index):
    request_data['probes'][index]['extra'] = {'nested': ['synthetic']}
    assert_generic_422(post_raw(local_client, request_data))
    assert_refused(evaluate_variable_beam(request_data))


def test_unsupported_evaluation_is_200(local_client, request_data):
    request_data['evaluation'] = 'unsupported-synthetic-evaluation'
    response = post_raw(local_client, request_data)
    assert response.status_code == 200, response.text
    assert_refused(response.json(), 'SOLVER_UNSUPPORTED')


def test_variable_inertia_exact_core_parity(local_client, request_data):
    original = deepcopy(request_data)
    solution = solve_beam_variable(
        **{field: request_data[field] for field in SCALARS},
        nodes_m=tuple(request_data['nodes_m']),
        second_moments_m4=tuple(request_data['second_moments_m4']),
    )
    expected = {
        'elements': solution.n,
        'nodes_m': list(solution.nodes),
        'second_moments_m4': list(solution.second_moments_m4),
        'displacements_m': list(solution.displacements),
        'rotations_rad': list(solution.rotations),
        'root_force_n': solution.root_force_n,
        'root_moment_nm': solution.root_moment_nm,
        'normalized_linear_residual': solution.normalized_linear_residual,
        'probes': [
            {**probe, **asdict(evaluate_variable_solution(
                solution, probe['element_index'], probe['local_coordinate']))}
            for probe in request_data['probes']
        ],
    }
    direct = evaluate_variable_beam(request_data)
    assert direct['status'] == 'COMPUTED_EXPERIMENTAL'
    assert direct['outputs'] == expected
    response = post_raw(local_client, request_data)
    assert response.status_code == 200, response.text
    assert response.json()['outputs'] == expected
    assert request_data == original


class DictSubclass(dict):
    pass


class ListSubclass(list):
    pass


class FloatSubclass(float):
    pass


class IntSubclass(int):
    pass


class StrSubclass(str):
    pass


SUBCLASS_CASES = (
    ['request', 'probe', 'probes', 'nodes_m', 'second_moments_m4']
    + [f'{field}:{kind}' for field in SCALARS for kind in ('float', 'int')]
    + [f'{field}:{kind}' for field in ('nodes_m', 'second_moments_m4')
       for kind in ('float-item', 'int-item')]
    + ['probe-index', 'probe-coordinate-float', 'probe-coordinate-int',
       'evaluation', 'property_source', 'applicability_declaration']
)


@pytest.mark.parametrize('case', SUBCLASS_CASES)
def test_direct_rejects_builtin_subclasses(request_data, case):
    if case == 'request':
        request_data = DictSubclass(request_data)
    elif case == 'probe':
        request_data['probes'][0] = DictSubclass(request_data['probes'][0])
    elif case in ('probes', 'nodes_m', 'second_moments_m4'):
        request_data[case] = ListSubclass(request_data[case])
    elif ':' in case:
        field, kind = case.split(':')
        if kind.endswith('-item'):
            request_data[field][0] = FloatSubclass(request_data[field][0]) if kind == 'float-item' else IntSubclass(1)
        else:
            request_data[field] = FloatSubclass(request_data[field]) if kind == 'float' else IntSubclass(1)
    elif case == 'probe-index':
        request_data['probes'][0]['element_index'] = IntSubclass(0)
    elif case.startswith('probe-coordinate'):
        request_data['probes'][0]['local_coordinate'] = FloatSubclass(0.5) if case.endswith('float') else IntSubclass(1)
    else:
        request_data[case] = StrSubclass(request_data[case])
    assert_refused(evaluate_variable_beam(request_data))


@pytest.mark.parametrize('value', [None, True, 1, 1.0, [], {}, StrSubclass('variable_beam_fem_experimental')])
def test_nonstring_evaluation_direct_is_model_inapplicable(request_data, value):
    request_data['evaluation'] = value
    assert_refused(evaluate_variable_beam(request_data))


def test_returned_outputs_and_units_do_not_leak_between_calls(local_client, request_data):
    original = deepcopy(request_data)
    baseline = deepcopy(evaluate_variable_beam(request_data))
    assert baseline['status'] == 'COMPUTED_EXPERIMENTAL'
    first = evaluate_variable_beam(request_data)
    first['outputs']['nodes_m'][0] = -999
    first['outputs']['second_moments_m4'].clear()
    first['outputs']['displacements_m'].append(999)
    first['outputs']['rotations_rad'].clear()
    first['outputs']['probes'][0]['deflection_m'] = -999
    first['outputs']['probes'].append({'extra': True})
    first['outputs']['extra'] = 'mutated'
    first['output_units']['nodes_m'] = 'wrong'
    first['output_units']['probes']['deflection_m'] = 'wrong'
    first['output_units']['probes']['extra'] = 'wrong'
    assert evaluate_variable_beam(request_data) == baseline
    assert request_data == original
    response = post_raw(local_client, request_data)
    assert response.status_code == 200, response.text
    http_baseline = deepcopy(response.json())
    returned = response.json()
    returned['outputs']['probes'][0].clear()
    returned['output_units']['probes'].clear()
    assert post_raw(local_client, request_data).json() == http_baseline


def test_hosted_browser_cookie_csrf_and_bearer_separation(tmp_path, request_data):
    app = create_app(Settings(
        tmp_path, tmp_path / 'jobs.sqlite', 'synthetic-token', None,
        hosted_mode=True,
        hosted_signin_issuer='https://idp.example.test',
        hosted_signin_discovery_url='https://idp.example.test/discovery',
        hosted_signin_client_id='synthetic-client',
        hosted_signin_origin='https://testserver',
    ))
    with TestClient(app, base_url='https://testserver') as c:
        app.state.identity.provision(
            'beam-cookie@example.test', password='synthetic-fixture-password')
        token = app.state.identity.login(
            'beam-cookie@example.test', password='synthetic-fixture-password')['token']
        # Only the browser marker is synthetic. Authentication and CSRF remain real.
        with app.state.metadata.connection(write=True) as db:
            db.execute('INSERT INTO hosted_browser_sessions VALUES(?)', (token_hash(token),))
        c.cookies.set('physicore_hosted_session', token)
        response = c.post(PATH, json=request_data)
        assert response.status_code == 403, response.text
        response = c.post(PATH, json=request_data, headers={'Origin': 'https://wrong.example.test'})
        assert response.status_code == 403, response.text
        response = c.post(PATH, json=request_data, headers={'Origin': 'https://testserver'})
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'COMPUTED_EXPERIMENTAL'
        assert app.state.projects.repository.page()['projects'] == []
        c.cookies.clear()
        response = c.post(PATH, json=request_data, headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 401, response.text
