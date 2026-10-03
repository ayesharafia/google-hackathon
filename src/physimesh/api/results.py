"""Authenticated local results and export from the same immutable package."""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import ValidationError

from physimesh.core.jobs import JobLedger
from physimesh.postpro.publication import identity_bytes, publication_identity, validate_identity
from physimesh.postpro.result_contract import ResultsV1

router = APIRouter(prefix='/api/drone')
_GROUP = re.compile(r'[0-9a-f]{16}')
_FILE = re.compile(r'(slice_eligibility\.json|publication\.json|results\.json|run_group\.json|plots/[a-z0-9_]+\.png|recipes/[a-z0-9_]+\.json|surfaces/[a-z0-9_]+\.json)')


def _package(request, group_id):
    if not _GROUP.fullmatch(group_id):
        raise HTTPException(404, 'unknown results group')
    root = request.app.state.settings.data_root/'results'
    path = root/group_id
    if not path.is_dir():
        raise HTTPException(404, 'unknown results group')
    if not path.resolve().is_relative_to(root.resolve()):
        raise HTTPException(409, 'package escapes configured results root')
    return path


def _manifest(package):
    try:
        value = json.loads((package/'hashes.json').read_text())
        if (not isinstance(value, dict) or not value or
                any(not _FILE.fullmatch(name) or re.fullmatch(r'[0-9a-f]{64}', digest) is None
                    for name, digest in value.items())):
            raise ValueError('invalid hash manifest')
        return value
    except (OSError, TypeError, ValueError) as exc:
        raise HTTPException(409, 'invalid retained package manifest') from exc


def _read(package: Path, name: str, manifest: dict):
    if name not in manifest or not _FILE.fullmatch(name):
        raise HTTPException(404, 'artifact absent from retained package')
    target = package/name
    try:
        if not target.resolve().is_relative_to(package.resolve()):
            raise ValueError('artifact escapes package')
        raw = target.read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest[name]:
            raise ValueError('artifact hash differs')
        return raw
    except (OSError, ValueError) as exc:
        raise HTTPException(409, 'retained artifact is missing or has changed') from exc


def _result(package, manifest):
    try:
        result = ResultsV1.model_validate_json(_read(package, 'results.json', manifest)).model_dump(mode='json')
        if result['run_group_id'] != package.name:
            raise ValueError('result group does not match package')
        return result
    except (ValidationError, ValueError) as exc:
        raise HTTPException(409, 'retained results contract is invalid') from exc


@router.get('/results')
def inventory(request: Request):
    root = request.app.state.settings.data_root/'results'
    groups = []
    if root.exists():
        for package in sorted(root.iterdir()):
            if package.is_dir() and _GROUP.fullmatch(package.name):
                package = _package(request, package.name)
                result = _result(package, _manifest(package))
                groups.append({key: result[key] for key in ('run_group_id', 'label', 'status', 'evidence')})
    return {'groups': groups}


@router.get('/results/{group_id}')
def results(request: Request, group_id: str):
    package = _package(request, group_id)
    return _result(package, _manifest(package))


@router.get('/plots/{group_id}/{plot_id}.png')
def plot(request: Request, group_id: str, plot_id: str):
    if re.fullmatch(r'[a-z0-9_]+', plot_id) is None:
        raise HTTPException(404, 'unknown plot')
    package = _package(request, group_id)
    raw = _read(package, f'plots/{plot_id}.png', _manifest(package))
    return Response(raw, media_type='image/png', headers={'Cache-Control': 'private, no-cache'})


def _publication(package, manifest, result):
    # Verify all payload bytes before exposing a content identity, including
    # legacy packages that predate the envelope. Never rewrite their files.
    for name in manifest:
        _read(package, name, manifest)
    try:
        identity = publication_identity(manifest, result['provenance']['run_group_sha256'])
        if 'publication.json' in manifest:
            validate_identity(_read(package, 'publication.json', manifest), identity)
        return identity
    except (ValueError, TypeError) as exc:
        raise HTTPException(409, 'publication identity differs from retained content') from exc


@router.get('/results/{group_id}/publication')
def publication(request: Request, group_id: str):
    package = _package(request, group_id)
    manifest = _manifest(package)
    result = _result(package, manifest)
    return {'identity': _publication(package, manifest, result).model_dump(mode='json'),
            'origin': 'retained_envelope' if 'publication.json' in manifest else 'derived_legacy',
            'qualification': 'Content identity only; evidence and independent review remain separate.'}


@router.get('/runs/{run_id}')
def run(request: Request, run_id: str):
    if _GROUP.fullmatch(run_id):
        package = _package(request, run_id)
        result = _result(package, _manifest(package))
        return {key: result[key] for key in ('run_group_id', 'status', 'evidence', 'provenance', 'runs')}
    settings = request.app.state.settings
    if re.fullmatch(r'[0-9a-f]{32}', run_id) is None or not settings.db_path.is_file():
        raise HTTPException(404, 'unknown run')
    ledger = JobLedger(settings.db_path)
    try:
        job = ledger.get(run_id)
        events = [json.loads(row[0]) for row in ledger.db.execute('SELECT event FROM events WHERE job_id=?', (run_id,))]
        return {**asdict(job), 'events': events, 'evidence': 'unverified'}
    except KeyError as exc:
        raise HTTPException(404, 'unknown run') from exc
    finally:
        ledger.db.close()


@router.get('/runs/{group_id}/export')
def export(request: Request, group_id: str):
    package = _package(request, group_id)
    manifest = _manifest(package)
    result = _result(package, manifest)  # refuse schema/status corruption before export
    identity = _publication(package, manifest, result)
    files = {name: _read(package, name, manifest) for name in manifest}
    files['publication.json'] = identity_bytes(identity)
    manifest = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    files['hashes.json'] = (json.dumps(manifest, indent=2, sort_keys=True)+'\n').encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    return Response(stream.getvalue(), media_type='application/zip',
                    headers={'Content-Disposition': f'attachment; filename="sphere-{group_id}-{identity.package_revision_sha256}.zip"'})


@router.get('/surfaces/{group_id}/{surface_id}.json')
def surface(request: Request, group_id: str, surface_id: str):
    if re.fullmatch(r'[a-z0-9_]+', surface_id) is None:
        raise HTTPException(404, 'unknown surface')
    package = _package(request, group_id)
    return Response(_read(package, f'surfaces/{surface_id}.json', _manifest(package)), media_type='application/json')
