import math
import re
from copy import deepcopy

from scipy.optimize import least_squares

from . import rotor_assembly as ra
from .graph_mission import _normal, _require
from .model_graph_execution import _json
from .provenance import sha256_record
from .rotor_thrust_target_assembly import _valid

EVALUATION = "bounded_static_wrench_solve_experimental"


class _BudgetStop(Exception):
    pass


class _ResidualMet(Exception):
    pass


def _assembly_input(s, speeds):
    assembled = deepcopy(s["assembly_template"])
    speed_by_node = dict(zip(
        (rotor["node"] for rotor in assembled["rotors"]), speeds
    ))
    for node in assembled["graph"]["nodes"]:
        if node["model"] == "isolated_hover_bemt_experimental":
            node["inputs"]["angular_speed_rad_s"] = speed_by_node[node["id"]]
    return assembled


def _preflight(request):
    _json(request, budget=32768)
    _require(type(request) is dict)
    _require(set(request) == {
        "evaluation", "assembly_template", "rotor_speed_bounds",
        "required_net_force_body_n", "required_net_moment_cg_body_nm",
        "absolute_force_tolerance_n", "absolute_moment_tolerance_nm",
        "max_evaluations",
    })
    s = deepcopy(request)
    _require(s["evaluation"] == EVALUATION)
    ra._vector(s["required_net_force_body_n"])
    ra._vector(s["required_net_moment_cg_body_nm"])
    _require(_normal(s["absolute_force_tolerance_n"]) > 0)
    _require(_normal(s["absolute_moment_tolerance_nm"]) > 0)
    _require(type(s["max_evaluations"]) is int and 2 <= s["max_evaluations"] <= 64)
    template = s["assembly_template"]
    _require(type(template) is dict)
    rotors = template.get("rotors")
    _require(type(rotors) is list and 1 <= len(rotors) <= 15)
    bounds = s["rotor_speed_bounds"]
    _require(type(bounds) is list and len(bounds) == len(rotors))
    for bound, rotor in zip(bounds, rotors):
        _require(type(bound) is dict and set(bound) == {
            "node", "angular_speed_bracket_rad_s", "initial_angular_speed_rad_s",
        })
        _require(type(rotor) is dict and "node" in rotor)
        _require(bound["node"] == rotor["node"])
        bracket = bound["angular_speed_bracket_rad_s"]
        _require(type(bracket) is list and len(bracket) == 2)
        lo, hi = (_normal(value) for value in bracket)
        _require(0 < lo < hi)
        initial = _normal(bound["initial_angular_speed_rad_s"])
        _require(lo <= initial <= hi)
    _template_check(s)
    return s


def _template_check(s):
    nodes = s["assembly_template"]["graph"]["nodes"]
    aggregate = 0
    for node in nodes.values() if isinstance(nodes, dict) else nodes:
        if node.get("model") != "isolated_hover_bemt_experimental":
            continue
        inputs = node.get("inputs", {})
        _require("angular_speed_rad_s" not in inputs)
        annuli = inputs.get("annuli")
        _require(type(annuli) is int and 1 <= annuli <= 512)
        aggregate += annuli
    _require(_normal(s["max_evaluations"]) * aggregate <= 32768)
    ra._preflight(_assembly_input(
        s, [entry["initial_angular_speed_rad_s"] for entry in s["rotor_speed_bounds"]]
    ))


def _assembly_contract(raw, req):
    _valid(raw, ra.EVALUATION, req)
    vector_keys = (
        "gravity_force_body_n",
        "net_force_body_n",
        "net_moment_cg_body_nm",
    )
    outputs = raw["outputs"]
    _require(
        isinstance(outputs, dict)
        and set(outputs) == {"rotors", *vector_keys}
    )
    _require(
        raw["output_units"] == {
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
    )
    rows = outputs["rotors"]
    row_keys = {
        "node", "force_body_n", "reaction_torque_body_nm", "moment_cg_body_nm"
    }
    _require(isinstance(rows, list))
    for row in rows:
        _require(isinstance(row, dict) and set(row) == row_keys)
        for key in row_keys - {"node"}:
            ra._vector(row[key])
    _require(
        [row["node"] for row in rows] == [rotor["node"] for rotor in req["rotors"]]
    )
    for key in vector_keys:
        ra._vector(outputs[key])
    for i in range(3):
        force = math.fsum(
            [row["force_body_n"][i] for row in rows]
            + [outputs["gravity_force_body_n"][i]]
        )
        moment = math.fsum(row["moment_cg_body_nm"][i] for row in rows)
        for key, expected in (
            ("net_force_body_n", force), ("net_moment_cg_body_nm", moment)
        ):
            _require(math.isfinite(expected))
            _require(
                math.isclose(outputs[key][i], expected, rel_tol=1e-12, abs_tol=1e-12)
            )
    stages = raw["stages"]
    _require(isinstance(stages, list) and len(stages) == 1)
    stage = stages[0]
    _require(isinstance(stage, dict) and set(stage) == {
        "stage_id", "request_sha256", "result_sha256"
    })
    _require(stage["stage_id"] == "isolated_air_rotor_graph")
    _require(stage["request_sha256"] == sha256_record(req["graph"]))
    digest = stage["result_sha256"]
    _require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None)


def _candidate(s, speeds, raw):
    outputs = raw["outputs"]
    force = [_normal(v) for v in outputs["net_force_body_n"]]
    moment = [_normal(v) for v in outputs["net_moment_cg_body_nm"]]
    required_force = [_normal(v) for v in s["required_net_force_body_n"]]
    required_moment = [_normal(v) for v in s["required_net_moment_cg_body_nm"]]
    _require(len(force) == len(moment) == len(required_force) == len(required_moment) == 3)
    ft = _normal(s["absolute_force_tolerance_n"])
    mt = _normal(s["absolute_moment_tolerance_nm"])
    _require(ft > 0 and mt > 0)
    fr = [_normal(a - r) for a, r in zip(force, required_force)]
    mr = [_normal(a - r) for a, r in zip(moment, required_moment)]
    scaled = [_normal(v / ft) for v in fr] + [_normal(v / mt) for v in mr]
    return {
        "angular_speeds_rad_s": [_normal(v) for v in speeds],
        "net_force_body_n": force,
        "net_moment_cg_body_nm": moment,
        "force_residual_n": fr,
        "moment_residual_nm": mr,
        "scaled_residual": scaled,
        "max_scaled_residual": max(abs(v) for v in scaled),
    }

def _candidate_units():
    return {
        "angular_speeds_rad_s": "rad/s",
        "net_force_body_n": "N",
        "net_moment_cg_body_nm": "N*m",
        "force_residual_n": "N",
        "moment_residual_nm": "N*m",
        "scaled_residual": "1",
        "max_scaled_residual": "1",
    }


def _solve(s):
    bounds = s["rotor_speed_bounds"]
    los = [b["angular_speed_bracket_rad_s"][0] for b in bounds]
    his = [b["angular_speed_bracket_rad_s"][1] for b in bounds]
    initial = [b["initial_angular_speed_rad_s"] for b in bounds]
    maxeval = s["max_evaluations"]
    _require(type(maxeval) is int and 2 <= maxeval <= 64)
    candidates, stages = [], []

    def run(x, final=False):
        speeds = [float(v) for v in x]
        _require(len(speeds) == len(bounds))
        speeds = [_normal(v) for v in speeds]
        _require(all(lo <= v <= hi for v, lo, hi in zip(speeds, los, his)))
        if len(candidates) >= (maxeval if final else maxeval - 1):
            raise _BudgetStop
        req = _assembly_input(s, speeds)
        raw = ra.evaluate_rotor_assembly(req)
        _assembly_contract(raw, req)
        row = _candidate(s, speeds, raw)
        candidates.append(row)
        stages.append({
            "stage_id": "final" if final else f"evaluation_{len(candidates)}",
            "request_sha256": sha256_record(req),
            "result_sha256": sha256_record(raw),
        })
        return row, raw

    def objective(x):
        row, _ = run(x)
        if row["max_scaled_residual"] <= 1:
            raise _ResidualMet
        return row["scaled_residual"]

    budgetstop = False
    try:
        least_squares(
            objective,
            initial,
            bounds=(los, his),
            method="trf",
            ftol=1e-12,
            xtol=1e-12,
            gtol=1e-12,
            max_nfev=maxeval,
        )
    except _BudgetStop:
        budgetstop = True
    except _ResidualMet:
        budgetstop = False

    chosen = deepcopy(min(candidates, key=lambda r: r["max_scaled_residual"]))
    finalrow, finalraw = run(chosen["angular_speeds_rad_s"], final=True)
    _require(finalrow == chosen)
    outcome = (
        "RESIDUAL_MET" if finalrow["max_scaled_residual"] <= 1
        else "EVALUATION_LIMIT" if budgetstop
        else "SOLVER_STOPPED"
    )
    return outcome, candidates, stages, finalrow, finalraw


def evaluate_static_wrench_solve(request):
    envelope = {
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
            ("Bounded local numerical solving assesses only the actual "
            "six-component wrench residual."),
            ("COMPUTED_EXPERIMENTAL does not imply that residual tolerances "
            "were met; the outcome must be inspected."),
            ("No physical trim, control authority, global uniqueness, "
            "infeasibility, electrical or thermal adequacy, or installed "
            "flight capability is established."),
            "No new physics is introduced.",
            ("All actual evaluation calls, including finite-difference "
            "and final calls, are counted."),
            ("A request hash is not validation; inner graph result SHA "
            "checks establish syntax only."),
        ],
    }
    try:
        s = _preflight(request)
        request_sha = sha256_record(s)
    except Exception:  # noqa: BLE001 - Contain failures at the public API boundary.
        envelope["reasons"] = ["Invalid static wrench solve request."]
        return deepcopy(envelope)

    envelope["request_sha256"] = request_sha
    try:
        outcome, candidates, stages, finalrow, finalraw = _solve(s)
        return deepcopy({
            **envelope,
            "status": "COMPUTED_EXPERIMENTAL",
            "diagnostics_complete": True,
            "stages": stages,
            "outputs": {
                "outcome": outcome,
                "evaluations_used": len(candidates),
                "candidates": candidates,
                "selected_candidate": finalrow,
                "assembly": finalraw["outputs"],
            },
            "output_units": {
                "outcome": "not_applicable",
                "evaluations_used": "1",
                "candidates": [_candidate_units() for _ in candidates],
                "selected_candidate": _candidate_units(),
                "assembly": finalraw["output_units"],
            },
        })
    except Exception:  # noqa: BLE001 - Contain failures at the public API boundary.
        envelope["status"] = "EXECUTION_FAILED"
        envelope["reasons"] = ["Static wrench solve execution failed."]
        return deepcopy(envelope)
