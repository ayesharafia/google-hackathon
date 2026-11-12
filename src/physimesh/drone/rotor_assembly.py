import math
from copy import deepcopy

from .graph_mission import _normal, _require
from .model_graph_execution import _json
from .provenance import sha256_record
from .reference_air_graph import EVALUATION as GRAPH_EVALUATION
from .reference_air_graph import _validate, evaluate_reference_air_graph

EVALUATION = "isolated_rotor_static_assembly_experimental"


def _vector(v):
    _require(type(v) is list and len(v) == 3)
    result = []
    for value in v:
        _require(type(value) in (int, float))
        value = _normal(value)
        _require(type(value) in (int, float) and math.isfinite(value))
        result.append(float(value))
    return result


def _unit(v):
    v = _vector(v)
    _require(abs(math.hypot(*v) - 1.0) <= 1e-12)
    return v


def _preflight(request):
    _json(request, budget=16384)
    snapshot = deepcopy(request)
    _require(
        type(snapshot) is dict
        and set(snapshot)
        == {
            "evaluation",
            "graph",
            "air_node",
            "rotors",
            "mass_kg",
            "cg_body_m",
            "gravity_direction_body",
            "property_source",
        }
    )
    _require(snapshot["evaluation"] == EVALUATION)
    graph = snapshot["graph"]
    _require(type(graph) is dict and graph.get("evaluation") == GRAPH_EVALUATION)
    _validate(graph)
    _require(type(snapshot["mass_kg"]) in (int, float))
    _normal(snapshot["mass_kg"])
    _require(math.isfinite(snapshot["mass_kg"]) and snapshot["mass_kg"] > 0)
    _vector(snapshot["cg_body_m"])
    _unit(snapshot["gravity_direction_body"])
    source = snapshot["property_source"]
    _require(type(source) is str and bool(source.strip()) and len(source) <= 2000)
    air, rotors = snapshot["air_node"], snapshot["rotors"]
    _require(type(air) is str)
    _require(type(rotors) is list and 1 <= len(rotors) <= 15)
    nodes = {node["id"]: node for node in graph["nodes"]}
    _require(air in nodes and nodes[air]["model"] == "reference_air_properties")
    seen, expected_edges = {air}, set()
    expected_targets = {(air, "gravity_m_s2")}
    for rotor in rotors:
        _require(
            type(rotor) is dict
            and set(rotor)
            == {
                "node",
                "center_body_m",
                "axis_body",
                "rotation_sign",
            }
        )
        node = rotor["node"]
        _require(type(node) is str and node not in seen and node in nodes)
        _require(nodes[node]["model"] == "isolated_hover_bemt_experimental")
        _require("density_kg_m3" not in nodes[node]["inputs"])
        _require(type(rotor["rotation_sign"]) is int and rotor["rotation_sign"] in (-1, 1))
        _vector(rotor["center_body_m"])
        _unit(rotor["axis_body"])
        seen.add(node)
        expected_edges.add((air, "density_kg_m3", node, "density_kg_m3"))
        expected_targets.update({(node, "thrust_n"), (node, "shaft_torque_nm")})
    _require(set(nodes) == seen)
    edges = graph["connections"]
    _require(
        len(edges) == len(rotors)
        and {(e["from_node"], e["from_port"], e["to_node"], e["to_port"]) for e in edges} == expected_edges
    )
    _require({(t["node"], t["port"]) for t in graph["targets"]} == expected_targets)
    return snapshot


def _loads(snapshot, graphresult):
    import math

    def _product(a, b):
        p = _normal(a * b)
        _require(p == 0 if a == 0 or b == 0 else p != 0)
        return p

    def _cross(a, b):
        return (
            _normal(_product(a[1], b[2]) - _product(a[2], b[1])),
            _normal(_product(a[2], b[0]) - _product(a[0], b[2])),
            _normal(_product(a[0], b[1]) - _product(a[1], b[0])),
        )

    _json(graphresult, budget=49152, items=2048)
    result = graphresult
    _require(type(result) is dict)
    _require(result["evaluation"] == GRAPH_EVALUATION and result["status"] == "COMPUTED_EXPERIMENTAL")
    _require(result["diagnostics_complete"] is True and result["evidence_level"] == "unverified")
    _require(
        all(
            result[k] == "NOT_ESTABLISHED"
            for k in ("physical_validation", "numerical_qualification", "runtime_identity")
        )
    )
    _require(
        result["aircraft_status"] is None
        and result["feasibility"] is None
        and type(result["reasons"]) is list
        and result["reasons"] == []
    )
    graph = snapshot["graph"]
    _require(result["request_sha256"] == sha256_record(graph))
    air, rotors, outputs = snapshot["air_node"], snapshot["rotors"], result["outputs"]
    ids = [air] + [r["node"] for r in rotors]
    _require(type(outputs) is dict and len(set(ids)) == len(ids) and set(outputs) == set(ids))
    units = result["output_units"]
    _require(type(units) is dict and set(units) == set(ids))
    _require(type(units[air]) is dict and units[air] == {"gravity_m_s2": "m/s^2"})
    _require(type(outputs[air]) is dict and outputs[air].keys() == {"gravity_m_s2"})
    gravity = _normal(outputs[air]["gravity_m_s2"])
    mass, cg, direction = (
        _normal(snapshot["mass_kg"]),
        _vector(snapshot["cg_body_m"]),
        _vector(_unit(snapshot["gravity_direction_body"])),
    )
    _require(gravity > 0 and mass > 0)
    prepared, rows = [], []
    for r in rotors:
        out = outputs[r["node"]]
        _require(type(out) is dict and out.keys() == {"thrust_n", "shaft_torque_nm"})
        _require(
            type(units[r["node"]]) is dict and units[r["node"]] == {"thrust_n": "N", "shaft_torque_nm": "N*m"}
        )
        thrust, torque = _normal(out["thrust_n"]), _normal(out["shaft_torque_nm"])
        _require(
            thrust > 0 and torque >= 0 and type(r["rotation_sign"]) is int and r["rotation_sign"] in (-1, 1)
        )
        prepared.append(
            (
                r["node"],
                _vector(_unit(r["axis_body"])),
                _vector(r["center_body_m"]),
                r["rotation_sign"],
                thrust,
                torque,
            )
        )
    for node, axis, center, sign, thrust, torque in prepared:
        force, reaction = (
            tuple(_product(thrust, a) for a in axis),
            tuple(_product(_product(-sign, torque), a) for a in axis),
        )
        arm = _cross(tuple(_normal(c - g) for c, g in zip(center, cg, strict=True)), force)
        rows.append(
            {
                "node": node,
                "force_body_n": list(force),
                "reaction_torque_body_nm": list(reaction),
                "moment_cg_body_nm": [_normal(a + b) for a, b in zip(arm, reaction, strict=True)],
            }
        )
    gravityforce = [_product(_product(mass, gravity), d) for d in direction]
    return (
        rows,
        gravityforce,
        [_normal(math.fsum([r["force_body_n"][i] for r in rows] + [gravityforce[i]])) for i in range(3)],
        [_normal(math.fsum(r["moment_cg_body_nm"][i] for r in rows)) for i in range(3)],
    )


def evaluate_rotor_assembly(request):
    evaluation = {
        "evaluation": EVALUATION,
        "status": "GRAPH_INVALID",
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "diagnostics_complete": False,
        "reasons": [],
        "stages": [],
        "outputs": {},
        "output_units": {},
        "limitations": [
            "Linear superposition of isolated small-angle hover rotors, not an installed-aircraft model.",
            "Explicit forward/left/up body axes, CG, gravity direction and spin signs are caller declarations.",
            "No rotor interference, tilt dynamics, forward-flight loads, gyroscopic moments or mass/inertia evolution.",
            "Net force/moment are static residuals, not trim, control authority, stability, safety or feasibility.",
            "Unit-vector tolerance 1e-12 is an arithmetic declaration gate, not frame calibration.",
            "Data hashes identify inputs/results, not validation or runtime identity.",
        ],
    }
    try:
        snapshot = _preflight(request)
        evaluation["request_sha256"] = sha256_record(snapshot)
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError, KeyError, ZeroDivisionError):
        evaluation["reasons"] = ["Invalid rotor assembly request."]
        return deepcopy(evaluation)
    try:
        graph_request_sha256 = sha256_record(snapshot["graph"])
        graph = evaluate_reference_air_graph(deepcopy(snapshot["graph"]))
        graph_result_sha256 = sha256_record(graph)
        rows, g, f, m = _loads(snapshot, graph)
        evaluation.update(
            status="COMPUTED_EXPERIMENTAL",
            diagnostics_complete=True,
            stages=[
                {
                    "stage_id": "isolated_air_rotor_graph",
                    "request_sha256": graph_request_sha256,
                    "result_sha256": graph_result_sha256,
                }
            ],
            outputs={
                "rotors": rows,
                "gravity_force_body_n": g,
                "net_force_body_n": f,
                "net_moment_cg_body_nm": m,
            },
            output_units={
                "rotors": {
                    "node": "not_applicable",
                    "force_body_n": "N",
                    "reaction_torque_body_nm": "N*m",
                    "moment_cg_body_nm": "N*m",
                },
                "gravity_force_body_n": "N",
                "net_force_body_n": "N",
                "net_moment_cg_body_nm": "N*m",
            },
        )
    except Exception:  # noqa: BLE001
        evaluation.update(
            status="EXECUTION_FAILED",
            diagnostics_complete=False,
            stages=[],
            outputs={},
            output_units={},
            reasons=["Rotor assembly execution failed."],
        )
    return deepcopy(evaluation)
