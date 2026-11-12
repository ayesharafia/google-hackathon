import math
import re
from copy import deepcopy

from . import ledger_rotor_dynamics as ld
from . import mass_ledger_request as ml
from . import static_wrench_solve as ws
from .graph_mission import _normal, _require
from .model_graph_execution import _json
from .provenance import sha256_record

EVALUATION = "ledger_static_wrench_solve_experimental"


def _solve_input(s, o):
    request = deepcopy(s["solve_template"])
    assembly = request["assembly_template"]
    assembly["mass_kg"] = deepcopy(o["total_mass_kg"])
    assembly["cg_body_m"] = deepcopy(o["cg_body_m"])
    return request


def _preflight(req):
    _json(req, budget=49152)
    snapshot = deepcopy(req)
    _require(isinstance(snapshot, dict))
    _require(set(snapshot) == {"evaluation", "ledger", "solve_template"})
    _require(
        snapshot["evaluation"] == "ledger_static_wrench_solve_experimental"
    )
    ml._preflight(snapshot["ledger"])
    template = snapshot["solve_template"]
    _require(isinstance(template, dict))
    _require("assembly_template" in template)
    assembly = template["assembly_template"]
    _require(isinstance(assembly, dict))
    _require(set(assembly) == {
        "evaluation",
        "graph",
        "air_node",
        "rotors",
        "gravity_direction_body",
        "property_source",
    })
    ws._preflight(_solve_input(snapshot, {
        "total_mass_kg": 1,
        "cg_body_m": [0, 0, 0],
    }))
    return snapshot


def _solver_candidates(raw, spec):
    outputs = raw["outputs"]
    _require(set(outputs) == {
        "outcome", "evaluations_used", "candidates",
        "selected_candidate", "assembly",
    })
    used = outputs["evaluations_used"]
    _require(type(used) is int and 2 <= used <= spec["max_evaluations"])
    candidates = outputs["candidates"]
    stages = raw["stages"]
    _require(type(candidates) is list and len(candidates) == used)
    _require(type(stages) is list and len(stages) == used)
    _require(raw["output_units"] == {
        "outcome": "not_applicable",
        "evaluations_used": "1",
        "candidates": [ws._candidate_units() for _ in candidates],
        "selected_candidate": ws._candidate_units(),
        "assembly": _assembly_units(),
    })
    bounds = spec["rotor_speed_bounds"]
    for index, (candidate, stage) in enumerate(zip(candidates, stages)):
        if type(candidate) is not dict:
            raise ValueError("candidate must be a dictionary")
        for value in candidate.values():
            if type(value) is list:
                for number in value:
                    _normal(number)
            else:
                _normal(value)
        speeds = candidate["angular_speeds_rad_s"]
        _require(type(speeds) is list and len(speeds) == len(bounds))
        for speed, bound in zip(speeds, bounds):
            lower, upper = bound["angular_speed_bracket_rad_s"]
            value = _normal(speed)
            _require(value > 0 and lower <= value <= upper)
        ws.ra._vector(candidate["net_force_body_n"])
        ws.ra._vector(candidate["net_moment_cg_body_nm"])
        expected = ws._candidate(spec, speeds, {"outputs": {
            "net_force_body_n": candidate["net_force_body_n"],
            "net_moment_cg_body_nm": candidate["net_moment_cg_body_nm"],
        }})
        _require(candidate == expected)
        _require(set(stage) == {
            "stage_id", "request_sha256", "result_sha256",
        })
        expected_id = "final" if index == used - 1 else f"evaluation_{index + 1}"
        _require(stage["stage_id"] == expected_id)
        request = ws._assembly_input(spec, speeds)
        _require(stage["request_sha256"] == sha256_record(request))
        digest = stage["result_sha256"]
        _require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) is not None)
    selected = outputs["selected_candidate"]
    _require(selected == candidates[-1] == min(
        candidates, key=lambda candidate: candidate["max_scaled_residual"],
    ))
    outcome = outputs["outcome"]
    if selected["max_scaled_residual"] <= 1:
        _require(outcome == "RESIDUAL_MET")
    else:
        _require(outcome in ("EVALUATION_LIMIT", "SOLVER_STOPPED"))


def _assembly_units():
    return {
        "rotors": {
            "node": "not_applicable",
            "force_body_n": "N",
            "reaction_torque_body_nm": "N*m",
            "moment_cg_body_nm": "N*m",
        },
        "gravity_force_body_n": "N",
        "net_force_body_n": "N",
        "net_moment_cg_body_nm": "N*m",
    }


def _validated_solve(raw, spec):
    ld._valid(raw, ws.EVALUATION, spec)
    _solver_candidates(raw, spec)
    outputs = raw["outputs"]
    assembly = outputs["assembly"]
    _require(isinstance(assembly, dict))
    _require(set(assembly) == {
        "rotors", "gravity_force_body_n",
        "net_force_body_n", "net_moment_cg_body_nm",
    })
    rows = assembly["rotors"]
    template = spec["assembly_template"]["rotors"]
    _require(isinstance(rows, list) and len(rows) == len(template))
    row_keys = {
        "node", "force_body_n",
        "reaction_torque_body_nm", "moment_cg_body_nm",
    }
    for row, expected in zip(rows, template):
        _require(isinstance(row, dict) and set(row) == row_keys)
        _require(row["node"] == expected["node"])
        for key in row_keys - {"node"}:
            _require(ws.ra._vector(row[key]))
    for key in (
        "gravity_force_body_n", "net_force_body_n",
        "net_moment_cg_body_nm",
    ):
        _require(ws.ra._vector(assembly[key]))
    for axis in range(3):
        force = math.fsum([
            *(row["force_body_n"][axis] for row in rows),
            assembly["gravity_force_body_n"][axis],
        ])
        moment = math.fsum(row["moment_cg_body_nm"][axis] for row in rows)
        _require(math.isclose(
            assembly["net_force_body_n"][axis], force,
            rel_tol=1e-12, abs_tol=1e-12,
        ))
        _require(math.isclose(
            assembly["net_moment_cg_body_nm"][axis], moment,
            rel_tol=1e-12, abs_tol=1e-12,
        ))
    selected = outputs["selected_candidate"]
    _require(assembly["net_force_body_n"] == selected["net_force_body_n"])
    _require(assembly["net_moment_cg_body_nm"] == selected["net_moment_cg_body_nm"])
    return raw


def evaluate_ledger_static_wrench(request):
    result = {
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
        "transfers": {},
        "outputs": {},
        "output_units": {},
        "limitations": [
            "frozen ledger",
            "no inertia used",
            "no trim physical qualification",
        ],
    }
    try:
        s = _preflight(request)
        h = sha256_record(s)
    except Exception:  # noqa: BLE001
        result["reasons"] = ["Invalid request."]
        return deepcopy(result)
    result["request_sha256"] = h
    try:
        ledger_request = s["ledger"]
        lr = ml.evaluate_mass_ledger(ledger_request)
        ld._valid(lr, ml.EVALUATION, ledger_request)
        o = ld._ledger_outputs(lr)
        spec = _solve_input(s, o)
        raw = ws.evaluate_static_wrench_solve(spec)
        _validated_solve(raw, spec)
        result.update(
            status="COMPUTED_EXPERIMENTAL",
            diagnostics_complete=True,
            stages=[
                {
                    "stage_id": "ledger",
                    "request_sha256": sha256_record(ledger_request),
                    "result_sha256": sha256_record(lr),
                },
                {
                    "stage_id": "static_wrench_solve",
                    "request_sha256": sha256_record(spec),
                    "result_sha256": sha256_record(raw),
                },
            ],
            transfers={"mass_kg": o["total_mass_kg"], "cg_body_m": o["cg_body_m"]},
            outputs={"ledger": lr["outputs"], "solve": raw["outputs"]},
            output_units={
                "ledger": lr["output_units"],
                "solve": raw["output_units"],
            },
        )
    except Exception:  # noqa: BLE001
        result["status"] = "EXECUTION_FAILED"
        result["reasons"] = ["Execution failed."]
    return deepcopy(result)
