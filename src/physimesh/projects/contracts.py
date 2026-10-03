"""P01.1 wire contracts. Schema consistency never authenticates an approver.

Immutable records retain canonical JSON strings for extensible legacy snapshots,
so nested mutable dictionaries cannot alter an approved revision after creation.
No solver, feasibility search, persistence or identity-provider behavior is implied.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from physimesh.drone.models import project_from_mapping, readiness
from physimesh.drone.provenance import canonical_json, sha256_record
from physimesh.drone.snapshot_hash import snapshot_sha256
from physimesh.postpro.publication import PublicationIdentityV1

Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Identifier = Annotated[str, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')]
Nonnegative = Annotated[float, Field(ge=0)]
Outcome = Literal['feasible', 'infeasible', 'unresolved', 'unsupported', 'not_evaluated']
AircraftStatus = Literal['inputs_incomplete', 'screening_only', 'numerically_unverified',
                         'validation_pending', 'within_validated_envelope', 'requirement_not_met']


def _utc(value: str) -> str:
    datetime.strptime(value, '%Y-%m-%dT%H:%M:%S%z')
    return value


UTCTimestamp = Annotated[str, Field(pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$'), AfterValidator(_utc)]


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False, strict=True)


class ResourceRef(Record):
    """Asset byte hashes and immutable revision hashes are separately named."""
    kind: Literal['organization', 'identity', 'membership', 'project', 'geometry_asset',
                  'component_instance', 'rotor_configuration', 'performance_dataset',
                  'mass_ledger', 'mission', 'study', 'job_attempt', 'artifact_manifest',
                  'result_revision', 'review', 'client_grant']
    resource_id: Identifier
    revision_sha256: Digest | None = None
    bytes_sha256: Digest | None = None


class Reason(Record):
    code: Literal['missing_input', 'invalid_input', 'inconsistent_input', 'limit_exceeded',
                  'unsupported_domain', 'search_unresolved', 'case_not_evaluated',
                  'stale_binding', 'validation_not_established']
    field_path: str = Field(min_length=1, max_length=300)
    message: str = Field(min_length=1, max_length=2000)
    source_sha256: Digest | None = None


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f'nonfinite JSON constant {value}')


def parse_snapshot(raw: str) -> dict:
    data = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    project_from_mapping(data)
    snapshot_sha256(data)  # Browser-exact numeric bounds, preserving null/bool.
    if canonical_json(data) != raw:
        raise ValueError('snapshot_json must use canonical UTF-8 JSON serialization')
    return data


def _plain(value):
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError('JSON object keys must be strings')
        return {key: _plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(child) for child in value]
    return value


def snapshot_json(data: Mapping) -> str:
    text = canonical_json(_plain(data))
    parse_snapshot(text)
    return text


class ProjectDraftV1(Record):
    schema_version: Literal['project_draft_v1'] = 'project_draft_v1'
    organization_id: Identifier
    project_id: Identifier
    draft_version: int = Field(ge=0)
    expected_version: int = Field(ge=0)
    snapshot_json: str
    legacy_source_sha256: Digest | None = None
    payload_interpretation: Literal['installed_mass'] | None = None

    @model_validator(mode='after')
    def content(self):
        parse_snapshot(self.snapshot_json)
        if self.legacy_source_sha256 is not None and self.payload_interpretation is None:
            raise ValueError('legacy import requires an explicit installed-mass interpretation')
        return self


class DesignRevisionV1(Record):
    schema_version: Literal['design_revision_v1'] = 'design_revision_v1'
    organization_id: Identifier
    project_id: Identifier
    snapshot_json: str
    snapshot_sha256: Digest
    author_identity_id: Identifier
    created_utc: UTCTimestamp
    readiness_purpose: Literal['screening', 'cfd_run', 'feasibility']
    readiness_reasons: tuple[Reason, ...] = ()
    approval: Literal['draft', 'approval_pending', 'approved'] = 'draft'
    approval_attestation_sha256: Digest | None = None

    @model_validator(mode='after')
    def binding(self):
        data = parse_snapshot(self.snapshot_json)
        if snapshot_sha256(data) != self.snapshot_sha256:
            raise ValueError('design snapshot digest differs')
        if self.approval == 'approved' and (self.readiness_reasons or self.approval_attestation_sha256 is None):
            raise ValueError('approved revision requires complete readiness and detached attestation reference')
        if self.approval == 'approved' and not readiness(project_from_mapping(data), self.readiness_purpose).ready:
            raise ValueError('approved revision has incomplete method-specific inputs')
        if self.approval == 'approved':
            bound_mission(data)
        return self

    def revision_sha256(self) -> str:
        return sha256_record(self.model_dump(mode='json'))


class MissionCaseV1(Record):
    case_id: Identifier
    required: bool = True
    conditions_sha256: Digest


class MissionSegmentV1(Record):
    segment_id: Identifier
    case_id: Identifier
    duration_s: Annotated[float, Field(gt=0)]
    approximation: Literal['constant_point', 'quasi_steady_discretized', 'trajectory_model']
    model_sha256: Digest


class MissionDefinitionV1(Record):
    schema_version: Literal['mission_definition_v1'] = 'mission_definition_v1'
    cases: tuple[MissionCaseV1, ...] = Field(min_length=1)
    sequence: tuple[MissionSegmentV1, ...] = ()
    reserve_convention: Literal['held_usable_energy_fraction', 'held_energy_j', 'additional_mission_demand']
    reserve_value: Nonnegative
    pack_mode: Literal['fixed', 'sized']

    @model_validator(mode='after')
    def associations(self):
        names = [case.case_id for case in self.cases]
        segments = [segment.segment_id for segment in self.sequence]
        if len(set(names)) != len(names) or len(set(segments)) != len(segments):
            raise ValueError('duplicate case or segment identity')
        if not any(case.required for case in self.cases):
            raise ValueError('at least one required case')
        if any(segment.case_id not in names for segment in self.sequence):
            raise ValueError('sequence segment refers to unknown case')
        if self.reserve_convention == 'held_usable_energy_fraction' and self.reserve_value >= 1:
            raise ValueError('held usable-energy fraction must be below one')
        return self

    def revision_sha256(self) -> str:
        return sha256_record(self.model_dump(mode='json'))


def bound_mission(snapshot: dict) -> MissionDefinitionV1:
    """Resolve the typed mission INSIDE the approved physical snapshot.

    Conditions use the existing versioned SI numeric scheme. The typed mission
    binds sequence/required flags, while explicit legacy reserve/pack declarations
    must agree, preventing two contradictory views of the approved inputs.
    """
    raw = snapshot['mission']
    declaration = raw.get('contract_definition')
    if declaration is None:
        raise ValueError('approved revision requires an explicit typed mission declaration')
    mission = MissionDefinitionV1.model_validate_json(canonical_json(declaration))
    actual = raw.get('cases', [])
    if not isinstance(actual, list) or any(not isinstance(case, dict) for case in actual):
        raise ValueError('approved operating conditions must be a list of records')
    if any(not isinstance(case.get('name'), str) for case in actual):
        raise ValueError('approved operating conditions require named case identities')
    by_name = {case.get('name'): case for case in actual}
    if len(by_name) != len(actual) or set(by_name) != {case.case_id for case in mission.cases}:
        raise ValueError('typed mission cases differ from approved operating conditions')
    for case in mission.cases:
        condition = by_name[case.case_id]
        if case.conditions_sha256 != snapshot_sha256(condition) or case.required is not condition.get('required', True):
            raise ValueError('typed mission condition digest or required flag differs from approved snapshot')
    reserve = raw.get('reserve_policy', {})
    energy = raw.get('energy_system', {})
    if not isinstance(reserve, dict) or not isinstance(energy, dict):
        raise ValueError('explicit reserve and energy records required')  # noqa: TRY004 - Pydantic validation boundary
    if (reserve.get('convention') != mission.reserve_convention or reserve.get('value') != mission.reserve_value
            or energy.get('pack_mode') != mission.pack_mode):
        raise ValueError('typed mission reserve or pack mode differs from approved snapshot')
    return mission


class StudySpecV1(Record):
    schema_version: Literal['aircraft_study_spec_v1'] = 'aircraft_study_spec_v1'
    organization_id: Identifier
    project_id: Identifier
    design_revision_sha256: Digest
    mission: MissionDefinitionV1
    method: Literal['supplied_point_screening', 'measured_map_trim', 'bem', 'cfd']
    method_version: Identifier
    model_source_sha256: tuple[Digest, ...] = Field(min_length=1)
    settings_sha256: Digest
    code_commit: str = Field(pattern=r'^[0-9a-f]{40}$')
    backend_image_digest: str | None = Field(default=None, pattern=r'^[^\s@]+@sha256:[0-9a-f]{64}$')

    @model_validator(mode='after')
    def backend(self):
        if self.method == 'cfd' and self.backend_image_digest is None:
            raise ValueError('CFD study requires exact backend digest')
        if len(set(self.model_source_sha256)) != len(self.model_source_sha256):
            raise ValueError('duplicate model source')
        return self

    def study_sha256(self) -> str:
        return sha256_record(self.model_dump(mode='json'))

    def assert_design_binding(self, revision: DesignRevisionV1) -> None:
        purpose = 'cfd_run' if self.method == 'cfd' else 'screening' if self.method == 'supplied_point_screening' else 'feasibility'
        if ((self.organization_id, self.project_id) != (revision.organization_id, revision.project_id)
                or self.design_revision_sha256 != revision.revision_sha256()
                or revision.approval != 'approved' or revision.readiness_purpose != purpose):
            raise ValueError('study does not bind an approved same-project revision with applicable readiness')
        if self.mission != bound_mission(parse_snapshot(revision.snapshot_json)):
            raise ValueError('study mission differs from approved design revision')


class CaseResultV2(Record):
    case_id: Identifier
    outcome: Outcome
    feasible_payload_lower_bound_kg: Nonnegative | None = None
    explored_upper_bound_kg: Nonnegative | None = None
    search_tolerance_kg: Annotated[float, Field(gt=0)] | None = None
    force_residual_n: Nonnegative | None = None
    moment_residual_nm: Nonnegative | None = None
    reasons: tuple[Reason, ...] = ()

    @model_validator(mode='after')
    def outcome_fields(self):
        if self.outcome != 'feasible' and self.feasible_payload_lower_bound_kg is not None:
            raise ValueError('nonfeasible case cannot present a feasible payload')
        if self.outcome != 'feasible' and not self.reasons:
            raise ValueError('nonfeasible case requires structured reasons')
        if self.outcome == 'feasible' and self.feasible_payload_lower_bound_kg is None:
            raise ValueError('feasible case requires verified lower bound')
        if (self.feasible_payload_lower_bound_kg is not None and self.explored_upper_bound_kg is not None
                and self.explored_upper_bound_kg < self.feasible_payload_lower_bound_kg):
            raise ValueError('explored upper bound below feasible lower bound')
        return self


class AircraftStudyV2(Record):
    schema_version: Literal['aircraft_study_v2'] = 'aircraft_study_v2'
    spec: StudySpecV1
    execution: Literal['queued', 'preparing', 'meshing', 'running', 'postprocessing',
                       'completed', 'cancelled', 'failed']
    physical_outcome: Outcome
    aircraft_status: AircraftStatus
    evidence: Literal['unverified', 'iteration_converged', 'periodic_or_statistical_converged',
                      'mesh_assessed', 'time_assessed', 'validated_for_case_family']
    validation_envelope_sha256: Digest | None = None
    publication_state: Literal['private_staging', 'published', 'withdrawn'] = 'private_staging'
    publication: PublicationIdentityV1 | None = None
    cases: tuple[CaseResultV2, ...] = ()
    payload_lower_bound_kg: Nonnegative | None = None
    limiting_case_id: Identifier | None = None
    sequence_energy_evidence_sha256: Digest | None = None
    reasons: tuple[Reason, ...] = ()

    @model_validator(mode='after')
    def consistency(self):
        names = [case.case_id for case in self.cases]
        declared = {case.case_id: case for case in self.spec.mission.cases}
        if len(set(names)) != len(names) or any(name not in declared for name in names):
            raise ValueError('duplicate or undeclared result case')
        required = {name for name, case in declared.items() if case.required}
        by_name = {case.case_id: case for case in self.cases}
        if self.publication is not None and (self.publication.study_sha256 != self.spec.study_sha256()
                                            or self.publication.study_id != self.spec.study_sha256()[:16]):
            raise ValueError('publication bound to a different study')
        if self.publication_state == 'published' and (self.publication is None or self.execution != 'completed'):
            raise ValueError('published aircraft result requires complete execution and content identity')
        if self.publication_state == 'withdrawn' and self.publication is None:
            raise ValueError('withdrawn result requires retained publication identity')
        if self.evidence == 'validated_for_case_family' and self.validation_envelope_sha256 is None:
            raise ValueError('validated evidence requires scoped validation envelope')
        if self.aircraft_status == 'within_validated_envelope' and self.evidence != 'validated_for_case_family':
            raise ValueError('validated aircraft status requires validated evidence')
        if self.execution != 'completed' and self.evidence != 'unverified':
            raise ValueError('uncompleted execution cannot claim achieved numerical or validation evidence')
        if self.spec.method == 'supplied_point_screening' and self.evidence != 'unverified':
            raise ValueError('supplied-point screening cannot establish numerical or validated aircraft evidence')
        if self.physical_outcome == 'not_evaluated' and (
                self.aircraft_status != 'inputs_incomplete' or self.evidence != 'unverified'):
            raise ValueError('unevaluated study must retain incomplete status and unverified evidence')
        if self.physical_outcome == 'feasible':
            if self.execution != 'completed' or not required <= by_name.keys():
                raise ValueError('feasible result requires all required cases and complete execution')
            if any(by_name[name].outcome != 'feasible' for name in required):
                raise ValueError('required case is not feasible')
            if self.spec.mission.sequence and self.sequence_energy_evidence_sha256 is None:
                raise ValueError('chronological mission needs separate sequence energy evidence')
            allowed = ('screening_only',) if self.spec.method == 'supplied_point_screening' else (
                'validation_pending', 'within_validated_envelope')
            if self.aircraft_status not in allowed:
                raise ValueError('feasible status must match the declared method and validation scope')
        if self.physical_outcome in ('unsupported', 'unresolved', 'infeasible') and not self.reasons:
            raise ValueError('nonfeasible aircraft outcome requires structured reasons')
        if self.physical_outcome == 'unsupported' and self.aircraft_status != 'inputs_incomplete':
            raise ValueError('unsupported domain must not imply physical infeasibility or success')
        if self.physical_outcome == 'unresolved' and self.aircraft_status not in ('numerically_unverified', 'inputs_incomplete'):
            raise ValueError('unresolved search must not imply physical infeasibility or success')
        if self.physical_outcome == 'infeasible' and self.aircraft_status != 'requirement_not_met':
            raise ValueError('infeasible outcome needs compatibility requirement_not_met')
        if (self.physical_outcome == 'infeasible' and required <= by_name.keys()
                and all(by_name[name].outcome == 'feasible' for name in required)
                and not any(reason.code == 'limit_exceeded' for reason in self.reasons)):
            raise ValueError('infeasible aggregate with feasible cases requires an explicit aggregate limit reason')
        if self.payload_lower_bound_kg is not None:
            if self.physical_outcome != 'feasible':
                raise ValueError('only feasible complete results have a headline')
            minimum = min(by_name[name].feasible_payload_lower_bound_kg for name in required)
            if self.payload_lower_bound_kg != minimum or self.limiting_case_id not in required:
                raise ValueError('headline must equal the minimum required-case bound')
            if by_name[self.limiting_case_id].feasible_payload_lower_bound_kg != minimum:
                raise ValueError('limiting case differs from headline')
        elif self.limiting_case_id is not None:
            raise ValueError('limiting case needs a headline')
        return self


class ReviewAttestationV1(Record):
    schema_version: Literal['review_attestation_v1'] = 'review_attestation_v1'
    organization_id: Identifier
    project_id: Identifier
    package_revision_sha256: Digest
    study_sha256: Digest
    reviewer_identity_id: Identifier
    created_utc: UTCTimestamp
    state: Literal['pending', 'accepted', 'rejected', 'superseded']
    scope: str = Field(min_length=1, max_length=2000)
    authenticated_record_sha256: Digest | None = None
    supersedes_attestation_sha256: Digest | None = None

    @model_validator(mode='after')
    def authentication_reference(self):
        if not self.scope.strip():
            raise ValueError('review scope must contain meaningful text')
        if self.state != 'pending' and self.authenticated_record_sha256 is None:
            raise ValueError('review decision requires separately authenticated record reference')
        if self.state == 'superseded' and self.supersedes_attestation_sha256 is None:
            raise ValueError('superseded review requires the attestation it supersedes')
        return self

    def assert_applies_to(self, result: AircraftStudyV2) -> None:
        if (result.publication is None or self.package_revision_sha256 != result.publication.package_revision_sha256
                or self.study_sha256 != result.spec.study_sha256()
                or (self.organization_id, self.project_id) != (result.spec.organization_id, result.spec.project_id)):
            raise ValueError('detached review does not apply to this exact project/study/result revision')


def compatibility_status(outcome: Outcome, *, inputs_complete: bool) -> AircraftStatus:
    """Conservative bridge, never evidence or review promotion."""
    if not inputs_complete:
        return 'inputs_incomplete'
    return {'feasible': 'screening_only', 'infeasible': 'requirement_not_met',
            'unresolved': 'numerically_unverified', 'unsupported': 'inputs_incomplete',
            'not_evaluated': 'inputs_incomplete'}[outcome]
