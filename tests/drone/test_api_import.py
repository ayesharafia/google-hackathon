import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.core.artifacts import ArtifactStore
from physimesh.drone.demo_geometry import binary_stl_bytes, icosphere_triangles


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(tmp_path, tmp_path / "jobs.sqlite", "test-token", None)))


def _upload(client, units="mm"):
    data = binary_stl_bytes(icosphere_triangles(1.0, 1))
    fields = {} if units is None else {"source_units": units}
    return client.post("/api/drone/import", headers={"Authorization": "Bearer test-token"},
                       data=fields, files={"files": ("sphere.stl", data, "model/stl")})


def test_import_converts_declared_units_and_returns_readiness(client):
    response = _upload(client)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "read_ok"
    assert data["unit_scale_to_m"] == pytest.approx(0.001)
    assert data["bounding_box_m"]["max"][0] <= 0.0005
    assert data["triangle_count"] == 80
    assert data["shell_count"] == 1
    assert data["topology_issues"] == []
    assert data["components"][0]["requires_user_tag"] is True
    assert data["note"] == "Import success means the file was read; it does not mean a valid CFD case was created."
    assert data["geometry_revision_sha256"] == _upload(client).json()["geometry_revision_sha256"]


def test_import_requires_explicit_source_units(client):
    response = _upload(client, None)
    assert response.status_code == 422
    assert "source_units" in response.text


def test_import_is_authenticated(client):
    response = client.post("/api/drone/import", data={"source_units": "m"})
    assert response.status_code == 401


def test_import_retains_original_and_applies_declared_transform(client):
    raw = binary_stl_bytes(icosphere_triangles(1.0, 1), header=b"solid binary-demo")
    transform = {"scale": 2, "rotation_deg_zyx": [0, 0, 0], "translation_m": [1, 2, 3]}
    response = client.post("/api/drone/import", headers={"Authorization": "Bearer test-token"},
                           data={"source_units": "m", "transform_json": json.dumps(transform)},
                           files={"files": ("sphere.stl", raw, "model/stl")})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["bounding_box_m"]["min"] == pytest.approx([0, 1, 2])
    assert data["bounding_box_m"]["max"] == pytest.approx([2, 3, 4])
    digest = hashlib.sha256(raw).hexdigest()
    store = ArtifactStore(client.app.state.settings.data_root / "artifacts")
    with store.open(digest) as retained:
        assert retained.read() == raw


def test_invalid_transform_is_refused(client):
    raw = binary_stl_bytes(icosphere_triangles(1.0, 0))
    response = client.post("/api/drone/import", headers={"Authorization": "Bearer test-token"},
                           data={"source_units": "m", "transform_json": '{"scale": 2}'},
                           files={"files": ("sphere.stl", raw, "model/stl")})
    assert response.status_code == 422
