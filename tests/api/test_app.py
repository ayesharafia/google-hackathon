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


def _template_project():
    import pathlib

    import yaml

    from physimesh.drone import models
    path = pathlib.Path(models.__file__).with_name("schema") / "drone_manifest_v1.yaml"
    return yaml.safe_load(path.read_text())


AUTH = {"Authorization": "Bearer test-token"}


def test_validate_reports_template_as_inputs_incomplete(tmp_path):
    response = make(tmp_path).post("/api/drone/validate", headers=AUTH,
                                   json={"project": _template_project(), "purpose": "screening"})
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is False and body["status"] == "inputs_incomplete"
    assert "rotors (count must be declared)" in body["blocking"]


def test_validate_rejects_malformed_project(tmp_path):
    response = make(tmp_path).post("/api/drone/validate", headers=AUTH,
                                   json={"project": {"identity": {}}, "purpose": "screening"})
    assert response.status_code == 422


def test_validate_rejects_unknown_purpose(tmp_path):
    response = make(tmp_path).post("/api/drone/validate", headers=AUTH,
                                   json={"project": _template_project(), "purpose": "publish"})
    assert response.status_code == 422


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


def test_explicit_local_mode_needs_no_token(tmp_path):
    settings = load_settings({'PHYSIMESH_DATA_ROOT': str(tmp_path), 'PHYSIMESH_LOCAL_NO_AUTH': '1'})
    assert settings.local_no_auth and settings.api_token == ''


def test_token_free_mode_rejects_network_binding(tmp_path):
    with pytest.raises(ValueError, match='loopback'):
        Settings(tmp_path, tmp_path / 'jobs.sqlite', '', None, bind_host='0.0.0.0', local_no_auth=True)
