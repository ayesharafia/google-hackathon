"""Sourced deterministic joint scenarios and separately declared external caps.

No independent Cartesian products, density/map scaling, probabilities or approval
authentication are inferred. Common payloads are checked, never assumed feasible.
"""
from __future__ import annotations

import copy
import math
from typing import Annotated, Literal

from pydantic import Field, model_validator

from physimesh.projects.contracts import Digest, Identifier, Record

from .provenance import canonical_json, sha256_record
from .snapshot_hash import snapshot_sha256

Nonnegative = Annotated[float, Field(ge=0)]


class ScenarioAtmosphere(Record):
    pressure_pa: float = Field(gt=0)
    temperature_k: float = Field(gt=0)
    source: str = Field(min_length=1)


class ScenarioLoad(Record):
    force_body_n: tuple[float, float, float]
    moment_origin_body_nm: tuple[float, float, float]
    source_note: str = Field(min_length=1)


class ScenarioV1(Record):
    schema_version: Literal['deterministic_capacity_scenario_v1']
    scenario_id: Identifier
    source_note: str = Field(min_length=1, max_length=2000)
    correlation_note: str = Field(min_length=1, max_length=2000)
    mass_items_kg: dict[str, Nonnegative] = Field(default_factory=dict)
    map_sources_by_rotor: dict[Identifier, Digest] = Field(default_factory=dict)
    map_sources_by_case: dict[Identifier, dict[Identifier, Digest]] = Field(default_factory=dict)
    atmosphere: ScenarioAtmosphere | None = None
    body_loads_by_case: dict[Identifier, ScenarioLoad] = Field(default_factory=dict)

    @model_validator(mode='after')
    def meaningful_sources(self):
        sources = [self.source_note, self.correlation_note]
        if self.atmosphere:
            sources.append(self.atmosphere.source)
        sources.extend(load.source_note for load in self.body_loads_by_case.values())
        if any(not text.strip() for text in sources):
            raise ValueError('scenario and changed-condition sources must be meaningful')
        return self


class AllowableCapV1(Record):
    schema_version: Literal['external_payload_cap_v1']
    cap_id: Identifier
    kind: Literal['structural', 'operational']
    payload_kg: Nonnegative
    source_note: str = Field(min_length=1, max_length=2000)
    approval_status: Literal['proposed', 'declared_approved']
    approval_scope: str = Field(min_length=1, max_length=2000)
    approval_reference: str | None = None

    @model_validator(mode='after')
    def approved_source(self):
        if (not self.source_note.strip() or not self.approval_scope.strip()
                or self.approval_status == 'declared_approved'
                and (not self.approval_reference or not self.approval_reference.strip())):
            raise ValueError('external cap requires source/scope and a reference for declared approval')
        return self


def apply_scenario(snapshot, scenario: ScenarioV1):
    result = copy.deepcopy(snapshot)
    items = result['masses']['items']; names = [item.get('name') for item in items]
    if len(set(names)) != len(names) or not scenario.mass_items_kg.keys() <= set(names):
        raise ValueError('scenario mass names must uniquely resolve declared ledger items')
    for item in items:
        if item['name'] in scenario.mass_items_kg:
            if item.get('category') == 'payload':
                raise ValueError('scenario cannot override the searched payload ledger item')
            item['mass_kg'] = scenario.mass_items_kg[item['name']]
            item['source_note'] = scenario.source_note
    rotors = {r['rotor_id']: r for r in result['rotors']}
    cases = {c['name']: c for c in result['mission']['cases']}
    if (not scenario.map_sources_by_rotor.keys() <= rotors.keys()
            or not scenario.map_sources_by_case.keys() <= cases.keys()
            or not scenario.body_loads_by_case.keys() <= cases.keys()):
        raise ValueError('scenario sources/loads must resolve declared rotors and cases')
    for name, digest in scenario.map_sources_by_rotor.items():
        rotors[name]['map_ref'] = digest
    for name, sources in scenario.map_sources_by_case.items():
        if not sources.keys() <= rotors.keys():
            raise ValueError('scenario case map identifies an unknown rotor')
        cases[name]['performance_source_by_rotor'] = {
            **cases[name].get('performance_source_by_rotor', {}), **sources}
    if scenario.atmosphere:
        declared = scenario.atmosphere.model_dump(mode='json')
        result['atmosphere'].update(declared)
        # Scenario atmosphere intentionally applies to every participating case.
        for case in cases.values():
            case['atmosphere'] = declared.copy()
    for name, load in scenario.body_loads_by_case.items():
        cases[name].update(body_force_body_n=list(load.force_body_n),
                           body_moment_origin_body_nm=list(load.moment_origin_body_nm),
                           body_load_source=load.source_note)
    return result


def check_common_payload(snapshot, maps, payload):
    from .capacity import allocation
    from .mission_capacity import prepare_sequence, sequence_case_inputs
    from .trim import prepare_hover
    inputs = {}; checks = []
    try:
        for case in snapshot['mission']['cases']:
            if case.get('required', True):
                inputs[case['name']] = prepare_hover(snapshot, case, maps)
        sequence = []
        if snapshot['mission'].get('sequence'):
            inputs = sequence_case_inputs(snapshot, maps, inputs)
            sequence = prepare_sequence(snapshot, inputs)
        checks = [{'case_id': name, **allocation(case, payload_kg=payload)} for name, case in inputs.items()]
        if any(check['outcome'] != 'feasible' for check in checks):
            return {'outcome': 'unresolved', 'payload_kg': payload, 'case_checks': checks,
                    'reason': 'The common payload is not feasible in every participating case.'}
        power = {c['case_id']: c['candidate']['electrical_power_w'] for c in checks}
        energy = math.fsum(power[s['case_id']]*s['duration_s'] for s in sequence)
        budget = min(case.usable_j for case in inputs.values())
        tolerance = 1e-7*max(1., budget)
        if energy > budget+tolerance:
            return {'outcome': 'unresolved', 'payload_kg': payload, 'case_checks': checks,
                    'reason': 'Common payload exceeds its chronological fixed-pack budget.'}
        return {'outcome': 'feasible', 'payload_kg': payload, 'case_checks': checks,
                'sequence_energy_j': energy if sequence else None, 'usable_energy_j': budget,
                'energy_tolerance_j': tolerance}
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return {'outcome': 'unsupported', 'payload_kg': payload, 'case_checks': checks, 'reason': str(exc)}


def assess_scenarios_and_caps(snapshot, maps, nominal):
    from .capacity import nominal_capacity
    settings = snapshot['fidelity']['local_pilot']
    raw_scenarios = settings.get('scenarios', [])
    raw_caps = settings.get('allowable_caps', [])
    if not isinstance(raw_scenarios, list) or len(raw_scenarios) > 16:
        raise ValueError('declare at most 16 deterministic joint scenarios')
    if not isinstance(raw_caps, list) or len(raw_caps) > 16:
        raise ValueError('declare at most 16 sourced external payload caps')
    scenarios = [ScenarioV1.model_validate_json(canonical_json(raw)) for raw in raw_scenarios]
    caps = [AllowableCapV1.model_validate_json(canonical_json(raw)) for raw in raw_caps]
    if len({s.scenario_id for s in scenarios}) != len(scenarios) or any(s.scenario_id == 'nominal' for s in scenarios):
        raise ValueError('scenario IDs must be unique; nominal is reserved')
    if len({c.cap_id for c in caps}) != len(caps):
        raise ValueError('external cap IDs must be unique')
    records = []; states = {'nominal': snapshot}; results = {'nominal': nominal}
    for scenario in scenarios:
        state = apply_scenario(snapshot, scenario)
        result = nominal_capacity(state, maps)
        identity = {'scenario_id': scenario.scenario_id, 'snapshot_sha256': snapshot_sha256(state),
                    'model_version': result['model_version'], 'performance_source_sha256': sorted(maps)}
        result = {**result, 'specification': identity, 'study_sha256': sha256_record(identity)}
        records.append({'scenario_id': scenario.scenario_id, 'source_note': scenario.source_note,
                        'correlation_note': scenario.correlation_note, 'result': result})
        states[scenario.scenario_id] = state; results[scenario.scenario_id] = result
    complete = all(r['outcome'] == 'feasible' for r in results.values())
    supported = min(r['payload_lower_bound_kg'] for r in results.values()) if complete else None
    common_checks = []
    if supported is not None and scenarios:
        common_checks = [{'scenario_id': name, **check_common_payload(state, maps, supported)}
                         for name, state in states.items()]
        if any(check['outcome'] != 'feasible' for check in common_checks):
            supported = None
    analysis = {'status': ('not_declared' if not scenarios else 'supported' if supported is not None
                          else 'unresolved' if complete else 'incomplete'),
                'scenarios': records, 'supported_payload_kg': supported if scenarios else None,
                'limiting_scenario_ids': [name for name, r in results.items()
                                         if scenarios and supported is not None
                                         and r['payload_lower_bound_kg'] == supported],
                'common_payload_checks': common_checks,
                'qualification': 'Sourced deterministic joint declarations; correlations are preserved within each '
                                 'scenario. Partial uncertainty coverage, no probabilities or confidence intervals.'}
    approved = [cap for cap in caps if cap.approval_status == 'declared_approved']
    cap_kg = min(cap.payload_kg for cap in approved) if approved else None
    capped = None; cap_checks = []
    if cap_kg is not None and complete and (not scenarios or supported is not None):
        capped = min(cap_kg, supported)
        cap_checks = [{'scenario_id': name, **check_common_payload(state, maps, capped)}
                      for name, state in states.items()]
        if any(check['outcome'] != 'feasible' for check in cap_checks):
            capped = None
    allowable = {'status': ('not_declared' if not caps else 'no_declared_approved_cap' if not approved
                           else 'supported' if capped is not None else 'unresolved'),
                 'caps': [cap.model_dump(mode='json') for cap in caps], 'declared_approved_cap_kg': cap_kg,
                 'feasible_capped_payload_kg': capped, 'candidate_checks': cap_checks,
                 'limiting_cap_ids': [cap.cap_id for cap in approved if cap.payload_kg == cap_kg],
                 'qualification': 'External approval is a caller declaration, not authenticated engineering '
                                  'acceptance. Model capacity, deterministic envelope and caps remain distinct.'}
    return {**nominal, 'scenario_analysis': analysis, 'external_allowables': allowable}
