"""Encrypted provider credentials scoped to a trusted actor."""

import base64
import binascii
import os
import time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field

from .api import trusted
from .contracts import Strict

router = APIRouter(prefix="/api/drone/agent/provider-settings")


class ProviderInput(Strict):
    key: str = Field(default="", max_length=512, repr=False)
    model: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_./-]+$")


class ProviderSettings:
    def __init__(self, app):
        self.app = app
        with app.state.metadata.connection(write=True) as db:
            db.execute("CREATE TABLE IF NOT EXISTS agent_provider_settings (actor TEXT PRIMARY KEY, model TEXT NOT NULL, ciphertext TEXT NOT NULL, updated DOUBLE PRECISION NOT NULL)")

    def cipher(self):
        try:
            raw = base64.b64decode(self.app.state.settings.provider_encryption_key or "", altchars=b"-_", validate=True)
            if len(raw) != 32:
                raise ValueError()
            return AESGCM(raw)
        except (ValueError, binascii.Error):
            raise HTTPException(503, "AI settings need a valid server encryption key.") from None

    def get(self, actor):
        self.cipher()
        with self.app.state.metadata.connection() as db:
            return db.execute("SELECT model,ciphertext FROM agent_provider_settings WHERE actor=?", (actor,)).fetchone()

    def resolve(self, actor):
        row = self.get(actor)
        if not row:
            raise HTTPException(400, "Configure your Groq key in AI settings first.")
        try:
            raw = base64.urlsafe_b64decode(row["ciphertext"])
            key = self.cipher().decrypt(raw[:12], raw[12:], ("groq:" + actor).encode()).decode()
            return key, row["model"]
        except (InvalidTag, ValueError, UnicodeError, binascii.Error):
            raise HTTPException(503, "Saved AI key cannot be decrypted. Check server configuration or replace the key.") from None

    def save(self, actor, body):
        cipher = self.cipher()
        with self.app.state.metadata.connection(write=True) as db:
            row = db.execute("SELECT ciphertext FROM agent_provider_settings WHERE actor=?", (actor,)).fetchone()
            if body.key:
                if len(body.key) < 8 or body.key != body.key.strip():
                    raise HTTPException(400, "Enter a valid Groq key.")
                nonce = os.urandom(12)
                ciphertext = base64.urlsafe_b64encode(nonce + cipher.encrypt(nonce, body.key.encode(), ("groq:" + actor).encode())).decode()
            elif row:
                ciphertext = row["ciphertext"]
            else:
                raise HTTPException(400, "Enter a Groq key.")
            db.execute("INSERT INTO agent_provider_settings(actor,model,ciphertext,updated) VALUES(?,?,?,?) ON CONFLICT(actor) DO UPDATE SET model=excluded.model,ciphertext=excluded.ciphertext,updated=excluded.updated", (actor, body.model, ciphertext, time.time()))


def context(request, changing=False):
    from .chat import secure_origin
    ctx = trusted(request, changing=changing)
    if not secure_origin(request):
        raise HTTPException(403, "Use HTTPS or a loopback connection for AI settings.")
    return ctx


def settings_actor(request, ctx):
    return ctx.actor if request.app.state.settings.hosted_mode else "local:workspace"


@router.get("")
def read_settings(request: Request, response: Response):
    ctx = context(request)
    response.headers["Cache-Control"] = "no-store"
    row = request.app.state.provider_settings.get(settings_actor(request, ctx))
    return {"configured": bool(row), "model": row["model"] if row else None, "shared": not request.app.state.settings.hosted_mode}


@router.put("")
def save_settings(request: Request, response: Response, body: ProviderInput):
    ctx = context(request, changing=True)
    request.app.state.provider_settings.save(settings_actor(request, ctx), body)
    response.headers["Cache-Control"] = "no-store"
    return {"configured": True, "model": body.model, "shared": not request.app.state.settings.hosted_mode}


@router.delete("")
def delete_settings(request: Request, response: Response):
    ctx = context(request, changing=True)
    with request.app.state.metadata.connection(write=True) as db:
        db.execute("DELETE FROM agent_provider_settings WHERE actor=?", (settings_actor(request, ctx),))
    response.headers["Cache-Control"] = "no-store"
    return {"configured": False}
