import json

import pytest

from physimesh.drone.ledger_solved_sensitivity import EVALUATION, evaluate_ledger_solved_sensitivity
from physimesh.drone.provenance import sha256_record

from .test_ledger_solved_sensitivity import request as assembly_request
from .test_model_graph_application import client as client  # noqa: PLC0414

PATH = "/api/drone/ledger-solved-sensitivity/evaluate"
CATALOG = "/api/drone/ledger-solved-sensitivity/catalog"


def test_evaluate(client):
    body = assembly_request()
    direct = evaluate_ledger_solved_sensitivity(body)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    for key, value in direct.items():
        assert result[key] == value
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["analysis"]["sensitivity_state"] == "COMPUTED_AT_RESIDUAL_MET_POINT"
    assert result["outputs"]["analysis"]["sensitivity"]["evaluations_used"] == 13
    assert result["request_sha256"] == result["input_sha256"] == sha256_record(body)
    assert result.pop("evaluation_sha256") == sha256_record(result)


def test_catalog(client):
    response = client.get(CATALOG, headers=client.auth_headers)
    assert response.status_code == 200
    catalog = response.json()
    assert catalog["evaluation"] == EVALUATION
    assert catalog["physical_validation"] == "NOT_ESTABLISHED"
    assert catalog["numerical_qualification"] == "NOT_ESTABLISHED"
    assert catalog["runtime_identity"] == "NOT_ESTABLISHED"
    assert catalog["feasibility"] is None
    assert catalog["limits"]["body_bytes"] == 131072
    assert catalog["limits"]["json_values"] == 65536
    assert catalog["schema_version"] == "ledger_solved_wrench_sensitivity_v1"
    assert catalog["limits"]["max_solver_evaluations"] == {"type": "integer", "minimum": 2, "maximum": 64}


@pytest.mark.parametrize("raw", [b'{"evaluation":1,"evaluation":2}', b'{"evaluation":NaN}', b"\xff", b"[]"])
def test_invalid_json(client, raw):
    response = client.post(
        PATH, content=raw, headers={**client.auth_headers, "Content-Type": "application/json"}
    )
    assert response.status_code == 422 and response.json() == {"detail": "Invalid ledger solved sensitivity request."}


def test_invalid_max_evaluations(client):
    body = json.loads(json.dumps(assembly_request()))
    body["analysis_template"]["solve"]["max_evaluations"] = 65
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "GRAPH_INVALID"
    assert result["outputs"] == {}
    assert result["stages"] == []
    assert "request_sha256" not in result
    assert "input_sha256" not in result
    assert "evaluation_sha256" not in result


def test_body_cap(client):
    raw = json.dumps(assembly_request()).encode()
    boundary = raw + b" " * (131072 - len(raw))
    headers = {**client.auth_headers, "Content-Type": "application/json"}
    assert client.post(PATH, content=boundary, headers=headers).status_code == 200
    response = client.post(PATH, content=iter((boundary, b" ")), headers=headers)
    assert response.status_code == 413
    assert response.json()["detail"] == "request byte budget exceeded"
    assert client.post(PATH, content=boundary + b" ", headers=headers).status_code == 413


def test_auth_csrf(client):
    assert client.get(CATALOG).status_code in (401, 403)
    assert client.post(PATH, json=assembly_request()).status_code in (401, 403)
    foreign = {"Origin": "https://foreign.example"}
    same = {"Origin": "http://testserver"}
    assert (
        client.post(PATH, json=assembly_request(), headers={**client.auth_headers, **foreign}).status_code
        == 200
    )
    if client.hosted_test:
        for suffix in ("/", "/extra", "-extra"):
            assert (
                client.get(CATALOG + suffix, headers=client.auth_headers, follow_redirects=False).status_code
                == 403
            )
            assert (
                client.post(
                    PATH + suffix,
                    json=assembly_request(),
                    headers=client.auth_headers,
                    follow_redirects=False,
                ).status_code
                == 403
            )
        return
    session = client.post("/api/session", headers={**client.auth_headers, **same})
    assert session.status_code == 200
    assert client.get(CATALOG).status_code == 200
    assert client.post(PATH, json=assembly_request()).status_code == 403
    assert client.post(PATH, json=assembly_request(), headers=foreign).status_code == 403
    assert client.post(PATH, json=assembly_request(), headers=same).status_code == 200


def test_execution_atomic(client, monkeypatch):
    import physimesh.drone.ledger_solved_sensitivity as m

    def fail(*args, **kwargs):
        raise RuntimeError("private failure marker")

    body = assembly_request()
    monkeypatch.setattr(m.ss.ws, "evaluate_static_wrench_solve", fail)
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "EXECUTION_FAILED"
    assert result["diagnostics_complete"] is False
    assert result["stages"] == []
    assert result["outputs"] == {}
    assert result["output_units"] == {}
    assert result["request_sha256"] == sha256_record(body)
    assert result["input_sha256"] == sha256_record(body)
    unsigned = dict(result)
    evaluation_hash = unsigned.pop("evaluation_sha256")
    assert evaluation_hash == sha256_record(unsigned)
    assert "private failure marker" not in response.text


def test_json_depth_budget(client):
    nested = {}
    cursor = nested
    for _ in range(12):
        cursor["x"] = {}
        cursor = cursor["x"]
    # The byte budget binds first for the dense numeric fixture, so test depth here.
    raw = json.dumps(nested, separators=(",", ":")).encode("utf-8")
    assert len(raw) <= 131072
    response = client.post(PATH, content=raw, headers={**client.auth_headers, "Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid ledger solved sensitivity request."


def test_evaluation_budget_preflight(client, monkeypatch):
    import physimesh.drone.ledger_solved_sensitivity as m

    body = assembly_request()
    body["analysis_template"]["solve"]["max_evaluations"] = 65
    calls = []

    def unexpected_evaluation(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Forward rotor evaluation must not run")

    monkeypatch.setattr(
        m.ss.ws, "evaluate_static_wrench_solve", unexpected_evaluation
    )
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "GRAPH_INVALID"
    assert calls == []
    assert not {"request_sha256", "input_sha256", "evaluation_sha256"} & result.keys()
    assert result["stages"] == []
    assert result["outputs"] == {}
    assert result["output_units"] == {}
    assert result["diagnostics_complete"] is False


def test_exact_json_value_budget(client, monkeypatch):
    import physimesh.api.ledger_solved_sensitivity as route
    from physimesh.drone.model_graph_execution import _json

    calls = []

    def recorder(*args, **kwargs):
        calls.append((args, kwargs))
        return {"status": "GRAPH_INVALID"}

    monkeypatch.setattr(route, "evaluate_ledger_solved_sensitivity", recorder)
    headers = {**client.auth_headers, "Content-Type": "application/json"}
    body = {"": [[0] * 256 for _ in range(254)] + [[0] * 254]}

    def value_count(value):
        if isinstance(value, dict):
            return 1 + sum(
                value_count(key) + value_count(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return 1 + sum(value_count(item) for item in value)
        return 1

    assert len(body[""]) == 255
    assert value_count(body) == 65536
    payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
    assert len(payload) == 131072

    response = client.post(PATH, content=payload, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"status": "GRAPH_INVALID"}
    assert len(calls) == 1
    assert calls[0] == ((body,), {})

    _json(body, budget=65536)

    body[""][-1].append(0)
    assert value_count(body) == 65537
    with pytest.raises(ValueError):
        _json(body, budget=65536)

    payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
    assert len(payload) == 131074
    response = client.post(PATH, content=payload, headers=headers)
    assert response.status_code == 413
    assert response.json()["detail"] == "request byte budget exceeded"
    assert len(calls) == 1


def test_unreachable_honest_numerical_outcome(client, monkeypatch):
    import physimesh.drone.ledger_solved_sensitivity as m

    sensitivity_calls = []

    def forbidden_sensitivity(*args, **kwargs):
        sensitivity_calls.append((args, kwargs))
        raise AssertionError("Sensitivity must not run when residual is unmet")

    monkeypatch.setattr(
        m.ss.sn, "evaluate_wrench_sensitivity", forbidden_sensitivity
    )

    body = assembly_request()
    body["analysis_template"]["solve"]["required_net_force_body_n"][0] = 1e9
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert sensitivity_calls == []
    result = response.json()
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["analysis"]["sensitivity_state"] == "NOT_RUN_RESIDUAL_UNMET"
    assert result["outputs"]["analysis"]["sensitivity"] is None
    assert result["outputs"]["analysis"]["solve"]["outcome"] in ("EVALUATION_LIMIT", "SOLVER_STOPPED")
    assert result["outputs"]["analysis"]["solve"]["selected_candidate"]["max_scaled_residual"] > 1
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["numerical_qualification"] == "NOT_ESTABLISHED"
    assert result["runtime_identity"] == "NOT_ESTABLISHED"
    assert result["feasibility"] is None
    assert result["input_sha256"] == result["request_sha256"] == sha256_record(body)
    evaluation_sha256 = result.pop("evaluation_sha256")
    assert evaluation_sha256 == sha256_record(result)


def test_threadpool_dispatch(client, monkeypatch):
    import physimesh.api.ledger_solved_sensitivity as route

    body = assembly_request()
    calls = []

    async def dispatch(function, *args):
        calls.append((function, args))
        return function(*args)

    monkeypatch.setattr(route, "run_in_threadpool", dispatch)
    response = client.post(PATH, json=body, headers=client.auth_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "COMPUTED_EXPERIMENTAL"
    assert len(calls) == 1
    function, args = calls[0]
    assert function is route.evaluate_ledger_solved_sensitivity
    assert args == (body,)


def test_actual_evaluation_limit(client, monkeypatch):
    import physimesh.drone.ledger_solved_sensitivity as m

    sensitivity_calls = []

    def forbidden_sensitivity(*args, **kwargs):
        sensitivity_calls.append((args, kwargs))
        raise AssertionError("Sensitivity must not run when residual is unmet")

    monkeypatch.setattr(
        m.ss.sn, "evaluate_wrench_sensitivity", forbidden_sensitivity
    )

    body = assembly_request()
    for index, row in enumerate(body["analysis_template"]["solve"]["rotor_speed_bounds"]):
        row["initial_angular_speed_rad_s"] = (250, 270)[index]
    body["analysis_template"]["solve"]["max_evaluations"] = 2
    response = client.post(PATH, json=body, headers=client.auth_headers)
    assert response.status_code == 200
    assert sensitivity_calls == []
    result = response.json()
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["analysis"]["sensitivity_state"] == "NOT_RUN_RESIDUAL_UNMET"
    assert result["outputs"]["analysis"]["sensitivity"] is None
    outputs = result["outputs"]["analysis"]["solve"]
    assert outputs["outcome"] == "EVALUATION_LIMIT"
    assert outputs["evaluations_used"] == 2
    assert len(outputs["candidates"]) == 2
    assert len(result["stages"]) == 2
    assert result["stages"][0]["stage_id"] == "ledger"
    assert result["stages"][1]["stage_id"] == "solved_sensitivity"
    selected_candidate = outputs["selected_candidate"]
    assert selected_candidate["max_scaled_residual"] > 1
    assert outputs["assembly"]["net_force_body_n"] == selected_candidate["net_force_body_n"]
    assert result["request_sha256"] == result["input_sha256"] == sha256_record(body)
    evaluation_hash = result.pop("evaluation_sha256")
    assert evaluation_hash == sha256_record(result)
