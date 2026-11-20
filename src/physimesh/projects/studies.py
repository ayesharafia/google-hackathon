"""Immutable local analysis records, explicitly separate from approved publications."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import scipy

from physimesh.drone.capacity import capacity_from_snapshot
from physimesh.drone.local_results import LocalCapacityV2, LocalCapacityV3
from physimesh.drone.provenance import canonical_json, sha256_record
from physimesh.drone.trim import MODEL_VERSION

from .contracts import parse_snapshot
from .performance import load_map


def model_identity() -> dict:
    root = Path(__file__).parents[1]
    files = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(root.rglob('*.py'))}
    return {'model_version': MODEL_VERSION, 'source_fingerprint_sha256': sha256_record(files),
            'numpy_version': np.__version__, 'scipy_version': scipy.__version__,
            'qualification': 'Local source fingerprint and library versions; not an immutable deployed build.'}


class LocalStudies:
    def __init__(self, projects):
        self.projects = projects
        # Bind source state at application construction, not after a later edit.
        self.model_identity = model_identity()

    def run(self, project_id: str, revision_sha256: str) -> dict:
        revision = self.projects.repository.revision(project_id, revision_sha256)
        snapshot = parse_snapshot(revision.snapshot_json)
        refs = {rotor.get('map_ref') for rotor in snapshot['rotors'] if rotor.get('map_ref')}
        sources = {}
        source_errors = []
        for digest in sorted(refs):
            try:
                sources[digest] = load_map(self.projects.artifacts, digest)
            except (KeyError, ValueError, TypeError) as exc:
                source_errors.append(str(exc))
        spec = {'project_id': project_id, 'revision_sha256': revision_sha256,
                'snapshot_sha256': revision.snapshot_sha256, 'model': self.model_identity,
                'performance_source_sha256': sorted(refs), 'engineering_approval': 'pending'}
        spec['result_schema_version'] = 'local_mission_capacity_v3'
        study = sha256_record(spec)
        if source_errors:
            raise ValueError('retained performance source unavailable or corrupt: ' + '; '.join(source_errors))
        result = {**capacity_from_snapshot(snapshot, sources), 'study_sha256': study, 'specification': spec}
        raw = canonical_json(result).encode()
        LocalCapacityV3.model_validate_json(raw)
        digest = self.projects.artifacts.put_bytes(raw, kind='local_mission_capacity_v3', meta={'study_sha256': study})
        accepted = self.projects.repository.retain_study(project_id, revision_sha256, study, digest)
        return json.loads(self._bytes(accepted))

    def _bytes(self, digest: str) -> bytes:
        with self.projects.artifacts.open(digest) as stream:
            raw = stream.read(5_000_001)
        if len(raw) > 5_000_000 or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('retained study byte integrity failed')
        return raw

    def export(self, project_id: str, study: str) -> bytes:
        digest = self.projects.repository.study_digest(project_id, study)
        raw = self._bytes(digest)
        data = json.loads(raw)
        if data.get('schema_version') == 'local_mission_capacity_v3':
            LocalCapacityV3.model_validate_json(raw)
        elif data.get('schema_version') == 'local_mission_capacity_v2':
            LocalCapacityV2.model_validate_json(raw)
        elif data.get('schema_version') != 'local_hover_capacity_v1':
            raise ValueError('unsupported retained local result schema')
        if data['study_sha256'] != study or data['specification']['project_id'] != project_id:
            raise ValueError('retained study association failed')
        return raw

    def read(self, project_id: str, study: str) -> dict:
        return json.loads(self.export(project_id, study))

    def report_inputs(self, project_id: str, study: str) -> tuple[bytes, str]:
        raw = self.export(project_id, study)
        spec = json.loads(raw)['specification']
        revision = self.projects.repository.revision(project_id, spec['revision_sha256'])
        if revision.snapshot_sha256 != spec['snapshot_sha256']:
            raise ValueError('study frozen input association failed')
        return raw, revision.snapshot_json

    def pdf(self, project_id: str, study: str) -> tuple[bytes, dict]:
        from .reports import render_pdf, report_identity
        raw, snapshot = self.report_inputs(project_id, study)
        receipt = report_identity(raw, snapshot)
        pdf = render_pdf(raw, snapshot)
        digest = self.projects.artifacts.put_bytes(pdf, kind='retained_local_study_pdf_v1', meta=receipt)
        if self._bytes(digest) != pdf:
            raise ValueError('retained PDF integrity failed')
        return pdf, {**receipt, 'pdf_sha256': digest}

    def compare(self, project_id: str, before: str, after: str) -> dict:
        from .reports import compare_records
        before_raw, before_snapshot = self.report_inputs(project_id, before)
        after_raw, after_snapshot = self.report_inputs(project_id, after)
        return compare_records(json.loads(before_raw), json.loads(after_raw),
                               json.loads(before_snapshot), json.loads(after_snapshot))
