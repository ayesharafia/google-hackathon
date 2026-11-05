import concurrent.futures

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings


@pytest.fixture
def store(tmp_path):
    from physimesh.platform.hosted_signin import SigninTransactions

    with TestClient(
        create_app(Settings(tmp_path, tmp_path / "jobs.sqlite", "", None, hosted_mode=True))
    ) as c:
        yield SigninTransactions(c.app.state.metadata)


def test_state_is_browser_bound_and_consumed_once(store):
    from physimesh.platform.identity import Denied

    tx = store.create()
    with pytest.raises(Denied):
        store.consume(tx["state"], "wrong-browser")
    row = store.consume(tx["state"], tx["browser"])
    assert row["verifier"] and row["nonce_hash"]
    with pytest.raises(Denied):
        store.consume(tx["state"], tx["browser"])


def test_only_one_concurrent_callback_consumes_state(store):
    from physimesh.platform.identity import Denied

    tx = store.create()

    def attempt(_):
        try:
            store.consume(tx["state"], tx["browser"])
            return "ok"
        except Denied:
            return "refused"

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, range(2))) == ["ok", "refused"]


def test_provider_validates_metadata_nonce_audience_and_signed_identity():
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    from physimesh.platform.hosted_signin import Provider, digest

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk["kid"] = "fixture"
    jwk["alg"] = "RS256"
    jwk["use"] = "sig"
    provider = Provider(
        "https://issuer.example",
        "https://issuer.example/.well-known/openid-configuration",
        "browser-client",
        "https://app.example",
    )
    metadata = {
        "issuer": "https://issuer.example",
        "authorization_endpoint": "https://issuer.example/authorize",
        "token_endpoint": "https://issuer.example/token",
        "jwks_uri": "https://issuer.example/jwks",
        "response_types_supported": ["code"],
        "code_challenge_methods_supported": ["S256"],
    }
    provider.http_json = lambda url, form=None: {"keys": [jwk]} if url.endswith("/jwks") else metadata
    assert provider.metadata()["issuer"] == "https://issuer.example"
    import time

    claims = {
        "iss": "https://issuer.example",
        "sub": "subject",
        "aud": "browser-client",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "nonce": "secret-nonce",
    }
    token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "fixture"})
    assert provider.verify_id_token(token, metadata, digest("secret-nonce"))["sub"] == "subject"
    from physimesh.platform.identity import Denied

    for bad in [
        jwt.encode({**claims, "nonce": "wrong"}, key, algorithm="RS256", headers={"kid": "fixture"}),
        jwt.encode({**claims, "aud": "wrong"}, key, algorithm="RS256", headers={"kid": "fixture"}),
    ]:
        with pytest.raises(Denied):
            provider.verify_id_token(bad, metadata, digest("secret-nonce"))
    provider.http_json = lambda url, form=None: {**metadata, "token_endpoint": "https://evil.example/token"}
    with pytest.raises(Denied):
        provider.metadata()


def test_provider_callback_issues_cookie_and_enforces_origin(tmp_path):
    import time
    from urllib.parse import parse_qs, urlsplit

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    origin = "https://app.example"
    issuer = "https://issuer.example"
    app = create_app(
        Settings(
            tmp_path,
            tmp_path / "jobs.sqlite",
            "",
            None,
            hosted_mode=True,
            hosted_signin_issuer=issuer,
            hosted_signin_discovery_url=issuer + "/.well-known/openid-configuration",
            hosted_signin_client_id="browser-client",
            hosted_signin_origin=origin,
        )
    )
    uid = app.state.identity.provision("person@example.test", issuer=issuer, subject="subject")
    app.state.identity.organization(uid, "Synthetic")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk.update({"kid": "fixture", "alg": "RS256", "use": "sig"})
    metadata = {
        "issuer": issuer,
        "authorization_endpoint": issuer + "/authorize",
        "token_endpoint": issuer + "/token",
        "jwks_uri": issuer + "/jwks",
        "response_types_supported": ["code"],
        "code_challenge_methods_supported": ["S256"],
    }
    token_result = {}

    def fake_http(url, form=None):
        if url.endswith("/jwks"):
            return {"keys": [jwk]}
        if url.endswith("/token"):
            from physimesh.platform.hosted_signin import challenge

            assert (
                form["code"] == "synthetic-code"
                and challenge(form["code_verifier"]) == params["code_challenge"][0]
            )
            return token_result
        return metadata

    app.state.hosted_signin.provider.http_json = fake_http
    with TestClient(app, base_url=origin) as c:
        start = c.get("/api/oidc/start", follow_redirects=False)
        assert start.status_code == 302
        params = parse_qs(urlsplit(start.headers["location"]).query)
        state = params["state"][0]
        nonce = params["nonce"][0]
        claims = {
            "iss": issuer,
            "sub": "subject",
            "aud": "browser-client",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "nonce": nonce,
        }
        token_result["id_token"] = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "fixture"})
        callback = c.get(
            "/api/oidc/callback", params={"state": state, "code": "synthetic-code"}, follow_redirects=False
        )
        assert callback.status_code == 303 and callback.headers["location"] == "/web/workbench.html"
        assert "HttpOnly" in callback.headers["set-cookie"] and "Secure" in callback.headers["set-cookie"]
        assert c.get("/api/drone/platform/me").status_code == 200
        assert (
            c.post("/api/drone/platform/logout", headers={"Origin": "https://evil.example"}).status_code
            == 403
        )
        assert c.post("/api/drone/platform/logout", headers={"Origin": origin}).status_code == 200
        assert c.get("/api/drone/platform/me").status_code == 401
        assert (
            c.get(
                "/api/oidc/callback",
                params={"state": state, "code": "synthetic-code"},
                follow_redirects=False,
            )
            .headers["location"]
            .endswith("signin=failed")
        )
        # Verified email must never link a different provider subject.
        start = c.get("/api/oidc/start", follow_redirects=False)
        params = parse_qs(urlsplit(start.headers["location"]).query)
        unknown = {
            **claims,
            "sub": "different-subject",
            "email": "person@example.test",
            "nonce": params["nonce"][0],
        }
        token_result["id_token"] = jwt.encode(unknown, key, algorithm="RS256", headers={"kid": "fixture"})
        refused = c.get(
            "/api/oidc/callback",
            params={"state": params["state"][0], "code": "synthetic-code"},
            follow_redirects=False,
        )
        assert refused.headers["location"].endswith("signin=failed")
        assert c.get("/api/drone/platform/me").status_code == 401
        start = c.get("/api/oidc/start", follow_redirects=False)
        params = parse_qs(urlsplit(start.headers["location"]).query)
        bad = c.get(
            "/api/oidc/callback",
            params={"state": "wrong-state-value-0123456789", "code": "synthetic-code"},
            follow_redirects=False,
        )
        assert bad.headers["location"].endswith("signin=failed")
        assert c.get("/api/drone/platform/me").status_code == 401
