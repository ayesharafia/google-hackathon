import asyncio
import time
import jwt
import httpx2
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from physimesh.api.app import create_app
from physimesh.api.settings import Settings


def test_remote_http_sdk_scoped_project_and_revocation(tmp_path):
    async def exercise():
        origin = "https://app.example"
        issuer = "https://issuer.example"
        resource = origin + "/mcp/"
        app = create_app(
            Settings(
                tmp_path,
                tmp_path / "jobs.sqlite",
                "",
                None,
                hosted_mode=True,
                remote_mcp_origin=origin,
                remote_mcp_issuer=issuer,
                remote_mcp_jwks_url=issuer + "/jwks",
            )
        )
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        class Keys:
            def get_signing_key_from_jwt(self, token):
                class Selected:
                    pass

                item = Selected()
                item.key = key.public_key()
                return item

        app.state.remote_http.verifier.keys = Keys()
        identity = app.state.identity
        uid = identity.provision("owner@example.test", password="Synthetic-password-123")
        with app.state.metadata.connection(write=True) as db:
            db.execute("UPDATE users SET issuer=?,subject=? WHERE user_id=?", (issuer, "sub-owner", uid))
        browser_token = identity.login("owner@example.test", "Synthetic-password-123")["token"]
        principal = identity.session(browser_token)
        org = identity.organization(uid, "Synthetic")
        claims = {
            "iss": issuer,
            "aud": resource,
            "sub": "sub-owner",
            "client_id": "mcp-client",
            "iat": int(time.time()),
            "exp": int(time.time()) + 1200,
        }
        token = jwt.encode(claims, key, algorithm="RS256", headers={"typ": "at+jwt", "kid": "key"})
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=origin) as http:
                p = await http.post(
                    "/api/drone/projects/examples/hover",
                    headers={
                        "Authorization": "Bearer " + browser_token,
                        "Origin": origin,
                        "X-Organization-ID": org,
                    },
                )
                assert p.status_code == 201, p.text
                pid = p.json()["project_id"]
                consent_response = await http.post(
                    "/api/drone/agent/remote-consents",
                    headers={"Authorization": "Bearer " + browser_token, "Origin": origin},
                    json={
                        "project_id": pid,
                        "client_id": "mcp-client",
                        "groups": ["read"],
                        "lifetime_s": 600,
                    },
                )
                assert consent_response.status_code == 201, consent_response.text
                consent = consent_response.json()
                listed = await http.get(
                    "/api/drone/agent/remote-consents",
                    headers={"Authorization": "Bearer " + browser_token},
                    params={"project_id": pid},
                )
                assert listed.json()["consents"][0]["client_id"] == "mcp-client"
                invalid_host = await http.get(
                    "/.well-known/oauth-protected-resource/mcp/", headers={"Host": "untrusted.example"}
                )
                assert invalid_host.status_code == 400
                too_large = await http.post(
                    "/mcp/",
                    headers={
                        "Authorization": "Bearer " + token,
                        "Accept": "application/json, text/event-stream",
                    },
                    content=b" " * 262145,
                )
                assert too_large.status_code == 413
                metadata = await http.get("/.well-known/oauth-protected-resource/mcp/")
                assert metadata.json()["resource"] == resource
                unauth = await http.post("/mcp/", headers={"Accept": "application/json, text/event-stream"})
                assert unauth.status_code == 401 and "resource_metadata" in unauth.headers["www-authenticate"]
                second = await http.post(
                    "/api/drone/projects/examples/hover",
                    headers={
                        "Authorization": "Bearer " + browser_token,
                        "Origin": origin,
                        "X-Organization-ID": org,
                    },
                )
                second_pid = second.json()["project_id"]
                claims2 = {**claims, "client_id": "second-client"}
                token2 = jwt.encode(claims2, key, algorithm="RS256", headers={"typ": "at+jwt", "kid": "key"})
                app.state.agent.remote_consents.create(principal, second_pid, "second-client", ["read"], 600)

            async def scoped_call(access, allowed, denied_id):
                async with httpx2.AsyncClient(
                    transport=httpx2.ASGITransport(app=app), headers={"Authorization": "Bearer " + access}
                ) as transport:
                    async with streamable_http_client(resource, http_client=transport) as (read, write):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            good = await session.call_tool("physicore_design_get", {"project_id": allowed})
                            denied = await session.call_tool(
                                "physicore_design_get", {"project_id": denied_id}
                            )
                            assert (
                                good.model_dump(by_alias=True)["structuredContent"]["data"]["project_id"]
                                == allowed
                            )
                            assert denied.model_dump(by_alias=True)["isError"] is True

            await asyncio.gather(scoped_call(token, pid, second_pid), scoped_call(token2, second_pid, pid))
            async with httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app), headers={"Authorization": "Bearer " + token}
            ) as mcp_http:
                async with streamable_http_client(resource, http_client=mcp_http) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        names = {tool.name for tool in tools.tools}
                        assert "physicore_design_get" in names and "physicore_proposal_apply" not in names
                        result = await session.call_tool("physicore_design_get", {"project_id": pid})
                        assert (
                            result.model_dump(by_alias=True)["structuredContent"]["data"]["project_id"] == pid
                        )
                async with httpx2.AsyncClient(
                    transport=httpx2.ASGITransport(app=app), base_url=origin
                ) as ordinary:
                    denied_general = await ordinary.get(
                        "/api/drone/projects", headers={"Authorization": "Bearer " + token}
                    )
                    assert denied_general.status_code == 401
                app.state.agent.remote_consents.revoke(principal, consent["consent_id"])
                denied = await mcp_http.post(
                    resource,
                    headers={"Accept": "application/json, text/event-stream"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                )
                assert denied.status_code == 401
                with_cookie = await mcp_http.post(
                    resource,
                    headers={
                        "Accept": "application/json, text/event-stream",
                        "Cookie": "physicore_hosted_session=synthetic",
                    },
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                )
                assert with_cookie.status_code == 403
                writable = app.state.agent.remote_consents.create(
                    principal, pid, "mcp-client", ["read", "propose", "change"], 600
                )
                async with streamable_http_client(resource, http_client=mcp_http) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        proposal = await session.call_tool(
                            "physicore_design_propose",
                            {
                                "project_id": pid,
                                "expected_version": 1,
                                "edits": [{"field": "mission.duration_s", "value": 8.0, "unit": "min"}],
                            },
                        )
                        data = proposal.model_dump(by_alias=True)["structuredContent"]["data"]
                        args = {
                            "project_id": pid,
                            "proposal_id": data["proposal_id"],
                            "request_id": "exact_req_001",
                        }
                        pending = await session.call_tool("physicore_proposal_apply", args)
                        result = pending.model_dump(by_alias=True)["structuredContent"]
                        assert result["status"] == "awaiting_review"
                        async with httpx2.AsyncClient(
                            transport=httpx2.ASGITransport(app=app), base_url=origin
                        ) as human:
                            approved = await human.post(
                                "/api/drone/agent/reviews/" + result["data"]["review_id"] + "/confirm",
                                headers={"Authorization": "Bearer " + browser_token, "Origin": origin},
                                json={"execute": True},
                            )
                            assert approved.status_code == 200, approved.text
                            assert approved.json()["data"]["draft_version"] == 2
                        retry = await session.call_tool("physicore_proposal_apply", args)
                        assert retry.model_dump(by_alias=True)["structuredContent"] == approved.json()
                app.state.agent.remote_consents.revoke(principal, writable["consent_id"])

    asyncio.run(exercise())
