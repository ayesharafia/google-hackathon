"""Authenticated application shell; software readiness is not aircraft evidence [M§2]."""
from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ..core.artifacts import ArtifactStore
from ..drone.api import router as drone_router
from ..drone.models import project_from_mapping, readiness
from ..projects.service import ProjectService
from ..projects.sqlite import SQLiteProjects
from ..projects.studies import LocalStudies
from .contracts import router as contracts_router
from .fixed_wing import router as fixed_wing_router
from .projects import router as projects_router
from .results import router as results_router
from .screening import router as screening_router
from .settings import Settings, load_settings


def create_app(settings: Settings) -> FastAPI:
    """Create the API and source-checkout web shell; no physical inputs are defaulted."""
    app = FastAPI(title="PhysiCore Drone", version="0.1.0")
    app.state.settings = settings
    app.state.projects = ProjectService(SQLiteProjects(settings.db_path.parent / 'projects.sqlite'),
                                        ArtifactStore(settings.data_root / 'artifacts'))
    app.state.studies = LocalStudies(app.state.projects)
    app.include_router(drone_router)
    app.include_router(fixed_wing_router)
    app.include_router(results_router)
    app.include_router(contracts_router)
    app.include_router(screening_router)
    app.include_router(projects_router)

    @app.middleware("http")
    async def protect_drone_routes(request: Request, call_next):
        """Protect the whole drone namespace, including future routes [plan Task 1.5]."""
        path = request.url.path
        if settings.local_no_auth and path.startswith("/api/"):
            if request.url.hostname not in {"127.0.0.1", "localhost", "::1"}:
                return JSONResponse({"detail": "Use the local workspace address"}, status_code=403)
            origin = request.headers.get("origin")
            if (origin is not None and origin != f"{request.url.scheme}://{request.url.netloc}") or (
                request.headers.get("sec-fetch-site") == "cross-site"
            ):
                return JSONResponse({"detail": "Use this workspace's own page"}, status_code=403)
        elif path == "/api/drone" or path.startswith("/api/drone/"):
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
