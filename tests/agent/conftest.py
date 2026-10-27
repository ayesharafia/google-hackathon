import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings


@pytest.fixture
def workspace(tmp_path):
    with TestClient(create_app(Settings(tmp_path, tmp_path / "jobs.sqlite", "agent-test-token", None))) as c:
        p = c.post(
            "/api/drone/projects/examples/hover",
            headers={"Authorization": "Bearer agent-test-token", "Origin": "http://testserver"},
        ).json()
        yield c, p
