"""Browser-bound one-use authorization transactions for hosted sign-in."""

import base64
import hashlib
import secrets
import time
from .identity import Denied


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def challenge(value):
    return base64.urlsafe_b64encode(hashlib.sha256(value.encode()).digest()).decode().rstrip("=")


class SigninTransactions:
    def __init__(self, database, clock=time.time):
        self.database, self.clock = database, clock
        with database.connection(write=True) as db:
            if database.postgres:
                db.execute("SELECT pg_advisory_xact_lock(17010612)")
            db.execute("CREATE TABLE IF NOT EXISTS signin_schema(version INTEGER PRIMARY KEY)")
            versions = [r[0] for r in db.execute("SELECT version FROM signin_schema").fetchall()]
            if versions not in ([], [1]):
                raise ValueError("unsupported sign-in schema")
            if not versions:
                db.execute("""CREATE TABLE signin_transactions(state_hash TEXT PRIMARY KEY,browser_hash TEXT NOT NULL,
                    nonce_hash TEXT NOT NULL,verifier TEXT NOT NULL,expires DOUBLE PRECISION NOT NULL)""")
                db.execute("INSERT INTO signin_schema VALUES(1)")

    def create(self):
        state = secrets.token_urlsafe(32)
        browser = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        with self.database.connection(write=True) as db:
            if self.database.postgres:
                db.execute("SELECT pg_advisory_xact_lock(17010612)")
            db.execute("DELETE FROM signin_transactions WHERE expires<=?", (self.clock(),))
            if db.execute("SELECT COUNT(*) FROM signin_transactions").fetchone()[0] >= 10000:
                raise Denied("Sign-in capacity is full.")
            db.execute(
                "INSERT INTO signin_transactions VALUES(?,?,?,?,?)",
                (digest(state), digest(browser), digest(nonce), verifier, self.clock() + 300),
            )
        return {"state": state, "browser": browser, "nonce": nonce, "challenge": challenge(verifier)}

    def consume(self, state, browser):
        if (
            not isinstance(state, str)
            or not isinstance(browser, str)
            or not 20 <= len(state) <= 256
            or not 20 <= len(browser) <= 256
        ):
            raise Denied("Sign-in transaction is invalid.")
        with self.database.connection(write=True) as db:
            lock = " FOR UPDATE" if self.database.postgres else ""
            row = db.execute(
                "SELECT nonce_hash,verifier,expires FROM signin_transactions WHERE state_hash=? AND browser_hash=?"
                + lock,
                (digest(state), digest(browser)),
            ).fetchone()
            if not row or row["expires"] <= self.clock():
                raise Denied("Sign-in transaction is invalid or expired.")
            db.execute("DELETE FROM signin_transactions WHERE state_hash=?", (digest(state),))
            return dict(row)


class Provider:
    """Pinned OIDC discovery and ID-token verification, with bounded HTTPS calls."""

    def __init__(self, issuer, discovery, client_id, origin):
        self.issuer, self.discovery, self.client_id, self.origin = (
            issuer,
            discovery,
            client_id,
            origin.rstrip("/"),
        )
        self.callback = self.origin + "/api/oidc/callback"

    @staticmethod
    def http_json(url, form=None):
        import json
        from urllib.parse import urlencode
        from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise ValueError("Redirect refused")

        raw = urlencode(form).encode() if form is not None else None
        req = Request(
            url,
            data=raw,
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
            if raw is not None
            else {"Accept": "application/json"},
        )
        try:
            with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=8) as response:
                data = response.read(262145)
            if len(data) > 262144:
                raise ValueError()
            value = json.loads(data)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except Exception:
            raise Denied("Identity provider is unavailable or returned invalid data.") from None

    def metadata(self):
        from urllib.parse import urlsplit
        from physimesh.agent.remote_auth import https_url

        data = self.http_json(self.discovery)
        if (
            data.get("issuer") != self.issuer
            or "code" not in data.get("response_types_supported", [])
            or "S256" not in data.get("code_challenge_methods_supported", [])
        ):
            raise Denied("Identity provider is incompatible.")
        expected = urlsplit(self.issuer)
        for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            value = data.get(field)
            if not isinstance(value, str) or not https_url(value):
                raise Denied("Invalid provider endpoint.")
            actual = urlsplit(value)
            if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc) or actual.query:
                raise Denied("Invalid provider endpoint.")
        return data

    def authorize_url(self, metadata, transaction):
        from urllib.parse import urlencode

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.callback,
            "scope": "openid",
            "state": transaction["state"],
            "nonce": transaction["nonce"],
            "code_challenge": transaction["challenge"],
            "code_challenge_method": "S256",
        }
        return metadata["authorization_endpoint"] + "?" + urlencode(params)

    def verify_id_token(self, token, metadata, nonce_hash):
        import hmac
        import jwt

        try:
            if not isinstance(token, str) or not 1 <= len(token) <= 16384:
                raise ValueError()
            header = jwt.get_unverified_header(token)
            if (
                header.get("alg") not in ("RS256", "ES256")
                or not isinstance(header.get("kid"), str)
                or header.get("typ") in ("at+jwt", "application/at+jwt")
            ):
                raise ValueError()
            keys = self.http_json(metadata["jwks_uri"]).get("keys")
            if not isinstance(keys, list) or len(keys) > 100:
                raise ValueError()
            matches = [
                k
                for k in keys
                if isinstance(k, dict)
                and k.get("kid") == header["kid"]
                and k.get("use", "sig") == "sig"
                and k.get("alg", header["alg"]) == header["alg"]
            ]
            if len(matches) != 1:
                raise ValueError()
            key = jwt.PyJWK.from_dict(matches[0], algorithm=header["alg"]).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256", "ES256"],
                issuer=self.issuer,
                audience=self.client_id,
                options={"require": ["iss", "sub", "aud", "iat", "exp", "nonce"]},
            )
            audience = claims["aud"]
            nonce = claims["nonce"]
            subject = claims["sub"]
            if isinstance(audience, list) and (len(audience) > 1 and claims.get("azp") != self.client_id):
                raise ValueError()
            if "azp" in claims and claims["azp"] != self.client_id:
                raise ValueError()
            if (
                not isinstance(nonce, str)
                or not hmac.compare_digest(digest(nonce), nonce_hash)
                or not isinstance(subject, str)
                or not subject
                or len(subject) > 512
            ):
                raise ValueError()
            return claims
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            raise Denied("Provider identity could not be verified.") from None

    def exchange(self, metadata, code, verifier, nonce_hash):
        result = self.http_json(
            metadata["token_endpoint"],
            {
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "redirect_uri": self.callback,
                "code": code,
                "code_verifier": verifier,
            },
        )
        return self.verify_id_token(result.get("id_token"), metadata, nonce_hash)


HOSTED_COOKIE = "physicore_hosted_session"
TRANSACTION_COOKIE = "physicore_oidc_transaction"


class HostedSignin:
    def __init__(self, app):
        self.app = app
        settings = app.state.settings
        self.provider = Provider(
            settings.hosted_signin_issuer,
            settings.hosted_signin_discovery_url,
            settings.hosted_signin_client_id,
            settings.hosted_signin_origin,
        )
        self.transactions = SigninTransactions(app.state.metadata)
        with app.state.metadata.connection(write=True) as db:
            db.execute("CREATE TABLE IF NOT EXISTS hosted_browser_sessions(token_hash TEXT PRIMARY KEY)")

    def valid_origin(self, request):
        from urllib.parse import urlsplit

        expected = urlsplit(self.provider.origin)
        headers = request.scope.get("headers", [])
        return (
            request.url.scheme == "https"
            and request.headers.get("host", "").lower() == expected.netloc.lower()
            and sum(1 for name, _ in headers if name.lower() == b"host") == 1
        )

    def issue(self, claims):
        from .identity import token_hash

        identity = self.app.state.identity
        principal = identity.oidc(claims)
        token = secrets.token_urlsafe(32)
        now = identity.clock()
        with identity.database.connection(write=True) as db:
            self.app.state.agent.store.lock(db)
            row = db.execute(
                "SELECT active FROM users WHERE user_id=?"
                + (" FOR UPDATE" if identity.database.postgres else ""),
                (principal.user_id,),
            ).fetchone()
            if not row or not row["active"]:
                raise Denied("Account unavailable.")
            db.execute(
                "DELETE FROM hosted_browser_sessions WHERE token_hash IN (SELECT token_hash FROM sessions WHERE user_id=? AND expires_at<=?)",
                (principal.user_id, now),
            )
            db.execute("DELETE FROM sessions WHERE user_id=? AND expires_at<=?", (principal.user_id, now))
            if (
                db.execute(
                    "SELECT COUNT(*) FROM sessions WHERE user_id=? AND revoked=0 AND expires_at>?",
                    (principal.user_id, now),
                ).fetchone()[0]
                >= 20
            ):
                raise Denied("Session limit reached.")
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,0)", (token_hash(token), principal.user_id, now + 43200)
            )
            db.execute("INSERT INTO hosted_browser_sessions VALUES(?)", (token_hash(token),))
        return token

    def principal(self, token):
        from .identity import token_hash, InvalidSession

        if not token or len(token) > 256:
            raise InvalidSession("Browser session unavailable.")
        with self.app.state.metadata.connection() as db:
            marker = db.execute(
                "SELECT 1 FROM hosted_browser_sessions WHERE token_hash=?", (token_hash(token),)
            ).fetchone()
        if not marker:
            raise InvalidSession("Browser session unavailable.")
        return self.app.state.identity.session(token)


class RedactOIDCQuery:
    """Remove authorization codes from ASGI access-log scope before responding."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == "/api/oidc/callback":
            scope.setdefault("state", {})["oidc_query"] = scope.get("query_string", b"")
            scope["query_string"] = b""
        await self.app(scope, receive, send)
