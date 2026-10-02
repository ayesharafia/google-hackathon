"""Explicit isolated-hover power bound and axial-flight tip-Mach diagnostics."""
import math

import numpy as np

from physimesh.drone.atmosphere import make_atmosphere, tip_mach_screen
from physimesh.drone.frames import rotation_matrix_zyx


def diagnostics(project: dict, case_inputs: list[dict]) -> list[dict]:
    atm_data = project['atmosphere']
    viscosity = atm_data['viscosity']
    atm = make_atmosphere(atm_data['pressure_pa'], atm_data['temperature_k'], source=atm_data['source'],
                          gamma=atm_data['gamma'], viscosity_pa_s=viscosity.get('value_pa_s'),
                          viscosity_law=viscosity.get('law'))
    rotors = {rotor['rotor_id']: rotor for rotor in project['rotors']}
    cases = {case['name']: case for case in project['mission']['cases']}
    output = []
    for case_input in case_inputs:
        case = cases[case_input['case_id']]
        for point in case_input['rotors']:
            rotor = rotors[point['rotor_id']]
            record = {'case_id': case_input['case_id'], 'rotor_id': point['rotor_id'],
                      'tip_mach': None, 'isolated_ideal_hover_power_w': None, 'unavailable': []}
            try:
                axis = np.asarray(rotor['axis_body'], float)
                attitude = np.asarray(case['attitude_deg_zyx'], float)
                velocity = np.asarray(case['velocity_world_m_s'], float)
                rpm = rotor['signed_rpm']; radius = rotor['radius_m']
                if (any(vector.shape != (3,) or not np.isfinite(vector).all() for vector in (axis, attitude, velocity))
                        or np.linalg.norm(axis) == 0 or not math.isfinite(rpm) or not math.isfinite(radius) or radius <= 0):
                    raise ValueError('finite rotor frame, radius and RPM required')
                world_axis = rotation_matrix_zyx(*np.deg2rad(attitude)) @ (axis/np.linalg.norm(axis))
                if case.get('velocity_is_air_relative') is not True:
                    raise ValueError('declare air-relative velocity before tip-Mach or hover diagnostics')
                axial = float(velocity @ world_axis)
                lateral = np.linalg.norm(velocity-axial*world_axis)
                if lateral > 1e-9:
                    record['unavailable'].append('tip Mach formula is axial-flight screening only')
                else:
                    record['tip_mach'] = tip_mach_screen(atm, rpm*2*math.pi/60, radius, axial)
                if case.get('kind') == 'hover' and np.linalg.norm(velocity) <= 1e-9:
                    thrust = float(np.asarray(point['force_world_n']) @ world_axis)
                    if thrust >= 0:
                        record['isolated_ideal_hover_power_w'] = thrust**1.5/math.sqrt(2*atm.density*math.pi*radius**2)
                else:
                    record['unavailable'].append('isolated ideal-hover power bound is not a climb-power model')
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                record['unavailable'].append(str(exc))
            output.append(record)
    return output
