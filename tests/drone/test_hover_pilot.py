"""Independent closed-form capacity, wrench, source-domain and certificate fixtures."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

from physimesh.drone.atmosphere import G0, R_AIR
from physimesh.drone.capacity import capacity_from_snapshot
from physimesh.drone.trim import constraints, prepare_hover, solve_hover
from physimesh.projects.performance import parse_map


def fixture():
    raw = json.loads((Path(__file__).parents[1] / 'projects/fixtures/incomplete_draft.json').read_text())
    snapshot = json.loads(raw['snapshot_json'])
    snapshot['identity']['data_scope'] = 'analytic_fixture'
    snapshot['masses']['items'] = [{'name': cat, 'category': cat, 'mass_kg': mass, 'cg_body_m': [0, 0, 0]}
                                  for cat, mass in [('structure', 10), ('energy', 2), ('payload', 0),
                                                    ('propulsion', 0), ('avionics', 0), ('other', 0)]]
    snapshot['mission']['payload_positions_body_m'] = [[0, 0, 0]]
    snapshot['mission']['energy_system'] = {'pack_mass_item_names': ['energy'], 'pack_wh_per_kg': 100,
        'usable_fraction': .8, 'usable_energy_j': 460800., 'nominal_voltage_v': 50.,
        'max_electrical_power_w': 10000., 'max_current_a': 200., 'mode': 'fixed',
        'voltage_model': 'declared_constant_bus'}
    snapshot['mission']['reserve_policy'] = {'kind': 'fraction', 'value': .2,
                                            'convention': 'held_usable_energy_fraction'}
    snapshot['mission']['cases'] = [{'name': 'hover', 'kind': 'hover', 'required': True, 'duration_s': 10.,
        'attitude_deg_zyx': [0, 0, 0], 'velocity_world_m_s': [0, 0, 0],
        'acceleration_target_m_s2': [0, 0, 0], 'air_relative_velocity_body_m_s': [0, 0, 0],
        'source_note': 'Analytic fixture', 'body_force_body_n': [0, 0, 0],
        'body_moment_origin_body_nm': [0, 0, 0], 'body_load_source': 'Explicit analytic zero loads'}]
    snapshot['atmosphere'] = {'pressure_pa': 101325., 'temperature_k': 288.15, 'source': 'Analytic fixture'}
    snapshot['fidelity']['local_pilot'] = {'model_version': 'convex_static_hover_v1',
                                         'payload_domain_kg': [0., 100.], 'auxiliary_power_w': 0.}
    dataset = {'schema_version': 'rotor_map_v1', 'dataset_id': 'analytic-map', 'configuration_id': 'fixture-rotor',
        'source_kind': 'analytic_fixture', 'source_description': 'Artificial linear curve for independent math checks',
        'units': 'rpm_N_Nm_W', 'torque_convention': 'absorbed_shaft_magnitude',
        'density_kg_m3': 101325/(R_AIR*288.15), 'axial_inflow_m_s': 0., 'pitch_deg': 0.,
        'max_continuous_duration_s': 3600., 'power_basis': 'electrical', 'covered_intervals_rpm': [[0., 1000.]],
        'points': [{'rpm': rpm, 'thrust_n': thrust, 'shaft_torque_nm': .02*thrust, 'power_w': 10*thrust}
                   for rpm, thrust in [(0., 0.), (500., 50.), (1000., 100.)]]}
    model = parse_map(json.dumps(dataset).encode())
    snapshot['rotors'] = [{'rotor_id': 'r'+str(i), 'center_body_m': [x, y, 0], 'axis_body': [0, 0, 1],
        'rotation_sign': sign, 'configuration_id': 'fixture-rotor', 'map_ref': 'fixture', 'pitch_deg': 0.,
        'sustained_limits': {'max_rpm': 1000., 'max_electrical_power_w': 2000., 'max_input_current_a': 40.}}
        for i, (x, y, sign) in enumerate([(1, 1, 1), (-1, 1, -1), (-1, -1, 1), (1, -1, -1)])]
    return snapshot, dataset, {'fixture': model}


def test_closed_form_symmetric_capacity_and_signed_reaction_wrench():
    snapshot, _, maps = fixture()
    report = capacity_from_snapshot(snapshot, maps)
    assert report['outcome'] == 'feasible'
    assert report['payload_lower_bound_kg'] == pytest.approx(400/G0-12)
    candidate = report['cases'][0]['candidate']
    assert candidate['force_residual_n'] == pytest.approx([0, 0, 0], abs=1e-8)
    assert candidate['moment_residual_cg_nm'] == pytest.approx([0, 0, 0], abs=1e-8)
    assert candidate['commands'][0]['reaction_torque_body_nm'][2] == pytest.approx(-2)
    assert candidate['commands'][1]['reaction_torque_body_nm'][2] == pytest.approx(2)


def test_power_auxiliary_energy_and_every_required_case():
    snapshot, _, maps = fixture()
    snapshot['mission']['energy_system']['max_electrical_power_w'] = 3000.
    snapshot['fidelity']['local_pilot']['auxiliary_power_w'] = 100.
    report = capacity_from_snapshot(snapshot, maps)
    assert report['payload_lower_bound_kg'] == pytest.approx(290/G0-12)
    long = copy.deepcopy(snapshot['mission']['cases'][0]); long.update(name='long_hover', duration_s=300.)
    snapshot['mission']['cases'].append(long)
    report = capacity_from_snapshot(snapshot, maps)
    assert report['limiting_case_id'] == 'long_hover'
    assert report['payload_lower_bound_kg'] == pytest.approx((460800/300-100)/10/G0-12)
    snapshot['mission']['cases'][1]['air_relative_velocity_body_m_s'] = [1, 0, 0]
    report = capacity_from_snapshot(snapshot, maps)
    assert report['outcome'] == 'unsupported' and report['payload_lower_bound_kg'] is None


def test_shifted_payload_requires_asymmetric_allocation():
    snapshot, _, maps = fixture(); snapshot['mission']['payload_positions_body_m'] = [[.4, 0, 0]]
    prepared = prepare_hover(snapshot, snapshot['mission']['cases'][0], maps)
    result = solve_hover(prepared, payload_kg=10.)
    assert result['outcome'] == 'feasible'
    candidate = result['candidate']
    assert candidate['cg_body_m'][0] == pytest.approx(4/22)
    assert max(abs(v) for v in candidate['moment_residual_cg_nm']) < 1e-7
    right = sum(c['thrust_n'] for c in candidate['commands'] if c['rotor_id'] in ('r0', 'r3'))
    left = sum(c['thrust_n'] for c in candidate['commands'] if c['rotor_id'] in ('r1', 'r2'))
    assert right-left == pytest.approx(4*G0)


def test_impossible_yaw_has_independently_recomputable_certificate():
    snapshot, _, maps = fixture()
    for rotor in snapshot['rotors']:
        rotor['rotation_sign'] = 1
    prepared = prepare_hover(snapshot, snapshot['mission']['cases'][0], maps)
    result = solve_hover(prepared)
    assert result['outcome'] == 'infeasible'
    eq, rhs, a, b, bounds, _ = constraints(prepared)
    size = len(bounds)
    rows = np.vstack([a, eq, -eq, np.eye(size), -np.eye(size)])
    upper = np.concatenate([b, rhs, -rhs, [hi for lo, hi in bounds], [-lo for lo, hi in bounds]])
    cert = result['certificate']; weights = np.array(cert['multipliers'])/np.array(cert['row_scaling'])
    assert min(weights) >= 0
    combined = weights@rows
    lower = sum(c*(lo if c >= 0 else hi) for c, (lo, hi) in zip(combined, bounds, strict=True))
    assert lower-weights@upper > cert['rounding_guard']


def test_nonconvex_torque_or_power_and_map_holes_are_unsupported():
    snapshot, data, _ = fixture()
    for changed in ('torque', 'power', 'holes'):
        raw = copy.deepcopy(data)
        if changed == 'torque': raw['points'][1]['shaft_torque_nm'] = .8
        if changed == 'power': raw['points'][1]['power_w'] = 800.
        if changed == 'holes': raw['covered_intervals_rpm'] = [[0., 400.], [600., 1000.]]
        model = parse_map(json.dumps(raw).encode())
        report = capacity_from_snapshot(snapshot, {'fixture': model})
        assert report['outcome'] == 'unsupported' and report['payload_lower_bound_kg'] is None


def test_map_coverage_and_double_efficiency_refuse():
    _, data, maps = fixture(); model = maps['fixture']
    with pytest.raises(ValueError, match='density'):
        model.evaluate(500, density=1., inflow=0., pitch=0.)
    with pytest.raises(ValueError, match='covered'):
        model.evaluate(1001, density=model.density_kg_m3, inflow=0., pitch=0.)
    data['efficiency'] = .8
    with pytest.raises(ValueError, match='again'):
        parse_map(json.dumps(data).encode())


def test_zero_payload_is_not_assumed_feasible_for_every_design():
    snapshot, _, maps = fixture(); snapshot['masses']['items'][0]['cg_body_m'] = [2, 0, 0]
    snapshot['mission']['payload_positions_body_m'] = [[-1, 0, 0]]
    prepared = prepare_hover(snapshot, snapshot['mission']['cases'][0], maps)
    assert solve_hover(prepared, payload_kg=0)['outcome'] == 'infeasible'
    result = solve_hover(prepared)
    assert result['outcome'] == 'feasible' and result['candidate']['payload_kg'] > 0


def sequence(snapshot, durations):
    snapshot['mission']['cases'][0]['duration_s'] = max(durations)
    snapshot['mission']['sequence'] = [{'segment_id': f'leg_{i}', 'case_id': 'hover', 'duration_s': dt,
        'power_profile': 'constant', 'source_note': 'Analytic ordered constant condition'}
        for i, dt in enumerate(durations)]


def test_sequence_aggregate_binds_below_individually_feasible_cases():
    snapshot, _, maps = fixture(); sequence(snapshot, [150., 150., 60.])
    report = capacity_from_snapshot(snapshot, maps)
    assert report['outcome'] == 'feasible'
    assert report['payload_lower_bound_kg'] == pytest.approx(460800/360/10/G0-12)
    assert report['payload_lower_bound_kg'] < report['cases'][0]['candidate']['payload_kg']
    assert report['limiting_case_id'] is None and report['aggregate_limit'] == 'sequence_energy'
    evidence = report['sequence_evidence']
    assert evidence['total_energy_j'] == pytest.approx(460800)
    assert evidence['segments'][0]['remaining_usable_energy_j'] == pytest.approx(460800*(1-150/360))
    assert evidence['remaining_usable_energy_j'] == pytest.approx(0, abs=1e-7)


def test_sequence_reserve_once_and_exhausted_empty_aircraft():
    snapshot, _, maps = fixture(); sequence(snapshot, [200., 200.])
    report = capacity_from_snapshot(snapshot, maps)
    assert report['outcome'] == 'infeasible' and report['payload_lower_bound_kg'] is None
    assert report['certificate']['gap'] > report['certificate']['rounding_guard']
    snapshot['mission']['reserve_policy']['value'] = 0.
    snapshot['mission']['energy_system']['usable_energy_j'] = 576000.
    report = capacity_from_snapshot(snapshot, maps)
    assert report['payload_lower_bound_kg'] == pytest.approx(576000/400/10/G0-12)


def test_unsupported_sequence_transient_and_continuous_coverage():
    snapshot, _, maps = fixture(); sequence(snapshot, [10.])
    snapshot['mission']['sequence'][0]['power_profile'] = 'variable'
    assert capacity_from_snapshot(snapshot, maps)['outcome'] == 'unsupported'
    sequence(snapshot, [2000., 2000.])
    assert 'continuous-duration' in capacity_from_snapshot(snapshot, maps)['reasons'][0]


def test_failed_numerics_and_bogus_success_withhold_capacity(monkeypatch):
    from types import SimpleNamespace
    snapshot, _, maps = fixture()
    prepared = prepare_hover(snapshot, snapshot['mission']['cases'][0], maps)
    monkeypatch.setattr('physimesh.drone.trim.linprog', lambda *a, **k:
                        SimpleNamespace(success=False, status=1, x=None, message='time limit'))
    assert solve_hover(prepared)['outcome'] == 'unresolved'
    monkeypatch.setattr('physimesh.drone.trim.linprog', lambda *a, **k:
                        SimpleNamespace(success=True, status=0, x=np.zeros(9), message='success'))
    assert solve_hover(prepared)['outcome'] == 'unresolved'


def test_shaft_efficiency_once_and_inconsistent_watts_refuse():
    _, data, _ = fixture(); data.update(power_basis='shaft', efficiency=.8, efficiency_source='Fixture efficiency')
    for p in data['points']:
        p['power_w'] = p['shaft_torque_nm']*p['rpm']*2*np.pi/60
    model = parse_map(json.dumps(data).encode())
    point = model.evaluate(750., density=model.density_kg_m3, inflow=0., pitch=0.)
    assert point['electrical_power_w'] == pytest.approx(1.5*750*2*np.pi/60/.8)
    with pytest.raises(ValueError, match='constant absorbed torque'):
        model.convex_static_profile()
    data['points'][1]['power_w'] += 1.
    with pytest.raises(ValueError, match='shaft watts'):
        parse_map(json.dumps(data).encode())
