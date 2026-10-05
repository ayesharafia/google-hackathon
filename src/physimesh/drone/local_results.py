"""Versioned local studies, separate from approved AircraftStudyV2.

V1/V2 remain historical reads. V3 adds stronger participating-bound consistency;
old bytes are not retroactively subjected to successor acceptance rules.
"""
from typing import Literal

from pydantic import Field, model_validator

from physimesh.projects.contracts import Digest, Identifier, Outcome, Record


class Command(Record):
    rpm: float = Field(ge=0)
    thrust_n: float = Field(ge=0)
    shaft_torque_nm: float = Field(ge=0)
    electrical_power_w: float = Field(ge=0)
    scope: str
    rotor_id: str
    signed_rpm: float
    force_body_n: tuple[float, float, float]
    reaction_torque_body_nm: tuple[float, float, float]
    dc_input_current_a: float = Field(ge=0)


class Candidate(Record):
    payload_kg: float = Field(ge=0)
    total_mass_kg: float = Field(ge=0)
    cg_body_m: tuple[float, float, float]
    force_residual_n: tuple[float, float, float]
    moment_residual_cg_nm: tuple[float, float, float]
    electrical_power_w: float = Field(ge=0)
    energy_required_j: float = Field(ge=0)
    commands: tuple[Command, ...] = Field(min_length=1, max_length=16)


class ResidualPolicy(Record):
    force_tolerance_n: float = Field(gt=0)
    moment_tolerance_nm: float = Field(gt=0)
    qualification: str


class BoundOrigin(Record):
    lower: Literal['physical', 'coverage', 'analyst_domain', 'fixed_candidate']
    upper: Literal['physical', 'coverage', 'analyst_domain', 'fixed_candidate']


class BoundDependency(Record):
    variable_index: int = Field(ge=0)
    side: Literal['lower', 'upper']
    origin: Literal['coverage', 'analyst_domain']


class SourceDomainGap(Record):
    rotor_id: Identifier
    gap: Literal['below_retained_rpm', 'above_retained_rpm']


class Certificate(Record):
    kind: Literal['bounded_nonnegative_linear_combination']
    gap: float = Field(gt=0)
    rounding_guard: float = Field(gt=0)
    multipliers: tuple[float, ...]
    row_scaling: tuple[float, ...]
    minimum_over_variable_bounds: float
    combined_upper_bound: float
    bound_origins: tuple[BoundOrigin, ...] = ()
    nonphysical_bound_dependencies: tuple[BoundDependency, ...] = ()
    source_domain_gaps: tuple[SourceDomainGap, ...] = ()
    qualification: str | None = None


class CaseEvidence(Record):
    case_id: Identifier
    required: bool | None = None
    outcome: Outcome
    candidate: Candidate | None = None
    active_constraints: tuple[str, ...] = ()
    residual_policy: ResidualPolicy | None = None
    solver_status: int | None = None
    scope: str | None = None
    reason: str | None = None
    certificate: Certificate | None = None

    @model_validator(mode='after')
    def evidence(self):
        if self.outcome == 'feasible':
            if self.candidate is None or self.residual_policy is None:
                raise ValueError('feasible case requires candidate and residual policy')
            if max(abs(v) for v in self.candidate.force_residual_n) > self.residual_policy.force_tolerance_n:
                raise ValueError('force residual exceeds policy')
            if max(abs(v) for v in self.candidate.moment_residual_cg_nm) > self.residual_policy.moment_tolerance_nm:
                raise ValueError('moment residual exceeds policy')
        if self.outcome == 'infeasible' and self.certificate is None:
            raise ValueError('infeasible local case requires certificate')
        if self.outcome == 'infeasible' and (self.certificate.nonphysical_bound_dependencies
                                            or self.certificate.source_domain_gaps):
            raise ValueError('coverage/domain certificate cannot claim physical infeasibility')
        return self


class SegmentEvidence(Record):
    segment_id: str
    case_id: Identifier
    duration_s: float = Field(gt=0)
    source_note: str
    power_profile: Literal['constant']
    electrical_power_w: float = Field(ge=0)
    energy_required_j: float = Field(ge=0)
    remaining_usable_energy_j: float


class SequenceEvidence(Record):
    segments: tuple[SegmentEvidence, ...] = Field(min_length=1, max_length=32)
    total_energy_j: float = Field(ge=0)
    usable_energy_j: float = Field(gt=0)
    remaining_usable_energy_j: float
    energy_tolerance_j: float = Field(gt=0)
    reserve_convention: Literal['held_usable_energy_fraction_applied_once']
    integration_method: Literal['constant_power_exact_v1']

    @model_validator(mode='after')
    def ledger(self):
        consumed = 0.
        for segment in self.segments:
            if abs(segment.duration_s*segment.electrical_power_w-segment.energy_required_j) > self.energy_tolerance_j:
                raise ValueError('segment energy does not match constant-power integral')
            consumed += segment.energy_required_j
            if abs(self.usable_energy_j-consumed-segment.remaining_usable_energy_j) > self.energy_tolerance_j:
                raise ValueError('sequence remaining-energy ledger mismatch')
        if (abs(consumed-self.total_energy_j) > self.energy_tolerance_j
                or abs(self.usable_energy_j-consumed-self.remaining_usable_energy_j) > self.energy_tolerance_j
                or consumed > self.usable_energy_j+self.energy_tolerance_j):
            raise ValueError('sequence aggregate energy mismatch or budget exceeded')
        return self


class _CapacityRecord(Record):
    schema_version: Literal['local_mission_capacity_v2', 'local_mission_capacity_v3']
    model_version: Literal['convex_static_hover_v1']
    payload_lower_bound_kg: float | None = Field(default=None, ge=0)
    limiting_case_id: Identifier | None = None
    aggregate_limit: Literal['sequence_energy'] | None = None
    cases: tuple[CaseEvidence, ...] = Field(min_length=1, max_length=8)
    headline_candidate_checks: tuple[CaseEvidence, ...] = ()
    participating_case_bounds: tuple[CaseEvidence, ...] = ()
    engineering_approval: Literal['pending']
    data_scope: Literal['analytic_fixture', 'client_unvalidated'] | None
    map_source_kinds: tuple[Literal['analytic_fixture', 'measured'], ...]
    qualification: str
    mission_semantics: Literal['required_alternative_cases', 'required_cases_and_ordered_sequence']
    outcome: Outcome
    reasons: tuple[str, ...]
    sequence_evidence: SequenceEvidence | None = None
    reason: str | None = None
    certificate: Certificate | None = None
    study_sha256: Digest
    specification: dict


class LocalCapacityV3(_CapacityRecord):
    schema_version: Literal['local_mission_capacity_v3']

    @model_validator(mode='after')
    def headline(self):
        return self.check_headline()

    def check_headline(self, *, require_participating_bounds=True):
        from physimesh.drone.provenance import sha256_record
        if sha256_record(self.specification) != self.study_sha256:
            raise ValueError('study specification digest mismatch')
        names = [case.case_id for case in self.cases]
        if len(set(names)) != len(names) or not any(case.required for case in self.cases):
            raise ValueError('unique cases and a required case are necessary')
        if self.outcome != 'feasible':
            if self.payload_lower_bound_kg is not None:
                raise ValueError('failed study cannot publish a payload headline')
            if self.outcome == 'infeasible' and not (
                    any(case.required and case.outcome == 'infeasible' for case in self.cases)
                    or self.certificate and not (self.certificate.nonphysical_bound_dependencies
                                                  or self.certificate.source_domain_gaps)):
                raise ValueError('infeasible aggregate requires a supported certificate')
            return self
        if self.payload_lower_bound_kg is None or not self.headline_candidate_checks:
            raise ValueError('headline needs independently checked common candidate')
        checks = {case.case_id: case for case in self.headline_candidate_checks}
        if len(checks) != len(self.headline_candidate_checks):
            raise ValueError('duplicate common candidate checks')
        required = {case.case_id for case in self.cases if case.required}
        for case in self.cases:
            if case.required and (case.outcome != 'feasible'
                                  or self.payload_lower_bound_kg > case.candidate.payload_kg+1e-7):
                raise ValueError('headline exceeds a required feasible case bound')
        if not required <= checks.keys():
            raise ValueError('required candidate check missing')
        for case in checks.values():
            if case.outcome != 'feasible' or case.candidate.payload_kg != self.payload_lower_bound_kg:
                raise ValueError('common candidate is not feasible in every checked case')
        if self.mission_semantics == 'required_cases_and_ordered_sequence':
            if self.sequence_evidence is None:
                raise ValueError('sequence headline needs aggregate evidence')
            for segment in self.sequence_evidence.segments:
                if segment.case_id not in checks:
                    raise ValueError('sequence segment candidate check missing')
                if abs(segment.electrical_power_w-checks[segment.case_id].candidate.electrical_power_w) > 1e-7:
                    raise ValueError('sequence power differs from recomputed candidate')
        participating = required | ({s.case_id for s in self.sequence_evidence.segments}
                                    if self.sequence_evidence else set())
        if self.sequence_evidence and require_participating_bounds:
            bounds = {case.case_id: case for case in self.participating_case_bounds}
            if len(bounds) != len(self.participating_case_bounds) or bounds.keys() != participating:
                raise ValueError('unique bound for every participating case required')
            if any(case.outcome != 'feasible' or self.payload_lower_bound_kg > case.candidate.payload_kg+1e-7
                   for case in bounds.values()):
                raise ValueError('headline exceeds a participating feasible case bound')
        if self.aggregate_limit is None and self.limiting_case_id not in participating:
            raise ValueError('headline requires a participating limiting case')
        if self.aggregate_limit is not None and self.sequence_evidence is None:
            raise ValueError('aggregate limit needs sequence evidence')
        if self.aggregate_limit is not None and (self.limiting_case_id is not None
                or abs(self.sequence_evidence.remaining_usable_energy_j) > self.sequence_evidence.energy_tolerance_j):
            raise ValueError('aggregate energy limit must bind without an invented limiting case')
        if self.aggregate_limit is None:
            bounds = self.participating_case_bounds if self.sequence_evidence else self.cases
            attaining = next((case for case in bounds if case.case_id == self.limiting_case_id), None)
            if attaining is None or attaining.outcome != 'feasible' or abs(
                    attaining.candidate.payload_kg-self.payload_lower_bound_kg) > 1e-7:
                raise ValueError('limiting case must attain the common headline bound')
        return self


# Exact source fingerprint of commit 07b9f192d55fd79c0cb209ece063bd029ce3d93e,
# computed from the same source-file manifest used by LocalStudies.model_identity.
# Its earlier acceptance policy is retained for history, never new production.
FIRST_V2_SOURCE_SHA256 = '5ea15ad323a3630b35d3b8d4428ea5b86b0ba4df80d78059cd0a7125c44a69b2'
# Corrected V2 generations before all participating minima became mandatory.
PRE_MINIMUM_V2_SOURCES = frozenset({
    '0940847e403ea7c9e42dada54e7cb7642ea06bdea43afd2623e4043971812310',  # 0db6bb0
    'b77a023e87cb59f9b2fcd6b295329303ceab8d591eb1bb2600e562093e4fe789',  # 3f9b01d
})


class LocalCapacityV2(_CapacityRecord):
    """Historical reads. Known producer fingerprints select their earlier policies."""
    schema_version: Literal['local_mission_capacity_v2']

    @model_validator(mode='after')
    def historical_consistency(self):
        model = self.specification.get('model', {})
        source = model.get('source_fingerprint_sha256') if isinstance(model, dict) else None
        if source in PRE_MINIMUM_V2_SOURCES:
            return LocalCapacityV3.check_headline(self, require_participating_bounds=False)
        if source != FIRST_V2_SOURCE_SHA256:
            # Later/unknown producers must satisfy the strengthened evidence rules.
            # Missing legacy evidence is not sufficient to select a weaker policy.
            return LocalCapacityV3.check_headline(self)
        # Original 07b9f19 headline policy. Earlier attribution limitations stay
        # historical and visibly qualified; reading is not current requalification.
        from physimesh.drone.provenance import sha256_record
        if sha256_record(self.specification) != self.study_sha256:
            raise ValueError('study specification digest mismatch')
        names = [case.case_id for case in self.cases]
        if len(set(names)) != len(names) or not any(case.required for case in self.cases):
            raise ValueError('unique cases and a required case are necessary')
        if self.outcome != 'feasible':
            if self.payload_lower_bound_kg is not None:
                raise ValueError('failed study cannot publish a payload headline')
            return self
        if self.payload_lower_bound_kg is None or not self.headline_candidate_checks:
            raise ValueError('headline needs independently checked common candidate')
        checks = {case.case_id: case for case in self.headline_candidate_checks}
        if len(checks) != len(self.headline_candidate_checks):
            raise ValueError('duplicate common candidate checks')
        required = {case.case_id for case in self.cases if case.required}
        if not required <= checks.keys():
            raise ValueError('required candidate check missing')
        for case in checks.values():
            if case.outcome != 'feasible' or case.candidate.payload_kg != self.payload_lower_bound_kg:
                raise ValueError('common candidate is not feasible in every checked case')
        if self.mission_semantics == 'required_cases_and_ordered_sequence':
            if self.sequence_evidence is None:
                raise ValueError('sequence headline needs aggregate evidence')
            for segment in self.sequence_evidence.segments:
                if segment.case_id not in checks:
                    raise ValueError('sequence segment candidate check missing')
                if abs(segment.electrical_power_w-checks[segment.case_id].candidate.electrical_power_w) > 1e-7:
                    raise ValueError('sequence power differs from recomputed candidate')
        if self.aggregate_limit is None and self.limiting_case_id not in required:
            raise ValueError('alternative headline requires a required limiting case')
        if self.aggregate_limit is not None and self.sequence_evidence is None:
            raise ValueError('aggregate limit needs sequence evidence')
        return self
