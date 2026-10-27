import concurrent.futures
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings

AUTH = {"Authorization": "Bearer agent-test-token", "Origin": "http://testserver"}
ROOT = "/api/drone/agent"


def mint(c, pid, groups=None):
    response = c.post(
        ROOT + "/grants",
        headers=AUTH,
        json={
            "project_id": pid,
            "name": "Synthetic MCP client",
            "groups": groups or ["read", "propose", "change", "study"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def call(c, token, action, args, request_id=None):
    return c.post(
        ROOT + "/actions/" + action,
        headers={"Authorization": "Bearer " + token},
        json={
            "request_id": request_id or uuid4().hex,
            "arguments": args,
        },
    )


def approve(c, response, execute=True):
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["status"] == "awaiting_review", value
    return c.post(
        ROOT + "/reviews/" + value["data"]["review_id"] + "/confirm", headers=AUTH, json={"execute": execute}
    )


def test_scoped_catalog_and_credentials_cannot_escape_gateway(workspace):
    c, p = workspace
    g = mint(c, p["project_id"])
    headers = {"Authorization": "Bearer " + g["token"]}
    catalog = c.get(ROOT + "/catalog", headers=headers)
    assert catalog.status_code == 200
    names = [a["id"] for a in catalog.json()["actions"]]
    assert "design.propose" in names and not any("confirm" in a or "development" in a for a in names)
    assert c.get("/api/drone/projects", headers=headers).status_code == 401
    assert c.post(ROOT + "/grants", headers=headers, json={"project_id": p["project_id"]}).status_code == 403
    other = c.post("/api/drone/projects", headers=AUTH, json={"title": "Other project"}).json()
    assert call(c, g["token"], "design.get", {"project_id": other["project_id"]}).status_code == 403
    records = c.get(ROOT + "/grants", headers=AUTH).json()["grants"]
    assert all("token" not in row and "token_hash" not in row for row in records)


def test_review_apply_duplicate_and_undo_are_bound_to_exact_draft(workspace):
    c, p = workspace
    pid = p["project_id"]
    g = mint(c, pid)
    proposal = call(
        c,
        g["token"],
        "design.propose",
        {
            "project_id": pid,
            "expected_version": p["draft_version"],
            "edits": [{"field": "mission.duration_s", "value": 8.0, "unit": "min"}],
        },
    ).json()["data"]
    assert proposal["changes"][0]["after"] == 480.0
    args = {"project_id": pid, "proposal_id": proposal["proposal_id"]}
    request_id = uuid4().hex
    pending = call(c, g["token"], "proposal.apply", args, request_id)
    assert (
        c.post(
            ROOT + "/reviews/" + pending.json()["data"]["review_id"] + "/confirm",
            headers={"Authorization": "Bearer " + g["token"]},
            json={"execute": True},
        ).status_code
        == 403
    )
    applied = approve(c, pending)
    assert applied.status_code == 200, applied.text
    result = applied.json()
    assert result["status"] == "completed"
    assert call(c, g["token"], "proposal.apply", args, request_id).json() == result
    current = c.get("/api/drone/projects/" + pid, headers=AUTH).json()
    assert current["draft_version"] == p["draft_version"] + 1
    assert json.loads(current["snapshot_json"])["mission"]["duration_s"] == 480.0
    undone = approve(c, call(c, g["token"], "proposal.undo", args))
    assert undone.status_code == 200, undone.text
    current = c.get("/api/drone/projects/" + pid, headers=AUTH).json()
    assert current["draft_version"] == p["draft_version"] + 2
    assert json.loads(current["snapshot_json"]) == json.loads(p["snapshot_json"])


def test_stale_rejected_and_argument_changed_reviews_never_write(workspace):
    c, p = workspace
    pid = p["project_id"]
    g = mint(c, pid)
    proposal = call(
        c,
        g["token"],
        "design.propose",
        {
            "project_id": pid,
            "expected_version": 1,
            "edits": [{"field": "mission.duration_s", "value": 2.0, "unit": "min"}],
        },
    ).json()["data"]
    args = {"project_id": pid, "proposal_id": proposal["proposal_id"]}
    request_id = uuid4().hex
    pending = call(c, g["token"], "proposal.apply", args, request_id)
    raw = json.loads(p["snapshot_json"])
    raw["mission"]["duration_s"] = 90
    c.put(
        "/api/drone/projects/" + pid + "/draft",
        headers=AUTH,
        json={"expected_version": 1, "snapshot_json": json.dumps(raw)},
    )
    assert approve(c, pending).status_code == 409
    assert call(c, g["token"], "design.get", {"project_id": pid}, request_id).status_code == 422
    assert c.get("/api/drone/projects/" + pid, headers=AUTH).json()["draft_version"] == 2
    rejected = call(c, g["token"], "design.freeze", {"project_id": pid, "expected_version": 2})
    rid = rejected.json()["data"]["review_id"]
    assert c.post(ROOT + "/reviews/" + rid + "/reject", headers=AUTH).status_code == 200
    assert (
        c.post(ROOT + "/reviews/" + rid + "/confirm", headers=AUTH, json={"execute": True}).status_code == 422
    )


def test_units_shapes_duplicates_and_forged_permissions_are_refused(workspace):
    c, p = workspace
    pid = p["project_id"]
    g = mint(c, pid)
    edits = [
        [{"field": "mission.duration_s", "value": 4.0, "unit": "kg"}],
        [{"field": "mission.duration_s", "value": -4.0, "unit": "s"}],
        [{"field": "mass_kg", "item_name": "missing", "value": 4.0, "unit": "kg"}],
        [{"field": "mission.duration_s", "value": 4.0, "unit": "s", "approved": True}],
        [{"field": "mission.duration_s", "value": 4.0, "unit": "s"}] * 2,
        [{"field": "cg_body_m", "item_name": "structure", "value": [1.0, 2.0], "unit": "m"}],
    ]
    for values in edits:
        response = call(
            c, g["token"], "design.propose", {"project_id": pid, "expected_version": 1, "edits": values}
        )
        assert response.status_code == 422, response.text
    assert call(c, g["token"], "owner.execute", {"command": "anything"}).status_code == 422
    assert c.get("/api/drone/projects/" + pid, headers=AUTH).json()["draft_version"] == 1
    assert (
        c.post(
            ROOT + "/grants",
            headers={"Authorization": AUTH["Authorization"]},
            json={"project_id": pid, "name": "No origin"},
        ).status_code
        == 403
    )


def test_grant_defaults_quota_revoke_expiry_rotation_and_resource_scope(workspace):
    c, p = workspace
    pid = p["project_id"]
    g = c.post(
        ROOT + "/grants", headers=AUTH, json={"project_id": pid, "name": "Read and propose", "max_calls": 1}
    ).json()
    args = {"project_id": pid}
    req = uuid4().hex
    first = call(c, g["token"], "design.get", args, req)
    assert first.status_code == 200
    assert call(c, g["token"], "design.get", args, req).json() == first.json()
    assert call(c, g["token"], "design.get", args).status_code == 403
    assert call(c, g["token"], "design.freeze", {"project_id": pid, "expected_version": 1}).status_code == 403
    h = mint(c, pid)
    headers = {"Authorization": "Bearer " + h["token"]}
    other = c.post("/api/drone/projects", headers=AUTH, json={"title": "Private other"}).json()
    assert (
        c.get(
            ROOT + "/resource",
            headers=headers,
            params={"uri": "physicore://projects/" + other["project_id"] + "/draft"},
        ).status_code
        == 403
    )
    assert c.delete(ROOT + "/grants/" + h["grant_id"], headers=AUTH).status_code == 200
    assert c.get(ROOT + "/catalog", headers=headers).status_code == 403
    h = mint(c, pid)
    original = c.app.state.agent.store.clock
    c.app.state.agent.store.clock = lambda: h["expires"] + 1
    assert call(c, h["token"], "design.get", args).status_code == 403
    c.app.state.agent.store.clock = original
    h = mint(c, pid)
    from dataclasses import replace

    with TestClient(create_app(replace(c.app.state.settings, api_token="rotated-workspace-key"))) as rotated:
        assert call(rotated, h["token"], "design.get", args).status_code == 403


def test_concurrent_apply_commits_one_version_and_receipt(workspace):
    c, p = workspace
    pid = p["project_id"]
    g = mint(c, pid)
    proposal = call(
        c,
        g["token"],
        "design.propose",
        {
            "project_id": pid,
            "expected_version": 1,
            "edits": [{"field": "mission.duration_s", "value": 180.0, "unit": "s"}],
        },
    ).json()["data"]
    args = {"project_id": pid, "proposal_id": proposal["proposal_id"]}
    request_id = uuid4().hex
    approve(c, call(c, g["token"], "proposal.apply", args, request_id), execute=False)
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        responses = list(
            pool.map(lambda _: call(c, g["token"], "proposal.apply", args, request_id), range(2))
        )
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert responses[0].json() == responses[1].json()
    assert c.get("/api/drone/projects/" + pid, headers=AUTH).json()["draft_version"] == 2


def test_public_mode_and_unknown_schema_fail_closed(tmp_path):
    with TestClient(
        create_app(Settings(tmp_path, tmp_path / "jobs.sqlite", "", None, public_access=True))
    ) as c:
        assert c.get(ROOT + "/catalog").status_code == 403
        assert c.get("/api/session").json()["public_access"] is True
        db = c.app.state.metadata
        with db.connection(write=True) as connection:
            connection.execute("UPDATE agent_schema SET version=99")
    with pytest.raises(ValueError, match="unsupported agent schema"):
        create_app(Settings(tmp_path, tmp_path / "jobs.sqlite", "key", None))


def test_uncertain_admitted_study_never_reexecutes_on_retry(workspace, monkeypatch):
    c, p = workspace
    pid = p["project_id"]
    g = mint(c, pid)
    frozen = c.post(
        "/api/drone/projects/" + pid + "/revisions", headers=AUTH, json={"expected_version": 1}
    ).json()
    from physimesh.agent import operations

    actual = operations.run_study
    count = []

    def interrupted(*args, **kwargs):
        count.append(1)
        actual(*args, **kwargs)
        raise ValueError("Synthetic interruption after existing study retention")

    monkeypatch.setattr(operations, "run_study", interrupted)
    request_id = uuid4().hex
    args = {"project_id": pid, "revision_sha256": frozen["revision_sha256"]}
    pending = call(c, g["token"], "study.run", args, request_id)
    assert approve(c, pending).status_code == 422
    retried = call(c, g["token"], "study.run", args, request_id)
    assert retried.json()["status"] == "uncertain" and len(count) == 1
    assert len(c.get("/api/drone/projects/" + pid, headers=AUTH).json()["studies"]) == 1


def test_hosted_viewer_read_and_parent_session_revocation(tmp_path):
    with TestClient(
        create_app(Settings(tmp_path, tmp_path / "jobs.sqlite", "", None, hosted_mode=True))
    ) as c:
        identity = c.app.state.identity
        owner_id = identity.provision("owner@example.test", password="Synthetic-password-123")
        viewer_id = identity.provision("viewer@example.test", password="Synthetic-password-456")
        login = identity.login("owner@example.test", "Synthetic-password-123")
        owner = identity.session(login["token"])
        org = identity.organization(owner_id, "Synthetic agent test")
        headers = {
            "Authorization": "Bearer " + login["token"],
            "Origin": "http://testserver",
            "X-Organization-ID": org,
        }
        project = c.post("/api/drone/projects/examples/hover", headers=headers).json()
        pid = project["project_id"]
        viewer_login = identity.login("viewer@example.test", "Synthetic-password-456")
        viewer = identity.session(viewer_login["token"])
        invite = identity.invite(owner, pid, viewer.email, "viewer")
        identity.accept(viewer, invite["invitation_token"])
        vh = {"Authorization": "Bearer " + viewer_login["token"], "Origin": "http://testserver"}
        granted = c.post(
            ROOT + "/grants",
            headers=vh,
            json={"project_id": pid, "name": "Read-only viewer", "groups": ["read"]},
        )
        assert granted.status_code == 201, granted.text
        g = granted.json()
        token = g["token"]
        assert call(c, token, "design.inspect", {"project_id": pid}).status_code == 200
        assert (
            call(
                c, token, "design.propose", {"project_id": pid, "expected_version": 1, "edits": []}
            ).status_code
            == 403
        )
        assert (
            c.post(
                ROOT + "/grants",
                headers=vh,
                json={"project_id": pid, "name": "Escalate", "groups": ["change"]},
            ).status_code
            == 403
        )
        identity.remove_member(owner, pid, viewer_id)
        assert call(c, token, "design.get", {"project_id": pid}).status_code == 403
        # A separate grant also loses authority when its parent session is revoked.
        gr = c.post(
            ROOT + "/grants", headers=headers, json={"project_id": pid, "name": "Owner session"}
        ).json()
        identity.revoke(owner)
        assert call(c, gr["token"], "design.get", {"project_id": pid}).status_code == 403


def test_receipt_budget_failure_rolls_back_draft_and_approval_consumption(workspace, monkeypatch):
    from physimesh.platform.database import Overloaded

    c, p = workspace
    pid = p["project_id"]
    g = mint(c, pid)
    proposal = call(
        c,
        g["token"],
        "design.propose",
        {
            "project_id": pid,
            "expected_version": 1,
            "edits": [{"field": "mission.duration_s", "value": 4.0, "unit": "min"}],
        },
    ).json()["data"]
    args = {"project_id": pid, "proposal_id": proposal["proposal_id"]}
    request_id = uuid4().hex
    pending = call(c, g["token"], "proposal.apply", args, request_id)
    original = c.app.state.agent.store.quota

    def refused(*args, **kwargs):
        original(*args, **kwargs)
        if kwargs.get("new_record") is False:
            raise Overloaded("Synthetic receipt budget failure")

    monkeypatch.setattr(c.app.state.agent.store, "quota", refused)
    assert approve(c, pending).status_code == 503
    assert c.get("/api/drone/projects/" + pid, headers=AUTH).json()["draft_version"] == 1
    monkeypatch.setattr(c.app.state.agent.store, "quota", original)
    assert approve(c, pending).json()["data"]["draft_version"] == 2
    assert call(c, g["token"], "proposal.apply", args, request_id).json()["data"]["draft_version"] == 2


def test_request_response_and_metadata_byte_limits(workspace):
    from physimesh.platform.database import Overloaded

    c, p = workspace
    pid = p["project_id"]
    g = mint(c, pid)
    response = c.post(
        ROOT + "/actions/design.get",
        headers={"Authorization": "Bearer " + g["token"], "Content-Type": "application/json"},
        content=b"x" * 262145,
    )
    assert response.status_code == 413
    with c.app.state.metadata.connection(write=True) as db:
        for table in ["agent_calls", "agent_reviews", "agent_proposals"]:
            with pytest.raises(Overloaded):
                c.app.state.agent.store.quota(db, table, pid, 64_000_001)
    data = json.loads(p["snapshot_json"])
    data["identity"]["description"] = "x" * 263000
    assert (
        c.put(
            "/api/drone/projects/" + pid + "/draft",
            headers=AUTH,
            json={"expected_version": 1, "snapshot_json": json.dumps(data)},
        ).status_code
        == 200
    )
    assert call(c, g["token"], "design.get", {"project_id": pid}).status_code == 422


def test_revocation_before_response_withholds_result_and_keeps_receipt(workspace, monkeypatch):
    c, p = workspace
    pid = p["project_id"]
    g = mint(c, pid)
    revision = c.post(
        "/api/drone/projects/" + pid + "/revisions", headers=AUTH, json={"expected_version": 1}
    ).json()
    from physimesh.agent import operations

    original = operations.run_study

    def revoke_after_retention(*args, **kwargs):
        result = original(*args, **kwargs)
        with c.app.state.metadata.connection(write=True) as db:
            db.execute("UPDATE agent_grants SET revoked=1 WHERE grant_id=?", (g["grant_id"],))
        return result

    monkeypatch.setattr(operations, "run_study", revoke_after_retention)
    pending = call(
        c, g["token"], "study.run", {"project_id": pid, "revision_sha256": revision["revision_sha256"]}
    )
    assert approve(c, pending).status_code == 403
    records = c.get(ROOT + "/records/" + pid, headers=AUTH).json()["invocations"]
    assert any(r["action"] == "study.run" and r["state"] == "completed" for r in records)
    assert len(c.get("/api/drone/projects/" + pid, headers=AUTH).json()["studies"]) == 1
