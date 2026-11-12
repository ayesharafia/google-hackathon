import math
from copy import deepcopy

import numpy as np

from . import ledger_static_wrench as ls
from . import static_wrench_solve as ws
from . import wrench_sensitivity as sn
from .graph_mission import _normal, _require
from .model_graph_execution import _json
from .provenance import sha256_record

EVALUATION = "solved_static_wrench_sensitivity_experimental"


def _sensitivity_input(s, speeds):
    return {
        "evaluation": sn.EVALUATION,
        "assembly": ws._assembly_input(s["solve"], speeds),
        **deepcopy(s["sensitivity_settings"]),
    }


def _preflight(request):
    _json(request, budget=49152)
    s = deepcopy(request)
    _require(type(s) is dict and set(s) == {
        "evaluation", "solve", "sensitivity_settings"
    })
    _require(s["evaluation"] == EVALUATION)
    ws._preflight(s["solve"])
    settings = s["sensitivity_settings"]
    _require(type(settings) is dict and set(settings) == {
        "perturbations", "force_scale_n", "moment_scale_nm",
        "relative_singular_value_cutoff"
    })
    solve = s["solve"]
    template = solve["assembly_template"]
    rotors = template["rotors"]
    perturbations = settings["perturbations"]
    _require(type(perturbations) is list)
    _require(len(perturbations) == len(rotors))
    bounds = {b["node"]: b for b in solve["rotor_speed_bounds"]}
    lower, upper = [], []
    for rotor, perturbation in zip(rotors, perturbations):
        _require(type(perturbation) is dict and set(perturbation) == {
            "node", "half_step_rad_s", "speed_scale_rad_s"
        })
        _require(perturbation["node"] == rotor["node"])
        h = _normal(perturbation["half_step_rad_s"])
        _require(h > 0)
        _require(_normal(perturbation["speed_scale_rad_s"]) > 0)
        lo, hi = bounds[rotor["node"]]["angular_speed_bracket_rad_s"]
        _require(_normal(lo - h) > 0)
        _normal(hi + h)
        lower.append(lo)
        upper.append(hi)
    sn._preflight(_sensitivity_input(s, lower))
    sn._preflight(_sensitivity_input(s, upper))
    annuli = sum(
        node["inputs"]["annuli"] for node in template["graph"]["nodes"]
        if node["model"] == "isolated_hover_bemt_experimental"
    )
    _require(
        annuli * (solve["max_evaluations"] + 1 + 6 * len(rotors)) <= 32768
    )
    return s


def _matrix(value, rows, columns):
    _require(type(value) is list and len(value) == rows)
    for row in value:
        _require(type(row) is list and len(row) == columns)
        for scalar in row:
            _normal(scalar)
    return value


def _level_contract(level, spec, k):
    _require(type(level) is dict)
    _require(set(level) == {
        "half_steps_rad_s",
        "force_jacobian_n_per_rad_s",
        "moment_jacobian_nm_per_rad_s",
        "dimensionless_jacobian",
        "singular_values",
        "numerical_rank",
        "rank_cutoff",
    })
    settings = spec
    perturbations = spec["perturbations"]
    n = len(spec["assembly"]["rotors"])
    _require(len(perturbations) == n)
    half_steps = level["half_steps_rad_s"]
    _require(type(half_steps) is list and len(half_steps) == n)
    for step in half_steps:
        _normal(step)
    _require(half_steps == [
        _normal(p["half_step_rad_s"] / 2 ** k) for p in perturbations
    ])
    force = _matrix(level["force_jacobian_n_per_rad_s"], 3, n)
    moment = _matrix(level["moment_jacobian_nm_per_rad_s"], 3, n)
    dimensionless = _matrix(level["dimensionless_jacobian"], 6, n)
    expected = []
    for matrix, scale in (
        (force, settings["force_scale_n"]),
        (moment, settings["moment_scale_nm"]),
    ):
        for row in matrix:
            expected.append([
                _normal(_normal(value * p["speed_scale_rad_s"]) / scale)
                for value, p in zip(row, perturbations)
            ])
    _require(dimensionless == expected)
    singular = [
        float(value) for value in np.linalg.svd(expected, compute_uv=False)
    ]
    reported = level["singular_values"]
    _require(type(reported) is list and len(reported) == len(singular))
    for actual, independent in zip(reported, singular):
        _require(_normal(actual) >= 0)
        _require(math.isclose(
            actual, independent, rel_tol=1e-12, abs_tol=1e-12
        ))
    largest = singular[0] if singular else 0.0
    cutoff = _normal(settings["relative_singular_value_cutoff"] * largest)
    reported_cutoff = _normal(level["rank_cutoff"])
    _require(reported_cutoff >= 0)
    _require(reported_cutoff == cutoff)
    rank = level["numerical_rank"]
    _require(type(rank) is int)
    _require(rank == sum(value > cutoff for value in singular))


def _sensitivity_units():
    return {
        "nominal_assembly": ls._assembly_units(),
        "rotor_nodes": "not_applicable",
        "evaluations_used": "1",
        "levels": [
            {
                "half_steps_rad_s": "rad/s",
                "force_jacobian_n_per_rad_s": "N/(rad/s)",
                "moment_jacobian_nm_per_rad_s": "N*m/(rad/s)",
                "dimensionless_jacobian": "1",
                "singular_values": "1",
                "numerical_rank": "1",
                "rank_cutoff": "1",
            }
            for _ in range(3)
        ],
        "changes": [
            {
                "force_max_abs_delta": "N/(rad/s)",
                "moment_max_abs_delta": "N*m/(rad/s)",
                "dimensionless_max_abs_delta": "1",
            }
            for _ in range(2)
        ],
    }


def _validated_sensitivity(raw, spec, solve_raw):
    ls.ld._valid(raw, sn.EVALUATION, spec)
    outputs = raw["outputs"]
    _require(type(outputs) is dict)
    _require(set(outputs) == {
        "nominal_assembly", "rotor_nodes", "evaluations_used",
        "levels", "changes",
    })
    solve_request = spec["assembly"]
    rotors = solve_request["rotors"]
    nodes = [rotor["node"] for rotor in rotors]
    n = len(nodes)
    _require(type(outputs["rotor_nodes"]) is list)
    _require(outputs["rotor_nodes"] == nodes)
    _require(type(outputs["evaluations_used"]) is int)
    _require(outputs["evaluations_used"] == 1 + 6 * n)
    levels = outputs["levels"]
    _require(type(levels) is list and len(levels) == 3)
    for k, level in enumerate(levels):
        _level_contract(level, spec, k)
    _require(raw["output_units"] == _sensitivity_units())
    changes = outputs["changes"]
    _require(type(changes) is list and len(changes) == 2)
    change_keys = {
        "force_max_abs_delta", "moment_max_abs_delta",
        "dimensionless_max_abs_delta",
    }
    for change in changes:
        _require(type(change) is dict)
        _require(set(change) == change_keys)
        for key in change_keys:
            _require(_normal(change[key]) >= 0)
    _require(changes == sn._changes(levels))
    stack = [outputs["nominal_assembly"]]
    while stack:
        value = stack.pop()
        if type(value) is dict:
            stack.extend(value.keys())
            stack.extend(value.values())
        elif type(value) is list:
            stack.extend(value)
        elif type(value) is not str:
            _require(type(value) in (int, float))
            _normal(value)
    _require(outputs["nominal_assembly"] == solve_raw["outputs"]["assembly"])
    expected = [("nominal", solve_request)]
    perturbations = spec["perturbations"]
    for k in range(3):
        for i, node in enumerate(nodes):
            h = perturbations[i]["half_step_rad_s"]
            for suffix, sign in (("plus", 1), ("minus", -1)):
                request = sn._perturbed(spec, i, sign * h / (2 ** k))
                expected.append((f"level_{k}_rotor_{node}_{suffix}", request))
    stages = raw["stages"]
    _require(type(stages) is list and len(stages) == 1 + 6 * n)
    for stage, (stage_id, request) in zip(stages, expected):
        _require(type(stage) is dict)
        _require(set(stage) == {"stage_id", "request_sha256", "result_sha256"})
        _require(stage["stage_id"] == stage_id)
        _require(stage["request_sha256"] == sha256_record(request))
        digest = stage["result_sha256"]
        _require(type(digest) is str and len(digest) == 64)
        _require(all(character in "0123456789abcdef" for character in digest))


def evaluate_solved_wrench_sensitivity(request):
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
        "reasons": [],
        "stages": [],
        "transfers": {},
        "outputs": {},
        "output_units": {},
        "limitations": [
            "Numeric-only evaluation.",
            "Sensitivity is evaluated at a frozen point.",
            "Does not establish physical trim.",
            "Does not establish control authority.",
            "Does not provide a global proof.",
            "Inner result SHA validation checks syntax only.",
        ],
    }
    try:
        s = _preflight(request)
        request_hash = sha256_record(s)
    except Exception:  # noqa: BLE001
        result["reasons"] = ["Invalid request."]
        return deepcopy(result)
    result["request_sha256"] = request_hash
    try:
        solve_raw = ws.evaluate_static_wrench_solve(s["solve"])
        ls._validated_solve(solve_raw, s["solve"])
        stages = [{
            "stage_id": "solve",
            "request_sha256": sha256_record(s["solve"]),
            "result_sha256": sha256_record(solve_raw),
        }]
        speeds = list(
            solve_raw["outputs"]["selected_candidate"]["angular_speeds_rad_s"]
        )
        transfers = {"selected_angular_speeds_rad_s": list(speeds)}
        sensitivity = None
        sensitivity_units = "not_applicable"
        state = "NOT_RUN_RESIDUAL_UNMET"
        if solve_raw["outputs"]["outcome"] == "RESIDUAL_MET":
            spec = _sensitivity_input(s, speeds)
            sensitivity_raw = sn.evaluate_wrench_sensitivity(spec)
            _validated_sensitivity(sensitivity_raw, spec, solve_raw)
            state = "COMPUTED_AT_RESIDUAL_MET_POINT"
            sensitivity = sensitivity_raw["outputs"]
            sensitivity_units = sensitivity_raw["output_units"]
            stages.append({
                "stage_id": "sensitivity",
                "request_sha256": sha256_record(spec),
                "result_sha256": sha256_record(sensitivity_raw),
            })
        result.update({
            "status": "COMPUTED_EXPERIMENTAL",
            "diagnostics_complete": True,
            "stages": stages,
            "transfers": transfers,
            "outputs": {
                "sensitivity_state": state,
                "solve": solve_raw["outputs"],
                "sensitivity": sensitivity,
            },
            "output_units": {
                "sensitivity_state": "not_applicable",
                "solve": solve_raw["output_units"],
                "sensitivity": sensitivity_units,
            },
        })
    except Exception:  # noqa: BLE001
        result.update({
            "status": "EXECUTION_FAILED",
            "diagnostics_complete": False,
            "reasons": ["Execution failed."],
            "stages": [], "transfers": {}, "outputs": {}, "output_units": {},
        })
    return deepcopy(result)
