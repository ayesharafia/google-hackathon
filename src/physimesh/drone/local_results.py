"""Versioned local studies, separate from approved AircraftStudyV2.

V1/V2 remain historical reads. Exact known V2 producers retain their original
policies; unknown producers must satisfy stronger V3 consistency checks.
"""
from typing import Literal

from pydantic import Field, model_validator

from physimesh.projects.contracts import Digest, Identifier, Outcome, Record

from .scenarios import AllowableCapV1


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


class TorqueBandInterval(Record):
    lower: tuple[float, float, float]
    upper: tuple[float, float, float]
    allowance: tuple[float, float, float]
    source_note: str = Field(min_length=1)


class CandidateV4(Candidate):
    torque_band_moment_interval_nm: TorqueBandInterval | None = None


class SourceDomainGapV4(SourceDomainGap):
    gap: Literal['below_retained_rpm', 'above_retained_rpm', 'conditioned_surrogate']


class CertificateV4(Certificate):
    source_domain_gaps: tuple[SourceDomainGapV4, ...] = ()


class CaseEvidenceV4(CaseEvidence):
    candidate: CandidateV4 | None = None
    failed_rotor_ids: tuple[Identifier, ...] = ()
    axial_inflow_m_s: float = Field(default=0, ge=0)
    certificate: CertificateV4 | None = None

    @model_validator(mode='after')
    def extended_evidence(self):
        if self.outcome != 'feasible':
            return self
        ids = {command.rotor_id: command for command in self.candidate.commands}
        if len(set(self.failed_rotor_ids)) != len(self.failed_rotor_ids) or not set(self.failed_rotor_ids) <= ids.keys():
            raise ValueError('failed rotor evidence must identify unique commands')
        for name in self.failed_rotor_ids:
            c = ids[name]
            if any((c.rpm, c.thrust_n, c.shaft_torque_nm, c.electrical_power_w, c.dc_input_current_a,
                    *c.force_body_n, *c.reaction_torque_body_nm)):
                raise ValueError('failed rotor must produce zero thrust, torque and input power')
        band = self.candidate.torque_band_moment_interval_nm
        if band:
            if not band.source_note.strip():
                raise ValueError('torque-band allowance source is missing')
            for low, high, allowed, moment in zip(band.lower, band.upper, band.allowance,
                                                self.candidate.moment_residual_cg_nm, strict=True):
                if (allowed < 0 or not low <= moment <= high
                        or max(abs(low), abs(high)) > allowed+self.residual_policy.moment_tolerance_nm):
                    raise ValueError('torque-band moment interval exceeds its declared allowance')
        return self


class LocalCapacityV4(LocalCapacityV3):
    """Extended local model; inherited V3 common-candidate/sequence checks remain mandatory."""
    schema_version: Literal['local_mission_capacity_v4']
    model_version: Literal['convex_axial_capacity_v2']
    cases: tuple[CaseEvidenceV4, ...] = Field(min_length=1, max_length=8)
    headline_candidate_checks: tuple[CaseEvidenceV4, ...] = ()
    participating_case_bounds: tuple[CaseEvidenceV4, ...] = ()
    conditioning_sources: dict[str, dict]
    certificate: CertificateV4 | None = None
    scenario_analysis: 'ScenarioAnalysisV4 | None' = None
    external_allowables: 'AllowableEvidenceV4 | None' = None

    @model_validator(mode='after')
    def extended_headlines(self):
        from .conditioning import ConditionedProfileV1
        from .provenance import canonical_json, sha256_record
        for digest, receipt in self.conditioning_sources.items():
            profile = {k: v for k, v in receipt.items()
                       if k not in ('raw_source_sha256', 'conditioned_source_sha256', 'profile_sha256')}
            ConditionedProfileV1.model_validate_json(canonical_json(profile))
            if (receipt.get('conditioned_source_sha256') != digest
                    or digest not in self.specification.get('performance_source_sha256', [])
                    or receipt.get('profile_sha256') != sha256_record(profile)):
                raise ValueError('conditioned profile receipt is not bound to the retained study source')
        analysis = self.scenario_analysis
        results = {'nominal': self}
        if analysis:
            for scenario in analysis.scenarios:
                if scenario.scenario_id in results:
                    raise ValueError('scenario identities must be unique; nominal is reserved')
                results[scenario.scenario_id] = scenario.result
            if analysis.status == 'supported':
                if (not analysis.scenarios or any(r.outcome != 'feasible' for r in results.values())
                        or analysis.supported_payload_kg != min(r.payload_lower_bound_kg for r in results.values())):
                    raise ValueError('scenario envelope requires every feasible scenario and its actual minimum')
                validate_payload_checks(analysis.common_payload_checks, results, analysis.supported_payload_kg)
                limiting = {name for name, r in results.items()
                            if r.payload_lower_bound_kg == analysis.supported_payload_kg}
                if set(analysis.limiting_scenario_ids) != limiting:
                    raise ValueError('limiting scenario does not attain the deterministic minimum')
            elif analysis.supported_payload_kg is not None:
                raise ValueError('incomplete/undeclared uncertainty cannot publish a supported envelope')
        allowable = self.external_allowables
        if allowable:
            approved = [cap for cap in allowable.caps if cap.approval_status == 'declared_approved']
            expected_cap = min(cap.payload_kg for cap in approved) if approved else None
            if (len({c.cap_id for c in allowable.caps}) != len(allowable.caps)
                    or allowable.declared_approved_cap_kg != expected_cap
                    or set(allowable.limiting_cap_ids) != {c.cap_id for c in approved if c.payload_kg == expected_cap}):
                raise ValueError('external cap minimum or source attribution differs from its declarations')
            if allowable.status == 'supported':
                envelope = (analysis.supported_payload_kg if analysis and analysis.scenarios
                            else self.payload_lower_bound_kg)
                if (expected_cap is None or envelope is None or self.outcome != 'feasible'
                        or allowable.feasible_capped_payload_kg != min(expected_cap, envelope)):
                    raise ValueError('capped payload needs a supported model/envelope and a sourced cap')
                validate_payload_checks(allowable.candidate_checks, results, allowable.feasible_capped_payload_kg)
            elif allowable.feasible_capped_payload_kg is not None:
                raise ValueError('unresolved allowable cannot publish a feasible capped payload')
        return self


class PayloadCheckV4(Record):
    scenario_id: Identifier
    outcome: Outcome
    payload_kg: float = Field(ge=0)
    case_checks: tuple[CaseEvidenceV4, ...]
    sequence_energy_j: float | None = Field(default=None, ge=0)
    usable_energy_j: float | None = Field(default=None, gt=0)
    energy_tolerance_j: float | None = Field(default=None, gt=0)
    reason: str | None = None

    @model_validator(mode='after')
    def candidate(self):
        if self.outcome == 'feasible':
            if not self.case_checks or any(c.outcome != 'feasible' or c.candidate.payload_kg != self.payload_kg
                                           for c in self.case_checks):
                raise ValueError('common payload checks must be feasible at exactly the claimed payload')
            if self.sequence_energy_j is not None and (
                    self.usable_energy_j is None or self.energy_tolerance_j is None
                    or self.sequence_energy_j > self.usable_energy_j+self.energy_tolerance_j):
                raise ValueError('common payload chronological energy exceeds its fixed-pack budget')
        return self


class ScenarioEvidenceV4(Record):
    scenario_id: Identifier
    source_note: str = Field(min_length=1)
    correlation_note: str = Field(min_length=1)
    result: LocalCapacityV4

    @model_validator(mode='after')
    def association(self):
        if (not self.source_note.strip() or not self.correlation_note.strip()
                or self.result.specification.get('scenario_id') != self.scenario_id
                or self.result.scenario_analysis is not None or self.result.external_allowables is not None):
            raise ValueError('scenario result must retain its sourced identity without nested scenarios')
        return self


class ScenarioAnalysisV4(Record):
    status: Literal['not_declared', 'supported', 'incomplete', 'unresolved']
    scenarios: tuple[ScenarioEvidenceV4, ...] = Field(max_length=16)
    supported_payload_kg: float | None = Field(ge=0)
    limiting_scenario_ids: tuple[Identifier, ...]
    common_payload_checks: tuple[PayloadCheckV4, ...]
    qualification: str


class AllowableEvidenceV4(Record):
    status: Literal['not_declared', 'no_declared_approved_cap', 'supported', 'unresolved']
    caps: tuple[AllowableCapV1, ...] = Field(max_length=16)
    declared_approved_cap_kg: float | None = Field(ge=0)
    feasible_capped_payload_kg: float | None = Field(ge=0)
    candidate_checks: tuple[PayloadCheckV4, ...]
    limiting_cap_ids: tuple[Identifier, ...]
    qualification: str


def validate_payload_checks(checks, results, payload):
    by_name = {check.scenario_id: check for check in checks}
    if len(by_name) != len(checks) or by_name.keys() != results.keys():
        raise ValueError('unique common payload check for every scenario and nominal case is required')
    for name, record in results.items():
        check = by_name[name]
        expected = {c.case_id for c in record.headline_candidate_checks}
        actual = {c.case_id for c in check.case_checks}
        if (check.outcome != 'feasible' or check.payload_kg != payload
                or actual != expected or len(actual) != len(check.case_checks)):
            raise ValueError('scenario common payload omits participating case checks')
        if record.sequence_evidence:
            power = {c.case_id: c.candidate.electrical_power_w for c in check.case_checks}
            expected_energy = sum(power[s.case_id]*s.duration_s for s in record.sequence_evidence.segments)
            if (check.sequence_energy_j is None or abs(check.sequence_energy_j-expected_energy)
                    > record.sequence_evidence.energy_tolerance_j
                    or check.usable_energy_j != record.sequence_evidence.usable_energy_j):
                raise ValueError('scenario common payload energy differs from its participating segments')


LocalCapacityV4.model_rebuild()
