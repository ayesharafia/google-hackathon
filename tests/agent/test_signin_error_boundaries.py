"""Synthetic failures must remain generic at hosted sign-in error boundaries."""
from contextlib import nullcontext
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException

from physimesh.platform import hosted_signin_api as endpoints
from physimesh.platform.hosted_signin import HOSTED_COOKIE, TRANSACTION_COOKIE, Provider
from physimesh.platform.identity import Denied

SENTINEL = "synthetic-private-provider-detail"


def fail(*args, **kwargs):
    raise RuntimeError(SENTINEL)


def request(signin, query=b""):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(hosted_signin=signin)),
        cookies={},
        scope={"state": {"oidc_query": query}},
    )


@pytest.mark.parametrize("payload", [b"[]", b"null", b"1", b'"text"', b"not-json"])
def test_provider_nonobject_json_is_sanitized(monkeypatch, payload):
    import urllib.request

    opener = SimpleNamespace(open=lambda *args, **kwargs: nullcontext(SimpleNamespace(read=lambda n: payload)))
    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: opener)
    with pytest.raises(Denied) as caught:
        Provider.http_json("https://issuer.example/token")
    assert str(caught.value) == "Identity provider is unavailable or returned invalid data."
    assert caught.value.__suppress_context__


def test_provider_transport_error_does_not_echo_details(monkeypatch):
    import urllib.request

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: SimpleNamespace(open=fail))
    with pytest.raises(Denied) as caught:
        Provider.http_json("https://issuer.example/token")
    assert SENTINEL not in str(caught.value)
    assert caught.value.__suppress_context__


def test_status_error_is_private_disconnected():
    signin = SimpleNamespace(valid_origin=lambda req: True, principal=fail)
    response = endpoints.status(request(signin))
    assert response.body == b'{"enabled":true,"connected":false}'
    assert response.headers["cache-control"] == "no-store"
    assert SENTINEL not in repr(response.headers)


def test_start_error_is_generic():
    signin = SimpleNamespace(valid_origin=lambda req: True, provider=SimpleNamespace(metadata=fail))
    with pytest.raises(HTTPException) as caught:
        endpoints.start(request(signin))
    assert caught.value.status_code == 503
    assert caught.value.detail == "Organization sign-in is unavailable."
    assert caught.value.__suppress_context__


def test_callback_error_clears_transaction_cookie_without_session():
    signin = SimpleNamespace(
        valid_origin=lambda req: True,
        provider=SimpleNamespace(issuer="https://issuer.example"),
        transactions=SimpleNamespace(consume=fail),
    )
    query = urlencode({"state": "synthetic-state", "code": "synthetic-code"}).encode()
    response = endpoints.callback(request(signin, query))
    assert response.status_code == 303
    assert response.headers["location"] == "/web/workbench.html?signin=failed"
    cookies = response.headers.getlist("set-cookie")
    assert any(TRANSACTION_COOKIE in cookie and "Max-Age=0" in cookie for cookie in cookies)
    assert not any(cookie.startswith(HOSTED_COOKIE + "=") for cookie in cookies)
    assert SENTINEL not in repr(response.headers)
    assert response.headers["cache-control"] == "no-store"
