"""Actual tabulated-hover HTTP equality, provenance and bounded transport checks."""

import json
import threading
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock

import anyio

from physimesh.api import tabulated_hover as api
from physimesh.drone import tabulated_hover_bemt_request as adapter
from physimesh.drone.provenance import sha256_record

from .test_model_graph_application import client as client  # noqa: PLC0414 -- expose shared pytest fixture
from .test_tabulated_hover_bemt import inputs
from .test_tabulated_hover_bemt_request import EXPECTED_UNITS, assert_plain_json_and_count_nodes

PATH = "/api/drone/tabulated-hover/evaluate"
CATALOG = "/api/drone/tabulated-hover/catalog"
LIMIT = 131072
INVALID = {"detail": "Invalid tabulated hover request."}
TOO_LARGE = {"detail": "request byte budget exceeded"}


def spy_models(monkeypatch):
    adapter_spy = Mock(wraps=adapter.evaluate_tabulated_hover_bemt)
    core_spy = Mock(wraps=adapter.solve_tabulated_hover)
    monkeypatch.setattr(adapter, "evaluate_tabulated_hover_bemt", adapter_spy)
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)
    return adapter_spy, core_spy


def raw_chunks(client, chunks, *, declared=None, chunked=True, authorization=None):
    """Adapt V101's helper to the new route without httpx rewriting framing."""
    async def run():
        headers = [(b"host", b"testserver")]
        auth = client.auth_headers if authorization is None else authorization
        headers += [(key.lower().encode(), value.encode()) for key, value in auth.items()]
        if chunked:
            headers.append((b"transfer-encoding", b"chunked"))
        if declared is not None:
            headers.append((b"content-length", declared.encode()))
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "POST", "scheme": "http", "path": PATH, "raw_path": PATH.encode(),
            "query_string": b"", "root_path": "", "headers": headers,
            "client": ("127.0.0.1", 1234), "server": ("testserver", 80),
        }
        pending, delivered, responses = iter(enumerate(chunks)), [], []

        async def receive():
            item = next(pending, None)
            if item is None:
                await anyio.sleep_forever()
            index, chunk = item
            delivered.append(len(chunk))
            return {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}

        async def send(message):
            responses.append(message)

        await client.app(scope, receive, send)
        status = next(message["status"] for message in responses if message["type"] == "http.response.start")
        body = b"".join(message.get("body", b"") for message in responses
                        if message["type"] == "http.response.body")
        return status, json.loads(body), delivered

    return client.portal.call(run)


def test_actual_http_direct_equality_hashes_and_one_call(client, monkeypatch):
    core_request = inputs()
    body = {"evaluation": adapter.EVALUATION, **core_request}
    direct = adapter.evaluate_tabulated_hover_bemt(body)
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"

    # The direct baseline is outside both spies; only HTTP work is counted.
    adapter_spy = Mock(wraps=adapter.evaluate_tabulated_hover_bemt)
    core_spy = Mock(wraps=adapter.solve_tabulated_hover)
    monkeypatch.setattr(adapter, "evaluate_tabulated_hover_bemt", adapter_spy)
    monkeypatch.setattr(adapter, "solve_tabulated_hover", core_spy)

    response = client.post(PATH, json=body, headers=client.auth_headers)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result == direct
    adapter_spy.assert_called_once_with(body)
    core_spy.assert_called_once_with(**core_request)
    assert "input_sha256" not in result
    assert result["request_sha256"] == direct["request_sha256"] == sha256_record(body)
    assert result["evaluation_sha256"] == direct["evaluation_sha256"] == sha256_record({
        key: value for key, value in result.items() if key != "evaluation_sha256"
    })


def test_actual_catalog_is_fresh_nested_and_transport_is_separate(client, monkeypatch):
    actual_catalog = adapter.tabulated_hover_bemt_catalog
    baseline = actual_catalog()
    returned_catalogs = []

    def capture_catalog():
        result = actual_catalog()
        returned_catalogs.append(result)
        return result

    catalog_spy = Mock(side_effect=capture_catalog)
    monkeypatch.setattr(adapter, "tabulated_hover_bemt_catalog", catalog_spy)

    response = client.get(CATALOG, headers=client.auth_headers)
    assert response.status_code == 200, response.text
    first = response.json()
    assert set(first) == {"catalog", "transport"}
    assert first["catalog"] == returned_catalogs[0] == baseline
    assert "transport" not in first["catalog"]
    assert "body_bytes" not in first["catalog"]["limits"]
    transport = deepcopy(first["transport"])
    limits = transport["limits"]
    assert limits["body_bytes"] == 131072
    assert limits["input_json_reference"] == "catalog.limits.input_json"
    assert limits["response_json_reference"] == "catalog.limits.output_json"
    assert limits["model_shape_reference"] == "catalog.limits.core_work"

    # Mutate the actual first returned object as well as the decoded HTTP copy.
    for catalog in (returned_catalogs[0], first["catalog"]):
        catalog["limits"]["input_json"]["max_depth"] = -1
        catalog["input_units"]["stations"]["chord_m"] = "caller mutation"
        catalog["request_contract"]["geometry"]["stations"] = "caller mutation"
        catalog["required_fields"].append("caller mutation")
    first["transport"]["limits"]["body_bytes"] = -1

    response = client.get(CATALOG, headers=client.auth_headers)
    assert response.status_code == 200, response.text
    second = response.json()
    assert catalog_spy.call_count == 2
    assert second["catalog"] == returned_catalogs[1] == baseline == actual_catalog()
    assert second["transport"] == transport
    assert returned_catalogs[0]["limits"]["input_json"] is not returned_catalogs[1]["limits"]["input_json"]
    assert returned_catalogs[0]["input_units"]["stations"] is not returned_catalogs[1]["input_units"]["stations"]


def test_actual_zero_angle_keeps_positive_profile_power_over_http(client):
    core_request = inputs()
    assert core_request["profile_drag_coefficient"] > 0
    for station in core_request["stations"]:
        station["blade_angle_rad"] = 0.0
    body = {"evaluation": adapter.EVALUATION, **core_request}
    direct = adapter.evaluate_tabulated_hover_bemt(body)

    response = client.post(PATH, json=body, headers=client.auth_headers)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result == direct
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    outputs = result["outputs"]
    assert outputs["blade_angle_rad"] == [0.0] * core_request["annuli"]
    assert outputs["inflow_ratio"] == [0.0] * core_request["annuli"]
    assert outputs["thrust_n"] == outputs["thrust_coefficient"] == 0.0
    assert outputs["induced_power_coefficient"] == 0.0
    assert outputs["profile_power_coefficient"] > 0.0
    assert outputs["shaft_power_coefficient"] == outputs["profile_power_coefficient"]
    assert outputs["shaft_power_w"] > 0.0


def test_strict_parse_refusals_never_call_adapter_or_core(client, monkeypatch):
    spies = spy_models(monkeypatch)
    for raw in (
        b'{"evaluation":1,"evaluation":2}',
        b'{"stations":[{"radius_m":0,"radius_m":1}]}',
        b'{"stations":[{"chord_m":NaN}]}',
        b'{"x":Infinity}', b'{"x":-Infinity}', b'{"x":1e9999}',
        b'{"x":"\xff"}', b'{"x":"\\ud800"}',
        b'[]', b'null', b'1', b'true', b'"text"', b'{"PRIVATE_SECRET":',
    ):
        response = client.post(PATH, content=raw, headers=client.auth_headers)
        assert response.status_code == 422, raw
        assert response.json() == INVALID
    for spy in spies:
        spy.assert_not_called()


def test_missing_bad_auth_precedes_parsing_and_body_consumption(client, monkeypatch):
    spies = spy_models(monkeypatch)
    for authorization in ({}, {"Authorization": "Bearer wrong-token"}):
        assert client.get(CATALOG, headers=authorization).status_code == 401
        for declared in (None, "invalid", "-1", str(LIMIT + 1), "1"):
            headers = dict(authorization)
            if declared is not None:
                headers["Content-Length"] = declared
            response = client.post(PATH, content=b'{"PRIVATE_SECRET":', headers=headers)
            assert response.status_code == 401
            assert "PRIVATE_SECRET" not in response.text
            status, body, delivered = raw_chunks(
                client, [b"PRIVATE_SECRET" * 11000], declared=declared,
                chunked=declared is None, authorization=authorization,
            )
            assert status == 401
            assert "PRIVATE_SECRET" not in json.dumps(body)
            assert delivered == []
    for spy in spies:
        spy.assert_not_called()


def test_exact_routes_neighbors_and_slash_body_limit_order(client, monkeypatch):
    direct = adapter.evaluate_tabulated_hover_bemt({})
    spies = spy_models(monkeypatch)
    assert client.get(CATALOG, headers=client.auth_headers).status_code == 200
    response = client.post(PATH, json={}, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct
    assert direct["status"] == "MODEL_INAPPLICABLE"
    assert direct["request_sha256"] is direct["evaluation_sha256"] is None
    assert "input_sha256" not in response.json()
    assert client.get(PATH, headers=client.auth_headers).status_code == 405
    assert client.post(CATALOG, json={}, headers=client.auth_headers).status_code == 405
    for suffix in ("/extra", "-extra", "evil"):
        expected = 403 if client.hosted_test else 404
        assert client.get(CATALOG + suffix, headers=client.auth_headers).status_code == expected
        assert client.post(PATH + suffix, json={}, headers=client.auth_headers).status_code == expected
    for path, method in ((CATALOG, "GET"), (PATH, "POST")):
        response = client.request(method, path + "/", headers=client.auth_headers, follow_redirects=False)
        assert response.status_code == (403 if client.hosted_test else 307)
        if not client.hosted_test:
            assert response.headers["location"] == "http://testserver" + path
    for declared in (str(LIMIT + 1), "1"):
        headers = dict(client.auth_headers, **{"Content-Length": declared})
        response = client.post(PATH + "/", content=b" " * (LIMIT + 1), headers=headers,
                               follow_redirects=False)
        expected = 403 if client.hosted_test else (307 if declared == "1" else 413)
        assert response.status_code == expected
        if expected == 413:
            assert response.json() == TOO_LARGE
        elif expected == 307:
            assert response.headers["location"] == "http://testserver" + PATH
            canonical = client.post(PATH, content=b" " * (LIMIT + 1), headers=headers)
            assert canonical.status_code == 413
            assert canonical.json() == TOO_LARGE
    spies[0].assert_called_once_with({})
    spies[1].assert_not_called()


def test_declared_and_actual_byte_bound_negative_huge_malformed_lying(client, monkeypatch):
    spies = spy_models(monkeypatch)
    response = client.post(PATH, content=b" " * LIMIT, headers=client.auth_headers)
    assert response.status_code == 422
    assert response.json() == INVALID
    assert response.request.headers["content-length"] == str(LIMIT)
    for declared, expected in (
        (str(LIMIT + 1), 413), ("-1", 413), ("9" * 100, 413),
        ("invalid", 400), ("+1", 400), ("-0", 400), ("1", 413),
    ):
        headers = dict(client.auth_headers, **{"Content-Length": declared})
        response = client.post(PATH, content=b" " * (LIMIT + 1), headers=headers)
        assert response.status_code == expected, declared
        assert response.json() == (TOO_LARGE if expected == 413 else {"detail": "invalid content length"})
    for spy in spies:
        spy.assert_not_called()


def test_raw_chunked_absent_lying_bounds_and_split_utf8_actual_result(client, monkeypatch):
    body = {"evaluation": adapter.EVALUATION, **inputs(geometry_source="Synthetic µ source")}
    direct = adapter.evaluate_tabulated_hover_bemt(body)
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    spies = spy_models(monkeypatch)
    for chunked, declared in ((True, None), (False, None), (False, "1"), (False, str(LIMIT))):
        for extra in (0, 1):
            chunks = [b" " * 65536, b" " * 65536] + ([b" "] if extra else [])
            status, result, delivered = raw_chunks(client, chunks, chunked=chunked, declared=declared)
            assert delivered == [len(chunk) for chunk in chunks]
            assert sum(delivered) == LIMIT + extra
            assert status == (413 if extra else 422)
            assert result == (TOO_LARGE if extra else INVALID)
    status, result, delivered = raw_chunks(client, [b"{}"], declared=str(LIMIT + 1), chunked=False)
    assert (status, result, delivered) == (413, TOO_LARGE, [])
    for spy in spies:
        spy.assert_not_called()

    encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
    assert len(encoded) < LIMIT
    padded = encoded + b" " * (LIMIT - len(encoded))
    response = client.post(PATH, content=padded, headers=client.auth_headers)
    assert response.status_code == 200, response.text
    assert response.request.headers["content-length"] == str(LIMIT)
    assert response.json() == direct
    assert len(padded) == LIMIT
    split = encoded.index("µ".encode()) + 1
    chunks = [padded[:split], padded[split:65536], padded[65536:]]
    for declared in (str(LIMIT), "1"):
        status, result, delivered = raw_chunks(client, chunks, declared=declared, chunked=False)
        assert status == 200
        assert result == direct
        assert delivered == [len(chunk) for chunk in chunks]
        assert sum(delivered) == LIMIT
        assert "input_sha256" not in result
    assert [spy.call_count for spy in spies] == [3, 3]
    for spy in spies:
        spy.reset_mock()

    response = client.post(PATH, content=padded + b" ", headers=client.auth_headers)
    assert response.status_code == 413
    assert response.json() == TOO_LARGE
    for declared in (str(LIMIT + 1), str(LIMIT), "1"):
        status, result, delivered = raw_chunks(client, chunks + [b" "], declared=declared, chunked=False)
        assert status == 413
        assert result == TOO_LARGE
        assert delivered == ([] if declared == str(LIMIT + 1) else [len(chunk) for chunk in chunks] + [1])
    for spy in spies:
        spy.assert_not_called()


def test_actual_structured_status_nullable_hash_matrix_and_coherent_forgery(client, monkeypatch):
    valid = {"evaluation": adapter.EVALUATION, **inputs()}
    missing = deepcopy(valid)
    del missing["geometry_source"]
    for body, status, core_calls, has_request_hash in (
        (valid | {"evaluation": "unsupported"}, "SOLVER_UNSUPPORTED", 0, False),
        (missing, "MODEL_INAPPLICABLE", 0, False),
        (valid | {"unexpected": True}, "MODEL_INAPPLICABLE", 0, False),
        (valid | {"radius_m": -1.0}, "MODEL_INAPPLICABLE", 1, True),
    ):
        direct = adapter.evaluate_tabulated_hover_bemt(body)
        with monkeypatch.context() as patch:
            adapter_spy, core_spy = spy_models(patch)
            response = client.post(PATH, json=body, headers=client.auth_headers)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result == direct
        assert result["status"] == status
        assert result["outputs"] == result["output_units"] == {}
        assert result["diagnostics_complete"] is False
        assert "input_sha256" not in result
        assert result["request_sha256"] == (sha256_record(body) if has_request_hash else None)
        assert result["evaluation_sha256"] is None
        adapter_spy.assert_called_once_with(body)
        assert core_spy.call_count == core_calls

    core_request = inputs()
    actual = adapter.solve_tabulated_hover(**core_request)
    forged = replace(actual, thrust_n=actual.thrust_n * 2.0,
                     shaft_power_w=actual.shaft_power_w * 2.0,
                     shaft_torque_nm=actual.shaft_torque_nm * 2.0)
    # These forged loads retain P/Omega == Q; the actual adapter must still refuse them.
    assert forged.shaft_torque_nm == forged.shaft_power_w / core_request["angular_speed_rad_s"]
    with monkeypatch.context() as patch:
        fake_core = Mock(return_value=forged)
        patch.setattr(adapter, "solve_tabulated_hover", fake_core)
        direct = adapter.evaluate_tabulated_hover_bemt(valid)
        fake_core.reset_mock()
        adapter_spy = Mock(wraps=adapter.evaluate_tabulated_hover_bemt)
        patch.setattr(adapter, "evaluate_tabulated_hover_bemt", adapter_spy)
        response = client.post(PATH, json=valid, headers=client.auth_headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result == direct
    assert result["status"] == "EXECUTION_FAILED"
    assert result["outputs"] == result["output_units"] == {}
    assert result["diagnostics_complete"] is False
    assert result["core_model"] is result["core_version"] is result["core_status"] is None
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["request_sha256"] == sha256_record(valid)
    assert result["evaluation_sha256"] == sha256_record({
        key: value for key, value in result.items() if key != "evaluation_sha256"
    })
    assert "input_sha256" not in result
    adapter_spy.assert_called_once_with(valid)
    fake_core.assert_called_once_with(**core_request)


def test_actual_maximum_shape_full_response_units_and_one_call(client, monkeypatch):
    stations = [
        {"radius_m": index / 255, "chord_m": 0.05, "blade_angle_rad": 0.08}
        for index in range(256)
    ]
    core_request = inputs(stations=stations, annuli=2048, blade_count=32)
    body = {"evaluation": adapter.EVALUATION, **core_request}
    direct = adapter.evaluate_tabulated_hover_bemt(body)
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
    assert len(encoded) < LIMIT
    adapter_spy, core_spy = spy_models(monkeypatch)

    response = client.post(PATH, content=encoded, headers=client.auth_headers)

    assert response.status_code == 200, response.text
    assert response.request.headers["content-length"] == str(len(encoded))
    result = response.json()
    assert result == direct
    adapter_spy.assert_called_once_with(body)
    core_spy.assert_called_once_with(**core_request)
    assert result["diagnostics_complete"] is True
    outputs = result["outputs"]
    assert outputs["annuli"] == 2048
    assert len(outputs["stations"]) == 256
    assert result["output_units"] == EXPECTED_UNITS
    assert outputs.keys() == result["output_units"].keys()
    for station in outputs["stations"]:
        assert station.keys() == EXPECTED_UNITS["stations"].keys()
    for key, value in outputs.items():
        if isinstance(value, list) and key != "stations":
            assert len(value) == 2048, key
    assert assert_plain_json_and_count_nodes(body) <= result["limits"]["input_json"]["max_nodes_including_keys"]
    assert 8192 < assert_plain_json_and_count_nodes(result) <= result["limits"]["output_json"]["max_nodes_including_keys"]
    json.dumps(result, ensure_ascii=False, allow_nan=False)
    # The HTTP request byte bound does not cap the actual adapter response.
    assert len(response.content) > LIMIT
    assert result["request_sha256"] == sha256_record(body)
    assert result["evaluation_sha256"] == sha256_record({
        key: value for key, value in result.items() if key != "evaluation_sha256"
    })
    assert "input_sha256" not in result


def test_actual_adapter_once_off_loop_while_heartbeat_progresses(client, monkeypatch):
    body = {"evaluation": adapter.EVALUATION, **inputs()}
    direct = adapter.evaluate_tabulated_hover_bemt(body)
    adapter_spy, core_spy = spy_models(monkeypatch)
    entered, progressed = threading.Event(), threading.Event()
    worker_threads, loop_threads, dispatches = [], [], []
    actual_dispatch = api.run_in_threadpool

    def observed(payload):
        worker_threads.append(threading.get_ident())
        entered.set()
        assert progressed.wait(timeout=5), "The event loop did not progress while the adapter waited."
        return adapter_spy(payload)

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
            return await actual_dispatch(function, *args)

    monkeypatch.setattr(adapter, "evaluate_tabulated_hover_bemt", observed)
    monkeypatch.setattr(api, "run_in_threadpool", dispatch)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200, response.text
    assert response.json() == direct
    assert dispatches == [(observed, (body,))]
    assert len(worker_threads) == len(loop_threads) == 1
    assert worker_threads[0] != loop_threads[0]
    assert progressed.is_set()
    adapter_spy.assert_called_once_with(body)
    core_spy.assert_called_once_with(**inputs())
