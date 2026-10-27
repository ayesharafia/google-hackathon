"""Actual PostgreSQL transactions; requires an explicitly disposable test DSN."""

import concurrent.futures
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from tests.agent.test_foundation import ROOT, call


@pytest.mark.integration
def test_postgres_scoped_approval_atomic_concurrency_and_restart(tmp_path):
    url = os.environ.get("PHYSIMESH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("explicit disposable PostgreSQL DSN required")
    settings = Settings(tmp_path, tmp_path / "jobs.sqlite", "", None, hosted_mode=True, database_url=url)
    with TestClient(create_app(settings)) as c:
        identity = c.app.state.identity
        email = uuid4().hex + "@example.test"
        uid = identity.provision(email, password="Synthetic-PG-agent-test-123")
        login = identity.login(email, "Synthetic-PG-agent-test-123")
        org = identity.organization(uid, "Disposable agent integration")
        headers = {
            "Authorization": "Bearer " + login["token"],
            "Origin": "http://testserver",
            "X-Organization-ID": org,
        }
        p = c.post("/api/drone/projects/examples/hover", headers=headers).json()
        pid = p["project_id"]
        g = c.post(
            ROOT + "/grants",
            headers=headers,
            json={
                "project_id": pid,
                "name": "PG synthetic client",
                "groups": ["read", "propose", "change", "study"],
            },
        ).json()
        proposal = call(
            c,
            g["token"],
            "design.propose",
            {
                "project_id": pid,
                "expected_version": 1,
                "edits": [{"field": "mission.duration_s", "value": 240.0, "unit": "s"}],
            },
        ).json()["data"]
        args = {"project_id": pid, "proposal_id": proposal["proposal_id"]}
        request_id = uuid4().hex
        pending = call(c, g["token"], "proposal.apply", args, request_id).json()
        confirmed = c.post(
            ROOT + "/reviews/" + pending["data"]["review_id"] + "/confirm",
            headers=headers,
            json={"execute": False},
        )
        assert confirmed.status_code == 200, confirmed.text
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            responses = list(
                pool.map(lambda _: call(c, g["token"], "proposal.apply", args, request_id), range(2))
            )
        assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
        assert responses[0].json() == responses[1].json()
        assert c.get("/api/drone/projects/" + pid, headers=headers).json()["draft_version"] == 2
        result = responses[0].json()
    with TestClient(create_app(settings)) as restarted:
        assert call(restarted, g["token"], "proposal.apply", args, request_id).json() == result
        read = call(
            restarted, g["token"], "receipt.get", {"project_id": pid, "receipt_id": result["receipt_id"]}
        )
        assert read.json()["data"] == result
        frozen = call(
            restarted, g["token"], "design.freeze", {"project_id": pid, "expected_version": 2}
        ).json()
        revision = restarted.post(
            ROOT + "/reviews/" + frozen["data"]["review_id"] + "/confirm",
            headers=headers,
            json={"execute": True},
        ).json()["data"]
        pending = call(
            restarted,
            g["token"],
            "study.run",
            {"project_id": pid, "revision_sha256": revision["revision_sha256"]},
        ).json()
        job = restarted.post(
            ROOT + "/reviews/" + pending["data"]["review_id"] + "/confirm",
            headers=headers,
            json={"execute": True},
        )
        assert job.status_code == 200, job.text
        assert job.json()["status"] == "queued" and job.json()["data"]["state"] == "queued"
        jid = job.json()["data"]["job_id"]
        job_args = {"project_id": pid, "job_id": jid}
        assert call(restarted, g["token"], "job.get", job_args).json()["data"]["state"] == "queued"
        for action, state in [("job.cancel", "cancelled"), ("job.retry", "queued")]:
            pending = call(restarted, g["token"], action, job_args).json()
            result = restarted.post(
                ROOT + "/reviews/" + pending["data"]["review_id"] + "/confirm",
                headers=headers,
                json={"execute": True},
            )
            assert result.status_code == 200, result.text
            assert result.json()["data"]["state"] == state
