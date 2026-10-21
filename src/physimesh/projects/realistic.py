"""Deterministic analytic CT/CQ software fixtures. No licensed/client measurements."""
import json
import math

import numpy as np

from physimesh.drone.atmosphere import R_AIR
from physimesh.drone.conditioning import ConditioningPolicyV1
from physimesh.drone.trim import EXTENDED_MODEL_VERSION

from .examples import create_hover_example
from .performance import retain_conditioned_map, retain_map


def realistic_dataset(noise_fraction=.01, seed=7, *, basis='electrical', inflow=0.):
    """T=rho*n²*D⁴*CT; Q=rho*n²*D⁵*CQ, with bounded seeded noise.

    Thrust/RPM are exact fixture coordinates; only torque and power are perturbed.
    The climb torque multiplier is an explicit artificial input, not a climb law.
    """
    if not 0 <= noise_fraction <= .05 or basis not in ('shaft', 'electrical'):
        raise ValueError('fixture supports 0–5% noise and electrical/shaft basis')
    density = 101325/(R_AIR*288.15); diameter = .8; ct = .12; cq = .006
    rng = np.random.default_rng(seed); points = []
    for rpm in np.linspace(0., 3000., 11):
        n = rpm/60
        thrust = density*n*n*diameter**4*ct
        ideal_torque = density*n*n*diameter**5*cq*(1+.125*inflow)
        torque = ideal_torque*(1+rng.uniform(-noise_fraction, noise_fraction))
        shaft = torque*rpm*2*math.pi/60
        power = shaft if basis == 'shaft' else ideal_torque*rpm*2*math.pi/60/.85*(
            1+rng.uniform(-noise_fraction, noise_fraction))
        points.append({'rpm': float(rpm), 'thrust_n': float(thrust), 'shaft_torque_nm': float(torque),
                       'power_w': float(power)})
    dataset = {'schema_version': 'rotor_map_v1', 'dataset_id': f'analytic-ct-cq-seed-{seed}',
        'configuration_id': 'synthetic-ct-cq-rotor', 'source_kind': 'analytic_fixture',
        'source_description': f'Analytic CT/CQ fixture; seed {seed}; ±{noise_fraction*100:g}% bounded noise. '
                              'Exact thrust/RPM coordinates; not public test data or client measurements. '
                              'Climb torque multiplier 1+0.125*inflow is artificial.',
        'units': 'rpm_N_Nm_W', 'torque_convention': 'absorbed_shaft_magnitude',
        'density_kg_m3': density, 'axial_inflow_m_s': inflow, 'pitch_deg': 0.,
        'max_continuous_duration_s': 3600., 'power_basis': basis,
        'covered_intervals_rpm': [[0., 3000.]], 'points': points}
    if basis == 'shaft':
        dataset.update(efficiency=.85, efficiency_source='Explicit constant-efficiency analytic fixture')
    return dataset


def fixture_policy(noise_fraction=.01):
    return ConditioningPolicyV1(schema_version='rotor_conditioning_policy_v1',
        source_note='Declared analytic-fixture bounds; not engineering acceptance of measured data.',
        torque_relative_residual_tolerance=.08, power_relative_uncertainty=noise_fraction,
        torque_relative_uncertainty=noise_fraction, max_power_shift_fraction=.25)


def create_realistic_example(projects, *, motorout=False):
    project = create_hover_example(projects, 'Synthetic noisy CT/CQ '+('octo motor-out' if motorout else 'hover/climb'))
    snapshot = json.loads(project['snapshot_json'])
    snapshot['identity']['description'] = 'Synthetic noisy CT/CQ '+('octo motor-out' if motorout else 'hover/climb')
    snapshot['fidelity']['local_pilot']['model_version'] = EXTENDED_MODEL_VERSION
    sources = {}
    for inflow in (0., 2.):
        raw = retain_map(projects.artifacts, json.dumps(realistic_dataset(inflow=inflow)).encode())
        sources[inflow] = retain_conditioned_map(projects.artifacts, raw['source_sha256'], fixture_policy())
    if motorout:
        template = snapshot['rotors'][0]
        snapshot['rotors'] = [{**template, 'rotor_id': 'r'+str(i),
            'center_body_m': [math.cos(i*math.pi/4), math.sin(i*math.pi/4), 0.],
            'rotation_sign': 1 if i % 2 == 0 else -1} for i in range(8)]
    for rotor in snapshot['rotors']:
        rotor.update(map_ref=sources[0.]['source_sha256'], configuration_id='synthetic-ct-cq-rotor')
        rotor['sustained_limits'] = {'max_rpm': 3000., 'max_electrical_power_w': 5000., 'max_input_current_a': 100.}
    allowance = 2. if motorout else 1.
    for case in snapshot['mission']['cases']:
        case.update(torque_band_moment_allowance_nm=[0., 0., allowance],
                    torque_band_allowance_source='Synthetic test allowance only; not a flight-acceptance tolerance.')
    case = {**snapshot['mission']['cases'][1], 'name': 'r0_failed' if motorout else 'climb_2ms'}
    if motorout:
        case['failed_rotor_ids'] = ['r0']
    else:
        case.update(kind='axial_climb', axial_inflow_m_s=2., velocity_world_m_s=[0., 0., 2.],
                    air_relative_velocity_body_m_s=[0., 0., -2.],
                    performance_source_by_rotor={r['rotor_id']: sources[2.]['source_sha256']
                                                 for r in snapshot['rotors']})
    snapshot['mission']['cases'].append(case)
    return projects.save(project['project_id'], project['draft_version'], json.dumps(snapshot))
