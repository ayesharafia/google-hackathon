"""Bounded Groq tool calling over the existing project action gateway."""

import base64
import hashlib
import hmac
import json
import ipaddress
from threading import Event
import time
import urllib.error
import urllib.request
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from .api import trusted
from .contracts import Call, ID, Strict

router = APIRouter(prefix="/api/drone/agent")
MAX_STATE = 120_000


class ProviderFailure(Exception):
    """A safe, fixed provider failure category, never the provider's response."""

    def __init__(self, category):
        self.category = category


PROVIDER_MESSAGES = {
    "authentication": "Groq authentication failed. Check or replace the API key.",
    "forbidden": "Groq denied access. Check the key's permissions and account.",
    "request": "Groq rejected the request. The model or tool configuration may be incompatible.",
    "limit": "Groq rate or usage limit reached. Check your account limits and try again later.",
    "service": "Groq is temporarily unavailable. Try again later.",
    "connection": "Could not connect to Groq. Check the server's network connection.",
    "response": "Groq returned an invalid response. Try again or choose another model.",
}


class ChatInput(Strict):
    project_id: ID
    key: str = Field(default="", max_length=512, repr=False)
    model: str = Field(default="", max_length=128, pattern=r"^[A-Za-z0-9_./-]*$")
    prompt: str = Field(default="", max_length=6000)
    continuation: str = Field(default="", max_length=300000, repr=False)
    dirty: bool = False
    run_id: str = Field(pattern=r"^[a-f0-9]{32}$")


def groq_completion(key, model, messages, tools, timeout):
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "tools": tools,
            "parallel_tool_calls": False,
            "max_completion_tokens": 2048,
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "User-Agent": "PhysiCore/1.0",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError("Provider response exceeds the limit.")
        return json.loads(raw)["choices"][0]["message"]
    except urllib.error.HTTPError as exc:
        category = {400: "request", 401: "authentication", 403: "forbidden", 422: "request", 429: "limit"}.get(exc.code, "service")
        raise ProviderFailure(category) from None
    except (urllib.error.URLError, OSError):
        raise ProviderFailure("connection") from None
    except (ValueError, KeyError, IndexError, TypeError):
        raise ProviderFailure("response") from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise urllib.error.HTTPError("", 400, "Redirect refused", {}, None)


def _secret(request):
    return request.app.state.chat_signing_key


def seal(request, state):
    raw = json.dumps(state, separators=(",", ":"), ensure_ascii=False).encode()
    if len(raw) > MAX_STATE:
        raise ValueError("Conversation exceeds its size limit; start a new conversation.")
    data = base64.urlsafe_b64encode(raw).decode()
    sig = hmac.new(_secret(request), data.encode(), hashlib.sha256).hexdigest()
    return data + "." + sig


def unseal(request, value):
    try:
        data, sig = value.rsplit(".", 1)
        expected = hmac.new(_secret(request), data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError()
        raw = base64.urlsafe_b64decode(data.encode())
        if len(raw) > MAX_STATE:
            raise ValueError()
        return json.loads(raw)
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        raise ValueError("Conversation expired or was modified; start again.") from None


def secure_origin(request):
    host = request.url.hostname
    try:
        peer_loopback = ipaddress.ip_address(request.client.host).is_loopback
    except (ValueError, AttributeError):
        peer_loopback = False
    return request.url.scheme == "https" or (peer_loopback and host in ("localhost", "127.0.0.1", "::1"))


@router.post("/chat")
def chat(request: Request, body: ChatInput):
    ctx = trusted(request, changing=True)
    if not secure_origin(request):
        raise HTTPException(403, "Use HTTPS or a loopback connection for provider keys.")
    if not body.key:
        from .provider_settings import settings_actor
        key, model = request.app.state.provider_settings.resolve(settings_actor(request, ctx))
        body = body.model_copy(update={"key": key, "model": model})
    run_key = (ctx.actor, body.project_id, body.run_id)
    with request.app.state.chat_run_lock:
        if run_key in request.app.state.chat_runs or len(request.app.state.chat_runs) >= 64:
            raise HTTPException(409, "Chat run is already active or capacity is full.")
        cancelled = Event()
        request.app.state.chat_runs[run_key] = cancelled
    try:
        return run(request, ctx, body, cancelled)
    except ProviderFailure as exc:
        raise HTTPException(502, PROVIDER_MESSAGES.get(exc.category, PROVIDER_MESSAGES["service"])) from None
    except Exception:
        # Provider messages and request bodies can contain secrets; never echo exceptions.
        raise HTTPException(
            400, "Chat could not continue. Check the project, model, key and pending review."
        ) from None
    finally:
        with request.app.state.chat_run_lock:
            request.app.state.chat_runs.pop(run_key, None)


class StopInput(Strict):
    project_id: ID
    run_id: str = Field(pattern=r"^[a-f0-9]{32}$")


@router.post("/chat/stop")
def stop_chat(request: Request, body: StopInput):
    ctx = trusted(request, changing=True)
    request.app.state.agent.policy.authorize(ctx, body.project_id)
    with request.app.state.chat_run_lock:
        event = request.app.state.chat_runs.get((ctx.actor, body.project_id, body.run_id))
        if event:
            event.set()
    return {"status": "stop_requested" if event else "not_running"}


def run(request, ctx, body, cancelled):
    agent = request.app.state.agent
    agent.policy.authorize(ctx, body.project_id)
    agent.app.state.projects.repository.get(body.project_id)
    if body.key in body.prompt:
        raise ValueError("Do not include provider credentials in messages.")
    now = time.time()
    if body.continuation:
        state = unseal(request, body.continuation)
        if (
            state["actor"] != ctx.actor
            or state["project"] != body.project_id
            or state["model"] != body.model
            or state["expires"] < now
        ):
            raise ValueError("Conversation context changed.")
        pending = state.get("pending")
        if not pending:
            if not body.prompt.strip():
                raise ValueError("A prompt is required.")
            state["messages"].append({"role": "user", "content": body.prompt})
        else:
            resume_review(agent, ctx, body.project_id, state, pending)
    else:
        if not body.prompt.strip():
            raise ValueError("A prompt is required.")
        state = {
            "actor": ctx.actor,
            "project": body.project_id,
            "model": body.model,
            "expires": now + 900,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a PhysiCore assistant. Use only available tools and explicit user inputs. Never invent measurements, outcomes or scientific approval. Do not claim capabilities, editable fields, analysis types, or completed actions unless the available tools and their descriptions support them. If a requested capability is unavailable, say so. A tool result is not proof of physical validation. The selected project is "
                    + body.project_id
                    + ".",
                },
                {"role": "user", "content": body.prompt},
            ],
            "provider_calls": 0,
            "tool_calls": 0,
            "pending": None,
        }
    return _execute(request, ctx, body, state, cancelled)


def resume_review(agent, ctx, project_id, state, pending):
    with agent.store.database.connection() as db:
        row = db.execute(
            "SELECT status FROM agent_reviews WHERE review_id=? AND actor=? AND project_id=?",
            (pending["review_id"], ctx.actor, project_id),
        ).fetchone()
        receipt = db.execute(
            "SELECT result_json FROM agent_calls WHERE actor=? AND request_id=?",
            (ctx.actor, pending["request_id"]),
        ).fetchone()
    if row is None or row["status"] not in ("consumed", "rejected"):
        raise ValueError("Review must be completed first.")
    if row["status"] == "consumed" and (not receipt or not receipt["result_json"]):
        raise ValueError("Review result unavailable; inspect action history.")
    result = (
        json.loads(receipt["result_json"])
        if row["status"] == "consumed" and receipt and receipt["result_json"]
        else {"status": "rejected"}
    )
    state["messages"].append(
        {"role": "tool", "tool_call_id": pending["tool_id"], "content": json.dumps(result)}
    )
    state["pending"] = None


def _execute(request, ctx, body, state, cancelled):
    agent = request.app.state.agent
    deadline = time.monotonic() + 60
    actions = []
    while state["provider_calls"] < 8 and time.monotonic() < deadline:
        if cancelled.is_set():
            return {"status": "stopped", "actions": actions}
        catalog = agent.catalog(ctx, body.project_id)
        # projects.list has broader scope than a selected-project conversation.
        specs = {a["tool_name"]: a for a in catalog["actions"] if a["id"] != "projects.list"}
        if body.dirty:
            specs = {name: spec for name, spec in specs.items() if spec["effect"] == "read"}
        tools = [
            {
                "type": "function",
                "function": {
                    "name": s["tool_name"],
                    "description": s["description"],
                    "parameters": s["input_schema"],
                },
            }
            for s in specs.values()
        ]
        if body.key in json.dumps(state["messages"]):
            raise ValueError("Conversation contains a credential.")
        state["provider_calls"] += 1
        message = groq_completion(
            body.key, body.model, state["messages"], tools, min(15, max(1, deadline - time.monotonic()))
        )
        if cancelled.is_set():
            return {"status": "stopped", "actions": actions}
        if body.key in json.dumps(message):
            raise ValueError("Provider response contained a credential.")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise ValueError("Invalid provider response.")
        calls = message.get("tool_calls") or []
        if not calls:
            content = message.get("content")
            if not isinstance(content, str) or len(content) > 12000:
                raise ValueError("Invalid provider text.")
            state["messages"].append({"role": "assistant", "content": content})
            state["provider_calls"] = 0
            state["tool_calls"] = 0
            return {
                "status": "completed",
                "message": content,
                "actions": actions,
                "continuation": seal(request, state),
            }
        if len(calls) != 1 or state["tool_calls"] >= 12:
            raise ValueError("Tool limit exceeded.")
        item = calls[0]
        fn = item["function"]
        name = fn["name"]
        tool_id = item["id"]
        if name not in specs or not isinstance(tool_id, str) or len(tool_id) > 128:
            raise ValueError("Unknown tool.")
        args = json.loads(fn["arguments"])
        if not isinstance(args, dict) or ("project_id" in args and args["project_id"] != body.project_id):
            raise ValueError("Project scope mismatch.")
        if "project_id" in specs[name]["input_schema"].get("properties", {}):
            args["project_id"] = body.project_id
        state["tool_calls"] += 1
        request_id = uuid4().hex
        if cancelled.is_set():
            return {"status": "stopped", "actions": actions}
        result = agent.call(ctx, specs[name]["id"], Call(request_id=request_id, arguments=args))
        if body.key in json.dumps(result):
            raise ValueError("Action result contained a credential.")
        actions.append(result)
        state["messages"].append(message)
        if result["status"] == "awaiting_review":
            state["pending"] = {
                "review_id": result["data"]["review_id"],
                "request_id": request_id,
                "tool_id": tool_id,
            }
            return {
                "status": "awaiting_review",
                "actions": actions,
                "review": result,
                "continuation": seal(request, state),
            }
        state["messages"].append({"role": "tool", "tool_call_id": tool_id, "content": json.dumps(result)})
    raise ValueError("Run limit reached.")
