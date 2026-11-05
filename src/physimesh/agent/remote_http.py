"""Opt-in HTTP transport; every MCP message has its own authenticated scope."""

import asyncio
from urllib.parse import parse_qs, urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse

from physimesh.platform.identity import Denied, Principal, token_hash

from . import api
from .contracts import Call
from .mcp import BridgeError, create_server
from .remote_auth import AccessVerifier


class ScopedBridge:
    def __init__(self, request):
        if not request or not getattr(request.state, "agent_context", None):
            raise BridgeError("An authenticated remote request is required.")
        self.request = request

    async def fetch(self, path, body=None):
        def invoke():
            parsed = urlsplit(path)
            if parsed.path == "/api/drone/agent/catalog":
                return api.catalog(self.request)
            if parsed.path == "/api/drone/agent/resources":
                return api.resources(self.request)
            if parsed.path == "/api/drone/agent/resource":
                params = parse_qs(parsed.query, strict_parsing=True)
                if set(params) != {"uri"} or len(params["uri"]) != 1:
                    raise ValueError("Invalid resource request.")
                return api.resource(self.request, params["uri"][0])
            prefix = "/api/drone/agent/actions/"
            if parsed.path.startswith(prefix) and not parsed.query:
                return api.call(self.request, parsed.path[len(prefix) :], Call.model_validate(body))
            raise ValueError("Unsupported remote action.")

        try:
            return await run_in_threadpool(invoke)
        except Exception:  # noqa: BLE001 - Sanitize action failures into the fixed BridgeError.
            raise BridgeError(
                "Action denied or unavailable; inspect project permissions and state."
            ) from None


class RemoteHTTP:
    def __init__(self, app):
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from mcp.server.transport_security import TransportSecuritySettings

        self.app = app
        settings = app.state.settings
        self.origin = settings.remote_mcp_origin.rstrip("/")
        self.resource = self.origin + "/mcp/"
        self.expected_host = urlsplit(self.origin).netloc.lower()
        self.verifier = AccessVerifier(
            settings.remote_mcp_issuer, self.resource, settings.remote_mcp_jwks_url
        )
        self.limit = asyncio.Semaphore(32)
        server = create_server(lambda context: ScopedBridge(context.request))
        self.manager = StreamableHTTPSessionManager(
            server,
            stateless=True,
            json_response=True,
            security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
            max_request_body_size=262144,
        )

    def remote_session(self, token, claims):
        """Store remote-only sessions atomically; they are never browser credentials."""
        identity = self.app.state.identity
        principal = identity.oidc(claims)
        digest = token_hash(token)
        now = self.app.state.agent.store.clock()
        with self.app.state.metadata.connection(write=True) as db:
            self.app.state.agent.store.lock(db)
            user = db.execute("SELECT active FROM users WHERE user_id=?", (principal.user_id,)).fetchone()
            if not user or not user["active"]:
                raise Denied("Account inactive.")
            session = db.execute("SELECT * FROM sessions WHERE token_hash=?", (digest,)).fetchone()
            marker = db.execute(
                "SELECT 1 FROM remote_oauth_sessions WHERE token_hash=?", (digest,)
            ).fetchone()
            if session:
                if (
                    not marker
                    or session["revoked"]
                    or session["expires_at"] <= now
                    or session["user_id"] != principal.user_id
                ):
                    raise Denied("Session cannot be used for remote MCP.")
            else:
                db.execute(
                    "DELETE FROM remote_oauth_sessions WHERE token_hash IN (SELECT token_hash FROM sessions WHERE user_id=? AND expires_at<=?)",
                    (principal.user_id, now),
                )
                db.execute("DELETE FROM sessions WHERE user_id=? AND expires_at<=?", (principal.user_id, now))
                if (
                    db.execute(
                        "SELECT COUNT(*) FROM sessions WHERE user_id=?", (principal.user_id,)
                    ).fetchone()[0]
                    >= 200
                ):
                    raise Denied("Session history limit reached.")
                if (
                    db.execute(
                        "SELECT COUNT(*) FROM sessions WHERE user_id=? AND revoked=0 AND expires_at>?",
                        (principal.user_id, now),
                    ).fetchone()[0]
                    >= 20
                ):
                    raise Denied("Session limit reached.")
                expiry = min(float(claims["exp"]), now + 43200)
                if expiry <= now:
                    raise Denied("Session expired.")
                db.execute("INSERT INTO sessions VALUES(?,?,?,0)", (digest, principal.user_id, expiry))
                db.execute("INSERT INTO remote_oauth_sessions VALUES(?)", (digest,))
        return Principal(principal.user_id, principal.email, digest)

    def valid_host(self, request):
        headers = request.scope.get("headers", [])
        if (
            sum(1 for name, _ in headers if name.lower() == b"host") != 1
            or sum(1 for name, _ in headers if name.lower() == b"origin") > 1
        ):
            return False
        return (
            request.url.scheme == "https"
            and request.headers.get("host", "").lower() == self.expected_host
            and request.headers.get("origin", self.origin) == self.origin
            and not request.url.query
        )

    def metadata(self, request):
        if not self.valid_host(request):
            return JSONResponse({"detail": "Invalid endpoint origin."}, status_code=400)
        return JSONResponse(
            {
                "resource": self.resource,
                "authorization_servers": [self.verifier.issuer],
                "bearer_methods_supported": ["header"],
            },
            headers={"Cache-Control": "no-store"},
        )

    async def __call__(self, scope, receive, send):
        request = Request(scope, receive)

        def refuse(status, detail, headers=None):
            return JSONResponse({"detail": detail}, status_code=status, headers=headers)

        if not self.valid_host(request):
            await refuse(400, "Invalid endpoint origin.")(scope, receive, send)
            return
        from ..platform.hosted_signin import HOSTED_COOKIE
        if HOSTED_COOKIE in request.cookies:
            await refuse(403, 'Browser sessions are not remote MCP credentials.')(scope, receive, send)
            return
        headers = scope.get("headers", [])
        authorization = [v for k, v in headers if k.lower() == b"authorization"]
        challenge = {
            "WWW-Authenticate": f'Bearer resource_metadata="{self.origin}/.well-known/oauth-protected-resource/mcp/"',
            "Cache-Control": "no-store",
        }
        if len(authorization) != 1:
            await refuse(401, "Remote authorization required.", challenge)(scope, receive, send)
            return
        try:
            value = authorization[0].decode("ascii")
            if not value.startswith("Bearer "):
                raise ValueError()
            token = value[7:]

            def authenticate():
                claims = self.verifier.verify(token)
                identity = self.app.state.identity.oidc(claims)
                self.app.state.agent.remote_consents.find(identity.user_id, claims["client_id"])
                principal = self.remote_session(token, claims)
                binding = self.app.state.agent.remote_consents.bind(principal, claims["client_id"])
                return self.app.state.agent.policy.grant_context(grant_id=binding["grant_id"])

            ctx = await run_in_threadpool(authenticate)
        except Exception:  # noqa: BLE001 - Fail closed with the existing generic authorization response.
            await refuse(401, "Remote authorization required.", challenge)(scope, receive, send)
            return
        scope.setdefault("state", {})["agent_context"] = ctx

        async def no_store(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [(b"cache-control", b"no-store")]
            await send(message)

        async with self.limit:
            await self.manager.handle_request(scope, receive, no_store)
