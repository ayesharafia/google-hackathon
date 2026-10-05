"""Local project services; frozen design never implies human or physics approval."""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from physimesh.core.artifacts import ArtifactStore
from physimesh.drone import models
from physimesh.drone.snapshot_hash import snapshot_sha256

from .contracts import DesignRevisionV1, Reason, parse_snapshot, snapshot_json
from .repository import DraftConflict, ProjectRepository
from .sqlite import canonical_snapshot, utc_now


class ProjectService:
    def __init__(self, repository: ProjectRepository, artifacts: ArtifactStore):
        self.repository = repository
        self.artifacts = artifacts

    def create(self, title: str) -> dict:
        template = Path(models.__file__).with_name('schema') / 'drone_manifest_v1.yaml'
        snapshot = yaml.safe_load(template.read_text())
        snapshot['identity']['description'] = title.strip()
        return self.repository.create(title, snapshot_json(snapshot))

    def save(self, project_id: str, expected_version: int, raw: str) -> dict:
        return self.repository.save(project_id, expected_version, canonical_snapshot(raw))

    def freeze(self, project_id: str, expected_version: int, purpose: str) -> dict:
        project = self.repository.get(project_id)
        if project['draft_version'] != expected_version:
            raise DraftConflict(project['draft_version'])
        snapshot = parse_snapshot(project['snapshot_json'])
        from .performance import load_map, performance_refs
        for digest in performance_refs(snapshot):
            try:
                load_map(self.artifacts, digest)
            except KeyError as exc:
                raise ValueError('rotor-map source is not retained') from exc
        # Imported geometry references are byte identities, not inferred source claims.
        for component in snapshot['assembly'].get('components', []):
            digest = component.get('source_sha256')
            if digest:
                try:
                    with self.artifacts.open(digest) as stream:
                        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
                except KeyError as exc:
                    raise ValueError('geometry source is not retained') from exc
                if actual != digest:
                    raise ValueError('geometry source byte integrity failed')
        report = models.readiness(models.project_from_mapping(snapshot), purpose)
        revision = DesignRevisionV1(
            organization_id='local', project_id=project_id, snapshot_json=project['snapshot_json'],
            snapshot_sha256=snapshot_sha256(snapshot), author_identity_id='local_operator',
            created_utc=utc_now(), readiness_purpose=purpose,
            readiness_reasons=tuple(Reason(code='missing_input', field_path='readiness', message=text)
                                    for text in report.blocking), approval='draft')
        return self.repository.freeze(project_id, expected_version, revision)
