"""Actual frozen-ledger mission HTTP smoke contracts in local and hosted modes."""

import json
import math
import threading
from copy import deepcopy
from unittest.mock import Mock

import anyio
import pytest
from fastapi import HTTPException, Request

from physimesh.api import ledger_solved_dc_electrothermal as api
from physimesh.drone import ledger_solved_dc_electrothermal as m
from physimesh.drone.provenance import sha256_record

from .test_ledger_solved_dc_electrothermal import wrapper_request
from .test_model_graph_application import client as client  # noqa: PLC0414

PATH = '/api/drone/ledger-solved-dc-electrothermal/evaluate'
CATALOG = '/api/drone/ledger-solved-dc-electrothermal/catalog'
LIMIT = 131072
INVALID = {'detail': 'Invalid ledger solved DC electrothermal request.'}
TOO_LARGE = {'detail': 'request byte budget exceeded'}


def spy_models(monkeypatch):
    spies = {}
    for key, owner, name in (
        ('wrapper', m, 'evaluate_ledger_solved_dc_electrothermal'),
        ('ledger', m.ml, 'evaluate_mass_ledger'),
        ('mission', m.mission, 'evaluate_solved_dc_electrothermal'),
        ('point', m.mission.dp, 'evaluate_solved_dc_power'),
        ('thermal', m.mission.th, 'screen_thermal'),
    ):
        spy = Mock(wraps=getattr(owner, name))
        monkeypatch.setattr(owner, name, spy)
        spies[key] = spy
    return spies


def assert_actual_result(response, direct, request):
    assert response.status_code == 200, response.text
    result = response.json()
    digest = result.pop('evaluation_sha256')
    assert digest == sha256_record(result)
    assert result.pop('input_sha256') == direct['request_sha256'] == sha256_record(request)
    assert result == direct
    return result


def test_authenticated_actual_met_equality_hashes_and_calls(client, monkeypatch):
    request = wrapper_request.__wrapped__()
    before = deepcopy(request)
    direct = m.evaluate_ledger_solved_dc_electrothermal(request)
    assert direct['status'] == 'COMPUTED_EXPERIMENTAL', direct['reasons']
    assert api.ledger_mission is m
    spies = spy_models(monkeypatch)

    result = assert_actual_result(
        client.post(PATH, json=request, headers=client.auth_headers), direct, before,
    )

    assert request == before
    assert {key: spy.call_count for key, spy in spies.items()} == {
        'wrapper': 1, 'ledger': 1, 'mission': 1, 'point': 2, 'thermal': 1,
    }
    assert spies['wrapper'].call_args.args == (before,)
    assert spies['ledger'].call_args.args == (before['ledger'],)
    ledger = result['outputs']['ledger']
    assert ledger['total_mass_kg'] == 4
    assert ledger['cg_body_m'] == [.25, -.125, .05]
    instantiated = spies['mission'].call_args.args[0]
    for index, segment in enumerate(instantiated['segments']):
        assembly = segment['point']['solve']['assembly_template']
        assert assembly['mass_kg'] == ledger['total_mass_kg']
        assert assembly['cg_body_m'] == ledger['cg_body_m']
        assert spies['point'].call_args_list[index].args == (segment['point'],)
        transfer = result['transfers']['mass_cg'][index]
        assert transfer['mass_kg'] == ledger['total_mass_kg']
        assert transfer['cg_body_m'] == ledger['cg_body_m']
        assert transfer['segment_id'] == segment['id']
    assert instantiated['thermal_body'] == before['mission_template']['thermal_body']
    assert spies['thermal'].call_args.args[0]['mass_kg'] == 2 != ledger['total_mass_kg']
    assert result['outputs']['mission']['mission_state'] == 'COMPUTED_FROM_RESIDUAL_MET_SEGMENTS'
    assert set(result['outputs']) == set(result['output_units']) == {'ledger', 'mission'}
    for key in ('physical_validation', 'numerical_qualification', 'runtime_identity'):
        assert result[key] == 'NOT_ESTABLISHED'
    assert result['feasibility'] is result['aircraft_status'] is None


def test_actual_first_segment_unmet_retains_only_reached_prefix(client, monkeypatch):
    request = wrapper_request.__wrapped__()
    segments = request['mission_template']['segments']
    segments[0]['point']['solve'].update(
        max_evaluations=2, required_net_force_body_n=[1e9, 0, 0],
    )
    direct = m.evaluate_ledger_solved_dc_electrothermal(request)
    assert direct['status'] == 'COMPUTED_EXPERIMENTAL', direct['reasons']
    spies = spy_models(monkeypatch)

    result = assert_actual_result(
        client.post(PATH, json=request, headers=client.auth_headers), direct, request,
    )

    assert {key: spy.call_count for key, spy in spies.items()} == {
        'wrapper': 1, 'ledger': 1, 'mission': 1, 'point': 1, 'thermal': 0,
    }
    mission = result['outputs']['mission']
    units = result['output_units']['mission']
    assert mission['mission_state'] == 'STOPPED_AT_UNMET_SEGMENT'
    assert [row['segment_id'] for row in mission['power_segments']] == [segments[0]['id']]
    assert mission['power_segments'][0]['power'] is None
    assert mission['energy'] is mission['thermal'] is units['energy'] is units['thermal'] is None
    assert result['transfers']['mission'] == []
    assert [row['segment_id'] for row in result['transfers']['mass_cg']] == [s['id'] for s in segments]
    assert len(result['stages'][1]['stages']) == 1


def test_catalog_root_and_independent_transport_outer_limits(client):
    response = client.get(CATALOG, headers=client.auth_headers)
    assert response.status_code == 200
    catalog = response.json()
    assert catalog['evaluation'] == m.EVALUATION
    assert catalog['root_fields_exact'] is True
    assert set(catalog['required_root']) == {'evaluation', 'ledger', 'mission_template'}
    limits = catalog['limits']
    assert (limits['body_bytes'], limits['json_depth'], limits['json_values']) == (131072, 13, 98304)
    assert limits['root_depth'] == 1
    assert limits['ledger']['json_values'] == 16384
    assert limits['mission']['json_values'] == 65536
    assert 'Independent HTTP bound' in limits['body_bytes_constraint']
    assert 'do not promise HTTP acceptance' in limits['body_bytes_constraint']
    shape = catalog['field_shape']
    assert set(shape['ledger']['required']) == {'evaluation', 'items', 'property_source'}
    assembly = shape['mission_template']['segments']['point']['solve.assembly_template']
    assert set(assembly['must_omit']) == {'mass_kg', 'cg_body_m'}
    assert not {'mass_kg', 'cg_body_m'} & set(assembly['required'])
    assert catalog['limitations']['output_shape']['mission_path'] == 'outputs.mission'
    assert catalog['evidence_level'] == 'unverified'
    for key in ('physical_validation', 'numerical_qualification', 'runtime_identity'):
        assert catalog[key] == 'NOT_ESTABLISHED'
    assert catalog['feasibility'] is catalog['aircraft_status'] is None


def test_strict_parse_refusals_never_call_evaluators(client, monkeypatch):
    spies = spy_models(monkeypatch)
    for raw in (
        b'{"evaluation":1,"evaluation":2}',
        b'{"ledger":{"name":1,"name":2}}',
        b'{"ledger":{"mass_kg":NaN}}',
        b'{"x":Infinity}', b'{"x":-Infinity}', b'{"x":1e9999}',
        b'{"x":"\xff"}', b'{"x":"\\ud800"}',
        b'[]', b'null', b'1', b'"text"', b'{"PRIVATE_SECRET":',
    ):
        response = client.post(PATH, content=raw, headers=client.auth_headers)
        assert response.status_code == 422, raw
        assert response.json() == INVALID
    assert all(spy.call_count == 0 for spy in spies.values())


def test_missing_or_invalid_auth_precedes_parsing_and_body_limits(client, monkeypatch):
    spies = spy_models(monkeypatch)
    for authorization in ({}, {'Authorization': 'Bearer wrong-token'}):
        assert client.get(CATALOG, headers=authorization).status_code == 401
        for declared in ('invalid', str(LIMIT + 1)):
            headers = dict(authorization, **{'Content-Length': declared})
            response = client.post(PATH, content=b'PRIVATE_SECRET', headers=headers)
            assert response.status_code == 401
            assert 'PRIVATE_SECRET' not in response.text
    assert all(spy.call_count == 0 for spy in spies.values())


def test_exact_routes_neighbors_methods_and_slash_redirects(client, monkeypatch):
    spies = spy_models(monkeypatch)
    assert client.get(CATALOG, headers=client.auth_headers).status_code == 200
    response = client.post(PATH, json={}, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json()['status'] == 'GRAPH_INVALID'
    assert not {'request_sha256', 'input_sha256', 'evaluation_sha256'} & response.json().keys()
    assert client.get(PATH, headers=client.auth_headers).status_code == 405
    assert client.post(CATALOG, json={}, headers=client.auth_headers).status_code == 405
    for suffix in ('/extra', '-extra', 'evil'):
        expected = 403 if client.hosted_test else 404
        assert client.get(CATALOG + suffix, headers=client.auth_headers).status_code == expected
        assert client.post(PATH + suffix, json={}, headers=client.auth_headers).status_code == expected
    for path, method in ((CATALOG, 'GET'), (PATH, 'POST')):
        response = client.request(method, path + '/', headers=client.auth_headers, follow_redirects=False)
        assert response.status_code == (403 if client.hosted_test else 307)
        if not client.hosted_test:
            assert response.headers['location'] == 'http://testserver' + path
    assert {key: spy.call_count for key, spy in spies.items()} == {
        'wrapper': 1, 'ledger': 0, 'mission': 0, 'point': 0, 'thermal': 0,
    }


def test_declared_negative_huge_malformed_and_lying_lengths(client, monkeypatch):
    spies = spy_models(monkeypatch)
    for declared, expected in (
        (str(LIMIT + 1), 413), ('-1', 413), ('9' * 100, 413),
        ('invalid', 400), ('+1', 400), ('-0', 400), ('1', 413),
    ):
        headers = dict(client.auth_headers, **{'Content-Length': declared})
        response = client.post(PATH, content=b' ' * (LIMIT + 1), headers=headers)
        assert response.status_code == expected, declared
        assert response.json() == (TOO_LARGE if expected == 413 else {'detail': 'invalid content length'})
    assert all(spy.call_count == 0 for spy in spies.values())


def test_slash_body_limit_and_canonical_retry_match_existing_order(client, monkeypatch):
    spies = spy_models(monkeypatch)
    for declared in (str(LIMIT + 1), '1'):
        headers = dict(client.auth_headers, **{'Content-Length': declared})
        response = client.post(PATH + '/', content=b' ' * (LIMIT + 1), headers=headers,
                               follow_redirects=False)
        expected = 403 if client.hosted_test else (307 if declared == '1' else 413)
        assert response.status_code == expected
        if response.status_code == 307:
            assert response.headers['location'] == 'http://testserver' + PATH
            canonical = client.post(PATH, content=b' ' * (LIMIT + 1), headers=headers)
            assert canonical.status_code == 413
            assert canonical.json() == TOO_LARGE
    assert all(spy.call_count == 0 for spy in spies.values())


def raw_chunks(client, chunks, *, declared=None, chunked=True):
    """Deliver separate ASGI messages without httpx rewriting framing headers."""
    async def run():
        headers = [(b'host', b'testserver')]
        headers += [(key.lower().encode(), value.encode()) for key, value in client.auth_headers.items()]
        if chunked:
            headers.append((b'transfer-encoding', b'chunked'))
        if declared is not None:
            headers.append((b'content-length', declared.encode()))
        scope = {
            'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
            'method': 'POST', 'scheme': 'http', 'path': PATH, 'raw_path': PATH.encode(),
            'query_string': b'', 'root_path': '', 'headers': headers,
            'client': ('127.0.0.1', 1234), 'server': ('testserver', 80),
        }
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
        body = b''.join(message.get('body', b'') for message in responses
                        if message['type'] == 'http.response.body')
        return status, json.loads(body), delivered

    return client.portal.call(run)


def test_actual_multichunk_byte_limit_with_chunked_absent_and_lying_lengths(client, monkeypatch):
    spies = spy_models(monkeypatch)
    for chunked, declared in ((True, None), (False, None), (False, '1'), (False, str(LIMIT))):
        for extra in (0, 1):
            chunks = [b' ' * 65536, b' ' * 65536] + ([b' '] if extra else [])
            status, body, delivered = raw_chunks(client, chunks, chunked=chunked, declared=declared)
            assert delivered == [len(chunk) for chunk in chunks]
            assert sum(delivered) == LIMIT + extra
            assert status == (413 if extra else 422)
            assert body == (TOO_LARGE if extra else INVALID)
    status, body, delivered = raw_chunks(client, [b'{}'], declared=str(LIMIT + 1), chunked=False)
    assert (status, body, delivered) == (413, TOO_LARGE, [])
    assert all(spy.call_count == 0 for spy in spies.values())


def test_valid_utf8_exact_byte_boundary_and_split_character(client, monkeypatch):
    request = wrapper_request.__wrapped__()
    request['mission_template']['thermal_body']['property_source'] = 'Synthetic µ source'
    direct = m.evaluate_ledger_solved_dc_electrothermal(request)
    assert direct['status'] == 'COMPUTED_EXPERIMENTAL', direct['reasons']
    spies = spy_models(monkeypatch)
    encoded = json.dumps(request, ensure_ascii=False).encode('utf-8')
    assert len(encoded) < LIMIT
    padded = encoded + b' ' * (LIMIT - len(encoded))
    assert len(padded) == LIMIT
    assert_actual_result(client.post(PATH, content=padded, headers=client.auth_headers), direct, request)

    split = encoded.index('µ'.encode()) + 1
    chunks = [padded[:split], padded[split:65536], padded[65536:]]
    status, result, delivered = raw_chunks(client, chunks)
    assert status == 200
    assert delivered == [len(chunk) for chunk in chunks]
    digest = result.pop('evaluation_sha256')
    assert digest == sha256_record(result)
    assert result.pop('input_sha256') == direct['request_sha256'] == sha256_record(request)
    assert result == direct

    oversized = client.post(PATH, content=padded + b' ', headers=client.auth_headers)
    assert oversized.request.headers['content-length'] == str(LIMIT + 1)
    assert oversized.status_code == 413
    assert oversized.json() == TOO_LARGE
    status, body, delivered = raw_chunks(client, chunks + [b' '], chunked=False, declared='1')
    assert (status, body, sum(delivered)) == (413, TOO_LARGE, LIMIT + 1)
    assert {key: spy.call_count for key, spy in spies.items()} == {
        'wrapper': 2, 'ledger': 2, 'mission': 2, 'point': 4, 'thermal': 2,
    }


def test_actual_wrapper_runs_once_in_threadpool_while_event_loop_progresses(client, monkeypatch):
    request = wrapper_request.__wrapped__()
    direct = m.evaluate_ledger_solved_dc_electrothermal(request)
    spies = spy_models(monkeypatch)
    entered, progressed = threading.Event(), threading.Event()
    worker_threads, loop_threads, dispatches = [], [], []
    original_dispatch = api.run_in_threadpool

    def observed(payload):
        worker_threads.append(threading.get_ident())
        entered.set()
        assert progressed.wait(timeout=5), 'The event loop did not progress while the wrapper waited.'
        return spies['wrapper'](payload)

    async def dispatch(function, *args):
        dispatches.append((function, deepcopy(args)))
        loop_threads.append(threading.get_ident())

        async def heartbeat():
            with anyio.fail_after(5):
                while not entered.is_set():
                    await anyio.sleep(0.001)
            progressed.set()

        async with anyio.create_task_group() as group:
            group.start_soon(heartbeat)
            return await original_dispatch(function, *args)

    monkeypatch.setattr(m, 'evaluate_ledger_solved_dc_electrothermal', observed)
    monkeypatch.setattr(api, 'run_in_threadpool', dispatch)
    assert_actual_result(client.post(PATH, json=request, headers=client.auth_headers), direct, request)
    assert dispatches == [(observed, (request,))]
    assert len(worker_threads) == len(loop_threads) == 1
    assert worker_threads[0] != loop_threads[0]
    assert progressed.is_set()
    assert {key: spy.call_count for key, spy in spies.items()} == {
        'wrapper': 1, 'ledger': 1, 'mission': 1, 'point': 2, 'thermal': 1,
    }


def test_invalid_last_segment_and_global_work_preflight_before_any_child(client, monkeypatch):
    # The accepted fixture builder performs its own real ledger arithmetic.
    # Construct both inputs before observing evaluator calls from HTTP requests.
    base = wrapper_request.__wrapped__()
    spies = spy_models(monkeypatch)
    for defect in ('invalid_last', 'global_work'):
        request = deepcopy(base)
        segments = request['mission_template']['segments']
        if defect == 'invalid_last':
            segments[-1]['thermal']['ambient_temperature_k'] = True
        else:
            work = []
            for segment in segments:
                solve = segment['point']['solve']
                solve['max_evaluations'] = 32
                annuli = 0
                for node in solve['assembly_template']['graph']['nodes']:
                    if node['model'] == 'isolated_hover_bemt_experimental':
                        node['inputs']['annuli'] = 256
                        annuli += 256
                work.append(annuli * (solve['max_evaluations'] + 1))
            assert all(value <= 32768 for value in work)
            assert sum(work) > 32768
        response = client.post(PATH, json=request, headers=client.auth_headers)
        assert response.status_code == 200
        result = response.json()
        assert result['status'] == 'GRAPH_INVALID'
        assert result['diagnostics_complete'] is False
        assert result['reasons'] == ['Invalid ledger solved DC electrothermal request.']
        assert result['outputs'] == result['output_units'] == result['transfers'] == {}
        assert result['stages'] == []
        assert not {'request_sha256', 'input_sha256', 'evaluation_sha256'} & result.keys()
        assert all(spy.call_count == 0 for key, spy in spies.items() if key != 'wrapper')
    assert spies['wrapper'].call_count == 2


def call_handler(request):
    """Isolate JSON guards whose node limits can exceed the HTTP byte bound."""
    raw = json.dumps(request).encode()

    async def receive():
        return {'type': 'http.request', 'body': raw, 'more_body': False}

    scope = {'type': 'http', 'method': 'POST', 'path': PATH, 'headers': []}
    return anyio.run(api.evaluate, Request(scope, receive))


def node_tree(count):
    """Exactly count JSON nodes, with at most 256 children per container."""
    if count == 1:
        return 0
    children = min(256, count - 1)
    quotient, remainder = divmod(count - 1, children)
    return [node_tree(quotient + (index < remainder)) for index in range(children)]


def test_handler_outer_depth_node_scalar_and_container_boundaries(monkeypatch):
    # Only this parser probe replaces the evaluator; no scientific envelope is fabricated.
    probe = Mock(return_value={'parser_probe': True})
    monkeypatch.setattr(m, 'evaluate_ledger_solved_dc_electrothermal', probe)
    nested = 0
    for _ in range(11):
        nested = [nested]
    for request in (
        {'probe': nested},  # Root depth one, deepest scalar at depth 13.
        {'probe': node_tree(98302)},  # Root, key and tree total exactly 98,304 nodes.
        {'probe': ['x' * 2000, (1 << 1023) - 1, True, None]},
        {'probe': [0] * 256},
    ):
        before = probe.call_count
        assert call_handler(request) == {'parser_probe': True}
        assert probe.call_count == before + 1
        assert probe.call_args.args == (request,)
    for request in (
        {'probe': [nested]}, {'probe': node_tree(98303)},
        {'probe': 'x' * 2001}, {'probe': 1 << 1023}, {'probe': [0] * 257},
    ):
        before = probe.call_count
        with pytest.raises(HTTPException) as error:
            call_handler(request)
        assert error.value.status_code == 422
        assert error.value.detail == INVALID['detail']
        assert probe.call_count == before


def test_independent_child_json_budgets_reject_before_evaluators(monkeypatch):
    base = wrapper_request.__wrapped__()
    spies = spy_models(monkeypatch)
    for child, owner, name, budget in (
        ('ledger', m.ml, '_json', 16384),
        ('mission', m.mission, '_mission_json', 65536),
        ('point', m.mission.dp, '_json', 49152),
        ('solver', m.mission.dp.sp.ws, '_json', 32768),
        ('motor', m.mission.dp.dc, '_json', 4096),
    ):
        request = deepcopy(base)
        template = request['mission_template']
        point = template['segments'][0]['point']
        target = {
            'ledger': request['ledger'], 'mission': template['thermal_body'],
            'point': point['solve'], 'solver': point['solve'],
            'motor': point['motors'][0]['parameters'],
        }[child]
        target['probe'] = node_tree(budget + 1)
        m._outer_json(request)  # Each child refusal is independent of the outer guard.
        rejected = []
        original = getattr(owner, name)

        def guarded(value, *, original=original, rejected=rejected, **kwargs):
            try:
                return original(value, **kwargs)
            except ValueError:
                rejected.append(kwargs.get('budget', 65536))
                raise

        with monkeypatch.context() as patch:
            patch.setattr(owner, name, guarded)
            result = call_handler(request)
        assert rejected == [budget], child
        assert result['status'] == 'GRAPH_INVALID'
        assert result['outputs'] == result['output_units'] == result['transfers'] == {}
        assert result['stages'] == []
        assert 'input_sha256' not in result and 'evaluation_sha256' not in result
        assert all(spy.call_count == 0 for key, spy in spies.items() if key != 'wrapper')
    assert spies['wrapper'].call_count == 5


def test_boolean_numeric_fields_and_caller_mass_cg_fail_before_children(client, monkeypatch):
    base = wrapper_request.__wrapped__()
    spies = spy_models(monkeypatch)
    paths = (
        ('ledger', 'items', 0, 'mass_kg'), ('ledger', 'items', 0, 'cg_body_m', 0),
        ('mission_template', 'usable_energy_j'), ('mission_template', 'reserve_fraction'),
        ('mission_template', 'thermal_body', 'mass_kg'),
        ('mission_template', 'segments', 1, 'duration_s'),
        ('mission_template', 'segments', 1, 'thermal', 'conductance_w_k'),
        ('mission_template', 'segments', 1, 'point', 'solve', 'max_evaluations'),
        ('mission_template', 'segments', 1, 'point', 'motors', 0, 'parameters', 'motor_constant_si'),
    )
    defects = [(path, True) for path in paths]
    assembly_path = ('mission_template', 'segments', 1, 'point', 'solve', 'assembly_template')
    defects += [(assembly_path + ('mass_kg',), 4), (assembly_path + ('cg_body_m',), [.25, -.125, .05])]
    for path, value in defects:
        request = deepcopy(base)
        target = request
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        response = client.post(PATH, json=request, headers=client.auth_headers)
        assert response.status_code == 200
        result = response.json()
        assert result['status'] == 'GRAPH_INVALID', path
        assert result['outputs'] == result['output_units'] == result['transfers'] == {}
        assert result['stages'] == []
        assert not {'request_sha256', 'input_sha256', 'evaluation_sha256'} & result.keys()
    assert spies['wrapper'].call_count == len(defects)
    assert all(spy.call_count == 0 for key, spy in spies.items() if key != 'wrapper')


@pytest.mark.parametrize('child', ['ledger', 'mission'])
def test_coherent_actual_child_forgery_is_atomic_http_200(client, monkeypatch, child):
    request = wrapper_request.__wrapped__()
    owner, name = ((m.ml, 'evaluate_mass_ledger') if child == 'ledger'
                   else (m.mission, 'evaluate_solved_dc_electrothermal'))
    original = getattr(owner, name)

    def forged(payload):
        raw = original(payload)
        assert raw['status'] == 'COMPUTED_EXPERIMENTAL'
        if child == 'ledger':
            out = raw['outputs']
            out['total_mass_kg'] *= 2
            out['payload_kg'] *= 2
            out['by_category_kg'] = {key: value * 2 for key, value in out['by_category_kg'].items()}
            out['inertia_cg_body_kgm2'] = [[value * 2 for value in row]
                                         for row in out['inertia_cg_body_kgm2']]
        else:
            energy = raw['outputs']['energy']
            for row in energy['segments']:
                row['segment_energy_j'] *= 2
                row['cumulative_energy_j'] *= 2
                row['remaining_budget_j'] = energy['mission_budget_j'] - row['cumulative_energy_j']
            energy['total_energy_j'] *= 2
            energy['total_energy_wh'] *= 2
            energy['remaining_budget_j'] = energy['mission_budget_j'] - energy['total_energy_j']
            energy['budget_status'] = ('WITHIN_DECLARED_ENERGY' if energy['remaining_budget_j'] >= 0
                                       else 'EXCEEDS_DECLARED_ENERGY')
        return raw

    monkeypatch.setattr(owner, name, forged)
    direct = m.evaluate_ledger_solved_dc_electrothermal(request)
    spies = spy_models(monkeypatch)
    result = assert_actual_result(
        client.post(PATH, json=request, headers=client.auth_headers), direct, request,
    )
    assert result['status'] == 'EXECUTION_FAILED'
    assert result['diagnostics_complete'] is False
    assert result['outputs'] == result['output_units'] == result['transfers'] == {}
    assert result['stages'] == []
    assert result['reasons'] == ['Ledger solved DC electrothermal execution failed.']
    assert {key: spy.call_count for key, spy in spies.items()} == {
        'wrapper': 1, 'ledger': 1, 'mission': int(child == 'mission'),
        'point': 2 if child == 'mission' else 0, 'thermal': int(child == 'mission'),
    }


def test_second_unmet_segment_retains_two_points_and_no_thermal(client, monkeypatch):
    request = wrapper_request.__wrapped__()
    segments = request['mission_template']['segments']
    segments.append({**deepcopy(segments[-1]), 'id': 'never_reached'})
    segments[1]['point']['solve'].update(max_evaluations=2, required_net_force_body_n=[1e9, 0, 0])
    direct = m.evaluate_ledger_solved_dc_electrothermal(request)
    spies = spy_models(monkeypatch)
    result = assert_actual_result(client.post(PATH, json=request, headers=client.auth_headers), direct, request)
    assert result['status'] == 'COMPUTED_EXPERIMENTAL'
    out, units = result['outputs']['mission'], result['output_units']['mission']
    assert out['mission_state'] == 'STOPPED_AT_UNMET_SEGMENT'
    assert [row['segment_id'] for row in out['power_segments']] == [s['id'] for s in segments[:2]]
    assert out['power_segments'][0]['power'] is not None
    assert out['power_segments'][1]['power'] is None
    assert out['energy'] is out['thermal'] is units['energy'] is units['thermal'] is None
    assert result['outputs']['ledger']['cg_body_m'] == [.25, -.125, .05]
    assert len(result['transfers']['mass_cg']) == 3
    assert result['transfers']['mission'] == []
    assert {key: spy.call_count for key, spy in spies.items()} == {
        'wrapper': 1, 'ledger': 1, 'mission': 1, 'point': 2, 'thermal': 0,
    }


def test_different_points_thermal_conditions_and_energy_excess_ignore_heat_allocation(client, monkeypatch):
    base = wrapper_request.__wrapped__()
    template = base['mission_template']
    template.update(usable_energy_j=1, reserve_fraction=.25)
    for segment, duration, ambient, conductance, auxiliary in zip(
        template['segments'], (7, 19), (290, 310), (2, 0), (20, 37), strict=True,
    ):
        segment['duration_s'] = duration
        segment['thermal'].update(ambient_temperature_k=ambient, conductance_w_k=conductance)
        segment['point']['auxiliary']['power_w'] = auxiliary
    requests = []
    for fraction in (0, 1):
        request = deepcopy(base)
        for segment in request['mission_template']['segments']:
            segment['point']['auxiliary']['heat_fraction'] = fraction
            for motor in segment['point']['motors']:
                motor['heat_fraction_of_motor_loss'] = fraction
        requests.append(request)
    direct = [m.evaluate_ledger_solved_dc_electrothermal(request) for request in requests]
    spies = spy_models(monkeypatch)
    results = []
    for request, expected in zip(requests, direct, strict=True):
        result = assert_actual_result(client.post(PATH, json=request, headers=client.auth_headers),
                                     expected, request)
        assert result['status'] == 'COMPUTED_EXPERIMENTAL'
        mission = result['outputs']['mission']
        energy = mission['energy']
        assert energy['total_energy_j'] == pytest.approx(math.fsum(
            row['duration_s'] * row['power']['total_electrical_power_w'] for row in mission['power_segments']
        ))
        assert energy['held_reserve_j'] == .25 and energy['mission_budget_j'] == .75
        assert energy['remaining_budget_j'] < 0
        assert energy['budget_status'] == 'EXCEEDS_DECLARED_ENERGY'
        assert energy['elapsed_s'] == mission['thermal']['elapsed_s'] == 26
        assert result['feasibility'] is result['aircraft_status'] is None
        assert result['physical_validation'] == 'NOT_ESTABLISHED'
        results.append(mission)
    assert results[0]['energy'] == results[1]['energy']
    assert results[0]['thermal']['total_heat_input_j'] == 0
    assert results[1]['thermal']['total_heat_input_j'] > 0
    assert results[1]['thermal']['final_temperature_k'] > results[0]['thermal']['final_temperature_k']
    thermal_request = spies['thermal'].call_args.args[0]
    assert thermal_request['mass_kg'] == 2
    assert [row['ambient_temperature_k'] for row in thermal_request['segments']] == [290, 310]
    assert [row['conductance_w_k'] for row in thermal_request['segments']] == [2, 0]
    assert {key: spy.call_count for key, spy in spies.items()} == {
        'wrapper': 2, 'ledger': 2, 'mission': 2, 'point': 4, 'thermal': 2,
    }
