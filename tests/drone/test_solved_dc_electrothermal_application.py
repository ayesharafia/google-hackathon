"""Actual mission HTTP contract, bounded parsing, and inherited authorization."""

import json
from copy import deepcopy
from unittest.mock import Mock

import anyio
import pytest

from physimesh.api import solved_dc_electrothermal as api
from physimesh.drone import solved_dc_electrothermal as mission
from physimesh.drone.provenance import sha256_record

from . import test_solved_dc_electrothermal as mission_tests
from . import test_solved_dc_power as point_tests
from .test_model_graph_application import client as client  # noqa: PLC0414

PATH = '/api/drone/solved-dc-electrothermal/evaluate'
CATALOG = '/api/drone/solved-dc-electrothermal/catalog'
LIMIT = 131072
INVALID = {'detail': 'Invalid solved DC electrothermal request.'}


@pytest.fixture
def mission_request():
    return mission_tests.mission_request.__wrapped__(point_tests.bridge_request.__wrapped__())


def spy_models(monkeypatch):
    spies = []
    for owner, name in ((api.mission, 'evaluate_solved_dc_electrothermal'),
                        (mission.dp, 'evaluate_solved_dc_power'), (mission.th, 'screen_thermal')):
        spy = Mock(wraps=getattr(owner, name))
        monkeypatch.setattr(owner, name, spy)
        spies.append(spy)
    return spies


def assert_result(response, direct, body):
    assert response.status_code == 200, response.text
    result = response.json()
    if 'request_sha256' in direct:
        digest = result.pop('evaluation_sha256')
        assert digest == sha256_record(result)
        assert result.pop('input_sha256') == direct['request_sha256'] == sha256_record(body)
    assert result == direct
    return result


def test_actual_equality_hashes_and_calls(client, mission_request, monkeypatch):
    direct = mission.evaluate_solved_dc_electrothermal(mission_request)
    spies = spy_models(monkeypatch)
    result = assert_result(client.post(PATH, json=mission_request, headers=client.auth_headers),
                           direct, mission_request)
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    assert result['outputs']['mission_state'] == 'COMPUTED_FROM_RESIDUAL_MET_SEGMENTS'
    assert [spy.call_count for spy in spies] == [1, 2, 1]


def test_catalog(client):
    response = client.get(CATALOG, headers=client.auth_headers)
    assert response.status_code == 200
    catalog = response.json()
    assert catalog['evaluation'] == mission.EVALUATION
    assert catalog['root_fields_exact'] is True
    assert set(catalog['required_root']) == {
        'evaluation', 'usable_energy_j', 'reserve_fraction', 'thermal_body', 'segments'}
    limits = catalog['limits']
    assert (limits['body_bytes'], limits['json_depth'], limits['json_values']) == (LIMIT, 12, 65536)
    assert limits['segments'] == {'minimum': 1, 'maximum': 16}
    assert limits['combined_annuli'] == 32768
    point = limits['per_point']
    assert (point['json_depth'], point['json_values']) == (10, 49152)
    assert (point['solver_json_values'], point['motor_json_values']) == (32768, 4096)
    assert point['combined_annuli'] == 32768
    assert catalog['evidence_level'] == 'unverified'
    for key in ('physical_validation', 'numerical_qualification', 'runtime_identity'):
        assert catalog[key] == 'NOT_ESTABLISHED'
    assert catalog['feasibility'] is catalog['aircraft_status'] is None


def test_actual_unmet_prefix(client, mission_request, monkeypatch):
    mission_request['segments'].append({**deepcopy(mission_request['segments'][1]), 'id': 'third'})
    mission_request['segments'][1]['point']['solve'].update(
        max_evaluations=2, required_net_force_body_n=[1e9, 0, 0])
    direct = mission.evaluate_solved_dc_electrothermal(mission_request)
    spies = spy_models(monkeypatch)
    result = assert_result(client.post(PATH, json=mission_request, headers=client.auth_headers),
                           direct, mission_request)
    out, units = result['outputs'], result['output_units']
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    assert out['mission_state'] == 'STOPPED_AT_UNMET_SEGMENT'
    assert [row['segment_id'] for row in out['power_segments']] == ['first', 'second']
    assert out['energy'] is out['thermal'] is units['energy'] is units['thermal'] is None
    assert result['transfers'] == []
    assert [spy.call_count for spy in spies] == [1, 2, 0]


@pytest.mark.parametrize('defect', ['schema', 'last_segment'])
def test_scientific_invalid_200_before_models(client, mission_request, monkeypatch, defect):
    if defect == 'schema':
        mission_request['PRIVATE_SECRET'] = True
    else:
        mission_request['segments'][-1]['thermal']['ambient_temperature_k'] = True
    direct = mission.evaluate_solved_dc_electrothermal(mission_request)
    spies = spy_models(monkeypatch)
    result = assert_result(client.post(PATH, json=mission_request, headers=client.auth_headers),
                           direct, mission_request)
    assert result['status'] == 'GRAPH_INVALID'
    assert result['stages'] == result['transfers'] == []
    assert result['outputs'] == result['output_units'] == {}
    assert [spy.call_count for spy in spies] == [1, 0, 0]


@pytest.mark.parametrize('raw', [b'{"x":1,"x":2}', b'{"x":{"a":1,"a":2}}',
                                 b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}',
                                 b'{"x":"\xff"}', b'[]', b'{"PRIVATE_SECRET":'])
def test_parse_refusals(client, monkeypatch, raw):
    spies = spy_models(monkeypatch)
    response = client.post(PATH, content=raw, headers=client.auth_headers)
    assert response.status_code == 422
    assert response.json() == INVALID
    assert [spy.call_count for spy in spies] == [0, 0, 0]


def test_auth_for_both_routes(client, mission_request, monkeypatch):
    spies = spy_models(monkeypatch)
    for headers in ({}, {'Authorization': 'Bearer wrong-token'}):
        assert client.get(CATALOG, headers=headers).status_code == 401
        assert client.post(PATH, json=mission_request, headers=headers).status_code == 401
    assert [spy.call_count for spy in spies] == [0, 0, 0]


@pytest.mark.parametrize('suffix', ['', '/'])
@pytest.mark.parametrize('declared,expected', [('131073', 413), ('1', 413), ('invalid', 400), ('-1', 413)])
def test_body_limits_and_auth_order(client, monkeypatch, suffix, declared, expected):
    spies = spy_models(monkeypatch)
    headers = dict(client.auth_headers, **{'Content-Length': declared})
    response = client.post(PATH + suffix, content=b' ' * (LIMIT + 1), headers=headers,
                           follow_redirects=False)
    if client.hosted_test and suffix:
        assert response.status_code == 403  # Existing hosted allowlist precedes body limiting.
    elif suffix and declared == '1':
        assert response.status_code == 307
        assert response.headers['location'] == 'http://testserver' + PATH
        assert [spy.call_count for spy in spies] == [0, 0, 0]
        response = client.post(PATH, content=b' ' * (LIMIT + 1), headers=headers)
        assert response.status_code == 413
        assert response.json() == {'detail': 'request byte budget exceeded'}
    else:
        assert response.status_code == expected
        detail = 'invalid content length' if expected == 400 else 'request byte budget exceeded'
        assert response.json() == {'detail': detail}
    assert [spy.call_count for spy in spies] == [0, 0, 0]


def raw_chunks(client, chunks):
    async def run():
        headers = [(b'host', b'testserver'), (b'transfer-encoding', b'chunked')]
        headers += [(key.lower().encode(), value.encode()) for key, value in client.auth_headers.items()]
        assert all(key != b'content-length' for key, _ in headers)
        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                 'method': 'POST', 'scheme': 'http', 'path': PATH, 'raw_path': PATH.encode(),
                 'query_string': b'', 'root_path': '', 'headers': headers,
                 'client': ('127.0.0.1', 1234), 'server': ('testserver', 80)}
        pending, delivered, responses = iter(enumerate(chunks)), [], []

        async def receive():
            item = next(pending, None)
            if item is None:
                await anyio.sleep_forever()
            index, chunk = item
            delivered.append(len(chunk))
            return {'type': 'http.request', 'body': chunk, 'more_body': index < len(chunks) - 1}

        async def send(message):
            responses.append(message)

        await client.app(scope, receive, send)
        status = next(message['status'] for message in responses if message['type'] == 'http.response.start')
        body = b''.join(message.get('body', b'') for message in responses if message['type'] == 'http.response.body')
        return status, json.loads(body), delivered

    return client.portal.call(run)


@pytest.mark.parametrize('extra,expected', [(0, 422), (1, 413)])
def test_raw_split_chunked_actual_bytes(client, monkeypatch, extra, expected):
    spies = spy_models(monkeypatch)
    chunks = [b' ' * 65536, b' ' * 65536] + ([b' '] if extra else [])
    status, body, delivered = raw_chunks(client, chunks)
    assert delivered == ([65536, 65536, 1] if extra else [65536, 65536])
    assert sum(delivered) == 131072 + extra
    assert status == expected
    assert body == ({'detail': 'request byte budget exceeded'} if extra else INVALID)
    assert [spy.call_count for spy in spies] == [0, 0, 0]


def test_valid_mission_exact_byte_boundary(client, mission_request, monkeypatch):
    mission_request['thermal_body']['property_source'] = 'Synthetic µ'
    direct = mission.evaluate_solved_dc_electrothermal(mission_request)
    spies = spy_models(monkeypatch)
    encoded = json.dumps(mission_request, ensure_ascii=False).encode('utf-8')
    bounded = encoded + b' ' * (LIMIT - len(encoded))
    assert len(bounded) == 131072
    result = assert_result(client.post(PATH, content=bounded, headers=client.auth_headers),
                           direct, mission_request)
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    assert [spy.call_count for spy in spies] == [1, 2, 1]
    oversized = client.post(PATH, content=bounded + b' ', headers=client.auth_headers)
    assert oversized.request.headers['content-length'] == '131073'
    assert oversized.status_code == 413
    assert oversized.json() == {'detail': 'request byte budget exceeded'}
    assert [spy.call_count for spy in spies] == [1, 2, 1]


def test_private_point_failure_is_actual_atomic_result(client, mission_request, monkeypatch):
    spies = spy_models(monkeypatch)
    spies[1].side_effect = RuntimeError('PRIVATE_SECRET point internals')
    direct = mission.evaluate_solved_dc_electrothermal(mission_request)
    for spy in spies:
        spy.reset_mock()
    response = client.post(PATH, json=mission_request, headers=client.auth_headers)
    result = assert_result(response, direct, mission_request)
    assert result['status'] == 'EXECUTION_FAILED'
    assert result['diagnostics_complete'] is False
    assert result['reasons'] == ['Solved DC electrothermal execution failed.']
    assert result['stages'] == result['transfers'] == []
    assert result['outputs'] == result['output_units'] == {}
    assert 'PRIVATE_SECRET' not in response.text
    assert [spy.call_count for spy in spies] == [1, 1, 0]
