import json

import pytest

AUTH = {"Authorization": "Bearer agent-test-token", "Origin": "http://testserver"}


def test_chat_reads_only_selected_project_and_returns_actual_result(workspace, monkeypatch):
    from physimesh.agent import chat

    client, project = workspace
    pid = project["project_id"]
    monkeypatch.setattr(chat, "secure_origin", lambda request: True)
    calls = []

    def fake(key, model, messages, tools, timeout):
        assert "Do not claim capabilities" in messages[0]["content"]
        calls.append((messages, tools))
        if len(calls) == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "a",
                        "type": "function",
                        "function": {
                            "name": "physicore_design_get",
                            "arguments": json.dumps({"project_id": pid}),
                        },
                    }
                ],
            }
        assert json.loads(messages[-1]["content"])["status"] == "completed"
        return {"role": "assistant", "content": "Saved design inspected."}

    monkeypatch.setattr(chat, "groq_completion", fake)
    response = client.post(
        "/api/drone/agent/chat",
        headers=AUTH,
        json={
            "project_id": pid,
            "key": "synthetic-key",
            "model": "test-model",
            "prompt": "Inspect the design",
            "run_id": "a" * 32,
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["message"] == "Saved design inspected."
    assert result["actions"][0]["status"] == "completed"
    assert "synthetic-key" not in json.dumps(result)


def test_chat_cannot_use_another_project(workspace, monkeypatch):
    from physimesh.agent import chat

    client, project = workspace
    monkeypatch.setattr(chat, "secure_origin", lambda request: True)
    other = client.post("/api/drone/projects", headers=AUTH, json={"title": "Other"}).json()
    monkeypatch.setattr(
        chat,
        "groq_completion",
        lambda *args: {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "x",
                    "type": "function",
                    "function": {
                        "name": "physicore_design_get",
                        "arguments": json.dumps({"project_id": other["project_id"]}),
                    },
                }
            ],
        },
    )
    response = client.post(
        "/api/drone/agent/chat",
        headers=AUTH,
        json={
            "project_id": project["project_id"],
            "key": "synthetic-key",
            "model": "test-model",
            "prompt": "Read it",
            "run_id": "b" * 32,
        },
    )
    assert response.status_code == 400
    assert "synthetic-key" not in response.text


def test_chat_review_requires_human_then_continues_with_receipt(workspace, monkeypatch):
    from physimesh.agent import chat

    client, project = workspace
    pid = project["project_id"]
    monkeypatch.setattr(chat, "secure_origin", lambda request: True)
    proposal = client.post(
        "/api/drone/agent/actions/design.propose",
        headers=AUTH,
        json={
            "request_id": "proposal001",
            "arguments": {
                "project_id": pid,
                "expected_version": project["draft_version"],
                "edits": [{"field": "mission.duration_s", "value": 8.0, "unit": "min"}],
            },
        },
    ).json()["data"]
    count = []

    def provider(key, model, messages, tools, timeout):
        count.append(1)
        if len(count) == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "apply",
                        "type": "function",
                        "function": {
                            "name": "physicore_proposal_apply",
                            "arguments": json.dumps(
                                {"project_id": pid, "proposal_id": proposal["proposal_id"]}
                            ),
                        },
                    }
                ],
            }
        assert json.loads(messages[-1]["content"])["status"] == "completed"
        return {"role": "assistant", "content": "Applied."}

    monkeypatch.setattr(chat, "groq_completion", provider)
    body = {
        "project_id": pid,
        "key": "synthetic-key",
        "model": "test-model",
        "prompt": "Apply it",
        "run_id": "c" * 32,
    }
    first = client.post("/api/drone/agent/chat", headers=AUTH, json=body).json()
    assert first["status"] == "awaiting_review"
    assert (
        client.get("/api/drone/projects/" + pid, headers=AUTH).json()["draft_version"]
        == project["draft_version"]
    )
    resume = {**body, "prompt": "", "continuation": first["continuation"]}
    assert client.post("/api/drone/agent/chat", headers=AUTH, json=resume).status_code == 400
    result = client.post(
        "/api/drone/agent/reviews/" + first["review"]["data"]["review_id"] + "/confirm",
        headers=AUTH,
        json={"execute": True},
    )
    assert result.status_code == 200
    final = client.post("/api/drone/agent/chat", headers=AUTH, json=resume)
    assert final.status_code == 200 and final.json()["message"] == "Applied."
    assert "synthetic-key" not in json.dumps(final.json())


def test_chat_hides_provider_failure_and_limits_tools(workspace, monkeypatch):
    from physimesh.agent import chat

    client, project = workspace
    monkeypatch.setattr(chat, "secure_origin", lambda request: True)

    def bad(*args):
        raise RuntimeError("synthetic-secret")

    monkeypatch.setattr(chat, "groq_completion", bad)
    result = client.post(
        "/api/drone/agent/chat",
        headers=AUTH,
        json={
            "project_id": project["project_id"],
            "key": "synthetic-secret",
            "model": "test",
            "prompt": "hi",
            "run_id": "d" * 32,
        },
    )
    assert result.status_code == 400 and "synthetic-secret" not in result.text


@pytest.mark.parametrize("code, expected", [
    (400, "rejected"), (401, "authentication"), (403, "denied"),
    (422, "rejected"), (429, "limit"), (503, "unavailable"),
])
def test_chat_reports_provider_status_without_exposing_provider_data(workspace, monkeypatch, code, expected):
    import urllib.error

    from physimesh.agent import chat

    client, project = workspace
    monkeypatch.setattr(chat, "secure_origin", lambda request: True)

    class Opener:
        def open(self, request, timeout):
            assert request.get_header("User-agent") == "PhysiCore/1.0"
            raise urllib.error.HTTPError(request.full_url, code, "synthetic-secret", {}, None)

    monkeypatch.setattr(chat.urllib.request, "build_opener", lambda *args: Opener())
    response = client.post(
        "/api/drone/agent/chat", headers=AUTH,
        json={"project_id": project["project_id"], "key": "synthetic-secret",
              "model": "test", "prompt": "hi", "run_id": "e" * 32},
    )
    assert expected in response.json()["detail"].lower()
    assert "synthetic-secret" not in response.text


def test_stop_during_provider_call_prevents_subsequent_action(workspace, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from physimesh.agent import chat

    client, project = workspace
    monkeypatch.setattr(chat, "secure_origin", lambda request: True)
    started, release = Event(), Event()

    def provider(*args):
        started.set()
        assert release.wait(5)
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "one",
                    "type": "function",
                    "function": {
                        "name": "physicore_design_get",
                        "arguments": json.dumps({"project_id": project["project_id"]}),
                    },
                }
            ],
        }

    monkeypatch.setattr(chat, "groq_completion", provider)
    body = {
        "project_id": project["project_id"],
        "key": "synthetic-key",
        "model": "test",
        "prompt": "inspect",
        "run_id": "e" * 32,
    }
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(client.post, "/api/drone/agent/chat", headers=AUTH, json=body)
        assert started.wait(5)
        stop = client.post(
            "/api/drone/agent/chat/stop",
            headers=AUTH,
            json={"project_id": project["project_id"], "run_id": "e" * 32},
        )
        assert stop.json()["status"] == "stop_requested"
        release.set()
        result = future.result(timeout=5)
    assert result.json()["status"] == "stopped"
    assert result.json()["actions"] == []


def test_invalid_chat_body_does_not_echo_key(workspace):
    client, project = workspace
    response = client.post(
        "/api/drone/agent/chat",
        headers=AUTH,
        json={
            "project_id": project["project_id"],
            "key": "synthetic-key",
            "model": "bad model",
            "prompt": "hello",
            "run_id": "a" * 32,
        },
    )
    assert response.status_code == 422
    assert "synthetic-key" not in response.text


def test_tampered_conversation_and_delegated_client_are_refused(workspace, monkeypatch):
    from physimesh.agent import chat

    client, project = workspace
    monkeypatch.setattr(chat, "secure_origin", lambda request: True)
    monkeypatch.setattr(chat, "groq_completion", lambda *args: {"role": "assistant", "content": "Done"})
    body = {
        "project_id": project["project_id"],
        "key": "synthetic-key",
        "model": "test",
        "prompt": "hello",
        "run_id": "f" * 32,
    }
    initial = client.post("/api/drone/agent/chat", headers=AUTH, json=body).json()
    token = initial["continuation"]
    changed = ("A" if token[0] != "A" else "B") + token[1:]
    assert (
        client.post("/api/drone/agent/chat", headers=AUTH, json={**body, "continuation": changed}).status_code
        == 400
    )
    grant = client.post(
        "/api/drone/agent/grants",
        headers=AUTH,
        json={"project_id": project["project_id"], "name": "read", "groups": ["read"]},
    ).json()
    response = client.post(
        "/api/drone/agent/chat",
        headers={"Authorization": "Bearer " + grant["token"], "Origin": "http://testserver"},
        json=body,
    )
    assert response.status_code == 403


def test_tool_call_limit_stops_repeating_model(workspace, monkeypatch):
    from physimesh.agent import chat

    client, project = workspace
    monkeypatch.setattr(chat, "secure_origin", lambda request: True)
    count = []

    def repeated(*args):
        count.append(1)
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": str(len(count)),
                    "type": "function",
                    "function": {
                        "name": "physicore_design_get",
                        "arguments": json.dumps({"project_id": project["project_id"]}),
                    },
                }
            ],
        }

    monkeypatch.setattr(chat, "groq_completion", repeated)
    body = {
        "project_id": project["project_id"],
        "key": "synthetic-key",
        "model": "test",
        "prompt": "inspect",
        "run_id": "9" * 32,
    }
    response = client.post("/api/drone/agent/chat", headers=AUTH, json=body)
    assert response.status_code == 400
    assert len(count) == 8


def test_hosted_viewer_sees_only_allowed_chat_tools(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from physimesh.agent import chat
    from physimesh.api.app import create_app
    from physimesh.api.settings import Settings

    monkeypatch.setattr(chat, "secure_origin", lambda request: True)
    with TestClient(
        create_app(Settings(tmp_path, tmp_path / "jobs.sqlite", "", None, hosted_mode=True))
    ) as client:
        identity = client.app.state.identity
        owner_id = identity.provision("owner@example.test", password="Synthetic-password-123")
        identity.provision("viewer@example.test", password="Synthetic-password-456")
        login = identity.login("owner@example.test", "Synthetic-password-123")
        owner = identity.session(login["token"])
        org = identity.organization(owner_id, "Synthetic")
        headers = {
            "Authorization": "Bearer " + login["token"],
            "Origin": "http://testserver",
            "X-Organization-ID": org,
        }
        project = client.post("/api/drone/projects/examples/hover", headers=headers).json()
        pid = project["project_id"]
        viewer_login = identity.login("viewer@example.test", "Synthetic-password-456")
        viewer = identity.session(viewer_login["token"])
        identity.accept(viewer, identity.invite(owner, pid, viewer.email, "viewer")["invitation_token"])

        def provider(key, model, messages, tools, timeout):
            names = {tool["function"]["name"] for tool in tools}
            assert "physicore_design_get" in names and "physicore_proposal_apply" not in names
            return {"role": "assistant", "content": "Read only."}

        monkeypatch.setattr(chat, "groq_completion", provider)
        response = client.post(
            "/api/drone/agent/chat",
            headers={"Authorization": "Bearer " + viewer_login["token"], "Origin": "http://testserver"},
            json={
                "project_id": pid,
                "key": "synthetic-key",
                "model": "test",
                "prompt": "inspect",
                "run_id": "1" * 32,
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["message"] == "Read only."
