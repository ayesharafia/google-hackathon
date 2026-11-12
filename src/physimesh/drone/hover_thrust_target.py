import math
from copy import deepcopy

from . import hover_bemt_request as hb
from .graph_mission import _normal, _require
from .model_graph_execution import _json
from .provenance import sha256_record

EVALUATION = "isolated_hover_thrust_target_experimental"
_TEMPLATE_EVALUATION = "isolated_hover_bemt_experimental"
_REQUEST_KEYS = {
    "evaluation", "rotor_template", "target_thrust_n",
    "angular_speed_bracket_rad_s", "absolute_thrust_tolerance_n",
    "max_evaluations",
}
_POSITIVE_FIELDS = (
    "radius_m", "density_kg_m3", "chord_m", "lift_curve_slope_per_rad",
)
_NONNEGATIVE_FIELDS = ("profile_drag_coefficient", "pitch_tip_rad")
_ARRAY_FIELDS = (
    "radial_fraction", "inflow_ratio", "pitch_rad",
    "approx_inflow_angle_rad", "approx_angle_of_attack_rad",
)


def _finite(value):
    _require(type(value) in (int, float))
    _require(math.isfinite(value))
    _require(_normal(value) is not None)
    return value


def _positive_normal(value):
    _finite(value)
    _require(value > 0 and _normal(value))
    return value


def _preflight(request):
    _json(request, budget=8192)
    snapshot = deepcopy(request)
    _require(type(snapshot) is dict and set(snapshot) == _REQUEST_KEYS)
    _require(snapshot["evaluation"] == EVALUATION)
    template = snapshot["rotor_template"]
    _require(type(template) is dict)
    _require(set(template) == set(hb._REQUEST_KEYS) - {"angular_speed_rad_s"})
    _require(template["evaluation"] == _TEMPLATE_EVALUATION)

    bracket = snapshot["angular_speed_bracket_rad_s"]
    _require(type(bracket) is list and len(bracket) == 2)
    lo, hi = (_positive_normal(value) for value in bracket)
    _require(lo < hi)
    target = _positive_normal(snapshot["target_thrust_n"])
    tolerance = _positive_normal(snapshot["absolute_thrust_tolerance_n"])
    _require(tolerance < target)
    count = snapshot["max_evaluations"]
    _require(type(count) is int and 2 <= count <= 64)
    annuli = template["annuli"]
    _require(type(annuli) is int and 1 <= annuli <= 512)
    _require(count * annuli <= 32768)

    for key in _POSITIVE_FIELDS:
        _require(_finite(template[key]) > 0)
    for key in _NONNEGATIVE_FIELDS:
        _require(_finite(template[key]) >= 0)
    _require(0 < _finite(template["root_cutout_fraction"]) < 1)
    blades = template["blade_count"]
    _require(type(blades) is int and 1 <= blades <= 32)
    twist = template["twist_law"]
    _require(type(twist) is str and twist in ("constant", "hyperbolic", "linear"))
    if twist == "linear":
        _require(_finite(template["pitch_root_rad"]) >= 0)
    else:
        _require(template["pitch_root_rad"] is None)

    structural_keys = set(_POSITIVE_FIELDS) | set(_NONNEGATIVE_FIELDS) | {
        "evaluation", "annuli", "root_cutout_fraction", "blade_count",
        "twist_law", "pitch_root_rad",
    }
    for key in set(template) - structural_keys:
        declaration = template[key]
        _require(type(declaration) is str)
        _require(bool(declaration.strip()) and len(declaration) <= 2000)
    return snapshot


def _forward(template, omega):
    inputs = deepcopy(template)
    inputs["angular_speed_rad_s"] = omega
    raw = hb.evaluate_hover_bemt(inputs)
    _json(raw, budget=32768, items=2048)
    _require(type(raw) is dict)
    _require(raw["model_id"] == "isolated_hover_small_angle_bemt_v1")
    _require(raw["status"] == "COMPUTED_EXPERIMENTAL")
    _require(raw["evidence_level"] == "unverified")
    _require(raw["physical_validation"] == "NOT_ESTABLISHED")
    _require(raw["aircraft_status"] is None and raw["feasibility"] is None)
    _require(type(raw["reasons"]) is list and raw["reasons"] == [])
    units, outputs = raw["output_units"], raw["outputs"]
    _require(type(units) is dict and units == hb._OUTPUT_UNITS)
    _require(type(outputs) is dict and set(outputs) == set(hb._OUTPUT_UNITS))
    for key in set(outputs) - set(_ARRAY_FIELDS) - {"annuli"}:
        value = _finite(outputs[key])
        _require(value >= 0 and _normal(value) is not None)
    annuli = outputs["annuli"]
    _require(type(annuli) is int and annuli == template["annuli"])
    for key in _ARRAY_FIELDS:
        values = outputs[key]
        _require(type(values) is list and len(values) == annuli)
        for value in values:
            _finite(value)
    return inputs, raw


def evaluate_hover_thrust_target(request):
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
        "outputs": {},
        "output_units": {},
        "limitations": [
            "Isolated small-angle model; unvalidated.",
            "Target residual is not physical trim.",
            "Safety is not established.",
            "No stall, Mach, or polar validation.",
            "No interference or electrical-limit assessment.",
            "Aircraft feasibility and operating envelope are not established.",
            "Data hashes establish neither proof nor a physical pass.",
        ],
    }
    try:
        data = _preflight(request)
        target = data["target_thrust_n"]
        tolerance = data["absolute_thrust_tolerance_n"]
        lower, upper = data["angular_speed_bracket_rad_s"]
        budget = data["max_evaluations"]
        request_hash = sha256_record(data)
    except Exception:  # noqa: BLE001
        result["reasons"] = ["invalid_request"]
        return deepcopy(result)

    result["request_sha256"] = request_hash
    try:
        candidates, stages = [], []

        def evaluate(speed):
            inputs, raw = _forward(data["rotor_template"], speed)
            values = raw["outputs"]
            thrust = _normal(values["thrust_n"])
            power = _normal(values["shaft_power_w"])
            torque = _normal(values["shaft_torque_nm"])
            residual = _normal(thrust - target)
            _require(all(math.isfinite(value) for value in
                         (thrust, power, torque, residual)))
            record_hash = sha256_record(deepcopy(raw))
            candidate = {
                "angular_speed_rad_s": speed,
                "thrust_n": thrust,
                "shaft_power_w": power,
                "shaft_torque_nm": torque,
                "residual_n": residual,
                "request_sha256": sha256_record(inputs),
                "result_sha256": record_hash,
            }
            candidates.append(deepcopy(candidate))
            stages.append({
                "stage_id": "eval_" + str(len(candidates)),
                "request_sha256": sha256_record(inputs),
                "result_sha256": record_hash,
            })
            return candidate

        lo, hi = evaluate(lower), evaluate(upper)
        if lo["thrust_n"] > hi["thrust_n"]:
            raise ValueError("model_not_monotonic_observed")
        best = min(candidates, key=lambda item: abs(item["residual_n"]))
        if abs(best["residual_n"]) <= tolerance:
            outcome = "TARGET_RESIDUAL_MET"
        elif not lo["thrust_n"] <= target <= hi["thrust_n"]:
            outcome = "TARGET_NOT_BRACKETED"
        else:
            outcome = "EVALUATION_LIMIT"
            while len(candidates) < budget:
                midpoint = lower + (upper - lower) / 2
                _require(math.isfinite(midpoint) and midpoint > 0)
                if midpoint == lower or midpoint == upper:
                    outcome = "FLOATING_POINT_STAGNATION"
                    break
                current = evaluate(midpoint)
                if not lo["thrust_n"] <= current["thrust_n"] <= hi["thrust_n"]:
                    raise ValueError("model_not_monotonic_observed")
                if abs(current["residual_n"]) < abs(best["residual_n"]):
                    best = current
                if current["thrust_n"] < target:
                    lower, lo = midpoint, current
                else:
                    upper, hi = midpoint, current
                if abs(best["residual_n"]) <= tolerance:
                    outcome = "TARGET_RESIDUAL_MET"
                    break

        candidate_units = {
            "angular_speed_rad_s": "rad/s",
            "thrust_n": "N",
            "shaft_power_w": "W",
            "shaft_torque_nm": "N*m",
            "residual_n": "N",
            "request_sha256": "not_applicable",
            "result_sha256": "not_applicable",
        }
        result["outputs"] = deepcopy({
            "outcome": outcome,
            "target_thrust_n": target,
            "absolute_thrust_tolerance_n": tolerance,
            "evaluations_used": len(candidates),
            "candidates": candidates,
            "best_candidate": best,
            "final_bracket_rad_s": [lower, upper],
        })
        result["output_units"] = {
            "outcome": "not_applicable",
            "target_thrust_n": "N",
            "absolute_thrust_tolerance_n": "N",
            "evaluations_used": "1",
            "candidates": [deepcopy(candidate_units) for _ in candidates],
            "best_candidate": deepcopy(candidate_units),
            "final_bracket_rad_s": ["rad/s", "rad/s"],
        }
        result["stages"] = deepcopy(stages)
        result["status"] = "COMPUTED_EXPERIMENTAL"
        result["diagnostics_complete"] = True
    except Exception:  # noqa: BLE001
        result.update({
            "status": "EXECUTION_FAILED",
            "diagnostics_complete": False,
            "reasons": ["Execution failed."],
            "stages": [],
            "outputs": {},
            "output_units": {},
        })
    return deepcopy(result)
