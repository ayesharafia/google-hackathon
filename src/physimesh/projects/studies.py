"""Immutable local analysis records, explicitly separate from approved publications."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import scipy

from physimesh.drone.capacity import capacity_from_snapshot
from physimesh.drone.local_results import LocalCapacityV2, LocalCapacityV3, LocalCapacityV4
from physimesh.drone.provenance import canonical_json, sha256_record
from physimesh.drone.trim import EXTENDED_MODEL_VERSION, MODEL_VERSION

from .contracts import parse_snapshot
from .performance import load_map, performance_refs
from .repository import ProjectMissing

MODEL_MODULES = (
    'drone/performance.py', 'drone/conditioning.py', 'drone/trim.py', 'drone/capacity.py',
    'drone/mission_capacity.py', 'drone/scenarios.py', 'drone/authoring.py', 'drone/atmosphere.py', 'drone/mass.py',
    'drone/screening_scope.py', 'drone/models.py', 'drone/frames.py', 'drone/units.py',
    'drone/provenance.py', 'drone/snapshot_hash.py', 'drone/local_results.py',
    'projects/contracts.py', 'projects/performance.py',
)


def model_identity(root: Path | None = None) -> dict:
    root = root or Path(__file__).parents[1]
    files = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in MODEL_MODULES}
    fingerprint = {'policy': 'semantic_model_identity_v1', 'modules': files}
    return {'model_version': MODEL_VERSION, 'source_fingerprint_sha256': sha256_record(fingerprint),
            'fingerprint_policy': 'semantic_model_identity_v1', 'model_module_sha256': files,
            'numpy_version': np.__version__, 'scipy_version': scipy.__version__,
            'qualification': 'Explicit numerical-model dependency closure and library versions; '
                             'historical full-tree identities remain historical. Not an immutable deployed build.'}


class LocalStudies:
    def __init__(self, projects):
        self.projects = projects
        # Bind source state at application construction, not after a later edit.
        self.model_identity = model_identity()

    def prepare(self, project_id: str, revision_sha256: str):
        revision = self.projects.repository.revision(project_id, revision_sha256)
        snapshot = parse_snapshot(revision.snapshot_json)
        refs = performance_refs(snapshot)
        sources = {}
        source_errors = []
        for digest in sorted(refs):
            try:
                sources[digest] = load_map(self.projects.artifacts, digest)
            except (KeyError, ValueError, TypeError) as exc:
                source_errors.append(str(exc))
        extended = snapshot['fidelity'].get('local_pilot', {}).get('model_version') == EXTENDED_MODEL_VERSION
        schema = 'local_mission_capacity_v4' if extended else 'local_mission_capacity_v3'
        identity = {**self.model_identity, 'model_version': EXTENDED_MODEL_VERSION if extended else MODEL_VERSION}
        spec = {'project_id': project_id, 'revision_sha256': revision_sha256,
                'snapshot_sha256': revision.snapshot_sha256, 'model': identity,
                'performance_source_sha256': sorted(refs), 'engineering_approval': 'pending'}
        spec['result_schema_version'] = schema
        study = sha256_record(spec)
        if source_errors:
            raise ValueError('retained performance source unavailable or corrupt: ' + '; '.join(source_errors))
        return snapshot, sources, spec, study, extended

    def evaluate(self, project_id: str, revision_sha256: str) -> dict:
        """Compute an attempt without publishing any result or association."""
        snapshot, sources, spec, study, extended = self.prepare(project_id, revision_sha256)
        try:
            accepted = self.read(project_id, study)
        except ProjectMissing:
            accepted = None
        if accepted is not None:
            if accepted['specification'] != spec:
                raise ValueError('retained study specification integrity failed')
            return accepted
        result = {**capacity_from_snapshot(snapshot, sources), 'study_sha256': study, 'specification': spec}
        (LocalCapacityV4 if extended else LocalCapacityV3).model_validate_json(canonical_json(result))
        return result

    def run(self, project_id: str, revision_sha256: str) -> dict:
        snapshot, sources, spec, study, extended = self.prepare(project_id, revision_sha256)
        try:
            retained = self.read(project_id, study)
        except ProjectMissing:
            retained = None
        if retained is not None:
            if retained['specification'] != spec:
                raise ValueError('retained study specification integrity failed')
            return retained
        result = {**capacity_from_snapshot(snapshot, sources), 'study_sha256': study, 'specification': spec}
        raw = canonical_json(result).encode()
        schema = spec['result_schema_version']
        (LocalCapacityV4 if extended else LocalCapacityV3).model_validate_json(raw)
        digest = self.projects.artifacts.put_bytes(raw, kind=schema, meta={'study_sha256': study})
        self.projects.repository.retain_study(project_id, revision_sha256, study, digest)
        return self.read(project_id, study)

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
        if data.get('schema_version') == 'local_mission_capacity_v4':
            LocalCapacityV4.model_validate_json(raw)
        elif data.get('schema_version') == 'local_mission_capacity_v3':
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

    def cached_pdf(self, project_id: str, study: str) -> tuple[bytes, dict] | None:
        from .reports import report_identity
        raw, snapshot = self.report_inputs(project_id, study)
        receipt = report_identity(raw, snapshot)
        stored = self.projects.repository.report_receipt(sha256_record(receipt))
        if stored is None:
            return None
        retained_receipt = json.loads(stored['receipt'])
        receipt_digest = retained_receipt.pop('receipt_sha256', None)
        if retained_receipt != receipt or receipt_digest is None:
            raise ValueError('retained PDF receipt integrity failed')
        digest = stored['pdf_sha256']
        receipt_raw = self._bytes(receipt_digest)
        if json.loads(receipt_raw) != {**receipt, 'pdf_sha256': digest}:
            raise ValueError('retained PDF receipt artifact association failed')
        pdf = self._bytes(digest)
        if not pdf.startswith(b'%PDF-'):
            raise ValueError('retained PDF integrity failed')
        return pdf, {**receipt, 'pdf_sha256': digest}

    def retain_pdf(self, project_id, study, pdf, receipt):
        from .reports import report_identity
        raw, snapshot = self.report_inputs(project_id, study)
        if receipt != report_identity(raw, snapshot) or not pdf.startswith(b'%PDF-'):
            raise ValueError('PDF frozen input/renderer identity failed')
        digest = self.projects.artifacts.put_bytes(pdf, kind='retained_local_study_pdf_v1', meta=receipt)
        if self._bytes(digest) != pdf:
            raise ValueError('retained PDF integrity failed')
        receipt_digest = self.projects.artifacts.put_bytes(
            canonical_json({**receipt, 'pdf_sha256': digest}).encode(), kind='verified_report_receipt_v2', meta={})
        self.projects.repository.retain_report(sha256_record(receipt), digest, {**receipt, 'receipt_sha256': receipt_digest})
        return self.cached_pdf(project_id, study)

    def pdf(self, project_id: str, study: str) -> tuple[bytes, dict]:
        from .reports import render_pdf, report_identity
        cached = self.cached_pdf(project_id, study)
        if cached is not None:
            return cached
        raw, snapshot = self.report_inputs(project_id, study)
        return self.retain_pdf(project_id, study, render_pdf(raw, snapshot), report_identity(raw, snapshot))

    def compare(self, project_id: str, before: str, after: str) -> dict:
        from .reports import compare_records
        before_raw, before_snapshot = self.report_inputs(project_id, before)
        after_raw, after_snapshot = self.report_inputs(project_id, after)
        return compare_records(json.loads(before_raw), json.loads(after_raw),
                               json.loads(before_snapshot), json.loads(after_snapshot))
