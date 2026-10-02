"""Deterministic illustrative inputs. Every numeric value is EXAMPLE, not client data."""
from copy import deepcopy
from pathlib import Path

import yaml

from physimesh.core.artifacts import ArtifactStore
from physimesh.drone.provenance import canonical_json, sha256_record

LABEL = "Illustrative example inputs, not the client's aircraft."


def example_request(store: ArtifactStore) -> dict:
    """Retain synthetic performance records before returning a screening request."""
    project = yaml.safe_load(Path(__file__).with_name('schema').joinpath('drone_manifest_v1.yaml').read_text())
    project['identity'].update(study_id='EXAMPLE-multirotor', description=LABEL, created_utc='2026-10-02T00:00:00Z')
    project['units_and_frames']['source_units'] = 'm'
    project['masses']['items'] = [{"name": name, "category": category, "mass_kg": mass, "cg_body_m": [0, 0, 0]}
                                for name, category, mass in [('frame', 'structure', 25), ('motors', 'propulsion', 15),
                                                            ('battery', 'energy', 20), ('avionics', 'avionics', 5), ('payload', 'payload', 0), ('other', 'other', 0)]]
    project['atmosphere'].update(source='EXAMPLE dry sea-level atmosphere', altitude_m=0, pressure_pa=101325,
                                 temperature_k=288.15, viscosity={'law': 'sutherland'}, humidity_assumption='dry air')
    project['mission'].update(duration_s=300, reserve_policy={'kind': 'fraction', 'value': .2},
                             energy_system={'pack_wh_per_kg': 250, 'usable_fraction': .8, 'usable_energy_j': 20*250*.8*(1-.2)*3600, 'available_electrical_power_w': 28000})
    project['mission']['cases'] = [
        {"name": 'hover', "velocity_is_air_relative": True, "kind": 'hover', "duration_s": 300, "velocity_world_m_s": [0, 0, 0], "attitude_deg_zyx": [0, 0, 0],
             "acceleration_target_m_s2": [0, 0, 0], "ground_clearance_m": 10, "mass_state": 'empty_plus_calculated_payload'},
        {"name": 'climb', "velocity_is_air_relative": True, "kind": 'climb', "duration_s": 180, "velocity_world_m_s": [0, 0, 2], "attitude_deg_zyx": [0, 0, 0],
             "acceleration_target_m_s2": [0, 0, .6], "ground_clearance_m": 10, "mass_state": 'empty_plus_calculated_payload'},
    ]
    map_doc = {'schema': 'EXAMPLE-map-description', 'label': LABEL,
               'note': 'Synthetic illustrative points; no measured map or rotor validation exists.'}
    map_sha = store.put_bytes(canonical_json(map_doc).encode(), kind='EXAMPLE_performance_description', meta={'label': LABEL})
    project['rotors'] = [{"rotor_id": f'R{i}', "model": 'measured_map', "map_ref": map_sha, "radius_m": .65,
                             "center_body_m": [x, y, 0], "axis_body": [0, 0, 1], "signed_rpm": sign*1500,
                             "sustained_limits": {'electrical_power_w': 7000},
                             "pitch_deg": 0, "n_blades": 2, "root_cutout_m": .08, "azimuth_zero_deg": 0, "phase_offset_deg": 0}
                         for i, (x, y, sign) in enumerate([(1, -1, 1), (1, 1, -1), (-1, 1, 1), (-1, -1, -1)])]
    project['fidelity'].update(initial='measured_map', requested_question='payload_lift')
    design_hash = sha256_record(project)
    cases = []
    for case in project['mission']['cases']:
        name = case['name']; hover = name == 'hover'
        common = {'label': LABEL, 'design_snapshot_sha256': design_hash, 'case_sha256': sha256_record(case)}
        body_force = [0, 0, -40 if hover else -60]
        body_record = {**common, 'schema': 'body_force_v1', 'body_force_world_n': body_force}
        body_sha = store.put_bytes(canonical_json(body_record).encode(), kind='EXAMPLE_body_force', meta={'label': LABEL})
        rotors = []
        for rotor in project['rotors']:
            point = {**common, 'schema': 'rotor_limit_point_v1', 'rotor_id': rotor['rotor_id'],
                     'force_world_n': [0, 0, 350 if hover else 320], 'electrical_power_w': 6000 if hover else 5600}
            point_sha = store.put_bytes(canonical_json(point).encode(), kind='EXAMPLE_rotor_performance', meta={'label': LABEL})
            limit = {'label': LABEL, 'design_snapshot_sha256': design_hash, 'schema': 'sustained_limit_v1',
                     'rotor_id': rotor['rotor_id'], 'sustained_electrical_power_limit_w': 7000}
            limit_sha = store.put_bytes(canonical_json(limit).encode(), kind='EXAMPLE_sustained_limit', meta={'label': LABEL})
            rotors.append({"rotor_id": rotor['rotor_id'], "force_world_n": point['force_world_n'],
                               "electrical_power_w": point['electrical_power_w'], "sustained_electrical_power_limit_w": 7000,
                               "performance_source_sha256": point_sha, "limit_source_sha256": limit_sha})
        cases.append({"case_id": name, "rotors": rotors, "body_force_world_n": body_force, "body_force_source_sha256": body_sha,
                          "vertical_acceleration_m_s2": case['acceleration_target_m_s2'][2], "duration_s": 300 if hover else 180,
                          "available_electrical_power_w": 28000})
    return {'project': deepcopy(project), 'approved_design_sha256': design_hash, 'case_inputs': cases,
            'usable_energy_j': 20*250*.8*(1-.2)*3600}


def example_battery_loops() -> dict:
    """Plan's analytical A/B/C fixtures, separate from fixed-battery lift capacity."""
    import math
    from dataclasses import asdict

    from physimesh.drone.mission import size_battery

    rho = 101325/(287.05*288.15)
    area = 8*math.pi*1.5**2

    def power(mass):
        return (mass*9.80665)**1.5/math.sqrt(2*rho*area)/.7/.85+2000

    cases = []
    for name, density, seconds in [('A', 250, 600), ('B', 200, 1200), ('C', 200, 3600)]:
        result = size_battery(1200, power, duration_s=seconds, e_pack_wh_per_kg=density,
                              f_usable=.8, reserve_fraction=.2, rel_tol=1e-6,
                              max_iterations=500, divergence_mass_kg=1e6)
        cases.append({'name': name, 'pack_wh_per_kg': density, 'duration_s': seconds, **asdict(result)})
    return {'label': 'EXAMPLE analytical battery-sizing fixtures; separate from the four-rotor capacity example.',
            'assumptions': {'mass_without_battery_kg': 1200, 'rotors': 8, 'radius_m': 1.5,
                            'figure_of_merit': .7, 'electrical_efficiency': .85, 'auxiliary_power_w': 2000,
                            'usable_fraction': .8, 'reserve_fraction': .2,
                            'model': 'isolated ideal-hover lower bound divided by assumed FM and efficiency'},
            'cases': cases}
