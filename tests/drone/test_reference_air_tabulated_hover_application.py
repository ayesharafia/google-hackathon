"""HTTP transport checks against actual V106 results and component calls."""

import json
import threading
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock

import anyio
import pytest

from physimesh.api import reference_air_tabulated_hover as api
from physimesh.api.settings import Settings, load_settings
from physimesh.drone import reference_air_tabulated_hover as workflow
from physimesh.drone import tabulated_hover_bemt_request as child
from physimesh.drone.provenance import sha256_record

from .test_model_graph_application import client as client  # noqa: PLC0414 -- shared fixture
from .test_reference_air_tabulated_hover import assert_atomic, request
from .test_tabulated_hover_bemt_request import assert_plain_json_and_count_nodes

PATH = "/api/drone/reference-air-tabulated-hover/evaluate"
CATALOG = "/api/drone/reference-air-tabulated-hover/catalog"
LIMIT = 131072
INVALID = {"detail": "Invalid reference air tabulated hover request."}
TOO_LARGE = {"detail": "request byte budget exceeded"}


def spies(monkeypatch):
    targets = ((workflow, "evaluate_reference_air_tabulated_hover"),
               (workflow, "reference_air_properties"),
               (workflow, "evaluate_tabulated_hover_bemt"),
               (child, "solve_tabulated_hover"))
    result = []
    for module, name in targets:
        spy = Mock(wraps=getattr(module, name))
        monkeypatch.setattr(module, name, spy)
        result.append(spy)
    return result


def assert_full_hashes(result, body):
    """Check every returned data binding without modifying the response."""
    raw_air, rotor = result["outputs"]["air"], result["outputs"]["rotor"]
    injected = {**body["rotor_template"], "density_kg_m3": raw_air["state"]["density_kg_m3"]}
    assert result["request_sha256"] == sha256_record(body)
    for envelope in (result, rotor):
        assert "input_sha256" not in envelope
        assert envelope["evaluation_sha256"] == sha256_record({
            k: v for k, v in envelope.items() if k != "evaluation_sha256"
        })
    assert rotor["request_sha256"] == sha256_record(injected)
    assert result["stages"] == [
        {"stage": "air", "inputs": body["air"], "inputs_sha256": sha256_record(body["air"]),
         "result_sha256": sha256_record(raw_air)},
        {"stage": "rotor", "inputs": injected, "inputs_sha256": sha256_record(injected),
         "result_sha256": sha256_record(rotor)},
    ]
    assert result["transfers"] == [{
        "from_stage": "air", "from_field": "state.density_kg_m3", "to_stage": "rotor",
        "to_field": "density_kg_m3", "value": raw_air["state"]["density_kg_m3"], "unit": "kg/m^3",
        "producer_result_sha256": sha256_record(raw_air), "consumer_request_sha256": sha256_record(injected),
    }]
    assert result["output_units"]["air"].keys() == raw_air.keys()
    assert result["output_units"]["air"]["state"].keys() == raw_air["state"].keys()
    assert result["output_units"]["rotor"] == rotor["output_units"]
    assert result["output_units"]["rotor"].keys() == rotor["outputs"].keys()


def test_catalog_fresh_actual_nested(client, monkeypatch):
    actual = workflow.reference_air_tabulated_hover_catalog
    baseline = actual()
    returned = []

    def capture():
        value = actual()
        returned.append(value)
        return value

    spy = Mock(side_effect=capture)
    monkeypatch.setattr(workflow, "reference_air_tabulated_hover_catalog", spy)
    first = client.get(CATALOG, headers=client.auth_headers)
    assert first.status_code == 200
    assert set(first.json()) == {"catalog", "transport"}
    assert first.json()["catalog"] == baseline == returned[0]
    transport = deepcopy(first.json()["transport"])
    returned[0]["limits"]["input_json"]["max_depth"] = -1
    returned[0]["output_field_units"]["air"]["state"]["density_kg_m3"] = "bad"
    returned[0]["input_units"]["rotor_template"]["stations"]["chord_m"] = "bad"
    second = client.get(CATALOG, headers=client.auth_headers)
    assert second.status_code == 200
    assert second.json() == {"catalog": baseline, "transport": transport}
    assert spy.call_count == 2


def test_full_post_exact_direct_hashes_and_calls(client, monkeypatch):
    body = request()
    direct = workflow.evaluate_reference_air_tabulated_hover(body)
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    observed = spies(monkeypatch)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    assert result == direct
    for spy in observed:
        spy.assert_called_once()
    observed[0].assert_called_once_with(body)
    observed[1].assert_called_once_with(**body["air"])
    injected = {**body["rotor_template"], "density_kg_m3": result["outputs"]["air"]["state"]["density_kg_m3"]}
    observed[2].assert_called_once_with(injected)
    observed[3].assert_called_once_with(**{k: v for k, v in injected.items() if k != "evaluation"})
    assert result["request_sha256"] == sha256_record(body)
    assert result["evaluation_sha256"] == sha256_record({
        k: v for k, v in result.items() if k != "evaluation_sha256"
    })
    assert "input_sha256" not in result
    assert_full_hashes(result, body)


def test_preflight_invalid_is_workflow_status(client, monkeypatch):
    body = request()
    body["air"]["altitude_m"] = -1
    direct = workflow.evaluate_reference_air_tabulated_hover(body)
    observed = spies(monkeypatch)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct
    assert_atomic(response.json(), "MODEL_INAPPLICABLE")
    observed[0].assert_called_once_with(body)
    for spy in observed[1:]:
        spy.assert_not_called()


@pytest.mark.parametrize("altitude,kind", [
    (0.0, "geometric"), (10000.0, "geometric"), (30000.0, "geometric"),
    (11000.0, "geopotential"), (20000.0, "geopotential"), (30000.0, "geopotential"),
])
def test_actual_altitude_boundaries_full_equality(client, monkeypatch, altitude, kind):
    body = request(altitude, kind)
    direct = workflow.evaluate_reference_air_tabulated_hover(body)
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    observed = spies(monkeypatch)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct
    assert_full_hashes(response.json(), body)
    for spy in observed:
        spy.assert_called_once()


def test_actual_zero_angle_keeps_positive_profile_power(client, monkeypatch):
    body = request()
    for station in body["rotor_template"]["stations"]:
        station["blade_angle_rad"] = 0.0
    direct = workflow.evaluate_reference_air_tabulated_hover(body)
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    observed = spies(monkeypatch)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    assert result == direct
    assert_full_hashes(result, body)
    outputs = result["outputs"]["rotor"]["outputs"]
    assert outputs["blade_angle_rad"] == outputs["inflow_ratio"] == [0.0] * body["rotor_template"]["annuli"]
    assert outputs["thrust_n"] == outputs["thrust_coefficient"] == outputs["induced_power_coefficient"] == 0.0
    assert outputs["shaft_power_coefficient"] == outputs["profile_power_coefficient"] > 0.0
    assert outputs["shaft_power_w"] > 0.0
    for spy in observed:
        spy.assert_called_once()


def test_actual_maximum_shape_full_response_exceeds_request_budget(client, monkeypatch):
    stations = [{"radius_m": i / 255, "chord_m": 0.05, "blade_angle_rad": 0.08} for i in range(256)]
    body = request(20000.0, stations=stations, annuli=2048, blade_count=32)
    direct = workflow.evaluate_reference_air_tabulated_hover(body)
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
    assert len(encoded) < LIMIT
    observed = spies(monkeypatch)
    response = client.post(PATH, content=encoded, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    assert result == direct
    assert_full_hashes(result, body)
    outputs = result["outputs"]["rotor"]["outputs"]
    assert outputs["annuli"] == 2048 and len(outputs["stations"]) == 256
    for name, value in outputs.items():
        if type(value) is list and name != "stations":
            assert len(value) == 2048, name
    assert assert_plain_json_and_count_nodes(body) <= 16384
    assert 18000 < assert_plain_json_and_count_nodes(result) <= 65536
    workflow._JSON(result, workflow._LIMITS["output_json"])
    child._json_walk(result["outputs"]["rotor"], child._LIMITS["output_json"])
    assert len(response.content) > LIMIT
    for spy in observed:
        spy.assert_called_once()


@pytest.mark.parametrize("defect,status,accepted,component_calls", [
    ("unsupported", "SOLVER_UNSUPPORTED", False, 0),
    ("missing", "MODEL_INAPPLICABLE", False, 0),
    ("extra", "MODEL_INAPPLICABLE", False, 0),
    ("density", "MODEL_INAPPLICABLE", False, 0),
    ("altitude-bool", "MODEL_INAPPLICABLE", False, 0),
    ("altitude-over", "MODEL_INAPPLICABLE", False, 0),
    ("radius", "MODEL_INAPPLICABLE", True, 1),
    ("chord", "MODEL_INAPPLICABLE", True, 1),
    ("root-cutout", "MODEL_INAPPLICABLE", True, 1),
])
def test_actual_status_nullable_hash_matrix(client, monkeypatch, defect, status, accepted, component_calls):
    body = request()
    if defect == "unsupported":
        body["evaluation"] = "unsupported"
    elif defect == "missing":
        del body["rotor_template"]["geometry_source"]
    elif defect == "extra":
        body["extra"] = True
    elif defect == "density":
        body["rotor_template"]["density_kg_m3"] = 1.225
    elif defect == "altitude-bool":
        body["air"]["altitude_m"] = True
    elif defect == "altitude-over":
        body["air"]["altitude_m"] = 30000.01
    elif defect == "radius":
        body["rotor_template"]["radius_m"] = -1.0
    elif defect == "chord":
        body["rotor_template"]["stations"][0]["chord_m"] = -0.01
    else:
        body["rotor_template"]["root_cutout_m"] = 0.0
    direct = workflow.evaluate_reference_air_tabulated_hover(body)
    observed = spies(monkeypatch)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct
    assert_atomic(response.json(), status, body if accepted else None)
    assert "input_sha256" not in response.json()
    observed[0].assert_called_once_with(body)
    assert [spy.call_count for spy in observed[1:]] == [component_calls] * 3


@pytest.mark.parametrize("component", ["air", "child"])
def test_coherent_forged_actual_components_are_workflow_failures(client, monkeypatch, component):
    body = request(20000.0)
    baseline = workflow.evaluate_reference_air_tabulated_hover(body)
    assert baseline["status"] == "COMPUTED_EXPERIMENTAL"
    if component == "air":
        actual = workflow.reference_air_properties(**body["air"])
        forged = replace(actual, state=replace(
            actual.state, pressure_pa=actual.state.pressure_pa * 1.01,
            density_kg_m3=actual.state.density_kg_m3 * 1.01,
        ))
        monkeypatch.setattr(workflow, "reference_air_properties", Mock(return_value=forged))
    else:
        forged = deepcopy(baseline["outputs"]["rotor"])
        for name in ("thrust_n", "shaft_power_w", "shaft_torque_nm"):
            forged["outputs"][name] *= 1.01
        # Negative fixture: keep its digest coherent so validation must inspect actual loads.
        forged["evaluation_sha256"] = sha256_record({
            k: v for k, v in forged.items() if k != "evaluation_sha256"
        })
        monkeypatch.setattr(workflow, "evaluate_tabulated_hover_bemt", Mock(return_value=forged))
    direct = workflow.evaluate_reference_air_tabulated_hover(body)
    observed = spies(monkeypatch)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct
    assert_atomic(response.json(), "EXECUTION_FAILED", body)
    assert "input_sha256" not in response.json()
    assert [spy.call_count for spy in observed] == ([1, 1, 0, 0] if component == "air" else [1, 1, 1, 0])


@pytest.mark.parametrize("raw", [
    b'{"evaluation":1,"evaluation":2}',
    b'{"air":{"altitude_m":0,"altitude_m":1}}',
    b'{"rotor_template":{"stations":[{"chord_m":0,"chord_m":1}]}}',
    b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}', b'{"x":1e9999}',
    b'{"x":"\xff"}', b'{"x":"\\ud800"}',
    b'[]', b'null', b'1', b'true', b'"text"', b'{"PRIVATE_SENTINEL":',
])
def test_strict_parser_generic_refusal_zero_calls(client, monkeypatch, raw):
    observed = spies(monkeypatch)
    response = client.post(PATH, content=raw, headers=client.auth_headers)
    assert response.status_code == 422
    assert response.json() == INVALID
    for spy in observed:
        spy.assert_not_called()


@pytest.mark.parametrize("authorization", [{}, {"Authorization": "Bearer wrong-token"}])
def test_missing_wrong_auth_zero_calls(client, monkeypatch, authorization):
    observed = spies(monkeypatch)
    assert client.get(CATALOG, headers=authorization).status_code == 401
    for raw in (b'{"PRIVATE_SENTINEL":', json.dumps(request()).encode()):
        response = client.post(PATH, content=raw, headers=authorization)
        assert response.status_code == 401
        assert "PRIVATE_SENTINEL" not in response.text
    for spy in observed:
        spy.assert_not_called()


def raw_chunks(client, chunks, *, declared=None, chunked=True, authorization=None, path=PATH):
    """Send real ASGI chunks without a client normalizing the framing headers."""
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
            "method": "POST", "scheme": "http", "path": path, "raw_path": path.encode(),
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

        with anyio.fail_after(10):
            await client.app(scope, receive, send)
        start = next(message for message in responses if message["type"] == "http.response.start")
        body = b"".join(message.get("body", b"") for message in responses
                        if message["type"] == "http.response.body")
        return start["status"], json.loads(body) if body else None, delivered, dict(start["headers"])

    return client.portal.call(run)


def test_declared_length_and_actual_bytes_are_independent(client, monkeypatch):
    observed = spies(monkeypatch)
    response = client.post(PATH, content=b" " * LIMIT, headers=client.auth_headers)
    assert response.status_code == 422 and response.json() == INVALID
    assert response.request.headers["content-length"] == str(LIMIT)
    for declared, expected in (
        (str(LIMIT + 1), 413), ("-1", 413), ("9" * 100, 413),
        ("invalid", 400), ("", 400), ("+1", 400), ("-0", 400), (" 1", 400), ("1", 413),
    ):
        headers = dict(client.auth_headers, **{"Content-Length": declared})
        response = client.post(PATH, content=b" " * (LIMIT + 1), headers=headers)
        assert response.status_code == expected, declared
        assert response.json() == (TOO_LARGE if expected == 413 else {"detail": "invalid content length"})
    for spy in observed:
        spy.assert_not_called()


@pytest.mark.parametrize("chunked,declared", [(True, None), (False, None), (False, "1"), (False, str(LIMIT))])
def test_actual_chunks_at_and_over_byte_budget(client, monkeypatch, chunked, declared):
    observed = spies(monkeypatch)
    for extra in (0, 1):
        chunks = [b" " * 65536, b" " * 65536] + ([b" "] if extra else [])
        status, result, delivered, _ = raw_chunks(client, chunks, declared=declared, chunked=chunked)
        assert delivered == [len(chunk) for chunk in chunks]
        assert sum(delivered) == LIMIT + extra
        assert status == (413 if extra else 422)
        assert result == (TOO_LARGE if extra else INVALID)
    for spy in observed:
        spy.assert_not_called()


def test_actual_utf8_whitespace_boundary_success_and_one_over(client, monkeypatch):
    # Caller declarations stay unverified, including a multibyte source and unknown uncertainty.
    body = request(geometry_source="Synthetic µ source " + "\U0001f680" * 100,
                   uncertainty_status="unknown")
    direct = workflow.evaluate_reference_air_tabulated_hover(body)
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
    assert len(encoded) > len(encoded.decode("utf-8"))
    padded = encoded + b" " * (LIMIT - len(encoded))
    assert len(padded) == LIMIT
    split = encoded.index("µ".encode()) + 1
    chunks = [padded[:split], padded[split:65536], padded[65536:]]
    observed = spies(monkeypatch)
    response = client.post(PATH, content=padded, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.request.headers["content-length"] == str(LIMIT)
    assert response.json() == direct
    assert_full_hashes(response.json(), body)
    for chunked, declared in ((True, None), (False, None), (False, "1"), (False, str(LIMIT))):
        status, result, delivered, _ = raw_chunks(client, chunks, declared=declared, chunked=chunked)
        assert status == 200
        assert result == direct
        assert delivered == [len(chunk) for chunk in chunks]
        assert sum(delivered) == LIMIT
    assert [spy.call_count for spy in observed] == [5] * 4
    for spy in observed:
        spy.reset_mock()
    response = client.post(PATH, content=padded + b" ", headers=client.auth_headers)
    assert response.status_code == 413 and response.json() == TOO_LARGE
    for chunked, declared in (
        (True, None), (False, None), (False, "1"), (False, str(LIMIT)), (False, str(LIMIT + 1)),
    ):
        status, result, delivered, _ = raw_chunks(client, chunks + [b" "], declared=declared, chunked=chunked)
        assert status == 413 and result == TOO_LARGE
        assert delivered == ([] if declared == str(LIMIT + 1) else [len(chunk) for chunk in chunks] + [1])
    for spy in observed:
        spy.assert_not_called()


@pytest.mark.parametrize("authorization", [{}, {"Authorization": "Bearer wrong-token"}])
def test_auth_precedes_body_consumption_length_checks_and_parser(client, monkeypatch, authorization):
    observed = spies(monkeypatch)
    walk = Mock(wraps=workflow._JSON)
    catalog = Mock(wraps=workflow.reference_air_tabulated_hover_catalog)
    dispatch = Mock(wraps=api.run_in_threadpool)
    monkeypatch.setattr(workflow, "_JSON", walk)
    monkeypatch.setattr(workflow, "reference_air_tabulated_hover_catalog", catalog)
    monkeypatch.setattr(api, "run_in_threadpool", dispatch)
    assert client.get(CATALOG, headers=authorization).status_code == 401
    for declared in (None, "invalid", "-1", str(LIMIT + 1), "1"):
        for path in (PATH, PATH + "/"):
            status, body, delivered, _ = raw_chunks(
                client, [b"PRIVATE_SENTINEL" * 10000], declared=declared,
                chunked=declared is None, authorization=authorization, path=path,
            )
            assert status == 401
            assert "PRIVATE_SENTINEL" not in json.dumps(body)
            assert delivered == []
    for spy in [*observed, walk, catalog, dispatch]:
        spy.assert_not_called()


def test_canonical_methods_slashes_neighbors_and_body_order(client, monkeypatch):
    observed = spies(monkeypatch)
    assert client.get(PATH, headers=client.auth_headers).status_code == 405
    assert client.post(CATALOG, json={}, headers=client.auth_headers).status_code == 405
    for suffix in ("/extra", "-extra", "evil"):
        expected = 403 if client.hosted_test else 404
        assert client.get(CATALOG + suffix, headers=client.auth_headers).status_code == expected
        status, _, delivered, _ = raw_chunks(client, [b"x" * (LIMIT + 1)], path=PATH + suffix)
        assert status == expected
        assert delivered == []
    for path, method in ((CATALOG, "GET"), (PATH, "POST")):
        response = client.request(method, path + "/", headers=client.auth_headers, follow_redirects=False)
        assert response.status_code == (403 if client.hosted_test else 307)
        if not client.hosted_test:
            assert response.headers["location"] == "http://testserver" + path
    for suffix in ("/", "///"):
        for declared in (str(LIMIT + 1), "1"):
            status, body, delivered, headers = raw_chunks(
                client, [b" " * (LIMIT + 1)], path=PATH + suffix, declared=declared, chunked=False,
            )
            expected = 403 if client.hosted_test else (307 if declared == "1" else 413)
            assert status == expected
            assert delivered == []
            if expected == 413:
                assert body == TOO_LARGE
            elif expected == 307:
                assert headers[b"location"].decode() == "http://testserver" + PATH
                canonical, result, delivered, _ = raw_chunks(
                    client, [b" " * (LIMIT + 1)], declared="1", chunked=False,
                )
                assert canonical == 413 and result == TOO_LARGE
                assert delivered == [LIMIT + 1]
    for spy in observed:
        spy.assert_not_called()


@pytest.mark.parametrize("token", [None, "", "   "])
def test_missing_configured_local_token_refuses_startup(tmp_path, token):
    # create_app receives Settings; both direct settings and environment loading reject missing tokens.
    with pytest.raises(ValueError, match="PHYSIMESH_API_TOKEN"):
        Settings(tmp_path, tmp_path / "jobs.sqlite", token, None)
    env = {"PHYSIMESH_DATA_ROOT": str(tmp_path)}
    if token is not None:
        env["PHYSIMESH_API_TOKEN"] = token
    with pytest.raises(ValueError, match="PHYSIMESH_API_TOKEN"):
        load_settings(env)


def test_configured_local_token_is_not_a_hosted_individual_session(client, monkeypatch):
    observed = spies(monkeypatch)
    headers = {"Authorization": "Bearer synthetic-token"}
    response = client.get(CATALOG, headers=headers)
    assert response.status_code == (401 if client.hosted_test else 200)
    for spy in observed:
        spy.assert_not_called()


def test_actual_workflow_once_in_worker_while_event_loop_heartbeat_progresses(client, monkeypatch):
    body = request()
    direct = workflow.evaluate_reference_air_tabulated_hover(body)
    observed = spies(monkeypatch)
    entered, progressed = threading.Event(), threading.Event()
    worker_threads, loop_threads, dispatches = [], [], []
    actual_dispatch = api.run_in_threadpool

    def evaluate(payload):
        worker_threads.append(threading.get_ident())
        entered.set()
        assert progressed.wait(timeout=5), "Event loop did not progress while the workflow waited."
        return observed[0](payload)

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

    monkeypatch.setattr(workflow, "evaluate_reference_air_tabulated_hover", evaluate)
    monkeypatch.setattr(api, "run_in_threadpool", dispatch)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct
    assert dispatches == [(evaluate, (body,))]
    assert len(worker_threads) == len(loop_threads) == 1
    assert worker_threads[0] != loop_threads[0] and progressed.is_set()
    for spy in observed:
        spy.assert_called_once()
    observed[0].assert_called_once_with(body)
