import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings, load_settings


def make(tmp_path, digest=None):
    s = Settings(tmp_path, tmp_path / "jobs.sqlite", "test-token", digest)
    return TestClient(create_app(s))


def test_health_reports_backend_pin_state(tmp_path):
    r = make(tmp_path).get("/api/health")
    assert r.status_code == 200 and r.json()["backend_pinned"] is False


def test_drone_routes_require_token(tmp_path):
    c = make(tmp_path)
    assert c.post("/api/drone/validate", json={}).status_code == 401


def test_missing_token_setting_refuses_start():
    with pytest.raises(ValueError, match="PHYSIMESH_API_TOKEN"):
        load_settings({"PHYSIMESH_DATA_ROOT": "/tmp/x"})


def test_invalid_token_is_refused(tmp_path):
    assert make(tmp_path).post("/api/drone/validate", json={},
                              headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_future_drone_routes_are_protected(tmp_path):
    assert make(tmp_path).get("/api/drone/future").status_code == 401


def test_validator_is_explicitly_unavailable(tmp_path):
    response = make(tmp_path).post("/api/drone/validate", json={},
                                  headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 501
    assert response.json()["status"] == "inputs_incomplete"
    assert response.json()["available"] is False


def test_direct_settings_cannot_bypass_missing_token(tmp_path):
    with pytest.raises(ValueError, match="PHYSIMESH_API_TOKEN"):
        Settings(tmp_path, tmp_path / "jobs.sqlite", " ", None)


def test_malformed_pin_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="immutable"):
        Settings(tmp_path, tmp_path / "jobs.sqlite", "test-token", "image@sha256:bad")


def test_configured_pin_is_not_a_capability_claim(tmp_path):
    response = make(tmp_path, "image@sha256:" + "a" * 64).get("/api/health")
    assert response.json()["backend_pinned"] is True
    assert response.json()["capabilities"] == []
    assert response.json()["workflow_ready"] is False


def test_web_assets_are_served_without_exposing_workspace(tmp_path):
    client = make(tmp_path)
    assert client.get("/web/").status_code == 200
    assert client.get("/web/js/app.js").status_code == 200
    assert client.get("/web/../plan.md").status_code == 404
    assert client.get("/web/%2e%2e/plan.md").status_code == 404
