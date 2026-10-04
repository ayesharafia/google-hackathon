"""Explicitly artificial hover fixture. Never substitutes for client measurements."""
import json

from physimesh.drone.atmosphere import R_AIR
from physimesh.drone.trim import MODEL_VERSION

from .performance import retain_map


def create_hover_example(projects):
    project = projects.create('Illustrative hover design')
    snapshot = json.loads(project['snapshot_json'])
    snapshot['identity']['data_scope'] = 'analytic_fixture'
    snapshot['masses']['items'] = [{'name': c, 'category': c, 'mass_kg': mass, 'cg_body_m': [0, 0, 0],
                                   'source_note': 'Analytic software fixture; not measured aircraft mass.'}
                                  for c, mass in [('structure', 10), ('energy', 2), ('payload', 0),
                                                  ('propulsion', 0), ('avionics', 0), ('other', 0)]]
    snapshot['mission']['payload_positions_body_m'] = [[0, 0, 0]]
    snapshot['mission']['energy_system'] = {'pack_mass_item_names': ['energy'], 'pack_wh_per_kg': 100,
        'usable_fraction': .8, 'usable_energy_j': 460800., 'nominal_voltage_v': 50.,
        'max_electrical_power_w': 3000., 'max_current_a': 60., 'mode': 'fixed',
        'voltage_model': 'declared_constant_bus'}
    snapshot['mission']['reserve_policy'] = {'kind': 'fraction', 'value': .2,
                                            'convention': 'held_usable_energy_fraction'}
    snapshot['mission']['cases'] = [{'name': name, 'kind': 'hover', 'required': True, 'duration_s': seconds,
        'attitude_deg_zyx': [0, 0, 0], 'velocity_world_m_s': [0, 0, 0],
        'acceleration_target_m_s2': [0, 0, 0], 'air_relative_velocity_body_m_s': [0, 0, 0],
        'source_note': 'Synthetic duration case for software verification', 'body_force_body_n': [0, 0, 0],
        'body_moment_origin_body_nm': [0, 0, 0], 'body_load_source': 'Explicit analytic zero-load fixture'}
        for name, seconds in [('hover_short', 60.), ('hover_long', 300.)]]
    snapshot['atmosphere'].update(pressure_pa=101325., temperature_k=288.15, source='Analytic air-state fixture')
    snapshot['fidelity']['local_pilot'] = {'model_version': MODEL_VERSION, 'payload_domain_kg': [0., 100.],
                                         'auxiliary_power_w': 0.}
    dataset = {'schema_version': 'rotor_map_v1', 'dataset_id': 'analytic-linear-rotor',
        'configuration_id': 'fixture-rotor', 'source_kind': 'analytic_fixture',
        'source_description': 'Artificial linear thrust/power and affine torque for closed-form software checks.',
        'units': 'rpm_N_Nm_W', 'torque_convention': 'absorbed_shaft_magnitude',
        'density_kg_m3': 101325/(R_AIR*288.15), 'axial_inflow_m_s': 0., 'pitch_deg': 0.,
        'max_continuous_duration_s': 3600., 'power_basis': 'electrical', 'covered_intervals_rpm': [[0., 1000.]],
        'points': [{'rpm': rpm, 'thrust_n': thrust, 'shaft_torque_nm': .02*thrust, 'power_w': 10*thrust}
                   for rpm, thrust in [(0., 0.), (500., 50.), (1000., 100.)]]}
    source = retain_map(projects.artifacts, json.dumps(dataset).encode())['source_sha256']
    snapshot['rotors'] = [{'rotor_id': 'r'+str(i), 'center_body_m': [x, y, 0], 'axis_body': [0, 0, 1],
        'radius_m': .2, 'rotation_sign': sign, 'configuration_id': 'fixture-rotor', 'map_ref': source, 'pitch_deg': 0.,
        'sustained_limits': {'max_rpm': 1000., 'max_electrical_power_w': 2000., 'max_input_current_a': 40.}}
        for i, (x, y, sign) in enumerate([(1, 1, 1), (-1, 1, -1), (-1, -1, 1), (1, -1, -1)])]
    return projects.save(project['project_id'], 0, json.dumps(snapshot))
