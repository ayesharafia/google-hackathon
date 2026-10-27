"""Disposable loopback-only local workspace for agent browser interaction checks."""

import argparse
import json
import os
import socket
import tempfile
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.projects.examples import create_hover_example
from physimesh.platform.scoped_artifacts import artifact_scope

parser = argparse.ArgumentParser()
parser.add_argument("--runtime", required=True)
parser.add_argument("--mode", choices=["local", "hosted", "public"], default="local")
args = parser.parse_args()
workspace = Path(__file__).resolve().parents[2]
runtime = Path(args.runtime).resolve()
if os.environ.get("PHYSIMESH_BROWSER_DISPOSABLE") != "1" or runtime.parent != workspace / ".backend":
    raise RuntimeError("Explicit disposable loopback fixture and workspace receipt required")
runtime.parent.mkdir(exist_ok=True)
root = Path(tempfile.mkdtemp(prefix="agent-ui-", dir=runtime.parent))
token = "synthetic-agent-browser-key"
app = create_app(
    Settings(
        root,
        root / "jobs.sqlite",
        token,
        None,
        hosted_mode=args.mode == "hosted",
        public_access=args.mode == "public",
    )
)
password = "Synthetic-browser-agent-123"
if args.mode == "hosted":
    identity = app.state.identity
    owner_id = identity.provision("owner@example.test", password=password)
    identity.provision("viewer@example.test", password=password)
    login = identity.login("owner@example.test", password)
    owner = identity.session(login["token"])
    organization = identity.organization(owner_id, "Disposable agent browser fixture")
    headers = {"Authorization": "Bearer " + login["token"], "X-Organization-ID": organization}
    with TestClient(app) as client:
        project = client.post("/api/drone/projects/examples/hover", headers=headers).json()
        other = client.post(
            "/api/drone/projects", headers=headers, json={"title": "Other private project"}
        ).json()
        revision = client.post(
            "/api/drone/projects/" + project["project_id"] + "/revisions",
            headers=headers,
            json={"expected_version": project["draft_version"]},
        ).json()
    viewer = identity.session(identity.login("viewer@example.test", password)["token"])
    invitation = identity.invite(owner, project["project_id"], viewer.email, "viewer")
    identity.accept(viewer, invitation["invitation_token"])
else:
    project = create_hover_example(app.state.projects)
    other = app.state.projects.create("Other synthetic workspace")
    revision = app.state.projects.freeze(project["project_id"], project["draft_version"], "screening")
with artifact_scope(project["project_id"]):
    study = app.state.studies.run(project["project_id"], revision["revision_sha256"])
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
runtime.write_text(
    json.dumps(
        {
            "base": "http://127.0.0.1:" + str(sock.getsockname()[1]),
            "pid": os.getpid(),
            "token": token,
            "project_id": project["project_id"],
            "other_project_id": other["project_id"],
            "study_sha256": study["study_sha256"],
            "data_root": str(root),
            "mode": args.mode,
            "password": password,
        }
    )
    + "\n"
)
print("Disposable agent fixture ready", flush=True)
uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False)).run(sockets=[sock])
