"""Resolve saved geometry from immutable import records and original STL bytes."""
from __future__ import annotations

import hashlib
import json

from physimesh.core.artifacts import ArtifactStore
from physimesh.drone.provenance import canonical_json


def source_bytes(store: ArtifactStore, digest: str) -> bytes:
    """Refuse missing or changed bytes instead of rendering a different surface."""
    try:
        with store.open(digest) as stream:
            raw = stream.read()
    except (KeyError, ValueError, OSError) as exc:
        raise ValueError('geometry artifact is not retained') from exc
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('geometry artifact byte integrity failed')
    return raw


def _record(store: ArtifactStore, digest: str) -> dict:
    raw = source_bytes(store, digest)
    try:
        value = json.loads(raw)
        if not isinstance(value, dict) or canonical_json(value).encode() != raw:
            raise ValueError('noncanonical record')
    except (ValueError, UnicodeError) as exc:
        raise ValueError('invalid retained geometry record') from exc
    return value


def geometry_report(store: ArtifactStore, snapshot: dict, *, verify_sources: bool = False) -> dict | None:
    """Bind filenames, byte references, source units and transform to one import.

    Component role/rotor tagging may evolve independently in the draft. Earlier
    snapshots without a workbench import record remain readable and freezable.
    """
    assembly = snapshot['assembly']
    digest = assembly.get('geometry_import_sha256')
    if digest is None:
        return None
    report = _record(store, digest)
    try:
        if report['schema_version'] != 'geometry_import_report_v1':
            raise ValueError('unsupported geometry import record')
        components = report['components']
        transform = {key: report['transform'][key]
                     for key in ('scale', 'rotation_deg_zyx', 'translation_m')}
        expected = {'original_sha256': [c['source_sha256'] for c in components],
                    'source_units': report['conversion']['from'], 'transform': transform,
                    'schema': 'geometry_import_v1'}
        if _record(store, report['geometry_revision_sha256']) != expected:
            raise ValueError('geometry import differs from its retained revision')
        identity = lambda c: (c['component_id'], c['source_sha256'], c['filename'])
        if (assembly.get('geometry_revision_sha256') != report['geometry_revision_sha256']
                or [identity(c) for c in assembly.get('components', [])] != [identity(c) for c in components]):
            raise ValueError('project geometry differs from its retained import')
        units = snapshot['units_and_frames']
        if units.get('source_units') != expected['source_units'] or units.get('cad_transform') != transform:
            raise ValueError('geometry units or transform differ from the retained import; upload again to change them')
        if verify_sources:
            for component in components:
                source_bytes(store, component['source_sha256'])
    except (KeyError, TypeError) as exc:
        raise ValueError('invalid saved geometry binding') from exc
    return {**report, 'report_sha256': digest}
