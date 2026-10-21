"""Revocable browser access without exposing the workspace token to JavaScript."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

COOKIE = "physicore_browser"
LIFETIME = 30 * 24 * 60 * 60
router = APIRouter(prefix="/api/session")


class BrowserSessions:
    """Persist only session hashes, bound to the current workspace token."""

    def __init__(self, path: Path, api_token: str):
        self.path = path
        self.binding = hmac.new(api_token.encode(), b"physicore-browser-sessions-v1", "sha256").hexdigest()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(mode=0o600, exist_ok=True)
        path.chmod(0o600)
        with self._connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS browser_sessions "
                       "(digest TEXT PRIMARY KEY, binding TEXT NOT NULL, expires REAL NOT NULL)")
            db.execute("DELETE FROM browser_sessions WHERE expires <= ? OR binding != ?",
                       (time.time(), self.binding))

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def digest(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def issue(self) -> str:
        value = secrets.token_urlsafe(32)
        now = time.time()
        with self._connection() as db:
            db.execute("DELETE FROM browser_sessions WHERE expires <= ? OR binding != ?", (now, self.binding))
            db.execute("INSERT INTO browser_sessions VALUES (?, ?, ?)",
                       (self.digest(value), self.binding, now + LIFETIME))
        return value

    def valid(self, value: str) -> bool:
        if not value or len(value) > 256:
            return False
        with self._connection() as db:
            return db.execute("SELECT 1 FROM browser_sessions WHERE digest = ? AND binding = ? AND expires > ?",
                              (self.digest(value), self.binding, time.time())).fetchone() is not None

    def revoke(self, value: str) -> None:
        if value and len(value) <= 256:
            with self._connection() as db:
                db.execute("DELETE FROM browser_sessions WHERE digest = ?", (self.digest(value),))


def valid_bearer(request: Request) -> bool:
    expected = f"Bearer {request.app.state.settings.api_token}"
    return hmac.compare_digest(request.headers.get("authorization", "").encode(), expected.encode())


def same_origin(request: Request) -> bool:
    return request.headers.get("origin") == str(request.base_url).rstrip("/")


def reply(connected: bool, status_code: int = 200, detail: str | None = None,
          *, public_access: bool = False) -> JSONResponse:
    body = {"connected": connected, "public_access": public_access}
    if detail:
        body["detail"] = detail
    return JSONResponse(body, status_code=status_code, headers={"Cache-Control": "no-store"})


def cookie_options(request: Request) -> dict:
    return {"path": "/api", "httponly": True, "secure": request.url.scheme == "https", "samesite": "strict"}


@router.get("")
def status(request: Request) -> JSONResponse:
    if request.app.state.settings.public_access:
        return reply(True, public_access=True)
    return reply(request.app.state.browser_sessions.valid(request.cookies.get(COOKIE, "")))


@router.post("")
def connect(request: Request) -> JSONResponse:
    if request.app.state.settings.public_access:
        return reply(True, public_access=True)
    if not valid_bearer(request):
        return reply(False, 401, "Missing or invalid workspace access token.")
    if "origin" in request.headers and not same_origin(request):
        return reply(False, 403, "Connect from this workspace's own page.")
    sessions = request.app.state.browser_sessions
    sessions.revoke(request.cookies.get(COOKIE, ""))
    response = reply(True)
    response.set_cookie(COOKIE, sessions.issue(), max_age=LIFETIME, **cookie_options(request))
    return response


@router.delete("")
def forget(request: Request) -> JSONResponse:
    if not same_origin(request):
        return reply(False, 403, "Forget access from this workspace's own page.")
    public_access = request.app.state.settings.public_access
    if not public_access:
        request.app.state.browser_sessions.revoke(request.cookies.get(COOKIE, ""))
    response = reply(public_access, public_access=public_access)
    response.delete_cookie(COOKIE, **cookie_options(request))
    return response
