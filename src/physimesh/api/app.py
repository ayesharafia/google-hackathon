"""Authenticated application shell; software readiness is not aircraft evidence [M§2]."""
from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .settings import Settings, load_settings


def create_app(settings: Settings) -> FastAPI:
    """Create the API and source-checkout web shell; no physical inputs are defaulted."""
    app = FastAPI(title="PhysiCore Drone", version="0.1.0")
    app.state.settings = settings

    @app.middleware("http")
    async def protect_drone_routes(request: Request, call_next):
        """Protect the whole drone namespace, including future routes [plan Task 1.5]."""
        path = request.url.path
        if path == "/api/drone" or path.startswith("/api/drone/"):
            expected = f"Bearer {settings.api_token}"
            if not hmac.compare_digest(request.headers.get("authorization", "").encode(), expected.encode()):
                return JSONResponse({"detail": "missing or invalid bearer token"}, status_code=401,
                                    headers={"WWW-Authenticate": "Bearer"})
        return await call_next(request)

    @app.get("/api/health")
    def health() -> dict:
        """Report process/configuration health only; a pin does not establish capability."""
        return {"status": "ok", "backend_pinned": settings.openfoam_image_digest is not None,
                "backend_image": settings.openfoam_image_digest, "capabilities": [],
                "workflow_ready": False}

    @app.post("/api/drone/validate")
    def validate(body: dict) -> JSONResponse:
        """Report the absent snapshot validator honestly until Task 2.5 [M§26]."""
        return JSONResponse({"status": "inputs_incomplete", "available": False,
                             "blocking": ["project snapshot validator is pending Task 2.5"],
                             "next_action": "Implement the versioned project schema and readiness gates."},
                            status_code=501)

    @app.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse("/web/")

    # Assets live alongside src in the greenfield source checkout [plan Task 1.5].
    web_root = Path(__file__).resolve().parents[3] / "web"
    app.mount("/web", StaticFiles(directory=web_root, html=True), name="web")
    return app


def app_from_environment() -> FastAPI:
    """Uvicorn factory using PHYSIMESH_* configuration; no physical units."""
    return create_app(load_settings(os.environ))
