import math
from copy import deepcopy

from . import rotor_assembly as ra
from .graph_mission import _normal, _require
from .model_graph_execution import _json
from .provenance import sha256_record

EVALUATION = 'isolated_rotor_frozen_load_dynamics_experimental'


def _vec(v, n=3):
    _require(type(v) is list and len(v) == n)
    _require(all(type(x) in (int, float) and _normal(x) is not None for x in v))
    return tuple(float(x) for x in v)


def _preflight(value):
    _json(value, budget=32768)
    snap = deepcopy(value)
    _require(type(snap) is dict)
    _require(set(snap) == {
        "evaluation", "assembly", "initial_state", "inertia_body_kg_m2",
        "dt_s", "steps", "applicability_declaration",
    })
    _require(snap["evaluation"] == EVALUATION)
    assembly = ra._preflight(snap["assembly"])
    _require(assembly["gravity_direction_body"] == [0, 0, -1])
    state = snap["initial_state"]
    _require(type(state) is dict)
    _require(set(state) == {
        "position_enu_m", "velocity_enu_m_s",
        "quaternion_body_to_enu", "angular_velocity_body_rad_s",
    })
    _vec(state["position_enu_m"])
    _vec(state["velocity_enu_m_s"])
    _vec(state["quaternion_body_to_enu"], 4)
    _vec(state["angular_velocity_body_rad_s"])
    _require(state["quaternion_body_to_enu"] == [1, 0, 0, 0])
    inertia = snap["inertia_body_kg_m2"]
    _require(type(inertia) is list and len(inertia) == 3)
    for row in inertia:
        _vec(row)
    _require(_normal(snap["dt_s"]) and snap["dt_s"] > 0)
    _require(type(snap["steps"]) is int and 1 <= snap["steps"] <= 1000)
    declaration = snap["applicability_declaration"]
    _require(type(declaration) is str)
    _require(bool(declaration.strip()) and len(declaration) <= 2000)
    return snap


def _assembly_loads(raw, spec):
    _json(raw, budget=49152, items=2048)
    _require(type(raw) is dict)
    _require(raw["status"] == "COMPUTED_EXPERIMENTAL")
    _require(raw["evaluation"] == ra.EVALUATION)
    _require(raw["diagnostics_complete"] is True)
    _require(raw["evidence_level"] == "unverified")
    for key in ("physical_validation", "numerical_qualification", "runtime_identity"):
        _require(raw[key] == "NOT_ESTABLISHED")
    _require(raw["feasibility"] is None and raw["aircraft_status"] is None)
    _require(type(raw["reasons"]) is list and raw["reasons"] == [])
    _require(raw["request_sha256"] == sha256_record(spec))
    outputs = raw["outputs"]
    _require(type(outputs) is dict and set(outputs) == {
        "rotors", "gravity_force_body_n", "net_force_body_n", "net_moment_cg_body_nm"
    })
    _require(raw["output_units"] == {
        "rotors": {"node": "not_applicable", "force_body_n": "N",
                   "reaction_torque_body_nm": "N*m", "moment_cg_body_nm": "N*m"},
        "gravity_force_body_n": "N", "net_force_body_n": "N",
        "net_moment_cg_body_nm": "N*m",
    })
    def vector(value):
        _require(type(value) is list and len(value) == 3)
        _require(all(type(component) in (int, float) for component in value))
        return _vec(value)
    rows = outputs["rotors"]
    _require(type(rows) is list and len(rows) == len(spec["rotors"]))
    forces, moments = [], []
    for row, requested in zip(rows, spec["rotors"]):
        _require(type(row) is dict and set(row) == {
            "node", "force_body_n", "reaction_torque_body_nm", "moment_cg_body_nm"
        })
        _require(row["node"] == requested["node"])
        forces.append(vector(row["force_body_n"]))
        vector(row["reaction_torque_body_nm"])
        moments.append(vector(row["moment_cg_body_nm"]))
    gravity_force = vector(outputs["gravity_force_body_n"])
    net_force = vector(outputs["net_force_body_n"])
    net_moment = vector(outputs["net_moment_cg_body_nm"])
    force = tuple(_normal(math.fsum(v[i] for v in forces)) for i in range(3))
    moment = tuple(_normal(math.fsum(v[i] for v in moments)) for i in range(3))
    _require(net_force == tuple(_normal(math.fsum(
        [v[i] for v in forces] + [gravity_force[i]])) for i in range(3)))
    _require(net_moment == moment)
    _require(gravity_force[0] == 0.0 and gravity_force[1] == 0.0 and gravity_force[2] < 0.0)
    gravity = (0.0, 0.0, _normal(gravity_force[2] / spec["mass_kg"]))
    _require(gravity[2] < 0.0)
    return force, moment, gravity


def _run_dynamics(s, force, moment, gravity):
    from .rigid_body_request import evaluate_rigid_body

    r = {
        'evaluation': 'rigid_body_constant_wrench_experimental',
        'initial_state': deepcopy(s['initial_state']),
        'mass_kg': s['assembly']['mass_kg'],
        'inertia_body_kg_m2': deepcopy(s['inertia_body_kg_m2']),
        'force_body_n': list(force), 'moment_cg_body_nm': list(moment),
        'gravity_enu_m_s2': list(gravity),
        'dt_s': s['dt_s'], 'steps': s['steps'],
        'property_source': s['assembly']['property_source'],
        'applicability_declaration': s['applicability_declaration'],
    }
    actual = evaluate_rigid_body(r)
    _json(actual, budget=49152, items=2048)
    _require(actual['status'] == 'COMPUTED_EXPERIMENTAL' and actual['model_id'] == 'rigid_body_constant_body_wrench_rk4_v1')
    _require(actual['evidence_level'] == 'unverified' and actual['physical_validation'] == 'NOT_ESTABLISHED')
    _require(actual['feasibility'] is None and actual['aircraft_status'] is None)
    _validated_dynamics(actual, r)
    return r, actual


def evaluate_rotor_fixed_load_dynamics(request):
    result = {
        "evaluation": EVALUATION, "status": "GRAPH_INVALID",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "evidence_level": "unverified", "aircraft_status": None,
        "feasibility": None, "diagnostics_complete": False,
        "reasons": [], "stages": [], "transfers": {},
        "outputs": {}, "output_units": {},
        "limitations": [
            "Isolated hover loads are frozen and are not updated with motion.",
            "The initial body orientation is identity relative to ENU.",
            (
                "Accepted constant body wrench uses RK4; raw stage quaternions "
                "can produce nonorthogonal intermediate rotations."
            ),
            "No horizon guarantee; timestep refinement is required.",
            (
                "No installed performance, trim, control, stability, energy/thermal "
                "feasibility, mass closure, or aircraft pass is established."
            )]}
    try:
        snapshot = _preflight(request)
        result["request_sha256"] = sha256_record(snapshot)
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError, KeyError):
        result["reasons"] = ["Invalid request."]
        return deepcopy(result)
    try:
        assembly_input = snapshot["assembly"]
        assembly_raw = ra.evaluate_rotor_assembly(assembly_input)
        force, moment, gravity = _assembly_loads(assembly_raw, assembly_input)
        dynamics_input, dynamics_raw = _run_dynamics(snapshot, force, moment, gravity)
        stages = [
            {"stage_id": name, "request_sha256": sha256_record(inp),
             "result_sha256": sha256_record(raw)}
            for name, inp, raw in [
                ("assembly", assembly_input, assembly_raw),
                ("dynamics", dynamics_input, dynamics_raw)]]
        result.update(status="COMPUTED_EXPERIMENTAL", diagnostics_complete=True, stages=stages,
                      transfers={"force_body_n": list(force), "moment_cg_body_nm": list(moment),
                                 "gravity_enu_m_s2": list(gravity)},
                      outputs={"assembly": assembly_raw["outputs"], "dynamics": dynamics_raw["outputs"]},
                      output_units={"assembly": assembly_raw["output_units"], "dynamics": dynamics_raw["output_units"]})
    except Exception:  # noqa: BLE001 - Whole-component failure requires atomic refusal.
        result.update(status="EXECUTION_FAILED", diagnostics_complete=False,
                      reasons=["Execution failed."], stages=[], transfers={}, outputs={}, output_units={})
    return deepcopy(result)


def _validated_dynamics(actual, r):
    units = {'elapsed_s':'s','steps':'1','initial_state':{'position_enu_m':'m','velocity_enu_m_s':'m/s','quaternion_body_to_enu':'1','angular_velocity_body_rad_s':'rad/s'},'final_state':{'position_enu_m':'m','velocity_enu_m_s':'m/s','quaternion_body_to_enu':'1','angular_velocity_body_rad_s':'rad/s'},'input_quaternion_norm_correction':'1','max_preprojection_quaternion_norm_error':'1','final_quaternion_norm':'1','initial_rotational_kinetic_energy_j':'J','final_rotational_kinetic_energy_j':'J','initial_angular_momentum_enu_kg_m2_s':'kg*m^2/s','final_angular_momentum_enu_kg_m2_s':'kg*m^2/s','torque_free_relative_energy_drift':'1','torque_free_relative_angular_momentum_drift':'1'}
    _require(type(actual['reasons']) is list and actual['reasons'] == [])
    _require(actual['inertia_physical_admissibility'] == 'NOT_ASSESSED')
    o = actual['outputs']
    _require(type(o) is dict and o.keys() == units.keys())
    _require(type(actual['output_units']) is dict and actual['output_units'] == units)
    _require(type(o['steps']) is int and o['steps'] == r['steps'])
    _normal(o['elapsed_s'])
    _require(o['elapsed_s'] > 0 and o['elapsed_s'] == r['dt_s'] * o['steps'])
    for phase in ('initial_state', 'final_state'):
        state = o[phase]
        _require(type(state) is dict and state.keys() == units[phase].keys())
        for key in units[phase]:
            _vec(state[key], 4 if key == 'quaternion_body_to_enu' else 3)
            if phase == 'initial_state':
                _require(state[key] == r['initial_state'][key])
    _require(abs(math.hypot(*o['final_state']['quaternion_body_to_enu']) - 1) <= 1e-12)
    for key in ('input_quaternion_norm_correction', 'max_preprojection_quaternion_norm_error', 'final_quaternion_norm', 'initial_rotational_kinetic_energy_j', 'final_rotational_kinetic_energy_j'):
        _normal(o[key])
        _require(o[key] >= 0)
    _require(o['final_quaternion_norm'] > 0)
    for key in ('initial_angular_momentum_enu_kg_m2_s', 'final_angular_momentum_enu_kg_m2_s'):
        _vec(o[key], 3)
    has_moment = any(component != 0 for component in r['moment_cg_body_nm'])
    for key in ('torque_free_relative_energy_drift', 'torque_free_relative_angular_momentum_drift'):
        value = o[key]
        _require((value is None and has_moment) or (type(value) in (int, float) and math.isfinite(value) and value >= 0))
