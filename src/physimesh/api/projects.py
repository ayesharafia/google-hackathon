"""Authenticated local workbench; shared bearer access is not invited identity."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from physimesh.drone.authoring import inspect_inputs
from physimesh.drone.conditioning import ConditionedMap, ConditioningPolicyV1
from physimesh.drone.models import project_from_mapping, readiness
from physimesh.projects.contracts import parse_snapshot
from physimesh.projects.repository import DraftConflict, ProjectMissing

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
    return operation(lambda: create_hover_example(request.app.state.projects))


@router.post('/examples/realistic', status_code=201)
def realistic_example(request: Request):
    from physimesh.projects.realistic import create_realistic_example
    return operation(lambda: create_realistic_example(request.app.state.projects))


@router.post('/examples/motorout', status_code=201)
def motorout_example(request: Request):
    from physimesh.projects.realistic import create_realistic_example
    return operation(lambda: create_realistic_example(request.app.state.projects, motorout=True))


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
def projects(request: Request):
    return {'projects': request.app.state.projects.repository.list_projects(),
            'qualification': 'Local single-operator workspace; invited identity is not configured.'}


@router.post('', status_code=201)
def create(request: Request, body: CreateProject):
    return operation(lambda: request.app.state.projects.create(body.title))


@router.get('/{project_id}')
def project(request: Request, project_id: str):
    return operation(lambda: request.app.state.projects.repository.get(project_id))


@router.get('/{project_id}/inspection')
def inspection(request: Request, project_id: str):
    def inspect():
        project = request.app.state.projects.repository.get(project_id)
        snapshot = parse_snapshot(project['snapshot_json'])
        report = inspect_inputs(snapshot)
        ready = readiness(project_from_mapping(snapshot), 'screening')
        from physimesh.drone.capacity import hover_readiness
        from physimesh.projects.performance import load_map, performance_refs
        sources, errors = {}, []
        for digest in performance_refs(snapshot):
            try:
                sources[digest] = load_map(request.app.state.projects.artifacts, digest)
            except (ValueError, KeyError, TypeError) as exc:
                errors.append(str(exc))
        return {**report, 'draft_version': project['draft_version'],
                'hover_readiness': hover_readiness(snapshot, sources, errors),
                'screening_readiness': {'ready': ready.ready, 'blocking': ready.blocking}}
    return operation(inspect)


@router.put('/{project_id}/draft')
def save(request: Request, project_id: str, body: SaveDraft):
    return operation(lambda: request.app.state.projects.save(project_id, body.expected_version, body.snapshot_json))


@router.post('/{project_id}/revisions')
def freeze(request: Request, project_id: str, body: FreezeDraft):
    return operation(lambda: request.app.state.projects.freeze(project_id, body.expected_version, body.purpose))


@router.get('/{project_id}/revisions/{digest}')
def revision(request: Request, project_id: str, digest: str):
    return operation(lambda: request.app.state.projects.repository.revision(project_id, digest).model_dump(mode='json'))


@router.post('/{project_id}/studies')
def run_study(request: Request, project_id: str, body: RunStudy):
    return operation(lambda: request.app.state.studies.run(project_id, body.revision_sha256))


@router.get('/{project_id}/studies/{study}')
def study(request: Request, project_id: str, study: str):
    return operation(lambda: request.app.state.studies.read(project_id, study))


@router.get('/{project_id}/studies/{study}/export')
def export_study(request: Request, project_id: str, study: str):
    raw = operation(lambda: request.app.state.studies.export(project_id, study))
    return Response(raw, media_type='application/json', headers={'Content-Disposition': 'attachment; filename=study.json'})


@router.get('/{project_id}/studies/{study}/pdf')
def pdf_study(request: Request, project_id: str, study: str):
    raw, receipt = operation(lambda: request.app.state.studies.pdf(project_id, study))
    return Response(raw, media_type='application/pdf', headers={
        'Content-Disposition': 'attachment; filename=physicore-local-study.pdf',
        'X-Study-JSON-SHA256': receipt['study_json_sha256'], 'X-PDF-SHA256': receipt['pdf_sha256'],
        'X-Report-Renderer': receipt['renderer_version'],
        'X-Report-Renderer-SHA256': receipt['renderer_source_sha256']})


@router.post('/{project_id}/comparisons')
def compare_studies(request: Request, project_id: str, body: CompareStudies):
    return operation(lambda: request.app.state.studies.compare(project_id, body.before, body.after))
