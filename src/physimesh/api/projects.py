"""Authenticated local workbench; shared bearer access is not invited identity."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from physimesh.drone.conditioning import ConditionedMap, ConditioningPolicyV1
from physimesh.projects.repository import DraftConflict, ProjectMissing
from physimesh.agent import operations as agent_operations

router = APIRouter(prefix='/api/drone/projects')


class CreateProject(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    title: str = Field(min_length=1, max_length=160)


class SaveDraft(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected_version: int = Field(ge=0)
    snapshot_json: str = Field(max_length=2_000_000)


class FreezeDraft(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected_version: int = Field(ge=0)
    purpose: Literal['screening', 'feasibility', 'cfd_run'] = 'screening'


class ImportMap(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    dataset_json: str = Field(max_length=500_000)


class ConditionMap(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    policy: ConditioningPolicyV1


class RunStudy(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    revision_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class CompareStudies(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    before: str = Field(pattern=r'^[0-9a-f]{64}$')
    after: str = Field(pattern=r'^[0-9a-f]{64}$')


@router.post('/examples/hover', status_code=201)
def example(request: Request):
    from physimesh.projects.examples import create_hover_example
    return register_project(request, lambda: create_hover_example(request.app.state.projects))


@router.post('/examples/realistic', status_code=201)
def realistic_example(request: Request):
    from physimesh.projects.realistic import create_realistic_example
    return register_project(request, lambda: create_realistic_example(request.app.state.projects))


@router.post('/examples/motorout', status_code=201)
def motorout_example(request: Request):
    from physimesh.projects.realistic import create_realistic_example
    return register_project(request, lambda: create_realistic_example(request.app.state.projects, motorout=True))


@router.post('/performance-sources', status_code=201)
def import_map(request: Request, body: ImportMap):
    from physimesh.projects.performance import retain_map
    return operation(lambda: retain_map(request.app.state.projects.artifacts, body.dataset_json.encode('utf-8')))


@router.get('/performance-sources/{digest}')
def source(request: Request, digest: str):
    from physimesh.projects.performance import load_map
    def read():
        model = load_map(request.app.state.projects.artifacts, digest)
        if isinstance(model, ConditionedMap):
            return {'schema_version': 'rotor_map_conditioned_v1', 'dataset': model.raw.model_dump(mode='json'),
                    'conditioning': model.evidence()}
        return model.model_dump(mode='json')
    return operation(read)


@router.post('/performance-sources/{digest}/condition', status_code=201)
def condition_source(request: Request, digest: str, body: ConditionMap):
    from physimesh.projects.performance import retain_conditioned_map
    return operation(lambda: retain_conditioned_map(request.app.state.projects.artifacts, digest, body.policy))


@router.get('/geometry-sources/{digest}')
def geometry_source(request: Request, digest: str):
    def read():
        import hashlib

        from physimesh.drone.stl_import import parse_stl
        settings = request.app.state.settings
        with request.app.state.projects.artifacts.open(digest) as stream:
            raw = stream.read(settings.max_upload_bytes+1)
        if len(raw) > settings.max_upload_bytes or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('geometry source byte integrity or size check failed')
        parse_stl(raw, max_bytes=settings.max_upload_bytes, max_triangles=settings.max_triangles)
        return raw
    return Response(operation(read), media_type='application/octet-stream',
                    headers={'X-Geometry-Source-SHA256': digest})


def operation(action):
    try:
        return action()
    except ProjectMissing as exc:
        raise HTTPException(404, 'project or revision not found') from exc
    except DraftConflict as exc:
        raise HTTPException(409, {'code': 'draft_conflict', 'current_version': exc.current_version,
                                  'message': str(exc)}) from exc
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('')
def projects(request: Request, limit: int = 25, after: str = ''):
    user = request.state.principal.user_id if request.app.state.settings.hosted_mode else None
    organization = request.headers.get('X-Organization-ID') if user is not None else None
    if organization is not None:
        from physimesh.platform.identity import Denied
        with request.app.state.metadata.connection() as db:
            if not db.execute('SELECT 1 FROM org_members WHERE org_id=? AND user_id=?',
                              (organization, user)).fetchone():
                raise Denied('organization access denied')
    return operation(lambda: request.app.state.projects.repository.page(
        limit=limit, after=after, user_id=user, organization_id=organization))


@router.post('', status_code=201)
def create(request: Request, body: CreateProject):
    return register_project(request, lambda: request.app.state.projects.create(body.title))


@router.get('/{project_id}')
def project(request: Request, project_id: str):
    record = operation(lambda: request.app.state.projects.repository.get(project_id))
    if request.app.state.settings.hosted_mode:
        record['access_scope'] = 'authenticated_project'
        record.update(request.state.access)
    return record


@router.get('/{project_id}/history/{kind}')
def history(request: Request, project_id: str, kind: str, limit: int = 25, after: str = ''):
    return operation(lambda: request.app.state.projects.repository.history(project_id, kind, limit=limit, after=after))


@router.get('/{project_id}/inspection')
def inspection(request: Request, project_id: str):
    return operation(lambda: agent_operations.inspect_project(request.app, project_id))


@router.get('/{project_id}/geometry')
def geometry(request: Request, project_id: str, revision_sha256: str | None = None):
    return {'report': operation(lambda: request.app.state.projects.geometry(project_id, revision_sha256))}


@router.get('/{project_id}/geometry/{digest}.stl')
def project_geometry_source(request: Request, project_id: str, digest: str, revision_sha256: str | None = None):
    raw = operation(lambda: request.app.state.projects.geometry_source(project_id, digest, revision_sha256))
    return Response(raw, media_type='model/stl', headers={
        'Cache-Control': 'private, no-store', 'X-Content-SHA256': digest})


@router.put('/{project_id}/draft')
def save(request: Request, project_id: str, body: SaveDraft):
    record = operation(lambda: request.app.state.projects.save(project_id, body.expected_version, body.snapshot_json))
    if request.app.state.settings.hosted_mode:
        record['access_scope'] = 'authenticated_project'
        record.update(request.state.access)
    return record


@router.post('/{project_id}/revisions')
def freeze(request: Request, project_id: str, body: FreezeDraft):
    return operation(lambda: agent_operations.freeze_project(request.app, project_id,
        body.expected_version, body.purpose, getattr(request.state, 'principal', None)))


@router.get('/{project_id}/revisions/{digest}')
def revision(request: Request, project_id: str, digest: str):
    return operation(lambda: request.app.state.projects.repository.revision(project_id, digest).model_dump(mode='json'))


@router.post('/{project_id}/studies')
def run_study(request: Request, project_id: str, body: RunStudy):
    result = operation(lambda: agent_operations.run_study(request.app, project_id,
        body.revision_sha256, getattr(request.state, 'principal', None)))
    if request.app.state.settings.hosted_mode:
        return JSONResponse(result, status_code=202)
    return result


@router.get('/{project_id}/studies/{study}')
def study(request: Request, project_id: str, study: str):
    return operation(lambda: request.app.state.studies.read(project_id, study))


@router.get('/{project_id}/studies/{study}/export')
def export_study(request: Request, project_id: str, study: str):
    raw = operation(lambda: request.app.state.studies.export(project_id, study))
    return Response(raw, media_type='application/json', headers={'Content-Disposition': 'attachment; filename=study.json'})


@router.get('/{project_id}/studies/{study}/summary')
def study_summary(request: Request, project_id: str, study: str):
    return operation(lambda: request.app.state.studies.summary(project_id, study))


def prepared_study_pdf(request, project_id, study):
    if request.app.state.settings.hosted_mode:
        cached = operation(lambda: request.app.state.studies.cached_pdf(project_id, study))
        if cached is None:
            from physimesh.projects.reports import report_identity
            raw, snapshot = operation(lambda: request.app.state.studies.report_inputs(project_id, study))
            job = operation(lambda: request.app.state.jobs.submit(project_id, 'report',
                {'study_sha256': study, 'report_identity': report_identity(raw, snapshot),
                 'application_build': request.app.state.build.get('build_sha256')},
                submitted_by=request.state.principal.user_id))
            return JSONResponse(job, status_code=202, headers={'Cache-Control': 'private, no-store'})
        return cached
    else:
        return operation(lambda: request.app.state.studies.pdf(project_id, study))


@router.get('/{project_id}/studies/{study}/pdf')
def pdf_study(request: Request, project_id: str, study: str):
    prepared = prepared_study_pdf(request, project_id, study)
    if isinstance(prepared, JSONResponse):
        return prepared
    raw, receipt = prepared
    return Response(raw, media_type='application/pdf', headers={
        'Content-Disposition': 'attachment; filename=physicore-local-study.pdf',
        'X-Study-JSON-SHA256': receipt['study_json_sha256'], 'X-PDF-SHA256': receipt['pdf_sha256'],
        'X-Report-Renderer': receipt['renderer_version'],
        'X-Report-Renderer-SHA256': receipt['renderer_source_sha256']})


@router.get('/{project_id}/studies/{study}/review-pack')
def review_pack(request: Request, project_id: str, study: str):
    import hashlib

    from physimesh.projects.review_pack import PackBusy, build_review_pack
    prepared = prepared_study_pdf(request, project_id, study)
    if isinstance(prepared, JSONResponse):
        return prepared
    try:
        raw, manifest = operation(lambda: build_review_pack(request.app.state.studies, project_id, study, prepared))
    except PackBusy as exc:
        raise HTTPException(503, str(exc), headers={'Retry-After': '2'}) from exc
    return Response(raw, media_type='application/zip', headers={
        'Cache-Control': 'private, no-store',
        'Content-Disposition': 'attachment; filename=physicore-study-review.zip',
        'X-Review-Pack-Schema': manifest['schema_version'], 'X-Study-SHA256': manifest['study_sha256'],
        'X-Project-ID': manifest['project_id'],
        'X-Revision-SHA256': manifest['revision_sha256'], 'X-Pack-SHA256': hashlib.sha256(raw).hexdigest()})


@router.post('/{project_id}/comparisons')
def compare_studies(request: Request, project_id: str, body: CompareStudies):
    return operation(lambda: agent_operations.compare_studies(request.app, project_id, body.before, body.after))


def register_project(request, action):
    if not request.app.state.settings.hosted_mode:
        return operation(action)
    from physimesh.platform.identity import Denied
    from physimesh.platform.scoped_artifacts import CURRENT_SCOPE
    org = request.headers.get('X-Organization-ID')
    if not org:
        raise Denied('select an organization before creating a project')
    access = request.app.state.identity
    reservation = access.reserve_project(request.state.principal, org)
    try:
        record = operation(action)
        access.claim_project(request.state.principal, org, record['project_id'], reservation=reservation)
    finally:
        access.release_project_reservation(reservation)
    scope = CURRENT_SCOPE.get()
    request.app.state.projects.artifacts.bind_pending(scope, record['project_id'])
    record['access_scope'], record['role'] = 'authenticated_project', 'engineer'
    record.update(can_invite=True, can_review=True, org_id=org)
    return record


@router.get('/{project_id}/jobs/{job_id}')
def job(request: Request, project_id: str, job_id: str):
    if not request.app.state.settings.hosted_mode:
        raise HTTPException(404, 'durable jobs require hosted mode')
    return operation(lambda: agent_operations.read_job(request.app, project_id, job_id))


@router.post('/{project_id}/jobs/{job_id}/cancel')
def cancel_job(request: Request, project_id: str, job_id: str):
    if not request.app.state.settings.hosted_mode:
        raise HTTPException(404, 'durable jobs require hosted mode')
    return request.app.state.jobs.cancel(project_id, job_id)


@router.post('/{project_id}/jobs/{job_id}/retry')
def retry_job(request: Request, project_id: str, job_id: str):
    if not request.app.state.settings.hosted_mode:
        raise HTTPException(404, 'durable jobs require hosted mode')
    return operation(lambda: request.app.state.jobs.retry(project_id, job_id))


@router.get('/{project_id}/jobs')
def jobs(request: Request, project_id: str, limit: int = 25, after: str = ''):
    if not request.app.state.settings.hosted_mode:
        raise HTTPException(404, 'durable jobs require hosted mode')
    return operation(lambda: request.app.state.jobs.page(project_id, limit=limit, after=after))
