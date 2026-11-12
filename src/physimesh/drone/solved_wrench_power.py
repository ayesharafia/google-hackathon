import math
from copy import deepcopy

from . import ledger_static_wrench as ls
from . import reference_air_graph as rg
from . import static_wrench_solve as ws
from .graph_mission import _normal, _require
from .model_graph_execution import _json
from .provenance import sha256_record

EVALUATION = "solved_static_wrench_power_experimental"


def _power_graph(spec, speeds):
    assembly = ws._assembly_input(spec, speeds)
    graph = deepcopy(assembly["graph"])
    targets = graph.setdefault("targets", [])
    for rotor in assembly["rotors"]:
        targets.append({"node": rotor["node"], "port": "shaft_power_w"})
    return graph


def _preflight(request):
    _json(request, budget=49152)
    result = deepcopy(request)
    _require(type(result) is dict)
    _require(set(result) == {"evaluation", "solve", "conversion"})
    _require(result["evaluation"] == EVALUATION)
    spec = ws._preflight(result["solve"])
    conversion = result["conversion"]
    _require(type(conversion) is dict)
    _require(
        set(conversion) == {"rotors", "auxiliary_power_w", "auxiliary_source"}
    )
    rotors = conversion["rotors"]
    expected = spec["assembly_template"]["rotors"]
    _require(type(rotors) is list)
    _require(len(rotors) == len(expected))
    for rotor, template in zip(rotors, expected):
        _require(type(rotor) is dict)
        _require(
            set(rotor) == {"node", "conversion_efficiency", "conversion_source"}
        )
        _require(rotor["node"] == template["node"])
        eta = rotor["conversion_efficiency"]
        _require(0 < _normal(eta) <= 1)
        source = rotor["conversion_source"]
        _require(
            type(source) is str and bool(source.strip()) and len(source) <= 2000
        )
    auxiliary = conversion["auxiliary_power_w"]
    _require(_normal(auxiliary) >= 0)
    source = conversion["auxiliary_source"]
    _require(
        type(source) is str and bool(source.strip()) and len(source) <= 2000
    )
    aggregate = sum(
        node["inputs"]["annuli"]
        for node in spec["assembly_template"]["graph"]["nodes"]
        if node["model"] == "isolated_hover_bemt_experimental"
    )
    _require(aggregate * (spec["max_evaluations"] + 1) <= 32768)
    speeds = [
        bound["initial_angular_speed_rad_s"]
        for bound in spec["rotor_speed_bounds"]
    ]
    rg._validate(_power_graph(spec, speeds))
    result["solve"] = spec
    return result


def _power_sum(values):
    copiedvalues, total = [], 0.
    for value in values:
        _require(_normal(value) >= 0)
        copiedvalues.append(value)
        newtotal = _normal(math.fsum(copiedvalues))
        _require(value == 0 or newtotal > total)
        _require(total == 0 or newtotal > value)
        total = newtotal
    return total


def _validated_power(raw, graph, spec, solve_raw, conversion):
    ls.ld._valid(raw, rg.EVALUATION, graph)
    template = spec["assembly_template"]
    rotors, air = template["rotors"], template["air_node"]
    outputs, units = raw["outputs"], raw["output_units"]
    ids = [air] + [r["node"] for r in rotors]
    _require(len(set(ids)) == len(ids))
    _require(type(outputs) is dict and set(outputs) == set(ids))
    _require(type(units) is dict and set(units) == set(ids))
    _require(type(outputs[air]) is dict and set(outputs[air]) == {"gravity_m_s2"})
    _require(type(units[air]) is dict and units[air] == {"gravity_m_s2": "m/s^2"})
    gravity = _normal(outputs[air]["gravity_m_s2"])
    mass = _normal(template["mass_kg"])
    _require(gravity > 0 and mass > 0)
    cg = ws.ra._vector(template["cg_body_m"])
    direction = ws.ra._unit(template["gravity_direction_body"])
    assembly = solve_raw["outputs"]["assembly"]
    _require(type(assembly) is dict and set(assembly) == {
        "rotors", "gravity_force_body_n", "net_force_body_n", "net_moment_cg_body_nm"})
    rows = assembly["rotors"]
    speeds = solve_raw["outputs"]["selected_candidate"]["angular_speeds_rad_s"]
    conversions = conversion["rotors"]
    for items in (rows, speeds, conversions):
        _require(type(items) is list and len(items) == len(rotors))
    auxiliary = _normal(conversion["auxiliary_power_w"])
    _require(auxiliary >= 0)
    power, forces, moments = [], [], []
    rotor_units = {"thrust_n": "N", "shaft_torque_nm": "N*m", "shaft_power_w": "W"}
    for rotor, row, speed, item in zip(rotors, rows, speeds, conversions):
        node = rotor["node"]
        out = outputs[node]
        _require(type(out) is dict and set(out) == set(rotor_units))
        _require(type(units[node]) is dict and units[node] == rotor_units)
        thrust, torque, shaft = (_normal(out[k]) for k in rotor_units)
        _require(thrust > 0 and torque >= 0 and shaft >= 0)
        omega = _normal(speed)
        _require(omega > 0)
        _require(math.isclose(_normal(torque * omega), shaft, rel_tol=1e-12, abs_tol=1e-12))
        _require(type(item) is dict and set(item) == {
            "node", "conversion_efficiency", "conversion_source"})
        _require(item["node"] == node)
        eta = _normal(item["conversion_efficiency"])
        _require(0 < eta <= 1)
        electrical = _normal(shaft / eta)
        _require(type(row) is dict and set(row) == {
            "node", "force_body_n", "reaction_torque_body_nm", "moment_cg_body_nm"})
        _require(row["node"] == node)
        axis = ws.ra._unit(rotor["axis_body"])
        center = ws.ra._vector(rotor["center_body_m"])
        sign = rotor["rotation_sign"]
        _require(type(sign) is int and sign in (-1, 1))
        force = [_normal(thrust * a) for a in axis]
        signed_torque = _normal(-sign * torque)
        reaction = [_normal(signed_torque * a) for a in axis]
        arm = [_normal(c - g) for c, g in zip(center, cg)]
        moment = [
            _normal(_normal(_normal(arm[j] * force[k]) -
                            _normal(arm[k] * force[j])) + reaction[i])
            for i, j, k in ((0, 1, 2), (1, 2, 0), (2, 0, 1))
        ]
        for key, expected in (
            ("force_body_n", force), ("reaction_torque_body_nm", reaction),
            ("moment_cg_body_nm", moment),
        ):
            actual = row[key]
            _require(type(actual) is list and len(actual) == 3)
            for value, target in zip(actual, expected):
                _require(math.isclose(_normal(value), target, rel_tol=1e-12, abs_tol=1e-12))
        forces.append(force)
        moments.append(moment)
        power.append({
            "node": node, "angular_speed_rad_s": omega,
            "shaft_power_w": shaft, "shaft_torque_nm": torque,
            "conversion_efficiency": eta, "electrical_power_w": electrical,
        })
    weight = _normal(mass * gravity)
    gravity_force = [_normal(weight * d) for d in direction]
    net_force = [_normal(math.fsum([f[i] for f in forces] + [gravity_force[i]]))
                 for i in range(3)]
    net_moment = [_normal(math.fsum(m[i] for m in moments)) for i in range(3)]
    for key, expected in (
        ("gravity_force_body_n", gravity_force), ("net_force_body_n", net_force),
        ("net_moment_cg_body_nm", net_moment),
    ):
        actual = assembly[key]
        _require(type(actual) is list and len(actual) == 3)
        for value, target in zip(actual, expected):
            _require(math.isclose(_normal(value), target, rel_tol=1e-12, abs_tol=1e-12))
    return {
        "rotors": power,
        "total_shaft_power_w": _power_sum(r["shaft_power_w"] for r in power),
        "total_electrical_power_w": _power_sum([r["electrical_power_w"] for r in power] + [auxiliary]),
        "auxiliary_power_w": auxiliary,
    }


def _power_units(n):
    return {
        "rotors": [{
            "node": "not_applicable", "angular_speed_rad_s": "rad/s",
            "shaft_power_w": "W", "shaft_torque_nm": "N*m",
            "conversion_efficiency": "1", "electrical_power_w": "W",
        } for _ in range(n)],
        "total_shaft_power_w": "W",
        "total_electrical_power_w": "W",
        "auxiliary_power_w": "W",
    }





def evaluate_solved_wrench_power(request):
    result = {
        "evaluation": EVALUATION,
        "status": "GRAPH_INVALID",
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "feasibility": None,
        "aircraft_status": None,
        "diagnostics_complete": False,
        "reasons": [],
        "stages": [],
        "transfers": {},
        "outputs": {},
        "output_units": {},
        "limitations": [
            "Scientifically unqualified experimental computation.",
            "Isolated static model with caller-supplied conversion assumptions.",
            "Does not establish installed physics or control authority.",
            "Does not establish trim, feasibility, energy, or thermal adequacy.",
            "Hashes do not establish physical validation.",
        ],
    }
    errors = (
        ValueError, TypeError, OverflowError, UnicodeError,
        RecursionError, KeyError, ZeroDivisionError,
    )
    try:
        snapshot = _preflight(request)
    except errors:
        result["reasons"] = ["Invalid solved wrench power request."]
        return deepcopy(result)
    try:
        result["request_sha256"] = sha256_record(snapshot)
        spec = snapshot["solve"]
        solve_raw = ws.evaluate_static_wrench_solve(deepcopy(spec))
        ls._validated_solve(solve_raw, spec)
        stages = [{
            "stage_id": "solve",
            "request_sha256": sha256_record(spec),
            "result_sha256": sha256_record(solve_raw),
        }]
        state, power, power_units = "NOT_RUN_RESIDUAL_UNMET", None, None
        transfers = {}
        if solve_raw["outputs"]["outcome"] == "RESIDUAL_MET":
            selected = deepcopy(
                solve_raw["outputs"]["selected_candidate"]["angular_speeds_rad_s"]
            )
            graph = _power_graph(spec, selected)
            power_raw = rg.evaluate_reference_air_graph(deepcopy(graph))
            power = _validated_power(
                power_raw, graph, spec, solve_raw, snapshot["conversion"]
            )
            power_units = _power_units(len(selected))
            stages.append({
                "stage_id": "power_graph",
                "request_sha256": sha256_record(graph),
                "result_sha256": sha256_record(power_raw),
            })
            state = "COMPUTED_AT_RESIDUAL_MET_POINT"
            transfers = {
                "angular_speeds_rad_s": selected,
                "source": "solve_selected_candidate",
            }
        completed = deepcopy({
            "status": "COMPUTED_EXPERIMENTAL",
            "diagnostics_complete": True,
            "stages": stages,
            "transfers": transfers,
            "outputs": {
                "solve": solve_raw["outputs"], "power_state": state, "power": power,
            },
            "output_units": {
                "solve": solve_raw["output_units"],
                "power_state": "not_applicable", "power": power_units,
            },
        })
        result.update(completed)
    except Exception:  # noqa: BLE001 - contain evaluator and returned-contract failures
        result["status"] = "EXECUTION_FAILED"
        result["reasons"] = ["Solved wrench power execution failed."]
    return deepcopy(result)
