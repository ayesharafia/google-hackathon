"""Project-authorized tabular preview, persistence and library reuse."""
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from physimesh.api.projects import operation
from physimesh.platform.identity import Denied
from physimesh.projects.tabular import (
    MAX_FILE,
    ImportSelection,
    TableSelection,
    inspect_table,
    preview_import,
)

router = APIRouter(prefix='/api/drone/projects/{project_id}/source-library')


def principal(request, project_id):
    user = getattr(request.state, 'principal', None)
    org = request.app.state.source_library.authorize(project_id, user)
    if org and request.headers.get('X-Organization-ID', org) != org:
        raise Denied('selected organization differs from project')
    return user


@router.post('/inspect')
@router.post('/preview')
@router.post('/save', status_code=201)
async def import_table(request: Request, project_id: str, file: Annotated[UploadFile, File()], spec: Annotated[str, Form(max_length=64000)]):
    try:
        raw = await file.read(MAX_FILE + 1)
        filename = file.filename or ''
    finally:
        await file.close()
    def work():
        user = principal(request, project_id)
        library = request.app.state.source_library
        library.authorize(project_id, user, write=True)
        if len(raw) > MAX_FILE:
            raise ValueError('File exceeds 2 MiB.')
        if request.url.path.endswith('/inspect'):
            return inspect_table(raw, filename, TableSelection.model_validate_json(spec))
        selection = ImportSelection.model_validate_json(spec)
        if request.url.path.endswith('/preview'):
            return preview_import(raw, filename, selection)
        return library.save(project_id, raw, filename, selection, user)
    return await run_in_threadpool(operation, work)


@router.get('')
def library_page(request: Request, project_id: str, query: str = '', after: str = '', limit: int = 25):
    return operation(lambda: request.app.state.source_library.page(
        project_id, principal(request, project_id), query=query, after=after, limit=limit))


@router.get('/{entry_id}')
def library_detail(request: Request, project_id: str, entry_id: str):
    return operation(lambda: request.app.state.source_library.detail(project_id, entry_id, principal(request, project_id)))


@router.get('/{entry_id}/original')
def library_original(request: Request, project_id: str, entry_id: str):
    def read():
        _, manifest, _, objects = request.app.state.source_library.bundle(project_id, entry_id, principal(request, project_id))
        return manifest, objects[0][0]
    manifest, raw = operation(read)
    return Response(raw, media_type='application/octet-stream', headers={
        'Cache-Control': 'private, no-store', 'X-Content-SHA256': manifest['file_sha256'],
        'Content-Disposition': 'attachment; filename="original-source"'})


@router.post('/{entry_id}/reuse')
def library_reuse(request: Request, project_id: str, entry_id: str):
    return operation(lambda: request.app.state.source_library.reuse(project_id, entry_id, principal(request, project_id)))
