"""Eligibility and pack consistency for the bounded vertical screening adapter.

These are input consistency gates, never six-degree-of-freedom trim or battery
validation. The 1e-9 zero tolerance is numerical, not a flight-control margin.
"""
import math
from collections.abc import Mapping

import numpy as np

MAX_MARGIN_DURATION_S = 2.0  # Bounded illustration policy, not a physical trajectory-validity limit.


def pack_consistency(project: dict) -> dict:
    try:
        energy = project['mission']['energy_system']
        reserve = project['mission']['reserve_policy']
        names = energy.get('pack_mass_item_names')
        items = project['masses']['items']
        by_name = {item['name']: item for item in items}
        if (not isinstance(names, list) or not names or any(not isinstance(n, str) for n in names)
                or len(set(names)) != len(names) or len(by_name) != len(items)
                or any(n not in by_name or by_name[n]['category'] != 'energy' for n in names)):
            raise ValueError('select unique energy-category battery mass items explicitly')
        mass = math.fsum(by_name[n]['mass_kg'] for n in names)
        density, fraction, declared = (energy.get(k) for k in ('pack_wh_per_kg', 'usable_fraction', 'usable_energy_j'))
        if not isinstance(reserve, Mapping) or reserve.get('kind') != 'fraction':
            raise ValueError('reserve must be a fraction of usable pack energy')
        r = reserve.get('value')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               for v in (mass, density, fraction, declared, r)):
            raise ValueError('finite numeric pack mass, density, usable fraction, reserve and energy required')
        if mass <= 0 or density <= 0 or not 0 < fraction <= 1 or not 0 <= r < 1 or declared <= 0:
            raise ValueError('positive pack mass/energy and bounded fractions required')
        derived = mass * density * fraction * (1-r) * 3600
        if not math.isfinite(derived) or derived <= 0:
            raise ValueError('derived pack energy overflowed or underflowed')
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        return {'status': 'inputs_incomplete', 'code': 'pack_inputs_unresolved', 'detail': str(exc)}
    return {'status': 'consistent' if math.isclose(declared, derived, rel_tol=1e-9, abs_tol=0) else 'inconsistent',
            'code': 'pack_energy_consistency', 'pack_mass_kg': mass, 'pack_mass_item_names': names,
            'derived_usable_energy_j': derived, 'declared_usable_energy_j': declared,
            'relative_tolerance': 1e-9,
            'formula': 'm_pack * pack_Wh_per_kg * usable_fraction * (1-reserve_fraction) * 3600',
            'reserve_convention': 'fraction of usable pack energy held back once',
            'qualification': 'Declared parameter consistency only; no measured pack capacity or power validation.'}


def case_scope(case: dict, rotors: list[dict]) -> list[str]:
    """Refuse unsupported geometry/conditions before publishing a vertical ceiling."""
    issues = []
    try:
        attitude = np.asarray(case['attitude_deg_zyx'], float)
        acceleration = np.asarray(case['acceleration_target_m_s2'], float)
        velocity = np.asarray(case['velocity_world_m_s'], float)
        if any(v.shape != (3,) or not np.isfinite(v).all() for v in (attitude, acceleration, velocity)):
            raise ValueError('finite attitude, velocity and acceleration three-vectors required')
        if np.max(np.abs(attitude[1:])) > 1e-9:
            issues.append('nonzero pitch/roll requires trim')
        if np.max(np.abs(acceleration[:2])) > 1e-9 or np.max(np.abs(velocity[:2])) > 1e-9:
            issues.append('horizontal velocity/acceleration requires a supported trim model')
        for rotor in rotors:
            axis = np.asarray(rotor['axis_body'], float)
            if axis.shape != (3,) or not np.isfinite(axis).all() or not np.allclose(axis, [0, 0, 1], atol=1e-9, rtol=0):
                issues.append(f"rotor {rotor.get('rotor_id')}: tilted or unresolved rotor axis requires trim")
        scope = case.get('analysis_scope')
        if scope not in ('constant_operating_point', 'instantaneous_vertical_margin'):
            issues.append('declare constant operating point or instantaneous vertical margin scope')
        if scope == 'constant_operating_point' and abs(acceleration[2]) > 1e-9:
            issues.append('nonzero acceleration is not a constant velocity operating point')
        # Duration means a constant-point energy illustration, not integrating
        # this acceleration into a trajectory at unchanged thrust/velocity.
        if scope == 'instantaneous_vertical_margin' and case.get('kind') != 'acceleration_margin':
            issues.append('instantaneous margin must be labelled acceleration_margin')
        if scope == 'instantaneous_vertical_margin':
            duration = case.get('duration_s')
            if (isinstance(duration, bool) or not isinstance(duration, (int, float)) or
                    not math.isfinite(duration) or not 0 < duration <= MAX_MARGIN_DURATION_S):
                issues.append('instantaneous margin duration must be at most 2 s; longer segments require a trajectory model')
    except (KeyError, TypeError, ValueError) as exc:
        issues.append(f'operating scope unresolved: {exc}')
    return [f"case {case.get('name')}: {issue}" for issue in issues]
