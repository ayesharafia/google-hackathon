"""Authenticated application shell; software readiness is not aircraft evidence [M§2]."""
from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ..drone.api import router as drone_router
from ..drone.models import project_from_mapping, readiness
from .results import router as results_router
from .settings import Settings, load_settings


def create_app(settings: Settings) -> FastAPI:
    """Create the API and source-checkout web shell; no physical inputs are defaulted."""
    app = FastAPI(title="PhysiCore Drone", version="0.1.0")
    app.state.settings = settings
    app.include_router(drone_router)
    app.include_router(results_router)

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
        """Input readiness for a project snapshot [M§26]; never a capability or validation claim.

        Body: {"project": <drone_manifest_v1 mapping>, "purpose": "screening"|"cfd_run"|"feasibility"}.
        """
        purpose = body.get("purpose")
        if purpose not in ("screening", "cfd_run", "feasibility"):
            return JSONResponse({"detail": "purpose must be screening, cfd_run or feasibility"},
                                status_code=422)
        try:
            snapshot = project_from_mapping(body.get("project"))
        except (TypeError, ValueError) as exc:
            return JSONResponse({"detail": f"invalid project: {exc}"}, status_code=422)
        report = readiness(snapshot, purpose)
        return JSONResponse({"purpose": report.purpose, "ready": report.ready,
                             "status": report.status.value if report.status else None,
                             "blocking": report.blocking, "warnings": report.warnings})

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
