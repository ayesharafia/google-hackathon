"""Exercise the approved saved-design chat flow using a scripted provider."""

import json
from uuid import uuid4

AUTH = {"Authorization": "Bearer agent-test-token", "Origin": "http://testserver"}


def test_explain_edit_review_freeze_run_and_read_real_retained_study(workspace, monkeypatch):
    from physimesh.agent import chat

    client, project = workspace
    pid = project["project_id"]
    observed = []
    monkeypatch.setattr(chat, "secure_origin", lambda request: True)

    def call(name, args):
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": uuid4().hex,
                    "type": "function",
                    "function": {
                        "name": "physicore_" + name.replace(".", "_"),
                        "arguments": json.dumps(args),
                    },
                }
            ],
        }

    def provider(key, model, messages, tools, timeout):
        last = messages[-1]
        if last["role"] == "user":
            if "explain" in last["content"]:
                return call("design.schema", {})
            return call("design.get", {"project_id": pid})
        result = json.loads(last["content"])
        action = result["action"]
        observed.append(result)
        if action == "design.schema":
            assert result["data"]["units"]["duration"] == ["s", "min"]
            return {"role": "assistant", "content": "Duration is an input stated in seconds or minutes."}
        if action == "design.get":
            return call(
                "design.propose",
                {
                    "project_id": pid,
                    "expected_version": result["data"]["draft_version"],
                    "edits": [{"field": "mission.duration_s", "value": 8, "unit": "min"}],
                },
            )
        if action == "design.propose":
            return call("proposal.apply", {"project_id": pid, "proposal_id": result["data"]["proposal_id"]})
        if action == "proposal.apply":
            return call(
                "design.freeze", {"project_id": pid, "expected_version": result["data"]["draft_version"]}
            )
        if action == "design.freeze":
            return call(
                "study.run", {"project_id": pid, "revision_sha256": result["data"]["revision_sha256"]}
            )
        if action == "study.run":
            return call("study.summary", {"project_id": pid, "study_sha256": result["data"]["study_sha256"]})
        if action == "study.summary":
            return {
                "role": "assistant",
                "content": "Study evidence is recorded; engineering acceptance is separate.",
            }
        raise AssertionError(action)

    monkeypatch.setattr(chat, "groq_completion", provider)

    def post(prompt="", continuation=""):
        result = client.post(
            "/api/drone/agent/chat",
            headers=AUTH,
            json={
                "project_id": pid,
                "key": "synthetic-key",
                "model": "fixture",
                "prompt": prompt,
                "continuation": continuation,
                "run_id": uuid4().hex,
            },
        )
        assert result.status_code == 200, result.text
        return result.json()

    explanation = post("explain mission duration")
    assert explanation["status"] == "completed" and "seconds" in explanation["message"]
    result = post("change duration to 8 minutes and run the study", explanation["continuation"])
    for expected in ["proposal.apply", "design.freeze", "study.run"]:
        assert result["status"] == "awaiting_review" and result["review"]["action"] == expected
        reviewed = client.post(
            "/api/drone/agent/reviews/" + result["review"]["data"]["review_id"] + "/confirm",
            headers=AUTH,
            json={"execute": True},
        )
        assert reviewed.status_code == 200, reviewed.text
        result = post(continuation=result["continuation"])
    assert result["status"] == "completed"
    assert [r["action"] for r in observed] == [
        "design.schema",
        "design.get",
        "design.propose",
        "proposal.apply",
        "design.freeze",
        "study.run",
        "study.summary",
    ]
    actual = client.get("/api/drone/projects/" + pid, headers=AUTH).json()
    assert (
        actual["draft_version"] == 2 and json.loads(actual["snapshot_json"])["mission"]["duration_s"] == 480
    )
    assert any(
        s["study_sha256"] == next(r for r in observed if r["action"] == "study.run")["data"]["study_sha256"]
        for s in actual["studies"]
    )
    assert "engineering acceptance is separate" in result["message"]
