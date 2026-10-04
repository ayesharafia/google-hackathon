"""Restricted static map trim: linear allocation, independently recomputed wrench.

ADR-0003 defines coverage. Solver status alone never establishes feasibility.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from .atmosphere import G0, R_AIR
from .authoring import candidate_mass
from .performance import RotorMapV1
from .screening_scope import pack_consistency

MODEL_VERSION = 'convex_static_hover_v1'
RESIDUAL_REL = 1e-8
RESIDUAL_ABS_N = 1e-7
RESIDUAL_ABS_NM = 1e-7


def number(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + ': finite numeric input required')
    if value < 0 or (positive and value <= 0):
        raise ValueError(name + ': positive input required' if positive else name + ': nonnegative input required')
    return float(value)


def vector(value, name):
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value)):
        raise ValueError(name + ': three finite numeric components required')
    return np.asarray(value, float)


@dataclass
class HoverInputs:
    snapshot: dict
    case: dict
    rotors: list[dict]
    maps: list[RotorMapV1]
    profiles: list[dict]
    position: np.ndarray
    empty_mass: float
    empty_cg: np.ndarray
    density: float
    body_force: np.ndarray
    body_moment: np.ndarray
    auxiliary_w: float
    usable_j: float
    voltage_v: float
    pack_limit_w: float
    rotor_limits_w: list[float]
    thrust_bounds: list[tuple[float, float]]
    payload_bounds: tuple[float, float]
    duration_s: float


def prepare_hover(snapshot: dict, case: dict, sources: dict[str, RotorMapV1]) -> HoverInputs:
    frames = snapshot['units_and_frames']
    if not isinstance(frames, dict) or not isinstance(snapshot['fidelity'], dict):
        raise TypeError('frames and fidelity must be explicit mappings')
    allowed_case = {'name', 'kind', 'required', 'duration_s', 'attitude_deg_zyx', 'velocity_world_m_s',
                    'acceleration_target_m_s2', 'air_relative_velocity_body_m_s', 'angular_velocity_body_rad_s',
                    'angular_acceleration_body_rad_s2', 'source_note', 'body_force_body_n',
                    'body_moment_origin_body_nm', 'body_load_source', 'atmosphere', 'ground_clearance_m', 'mass_state'}
    if set(case)-allowed_case or case.get('ground_clearance_m') is not None or case.get('mass_state') is not None:
        raise ValueError('case has unsupported physical declarations; initial profile uses explicit static ledger inputs')
    if frames.get('body_frame') != 'x_forward_y_left_z_up' or frames.get('world_frame') != 'ENU_z_up':
        raise ValueError('static profile requires the declared z-up body/world conventions')
    for key in ('attitude_deg_zyx', 'velocity_world_m_s', 'acceleration_target_m_s2',
                'air_relative_velocity_body_m_s', 'angular_velocity_body_rad_s',
                'angular_acceleration_body_rad_s2'):
        if np.any(vector(case.get(key), key) != 0):
            raise ValueError(key + ': nonzero conditions outside static-hover profile')
    if (case.get('kind') != 'hover' or not isinstance(case.get('source_note'), str)
            or not case['source_note'].strip()):
        raise ValueError('declare a sourced static hover case')
    body_force = vector(case.get('body_force_body_n'), 'body_force_body_n')
    body_moment = vector(case.get('body_moment_origin_body_nm'), 'body_moment_origin_body_nm')
    if not isinstance(case.get('body_load_source'), str) or not case['body_load_source'].strip():
        raise ValueError('body_load_source: explicit load source required, including a zero-load fixture')
    settings = snapshot['fidelity'].get('local_pilot')
    if not isinstance(settings, dict) or settings.get('model_version') != MODEL_VERSION:
        raise ValueError('declare local_pilot model_version ' + MODEL_VERSION)
    if snapshot['identity'].get('data_scope') not in ('analytic_fixture', 'client_unvalidated'):
        raise ValueError('declare analytic_fixture or client_unvalidated data_scope')
    low, high = settings.get('payload_domain_kg', (None, None))
    low, high = number(low, 'payload domain lower'), number(high, 'payload domain upper')
    if low > high:
        raise ValueError('payload domain is reversed')
    positions = snapshot['mission'].get('payload_positions_body_m')
    if not isinstance(positions, list) or len(positions) != 1:
        raise ValueError('initial profile requires one explicit payload position')
    position = vector(positions[0], 'payload position')
    empty = candidate_mass(snapshot, 0, position.tolist())
    if not empty.complete:
        raise ValueError('mass ledger: ' + '; '.join(empty.missing + empty.errors))
    pack = pack_consistency(snapshot)
    if pack['status'] != 'consistent':
        raise ValueError('pack consistency: ' + pack.get('detail', pack['status']))
    energy = snapshot['mission']['energy_system']
    if energy.get('mode') != 'fixed' or energy.get('voltage_model') != 'declared_constant_bus':
        raise ValueError('initial profile needs fixed pack and declared_constant_bus voltage model')
    voltage = number(energy.get('nominal_voltage_v'), 'nominal bus voltage', positive=True)
    pack_limit = min(number(energy.get('max_electrical_power_w'), 'pack power limit', positive=True),
                     voltage * number(energy.get('max_current_a'), 'pack input current limit', positive=True))
    duration = number(case.get('duration_s'), 'duration_s', positive=True)
    atmosphere = case.get('atmosphere', snapshot['atmosphere'])
    if not isinstance(atmosphere, dict):
        raise TypeError('atmosphere must be an explicitly declared mapping')
    if not isinstance(atmosphere.get('source'), str) or not atmosphere['source'].strip():
        raise ValueError('atmosphere source required')
    density = number(atmosphere.get('pressure_pa'), 'absolute Pa', positive=True) / (
        R_AIR * number(atmosphere.get('temperature_k'), 'temperature K', positive=True))
    rotors = snapshot['rotors']
    if (not isinstance(rotors, list) or not 1 <= len(rotors) <= 16
            or any(not isinstance(r, dict) or not isinstance(r.get('rotor_id'), str)
                   or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', r['rotor_id']) is None for r in rotors)
            or len({r['rotor_id'] for r in rotors}) != len(rotors)):
        raise ValueError('1-16 uniquely identified rotors required')
    maps, profiles, limits, bounds = [], [], [], []
    for rotor in rotors:
        axis = vector(rotor.get('axis_body'), 'rotor axis')
        vector(rotor.get('center_body_m'), 'rotor centre')
        if not math.isclose(float(np.linalg.norm(axis)), 1, rel_tol=0, abs_tol=1e-9):
            raise ValueError('rotor axis must already be a unit vector')
        if type(rotor.get('rotation_sign')) is not int or rotor['rotation_sign'] not in (-1, 1):
            raise ValueError('rotation_sign must declare signed shaft rotation (+1 or -1)')
        model = sources.get(rotor.get('map_ref'))
        if model is None or rotor.get('configuration_id') != model.configuration_id:
            raise ValueError('rotor configuration must bind a retained map')
        profile = model.convex_static_profile()
        model.evaluate(model.points[0].rpm, density=density, inflow=0, pitch=rotor.get('pitch_deg'))
        if duration > model.max_continuous_duration_s:
            raise ValueError('case exceeds map continuous-duration coverage')
        declared = rotor.get('sustained_limits', {})
        if not isinstance(declared, dict):
            raise TypeError('sustained_limits must be an explicit mapping')
        maximum_rpm = min(number(declared.get('max_rpm'), 'continuous RPM limit', positive=True),
                          model.points[-1].rpm)
        if maximum_rpm < model.points[0].rpm:
            raise ValueError('continuous RPM limit is below map coverage')
        limit = min(number(declared.get('max_electrical_power_w'), 'rotor continuous input power', positive=True),
                    voltage * number(declared.get('max_input_current_a'), 'rotor DC input current', positive=True))
        bounds.append((model.points[0].thrust_n,
                       model.evaluate(maximum_rpm, density=density, inflow=0,
                                      pitch=rotor['pitch_deg'])['thrust_n']))
        maps.append(model); profiles.append(profile); limits.append(limit)
    return HoverInputs(snapshot, case, rotors, maps, profiles, position, empty.total_mass_kg,
                       empty.cg_body_m, density, body_force, body_moment,
                       number(settings.get('auxiliary_power_w'), 'auxiliary watts'),
                       pack['derived_usable_energy_j'], voltage, pack_limit, limits, bounds, (low, high), duration)


def constraints(inputs: HoverInputs, *, payload_kg=None):
    """Variables: rotor thrust N, electrical epigraph W, payload kg. Origin moments are linear."""
    n = len(inputs.rotors); size = 2*n+1
    eq = np.zeros((6, size)); constant_torque = np.zeros(3)
    for i, (rotor, profile) in enumerate(zip(inputs.rotors, inputs.profiles, strict=True)):
        axis = np.array(rotor['axis_body']); centre = np.array(rotor['center_body_m'])
        reaction = -rotor['rotation_sign'] * axis
        eq[:3, i] = axis
        eq[3:, i] = np.cross(centre, axis) + reaction * profile['torque_slope']
        constant_torque += reaction * profile['torque_offset']
    gravity = np.array([0, 0, -G0])
    eq[:3, -1] = gravity; eq[3:, -1] = np.cross(inputs.position, gravity)
    rhs = np.concatenate((-inputs.body_force - inputs.empty_mass*gravity,
                          -inputs.body_moment - constant_torque
                          - np.cross(inputs.empty_mass*inputs.empty_cg, gravity)))
    inequalities, upper, names = [], [], []
    for i, profile in enumerate(inputs.profiles):
        for slope, offset in zip(profile['power_slopes'], profile['power_offsets'], strict=True):
            row = np.zeros(size); row[i] = slope; row[n+i] = -1
            inequalities.append(row); upper.append(-offset); names.append(f'rotor_{i}_power_curve')
    row = np.zeros(size); row[n:2*n] = 1
    inequalities.extend((row.copy(), row.copy()))
    upper.extend((inputs.pack_limit_w-inputs.auxiliary_w,
                  inputs.usable_j/inputs.duration_s-inputs.auxiliary_w))
    names.extend(('pack_power_or_current', 'case_energy'))
    bounds = inputs.thrust_bounds + [(0, limit) for limit in inputs.rotor_limits_w]
    bounds.append(inputs.payload_bounds if payload_kg is None else (payload_kg, payload_kg))
    return eq, rhs, np.array(inequalities), np.array(upper), bounds, names


def bound_origins(inputs: HoverInputs, *, fixed_payload=False):
    origins = [{'lower': 'physical' if lo == 0 else 'coverage',
                'upper': ('physical' if rotor['sustained_limits']['max_rpm'] <= model.points[-1].rpm
                          else 'coverage')}
               for rotor, model, (lo, _hi) in zip(inputs.rotors, inputs.maps, inputs.thrust_bounds, strict=True)]
    origins += [{'lower': 'physical', 'upper': 'physical'} for _ in inputs.rotors]
    origins += [{'lower': ('fixed_candidate' if fixed_payload else 'physical'
                           if inputs.payload_bounds[0] == 0 else 'analyst_domain'),
                 'upper': 'fixed_candidate' if fixed_payload else 'analyst_domain'}]
    return origins


def source_domain_gaps(inputs: HoverInputs):
    gaps = []
    for rotor, model in zip(inputs.rotors, inputs.maps, strict=True):
        if model.points[0].rpm > 0:
            gaps.append({'rotor_id': rotor['rotor_id'], 'gap': 'below_retained_rpm'})
        if rotor['sustained_limits']['max_rpm'] > model.points[-1].rpm:
            gaps.append({'rotor_id': rotor['rotor_id'], 'gap': 'above_retained_rpm'})
    return gaps


def classify_certificate(certificate, eq, inequalities, bounds, origins, source_gaps=()):
    """A bounded-model contradiction is not necessarily a physical-limit decision."""
    size = len(bounds); base = len(inequalities)+2*len(eq)
    weights = np.array(certificate['multipliers'])/np.array(certificate['row_scaling'])
    rows = np.vstack((inequalities, eq, -eq, np.eye(size), -np.eye(size)))
    combined = weights @ rows
    dependencies = []
    for i, (origin, (lo, hi)) in enumerate(zip(origins, bounds, strict=True)):
        for side, row in [('upper', base+i), ('lower', base+size+i)]:
            if origin[side] in ('coverage', 'analyst_domain') and weights[row] > 0:
                dependencies.append({'variable_index': i, 'side': side, 'origin': origin[side]})
        side = 'lower' if combined[i] >= 0 else 'upper'
        if (origin[side] in ('coverage', 'analyst_domain')
                and abs(combined[i])*(hi-lo) > certificate['rounding_guard']):
            dependencies.append({'variable_index': i, 'side': side, 'origin': origin[side]})
    certificate['bound_origins'] = origins
    certificate['nonphysical_bound_dependencies'] = dependencies
    certificate['source_domain_gaps'] = list(source_gaps)
    certificate['qualification'] = 'Contradiction within the declared model, with bound provenance retained.'
    # Map-derived power/torque rows can prove contradictions without assigning a
    # multiplier to their coverage bound. With unknown admissible RPM states,
    # no such source-equation certificate establishes physical infeasibility.
    return 'unsupported' if dependencies or source_gaps else 'infeasible'


def infeasibility_certificate(eq, rhs, inequalities, upper, bounds):
    """Independently check a nonnegative combination against finite variable bounds."""
    size = len(bounds); identity = np.eye(size)
    a = np.vstack((inequalities, eq, -eq, identity, -identity))
    b = np.concatenate((upper, rhs, -rhs, [hi for lo, hi in bounds], [-lo for lo, hi in bounds]))
    scale = np.maximum(1, np.maximum(np.max(np.abs(a), axis=1), np.abs(b)))
    a = a/scale[:, None]; b = b/scale
    try:
        dual = linprog(np.zeros(len(b)), A_eq=np.vstack((a.T, b)),
                       b_eq=np.concatenate((np.zeros(size), [-1.])), bounds=(0, None), method='highs',
                       options={'time_limit': 1., 'maxiter': 10000})
    except (ValueError, RuntimeError):
        return None
    if not dual.success or dual.x is None or not np.isfinite(dual.x).all():
        return None
    multipliers = np.maximum(dual.x, 0)
    combined = multipliers @ a; combined_bound = float(multipliers @ b)
    minimum = math.fsum(float(coefficient)*(lo if coefficient >= 0 else hi)
                        for coefficient, (lo, hi) in zip(combined, bounds, strict=True))
    gap = minimum-combined_bound
    rounding_guard = 1e-7 * max(1., float(np.sum(np.abs(multipliers*b))), abs(minimum))
    if not math.isfinite(gap) or gap <= rounding_guard:
        return None
    return {'kind': 'bounded_nonnegative_linear_combination', 'gap': gap,
            'rounding_guard': rounding_guard, 'multipliers': multipliers.tolist(),
            'row_scaling': scale.tolist(), 'minimum_over_variable_bounds': minimum,
            'combined_upper_bound': combined_bound}


def recompute(inputs: HoverInputs, payload: float, thrusts: np.ndarray) -> dict:
    mass = candidate_mass(inputs.snapshot, payload, inputs.position.tolist())
    force = inputs.body_force.copy() + np.array([0, 0, -mass.total_mass_kg*G0])
    moment = inputs.body_moment.copy() - np.cross(mass.cg_body_m, inputs.body_force)
    commands = []; power = inputs.auxiliary_w
    for rotor, model, profile, thrust in zip(inputs.rotors, inputs.maps, inputs.profiles, thrusts, strict=True):
        rpm = float(np.interp(thrust, profile['thrust'], profile['rpm']))
        point = model.evaluate(rpm, density=inputs.density, inflow=0, pitch=rotor['pitch_deg'])
        f = np.array(rotor['axis_body'])*point['thrust_n']
        reaction = -rotor['rotation_sign']*np.array(rotor['axis_body'])*point['shaft_torque_nm']
        force += f; moment += np.cross(np.array(rotor['center_body_m'])-mass.cg_body_m, f)+reaction
        power += point['electrical_power_w']
        commands.append({**point, 'rotor_id': rotor['rotor_id'], 'signed_rpm': rotor['rotation_sign']*rpm,
                         'force_body_n': f.tolist(), 'reaction_torque_body_nm': reaction.tolist(),
                         'dc_input_current_a': point['electrical_power_w']/inputs.voltage_v})
    return {'payload_kg': payload, 'total_mass_kg': mass.total_mass_kg, 'cg_body_m': mass.cg_body_m.tolist(),
            'force_residual_n': force.tolist(), 'moment_residual_cg_nm': moment.tolist(),
            'electrical_power_w': power, 'energy_required_j': power*inputs.duration_s, 'commands': commands}


def solve_hover(inputs: HoverInputs, *, payload_kg=None) -> dict:
    if payload_kg is not None and not inputs.payload_bounds[0] <= payload_kg <= inputs.payload_bounds[1]:
        return {'outcome': 'unsupported', 'reason': 'candidate outside the declared payload domain'}
    eq, rhs, a, b, bounds, _names = constraints(inputs, payload_kg=payload_kg)
    n = len(inputs.rotors); objective = np.zeros(2*n+1)
    if payload_kg is None:
        objective[-1] = -1
    else:
        objective[n:2*n] = 1
    try:
        solved = linprog(objective, A_eq=eq, b_eq=rhs, A_ub=a, b_ub=b, bounds=bounds,
                         method='highs', options={'time_limit': 1., 'maxiter': 10000})
    except (ValueError, RuntimeError) as exc:
        return {'outcome': 'unresolved', 'reason': 'numerical allocation failed: ' + str(exc)}
    if not solved.success or solved.x is None:
        certificate = infeasibility_certificate(eq, rhs, a, b, bounds) if solved.status == 2 else None
        outcome = (classify_certificate(certificate, eq, a, bounds,
                                       bound_origins(inputs, fixed_payload=payload_kg is not None),
                                       source_domain_gaps(inputs))
                   if certificate else 'unresolved')
        return {'outcome': outcome,
                'reason': ('Coverage or analyst-domain bounds prevent this study; physical infeasibility is not established.'
                           if outcome == 'unsupported' else solved.message),
                'certificate': certificate, 'solver_status': int(solved.status)}
    if not np.isfinite(solved.x).all():
        return {'outcome': 'unresolved', 'reason': 'solver returned nonfinite commands'}
    # Reject instead of silently clamping an out-of-domain command.
    if any(value < lo or value > hi for value, (lo, hi) in zip(solved.x, bounds, strict=True)):
        return {'outcome': 'unresolved', 'reason': 'solver command outside declared bounds'}
    try:
        report = recompute(inputs, float(solved.x[-1]), solved.x[:n])
    except (ValueError, TypeError, KeyError, OverflowError, RuntimeError) as exc:
        return {'outcome': 'unresolved', 'reason': 'candidate recomputation failed: ' + str(exc)}
    force_scale = max(1., report['total_mass_kg']*G0, float(np.linalg.norm(inputs.body_force)))
    length = max(1., *(float(np.linalg.norm(np.array(r['center_body_m'])-report['cg_body_m']))
                      for r in inputs.rotors))
    force_tol = max(RESIDUAL_ABS_N, RESIDUAL_REL*force_scale)
    moment_tol = max(RESIDUAL_ABS_NM, RESIDUAL_REL*force_scale*length)
    power = report['electrical_power_w']
    violations = []
    if max(abs(v) for v in report['force_residual_n']) > force_tol:
        violations.append('force residual')
    if max(abs(v) for v in report['moment_residual_cg_nm']) > moment_tol:
        violations.append('moment residual')
    if power > min(inputs.pack_limit_w, inputs.usable_j/inputs.duration_s) + 1e-7:
        violations.append('pack power/current or case energy')
    for command, limit, rotor in zip(report['commands'], inputs.rotor_limits_w, inputs.rotors, strict=True):
        if command['electrical_power_w'] > limit+1e-7:
            violations.append('rotor continuous power/current')
        if command['rpm'] > rotor['sustained_limits']['max_rpm']:
            violations.append('recomputed rotor RPM exceeds declared maximum')
    if violations:
        return {'outcome': 'unresolved', 'reason': '; '.join(violations), 'candidate': report}
    active = []
    if abs(power-inputs.pack_limit_w) < 1e-6:
        active.append('pack_power_or_current')
    if abs(power*inputs.duration_s-inputs.usable_j) < 1e-4:
        active.append('case_energy')
    if abs(solved.x[-1]-inputs.payload_bounds[1]) < 1e-6:
        active.append('declared_payload_domain_upper')
    for rotor, thrust, (_, hi) in zip(inputs.rotors, solved.x[:n], inputs.thrust_bounds, strict=True):
        if abs(thrust-hi) < 1e-6:
            active.append(rotor['rotor_id'] + '_map_or_rpm_upper')
    for command, limit in zip(report['commands'], inputs.rotor_limits_w, strict=True):
        if abs(command['electrical_power_w']-limit) < 1e-6:
            active.append(command['rotor_id'] + '_continuous_power_or_current')
    return {'outcome': 'feasible', 'candidate': report, 'active_constraints': active,
            'residual_policy': {'force_tolerance_n': force_tol, 'moment_tolerance_nm': moment_tol,
                                'qualification': 'Numerical fixture policy, not flight acceptance.'},
            'solver_status': int(solved.status),
            'scope': 'Feasible point within the bounded convex static-hover model; not a global aircraft maximum.'}
