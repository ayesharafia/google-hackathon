"""V137 transport tests using invented inputs and the actual V136 evaluator."""

import json
import math
import threading
from copy import deepcopy
from itertools import pairwise
from unittest.mock import Mock

import anyio
import httpx
import pytest

from physimesh.api import polar_rotor as api
from physimesh.api.settings import Settings
from physimesh.drone import polar_rotor as rotor
from physimesh.drone.provenance import sha256_record

from .test_polar_rotor import _derived, _three_annuli
from .test_polar_rotor import request_data as _request_data

PATH = api.PREFIX + "/evaluate"
CATALOG = api.PREFIX + "/catalog"
INVALID = {"detail": "Invalid polar rotor request."}
LIMIT = 1048576


@pytest.fixture
def request_data():
    return _request_data.__wrapped__()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(params=[False, True], ids=["local", "hosted"])
async def client(tmp_path, monkeypatch, request):
    from physimesh.api import app as app_module

    (tmp_path / "web").mkdir()
    monkeypatch.setattr(app_module, "__file__", str(tmp_path / "src/physimesh/api/app.py"))
    app = app_module.create_app(Settings(
        tmp_path, tmp_path / "jobs.sqlite", "synthetic-token", None, hosted_mode=request.param,
    ))
    token = "synthetic-token"
    if request.param:
        app.state.identity.provision("rotor@example.test", password="synthetic-fixture-password")
        token = app.state.identity.login(
            "rotor@example.test", password="synthetic-fixture-password",
        )["token"]
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as connection,
    ):
        connection.app = app
        connection.hosted_test = request.param
        connection.auth_headers = {"Authorization": f"Bearer {token}"}
        yield connection


@pytest.mark.anyio
async def test_actual_full_http_equality(client, request_data):
    snapshot = deepcopy(request_data)
    direct = rotor.evaluate_polar_rotor(request_data)
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    response = await client.post(PATH, json=request_data, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json() == direct
    assert request_data == snapshot


@pytest.mark.anyio
async def test_catalog_exact(client):
    response = await client.get(CATALOG, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json()["catalog"] == rotor.polar_rotor_catalog()


@pytest.mark.anyio
@pytest.mark.parametrize("raw", [
    b'{"x":1,"x":2}', b'{"a":[{"x":1,"x":2}]}',
    b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}', b'{"x":1e9999}',
    b'{"x":"\xff"}', b'{"x":"\\ud800"}', b'\xef\xbb\xbf{}',
    b'[]', b'null', b'1', b'true', b'"text"', b'{"PRIVATE_SENTINEL":',
])
async def test_strict_json(client, raw):
    response = await client.post(PATH, content=raw, headers=client.auth_headers)
    assert response.status_code == 422
    assert response.json() == INVALID


async def raw_chunks(client, chunks, *, declared=None, chunked=True, authorization=None,
                     path=PATH, raw_path=None, method="POST"):
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
            "method": method, "scheme": "http", "path": path,
            "raw_path": path.encode() if raw_path is None else raw_path,
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


def model_spies(monkeypatch):
    observed = []
    for module, name in (
        (rotor, "evaluate_polar_rotor"),
        (rotor._solve, "evaluate_section_solve"),
        (rotor._solve._res, "evaluate_section_residual"),
        (rotor._solve._res._load, "evaluate_section_load"),
        (rotor._solve._res._load._polar, "evaluate_section_polar"),
    ):
        call = Mock(wraps=getattr(module, name))
        monkeypatch.setattr(module, name, call)
        observed.append(call)
    return observed


@pytest.mark.anyio
async def test_catalog_fresh_zero_model_calls(client, monkeypatch):
    actual = rotor.polar_rotor_catalog
    baseline, retained = actual(), []

    def capture():
        result = actual()
        retained.append(result)
        return result

    catalog = Mock(side_effect=capture)
    observed = model_spies(monkeypatch)
    monkeypatch.setattr(rotor, "polar_rotor_catalog", catalog)
    first = await client.get(CATALOG, headers=client.auth_headers)
    assert first.status_code == 200
    assert set(first.json()) == {"catalog", "transport"}
    assert first.json()["catalog"] == baseline
    retained[0]["limits"]["input_json"]["max_depth"] = 0
    retained[0]["limitations"].clear()
    retained[0]["output_field_units"].clear()
    second = await client.get(CATALOG, headers=client.auth_headers)
    assert second.status_code == 200
    assert second.json()["catalog"] == baseline
    assert retained[0] is not retained[1]
    assert catalog.call_count == 2
    limits = second.json()["transport"]["limits"]
    assert limits["body_bytes"] == LIMIT
    assert limits["input_json_reference"] == "catalog.limits.input_json"
    assert limits["response_json_reference"] == "catalog.limits.output_json"
    assert second.json()["catalog"]["limits"]["input_json"]["max_nodes_including_keys"] == 262144
    for call in observed:
        call.assert_not_called()


@pytest.mark.anyio
async def test_actual_once_off_loop_without_child_reruns(client, request_data, monkeypatch):
    direct = rotor.evaluate_polar_rotor(request_data)
    observed = model_spies(monkeypatch)
    actual_evaluate, dispatch = rotor.evaluate_polar_rotor, api.run_in_threadpool
    loop_thread, workers, dispatches = threading.get_ident(), [], []
    entered, progressed = threading.Event(), threading.Event()

    def evaluate(body):
        workers.append(threading.get_ident())
        entered.set()
        assert progressed.wait(timeout=5), "Event loop did not progress"
        return actual_evaluate(body)

    async def threadpool(function, *args):
        dispatches.append((function, deepcopy(args)))

        async def heartbeat():
            with anyio.fail_after(5):
                while not entered.is_set():
                    await anyio.sleep(0.001)
            progressed.set()

        async with anyio.create_task_group() as group:
            group.start_soon(heartbeat)
            return await dispatch(function, *args)

    monkeypatch.setattr(rotor, "evaluate_polar_rotor", evaluate)
    monkeypatch.setattr(api, "run_in_threadpool", threadpool)
    response = await client.post(PATH, json=request_data, headers=client.auth_headers)
    assert response.status_code == 200 and response.json() == direct
    assert dispatches == [(evaluate, (request_data,))]
    assert len(workers) == 1 and workers[0] != loop_thread and progressed.is_set()
    observed[0].assert_called_once_with(request_data)
    assert observed[1].call_count == direct["section_solve_result_count"] == 1
    assert [call.call_count for call in observed[2:]] == [direct["residual_result_count"]] * 3


@pytest.mark.anyio
@pytest.mark.parametrize("case", ["computed", "ood", "nonbracket", "budget"])
async def test_three_actual_annuli_full_equality(client, request_data, monkeypatch, case):
    _three_annuli(request_data)
    middle = request_data["annuli"][1]
    if case == "ood":
        middle["polar"].update(sampled_mach_number=0, declared_mach_interval=[0, 0])
    elif case == "nonbracket":
        for table in middle["polar"]["reynolds_tables"]:
            for row in table["rows"]:
                row["cl"] = 0
    elif case == "budget":
        middle["solve"]["max_evaluations"] = 2
    snapshot = deepcopy(request_data)
    direct = rotor.evaluate_polar_rotor(request_data)
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    assert direct["section_solve_result_count"] == 3
    states = {"computed": "CONVERGED", "ood": "NOT_RUN_OUT_OF_POLAR_DOMAIN",
              "nonbracket": "NOT_BRACKETED", "budget": "EVALUATION_BUDGET_EXHAUSTED"}
    assert direct["outputs"]["annuli"][1]["solve_result"]["outputs"]["solve_state"] == states[case]
    assert direct["outputs"]["rotor_state"] == (
        "COMPUTED" if case == "computed" else "NOT_RUN_SECTION_NOT_CONVERGED")
    observed = model_spies(monkeypatch)
    response = await client.post(PATH, json=request_data, headers=client.auth_headers)
    assert response.status_code == 200 and response.json() == direct
    assert request_data == snapshot
    observed[0].assert_called_once_with(request_data)
    assert observed[1].call_count == 3
    assert [call.call_count for call in observed[2:]] == [direct["residual_result_count"]] * 3


@pytest.mark.anyio
@pytest.mark.parametrize("authorization", [{}, {"Authorization": "Bearer wrong-token"}])
async def test_auth_before_body_length_parser(client, monkeypatch, authorization):
    observed = model_spies(monkeypatch)
    for module, name in ((rotor, "_walk"), (rotor, "polar_rotor_catalog"),
                         (api, "run_in_threadpool"), (api, "_pairs"), (api, "_constant")):
        call = Mock(wraps=getattr(module, name))
        monkeypatch.setattr(module, name, call)
        observed.append(call)
    assert (await client.get(CATALOG, headers=authorization)).status_code == 401
    for declared in (None, "invalid", "-1", str(LIMIT + 1), "1"):
        for path in (PATH, PATH + "/"):
            status, body, delivered, _ = await raw_chunks(
                client, [b"PRIVATE_SENTINEL" * (LIMIT // 16 + 1)], path=path,
                authorization=authorization, declared=declared,
            )
            assert status == 401
            assert delivered == []
            assert "PRIVATE_SENTINEL" not in str(body)
    for call in observed:
        call.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("chunked,declared", [
    (True, None), (False, None), (False, "1"), (False, str(LIMIT)), (True, "1"),
])
async def test_actual_byte_boundary_utf8_chunks(client, request_data, monkeypatch, chunked, declared):
    request_data["rotor"]["geometry_source"] = "Invented µ source 🚀"
    direct = rotor.evaluate_polar_rotor(request_data)
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    encoded = json.dumps(request_data, ensure_ascii=False, allow_nan=False).encode("utf-8")
    padded = encoded + b" " * (LIMIT - len(encoded))
    split = encoded.index("µ".encode()) + 1
    chunks = [padded[:split], padded[split:4096], padded[4096:65536], padded[65536:]]
    assert len(padded) == LIMIT and len(encoded) > len(encoded.decode("utf-8"))
    observed = model_spies(monkeypatch)
    status, body, delivered, _ = await raw_chunks(
        client, chunks, path=PATH, chunked=chunked, declared=declared,
    )
    assert status == 200 and body == direct
    assert delivered == [len(chunk) for chunk in chunks]
    observed[0].assert_called_once_with(request_data)
    for call in observed:
        call.reset_mock()
    status, body, delivered, _ = await raw_chunks(
        client, chunks + [b" "], path=PATH, chunked=chunked, declared=declared,
    )
    assert status == 413 and body == {"detail": "request byte budget exceeded"}
    assert sum(delivered) == LIMIT + 1
    for call in observed:
        call.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("declared,status", [
    (str(LIMIT + 1), 413), ("-1", 413), ("9" * 100, 413),
    ("invalid", 400), ("", 400), ("+1", 400), ("-0", 400), (" 1", 400),
    ("9" * 5000, 400),
])
async def test_header_refusal_before_receive(client, monkeypatch, declared, status):
    observed = model_spies(monkeypatch)
    result, body, delivered, _ = await raw_chunks(
        client, [b"PRIVATE_SENTINEL"], path=PATH, declared=declared,
    )
    assert result == status and delivered == []
    assert body == {"detail": "request byte budget exceeded" if status == 413 else "invalid content length"}
    for call in observed:
        call.assert_not_called()


def json_nodes(value):
    if type(value) is dict:
        return 1 + sum(1 + json_nodes(child) for child in value.values())
    if type(value) is list:
        return 1 + sum(json_nodes(child) for child in value)
    return 1


def node_boundary():
    blocks = [[[0] * 256 for _ in range(256)] for _ in range(4)]
    blocks[-1] = blocks[-1][:252]
    blocks[-1][-1] = blocks[-1][-1][:253]
    return {"x": blocks}


@pytest.mark.anyio
async def test_actual_walker_node_boundary_independent_of_byte_budget(client, monkeypatch):
    body = node_boundary()
    assert json_nodes(body) == 262144
    encoded = json.dumps(body, separators=(",", ":")).encode()
    assert len(encoded) < LIMIT
    direct = rotor.evaluate_polar_rotor(body)
    assert direct["status"] == "MODEL_INAPPLICABLE"
    actual_walk = rotor._walk
    walk = Mock(wraps=actual_walk)
    observed = model_spies(monkeypatch)
    monkeypatch.setattr(rotor, "_walk", walk)
    response = await client.post(PATH, content=encoded, headers=client.auth_headers)
    assert response.status_code == 200 and response.json() == direct
    assert walk.call_args_list[0].args == (body,)
    observed[0].assert_called_once_with(body)
    for call in observed:
        call.reset_mock()
    walk.reset_mock()
    body["x"][-1][-1].append(0)
    assert json_nodes(body) == 262145
    encoded = json.dumps(body, separators=(",", ":")).encode()
    assert len(encoded) < LIMIT
    response = await client.post(PATH, content=encoded, headers=client.auth_headers)
    assert response.status_code == 422 and response.json() == INVALID
    walk.assert_called_once_with(body)
    for call in observed:
        call.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("case", ["depth", "container", "string", "integer", "parser_recursion"])
async def test_admission_limits_before_dispatch(client, monkeypatch, case):
    if case == "depth":
        body = {"x": 0}
        for _ in range(15):
            body = {"x": body}
        raw = json.dumps(body).encode()
    elif case == "container":
        raw = json.dumps({"x": [0] * 257}).encode()
    elif case == "string":
        raw = json.dumps({"x": "a" * 2001}).encode()
    elif case == "integer":
        raw = json.dumps({"x": 1 << 1023}).encode()
    else:
        raw = b'{"x":' + b'[' * 2000 + b'0' + b']' * 2000 + b'}'
    assert len(raw) < LIMIT
    observed = model_spies(monkeypatch)
    dispatch = Mock(wraps=api.run_in_threadpool)
    monkeypatch.setattr(api, "run_in_threadpool", dispatch)
    response = await client.post(PATH, content=raw, headers=client.auth_headers)
    assert response.status_code == 422 and response.json() == INVALID
    for call in [*observed, dispatch]:
        call.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("error", [ValueError, RecursionError])
async def test_parser_exceptions_sanitized(client, monkeypatch, error):
    observed = model_spies(monkeypatch)
    with monkeypatch.context() as patch:
        patch.setattr(api.json, "loads", Mock(side_effect=error("PRIVATE_SENTINEL")))
        response = await client.post(PATH, content=b"{}", headers=client.auth_headers)
    assert response.status_code == 422 and response.json() == INVALID
    for call in observed:
        call.assert_not_called()


@pytest.mark.anyio
async def test_native_integer_exact_knot_and_negative_zero_preserved(client, request_data, monkeypatch):
    # Probe actual V134 to locate an exact query knot, as in the native V135 test.
    child = _derived(request_data, 0)
    residual_request = deepcopy(child["residual_template"])
    residual_request["section"]["psi_rad"] = child["solve"]["psi_lower_rad"]
    probe = rotor._solve._res.evaluate_section_residual(residual_request)
    assert probe["status"] == "COMPUTED_EXPERIMENTAL"
    query = probe["outputs"]["actual_load_result"]["outputs"]["actual_lookup_request"]["query"]
    knot = 2 ** 53 + 1
    request_data["annuli"][0]["polar"]["reynolds_tables"] = [{
        "reynolds_number": query["reynolds_number"],
        "rows": [{"alpha_rad": query["alpha_rad"], "cl": knot, "cd": -0.0},
                 {"alpha_rad": 1.5, "cl": 0, "cd": 0}],
    }]
    snapshot = deepcopy(request_data)
    direct = rotor.evaluate_polar_rotor(request_data)
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    observed = model_spies(monkeypatch)
    response = await client.post(PATH, json=request_data, headers=client.auth_headers)
    assert response.status_code == 200 and response.json() == direct
    assert request_data == snapshot
    observed[0].assert_called_once_with(request_data)
    admitted = observed[0].call_args.args[0]["annuli"][0]["polar"]["reynolds_tables"][0]["rows"][0]
    assert type(admitted["cl"]) is int and admitted["cl"] == knot
    rows = response.json()["outputs"]["annuli"][0]["solve_result"]["outputs"]["evaluations"]
    lookup = rows[0]["result"]["outputs"]["actual_load_result"]["outputs"]["actual_lookup_result"]["outputs"]
    assert type(lookup["cl"]) is int and lookup["cl"] == knot
    assert type(lookup["cd"]) is float and math.copysign(1, lookup["cd"]) == -1
    assert b'"cl":9007199254740993' in response.content
    assert b'"cd":-0.0' in response.content
    derived = observed[1].call_args.args[0]
    retained = derived["residual_template"]["polar"]["reynolds_tables"][0]["rows"][0]
    assert type(retained["cl"]) is int and retained["cl"] == knot
    assert response.json()["request_sha256"] == sha256_record(request_data)
    assert response.json()["evaluation_sha256"] == sha256_record({
        key: value for key, value in direct.items() if key != "evaluation_sha256"
    })


@pytest.mark.anyio
async def test_actual_eight_annuli_128_results_response_over_one_mib(client, request_data, monkeypatch):
    # Invented input; all returned results are from actual V136 and its actual children.
    template = deepcopy(request_data["annuli"][0])
    boundaries = [0.2 + 0.05 * index for index in range(8)] + [0.6]
    request_data["annuli"] = []
    for inner, outer in pairwise(boundaries):
        annulus = deepcopy(template)
        annulus.update(radial_inner_m=inner, radial_outer_m=outer)
        radius = math.fsum((inner, 0.5 * math.fsum((outer, -inner))))
        annulus["solve"].update(
            psi_lower_rad=math.atan2(5, 50 * radius) + 0.0001, psi_upper_rad=1.5,
            angle_tolerance_rad=1e-30, residual_tolerance_m2_s=1e-30)
        request_data["annuli"].append(annulus)
    assert len(json.dumps(request_data).encode()) < LIMIT
    snapshot = deepcopy(request_data)
    direct = rotor.evaluate_polar_rotor(request_data)
    assert direct["status"] == "COMPUTED_EXPERIMENTAL"
    assert direct["section_solve_result_count"] == 8
    assert [direct[key] for key in (
        "residual_result_count", "load_result_count", "lookup_result_count",
    )] == [128, 128, 128]
    assert len(json.dumps(direct, separators=(",", ":")).encode()) > LIMIT
    observed = model_spies(monkeypatch)
    response = await client.post(PATH, json=request_data, headers=client.auth_headers)
    assert response.status_code == 200
    assert len(response.content) > LIMIT
    assert response.json() == direct
    assert request_data == snapshot
    observed[0].assert_called_once_with(request_data)
    assert [call.call_count for call in observed[1:]] == [8, 128, 128, 128]
    assert len(response.json()["outputs"]["annuli"]) == 8
    assert all(row["solve_result"]["outputs"]["solve_state"] == "EVALUATION_BUDGET_EXHAUSTED"
               for row in response.json()["outputs"]["annuli"])


@pytest.mark.anyio
async def test_canonical_methods_neighbors_and_slash_order(client, monkeypatch):
    observed = model_spies(monkeypatch)
    assert (await client.get(PATH, headers=client.auth_headers)).status_code == 405
    assert (await client.post(CATALOG, json={}, headers=client.auth_headers)).status_code == 405
    for suffix in ("/extra", "-extra", "evil"):
        expected = 403 if client.hosted_test else 404
        assert (await client.get(CATALOG + suffix, headers=client.auth_headers)).status_code == expected
        status, _, delivered, _ = await raw_chunks(client, [b"x" * (LIMIT + 1)], path=PATH + suffix)
        assert status == expected and delivered == []
    for path, method in ((CATALOG, "GET"), (PATH, "POST")):
        response = await client.request(
            method, path + "/", headers=client.auth_headers, follow_redirects=False,
        )
        assert response.status_code == (403 if client.hosted_test else 307)
        if not client.hosted_test:
            assert response.headers["location"] == "http://testserver" + path
    for suffix in ("/", "///"):
        for declared in (str(LIMIT + 1), "1", "invalid"):
            status, body, delivered, headers = await raw_chunks(
                client, [b" " * (LIMIT + 1)], path=PATH + suffix, declared=declared,
            )
            expected = 403 if client.hosted_test else (
                307 if declared == "1" else (400 if declared == "invalid" else 413))
            assert status == expected and delivered == []
            if expected == 307:
                assert headers[b"location"].decode() == "http://testserver" + PATH
            elif expected in (400, 413):
                assert body == {"detail": "invalid content length" if expected == 400
                                else "request byte budget exceeded"}
    for call in observed:
        call.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("raw_path", [
    b"/api/drone/%70olar-rotor/evaluate", b"/api/drone/polar-rotor%2fevaluate",
    b"/api%2fdrone/polar-rotor/evaluate",
])
async def test_hosted_escaped_path_not_an_authorization_alias(client, monkeypatch, raw_path):
    observed = model_spies(monkeypatch)
    status, body, delivered, _ = await raw_chunks(
        client, [b"{}"], path=PATH, raw_path=raw_path,
    )
    if client.hosted_test:
        assert status == 403 and delivered == []
        for call in observed:
            call.assert_not_called()
    else:
        # Existing local namespace authentication accepts decoded routes after bearer auth.
        assert status == 200 and body == rotor.evaluate_polar_rotor({})
        assert delivered == [2]


@pytest.mark.anyio
async def test_local_configured_token_is_not_hosted_session(client):
    response = await client.get(CATALOG, headers={"Authorization": "Bearer synthetic-token"})
    assert response.status_code == (401 if client.hosted_test else 200)
