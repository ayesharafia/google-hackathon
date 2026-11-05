"""Agent reads must stay inside the selected project even in a shared library."""
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from tests.agent.test_foundation import AUTH, ROOT, mint
from tests.agent.test_mcp import api_server  # noqa: F401
from tests.agent.test_remote_consent import hosted  # noqa: F401
from tests.projects.test_source_library import RAW, SPEC


def request(client, token, action, arguments):
    return client.post(ROOT + "/actions/" + action,
                       headers={"Authorization": "Bearer " + token},
                       json={"request_id": uuid4().hex, "arguments": arguments})


def test_project_scoped_library_list_detail_and_integrity(workspace):
    client, project = workspace
    pid = project["project_id"]
    other = client.post("/api/drone/projects", headers=AUTH, json={"title": "Other"}).json()["project_id"]
    def save(project_id, name):
        result = client.post(f"/api/drone/projects/{project_id}/source-library/save", headers=AUTH,
                             data={"spec": json.dumps(SPEC)}, files={"file": (name, RAW)})
        assert result.status_code == 201, result.text
        return result.json()
    own, foreign = save(pid, "own.csv"), save(other, "other.csv")
    token = mint(client, pid, ["read"])["token"]
    response = request(client, token, "sources.list", {"project_id": pid})
    assert response.status_code == 200, response.text
    entries = response.json()["data"]["entries"]
    assert [e["entry_id"] for e in entries] == [own["entry"]["entry_id"]]
    detail = request(client, token, "sources.inspect", {"project_id": pid, "entry_id": own["entry"]["entry_id"]})
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["source_sha256"] == own["source_sha256"]
    assert detail.json()["data"]["test_conditions"]["density_kg_m3"] == 1.225
    assert request(client, token, "sources.inspect", {"project_id": pid, "entry_id": foreign["entry"]["entry_id"]}).status_code != 200
    second = client.post(f"/api/drone/projects/{pid}/source-library/save", headers=AUTH,
                         data={"spec": json.dumps(SPEC)}, files={"file": ("second.csv", RAW + b"\r\n")})
    assert second.status_code == 201, second.text
    first_page = request(client, token, "sources.list", {"project_id": pid, "limit": 1}).json()["data"]
    next_page = request(client, token, "sources.list", {"project_id": pid, "limit": 1, "after": first_page["next_cursor"]}).json()["data"]
    assert len(first_page["entries"]) == len(next_page["entries"]) == 1
    assert first_page["entries"][0]["entry_id"] != next_page["entries"][0]["entry_id"]
    client.app.state.artifact_backend._obj(own["manifest"]["file_sha256"]).write_bytes(b"corrupt")
    assert request(client, token, "sources.inspect", {"project_id": pid, "entry_id": own["entry"]["entry_id"]}).status_code != 200


def test_real_mcp_client_discovers_and_calls_source_actions(api_server):  # noqa: F811
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters
    client, project, base = api_server
    pid = project["project_id"]
    saved = client.post(f"/api/drone/projects/{pid}/source-library/save", headers=AUTH,
                        data={"spec": json.dumps(SPEC)}, files={"file": ("source.csv", RAW)}).json()
    token = mint(client, pid, ["read"])["token"]
    params = StdioServerParameters(command=sys.executable, args=["-m", "physimesh.agent.mcp"],
        cwd=Path(__file__).parents[2], env={"PYTHONPATH": str(Path(__file__).parents[2] / "src"),
        "PHYSICORE_API_URL": base, "PHYSICORE_AGENT_TOKEN": token})

    async def exercise():
        async with Client(params, mode="legacy", read_timeout_seconds=30) as mcp:
            names = [tool.name for tool in (await mcp.list_tools()).tools]
            assert "physicore_sources_list" in names and "physicore_sources_inspect" in names
            result = await mcp.call_tool("physicore_sources_inspect", {"project_id": pid, "entry_id": saved["entry"]["entry_id"]})
            assert result.model_dump(by_alias=True)["structuredContent"]["data"]["source_sha256"] == saved["source_sha256"]
    asyncio.run(exercise())


def test_chat_can_use_source_inspection(workspace, monkeypatch):
    from physimesh.agent import chat
    client, project = workspace
    pid = project["project_id"]
    entry = client.post(f"/api/drone/projects/{pid}/source-library/save", headers=AUTH,
                        data={"spec": json.dumps(SPEC)}, files={"file": ("source.csv", RAW)}).json()["entry"]["entry_id"]
    monkeypatch.setattr(chat, "secure_origin", lambda request: True)
    def provider(key, model, messages, tools, timeout):
        assert any(tool["function"]["name"] == "physicore_sources_inspect" for tool in tools)
        if messages[-1]["role"] == "user":
            return {"role": "assistant", "tool_calls": [{"id": "read", "type": "function", "function": {"name": "physicore_sources_inspect", "arguments": json.dumps({"project_id": pid, "entry_id": entry})}}]}
        assert json.loads(messages[-1]["content"])["data"]["test_conditions"]["density_kg_m3"] == 1.225
        return {"role": "assistant", "content": "Source inspected."}
    monkeypatch.setattr(chat, "groq_completion", provider)
    response = client.post(ROOT + "/chat", headers=AUTH, json={"project_id": pid, "key": "synthetic-key", "model": "test", "prompt": "Inspect this source", "run_id": "f" * 32})
    assert response.status_code == 200, response.text
    assert response.json()["actions"][0]["action"] == "sources.inspect"


def test_hosted_project_viewer_can_read_but_not_escape_scope(hosted):  # noqa: F811
    from physimesh.projects.tabular import ImportSelection
    client, project, owner, viewer = hosted
    pid = project["project_id"]
    saved = client.app.state.source_library.save(pid, RAW, "source.csv", ImportSelection.model_validate(SPEC), owner)
    token = client.app.state.identity.login(viewer.email, "Synthetic-password-456")["token"]
    headers = {"Authorization": "Bearer " + token, "Origin": "http://testserver"}
    response = client.post(ROOT + "/actions/sources.inspect", headers=headers,
                           json={"request_id": uuid4().hex, "arguments": {"project_id": pid, "entry_id": saved["entry"]["entry_id"]}})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["entry"]["project_id"] == pid
    assert request(client, token, "sources.list", {"project_id": "project_" + "a" * 32}).status_code != 200
