"""Explicit disposable HTTPS fixture with a simulated OIDC provider."""

import json, os, socket, tempfile, time
from pathlib import Path
import jwt, uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.platform.identity import Principal

if os.environ.get("PHYSIMESH_BROWSER_DISPOSABLE") != "1":
    raise RuntimeError("Disposable fixture required")
workspace = Path(__file__).resolve().parents[2]
base = workspace / ".backend"
root = Path(tempfile.mkdtemp(prefix="oidc-ui-", dir=base))
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
origin = "https://localhost:" + str(sock.getsockname()[1])
issuer = "https://issuer.example"
resource = origin + "/mcp/"
settings = Settings(
    root,
    root / "jobs.sqlite",
    "",
    None,
    hosted_mode=True,
    remote_mcp_origin=origin,
    remote_mcp_issuer=issuer,
    remote_mcp_jwks_url=issuer + "/jwks",
    hosted_signin_origin=origin,
    hosted_signin_issuer=issuer,
    hosted_signin_discovery_url=issuer + "/.well-known/openid-configuration",
    hosted_signin_client_id="browser-client",
)
app = create_app(settings)
identity = app.state.identity
uid = identity.provision("owner@example.test", issuer=issuer, subject="synthetic-subject")
org = identity.organization(uid, "Synthetic")
project = app.state.projects.create("Synthetic OIDC project")
identity.claim_project(Principal(uid, "owner@example.test"), org, project["project_id"])
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


def fake_provider(url, form=None):
    if url.endswith("/jwks"):
        return {"keys": [jwk]}
    if url.endswith("/token"):
        nonce = form["code"].removeprefix("synthetic-code-")
        claims = {
            "iss": issuer,
            "sub": "synthetic-subject",
            "aud": "browser-client",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "nonce": nonce,
        }
        return {"id_token": jwt.encode(claims, key, algorithm="RS256", headers={"kid": "fixture"})}
    return metadata


app.state.hosted_signin.provider.http_json = fake_provider


class Keys:
    def get_signing_key_from_jwt(self, token):
        class Selected:
            pass

        item = Selected()
        item.key = key.public_key()
        return item


app.state.remote_http.verifier.keys = Keys()
claims = {
    "iss": issuer,
    "sub": "synthetic-subject",
    "aud": resource,
    "client_id": "synthetic-client",
    "iat": int(time.time()),
    "exp": int(time.time()) + 1200,
}
remote_token = jwt.encode(claims, key, algorithm="RS256", headers={"typ": "at+jwt", "kid": "fixture"})
(base / "oidc-runtime.json").write_text(
    json.dumps(
        {
            "base": origin,
            "pid": os.getpid(),
            "project_id": project["project_id"],
            "remote_token": remote_token,
        }
    )
    + "\n"
)
print("Disposable HTTPS OIDC fixture ready", flush=True)
uvicorn.Server(
    uvicorn.Config(
        app,
        log_level="warning",
        access_log=False,
        ssl_keyfile=str(base / "oidc-cert/key.pem"),
        ssl_certfile=str(base / "oidc-cert/cert.pem"),
    )
).run(sockets=[sock])
