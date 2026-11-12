"""Bounded HTTP transport against actual accepted V110 results."""

import json
import threading
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock

import anyio
import pytest
from fastapi.testclient import TestClient

from physimesh.api import reference_air_tabulated_hover_thrust_target as api
from physimesh.api.sessions import COOKIE
from physimesh.api.settings import Settings, load_settings
from physimesh.drone import reference_air_tabulated_hover_thrust_target as workflow
from physimesh.drone import tabulated_hover_bemt_request as forward
from physimesh.drone.provenance import sha256_record

from .test_model_graph_application import client as client  # noqa: PLC0414 -- shared fixture
from .test_reference_air_tabulated_hover_thrust_target import (
    actual_baseline,
    actual_spies,
    assert_atomic,
    assert_success,
    forge_inverse,
)

PATH = api.PREFIX + "/evaluate"
CATALOG = api.PREFIX + "/catalog"
LIMIT = 131072
INVALID = {"detail": "Invalid reference air tabulated hover thrust target request."}
TOO_LARGE = {"detail": "request byte budget exceeded"}


def spies(monkeypatch):
    outer = Mock(wraps=workflow.evaluate_reference_air_tabulated_hover_thrust_target)
    monkeypatch.setattr(workflow, "evaluate_reference_air_tabulated_hover_thrust_target", outer)
    return [outer, *actual_spies(monkeypatch)]


def assert_full_hashes(result, body):
    air, target = result["outputs"]["air"], result["outputs"]["target"]
    injected = deepcopy(body["target_template"])
    injected["rotor_template"]["density_kg_m3"] = air["state"]["density_kg_m3"]
    assert_success(result, body, air, injected, target)
    forward = target["outputs"]["actual_forward_result"]
    for envelope in (result, target, forward):
        assert "input_sha256" not in envelope
        assert envelope["evaluation_sha256"] == sha256_record({
            key: value for key, value in envelope.items() if key != "evaluation_sha256"
        })
    assert target["request_sha256"] == sha256_record(injected)
    assert forward["request_sha256"] == sha256_record(target["outputs"]["actual_forward_request"])
    selected = target["outputs"]["angular_speed_rad_s"]
    retained = next(row for row in target["trace"] if row["angular_speed_rad_s"] == selected)
    assert retained["full_actual_result_sha256"] == sha256_record(forward)


def test_catalog_fresh_actual_nested(client, monkeypatch):
    actual = workflow.reference_air_tabulated_hover_thrust_target_catalog
    baseline = actual()
    returned = []

    def capture():
        result = actual()
        returned.append(result)
        return result

    call = Mock(side_effect=capture)
    monkeypatch.setattr(workflow, "reference_air_tabulated_hover_thrust_target_catalog", call)
    first = client.get(CATALOG, headers=client.auth_headers)
    assert first.status_code == 200
    assert set(first.json()) == {"catalog", "transport"}
    assert first.json()["catalog"] == baseline == returned[0]
    returned[0]["limits"]["core_work"]["annuli_max"] = 0
    returned[0]["limitations"].clear()
    second = client.get(CATALOG, headers=client.auth_headers)
    assert second.status_code == 200
    assert second.json()["catalog"] == baseline
    assert returned[0] is not returned[1]
    assert call.call_count == 2
    limits = second.json()["transport"]["limits"]
    assert limits["body_bytes"] == LIMIT
    assert limits["input_json_reference"] == "catalog.limits.input_json"
    assert limits["response_json_reference"] == "catalog.limits.output_json"


def test_actual_full_post_hashes_and_call_counts(client, monkeypatch):
    body, air, injected, inverse = actual_baseline()
    direct = workflow.evaluate_reference_air_tabulated_hover_thrust_target(body)
    observed = spies(monkeypatch)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct
    assert_success(response.json(), body, air, injected, inverse)
    assert_full_hashes(response.json(), body)
    assert [spy.call_count for spy in observed] == [1, 1, 1, 3, 3, 1]
    observed[0].assert_called_once_with(body)
    observed[2].assert_called_once_with(injected)


def test_actual_structured_domain_refusal(client, monkeypatch):
    body, _, _, _ = actual_baseline()
    body["target_template"]["rotor_template"]["stations"][0]["chord_m"] = -1.0
    direct = workflow.evaluate_reference_air_tabulated_hover_thrust_target(body)
    observed = spies(monkeypatch)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct
    assert_atomic(response.json(), "MODEL_INAPPLICABLE", 1, body)
    assert [spy.call_count for spy in observed] == [1, 1, 1, 1, 1, 1]


@pytest.mark.parametrize("altitude,kind,omega", [
    (0, "geometric", 50.0), (10000, "geometric", 100.0),
    (30000, "geometric", 150.0), (11000, "geopotential", 50.0),
    (20000, "geopotential", 100.0), (30000, "geopotential", 150.0),
])
def test_actual_altitude_endpoint_full_equality(client, monkeypatch, altitude, kind, omega):
    body, air, injected, inverse = actual_baseline(altitude, kind, omega)
    direct = workflow.evaluate_reference_air_tabulated_hover_thrust_target(body)
    observed = spies(monkeypatch)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct
    assert_success(response.json(), body, air, injected, inverse)
    assert_full_hashes(response.json(), body)
    count = inverse["evaluation_count"]
    assert count == (3 if omega == 100.0 else 2)
    assert [spy.call_count for spy in observed] == [1, 1, 1, count, count, 1]


def test_actual_maximum_shape_response_exceeds_request_bytes(client, monkeypatch):
    body, _, _, _ = actual_baseline(omega=50.0)
    rotor = body["target_template"]["rotor_template"]
    rotor.update(annuli=512, blade_count=32, stations=[
        {"radius_m": index / 255, "chord_m": 0.04, "blade_angle_rad": 0.08}
        for index in range(256)
    ])
    body["target_template"]["max_evaluations"] = 64
    actual_air = workflow.reference_air_properties(**body["air"])
    known = forward.evaluate_tabulated_hover_bemt({
        **rotor, "density_kg_m3": actual_air.state.density_kg_m3, "angular_speed_rad_s": 50.0,
    })
    assert known["status"] == "COMPUTED_EXPERIMENTAL"
    body["target_template"]["target_thrust_n"] = known["outputs"]["thrust_n"]
    direct = workflow.evaluate_reference_air_tabulated_hover_thrust_target(body)
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
    assert len(encoded) < LIMIT
    observed = spies(monkeypatch)
    response = client.post(PATH, content=encoded, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    assert result == direct
    assert_full_hashes(result, body)
    selected = result["outputs"]["target"]["outputs"]["actual_forward_result"]
    assert len(selected["outputs"]["radii_m"]) == 512
    assert len(selected["outputs"]["stations"]) == 256
    selected_request = result["outputs"]["target"]["outputs"]["actual_forward_request"]
    assert selected_request["blade_count"] == 32
    for call in observed[4].call_args_list:
        assert call.kwargs["blade_count"] == 32
    assert body["target_template"]["max_evaluations"] * rotor["annuli"] == 32768
    assert [spy.call_count for spy in observed] == [1, 1, 1, 2, 2, 1]
    workflow._JSON(result, workflow._LIMITS["output_json"])
    assert workflow._LIMITS["output_json"]["max_nodes_including_keys"] == LIMIT
    assert len(response.content) > LIMIT


@pytest.mark.parametrize("case,status,count,accepted", [
    ("unsupported", "SOLVER_UNSUPPORTED", 0, False),
    ("missing", "MODEL_INAPPLICABLE", 0, False),
    ("extra", "MODEL_INAPPLICABLE", 0, False),
    ("density", "MODEL_INAPPLICABLE", 0, False),
    ("altitude_bool", "MODEL_INAPPLICABLE", 0, False),
    ("altitude_over", "MODEL_INAPPLICABLE", 0, False),
    ("work", "MODEL_INAPPLICABLE", 0, False),
    ("chord", "MODEL_INAPPLICABLE", 1, True),
    ("zero_angle", "TARGET_NOT_BRACKETED", 2, True),
    ("budget", "ITERATION_LIMIT", 2, True),
])
def test_actual_status_nullable_count_matrix(client, monkeypatch, case, status, count, accepted):
    body, _, _, _ = actual_baseline()
    target = body["target_template"]
    rotor = target["rotor_template"]
    if case == "unsupported":
        body["evaluation"] = "other"
    elif case == "missing":
        del rotor["geometry_source"]
    elif case == "extra":
        body["extra"] = True
    elif case == "density":
        rotor["density_kg_m3"] = 1.225
    elif case == "altitude_bool":
        body["air"]["altitude_m"] = True
    elif case == "altitude_over":
        body["air"]["altitude_m"] = 30000.01
    elif case == "work":
        rotor["annuli"] = 513
        target["max_evaluations"] = 64
    elif case == "chord":
        rotor["stations"][0]["chord_m"] = -1.0
    elif case == "zero_angle":
        for station in rotor["stations"]:
            station["blade_angle_rad"] = 0.0
    else:
        target["max_evaluations"] = 2
    direct = workflow.evaluate_reference_air_tabulated_hover_thrust_target(body)
    observed = spies(monkeypatch)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct
    assert_atomic(response.json(), status, count, body if accepted else None)
    assert "input_sha256" not in response.json()
    assert [spy.call_count for spy in observed] == (
        [1, 1, 1, count, count, 1] if accepted else [1, 0, 0, 0, 0, 0]
    )


@pytest.mark.parametrize("component", ["air", "inverse"])
def test_coherent_actual_component_forgery_is_atomic_failure(client, monkeypatch, component):
    body, _, _, inverse = actual_baseline()
    if component == "air":
        actual = workflow.reference_air_properties(**body["air"])
        forged = replace(actual, state=replace(
            actual.state, pressure_pa=actual.state.pressure_pa * 1.01,
            density_kg_m3=actual.state.density_kg_m3 * 1.01,
        ))
        monkeypatch.setattr(workflow, "reference_air_properties", Mock(return_value=forged))
    else:
        # Mutate and rehash an actual inverse including its selected full child.
        forge_inverse(inverse, "selected_child")
        monkeypatch.setattr(workflow, "evaluate_tabulated_hover_thrust_target", Mock(return_value=inverse))
    direct = workflow.evaluate_reference_air_tabulated_hover_thrust_target(body)
    observed = spies(monkeypatch)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct
    assert_atomic(response.json(), "EXECUTION_FAILED", 0, body)
    assert [spy.call_count for spy in observed] == (
        [1, 1, 0, 0, 0, 0] if component == "air" else [1, 1, 1, 0, 0, 1]
    )


@pytest.mark.parametrize("raw", [
    b'{"evaluation":1,"evaluation":2}',
    b'{"air":{"altitude_m":0,"altitude_m":1}}',
    b'{"target_template":{"rotor_template":{"stations":[{"chord_m":0,"chord_m":1}]}}}',
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
def test_missing_wrong_protected_auth_zero_calls(client, monkeypatch, authorization):
    body, _, _, _ = actual_baseline()
    observed = spies(monkeypatch)
    assert client.get(CATALOG, headers=authorization).status_code == 401
    for raw in (b'{"PRIVATE_SENTINEL":', json.dumps(body).encode()):
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
    body, _, _, _ = actual_baseline()
    body["target_template"]["rotor_template"].update(
        geometry_source="Synthetic µ source " + "\U0001f680" * 100, uncertainty_status="unknown",
    )
    direct = workflow.evaluate_reference_air_tabulated_hover_thrust_target(body)
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
    assert [spy.call_count for spy in observed] == [5, 5, 5, 15, 15, 5]
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
    catalog = Mock(wraps=workflow.reference_air_tabulated_hover_thrust_target_catalog)
    dispatch = Mock(wraps=api.run_in_threadpool)
    monkeypatch.setattr(workflow, "_JSON", walk)
    monkeypatch.setattr(workflow, "reference_air_tabulated_hover_thrust_target_catalog", catalog)
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
    body, _, _, _ = actual_baseline()
    direct = workflow.evaluate_reference_air_tabulated_hover_thrust_target(body)
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

    monkeypatch.setattr(workflow, "evaluate_reference_air_tabulated_hover_thrust_target", evaluate)
    monkeypatch.setattr(api, "run_in_threadpool", dispatch)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct
    assert dispatches == [(evaluate, (body,))]
    assert len(worker_threads) == len(loop_threads) == 1
    assert worker_threads[0] != loop_threads[0] and progressed.is_set()
    assert [spy.call_count for spy in observed] == [1, 1, 1, 3, 3, 1]
    observed[0].assert_called_once_with(body)


@pytest.mark.parametrize("defect", ["depth", "nodes", "items", "string", "integer"])
def test_actual_outer_input_walker_refuses_before_dispatch(client, monkeypatch, defect):
    body, _, _, _ = actual_baseline()
    if defect == "depth":
        nested = 0
        for _ in range(12):
            nested = [nested]
        body["extra"] = nested
    elif defect == "nodes":
        body["extra"] = [[0] * 255 for _ in range(130)]
    elif defect == "items":
        body["extra"] = [0] * 257
    elif defect == "string":
        body["target_template"]["rotor_template"]["geometry_source"] = "x" * 2001
    else:
        body["air"]["altitude_m"] = 1 << 1023
    encoded = json.dumps(body).encode()
    assert len(encoded) < LIMIT
    observed = spies(monkeypatch)
    walker = Mock(wraps=workflow._JSON)
    dispatch = Mock(wraps=api.run_in_threadpool)
    monkeypatch.setattr(workflow, "_JSON", walker)
    monkeypatch.setattr(api, "run_in_threadpool", dispatch)
    response = client.post(PATH, content=encoded, headers=client.auth_headers)
    assert response.status_code == 422 and response.json() == INVALID
    walker.assert_called_once_with(body, workflow._LIMITS["input_json"])
    for spy in [*observed, dispatch]:
        spy.assert_not_called()


@pytest.fixture
def public_client(tmp_path, monkeypatch):
    from physimesh.api import app as app_module

    (tmp_path / "web").mkdir()
    monkeypatch.setattr(app_module, "__file__", str(tmp_path / "src/physimesh/api/app.py"))
    settings = Settings(tmp_path, tmp_path / "jobs.sqlite", "", None, public_access=True)
    with TestClient(app_module.create_app(settings)) as connection:
        yield connection


def test_public_local_tokenless_routes_origin_and_no_agent(public_client, monkeypatch):
    body, _, _, _ = actual_baseline()
    direct = workflow.evaluate_reference_air_tabulated_hover_thrust_target(body)
    observed = spies(monkeypatch)
    assert public_client.app.state.settings.api_token == ""
    assert public_client.app.state.browser_sessions is None
    assert public_client.get(CATALOG).json()["catalog"] == (
        workflow.reference_air_tabulated_hover_thrust_target_catalog()
    )
    for headers in ({}, {"Origin": "http://testserver"}):
        response = public_client.post(PATH, json=body, headers=headers)
        assert response.status_code == 200 and response.json() == direct
        assert_full_hashes(response.json(), body)
    assert [spy.call_count for spy in observed] == [2, 2, 2, 6, 6, 2]
    for spy in observed:
        spy.reset_mock()
    response = public_client.post(PATH, content=b"{PRIVATE", headers={"Origin": "https://other.example"})
    assert response.status_code == 403
    for path in ("/api/drone/agent/catalog", "/api/drone/agent/anything"):
        assert public_client.get(path).status_code == 403
    for spy in observed:
        spy.assert_not_called()


def test_public_mode_configuration_is_local_only(tmp_path):
    settings = load_settings({"PHYSIMESH_DATA_ROOT": str(tmp_path), "PHYSIMESH_PUBLIC_ACCESS": "1"})
    assert settings.public_access and settings.api_token == ""
    with pytest.raises(ValueError, match="only in local mode"):
        Settings(tmp_path, tmp_path / "jobs.sqlite", "", None, hosted_mode=True, public_access=True)
    with pytest.raises(ValueError, match="only in local mode"):
        load_settings({"PHYSIMESH_DATA_ROOT": str(tmp_path), "PHYSIMESH_PUBLIC_ACCESS": "1",
                       "PHYSIMESH_MODE": "hosted"})


@pytest.fixture(params=[False, True], ids=["local-cookie", "hosted-cookie"])
def cookie_client(tmp_path, monkeypatch, request):
    from physimesh.api import app as app_module
    from physimesh.platform.hosted_signin import HOSTED_COOKIE

    (tmp_path / "web").mkdir()
    monkeypatch.setattr(app_module, "__file__", str(tmp_path / "src/physimesh/api/app.py"))
    hosted = request.param
    options = {}
    if hosted:
        options = {
            "hosted_signin_issuer": "https://issuer.example",
            "hosted_signin_discovery_url": "https://issuer.example/.well-known/openid-configuration",
            "hosted_signin_client_id": "browser-fixture",
            "hosted_signin_origin": "https://testserver",
        }
    app = app_module.create_app(Settings(
        tmp_path, tmp_path / "jobs.sqlite", "synthetic-token", None, hosted_mode=hosted, **options,
    ))
    with TestClient(app, base_url="https://testserver") as connection:
        if hosted:
            app.state.identity.provision("cookie@example.test", issuer="https://issuer.example", subject="fixture")
            token = app.state.hosted_signin.issue({"iss": "https://issuer.example", "sub": "fixture"})
            connection.cookies.set(HOSTED_COOKIE, token)
            app.state.identity.provision("bearer@example.test", password="synthetic-fixture-password")
            bearer = app.state.identity.login(
                "bearer@example.test", password="synthetic-fixture-password",
            )["token"]
        else:
            bearer = "synthetic-token"
            response = connection.post("/api/session", headers={
                "Authorization": f"Bearer {bearer}", "Origin": "https://testserver",
            })
            assert response.status_code == 200
            assert COOKIE in connection.cookies
        connection.auth_headers = {"Authorization": f"Bearer {bearer}"}
        connection.hosted_test = hosted
        yield connection


def test_real_cookie_or_bearer_origin_and_explicit_bad_header(cookie_client, monkeypatch):
    body, _, _, _ = actual_baseline()
    direct = workflow.evaluate_reference_air_tabulated_hover_thrust_target(body)
    observed = spies(monkeypatch)
    catalog = cookie_client.get(CATALOG)
    assert catalog.status_code == 200
    assert catalog.json()["catalog"] == workflow.reference_air_tabulated_hover_thrust_target_catalog()
    for headers in ({}, {"Origin": "https://other.example"}):
        response = cookie_client.post(PATH, content=b"{PRIVATE", headers=headers)
        assert response.status_code == 403
    for authorization in ("Bearer wrong-token", "Basic invalid"):
        headers = {"Authorization": authorization, "Origin": "https://testserver"}
        assert cookie_client.get(CATALOG, headers=headers).status_code == 401
        assert cookie_client.post(PATH, content=b"{PRIVATE", headers=headers).status_code == 401
    # A bad explicit Authorization cannot fall back to the remembered cookie.
    if not cookie_client.hosted_test:
        assert cookie_client.get(CATALOG, headers={"Authorization": ""}).status_code == 401
    for spy in observed:
        spy.assert_not_called()
    for headers in (
        {"Origin": "https://testserver"},
        dict(cookie_client.auth_headers, Origin="https://other.example"),
    ):
        response = cookie_client.post(PATH, json=body, headers=headers)
        assert response.status_code == 200 and response.json() == direct
        assert_full_hashes(response.json(), body)
    assert [spy.call_count for spy in observed] == [2, 2, 2, 6, 6, 2]
    # Hosted cookie authentication is chosen when Authorization has no value.
    if cookie_client.hosted_test:
        response = cookie_client.post(PATH, json=body, headers={
            "Authorization": "", "Origin": "https://testserver",
        })
        assert response.status_code == 200 and response.json() == direct
        assert [spy.call_count for spy in observed] == [3, 3, 3, 9, 9, 3]
