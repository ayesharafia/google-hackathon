"""Independent closed-form capacity, wrench, source-domain and certificate fixtures."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

from physimesh.drone.atmosphere import G0, R_AIR
from physimesh.drone.capacity import capacity_from_snapshot, hover_readiness
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
        'angular_velocity_body_rad_s': [0, 0, 0], 'angular_acceleration_body_rad_s2': [0, 0, 0],
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
        if changed == 'holes':
            raw['covered_intervals_rpm'] = [[0., 300.], [700., 1000.]]
            raw['points'] = [{'rpm': rpm, 'thrust_n': rpm/10, 'shaft_torque_nm': rpm*.002, 'power_w': rpm}
                             for rpm in [0., 300., 500., 700., 1000.]]
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


def test_unobserved_interval_brackets_refuse_import_and_queries():
    _, data, _ = fixture(); data['points'] = [data['points'][0], data['points'][-1]]
    data['covered_intervals_rpm'] = [[0., 100.], [900., 1000.]]
    with pytest.raises(ValueError, match='cannot bridge holes'):
        parse_map(json.dumps(data).encode())
    data['points'] = [{'rpm': rpm, 'thrust_n': rpm/10, 'shaft_torque_nm': rpm*.002, 'power_w': rpm}
                      for rpm in [0., 100., 900., 1000.]]
    model = parse_map(json.dumps(data).encode())
    assert model.evaluate(50., density=model.density_kg_m3, inflow=0., pitch=0.)['thrust_n'] == 5.
    with pytest.raises(ValueError, match='covered'):
        model.evaluate(500., density=model.density_kg_m3, inflow=0., pitch=0.)


def test_angular_motion_and_missing_angular_declarations_withhold():
    snapshot, _, maps = fixture()
    for key in ('angular_velocity_body_rad_s', 'angular_acceleration_body_rad_s2'):
        changed = copy.deepcopy(snapshot); changed['mission']['cases'][0][key] = [1., 0., 0.]
        assert capacity_from_snapshot(changed, maps)['outcome'] == 'unsupported'
        changed['mission']['cases'][0].pop(key)
        assert capacity_from_snapshot(changed, maps)['outcome'] == 'unsupported'


def test_failed_certificate_is_unresolved_for_case_and_joint(monkeypatch):
    from types import SimpleNamespace
    snapshot, _, maps = fixture()
    prepared = prepare_hover(snapshot, snapshot['mission']['cases'][0], maps)
    for error in (ValueError, RuntimeError):
        calls = []
        def fail_dual(*args, calls=calls, error=error, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                return SimpleNamespace(success=False, status=2, x=None, message='infeasible')
            raise error('certificate numeric failure')
        monkeypatch.setattr('physimesh.drone.trim.linprog', fail_dual)
        assert solve_hover(prepared)['outcome'] == 'unresolved'
    from physimesh.drone.mission_capacity import solve_sequence
    monkeypatch.setattr('physimesh.drone.mission_capacity.linprog', lambda *a, **k:
                        SimpleNamespace(success=False, status=2, x=None, message='infeasible'))
    assert solve_sequence({'hover': prepared}, [])['outcome'] == 'unresolved'


def test_optional_sequence_duration_and_attaining_case_are_correct():
    snapshot, _, maps = fixture()
    optional = copy.deepcopy(snapshot['mission']['cases'][0]); optional.update(name='sequence_only', required=False,
        duration_s=300., body_force_body_n=[0., 0., -100.])
    snapshot['mission']['cases'].append(optional)
    snapshot['mission']['sequence'] = [{'segment_id':'short', 'case_id':'sequence_only', 'duration_s':10.,
        'source_note':'Analytic short segment', 'power_profile':'constant'}]
    report = capacity_from_snapshot(snapshot, maps)
    assert report['outcome'] == 'feasible'
    assert report['payload_lower_bound_kg'] == pytest.approx(300/G0-12)
    assert report['limiting_case_id'] == 'sequence_only' and report['aggregate_limit'] is None
    assert report['sequence_evidence']['remaining_usable_energy_j'] == pytest.approx(420800)
    bound = next(c for c in report['participating_case_bounds'] if c['case_id'] == 'sequence_only')
    assert bound['candidate']['payload_kg'] == report['payload_lower_bound_kg']


def test_coverage_and_analyst_domains_never_claim_physical_infeasibility():
    snapshot, _, maps = fixture()
    snapshot['masses']['items'][0]['cg_body_m'] = [2., 0., 0.]
    snapshot['mission']['payload_positions_body_m'] = [[-1., 0., 0.]]
    snapshot['fidelity']['local_pilot']['payload_domain_kg'] = [0., 3.]
    report = capacity_from_snapshot(snapshot, maps)
    assert report['outcome'] == 'unsupported'
    assert report['cases'][0]['certificate']['nonphysical_bound_dependencies']
    snapshot, _, maps = fixture()
    snapshot['masses']['items'][0]['mass_kg'] = 100.
    for rotor in snapshot['rotors']:
        rotor['sustained_limits']['max_rpm'] = 2000.
    report = capacity_from_snapshot(snapshot, maps)
    assert report['outcome'] == 'unsupported' and report['payload_lower_bound_kg'] is None
    assert any(d['origin']=='coverage' for d in report['cases'][0]['certificate']['nonphysical_bound_dependencies'])


def test_malformed_limits_and_unrecognized_motion_are_input_refusals():
    snapshot, _, maps = fixture(); snapshot['rotors'][0]['sustained_limits'] = None
    assert capacity_from_snapshot(snapshot, maps)['outcome'] == 'unsupported'


def test_tilted_axes_body_loads_torque_offset_and_multislope_power():
    snapshot, data, _ = fixture()
    snapshot['masses']['items'][0]['cg_body_m'] = [.2, -.1, .3]
    snapshot['mission']['payload_positions_body_m'] = [[-.1, .2, .4]]
    for p in data['points']:
        p['shaft_torque_nm'] += .3
    data['points'][-1]['power_w'] = 1200.
    maps = {'fixture': parse_map(json.dumps(data).encode())}
    thrusts = [40., 50., 60., 70.]; forces = []; couples = []
    for i, (rotor, thrust) in enumerate(zip(snapshot['rotors'], thrusts, strict=True)):
        axis = np.array([np.sin(.2)*(1 if i%2 else -1), 0., np.cos(.2)])
        rotor['axis_body'] = axis.tolist(); rotor['center_body_m'][2] = .5*(1 if i%2 else -1)
        f = axis*thrust; forces.append(f)
        couples.append(np.cross(rotor['center_body_m'], f)-rotor['rotation_sign']*axis*(.02*thrust+.3))
    gravity = np.array([0., 0., -G0])
    c = snapshot['mission']['cases'][0]
    c['body_force_body_n'] = (-22*gravity-np.sum(forces, axis=0)).tolist()
    c['body_moment_origin_body_nm'] = (-np.sum(couples, axis=0)
        -np.cross(np.array([.2,-.1,.3])*10, gravity)-np.cross(np.array([-.1,.2,.4])*10, gravity)).tolist()
    result = solve_hover(prepare_hover(snapshot, c, maps), payload_kg=10.)
    assert result['outcome'] == 'feasible'
    assert result['candidate']['cg_body_m'] == pytest.approx([1/22, 1/22, 7/22])
    assert result['candidate']['force_residual_n'] == pytest.approx([0,0,0],abs=1e-7)
    assert result['candidate']['moment_residual_cg_nm'] == pytest.approx([0,0,0],abs=1e-7)
    # The unique commands span both affine electrical-power segments.
    assert [p['thrust_n'] for p in result['candidate']['commands']] == pytest.approx(thrusts)
    assert result['candidate']['electrical_power_w'] == pytest.approx(400+500+640+780)


def test_rpm_and_dc_current_limits_bind_independently():
    snapshot, _, maps = fixture()
    for rotor in snapshot['rotors']:
        rotor['sustained_limits']['max_rpm'] = 500.
    report = capacity_from_snapshot(snapshot, maps)
    assert report['payload_lower_bound_kg'] == pytest.approx(200/G0-12)
    assert all(p['rpm'] == pytest.approx(500.) for p in report['headline_candidate_checks'][0]['candidate']['commands'])
    for rotor in snapshot['rotors']:
        rotor['sustained_limits'].update(max_rpm=1000., max_input_current_a=8.)
    report = capacity_from_snapshot(snapshot, maps)
    assert report['payload_lower_bound_kg'] == pytest.approx(160/G0-12)
    assert all(p['dc_input_current_a'] == pytest.approx(8.) for p in report['headline_candidate_checks'][0]['candidate']['commands'])


def test_sequence_auxiliary_and_multiple_distinct_conditions():
    snapshot, _, maps = fixture(); snapshot['fidelity']['local_pilot']['auxiliary_power_w'] = 100.
    extra = copy.deepcopy(snapshot['mission']['cases'][0]); extra.update(name='download',duration_s=180.,
        body_force_body_n=[0.,0.,-20.])
    snapshot['mission']['cases'][0]['duration_s'] = 180.
    snapshot['mission']['cases'].append(extra)
    snapshot['mission']['sequence'] = [{'segment_id':'a','case_id':'hover','duration_s':180.,
        'power_profile':'constant','source_note':'Analytic'}, {'segment_id':'b','case_id':'download','duration_s':120.,
        'power_profile':'constant','source_note':'Analytic'}]
    report = capacity_from_snapshot(snapshot,maps)
    # E = 300*(10*g*(12+p)+100) + 120*10*20.
    expected = (460800/300-180)/10/G0-12
    assert report['payload_lower_bound_kg'] == pytest.approx(expected)
    assert report['sequence_evidence']['total_energy_j'] == pytest.approx(460800.)


def test_optional_standalone_coverage_does_not_override_segment_duty():
    snapshot, data, _ = fixture(); data['max_continuous_duration_s'] = 100.
    maps = {'fixture':parse_map(json.dumps(data).encode())}
    optional = copy.deepcopy(snapshot['mission']['cases'][0]); optional.update(name='optional',required=False,duration_s=300.)
    unused = copy.deepcopy(optional); unused.update(name='unused', air_relative_velocity_body_m_s=[1.,0.,0.])
    snapshot['mission']['cases'].extend([optional,unused])
    snapshot['mission']['sequence'] = [{'segment_id':'short','case_id':'optional','duration_s':10.,
        'power_profile':'constant','source_note':'Analytic short duty'}]
    assert hover_readiness(snapshot,maps)['eligible']
    assert capacity_from_snapshot(snapshot,maps)['outcome'] == 'feasible'


def test_source_curve_contradiction_with_unknown_operating_states_is_unsupported():
    snapshot, data, _ = fixture()
    data['points'] = [{'rpm':500.,'thrust_n':0.,'shaft_torque_nm':0.,'power_w':1000.},
                      {'rpm':1000.,'thrust_n':100.,'shaft_torque_nm':2.,'power_w':2000.}]
    data['covered_intervals_rpm'] = [[500.,1000.]]
    for r in snapshot['rotors']:
        r['sustained_limits']['max_rpm'] = 2000.
    snapshot['mission']['energy_system']['max_electrical_power_w'] = 3000.
    report = capacity_from_snapshot(snapshot, {'fixture':parse_map(json.dumps(data).encode())})
    assert report['outcome'] == 'unsupported'
    assert report['cases'][0]['certificate']['source_domain_gaps']


@pytest.mark.parametrize('rotor_id',[None,'','bad id',[]])
def test_rotor_identifiers_refuse_at_readiness(rotor_id):
    snapshot, _, maps = fixture(); snapshot['rotors'][0]['rotor_id'] = rotor_id
    assert not hover_readiness(snapshot,maps)['eligible']
    assert capacity_from_snapshot(snapshot,maps)['outcome'] == 'unsupported'
    snapshot, _, maps = fixture(); snapshot['mission']['cases'][0]['rotor_out_ids'] = ['r0']
    assert capacity_from_snapshot(snapshot, maps)['outcome'] == 'unsupported'
