"""Opt-in browser OIDC endpoints; callbacks never expose provider tokens."""

from urllib.parse import parse_qs
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from .hosted_signin import HOSTED_COOKIE, TRANSACTION_COOKIE

router = APIRouter(prefix="/api/oidc")


def configured(request):
    signin = getattr(request.app.state, "hosted_signin", None)
    if not signin:
        raise HTTPException(404, "Organization sign-in is not configured.")
    if not signin.valid_origin(request):
        raise HTTPException(400, "Invalid sign-in origin.")
    return signin


def private(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/status")
def status(request: Request):
    signin = getattr(request.app.state, "hosted_signin", None)
    if not signin:
        return private(JSONResponse({"enabled": False, "connected": False}))
    if not signin.valid_origin(request):
        raise HTTPException(400, "Invalid sign-in origin.")
    try:
        signin.principal(request.cookies.get(HOSTED_COOKIE, ""))
        connected = True
    except Exception:
        connected = False
    return private(JSONResponse({"enabled": True, "connected": connected}))


@router.get("/start")
def start(request: Request):
    signin = configured(request)
    try:
        metadata = signin.provider.metadata()
        tx = signin.transactions.create()
        location = signin.provider.authorize_url(metadata, tx)
    except Exception:
        raise HTTPException(503, "Organization sign-in is unavailable.") from None
    response = private(RedirectResponse(location, status_code=302))
    response.set_cookie(
        TRANSACTION_COOKIE,
        tx["browser"],
        max_age=300,
        path="/api/oidc/callback",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/callback")
def callback(request: Request):
    signin = configured(request)
    success = False
    token = None
    try:
        raw = request.scope.get("state", {}).get("oidc_query", b"")
        if len(raw) > 4096:
            raise ValueError()
        params = parse_qs(raw.decode("ascii"), strict_parsing=True)
        if (
            not {"state", "code"} <= set(params)
            or set(params) - {"state", "code", "iss"}
            or any(len(x) != 1 for x in params.values())
        ):
            raise ValueError()
        if "iss" in params and params["iss"][0] != signin.provider.issuer:
            raise ValueError()
        code = params["code"][0]
        if not 1 <= len(code) <= 2048:
            raise ValueError()
        tx = signin.transactions.consume(params["state"][0], request.cookies.get(TRANSACTION_COOKIE, ""))
        metadata = signin.provider.metadata()
        claims = signin.provider.exchange(metadata, code, tx["verifier"], tx["nonce_hash"])
        token = signin.issue(claims)
        success = True
    except Exception:
        pass
    response = private(
        RedirectResponse(
            "/web/workbench.html" if success else "/web/workbench.html?signin=failed", status_code=303
        )
    )
    response.delete_cookie(
        TRANSACTION_COOKIE, path="/api/oidc/callback", secure=True, httponly=True, samesite="lax"
    )
    if token:
        response.set_cookie(
            HOSTED_COOKIE, token, max_age=43200, path="/api", secure=True, httponly=True, samesite="strict"
        )
    return response
