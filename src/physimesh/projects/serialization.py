"""Explicit version dispatch and legacy intake; no in-place package migrations."""
import hashlib
import json

from physimesh.drone.provenance import canonical_json
from physimesh.postpro.publication import PublicationIdentityV1
from physimesh.postpro.result_contract import ResultsV1

from .contracts import (
    AircraftStudyV2,
    DesignRevisionV1,
    MissionDefinitionV1,
    ProjectDraftV1,
    ReviewAttestationV1,
    StudySpecV1,
    _constant,
    _pairs,
    snapshot_json,
)

CONTRACTS = {
    'results_v1': ResultsV1,
    'publication_identity_v1': PublicationIdentityV1,
    'project_draft_v1': ProjectDraftV1,
    'design_revision_v1': DesignRevisionV1,
    'mission_definition_v1': MissionDefinitionV1,
    'aircraft_study_spec_v1': StudySpecV1,
    'aircraft_study_v2': AircraftStudyV2,
    'review_attestation_v1': ReviewAttestationV1,
}


def load_contract(raw: bytes):
    data = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    if not isinstance(data, dict) or data.get('schema_version') not in CONTRACTS:
        raise ValueError('unknown contract schema_version')
    return CONTRACTS[data['schema_version']].model_validate_json(canonical_json(data))


def dump_contract(record) -> bytes:
    version = record.model_dump(mode='json')['schema_version']
    if version not in CONTRACTS or not isinstance(record, CONTRACTS[version]):
        raise ValueError('unregistered contract type')
    # Validate again: model_copy(update=...) is not a validation boundary.
    data = record.model_dump(mode='json')
    checked = load_contract(canonical_json(data).encode('utf-8'))
    return canonical_json(checked.model_dump(mode='json')).encode('utf-8')


def import_legacy_manifest(raw: bytes, *, organization_id: str, project_id: str,
                           payload_interpretation: str | None = None) -> ProjectDraftV1:
    if payload_interpretation != 'installed_mass':
        raise ValueError('confirm installed payload mass before legacy migration; historical targets need corrected data')
    data = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    return ProjectDraftV1(organization_id=organization_id, project_id=project_id,
                          draft_version=0, expected_version=0, snapshot_json=snapshot_json(data),
                          legacy_source_sha256=hashlib.sha256(raw).hexdigest(), payload_interpretation='installed_mass')
