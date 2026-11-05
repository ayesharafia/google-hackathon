import base64

from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings

AUTH = {"Authorization": "Bearer agent-test-token", "Origin": "http://testserver"}
MASTER = base64.urlsafe_b64encode(b"m" * 32).decode()


def test_settings_persist_encrypted_and_chat_uses_saved_key(tmp_path, monkeypatch):
    from physimesh.agent import chat

    settings = Settings(tmp_path, tmp_path / "jobs.sqlite", "agent-test-token", None, provider_encryption_key=MASTER)
    monkeypatch.setattr(chat, "secure_origin", lambda request: True)
    seen = []
    monkeypatch.setattr(chat, "groq_completion", lambda key, model, *args: (seen.append((key, model)) or {"role": "assistant", "content": "Ready"}))
    with TestClient(create_app(settings)) as client:
        saved = client.put("/api/drone/agent/provider-settings", headers=AUTH, json={"key": "sample-private-key", "model": "openai/gpt-oss-120b"})
        assert saved.status_code == 200 and "sample-private-key" not in saved.text
        project = client.post("/api/drone/projects/examples/hover", headers=AUTH).json()
    assert b"sample-private-key" not in (tmp_path / "projects.sqlite").read_bytes()
    with TestClient(create_app(settings)) as client:
        info = client.get("/api/drone/agent/provider-settings", headers=AUTH)
        assert info.json()["configured"] and "sample-private-key" not in info.text
        result = client.post("/api/drone/agent/chat", headers=AUTH, json={"project_id": project["project_id"], "prompt": "hello", "run_id": "a" * 32})
        assert result.status_code == 200 and result.json()["message"] == "Ready"
        assert seen == [("sample-private-key", "openai/gpt-oss-120b")]
        assert client.delete("/api/drone/agent/provider-settings", headers=AUTH).status_code == 200
        assert not client.get("/api/drone/agent/provider-settings", headers=AUTH).json()["configured"]


def test_settings_refuse_missing_encryption_key_without_echoing_input(workspace, monkeypatch):
    from physimesh.agent import chat
    monkeypatch.setattr(chat, "secure_origin", lambda request: True)
    client, _ = workspace
    response = client.put("/api/drone/agent/provider-settings", headers=AUTH, json={"key": "sample-private-key", "model": "model"})
    assert response.status_code == 503 and "sample-private-key" not in response.text


def test_invalid_request_and_delegated_client_never_expose_key(workspace, monkeypatch):
    from physimesh.agent import chat
    monkeypatch.setattr(chat, "secure_origin", lambda request: True)
    client, project = workspace
    bad = client.put("/api/drone/agent/provider-settings", headers=AUTH, json={"key": "sample-private-key", "model": "bad model"})
    assert bad.status_code == 422 and "sample-private-key" not in bad.text
    grant = client.post("/api/drone/agent/grants", headers=AUTH, json={"project_id": project["project_id"], "name": "test", "groups": ["read"], "lifetime_s": 3600}).json()
    denied = client.get("/api/drone/agent/provider-settings", headers={"Authorization": "Bearer " + grant["token"]})
    assert denied.status_code == 403


def test_ciphertext_is_actor_bound_and_tampering_is_rejected(tmp_path):
    import pytest
    from fastapi import HTTPException

    from physimesh.agent.provider_settings import ProviderInput

    settings = Settings(tmp_path, tmp_path / "jobs.sqlite", "agent-test-token", None, provider_encryption_key=MASTER)
    app = create_app(settings)
    store = app.state.provider_settings
    store.save("hosted:user-a", ProviderInput(key="sample-private-key", model="model"))
    assert store.get("hosted:user-b") is None
    with app.state.metadata.connection(write=True) as db:
        db.execute("INSERT INTO agent_provider_settings(actor,model,ciphertext,updated) SELECT ?,model,ciphertext,updated FROM agent_provider_settings WHERE actor=?", ("hosted:user-b", "hosted:user-a"))
    with pytest.raises(HTTPException):
        store.resolve("hosted:user-b")
    store.save("hosted:user-a", ProviderInput(key="", model="other-model"))
    assert store.resolve("hosted:user-a") == ("sample-private-key", "other-model")


def test_hosted_settings_are_isolated_by_signed_in_user(tmp_path, monkeypatch):
    from physimesh.agent import chat

    monkeypatch.setattr(chat, "secure_origin", lambda request: True)
    settings = Settings(tmp_path, tmp_path / "jobs.sqlite", "", None, hosted_mode=True, provider_encryption_key=MASTER)
    with TestClient(create_app(settings)) as client:
        identity = client.app.state.identity
        identity.provision("one@example.test", password="Synthetic-password-123")
        identity.provision("two@example.test", password="Synthetic-password-456")
        one = identity.login("one@example.test", "Synthetic-password-123")["token"]
        two = identity.login("two@example.test", "Synthetic-password-456")["token"]
        headers_one = {"Authorization": "Bearer " + one, "Origin": "http://testserver"}
        headers_two = {"Authorization": "Bearer " + two, "Origin": "http://testserver"}
        assert client.put("/api/drone/agent/provider-settings", headers=headers_one, json={"key": "sample-private-key", "model": "model"}).status_code == 200
        assert client.get("/api/drone/agent/provider-settings", headers=headers_one).json()["configured"]
        assert not client.get("/api/drone/agent/provider-settings", headers=headers_two).json()["configured"]
        assert client.delete("/api/drone/agent/provider-settings", headers=headers_two).status_code == 200
        assert client.get("/api/drone/agent/provider-settings", headers=headers_one).json()["configured"]
