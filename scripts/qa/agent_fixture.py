"""Disposable loopback-only local workspace for agent browser interaction checks."""

import argparse
import json
import os
import socket
import tempfile
from contextlib import nullcontext
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.platform.scoped_artifacts import artifact_scope
from physimesh.projects.examples import create_hover_example

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
        provider_encryption_key=os.environ.get("PHYSIMESH_PROVIDER_ENCRYPTION_KEY"),
        **(
            {
                "remote_mcp_origin": "https://app.example",
                "remote_mcp_issuer": "https://issuer.example",
                "remote_mcp_jwks_url": "https://issuer.example/jwks",
            }
            if os.environ.get("PHYSIMESH_FAKE_REMOTE") == "1" and args.mode == "hosted"
            else {}
        ),
    )
)
if os.environ.get("PHYSIMESH_FAKE_GROQ") == "1":
    import physimesh.agent.chat as chat_module

    def fake_groq(key, model, messages, tools, timeout):
        assert key == "synthetic-groq-key"

        def tool(name, args):
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "action",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                ],
            }

        if messages[-1]["role"] == "user":
            if "duration" in messages[-1]["content"]:
                return tool(
                    "physicore_design_propose",
                    {
                        "project_id": project["project_id"],
                        "expected_version": app.state.projects.repository.get(project["project_id"])[
                            "draft_version"
                        ],
                        "edits": [{"field": "mission.duration_s", "value": 8.0, "unit": "min"}],
                    },
                )
            return tool("physicore_design_get", {"project_id": project["project_id"]})
        result = json.loads(messages[-1]["content"])
        if result.get("action") == "design.propose":
            return tool(
                "physicore_proposal_apply",
                {"project_id": project["project_id"], "proposal_id": result["data"]["proposal_id"]},
            )
        if result.get("status") == "rejected":
            return {"role": "assistant", "content": "The change was rejected."}
        return {
            "role": "assistant",
            "content": "The saved design is available."
            if result.get("action") == "design.get"
            else "The reviewed change was saved.",
        }

    chat_module.groq_completion = fake_groq
password = "Synthetic-browser-agent-123"
if args.mode == "hosted":
    identity = app.state.identity
    owner_id = identity.provision("owner@example.test", password=password)
    if os.environ.get("PHYSIMESH_FAKE_REMOTE") == "1":
        # Test-only fixture: create an explicit synthetic identity link; production has no linking flow yet.
        with app.state.metadata.connection(write=True) as db:
            db.execute(
                "UPDATE users SET issuer=?,subject=? WHERE user_id=?",
                ("https://issuer.example", "synthetic-subject", owner_id),
            )
    identity.provision("viewer@example.test", password=password)
    login = identity.login("owner@example.test", password)
    owner = identity.session(login["token"])
    organization = identity.organization(owner_id, "Disposable agent browser fixture")
    headers = {"Authorization": "Bearer " + login["token"], "X-Organization-ID": organization}
    client_context = (
        nullcontext(TestClient(app)) if os.environ.get("PHYSIMESH_FAKE_REMOTE") == "1" else TestClient(app)
    )
    with client_context as client:
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
