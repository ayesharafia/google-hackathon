"""Alternative-case aggregation for the explicitly restricted local hover model."""
from __future__ import annotations

import re

from .mission_capacity import prepare_sequence, sequence_case_inputs, solve_sequence
from .trim import EXTENDED_MODEL_VERSION, MODEL_VERSION, prepare_hover, solve_hover


def allocation(case, *, payload_kg=None):
    """Inputs are already eligible. Unexpected solver/recompute failures stay unresolved."""
    try:
        result = solve_hover(case, payload_kg=payload_kg)
    except (ValueError, TypeError, KeyError, OverflowError, RuntimeError) as exc:
        result = {'outcome': 'unresolved', 'reason': 'allocation failed after input eligibility: ' + str(exc)}
    if case.snapshot['fidelity']['local_pilot']['model_version'] == EXTENDED_MODEL_VERSION:
        result.update(failed_rotor_ids=list(case.failed_rotor_ids), axial_inflow_m_s=case.inflow_m_s)
    return result


def hover_readiness(snapshot: dict, maps: dict, source_errors=()) -> dict:
    """Eligibility only, without allocating rotor commands or claiming feasibility."""
    cases = snapshot['mission'].get('cases', [])
    blocking = list(source_errors)
    if not isinstance(cases, list) or not 1 <= len(cases) <= 8:
        blocking.append('mission.cases: declare 1-8 cases')
        cases = []
    names = [c.get('name') for c in cases if isinstance(c, dict)]
    if (len(names) != len(cases) or any(not isinstance(name, str)
            or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', name) is None for name in names)
            or len(set(names)) != len(names)):
        blocking.append('mission.cases: unique case IDs required')
    if any(isinstance(c, dict) and type(c.get('required', True)) is not bool for c in cases):
        blocking.append('mission.cases.required: explicit boolean required')
    if not any(isinstance(c, dict) and c.get('required', True) is True for c in cases):
        blocking.append('mission.cases: at least one required case')
    records, prepared = [], {}
    for case in cases:
        try:
            if not isinstance(case, dict):
                raise TypeError('case must be a mapping')
            prepared[case['name']] = prepare_hover(snapshot, case, maps)
            records.append({'case_id': case.get('name'), 'eligible': True, 'blocking': []})
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            reason = str(exc)
            required = not isinstance(case, dict) or case.get('required', True) is not False
            records.append({'case_id': case.get('name') if isinstance(case, dict) else None,
                            'eligible': False, 'blocking': [reason]})
            if required:
                blocking.append(reason)
    if snapshot['mission'].get('sequence'):
        try:
            prepare_sequence(snapshot, sequence_case_inputs(snapshot, maps, prepared))
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            blocking.append(str(exc))
    return {'method': snapshot['fidelity'].get('local_pilot', {}).get('model_version'),
            'eligible': not blocking, 'blocking': blocking,
            'cases': records, 'qualification': 'Input eligibility only; trim and capacity are not yet established.'}


def capacity_from_snapshot(snapshot: dict, maps: dict) -> dict:
    result = nominal_capacity(snapshot, maps)
    if result['model_version'] == EXTENDED_MODEL_VERSION:
        from .scenarios import assess_scenarios_and_caps
        return assess_scenarios_and_caps(snapshot, maps, result)
    return result


def nominal_capacity(snapshot: dict, maps: dict) -> dict:
    version = snapshot['fidelity'].get('local_pilot', {}).get('model_version')
    extended = version == EXTENDED_MODEL_VERSION
    declared = snapshot['mission'].get('cases')
    if not isinstance(declared, list) or not 1 <= len(declared) <= 8:
        raise ValueError('1-8 explicit cases required for the bounded local pilot')
    if any(not isinstance(case, dict) for case in declared):
        raise ValueError('cases must be mappings')
    names = [case.get('name') for case in declared]
    if (any(not isinstance(name, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', name) is None
            for name in names) or len(set(names)) != len(names)):
        raise ValueError('case IDs must be unique valid identifiers')
    if any(type(case.get('required', True)) is not bool for case in declared):
        raise ValueError('required must be a boolean')
    required = [case for case in declared if case.get('required', True)]
    if not required:
        raise ValueError('at least one required case')
    records, inputs = [], {}
    for case in declared:
        try:
            prepared = prepare_hover(snapshot, case, maps)
            inputs[case['name']] = prepared
            result = allocation(prepared)
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            result = {'outcome': 'unsupported', 'reason': str(exc)}
        records.append({'case_id': case['name'], 'required': case.get('required', True), **result})
    needed = [record for record in records if record['required']]
    failures = [record for record in needed if record['outcome'] != 'feasible']
    report = {'schema_version': 'local_mission_capacity_v4' if extended else 'local_mission_capacity_v3',
              'model_version': EXTENDED_MODEL_VERSION if extended else MODEL_VERSION,
              'payload_lower_bound_kg': None, 'limiting_case_id': None, 'cases': records,
              'engineering_approval': 'pending',
              'data_scope': ('analytic_fixture' if any(m.source_kind == 'analytic_fixture' for m in maps.values())
                             else snapshot['identity'].get('data_scope')),
              'map_source_kinds': sorted({model.source_kind for model in maps.values()}),
              'qualification': 'Local frozen-input study within the declared static model. '
                               'No installed-aircraft validation or operational payload approval.',
              'mission_semantics': ('required_cases_and_ordered_sequence' if snapshot['mission'].get('sequence')
                                    else 'required_alternative_cases')}
    if extended:
        from .conditioning import ConditionedMap
        report['conditioning_sources'] = {digest: model.evidence() for digest, model in maps.items()
                                          if isinstance(model, ConditionedMap)}
        report['qualification'] = ('Local frozen-input static hover / axial climb allocation with declared '
                                   'failure states and optional conditioned maps. Torque bands are checked '
                                   'against sourced allowances; no flight or installed-aircraft approval.')
    sequence = None
    if snapshot['mission'].get('sequence'):
        try:
            selected = sequence_case_inputs(snapshot, maps, inputs)
            sequence = prepare_sequence(snapshot, selected)
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            return {**report, 'outcome': 'unsupported', 'reasons': [str(exc)]}
    if failures:
        outcome = ('infeasible' if any(r['outcome'] == 'infeasible' for r in failures)
                   else 'unsupported' if any(r['outcome'] == 'unsupported' for r in failures) else 'unresolved')
        return {**report, 'outcome': outcome, 'reasons': [r.get('reason') for r in failures]}
    if sequence is not None:
        try:
            result = solve_sequence(selected, sequence)
        except (ValueError, TypeError, KeyError, OverflowError, RuntimeError) as exc:
            return {**report, 'outcome': 'unresolved', 'reasons': ['joint allocation failed: ' + str(exc)]}
        if result['outcome'] != 'feasible':
            return {**report, **result, 'reasons': [result['reason']]}
        evidence = result['sequence_evidence']
        aggregate_binds = abs(evidence['remaining_usable_energy_j']) <= evidence['energy_tolerance_j']
        participating = [{'case_id': name, **allocation(case)} for name, case in selected.items()]
        if any(record['outcome'] != 'feasible' for record in participating):
            return {**report, 'outcome': 'unresolved', 'participating_case_bounds': participating,
                    'reasons': ['Participating case bounds are not independently established.']}
        individual = min(participating, key=lambda record: record['candidate']['payload_kg'])
        if (result['payload_kg'] > individual['candidate']['payload_kg']+1e-7
                or not aggregate_binds and abs(result['payload_kg']-individual['candidate']['payload_kg']) > 1e-7):
            return {**report, 'outcome': 'unresolved', 'participating_case_bounds': participating,
                    'headline_candidate_checks': result['headline_candidate_checks'],
                    'reasons': ['Joint payload and independently attained case bounds do not agree.']}
        return {**report, 'outcome': 'feasible', 'mission_semantics': 'required_cases_and_ordered_sequence',
                'payload_lower_bound_kg': result['payload_kg'],
                'limiting_case_id': None if aggregate_binds else individual['case_id'],
                'aggregate_limit': 'sequence_energy' if aggregate_binds else None,
                'headline_candidate_checks': result['headline_candidate_checks'],
                'participating_case_bounds': participating,
                'sequence_evidence': evidence, 'reasons': []}
    limiting = min(needed, key=lambda record: record['candidate']['payload_kg'])
    payload = limiting['candidate']['payload_kg']
    checks = []
    # Minimum individual maxima can be below another case's feasible interval.
    # Verify a compatible headline at the same candidate instead of assuming a prefix.
    for case in required:
        result = allocation(inputs[case['name']], payload_kg=payload)
        checks.append({'case_id': case['name'], **result})
    if any(result['outcome'] != 'feasible' for result in checks):
        return {**report, 'outcome': 'unresolved', 'headline_candidate_checks': checks,
                'reasons': ['Individual case bounds do not establish a compatible common payload.']}
    return {**report, 'outcome': 'feasible', 'payload_lower_bound_kg': payload,
            'limiting_case_id': limiting['case_id'], 'headline_candidate_checks': checks, 'reasons': []}
