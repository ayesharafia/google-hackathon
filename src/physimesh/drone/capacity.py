"""Alternative-case aggregation for the explicitly restricted local hover model."""
from __future__ import annotations

import re

from .mission_capacity import prepare_sequence, sequence_case_inputs, solve_sequence
from .trim import MODEL_VERSION, prepare_hover, solve_hover


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
    return {'method': MODEL_VERSION, 'eligible': not blocking, 'blocking': blocking,
            'cases': records, 'qualification': 'Input eligibility only; trim and capacity are not yet established.'}


def capacity_from_snapshot(snapshot: dict, maps: dict) -> dict:
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
            result = solve_hover(prepared)
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            result = {'outcome': 'unsupported', 'reason': str(exc)}
        records.append({'case_id': case['name'], 'required': case.get('required', True), **result})
    needed = [record for record in records if record['required']]
    failures = [record for record in needed if record['outcome'] != 'feasible']
    report = {'schema_version': 'local_mission_capacity_v2', 'model_version': MODEL_VERSION,
              'payload_lower_bound_kg': None, 'limiting_case_id': None, 'cases': records,
              'engineering_approval': 'pending',
              'data_scope': ('analytic_fixture' if any(m.source_kind == 'analytic_fixture' for m in maps.values())
                             else snapshot['identity'].get('data_scope')),
              'map_source_kinds': sorted({model.source_kind for model in maps.values()}),
              'qualification': 'Local frozen-input study within the declared static model. '
                               'No installed-aircraft validation or operational payload approval.',
              'mission_semantics': ('required_cases_and_ordered_sequence' if snapshot['mission'].get('sequence')
                                    else 'required_alternative_cases')}
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
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            return {**report, 'outcome': 'unsupported', 'reasons': [str(exc)]}
        if result['outcome'] != 'feasible':
            return {**report, **result, 'reasons': [result['reason']]}
        evidence = result['sequence_evidence']
        aggregate_binds = abs(evidence['remaining_usable_energy_j']) <= evidence['energy_tolerance_j']
        participating = [{'case_id': name, **solve_hover(case)} for name, case in selected.items()]
        if any(record['outcome'] != 'feasible' for record in participating):
            return {**report, 'outcome': 'unresolved', 'participating_case_bounds': participating,
                    'reasons': ['Participating case bounds are not independently established.']}
        individual = min(participating, key=lambda record: record['candidate']['payload_kg'])
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
        result = solve_hover(inputs[case['name']], payload_kg=payload)
        checks.append({'case_id': case['name'], **result})
    if any(result['outcome'] != 'feasible' for result in checks):
        return {**report, 'outcome': 'unresolved', 'headline_candidate_checks': checks,
                'reasons': ['Individual case bounds do not establish a compatible common payload.']}
    return {**report, 'outcome': 'feasible', 'payload_lower_bound_kg': payload,
            'limiting_case_id': limiting['case_id'], 'headline_candidate_checks': checks, 'reasons': []}
