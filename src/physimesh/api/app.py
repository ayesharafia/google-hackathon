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
from .atmosphere import router as atmosphere_router
from .cantilever import router as cantilever_router
from .contracts import router as contracts_router
from .dependencies import router as dependencies_router
from .evaluation import router as evaluation_router
from .fixed_wing import router as fixed_wing_router
from .projects import router as projects_router
from .results import router as results_router
from .screening import router as screening_router
from .sessions import COOKIE, BrowserSessions, same_origin, valid_bearer
from .sessions import router as sessions_router
from .settings import Settings, load_settings
from .thermal import router as thermal_router


def create_app(settings: Settings) -> FastAPI:
    """Create the API and source-checkout web shell; no physical inputs are defaulted."""
    @asynccontextmanager
    async def lifespan(application):
        from contextlib import AsyncExitStack
        try:
            async with AsyncExitStack() as stack:
                remote = getattr(application.state, 'remote_http', None)
                if remote:
                    await stack.enter_async_context(remote.manager.run())
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
    from ..projects.source_library import SourceLibrary
    app.state.source_library = SourceLibrary(app.state.metadata, app.state.projects, app.state.identity)
    app.state.studies = LocalStudies(app.state.projects)
    from ..agent.api import router as agent_router
    from ..agent.service import AgentService
    app.state.agent = AgentService(app)
    from ..agent.provider_settings import ProviderSettings
    from ..agent.provider_settings import router as provider_settings_router
    app.state.provider_settings = ProviderSettings(app)
    app.include_router(provider_settings_router)
    from ..platform.hosted_signin import HostedSignin, RedactOIDCQuery
    from ..platform.hosted_signin_api import router as signin_router
    app.state.hosted_signin = HostedSignin(app) if settings.hosted_signin_issuer else None
    app.include_router(signin_router)
    app.add_middleware(RedactOIDCQuery)
    import secrets
    app.state.chat_signing_key = secrets.token_bytes(32)
    from threading import Lock
    app.state.chat_run_lock = Lock()
    app.state.chat_runs = {}
    from ..agent.chat import router as chat_router
    app.include_router(chat_router)
    app.include_router(agent_router)
    if settings.remote_mcp_origin:
        from ..agent.remote_http import RemoteHTTP
        app.state.remote_http = RemoteHTTP(app)
        app.mount('/mcp', app.state.remote_http)

        @app.get('/.well-known/oauth-protected-resource/mcp/')
        def remote_metadata(request: Request):
            return app.state.remote_http.metadata(request)

    app.include_router(atmosphere_router)
    app.include_router(evaluation_router)
    app.include_router(fixed_wing_router)
    app.include_router(thermal_router)
    app.include_router(cantilever_router)
    app.include_router(dependencies_router)
    app.include_router(drone_router)
    app.include_router(results_router)
    app.include_router(contracts_router)
    app.include_router(screening_router)
    from .source_library import router as source_library_router
    app.include_router(source_library_router)
    app.include_router(projects_router)
    if not settings.hosted_mode:
        app.include_router(sessions_router)
    from ..platform.api import router as platform_router
    app.include_router(platform_router)

    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        if request.method == "POST" and request.url.path == "/api/drone/dependencies/plan":
            return JSONResponse({"detail": "Invalid dependency plan request."}, status_code=422)
        if request.method == "POST" and request.url.path == "/api/drone/cantilever/screen":
            return JSONResponse({"detail": "Invalid cantilever screening request."}, status_code=422)
        if request.method == "POST" and request.url.path == "/api/drone/thermal/screen":
            return JSONResponse({"detail": "Invalid thermal screening request."}, status_code=422)
        if request.method == "POST" and request.url.path == "/api/drone/fixed-wing/screen":
            return JSONResponse({"detail": "Invalid fixed-wing screening request."}, status_code=422)
        if request.method == "POST" and request.url.path == "/api/drone/evaluations/evaluate":
            return JSONResponse({"detail": "Invalid evaluation request."}, status_code=422)
        if request.url.path == "/api/drone/atmosphere/evaluate":
            # Validation errors may contain NaN/Infinity inputs, which cannot
            # be serialized by JSONResponse. Do not echo raw model inputs.
            return JSONResponse({"detail": "Invalid atmosphere request."}, status_code=422)
        if request.url.path in ("/api/drone/agent/chat", "/api/drone/agent/provider-settings"):
            return JSONResponse({"detail": "Invalid chat request."}, status_code=422)
        from fastapi.exception_handlers import request_validation_exception_handler
        return await request_validation_exception_handler(request, exc)

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
        agent_path = path == '/api/drone/agent' or path.startswith('/api/drone/agent/')
        if agent_path and settings.public_access:
            return JSONResponse({'detail': 'Agent access requires an authenticated workspace.'}, status_code=403)
        authorization = request.headers.get('authorization', '')
        if agent_path and authorization.startswith('Bearer pca_'):
            delegated = (request.method == 'POST' and path.startswith('/api/drone/agent/actions/')) or (
                request.method == 'GET' and (path in ('/api/drone/agent/catalog', '/api/drone/agent/resources',
                    '/api/drone/agent/resource') or path.startswith(('/api/drone/agent/records/', '/api/drone/agent/exports/'))))
            if not delegated:
                return JSONResponse({'detail': 'AI-client credentials cannot perform trusted user controls.'}, status_code=403)
            try:
                request.state.agent_context = await run_in_threadpool(
                    app.state.agent.policy.grant_context, token=authorization[7:])
            except Denied as exc:
                return JSONResponse({'detail': str(exc)}, status_code=403)
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
            cookie_auth = not authorization and app.state.hosted_signin is not None
            if cookie_auth:
                from ..platform.hosted_signin import HOSTED_COOKIE
                principal = await run_in_threadpool(app.state.hosted_signin.principal, request.cookies.get(HOSTED_COOKIE, ''))
                if request.method not in ('GET','HEAD','OPTIONS') and not same_origin(request):
                    raise Denied('Submit changes from this workspace page.')
            else:
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
            def restricted_session():
                with app.state.metadata.connection() as db:
                    remote = db.execute('SELECT 1 FROM remote_oauth_sessions WHERE token_hash=?', (principal.session_hash,)).fetchone()
                    browser = db.execute('SELECT 1 FROM hosted_browser_sessions WHERE token_hash=?', (principal.session_hash,)).fetchone() if app.state.hosted_signin else None
                    return bool(remote) or (bool(browser) and not cookie_auth)
            if await run_in_threadpool(restricted_session):
                raise InvalidSession('Credential cannot access application routes.')
            request.state.hosted_cookie = cookie_auth
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
            elif not (path == '/api/drone/projects' or path.startswith(('/api/drone/platform/', '/api/drone/contracts', '/api/drone/agent/'))
                      or path in ('/api/drone/validate', '/api/drone/atmosphere/evaluate', '/api/drone/evaluations/catalog', '/api/drone/evaluations/evaluate', '/api/drone/fixed-wing/screen', '/api/drone/thermal/screen', '/api/drone/cantilever/screen', '/api/drone/dependencies/plan')):
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
