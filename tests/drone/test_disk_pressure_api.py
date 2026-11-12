"""V144 real-application HTTP checks with synthetic test-only retained rotor records."""

import threading
from copy import deepcopy
from unittest.mock import Mock

import httpx
import pytest

from physimesh.api import disk_pressure as api
from physimesh.api.settings import Settings
from physimesh.drone import polar_rotor_disk_pressure as pressure
from physimesh.drone import polar_rotor_disk_pressure_export as exporter
from physimesh.drone.provenance import canonical_json, sha256_record

from .test_polar_rotor_api import raw_chunks
from .test_polar_rotor_disk_pressure import synthetic_response as _synthetic_response

CATALOG = api.PREFIX + "/catalog"
PATHS = (api.PREFIX + "/derive", api.PREFIX + "/export")
LIMIT = 16777216
INVALID = {"detail": "Invalid disk pressure request."}
BUDGET = {"detail": "request byte budget exceeded"}


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
        app.state.identity.provision("disk-pressure@example.test", password="synthetic-fixture-password")
        token = app.state.identity.login(
            "disk-pressure@example.test", password="synthetic-fixture-password",
        )["token"]
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as connection,
    ):
        connection.app = app
        connection.hosted_test = request.param
        connection.auth_headers = {"Authorization": f"Bearer {token}"}
        yield connection


@pytest.fixture
def rotor_response():
    """Reuse the V142 synthetic retained-record pattern, never actual physical evidence."""
    return _synthetic_response.__wrapped__()


@pytest.fixture
def derivation_response(rotor_response):
    result = pressure.derive_disk_pressure(rotor_response)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    return result


@pytest.mark.anyio
async def test_catalog_labels_and_independent_limits(client, monkeypatch):
    derive = Mock(wraps=pressure.derive_disk_pressure)
    export = Mock(wraps=exporter.export_disk_pressure_report)
    monkeypatch.setattr(pressure, "derive_disk_pressure", derive)
    monkeypatch.setattr(exporter, "export_disk_pressure_report", export)
    response = await client.get(CATALOG, headers=client.auth_headers)
    assert response.status_code == 200
    catalog = response.json()
    assert set(catalog) == {"catalog", "transport"}
    assert set(catalog["catalog"]["operations"]) == {"derive", "export"}
    assert set(catalog["transport"]) == {"limits", "parsing", "execution", "http_status", "ordering"}
    assert catalog["transport"]["limits"]["body_bytes"] == LIMIT
    assert "actual received request bytes" in catalog["transport"]["limits"]["body_bytes_constraint"]
    independent = catalog["transport"]["limits"]["independent_bounds"]
    for label in ("16 MiB", "V137 1 MiB", "V136", "413", "smaller annulus counts"):
        assert label in independent
    for label in ("IDEALIZED ACTUATOR-DISK", "NOT surface pressure", "NOT a solved or CFD pressure field"):
        assert label in catalog["catalog"]["state_text"]
    assert "Canonical digests bind JSON content, not provenance authenticity" in str(catalog)
    assert "HTTP 200 alone establishes neither computational nor physical success" in str(catalog)
    derive.assert_not_called()
    export.assert_not_called()


@pytest.mark.anyio
async def test_derive_exact_in_process_response(client, rotor_response):
    before = sha256_record(rotor_response)
    direct = pressure.derive_disk_pressure(rotor_response)
    response = await client.post(PATHS[0], json=rotor_response, headers=client.auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "COMPUTED_EXPERIMENTAL"
    assert response.json() == direct
    assert response.json()["outputs"]["annuli"] == direct["outputs"]["annuli"]
    assert sha256_record(rotor_response) == before


@pytest.mark.anyio
async def test_export_exact_and_independent_report_hash(client, derivation_response):
    before = sha256_record(derivation_response)
    response = await client.post(PATHS[1], json=derivation_response, headers=client.auth_headers)
    assert response.status_code == 200
    value = response.json()
    assert value == exporter.export_disk_pressure_report(derivation_response)
    assert value["status"] == "COMPUTED_EXPERIMENTAL"
    output = value["outputs"]
    assert output["report_canonical_sha256"] == sha256_record(output["report"])
    assert output["report_bytes"] == len(canonical_json(output["report"]).encode("utf-8"))
    assert sha256_record(derivation_response) == before


@pytest.mark.anyio
@pytest.mark.parametrize("path", PATHS)
async def test_once_in_threadpool(client, rotor_response, derivation_response, monkeypatch, path):
    module, name, body = ((pressure, "derive_disk_pressure", rotor_response) if path == PATHS[0]
                          else (exporter, "export_disk_pressure_report", derivation_response))
    actual, dispatch = getattr(module, name), api.run_in_threadpool
    loop_thread, workers, dispatches = threading.get_ident(), [], []

    def evaluate(value):
        workers.append(threading.get_ident())
        return actual(value)

    async def threadpool(function, *args):
        dispatches.append((function, deepcopy(args)))
        return await dispatch(function, *args)

    monkeypatch.setattr(module, name, evaluate)
    monkeypatch.setattr(api, "run_in_threadpool", threadpool)
    response = await client.post(path, json=body, headers=client.auth_headers)
    assert response.status_code == 200 and response.json() == actual(body)
    assert dispatches == [(evaluate, (body,))]
    assert len(workers) == 1 and workers[0] != loop_thread


@pytest.mark.anyio
@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("raw", [
    b'{"PRIVATE_SENTINEL":', b'{"x":1,"x":2}', b'{"a":[{"x":1,"x":2}]}',
    b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}', b'{"x":1e9999}',
    b'{"x":"\xff"}', b'{"x":"\\ud800"}', b'\xef\xbb\xbf{}',
    b'[]', b'null', b'1', b'true', b'"text"',
])
async def test_strict_parsing_before_dispatch(client, monkeypatch, path, raw):
    dispatch = Mock(wraps=api.run_in_threadpool)
    monkeypatch.setattr(api, "run_in_threadpool", dispatch)
    response = await client.post(path, content=raw, headers=client.auth_headers)
    assert response.status_code == 422 and response.json() == INVALID
    dispatch.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("declared", [str(LIMIT + 1), "-1", "invalid", "", "+1", "-0", " 1", "9" * 5000])
async def test_declared_length_refused_before_receive(client, path, declared):
    status, body, delivered, _ = await raw_chunks(client, [b"PRIVATE_SENTINEL"], path=path, declared=declared)
    assert status == 413 and body == BUDGET
    assert delivered == []


@pytest.mark.anyio
@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("declared", [None, "1", str(LIMIT)])
async def test_actual_sixteen_mib_boundary(client, rotor_response, derivation_response, path, declared):
    body = rotor_response if path == PATHS[0] else derivation_response
    encoded = canonical_json(body).encode("utf-8")
    padding, remainder = divmod(LIMIT - len(encoded), 65536)
    chunks = [encoded] + [b" " * 65536] * padding + [b" " * remainder]
    status, value, delivered, _ = await raw_chunks(client, chunks, path=path, declared=declared)
    direct = pressure.derive_disk_pressure(body) if path == PATHS[0] else exporter.export_disk_pressure_report(body)
    assert status == 200 and value == direct
    assert sum(delivered) == LIMIT
    status, value, delivered, _ = await raw_chunks(client, chunks + [b" "], path=path, declared=declared)
    assert status == 413 and value == BUDGET
    assert sum(delivered) == LIMIT + 1


@pytest.mark.anyio
async def test_stripped_labels_are_atomic_workflow_refusal(client, derivation_response):
    derivation_response["state_text"] = derivation_response["state_text"].replace(
        "NOT a solved or CFD pressure field", "removed")
    derivation_response["evaluation_sha256"] = sha256_record({
        key: value for key, value in derivation_response.items() if key != "evaluation_sha256"})
    response = await client.post(PATHS[1], json=derivation_response, headers=client.auth_headers)
    assert response.status_code == 200
    value = response.json()
    assert value["status"] == "MODEL_INAPPLICABLE"
    assert value["outputs"] == value["output_units"] == {}
    assert value["diagnostics_complete"] is False
    assert all(type(count) is int and count == 0 for key, count in value.items() if key.endswith("_result_count"))


@pytest.mark.anyio
@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("authorization", [{}, {"Authorization": "Bearer wrong-token"}])
async def test_authentication_before_receive_and_parser(client, monkeypatch, path, authorization):
    dispatch = Mock(wraps=api.run_in_threadpool)
    walk = Mock(wraps=api._rotor._walk)
    monkeypatch.setattr(api, "run_in_threadpool", dispatch)
    monkeypatch.setattr(api._rotor, "_walk", walk)
    assert (await client.get(CATALOG, headers=authorization)).status_code == 401
    for declared in (None, "invalid", "-1", str(LIMIT + 1), "1"):
        for suffix in ("", "/"):
            status, body, delivered, _ = await raw_chunks(
                client, [b"PRIVATE_SENTINEL"], path=path + suffix,
                authorization=authorization, declared=declared,
            )
            assert status == 401 and delivered == []
            assert "PRIVATE_SENTINEL" not in str(body)
    dispatch.assert_not_called()
    walk.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("path", PATHS)
async def test_trailing_slashes_and_neighbor_ordering(client, path):
    for suffix in ("/", "///"):
        for declared in (str(LIMIT + 1), "invalid", "1"):
            status, value, delivered, headers = await raw_chunks(
                client, [b"x" * (LIMIT + 1)], path=path + suffix, declared=declared,
            )
            expected = 403 if client.hosted_test else (307 if declared == "1" else 413)
            assert status == expected and delivered == []
            if expected == 413:
                assert value == BUDGET
            elif expected == 307:
                assert headers[b"location"].decode() == "http://testserver" + path
    for suffix in ("/extra", "-extra", "evil"):
        status, _, delivered, _ = await raw_chunks(client, [b"x"], path=path + suffix)
        assert status == (403 if client.hosted_test else 404) and delivered == []


@pytest.mark.anyio
@pytest.mark.parametrize("path,raw_path", [
    (PATHS[0], b"/api/drone/disk-pressure%2fderive"),
    (PATHS[1], b"/api/drone/%64isk-pressure/export"),
])
async def test_hosted_escaped_paths_not_authorization_aliases(client, path, raw_path):
    status, _, delivered, _ = await raw_chunks(client, [b"{}"], path=path, raw_path=raw_path)
    assert status == (403 if client.hosted_test else 200)
    assert delivered == ([] if client.hosted_test else [2])


@pytest.mark.anyio
async def test_local_token_is_not_hosted_identity(client):
    response = await client.get(CATALOG, headers={"Authorization": "Bearer synthetic-token"})
    assert response.status_code == (401 if client.hosted_test else 200)
