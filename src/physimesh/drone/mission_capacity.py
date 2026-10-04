"""Bounded joint static allocation with one chronological fixed-pack budget.

Constant conditions only. No transient dynamics, battery resizing, sag or thermal state.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import linprog

from .trim import (
    bound_origins,
    classify_certificate,
    constraints,
    infeasibility_certificate,
    number,
    prepare_hover,
    solve_hover,
)


def sequence_case_inputs(snapshot: dict, maps: dict, inputs: dict) -> dict:
    """Required standalone duty and optional segment duty have distinct durations."""
    declared = snapshot['mission']['cases']; segments = snapshot['mission'].get('sequence')
    if not isinstance(segments, list) or any(not isinstance(s, dict) for s in segments):
        raise ValueError('sequence must be an ordered list of segment mappings')
    selected = {}
    for case in declared:
        name = case['name']; durations = [number(s.get('duration_s'), 'segment duration', positive=True)
                                         for s in segments if s.get('case_id') == name]
        if case.get('required', True):
            if name not in inputs:
                raise ValueError('required sequence case is not eligible: '+name)
            selected[name] = inputs[name]
        elif durations:
            original = number(case.get('duration_s'), 'case duration', positive=True)
            if max(durations) > original:
                raise ValueError('segment duration exceeds its declared case duration')
            selected[name] = prepare_hover(snapshot, {**case, 'duration_s': max(durations)}, maps)
    return selected


def prepare_sequence(snapshot: dict, inputs: dict) -> list[dict]:
    sequence = snapshot['mission'].get('sequence')
    if not isinstance(sequence, list) or not 1 <= len(sequence) <= 32:
        raise ValueError('mission.sequence: declare 1-32 ordered constant-power segments')
    records, names = [], set()
    for segment in sequence:
        if not isinstance(segment, dict):
            raise TypeError('sequence segment must be a mapping')
        if set(segment) != {'segment_id', 'case_id', 'duration_s', 'source_note', 'power_profile'}:
            raise ValueError('sequence segment needs exactly ID, case, duration, source and constant power profile')
        name = segment.get('segment_id')
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError('sequence segment IDs must be meaningful and unique')
        names.add(name)
        case = inputs.get(segment.get('case_id'))
        if case is None:
            raise ValueError('sequence requires an eligible case: ' + str(segment.get('case_id')))
        if (segment.get('power_profile') != 'constant' or not isinstance(segment.get('source_note'), str)
                or not segment['source_note'].strip()):
            raise ValueError('sequence needs explicitly sourced constant-condition segments')
        duration = number(segment.get('duration_s'), 'sequence duration', positive=True)
        if duration > case.duration_s:
            raise ValueError('segment duration exceeds its declared case duration')
        records.append({**segment, 'duration_s': duration})
    total = math.fsum(record['duration_s'] for record in records)
    # No cooling/reset model: continuous coverage must span the complete flight.
    if any(total > model.max_continuous_duration_s for name, case in inputs.items()
           if any(s['case_id'] == name for s in records) for model in case.maps):
        raise ValueError('sequence exceeds retained continuous-duration coverage; no cooling reset is assumed')
    return records


def joint_constraints(inputs: dict, sequence: list[dict]):
    cases = list(inputs.values())
    widths = [2*len(case.rotors) for case in cases]
    size = sum(widths)+1
    equalities, rhs, inequalities, upper, bounds = [], [], [], [], []
    energy_row = np.zeros(size); auxiliary_j = 0.; offset = 0
    durations = {name: math.fsum(s['duration_s'] for s in sequence if s['case_id'] == name)
                 for name in inputs}
    for name, case, width in zip(inputs, cases, widths, strict=True):
        eq, b_eq, a, b, local_bounds, _ = constraints(case)
        indices = [*range(offset, offset+width), size-1]
        full_eq = np.zeros((len(eq), size)); full_eq[:, indices] = eq
        full_a = np.zeros((len(a), size)); full_a[:, indices] = a
        equalities.extend(full_eq); rhs.extend(b_eq); inequalities.extend(full_a); upper.extend(b)
        bounds.extend(local_bounds[:-1])
        n = len(case.rotors)
        energy_row[offset+n:offset+2*n] = durations[name]
        auxiliary_j += durations[name]*case.auxiliary_w
        offset += width
    bounds.append((max(case.payload_bounds[0] for case in cases),
                   min(case.payload_bounds[1] for case in cases)))
    if bounds[-1][0] > bounds[-1][1]:
        raise ValueError('case payload domains have no common intersection')
    usable = min(case.usable_j for case in cases)
    inequalities.append(energy_row); upper.append(usable-auxiliary_j)
    return np.array(equalities), np.array(rhs), np.array(inequalities), np.array(upper), bounds


def solve_sequence(inputs: dict, sequence: list[dict]) -> dict:
    eq, rhs, a, b, bounds = joint_constraints(inputs, sequence)
    objective = np.zeros(len(bounds)); objective[-1] = -1
    try:
        solved = linprog(objective, A_eq=eq, b_eq=rhs, A_ub=a, b_ub=b, bounds=bounds,
                         method='highs', options={'time_limit': 2., 'maxiter': 10000})
    except (ValueError, RuntimeError) as exc:
        return {'outcome': 'unresolved', 'reason': 'joint numerical allocation failed: ' + str(exc)}
    if not solved.success or solved.x is None:
        certificate = infeasibility_certificate(eq, rhs, a, b, bounds) if solved.status == 2 else None
        origins = [o for case in inputs.values() for o in bound_origins(case)[:-1]]
        origins.append({'lower': 'physical' if bounds[-1][0] == 0 else 'analyst_domain', 'upper': 'analyst_domain'})
        outcome = classify_certificate(certificate, eq, a, bounds, origins) if certificate else 'unresolved'
        return {'outcome': outcome,
                'reason': ('Coverage or analyst-domain bounds prevent this sequence; physical infeasibility is not established.'
                           if outcome == 'unsupported' else solved.message),
                'certificate': certificate}
    if not np.isfinite(solved.x).all() or any(v < lo or v > hi for v, (lo, hi)
                                                           in zip(solved.x, bounds, strict=True)):
        return {'outcome': 'unresolved', 'reason': 'joint solver command outside finite declared bounds'}
    payload = float(solved.x[-1])
    checks = [{'case_id': name, **solve_hover(case, payload_kg=payload)} for name, case in inputs.items()]
    if any(check['outcome'] != 'feasible' for check in checks):
        return {'outcome': 'unresolved', 'reason': 'joint candidate failed independent case trim',
                'headline_candidate_checks': checks}
    by_case = {check['case_id']: check['candidate'] for check in checks}
    usable = min(case.usable_j for case in inputs.values()); consumed = 0.; records = []
    for segment in sequence:
        power = by_case[segment['case_id']]['electrical_power_w']
        energy = power*segment['duration_s']; consumed += energy
        records.append({**segment, 'electrical_power_w': power, 'energy_required_j': energy,
                        'remaining_usable_energy_j': usable-consumed})
    energy_tolerance = 1e-7 * max(1., usable)
    if consumed > usable+energy_tolerance:
        return {'outcome': 'unresolved', 'reason': 'recomputed sequence exceeds fixed-pack budget',
                'headline_candidate_checks': checks}
    return {'outcome': 'feasible', 'payload_kg': payload, 'headline_candidate_checks': checks,
            'sequence_evidence': {'segments': records, 'total_energy_j': consumed, 'usable_energy_j': usable,
                                  'remaining_usable_energy_j': usable-consumed,
                                  'energy_tolerance_j': energy_tolerance,
                                  'reserve_convention': 'held_usable_energy_fraction_applied_once',
                                  'integration_method': 'constant_power_exact_v1'}}
