"""Authenticated application shell; software readiness is not aircraft evidence [M§2]."""
from __future__ import annotations

import hmac
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from ..core.artifacts import ArtifactStore
from ..drone.api import router as drone_router
from ..drone.models import project_from_mapping, readiness
from ..platform.database import MetadataDB, Overloaded
from ..platform.identity import Denied, Identity, InvalidSession, OIDCVerifier
from ..platform.jobs import Jobs
from ..platform.release import build_identity
from ..platform.scoped_artifacts import ScopedArtifacts, artifact_scope
from ..projects.service import ProjectService
from ..projects.sqlite import SQLiteProjects
from ..projects.studies import LocalStudies
from .contracts import router as contracts_router
from .projects import router as projects_router
from .results import router as results_router
from .screening import router as screening_router
from .sessions import COOKIE, BrowserSessions, same_origin, valid_bearer
from .sessions import router as sessions_router
from .settings import Settings, load_settings


def create_app(settings: Settings) -> FastAPI:
    """Create the API and source-checkout web shell; no physical inputs are defaulted."""
    @asynccontextmanager
    async def lifespan(application):
        try:
            yield
        finally:
            application.state.metadata.close()
    app = FastAPI(title="PhysiCore Drone", version="0.1.0", lifespan=lifespan)
    from ..platform.body_limit import BodyLimit
    app.add_middleware(BodyLimit, upload_bytes=settings.max_upload_bytes)
    app.state.settings = settings
    app.state.build = build_identity(verify=True)
    project_path = settings.db_path.parent/'projects.sqlite'
    app.state.metadata = MetadataDB(url=settings.database_url, pool_size=settings.pool_size) if settings.database_url else (
        MetadataDB(project_path))
    if settings.database_url:
        from ..platform.postgres import PostgreSQLProjects
        repository = PostgreSQLProjects(app.state.metadata)
    else:
        repository = SQLiteProjects(project_path)
    store = ArtifactStore(settings.data_root/'artifacts')
    if settings.s3_bucket:
        import boto3
        from botocore.config import Config

        from ..platform.object_storage import S3Artifacts
        store = S3Artifacts(boto3.client('s3', endpoint_url=settings.s3_endpoint, region_name=settings.s3_region,
                            config=Config(signature_version='s3v4', connect_timeout=5, read_timeout=10,
                                          max_pool_connections=settings.pool_size*2, retries={'max_attempts': 3})),
                            settings.s3_bucket)
        store.verify_private_bucket()
    app.state.artifact_backend = store
    app.state.browser_sessions = (BrowserSessions(settings.data_root/'browser-sessions.sqlite', settings.api_token)
                                  if not settings.hosted_mode and not settings.public_access else None)
    app.state.identity = Identity(app.state.metadata) if settings.hosted_mode else None
    app.state.jobs = Jobs(app.state.metadata) if settings.hosted_mode else None
    from ..platform.login_limit import LoginLimit
    app.state.login_limit = LoginLimit()
    app.state.oidc = OIDCVerifier(settings.oidc_issuer, settings.oidc_audience, settings.oidc_jwks_url) if (
        settings.hosted_mode and settings.oidc_issuer) else None
    app.state.projects = ProjectService(repository, ScopedArtifacts(store, app.state.identity)
                                        if settings.hosted_mode else store)
    app.state.studies = LocalStudies(app.state.projects)
    app.include_router(drone_router)
    app.include_router(results_router)
    app.include_router(contracts_router)
    app.include_router(screening_router)
    app.include_router(projects_router)
    if not settings.hosted_mode:
        app.include_router(sessions_router)
    from ..platform.api import router as platform_router
    app.include_router(platform_router)

    @app.exception_handler(Denied)
    async def denied_handler(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=403)

    @app.exception_handler(Overloaded)
    async def overload_handler(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=503, headers={'Retry-After': '2'})

    @app.middleware("http")
    async def protect_drone_routes(request: Request, call_next):
        """Protect the whole drone namespace, including future routes [plan Task 1.5]."""
        path = request.url.path
        if not (path == '/api/drone' or path.startswith('/api/drone/')):
            return await call_next(request)
        if not settings.hosted_mode:
            if settings.public_access:
                if (request.method not in ('GET', 'HEAD', 'OPTIONS') and 'origin' in request.headers
                        and not same_origin(request)):
                    return JSONResponse({'detail': "Submit changes from this workspace's own page."}, status_code=403,
                                        headers={'Cache-Control': 'no-store'})
                return await call_next(request)
            bearer = valid_bearer(request)
            sessions = app.state.browser_sessions
            remembered = sessions.valid(request.cookies.get(COOKIE, '')) if sessions else False
            if ('authorization' in request.headers and not bearer) or not (bearer or remembered):
                return JSONResponse({'detail': 'missing or invalid bearer token'}, status_code=401,
                                    headers={'WWW-Authenticate': 'Bearer', 'Cache-Control': 'no-store'})
            if not bearer and request.method not in ('GET', 'HEAD', 'OPTIONS') and not same_origin(request):
                return JSONResponse({'detail': "Submit changes from this workspace's own page."}, status_code=403,
                                    headers={'Cache-Control': 'no-store'})
            if path.startswith('/api/drone/platform/'):
                return JSONResponse({'detail': 'individual identity requires hosted mode'}, status_code=404)
            return await call_next(request)
        if path == '/api/drone/platform/login' and request.method == 'POST':
            peer = request.client.host if request.client else 'unknown'
            if not app.state.login_limit.allowed(peer):
                return JSONResponse({'detail': 'login rate limit exceeded'}, status_code=429, headers={'Retry-After': '60'})
            return await call_next(request)
        try:
            authorization = request.headers.get('authorization', '')
            if not authorization.startswith('Bearer ') or len(authorization) > 16384:
                raise InvalidSession('individual bearer session required')
            token = authorization[7:]
            def authenticate():
                try:
                    return app.state.identity.session(token)
                except InvalidSession:
                    if app.state.oidc is None:
                        raise
                    return app.state.identity.oidc_session(token, app.state.oidc.verify(token))
            principal = await run_in_threadpool(authenticate)
            request.state.principal = principal
            project_id = None
            if path.startswith('/api/drone/projects/'):
                parts = path[len('/api/drone/projects/'):].split('/')
                if parts[0].startswith('project_'):
                    project_id = parts[0]
                    request.state.access = await run_in_threadpool(app.state.identity.authorize, principal, project_id,
                        write=request.method not in ('GET', 'HEAD') and not path.endswith('/comparisons'), details=True)
                elif parts[0] in ('performance-sources', 'geometry-sources'):
                    project_id = request.headers.get('X-Project-ID')
                    if not project_id:
                        raise Denied('select a project before importing or reading private sources')
                    await run_in_threadpool(app.state.identity.authorize, principal, project_id,
                                            write=request.method not in ('GET', 'HEAD'))
                elif parts[0] != 'examples':
                    raise Denied('private project route is not supported')
            elif path == '/api/drone/import':
                project_id = request.headers.get('X-Project-ID')
                if not project_id:
                    raise Denied('select a project before importing private geometry')
                await run_in_threadpool(app.state.identity.authorize, principal, project_id, write=True)
            elif not (path == '/api/drone/projects' or path.startswith(('/api/drone/platform/', '/api/drone/contracts'))
                      or path == '/api/drone/validate'):
                # Legacy global screening/job/evidence hashes have no tenant ownership records.
                raise Denied('this legacy route has no private project authorization')
            with artifact_scope(project_id):
                return await call_next(request)
        except InvalidSession as exc:
            return JSONResponse({'detail': str(exc)}, status_code=401, headers={'WWW-Authenticate': 'Bearer'})
        except Denied as exc:
            return JSONResponse({'detail': str(exc)}, status_code=403)
        except Overloaded as exc:
            return JSONResponse({'detail': str(exc)}, status_code=503, headers={'Retry-After': '2'})

    from ..platform.monitoring import Metrics
    app.state.metrics = Metrics()

    @app.middleware('http')
    async def measure_request(request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        route = getattr(request.scope.get('route'), 'path', 'unmatched')
        app.state.metrics.record(request.method, route, response.status_code, time.perf_counter()-started)
        return response

    @app.get('/internal/metrics', include_in_schema=False)
    def metrics(request: Request):
        expected = settings.monitoring_token
        if not expected:
            return JSONResponse({'detail': 'monitoring is not configured'}, status_code=404)
        if not hmac.compare_digest(request.headers.get('authorization', '').encode(), ('Bearer '+expected).encode()):
            return JSONResponse({'detail': 'monitoring credential required'}, status_code=401)
        rendered = app.state.metrics.render()
        if settings.hosted_mode:
            with app.state.metadata.connection() as db:
                rows = db.execute('SELECT state,COUNT(*) AS n FROM durable_jobs GROUP BY state').fetchall()
            for row in rows:
                rendered += f'physimesh_jobs{{state="{row["state"]}"}} {row["n"]}\n'
        return Response(rendered, media_type='text/plain; version=0.0.4')

    @app.get("/api/health")
    def health() -> dict:
        """Report process/configuration health only; a pin does not establish capability."""
        return {"status": "ok", "backend_pinned": settings.openfoam_image_digest is not None,
                "backend_image": settings.openfoam_image_digest, "capabilities": [],
                "workflow_ready": False, 'mode': 'hosted' if settings.hosted_mode else 'local',
                'build': {k: v for k, v in app.state.build.items() if k in ('build_sha256', 'revision', 'dirty')},
                'metadata': 'postgresql' if settings.database_url else 'sqlite_local',
                'artifacts': 'private_s3' if settings.s3_bucket else 'local_filesystem'}

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
        return RedirectResponse('/web/workbench.html' if settings.hosted_mode else '/web/')

    # Assets live alongside src in the greenfield source checkout [plan Task 1.5].
    web_root = Path(__file__).resolve().parents[1]/'resources/web'
    if not web_root.exists():
        web_root = Path(__file__).resolve().parents[3]/'web'
    app.mount("/web", StaticFiles(directory=web_root, html=True), name="web")
    return app


def app_from_environment() -> FastAPI:
    """Uvicorn factory using PHYSIMESH_* configuration; no physical units."""
    return create_app(load_settings(os.environ))
