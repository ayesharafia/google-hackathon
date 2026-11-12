import math
from copy import deepcopy

from . import hover_thrust_target as ht
from . import reference_air_graph as ag
from . import rotor_assembly as ra
from .graph_mission import _normal, _require
from .model_graph_execution import _json
from .provenance import sha256_record

EVALUATION = "prescribed_rotor_thrust_target_assembly_experimental"


def _inverse_request(s, entry, density):
    node = next(
        node for node in s["assembly_template"]["graph"]["nodes"]
        if node["id"] == entry["node"]
    )
    inputs = deepcopy(node["inputs"])
    inputs.pop("angular_speed_rad_s", None)
    inputs["density_kg_m3"] = density
    return {
        "evaluation": ht.EVALUATION,
        "rotor_template": inputs,
        **{
            key: deepcopy(entry[key])
            for key in (
                "target_thrust_n", "angular_speed_bracket_rad_s",
                "absolute_thrust_tolerance_n", "max_evaluations",
            )
        },
    }


def _assembly_input(s, speeds):
    assembly = deepcopy(s["assembly_template"])
    for node in assembly["graph"]["nodes"]:
        if node["id"] in speeds:
            node["inputs"]["angular_speed_rad_s"] = speeds[node["id"]]
    return assembly


def _air_request(s):
    template = s["assembly_template"]
    air_id = template["air_node"]
    air_node = deepcopy(next(
        node for node in template["graph"]["nodes"] if node["id"] == air_id
    ))
    return {
        "evaluation": ag.EVALUATION,
        "nodes": [air_node],
        "connections": [],
        "targets": [{"node": air_id, "port": port}
                    for port in ("density_kg_m3", "gravity_m_s2")],
    }


def _preflight(value):
    _json(value, budget=32768)
    snapshot = deepcopy(value)
    _require(type(snapshot) is dict)
    _require(set(snapshot) == {"evaluation", "assembly_template", "targets"})
    _require(snapshot["evaluation"] == EVALUATION)

    temp = deepcopy(snapshot["assembly_template"])
    _require(type(temp) is dict)
    _require(type(temp.get("graph")) is dict)
    _require(type(temp["graph"].get("nodes")) is list)
    rotors = []
    for node in temp["graph"]["nodes"]:
        _require(type(node) is dict)
        if node.get("model") == "isolated_hover_bemt_experimental":
            _require(type(node.get("inputs")) is dict)
            _require("angular_speed_rad_s" not in node["inputs"])
            node["inputs"]["angular_speed_rad_s"] = 1.0
            rotors.append(node)
    ra._preflight(temp)

    indexed = {node["id"]: node for node in rotors}
    rotors = [indexed[rotor["node"]] for rotor in temp["rotors"]]
    targets = snapshot["targets"]
    _require(type(targets) is list)
    _require(len(targets) == len(rotors))
    work = 0
    for entry, rotor in zip(targets, rotors):
        _require(type(entry) is dict)
        _require(set(entry) == {
            "node", "target_thrust_n", "angular_speed_bracket_rad_s",
            "absolute_thrust_tolerance_n", "max_evaluations",
        })
        _require(entry["node"] == rotor["id"])
        ht._preflight(_inverse_request(snapshot, entry, 1.0))
        work += entry["max_evaluations"] * rotor["inputs"]["annuli"]
    _require(work <= 32768)
    return snapshot


def _valid(raw, evaluation, request):
    _json(raw, budget=131072, items=4096)
    record = raw
    _require(type(record) is dict)
    _require(record["status"] == "COMPUTED_EXPERIMENTAL")
    _require(record["evaluation"] == evaluation)
    _require(record["diagnostics_complete"] is True)
    _require(type(record["reasons"]) is list and record["reasons"] == [])
    _require(record["evidence_level"] == "unverified")
    _require(record["physical_validation"] == "NOT_ESTABLISHED")
    _require(record["numerical_qualification"] == "NOT_ESTABLISHED")
    _require(record["runtime_identity"] == "NOT_ESTABLISHED")
    _require(record["feasibility"] is None)
    _require(record["aircraft_status"] is None)
    _require(record["request_sha256"] == sha256_record(request))
    _require(type(record["outputs"]) is dict)
    _require(type(record["output_units"]) is dict)


def _inverse_solution(raw, spec):
    def number(value):
        _require(type(value) in (int, float))
        _require(math.isfinite(value))
        _require(value == 0 or _normal(value))
        return value

    output_keys = {
        "outcome", "target_thrust_n", "absolute_thrust_tolerance_n",
        "evaluations_used", "candidates", "best_candidate",
        "final_bracket_rad_s",
    }
    candidate_units = {
        "angular_speed_rad_s": "rad/s",
        "thrust_n": "N",
        "shaft_power_w": "W",
        "shaft_torque_nm": "N*m",
        "residual_n": "N",
        "request_sha256": "not_applicable",
        "result_sha256": "not_applicable",
    }
    outputs = raw["outputs"]
    _require(type(outputs) is dict and set(outputs) == output_keys)
    expected_units = {
        "outcome": "not_applicable",
        "target_thrust_n": "N",
        "absolute_thrust_tolerance_n": "N",
        "evaluations_used": "1",
        "candidates": [],
        "best_candidate": deepcopy(candidate_units),
        "final_bracket_rad_s": ["rad/s", "rad/s"],
    }
    target = spec["target_thrust_n"]
    tolerance = spec["absolute_thrust_tolerance_n"]
    _require(outputs["outcome"] == "TARGET_RESIDUAL_MET")
    _require(number(outputs["target_thrust_n"]) == target)
    _require(number(outputs["absolute_thrust_tolerance_n"]) == tolerance)
    count = outputs["evaluations_used"]
    _require(type(count) is int and 2 <= count <= spec["max_evaluations"])
    candidates, stages = outputs["candidates"], raw["stages"]
    _require(type(candidates) is list and len(candidates) == count)
    _require(type(stages) is list and len(stages) == count)
    expected_units["candidates"] = [deepcopy(candidate_units) for _ in candidates]
    _require(type(raw["output_units"]) is dict and raw["output_units"] == expected_units)
    initial_lo, initial_hi = spec["angular_speed_bracket_rad_s"]

    def candidate_check(candidate):
        _require(type(candidate) is dict and set(candidate) == set(candidate_units))
        for key in candidate_units:
            if key not in ("request_sha256", "result_sha256"):
                number(candidate[key])
        speed = candidate["angular_speed_rad_s"]
        _require(speed > 0 and initial_lo <= speed <= initial_hi)
        _require(all(candidate[key] >= 0 for key in (
            "thrust_n", "shaft_power_w", "shaft_torque_nm")))
        _require(candidate["residual_n"] == candidate["thrust_n"] - target)
        request = deepcopy(spec["rotor_template"])
        request["angular_speed_rad_s"] = speed
        _require(type(candidate["request_sha256"]) is str)
        _require(candidate["request_sha256"] == sha256_record(request))
        digest = candidate["result_sha256"]
        _require(type(digest) is str and len(digest) == 64)
        _require(all(char in "0123456789abcdef" for char in digest))

    for i, (candidate, stage) in enumerate(zip(candidates, stages), 1):
        candidate_check(candidate)
        _require(type(stage) is dict and set(stage) == {
            "stage_id", "request_sha256", "result_sha256"})
        _require(stage == {"stage_id": f"eval_{i}",
                              "request_sha256": candidate["request_sha256"],
                              "result_sha256": candidate["result_sha256"]})
    best = outputs["best_candidate"]
    candidate_check(best)
    _require(best in candidates)
    _require(abs(best["residual_n"]) <= tolerance)
    _require(abs(best["residual_n"]) == min(abs(c["residual_n"]) for c in candidates))
    bracket = outputs["final_bracket_rad_s"]
    _require(type(bracket) is list and len(bracket) == 2)
    lo, hi = map(number, bracket)
    _require(0 < lo <= hi and initial_lo <= lo and hi <= initial_hi)
    return best["angular_speed_rad_s"], best["thrust_n"], best["shaft_torque_nm"]


def evaluate_rotor_thrust_target_assembly(request):
    result = {
        "evaluation": EVALUATION,
        "status": "GRAPH_INVALID",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "evidence_level": "unverified",
        "aircraft_status": None,
        "feasibility": None,
        "diagnostics_complete": False,
        "reasons": [], "stages": [], "transfers": {},
        "outputs": {}, "output_units": {},
        "limitations": [
            "Prescribed isolated hover thrust targets; experimental and unvalidated.",
            "Caller mass, CG, air, rotor geometry and axes remain fixed.",
            "No trim, control allocation, mass closure or power feasibility assessment.",
            "No installed-aircraft performance, safety or feasibility claim.",
            "Final assembly recomputes reference air and all rotor loads.",
            "Air-property binding consistency does not establish runtime identity.",
            "Residual and numerical equality checks confer no physical qualification.",
            "Data hashes identify inputs and results; they establish no qualification.",
        ],
    }
    try:
        _json(request, budget=32768)
        s = _preflight(request)
        request_hash = sha256_record(s)
    except Exception:  # noqa: BLE001 - Contain invalid requests at the evaluation boundary.
        result["reasons"] = ["Invalid request."]
        return deepcopy(result)
    result["request_sha256"] = request_hash

    try:
        airreq = _air_request(s)
        air = ag.evaluate_reference_air_graph(airreq)
        _valid(air, ag.EVALUATION, airreq)
        airnode = s["assembly_template"]["air_node"]
        airunits = {"density_kg_m3": "kg/m^3", "gravity_m_s2": "m/s^2"}
        _require(set(air["outputs"]) == {airnode})
        _require(type(air["outputs"][airnode]) is dict)
        _require(set(air["outputs"][airnode]) == set(airunits))
        _require(type(air["output_units"][airnode]) is dict)
        _require(air["output_units"] == {airnode: airunits})
        for value in air["outputs"][airnode].values():
            _require(type(value) in (int, float))
            _require(math.isfinite(value) and _normal(value) > 0)
        density = air["outputs"][airnode]["density_kg_m3"]
        stages = [{
            "stage_id": "air", "request_sha256": sha256_record(airreq),
            "result_sha256": sha256_record(air),
        }]
        speeds, solved, inverseoutputs, inverseunits, best = {}, [], [], [], {}
        for entry in s["targets"]:
            node = entry["node"]
            invreq = _inverse_request(s, entry, density)
            raw = ht.evaluate_hover_thrust_target(invreq)
            _valid(raw, ht.EVALUATION, invreq)
            _require(raw["outputs"]["outcome"] == "TARGET_RESIDUAL_MET")
            speed, thrust, torque = _inverse_solution(raw, invreq)
            speeds[node] = speed
            best[node] = (thrust, torque)
            solved.append({"node": node, "angular_speed_rad_s": speed})
            inverseoutputs.append({"node": node, **deepcopy(raw["outputs"])})
            inverseunits.append({
                "node": "not_applicable", **deepcopy(raw["output_units"]),
            })
            stages.append({
                "stage_id": "rotor_" + node,
                "request_sha256": sha256_record(invreq),
                "result_sha256": sha256_record(raw),
            })

        assemblyreq = _assembly_input(s, speeds)
        actual = ra.evaluate_rotor_assembly(assemblyreq)
        _valid(actual, ra.EVALUATION, assemblyreq)
        rowunits = {
            "node": "not_applicable", "force_body_n": "N",
            "reaction_torque_body_nm": "N*m", "moment_cg_body_nm": "N*m",
        }
        assemblyunits = {
            "rotors": rowunits, "gravity_force_body_n": "N",
            "net_force_body_n": "N", "net_moment_cg_body_nm": "N*m",
        }
        outputs = actual["outputs"]
        _require(set(outputs) == set(assemblyunits))
        _require(type(actual["output_units"]["rotors"]) is dict)
        _require(actual["output_units"] == assemblyunits)
        rows = outputs["rotors"]
        _require(type(rows) is list and len(rows) == len(s["targets"]))
        for key in ("gravity_force_body_n", "net_force_body_n", "net_moment_cg_body_nm"):
            ra._vector(outputs[key])
        for row, entry in zip(rows, s["targets"], strict=True):
            _require(type(row) is dict and set(row) == set(rowunits))
            _require(row["node"] == entry["node"])
            for key in ("force_body_n", "reaction_torque_body_nm", "moment_cg_body_nm"):
                ra._vector(row[key])
            thrust = math.hypot(*row["force_body_n"])
            torque = math.hypot(*row["reaction_torque_body_nm"])
            best_thrust, best_torque = best[entry["node"]]
            _require(abs(thrust - entry["target_thrust_n"])
                     <= entry["absolute_thrust_tolerance_n"])
            _require(math.isclose(thrust, best_thrust, rel_tol=1e-12, abs_tol=1e-12))
            _require(math.isclose(torque, best_torque, rel_tol=1e-12, abs_tol=1e-12))
        stages.append({
            "stage_id": "assembly", "request_sha256": sha256_record(assemblyreq),
            "result_sha256": sha256_record(actual),
        })
        result.update(
            status="COMPUTED_EXPERIMENTAL", diagnostics_complete=True,
            stages=stages,
            transfers={"density_kg_m3": density, "solved_angular_speeds": solved},
            outputs={
                "air": air["outputs"], "targets": inverseoutputs, "assembly": outputs,
            },
            output_units={
                "air": air["output_units"], "targets": inverseunits,
                "assembly": actual["output_units"],
            },
        )
    except Exception:  # noqa: BLE001 - Contain execution failures at the evaluation boundary.
        result.update(
            status="EXECUTION_FAILED", diagnostics_complete=False,
            reasons=["Execution failed."], stages=[], transfers={},
            outputs={}, output_units={},
        )
    return deepcopy(result)
