import math
from copy import deepcopy

from . import ledger_static_wrench as ls
from . import mass_ledger_request as ml
from . import solved_wrench_sensitivity as ss
from .graph_mission import _normal, _require
from .model_graph_execution import _json
from .provenance import sha256_record

EVALUATION = "ledger_solved_wrench_sensitivity_experimental"


def _analysis_input(s, o):
    analysis = deepcopy(s["analysis_template"])
    assembly = analysis["solve"]["assembly_template"]
    assembly["mass_kg"] = deepcopy(o["total_mass_kg"])
    assembly["cg_body_m"] = deepcopy(o["cg_body_m"])
    return analysis


def _preflight(req):
    _json(req, budget=65536)
    s = deepcopy(req)
    _require(type(s) is dict and set(s) == {
        "evaluation", "ledger", "analysis_template"
    })
    _require(s["evaluation"] == EVALUATION)
    ml._preflight(s["ledger"])
    analysis = s["analysis_template"]
    _require(type(analysis) is dict and set(analysis) == {
        "evaluation", "solve", "sensitivity_settings"
    })
    _require(analysis["evaluation"] == ss.EVALUATION)
    solve = analysis["solve"]
    _require(type(solve) is dict and "assembly_template" in solve)
    assembly = solve["assembly_template"]
    _require(type(assembly) is dict and set(assembly) == {
        "evaluation", "graph", "air_node", "rotors",
        "gravity_direction_body", "property_source"
    })
    ss._preflight(_analysis_input(s, {
        "total_mass_kg": 1, "cg_body_m": [0, 0, 0]
    }))
    return s


def _solve_outputs(outputs, spec):
    _require(type(outputs) is dict and set(outputs) == {
        "outcome", "evaluations_used", "candidates", "selected_candidate", "assembly"
    })
    count = outputs["evaluations_used"]
    _require(type(count) is int and 2 <= count <= spec["max_evaluations"])
    candidates, selected = outputs["candidates"], outputs["selected_candidate"]
    _require(type(candidates) is list and len(candidates) == count)
    bounds = spec["rotor_speed_bounds"]
    candidate_keys = {
        "angular_speeds_rad_s", "net_force_body_n", "net_moment_cg_body_nm",
        "force_residual_n", "moment_residual_nm", "scaled_residual",
        "max_scaled_residual",
    }
    for candidate in candidates + [selected]:
        _require(type(candidate) is dict and set(candidate) == candidate_keys)
        for key in candidate_keys - {"max_scaled_residual"}:
            _require(type(candidate[key]) is list)
            for value in candidate[key]:
                _normal(value)
        _normal(candidate["max_scaled_residual"])
        speeds = candidate["angular_speeds_rad_s"]
        _require(len(speeds) == len(bounds))
        for speed, bound in zip(speeds, bounds):
            low, high = bound["angular_speed_bracket_rad_s"]
            _require(low <= speed <= high)
        force = ss.ws.ra._vector(candidate["net_force_body_n"])
        moment = ss.ws.ra._vector(candidate["net_moment_cg_body_nm"])
        expected = ss.ws._candidate(spec, speeds, {"outputs": {
            "net_force_body_n": force, "net_moment_cg_body_nm": moment
        }})
        _require(candidate == expected)
    _require(selected == candidates[-1] == min(
        candidates, key=lambda candidate: candidate["max_scaled_residual"]
    ))
    outcome = outputs["outcome"]
    _require(type(outcome) is str)
    _require(
        outcome == "RESIDUAL_MET" if selected["max_scaled_residual"] <= 1 else
        outcome in ("EVALUATION_LIMIT", "SOLVER_STOPPED")
    )
    assembly = outputs["assembly"]
    vector_keys = {"gravity_force_body_n", "net_force_body_n", "net_moment_cg_body_nm"}
    _require(type(assembly) is dict and set(assembly) == vector_keys | {"rotors"})
    for key in vector_keys:
        ss.ws.ra._vector(assembly[key])
        for value in assembly[key]:
            _normal(value)
    rows, rotors = assembly["rotors"], spec["assembly_template"]["rotors"]
    _require(type(rows) is list and len(rows) == len(rotors))
    row_vectors = {"force_body_n", "reaction_torque_body_nm", "moment_cg_body_nm"}
    for row, rotor in zip(rows, rotors):
        _require(type(row) is dict and set(row) == row_vectors | {"node"})
        _require(type(row["node"]) is str and row["node"] == rotor["node"])
        for key in row_vectors:
            ss.ws.ra._vector(row[key])
            for value in row[key]:
                _normal(value)
    for axis in range(3):
        force = sum(row["force_body_n"][axis] for row in rows)
        force += assembly["gravity_force_body_n"][axis]
        moment = sum(row["moment_cg_body_nm"][axis] for row in rows)
        _require(math.isclose(force, assembly["net_force_body_n"][axis],
                              rel_tol=1e-12, abs_tol=1e-12))
        _require(math.isclose(moment, assembly["net_moment_cg_body_nm"][axis],
                              rel_tol=1e-12, abs_tol=1e-12))
    for key in ("net_force_body_n", "net_moment_cg_body_nm"):
        _require(assembly[key] == selected[key])
    return selected["angular_speeds_rad_s"]


def _solver_units(outputs):
    return {
        "outcome": "not_applicable", "evaluations_used": "1",
        "candidates": [ss.ws._candidate_units() for _ in outputs["candidates"]],
        "selected_candidate": ss.ws._candidate_units(),
        "assembly": ls._assembly_units(),
    }


def _validate_outputs_sensitivity(outputs, spec, solveoutputs):
    def guard(value):
        if type(value) is dict:
            _require(all(type(key) is str for key in value))
            for child in value.values():
                guard(child)
        elif type(value) is list:
            for child in value:
                guard(child)
        elif type(value) is not str:
            _normal(value)

    _require(type(outputs) is dict)
    _require(set(outputs) == {
        "nominal_assembly", "rotor_nodes", "evaluations_used",
        "levels", "changes",
    })
    snreq = ss._sensitivity_input(
        spec, solveoutputs["selected_candidate"]["angular_speeds_rad_s"]
    )
    rotor_nodes = [rotor["node"] for rotor in snreq["assembly"]["rotors"]]
    _require(type(outputs["rotor_nodes"]) is list)
    _require(all(type(node) is str for node in outputs["rotor_nodes"]))
    _require(outputs["rotor_nodes"] == rotor_nodes)
    _require(type(outputs["evaluations_used"]) is int)
    _require(outputs["evaluations_used"] == 1 + 6 * len(rotor_nodes))

    nominal = outputs["nominal_assembly"]
    _require(type(nominal) is dict)
    guard(nominal)
    guard(solveoutputs["assembly"])
    _require(nominal == solveoutputs["assembly"])

    levels = outputs["levels"]
    _require(type(levels) is list and len(levels) == 3)
    for k, level in enumerate(levels):
        ss._level_contract(level, snreq, k)

    changes = outputs["changes"]
    _require(type(changes) is list and len(changes) == 2)
    change_keys = {
        "force_max_abs_delta", "moment_max_abs_delta",
        "dimensionless_max_abs_delta",
    }
    for change in changes:
        _require(type(change) is dict and set(change) == change_keys)
        for key in change_keys:
            _require(_normal(change[key]) >= 0)
    _require(changes == ss.sn._changes(levels))


def _validated_analysis(raw, spec):
    import re

    ls.ld._valid(raw, ss.EVALUATION, spec)

    outputs = raw["outputs"]
    _require(type(outputs) is dict)
    _require(set(outputs) == {"sensitivity_state", "solve", "sensitivity"})

    solve_outputs = outputs["solve"]
    _require(type(solve_outputs) is dict)
    _require(set(solve_outputs) == {
        "outcome", "evaluations_used", "candidates",
        "selected_candidate", "assembly",
    })
    speeds = _solve_outputs(solve_outputs, spec["solve"])
    _require(type(speeds) is list)
    for speed in speeds:
        _normal(speed)

    outcome = solve_outputs["outcome"]
    met = outcome == "RESIDUAL_MET"
    if met:
        _require(
            outputs["sensitivity_state"]
            == "COMPUTED_AT_RESIDUAL_MET_POINT"
        )
        _require(type(outputs["sensitivity"]) is dict)
        _validate_outputs_sensitivity(
            outputs["sensitivity"], spec, solve_outputs
        )
    else:
        _require(outcome in {"EVALUATION_LIMIT", "SOLVER_STOPPED"})
        _require(
            outputs["sensitivity_state"] == "NOT_RUN_RESIDUAL_UNMET"
        )
        _require(outputs["sensitivity"] is None)

    expected_units = {
        "sensitivity_state": "not_applicable",
        "solve": _solver_units(solve_outputs),
        "sensitivity": (
            ss._sensitivity_units() if met else "not_applicable"
        ),
    }
    _require(type(raw["output_units"]) is dict)
    _require(raw["output_units"] == expected_units)

    transfers = raw["transfers"]
    _require(type(transfers) is dict)
    _require(set(transfers) == {"selected_angular_speeds_rad_s"})
    transferred = transfers["selected_angular_speeds_rad_s"]
    _require(type(transferred) is list)
    for speed in transferred:
        _normal(speed)
    _require(transferred == speeds)

    stages = raw["stages"]
    _require(type(stages) is list)
    _require(len(stages) == (2 if met else 1))
    requests = [("solve", spec["solve"])]
    if met:
        requests.append((
            "sensitivity", ss._sensitivity_input(spec, speeds)
        ))

    for stage, (stage_id, request) in zip(stages, requests):
        _require(type(stage) is dict)
        _require(set(stage) == {
            "stage_id", "request_sha256", "result_sha256",
        })
        _require(stage["stage_id"] == stage_id)
        _require(stage["request_sha256"] == sha256_record(request))
        result_hash = stage["result_sha256"]
        _require(type(result_hash) is str)
        _require(re.fullmatch(r"[0-9a-f]{64}", result_hash) is not None)

    return outputs


def evaluate_ledger_solved_sensitivity(request):
    result = {
        "evaluation": EVALUATION,
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "evidence_level": "unverified",
        "aircraft_status": None,
        "feasibility": None,
        "status": "GRAPH_INVALID",
        "diagnostics_complete": False,
        "reasons": ["Invalid request."],
        "stages": [],
        "transfers": {},
        "outputs": {},
        "output_units": {},
        "limitations": [
            "Frozen ledger inertia is reported but not used.",
            "No trim or physical qualification is established.",
            "Inner raw SHA-256 hashes identify data only.",
        ],
    }
    try:
        root = _preflight(request)
        request_hash = sha256_record(root)
    except Exception:  # noqa: BLE001
        return deepcopy(result)
    result["request_sha256"] = request_hash
    try:
        sledger = root["ledger"]
        ledger_request_hash = sha256_record(sledger)
        lr = ml.evaluate_mass_ledger(sledger)
        ls.ld._valid(lr, ml.EVALUATION, sledger)
        ledger_result_hash = sha256_record(lr)
        o = ls.ld._ledger_outputs(lr)
        spec = _analysis_input(root, o)
        analysis_request_hash = sha256_record(spec)
        raw = ss.evaluate_solved_wrench_sensitivity(spec)
        _validated_analysis(raw, spec)
        analysis_result_hash = sha256_record(raw)
        completed = deepcopy(result)
        completed.update(
            status="COMPUTED_EXPERIMENTAL",
            diagnostics_complete=True,
            reasons=[],
            stages=[
                {
                    "stage_id": "ledger",
                    "request_sha256": ledger_request_hash,
                    "result_sha256": ledger_result_hash,
                },
                {
                    "stage_id": "solved_sensitivity",
                    "request_sha256": analysis_request_hash,
                    "result_sha256": analysis_result_hash,
                },
            ],
            transfers={
                "mass_kg": o["total_mass_kg"],
                "cg_body_m": o["cg_body_m"],
            },
            outputs={"ledger": o, "analysis": raw["outputs"]},
            output_units={
                "ledger": lr["output_units"],
                "analysis": raw["output_units"],
            },
        )
        return deepcopy(completed)
    except Exception:  # noqa: BLE001
        result.update(
            status="EXECUTION_FAILED",
            reasons=["Execution failed."],
        )
        return deepcopy(result)
