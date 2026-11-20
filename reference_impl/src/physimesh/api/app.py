"""FastAPI application factory with bearer-token auth on /api/drone/* (plan Task 1.5)."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException

from .settings import Settings


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="PhysiMesh Drone")

    def require_token(authorization: str = Header(default="")) -> None:
        expected = f"Bearer {settings.api_token}"
        if not hmac.compare_digest(authorization.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="missing or invalid bearer token")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "backend_pinned": settings.openfoam_image_digest is not None}

    drone = APIRouter(prefix="/api/drone", dependencies=[Depends(require_token)])

    @drone.post("/validate")
    def validate(body: dict) -> dict:          # replaced by the real readiness route in Task 2.5
        return {"status": "inputs_incomplete", "blocking": ["project snapshot not implemented"]}

    app.include_router(drone)
    return app
