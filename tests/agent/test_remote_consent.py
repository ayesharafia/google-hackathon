import time

import pytest
from fastapi.testclient import TestClient

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.platform.identity import Denied


@pytest.fixture
def hosted(tmp_path):
    with TestClient(
        create_app(Settings(tmp_path, tmp_path / "jobs.sqlite", "", None, hosted_mode=True))
    ) as client:
        identity = client.app.state.identity
        uid = identity.provision("owner@example.test", password="Synthetic-password-123")
        identity.provision("viewer@example.test", password="Synthetic-password-456")
        login = identity.login("owner@example.test", "Synthetic-password-123")
        owner = identity.session(login["token"])
        org = identity.organization(uid, "Fixture")
        headers = {
            "Authorization": "Bearer " + login["token"],
            "Origin": "http://testserver",
            "X-Organization-ID": org,
        }
        project = client.post("/api/drone/projects/examples/hover", headers=headers).json()
        viewer = identity.session(identity.login("viewer@example.test", "Synthetic-password-456")["token"])
        identity.accept(
            viewer, identity.invite(owner, project["project_id"], viewer.email, "viewer")["invitation_token"]
        )
        yield client, project, owner, viewer


def test_consent_binds_user_client_project_and_revokes(hosted):
    from physimesh.agent.remote_consent import RemoteConsents

    client, project, owner, _ = hosted
    consents = RemoteConsents(client.app.state.agent)
    value = consents.create(owner, project["project_id"], "sample-client", ["read", "propose"], 3600)
    result = consents.find(owner.user_id, "sample-client")
    assert result["project_id"] == project["project_id"] and result["groups"] == ["read", "propose"]
    with pytest.raises(Denied):
        consents.find(owner.user_id, "another-client")
    with pytest.raises(Denied):
        consents.create(owner, project["project_id"], "sample-client", ["read"], 3600)
    consents.revoke(owner, value["consent_id"])
    with pytest.raises(Denied):
        consents.find(owner.user_id, "sample-client")


def test_viewer_cannot_consent_to_writes_and_expired_session_is_denied(hosted):
    from physimesh.agent.remote_consent import RemoteConsents

    client, project, owner, viewer = hosted
    consents = RemoteConsents(client.app.state.agent)
    with pytest.raises(Denied):
        consents.create(viewer, project["project_id"], "client", ["read", "change"], 3600)
    consents.create(owner, project["project_id"], "client", ["read"], 3600)
    with client.app.state.metadata.connection(write=True) as db:
        db.execute("UPDATE sessions SET revoked=1 WHERE token_hash=?", (owner.session_hash,))
    with pytest.raises(Denied):
        consents.find(owner.user_id, "client")


def test_token_verification_requires_access_token_client_and_exact_audience():
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    from physimesh.agent.remote_auth import AccessVerifier

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = AccessVerifier(
        "https://issuer.example", "https://app.example/mcp", "https://issuer.example/jwks"
    )

    class Keys:
        def get_signing_key_from_jwt(self, token):
            class Selected:
                pass

            item = Selected()
            item.key = key.public_key()
            return item

    verifier.keys = Keys()
    claims = {
        "iss": "https://issuer.example",
        "aud": "https://app.example/mcp",
        "sub": "user-subject",
        "client_id": "client-123",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }

    def token(values, typ="at+jwt"):
        return jwt.encode(values, key, algorithm="RS256", headers={"typ": typ, "kid": "fixture"})

    assert verifier.verify(token(claims))["client_id"] == "client-123"
    for bad in [
        token(claims, "JWT"),
        token({**claims, "aud": "other"}),
        token({**claims, "aud": ["https://app.example/mcp", "another-resource"]}),
        token({**claims, "exp": int(time.time()) - 1}),
        token({k: v for k, v in claims.items() if k != "client_id"}),
    ]:
        with pytest.raises(Denied):
            verifier.verify(bad)


def test_remote_bound_grant_is_rechecked_when_consent_revoked(hosted):
    from physimesh.agent.remote_consent import RemoteConsents

    client, project, owner, _ = hosted
    service = RemoteConsents(client.app.state.agent)
    consent = service.create(owner, project["project_id"], "client", ["read"], 3600)
    bound = service.bind(owner, "client")
    ctx = client.app.state.agent.policy.grant_context(grant_id=bound["grant_id"])
    assert ctx.project_id == project["project_id"] and ctx.groups == ("read",)
    service.revoke(owner, consent["consent_id"])
    with pytest.raises(Denied):
        client.app.state.agent.policy.grant_context(grant_id=bound["grant_id"])
