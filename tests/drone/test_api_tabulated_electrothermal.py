"""V122 HTTP transport checks against the unchanged V121 workflow."""

import json
import threading
from copy import deepcopy
from unittest.mock import Mock

import anyio
import httpx
import pytest

from physimesh.api import tabulated_electrothermal as api
from physimesh.api.sessions import COOKIE
from physimesh.api.settings import Settings
from physimesh.drone import tabulated_electrothermal as workflow
from physimesh.drone.provenance import sha256_record

from .test_tabulated_electrothermal import json_nodes, request

PATH = api.PREFIX + "/evaluate"
CATALOG = api.PREFIX + "/catalog"
LIMIT = 1048576
INVALID = {"detail": "Invalid tabulated electrothermal request."}
TOO_LARGE = {"detail": "request byte budget exceeded"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(params=[False, True], ids=["local", "hosted"])
async def client(tmp_path, monkeypatch, request):
    from physimesh.api import app as app_module
    from physimesh.api.settings import Settings

    (tmp_path / "web").mkdir()
    monkeypatch.setattr(app_module, "__file__", str(tmp_path / "src/physimesh/api/app.py"))
    app = app_module.create_app(Settings(
        tmp_path, tmp_path / "jobs.sqlite", "synthetic-token", None, hosted_mode=request.param,
    ))
    token = "synthetic-token"
    if request.param:
        app.state.identity.provision("assembly@example.test", password="synthetic-fixture-password")
        token = app.state.identity.login(
            "assembly@example.test", password="synthetic-fixture-password",
        )["token"]
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as connection,
    ):
        connection.app = app
        connection.hosted_test = request.param
        connection.auth_headers = {"Authorization": f"Bearer {token}"}
        with anyio.fail_after(10):
            yield connection


@pytest.mark.anyio
async def test_actual_full_http_equality(client):
    body = request(2)
    direct = workflow.evaluate_tabulated_electrothermal(body)
    assert direct["status"] == "COMPUTED_EXPERIMENTAL", direct["reasons"]
    response = await client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct


@pytest.mark.anyio
async def test_catalog_fresh_without_child_calls(client, monkeypatch):
    actual = workflow.tabulated_electrothermal_catalog
    baseline = actual()
    returned = []

    def capture():
        result = actual()
        returned.append(result)
        return result

    catalog = Mock(side_effect=capture)
    children = []
    for module, name in (
        (workflow, "evaluate_tabulated_electrothermal"),
        (workflow.energy, "evaluate_tabulated_target_dc_energy"),
        (workflow.thermal, "screen_thermal"),
        (workflow.thermal, "integrate_segment"),
    ):
        child = Mock(wraps=getattr(module, name))
        monkeypatch.setattr(module, name, child)
        children.append(child)
    monkeypatch.setattr(workflow, "tabulated_electrothermal_catalog", catalog)
    first = await client.get(CATALOG, headers=client.auth_headers)
    assert first.status_code == 200
    assert set(first.json()) == {"catalog", "transport"}
    assert first.json()["catalog"] == baseline == returned[0]
    catalog.assert_called_once_with()
    returned[0]["energy_catalog"]["output_field_units"].clear()
    returned[0]["limits"]["thermal_input_json"]["max_depth"] = 0
    returned[0]["limitations"].clear()
    second = await client.get(CATALOG, headers=client.auth_headers)
    assert second.status_code == 200
    assert second.json()["catalog"] == baseline
    assert returned[0] is not returned[1]
    assert catalog.call_count == 2
    limits = second.json()["transport"]["limits"]
    assert limits["body_bytes"] == LIMIT
    assert limits["input_json_reference"] == "catalog.limits.input_json"
    assert limits["response_json_reference"] == "catalog.limits.output_json"
    http_status = second.json()["transport"]["http_status"]
    assert "response_contract" not in http_status
    for field in ("status", "reasons", "limitations"):
        assert field in second.json()["catalog"]
        assert f"catalog.{field}" in http_status
    for child in children:
        child.assert_not_called()


@pytest.mark.anyio
async def test_actual_evaluator_once_off_event_loop(client, monkeypatch):
    body = request(2)
    snapshot = deepcopy(body)
    direct = workflow.evaluate_tabulated_electrothermal(body)
    actual_evaluate = workflow.evaluate_tabulated_electrothermal
    actual_dispatch = api.run_in_threadpool
    entered, progressed = threading.Event(), threading.Event()
    worker_threads, loop_threads, dispatches = [], [], []
    evaluator = Mock(wraps=actual_evaluate)
    children = []
    for module, name in (
        (workflow.energy, "evaluate_tabulated_target_dc_energy"),
        (workflow.thermal, "screen_thermal"),
        (workflow.thermal, "integrate_segment"),
    ):
        child = Mock(wraps=getattr(module, name))
        monkeypatch.setattr(module, name, child)
        children.append(child)

    def evaluate(payload):
        worker_threads.append(threading.get_ident())
        entered.set()
        assert progressed.wait(timeout=5), "Event loop did not progress while the workflow waited."
        return evaluator(payload)

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

    monkeypatch.setattr(workflow, "evaluate_tabulated_electrothermal", evaluate)
    monkeypatch.setattr(api, "run_in_threadpool", dispatch)
    response = await client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct
    assert body == snapshot
    assert dispatches == [(evaluate, (body,))]
    assert len(worker_threads) == len(loop_threads) == 1
    assert worker_threads[0] != loop_threads[0] and progressed.is_set()
    evaluator.assert_called_once_with(body)
    children[0].assert_called_once()
    children[1].assert_called_once()
    assert children[2].call_count == len(body["thermal_segments"])


@pytest.mark.anyio
@pytest.mark.parametrize("raw", [
    b'{"evaluation":1,"evaluation":2}',
    b'{"thermal_body":{"mass_kg":1,"mass_kg":2}}',
    b'{"thermal_segments":[{"id":"first","id":"second"}]}',
    b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}', b'{"x":1e9999}',
    b'{"x":"\xff"}', b'{"x":"\\ud800"}',
    b'[]', b'null', b'1', b'true', b'"text"', b'{"PRIVATE_SENTINEL":',
])
async def test_malformed_json_generic_refusal_without_dispatch(client, monkeypatch, raw):
    observed = []
    for module, name in (
        (workflow, "evaluate_tabulated_electrothermal"),
        (workflow.energy, "evaluate_tabulated_target_dc_energy"),
        (workflow.thermal, "screen_thermal"),
        (workflow.thermal, "integrate_segment"),
        (api, "run_in_threadpool"),
    ):
        call = Mock(wraps=getattr(module, name))
        monkeypatch.setattr(module, name, call)
        observed.append(call)
    response = await client.post(PATH, content=raw, headers=client.auth_headers)
    assert response.status_code == 422
    assert response.json() == INVALID
    for call in observed:
        call.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("case,status", [
    ("invalid", "MODEL_INAPPLICABLE"),
    ("unsupported", "SOLVER_UNSUPPORTED"),
])
async def test_actual_invalid_or_unsupported_exact_http_equality(client, monkeypatch, case, status):
    # V121 owns the status vocabulary; the HTTP layer does not rename its refusals.
    body = request(2)
    if case == "invalid":
        body["thermal_body"]["mass_kg"] = -1
    else:
        body["evaluation"] = "unsupported"
    snapshot = deepcopy(body)
    direct = workflow.evaluate_tabulated_electrothermal(body)
    assert direct["status"] == status
    evaluator = Mock(wraps=workflow.evaluate_tabulated_electrothermal)
    energy = Mock(wraps=workflow.energy.evaluate_tabulated_target_dc_energy)
    thermal = Mock(wraps=workflow.thermal.screen_thermal)
    monkeypatch.setattr(workflow, "evaluate_tabulated_electrothermal", evaluator)
    monkeypatch.setattr(workflow.energy, "evaluate_tabulated_target_dc_energy", energy)
    monkeypatch.setattr(workflow.thermal, "screen_thermal", thermal)
    response = await client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct
    assert body == snapshot
    evaluator.assert_called_once_with(body)
    energy.assert_not_called()
    thermal.assert_not_called()


@pytest.mark.anyio
async def test_unknown_hosted_paths_are_forbidden(client, monkeypatch):
    evaluator = Mock(wraps=workflow.evaluate_tabulated_electrothermal)
    catalog = Mock(wraps=workflow.tabulated_electrothermal_catalog)
    monkeypatch.setattr(workflow, "evaluate_tabulated_electrothermal", evaluator)
    monkeypatch.setattr(workflow, "tabulated_electrothermal_catalog", catalog)
    for path in (CATALOG + "/extra", PATH + "-extra", PATH + "/"):
        response = await client.post(path, content=b"{PRIVATE_SENTINEL", headers=client.auth_headers)
        expected = 403 if client.hosted_test else (307 if path.endswith("/") else 404)
        assert response.status_code == expected
        assert "PRIVATE_SENTINEL" not in response.text
    evaluator.assert_not_called()
    catalog.assert_not_called()


# V113 transport/auth patterns, with V121 child ownership and a 1 MiB byte cap.
def spies(monkeypatch):
    observed = []
    for module, name in (
        (workflow, "evaluate_tabulated_electrothermal"),
        (workflow.energy, "evaluate_tabulated_target_dc_energy"),
        (workflow.thermal, "screen_thermal"),
        (workflow.thermal, "integrate_segment"),
    ):
        call = Mock(wraps=getattr(module, name))
        monkeypatch.setattr(module, name, call)
        observed.append(call)
    return observed


def assert_full_hashes(result, body):
    assert result["request_sha256"] == sha256_record(body)
    assert result["evaluation_sha256"] == sha256_record({
        key: value for key, value in result.items() if key != "evaluation_sha256"
    })


async def raw_chunks(client, chunks, *, declared=None, chunked=True, authorization=None, path=PATH):
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

    return await run()



@pytest.mark.anyio
async def test_declared_length_and_actual_bytes_are_independent(client, monkeypatch):
    observed = spies(monkeypatch)
    response = await client.post(PATH, content=b" " * LIMIT, headers=client.auth_headers)
    assert response.status_code == 422 and response.json() == INVALID
    assert response.request.headers["content-length"] == str(LIMIT)
    for declared, expected in (
        (str(LIMIT + 1), 413), ("-1", 413), ("9" * 100, 413),
        ("invalid", 400), ("", 400), ("+1", 400), ("-0", 400), (" 1", 400), ("1", 413),
    ):
        headers = dict(client.auth_headers, **{"Content-Length": declared})
        response = await client.post(PATH, content=b" " * (LIMIT + 1), headers=headers)
        assert response.status_code == expected, declared
        assert response.json() == (TOO_LARGE if expected == 413 else {"detail": "invalid content length"})
    for spy in observed:
        spy.assert_not_called()



@pytest.mark.anyio
@pytest.mark.parametrize("chunked,declared", [(True, None), (False, None), (False, "1"), (False, str(LIMIT))])
async def test_actual_chunks_at_and_over_byte_budget(client, monkeypatch, chunked, declared):
    observed = spies(monkeypatch)
    for extra in (0, 1):
        chunks = [b" " * 65536] * (LIMIT // 65536) + ([b" "] if extra else [])
        status, result, delivered, _ = await raw_chunks(client, chunks, declared=declared, chunked=chunked)
        assert delivered == [len(chunk) for chunk in chunks]
        assert sum(delivered) == LIMIT + extra
        assert status == (413 if extra else 422)
        assert result == (TOO_LARGE if extra else INVALID)
    for spy in observed:
        spy.assert_not_called()



@pytest.mark.anyio
async def test_actual_utf8_whitespace_boundary_success_and_one_over(client, monkeypatch):
    # The source is a caller declaration, without physical qualification.
    body = request(2)
    body["thermal_body"]["property_source"] = "Synthetic µ source " + "\U0001f680" * 100
    direct = workflow.evaluate_tabulated_electrothermal(body)
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
    assert len(encoded) > len(encoded.decode("utf-8"))
    padded = encoded + b" " * (LIMIT - len(encoded))
    assert len(padded) == LIMIT
    split = encoded.index("µ".encode()) + 1
    chunks = [padded[:split], padded[split:65536], padded[65536:]]
    observed = spies(monkeypatch)
    response = await client.post(PATH, content=padded, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.request.headers["content-length"] == str(LIMIT)
    assert response.json() == direct
    assert_full_hashes(response.json(), body)
    for chunked, declared in ((True, None), (False, None), (False, "1"), (False, str(LIMIT))):
        status, result, delivered, _ = await raw_chunks(client, chunks, declared=declared, chunked=chunked)
        assert status == 200
        assert result == direct
        assert delivered == [len(chunk) for chunk in chunks]
        assert sum(delivered) == LIMIT
    assert [spy.call_count for spy in observed] == [5, 5, 5, 5 * len(body["thermal_segments"])]
    for spy in observed:
        spy.reset_mock()
    response = await client.post(PATH, content=padded + b" ", headers=client.auth_headers)
    assert response.status_code == 413 and response.json() == TOO_LARGE
    for chunked, declared in (
        (True, None), (False, None), (False, "1"), (False, str(LIMIT)), (False, str(LIMIT + 1)),
    ):
        status, result, delivered, _ = await raw_chunks(client, chunks + [b" "], declared=declared, chunked=chunked)
        assert status == 413 and result == TOO_LARGE
        assert delivered == ([] if declared == str(LIMIT + 1) else [len(chunk) for chunk in chunks] + [1])
    for spy in observed:
        spy.assert_not_called()



@pytest.mark.anyio
@pytest.mark.parametrize("authorization", [{}, {"Authorization": "Bearer wrong-token"}])
async def test_auth_precedes_body_consumption_length_checks_and_parser(client, monkeypatch, authorization):
    observed = spies(monkeypatch)
    walk = Mock(wraps=workflow._json_walk)
    catalog = Mock(wraps=workflow.tabulated_electrothermal_catalog)
    dispatch = Mock(wraps=api.run_in_threadpool)
    monkeypatch.setattr(workflow, "_json_walk", walk)
    monkeypatch.setattr(workflow, "tabulated_electrothermal_catalog", catalog)
    monkeypatch.setattr(api, "run_in_threadpool", dispatch)
    assert (await client.get(CATALOG, headers=authorization)).status_code == 401
    for declared in (None, "invalid", "-1", str(LIMIT + 1), "1"):
        for path in (PATH, PATH + "/"):
            status, body, delivered, _ = await raw_chunks(
                client, [b"PRIVATE_SENTINEL" * (LIMIT // 16 + 1)], declared=declared,
                chunked=declared is None, authorization=authorization, path=path,
            )
            assert status == 401
            assert "PRIVATE_SENTINEL" not in json.dumps(body)
            assert delivered == []
    for spy in [*observed, walk, catalog, dispatch]:
        spy.assert_not_called()



@pytest.mark.anyio
async def test_canonical_methods_slashes_neighbors_and_body_order(client, monkeypatch):
    observed = spies(monkeypatch)
    assert (await client.get(PATH, headers=client.auth_headers)).status_code == 405
    assert (await client.post(CATALOG, json={}, headers=client.auth_headers)).status_code == 405
    for suffix in ("/extra", "-extra", "evil"):
        expected = 403 if client.hosted_test else 404
        assert (await client.get(CATALOG + suffix, headers=client.auth_headers)).status_code == expected
        status, _, delivered, _ = await raw_chunks(client, [b"x" * (LIMIT + 1)], path=PATH + suffix)
        assert status == expected
        assert delivered == []
    for path, method in ((CATALOG, "GET"), (PATH, "POST")):
        response = await client.request(method, path + "/", headers=client.auth_headers, follow_redirects=False)
        assert response.status_code == (403 if client.hosted_test else 307)
        if not client.hosted_test:
            assert response.headers["location"] == "http://testserver" + path
    for suffix in ("/", "///"):
        for declared in (str(LIMIT + 1), "1"):
            status, body, delivered, headers = await raw_chunks(
                client, [b" " * (LIMIT + 1)], path=PATH + suffix, declared=declared, chunked=False,
            )
            expected = 403 if client.hosted_test else (307 if declared == "1" else 413)
            assert status == expected
            assert delivered == []
            if expected == 413:
                assert body == TOO_LARGE
            elif expected == 307:
                assert headers[b"location"].decode() == "http://testserver" + PATH
                canonical, result, delivered, _ = await raw_chunks(
                    client, [b" " * (LIMIT + 1)], declared="1", chunked=False,
                )
                assert canonical == 413 and result == TOO_LARGE
                assert delivered == [LIMIT + 1]
    for spy in observed:
        spy.assert_not_called()



@pytest.mark.anyio
async def test_configured_local_token_is_not_a_hosted_individual_session(client, monkeypatch):
    observed = spies(monkeypatch)
    headers = {"Authorization": "Bearer synthetic-token"}
    response = await client.get(CATALOG, headers=headers)
    assert response.status_code == (401 if client.hosted_test else 200)
    for spy in observed:
        spy.assert_not_called()



@pytest.mark.anyio
async def test_public_local_tokenless_routes_origin_and_no_agent(public_client, monkeypatch):
    body = request(2)
    direct = workflow.evaluate_tabulated_electrothermal(body)
    observed = spies(monkeypatch)
    assert public_client.app.state.settings.api_token == ""
    assert public_client.app.state.browser_sessions is None
    assert (await public_client.get(CATALOG)).json()["catalog"] == (
        workflow.tabulated_electrothermal_catalog()
    )
    for headers in ({}, {"Origin": "http://testserver"}):
        response = await public_client.post(PATH, json=body, headers=headers)
        assert response.status_code == 200 and response.json() == direct
        assert_full_hashes(response.json(), body)
    assert [spy.call_count for spy in observed] == [2, 2, 2, 2 * len(body["thermal_segments"])]
    for spy in observed:
        spy.reset_mock()
    response = await public_client.post(PATH, content=b"{PRIVATE", headers={"Origin": "https://other.example"})
    assert response.status_code == 403
    for path in ("/api/drone/agent/catalog", "/api/drone/agent/anything"):
        assert (await public_client.get(path)).status_code == 403
    for spy in observed:
        spy.assert_not_called()



@pytest.mark.anyio
async def test_real_cookie_or_bearer_origin_and_explicit_bad_header(cookie_client, monkeypatch):
    body = request(2)
    direct = workflow.evaluate_tabulated_electrothermal(body)
    observed = spies(monkeypatch)
    catalog = await cookie_client.get(CATALOG)
    assert catalog.status_code == 200
    assert catalog.json()["catalog"] == workflow.tabulated_electrothermal_catalog()
    for headers in ({}, {"Origin": "https://other.example"}):
        response = await cookie_client.post(PATH, content=b"{PRIVATE", headers=headers)
        assert response.status_code == 403
    for authorization in ("Bearer wrong-token", "Basic invalid"):
        headers = {"Authorization": authorization, "Origin": "https://testserver"}
        assert (await cookie_client.get(CATALOG, headers=headers)).status_code == 401
        assert (await cookie_client.post(PATH, content=b"{PRIVATE", headers=headers)).status_code == 401
    # A bad explicit Authorization cannot fall back to the remembered cookie.
    if not cookie_client.hosted_test:
        assert (await cookie_client.get(CATALOG, headers={"Authorization": ""})).status_code == 401
    for spy in observed:
        spy.assert_not_called()
    for headers in (
        {"Origin": "https://testserver"},
        dict(cookie_client.auth_headers, Origin="https://other.example"),
    ):
        response = await cookie_client.post(PATH, json=body, headers=headers)
        assert response.status_code == 200 and response.json() == direct
        assert_full_hashes(response.json(), body)
    assert [spy.call_count for spy in observed] == [2, 2, 2, 2 * len(body["thermal_segments"])]
    # Hosted cookie authentication is chosen when Authorization has no value.
    if cookie_client.hosted_test:
        response = await cookie_client.post(PATH, json=body, headers={
            "Authorization": "", "Origin": "https://testserver",
        })
        assert response.status_code == 200 and response.json() == direct
        assert [spy.call_count for spy in observed] == [3, 3, 3, 3 * len(body["thermal_segments"])]



@pytest.fixture
async def public_client(tmp_path, monkeypatch):
    from physimesh.api import app as app_module

    (tmp_path / "web").mkdir()
    monkeypatch.setattr(app_module, "__file__", str(tmp_path / "src/physimesh/api/app.py"))
    app = app_module.create_app(Settings(tmp_path, tmp_path / "jobs.sqlite", "", None, public_access=True))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as connection,
    ):
        connection.app = app
        yield connection



@pytest.fixture(params=[False, True], ids=["local-cookie", "hosted-cookie"])
async def cookie_client(tmp_path, monkeypatch, request):
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
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://testserver") as connection,
    ):
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
            response = await connection.post("/api/session", headers={
                "Authorization": f"Bearer {bearer}", "Origin": "https://testserver",
            })
            assert response.status_code == 200
            assert COOKIE in connection.cookies
        connection.app = app
        connection.auth_headers = {"Authorization": f"Bearer {bearer}"}
        connection.hosted_test = hosted
        yield connection



async def isolated_body_limit(chunks, *, declared=None, chunked=True, path=PATH):
    """Exercise the actual middleware with raw ASGI frames and no workflow.

    The inner Starlette app supplies FastAPI-style JSON exception handling and reads
    the body. This probe tests byte framing only, without parser/model claims.
    """
    from types import SimpleNamespace

    from starlette.applications import Starlette
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    consumed = []

    async def endpoint(incoming):
        raw = await incoming.body()
        consumed.append(len(raw))
        return JSONResponse({"received": len(raw)})

    async def http_error(incoming, error):
        return JSONResponse({"detail": error.detail}, status_code=error.status_code)

    inner = Starlette(
        routes=[Route(PATH, endpoint, methods=["POST"])],
        exception_handlers={StarletteHTTPException: http_error},
    )
    probe = SimpleNamespace(app=api.TabulatedElectrothermalBodyLimit(inner), auth_headers={})
    status, body, delivered, headers = await raw_chunks(
        probe, chunks, declared=declared, chunked=chunked, path=path,
    )
    return status, body, delivered, headers, consumed


@pytest.mark.anyio
@pytest.mark.parametrize("declared,expected", [
    (str(LIMIT + 1), 413), ("+" + str(LIMIT + 1), 413), ("-1", 413), ("9" * 100, 413),
    ("invalid", 400), ("", 400), ("+1", 400), ("-0", 400),
    (" 1", 400), ("1 ", 400), ("1.0", 400),
])
async def test_isolated_declared_length_rejected_before_receive(declared, expected):
    status, result, delivered, _, consumed = await isolated_body_limit(
        [b"PRIVATE_SENTINEL"], declared=declared, chunked=False,
    )
    assert status == expected
    assert result == (TOO_LARGE if expected == 413 else {"detail": "invalid content length"})
    assert delivered == consumed == []


@pytest.mark.anyio
@pytest.mark.parametrize("chunked,declared", [
    (True, None), (False, None), (False, "1"), (False, str(LIMIT)),
])
async def test_isolated_actual_byte_cap_and_early_stream_stop(chunked, declared):
    chunks = [b" " * 65536] * (LIMIT // 65536)
    status, result, delivered, _, consumed = await isolated_body_limit(
        chunks, declared=declared, chunked=chunked,
    )
    assert status == 200 and result == {"received": LIMIT}
    assert delivered == [65536] * (LIMIT // 65536)
    assert consumed == [LIMIT]
    status, result, delivered, _, consumed = await isolated_body_limit(
        chunks + [b" ", b"MUST_NOT_BE_READ"], declared=declared, chunked=chunked,
    )
    assert status == 413 and result == TOO_LARGE
    assert delivered == [65536] * (LIMIT // 65536) + [1]
    assert consumed == []


@pytest.mark.anyio
async def test_isolated_utf8_bytes_and_small_declared_length():
    # Split a multibyte character across receive frames; whitespace counts too.
    encoded = '{"source":"µ🚀"}'.encode()
    padded = encoded + b" " * (LIMIT - len(encoded))
    assert len(padded) == LIMIT
    assert len(padded.decode("utf-8")) < LIMIT
    split = encoded.index("µ".encode()) + 1
    chunks = [padded[:split], padded[split:]]
    status, result, delivered, _, consumed = await isolated_body_limit(chunks, declared="1")
    assert status == 200 and result == {"received": LIMIT}
    assert delivered == [len(chunk) for chunk in chunks]
    assert consumed == [LIMIT]
    status, result, delivered, _, consumed = await isolated_body_limit(
        chunks + [b" ", b"MUST_NOT_BE_READ"], declared="1",
    )
    assert status == 413 and result == TOO_LARGE
    assert delivered == [len(chunk) for chunk in chunks] + [1]
    assert consumed == []


@pytest.mark.anyio
async def test_declared_length_is_not_a_new_exact_framing_requirement():
    # V113 permits actual bytes below a larger in-budget declaration.
    for declared in (None, "0", "1", str(LIMIT)):
        status, result, delivered, _, consumed = await isolated_body_limit(
            [b"{}"], declared=declared, chunked=False,
        )
        assert status == 200 and result == {"received": 2}
        assert delivered == consumed == [2]


@pytest.mark.anyio
async def test_cookie_origin_failure_precedes_declared_length(cookie_client, monkeypatch):
    observed = spies(monkeypatch)
    walker = Mock(wraps=workflow._json_walk)
    dispatch = Mock(wraps=api.run_in_threadpool)
    monkeypatch.setattr(workflow, "_json_walk", walker)
    monkeypatch.setattr(api, "run_in_threadpool", dispatch)
    for headers in ({}, {"Origin": "https://other.example"}):
        for declared in ("invalid", "-1", str(LIMIT + 1)):
            response = await cookie_client.post(PATH, content=b"PRIVATE_SENTINEL", headers={
                **headers, "Content-Length": declared,
            })
            assert response.status_code == 403
            assert "PRIVATE_SENTINEL" not in response.text
    for call in [*observed, walker, dispatch]:
        call.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("defect", ["depth", "container", "string", "integer", "nonfinite"])
async def test_actual_input_walker_rejects_before_dispatch(client, monkeypatch, defect):
    body = request(2)
    if defect == "depth":
        nested = 0
        for _ in range(24):
            nested = [nested]
        body["extra"] = nested
    elif defect == "container":
        body["extra"] = [0] * 257
    elif defect == "string":
        body["thermal_body"]["property_source"] = "x" * 2001
    elif defect == "integer":
        body["thermal_body"]["mass_kg"] = 1 << 1023
    else:
        body["extra"] = float("inf")
    # Overflowed finite JSON syntax reaches the real walker, rather than the
    # parser's separate rejection of the nonstandard Infinity constant.
    encoded = json.dumps(body).encode().replace(b"Infinity", b"1e9999")
    assert len(encoded) < LIMIT
    observed = spies(monkeypatch)
    walker = Mock(wraps=workflow._json_walk)
    dispatch = Mock(wraps=api.run_in_threadpool)
    monkeypatch.setattr(workflow, "_json_walk", walker)
    monkeypatch.setattr(api, "run_in_threadpool", dispatch)
    response = await client.post(PATH, content=encoded, headers=client.auth_headers)
    assert response.status_code == 422 and response.json() == INVALID
    walker.assert_called_once_with(body, workflow._LIMITS["input_json"])
    for call in [*observed, dispatch]:
        call.assert_not_called()


@pytest.mark.parametrize("scope,nodes", [
    ("input_json", 1048576), ("output_json", 8388608),
])
def test_helper_only_actual_node_extrema_are_independent_of_http_bytes(scope, nodes):
    # Helper-only resource checks: these alias trees are not HTTP model requests
    # or computed results. Every repeated occurrence counts under the real walk.
    limits = workflow._LIMITS[scope]
    assert limits["max_nodes_including_keys"] == nodes
    exact = json_nodes(nodes, limits["max_container_items"])
    workflow._json_walk(exact, limits)
    with pytest.raises(ValueError):
        workflow._json_walk(json_nodes(nodes + 1, limits["max_container_items"]), limits)


@pytest.mark.anyio
async def test_unit_probe_reduced_node_budget_rejects_before_dispatch(client, monkeypatch):
    # Reduced-budget transport unit probe. Production maxima are tested above
    # by the real walker; no claim that >1M nodes fit the 1 MiB HTTP byte cap.
    limits = deepcopy(workflow._LIMITS)
    limits["input_json"]["max_nodes_including_keys"] = 5
    monkeypatch.setattr(workflow, "_LIMITS", limits)
    body = {"x": [0, 0, 0]}  # Six nodes including the root, key and list.
    observed = spies(monkeypatch)
    walker = Mock(wraps=workflow._json_walk)
    dispatch = Mock(wraps=api.run_in_threadpool)
    monkeypatch.setattr(workflow, "_json_walk", walker)
    monkeypatch.setattr(api, "run_in_threadpool", dispatch)
    response = await client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 422 and response.json() == INVALID
    walker.assert_called_once_with(body, limits["input_json"])
    for call in [*observed, dispatch]:
        call.assert_not_called()


@pytest.mark.anyio
async def test_transport_unit_fixture_response_can_exceed_request_byte_cap(client, monkeypatch):
    # Deliberate transport fixture, NOT an actual science result or envelope.
    # This isolates response handling without asserting model feasibility.
    fixture = {"transport_unit_fixture": True, "chunks": ["x" * 2000] * 600}
    workflow._json_walk(fixture, workflow._LIMITS["output_json"])
    evaluator = Mock(return_value=fixture)
    energy = Mock(wraps=workflow.energy.evaluate_tabulated_target_dc_energy)
    thermal = Mock(wraps=workflow.thermal.screen_thermal)
    monkeypatch.setattr(workflow, "evaluate_tabulated_electrothermal", evaluator)
    monkeypatch.setattr(workflow.energy, "evaluate_tabulated_target_dc_energy", energy)
    monkeypatch.setattr(workflow.thermal, "screen_thermal", thermal)
    response = await client.post(PATH, json={}, headers=client.auth_headers)
    assert response.status_code == 200
    assert len(response.content) > LIMIT
    assert response.json() == fixture
    evaluator.assert_called_once_with({})
    energy.assert_not_called()
    thermal.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("child", ["energy", "thermal"])
@pytest.mark.parametrize("fault", ["exception", "untrusted_status"])
async def test_actual_boundary_execution_failed_exact_http_equality(client, monkeypatch, child, fault):
    body = request(2)
    snapshot = deepcopy(body)
    module, name = (
        (workflow.energy, "evaluate_tabulated_target_dc_energy") if child == "energy"
        else (workflow.thermal, "screen_thermal")
    )
    # Only the child boundary is fault-injected. Both comparisons run the
    # actual root evaluator and its unchanged validation/failure producers.
    if fault == "exception":
        faulty = Mock(side_effect=RuntimeError("PRIVATE_SENTINEL child exception"))
    else:
        faulty = Mock(return_value={
            "status": "PRIVATE_SENTINEL_UNTRUSTED_STATUS",
            "reasons": ["PRIVATE_SENTINEL alleged child cause"],
        })
    monkeypatch.setattr(module, name, faulty)
    direct = workflow.evaluate_tabulated_electrothermal(body)
    assert direct["status"] == "EXECUTION_FAILED"
    assert direct["reasons"] == [workflow._REASONS[child]]
    assert direct["energy_result_count"] == int(child == "thermal")
    assert direct["thermal_result_count"] == 0
    assert direct["outputs"] == direct["output_units"] == {}
    assert direct["stages"] == direct["transfers"] == []
    assert direct["diagnostics_complete"] is False
    assert "PRIVATE_SENTINEL" not in json.dumps(direct)
    faulty.reset_mock()
    evaluator = Mock(wraps=workflow.evaluate_tabulated_electrothermal)
    monkeypatch.setattr(workflow, "evaluate_tabulated_electrothermal", evaluator)
    response = await client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct
    assert body == snapshot
    assert "PRIVATE_SENTINEL" not in response.text
    evaluator.assert_called_once_with(body)
    faulty.assert_called_once()
    assert_full_hashes(response.json(), body)
