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
