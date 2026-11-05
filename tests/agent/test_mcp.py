import asyncio
import hashlib
import json
import socket
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest
import uvicorn

from physimesh.agent.mcp import Bridge, BridgeError, configured_bridge
from tests.agent.test_foundation import AUTH, ROOT, mint


@pytest.fixture
def api_server(workspace):
    c, p = workspace
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    base = "http://127.0.0.1:" + str(sock.getsockname()[1])
    server = uvicorn.Server(uvicorn.Config(c.app, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.01)
    assert server.started
    try:
        yield c, p, base
    finally:
        server.should_exit = True
        thread.join(5)
        sock.close()


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_real_stdio_sdk_design_to_study_workflow(api_server, mode):
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters

    c, p, base = api_server
    pid = p["project_id"]
    grant = mint(c, pid)
    frozen = c.post(
        "/api/drone/projects/" + pid + "/revisions", headers=AUTH, json={"expected_version": 1}
    ).json()
    first = c.post(
        "/api/drone/projects/" + pid + "/studies",
        headers=AUTH,
        json={"revision_sha256": frozen["revision_sha256"]},
    ).json()
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "physimesh.agent.mcp"],
        cwd=Path(__file__).parents[2],
        env={
            "PYTHONPATH": str(Path(__file__).parents[2] / "src"),
            "PHYSICORE_API_URL": base,
            "PHYSICORE_AGENT_TOKEN": grant["token"],
        },
    )

    def payload(result):
        value = result.model_dump(by_alias=True)
        assert not value.get("isError"), value
        return value["structuredContent"]

    async def exercise():
        async with Client(params, mode=mode, read_timeout_seconds=30) as client:
            listed = await client.list_tools()
            names = [t.name for t in listed.tools]
            assert "physicore_design_propose" in names
            assert all("confirm" not in n and "development" not in n for n in names)
            resource = await client.read_resource("physicore://projects/" + pid + "/draft")
            assert json.loads(resource.contents[0].text)["data"]["project_id"] == pid
            prompts = await client.list_prompts()
            assert prompts.prompts[0].name == "review_project_v1"
            prompt = await client.get_prompt("review_project_v1", arguments={"project_id": pid})
            assert pid in prompt.messages[0].content.text
            before = payload(await client.call_tool("physicore_design_inspect", {"project_id": pid}))
            assert before["data"] == c.get("/api/drone/projects/" + pid + "/inspection", headers=AUTH).json()
            proposed = payload(
                await client.call_tool(
                    "physicore_design_propose",
                    {
                        "project_id": pid,
                        "expected_version": 1,
                        "edits": [{"field": "mission.duration_s", "value": 8.0, "unit": "min"}],
                    },
                )
            )["data"]

            async def mutation(tool, args):
                args = {**args, "request_id": uuid4().hex}
                pending = payload(await client.call_tool(tool, args))
                assert pending["status"] == "awaiting_review"
                response = c.post(
                    ROOT + "/reviews/" + pending["data"]["review_id"] + "/confirm",
                    headers=AUTH,
                    json={"execute": True},
                )
                assert response.status_code == 200, response.text
                result = payload(await client.call_tool(tool, args))
                assert result == response.json()
                return result["data"]

            await mutation(
                "physicore_proposal_apply", {"project_id": pid, "proposal_id": proposed["proposal_id"]}
            )
            revision = await mutation("physicore_design_freeze", {"project_id": pid, "expected_version": 2})
            second = await mutation(
                "physicore_study_run", {"project_id": pid, "revision_sha256": revision["revision_sha256"]}
            )
            study_args = {"project_id": pid, "study_sha256": second["study_sha256"]}
            summary = payload(await client.call_tool("physicore_study_summary", study_args))
            assert (
                summary["data"]
                == c.get(
                    "/api/drone/projects/" + pid + "/studies/" + second["study_sha256"] + "/summary",
                    headers=AUTH,
                ).json()
            )
            compared = payload(
                await client.call_tool(
                    "physicore_study_compare",
                    {"project_id": pid, "before": first["study_sha256"], "after": second["study_sha256"]},
                )
            )
            assert compared["status"] == "completed"
            exported = payload(await client.call_tool("physicore_study_export", study_args))["data"]
            exact = await client.read_resource(exported["resource_uri"])
            raw = json.loads(exact.contents[0].text)["exact_utf8_json"].encode()
            assert hashlib.sha256(raw).hexdigest() == exported["sha256"]
            assert json.loads(raw) == second
            await mutation(
                "physicore_proposal_undo", {"project_id": pid, "proposal_id": proposed["proposal_id"]}
            )
            assert c.get("/api/drone/projects/" + pid, headers=AUTH).json()["draft_version"] == 3
            assert client.protocol_version == ("2025-11-25" if mode == "legacy" else "2026-07-28")

    asyncio.run(exercise())


def test_bridge_origin_secret_file_and_redirect_guards(tmp_path):
    for url in [
        "http://example.com",
        "https://user:secret@example.com",
        "file:///tmp/data",
        "https://example.com/path",
        "https://example.com?key=secret",
    ]:
        with pytest.raises(BridgeError):
            Bridge(url, "pca_" + "x" * 43)
    with pytest.raises(BridgeError):
        Bridge("http://127.0.0.1:8000", "workspace-secret")
    secret = tmp_path / "credential"
    secret.write_text("pca_" + "x" * 43)
    secret.chmod(0o644)
    env = {"PHYSICORE_API_URL": "http://127.0.0.1:8000", "PHYSICORE_AGENT_TOKEN_FILE": str(secret)}
    with pytest.raises(BridgeError):
        configured_bridge(env)
    secret.chmod(0o600)
    assert configured_bridge(env).token.startswith("pca_")
    from physimesh.agent.mcp import NoRedirect

    with pytest.raises(BridgeError):
        NoRedirect().redirect_request(None, None, 302, "", {}, "https://foreign.example")


def test_independent_mcp_clients_keep_their_project_scopes(api_server):
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters

    c, p, base = api_server
    other = c.post("/api/drone/projects", headers=AUTH, json={"title": "Second MCP scope"}).json()

    def parameters(project):
        g = mint(c, project["project_id"], ["read"])
        return StdioServerParameters(
            command=sys.executable,
            args=["-m", "physimesh.agent.mcp"],
            cwd=Path(__file__).parents[2],
            env={
                "PYTHONPATH": str(Path(__file__).parents[2] / "src"),
                "PHYSICORE_API_URL": base,
                "PHYSICORE_AGENT_TOKEN": g["token"],
            },
        )

    first, second = parameters(p), parameters(other)

    async def exercise():
        async with Client(first) as a, Client(second) as b:
            results = await asyncio.gather(
                a.call_tool("physicore_design_get", {"project_id": p["project_id"]}),
                b.call_tool("physicore_design_get", {"project_id": other["project_id"]}),
            )
            for result, project in zip(results, [p, other]):
                assert (
                    result.model_dump(by_alias=True)["structuredContent"]["data"]["project_id"]
                    == project["project_id"]
                )
            refused = await a.call_tool("physicore_design_get", {"project_id": other["project_id"]})
            assert refused.model_dump(by_alias=True)["isError"] is True

    asyncio.run(exercise())
