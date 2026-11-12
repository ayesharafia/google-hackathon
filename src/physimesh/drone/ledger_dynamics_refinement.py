import math
from copy import deepcopy

from . import ledger_rotor_dynamics as ld
from .graph_mission import _normal
from .graph_mission import _require as _base_require
from .model_graph_execution import _json
from .provenance import sha256_record

EVALUATION = "ledger_dynamics_timestep_refinement_experimental"


def _require(condition, reason=None):
    _base_require(condition)


def _preflight(request):
    _json(request, budget=65536)
    snapshot = deepcopy(request)
    _require(type(snapshot) is dict, "request must be a builtin dict")
    _require(set(snapshot) == {"evaluation", "dynamics"}, "invalid request keys")
    _require(snapshot["evaluation"] == EVALUATION, "incorrect evaluation")
    ld._preflight(snapshot["dynamics"])

    dynamics = snapshot["dynamics"]
    steps = dynamics["steps"]
    _require(type(steps) is int and 1 <= steps <= 250, "invalid dynamics steps")
    dt_s = _normal(dynamics["dt_s"])
    _require(dt_s > 0, "dt_s must be positive")
    horizon_s = _normal(dt_s * steps)
    _require(horizon_s > 0, "elapsed time must be positive")

    requests = []
    for factor in (1, 2, 4):
        refined = deepcopy(snapshot["dynamics"])
        refined_dynamics = refined
        refined_dynamics["steps"] = steps * factor
        refined_dynamics["dt_s"] = dt_s / factor
        refined_dt = _normal(refined_dynamics["dt_s"])
        _require(refined_dt > 0, "refined dt_s must be positive")
        elapsed = _normal(refined_dt * refined_dynamics["steps"])
        _require(elapsed > 0, "refined elapsed time must be positive")
        _require(elapsed == horizon_s, "refinement must preserve the horizon")
        requests.append(refined)

    return snapshot, requests, horizon_s


def _state(raw, request):
    _json(raw, budget=131072, items=4096)
    ld._valid(raw, ld.EVALUATION, request)
    outputs = raw["outputs"]
    units = raw["output_units"]
    output_keys = {"ledger", "frozen_dynamics"}
    _require(type(outputs) is dict and set(outputs) == output_keys,
             "invalid output keys")
    _require(type(units) is dict and set(units) == output_keys,
             "invalid output unit keys")
    ld._ledger_outputs({"outputs": outputs["ledger"],
                        "output_units": units["ledger"]})

    dynamics = outputs["frozen_dynamics"]["dynamics"]
    dynamics_units = units["frozen_dynamics"]["dynamics"]
    final_state = dynamics["final_state"]
    final_units = dynamics_units["final_state"]
    expected_units = {
        "position_enu_m": "m",
        "velocity_enu_m_s": "m/s",
        "quaternion_body_to_enu": "1",
        "angular_velocity_body_rad_s": "rad/s",
    }
    _require(type(final_state) is dict and set(final_state) == set(expected_units),
             "invalid final state keys")
    _require(type(final_units) is dict and final_units == expected_units,
             "invalid final state units")
    for key in expected_units:
        values = final_state[key]
        length = 4 if key == "quaternion_body_to_enu" else 3
        _require(type(values) is list and len(values) == length,
                 "invalid final state vector")
        for value in values:
            _require(type(value) in (int, float), "invalid state component")
            _normal(value)
            _require(math.isfinite(value), "nonfinite state component")
    _require(abs(math.hypot(*final_state["quaternion_body_to_enu"]) - 1) <= 1e-12,
             "quaternion must have unit norm")

    expected = request
    _require(type(dynamics["steps"]) is int
             and dynamics["steps"] == expected["steps"], "incorrect step count")
    elapsed_s = _normal(dynamics["elapsed_s"])
    _require(elapsed_s == expected["dt_s"] * expected["steps"],
             "incorrect elapsed time")
    _require(dynamics_units["elapsed_s"] == "s"
             and dynamics_units["steps"] == "1", "invalid dynamics units")
    return deepcopy(final_state)


def evaluate_ledger_dynamics_refinement(request):
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
            "Three fixed-initial-state isolated-rotor-load runs use the same ledger.",
            "Raw-stage RK4 finite differences are reported only.",
            "Assembly evaluations are repeated.",
            "Quaternion differences are sign-invariant unitless chords, not rotation angles.",
            "No reference exact solution, extrapolation, or error bound is provided.",
            "Physical accuracy, tolerance passage, and installed flight are not established.",
        ],
    }
    try:
        snapshot, run_requests, horizon = _preflight(request)
    except Exception:  # noqa: BLE001
        envelope["reasons"] = ["Invalid refinement request."]
        return deepcopy(envelope)

    try:
        envelope["request_sha256"] = sha256_record(snapshot)
        _require(len(run_requests) == 3, "Three refinement runs are required.")
        labels = ("coarse", "medium", "fine")
        raw_records, runs, stages, states = [], [], [], []
        for label, run_request in zip(labels, run_requests):
            request_hash = sha256_record(run_request)
            raw_record = ld.evaluate_ledger_rotor_dynamics(run_request)
            raw_records.append(deepcopy(raw_record))
            result_hash = sha256_record(raw_records[-1])
            final_state = deepcopy(_state(raw_record, run_request))
            states.append(final_state)
            runs.append({
                "label": label,
                "dt_s": run_request["dt_s"],
                "steps": run_request["steps"],
                "request_sha256": request_hash,
                "result_sha256": result_hash,
                "final_state": final_state,
            })
            stages.append({
                "stage_id": label,
                "request_sha256": request_hash,
                "result_sha256": result_hash,
            })

        field_units = {}
        quaternion_fields = set()
        for field in states[0]:
            if "quat" in field.lower():
                field_units[field] = "1"
                quaternion_fields.add(field)
            elif field.startswith("position"):
                field_units[field] = "m"
            elif field == "angular_velocity_body_rad_s":
                field_units[field] = "rad/s"
            elif field.startswith("velocity"):
                field_units[field] = "m/s"
        _require(
            len(field_units) == 4 and len(quaternion_fields) == 1,
            "Four dynamics state fields are required.",
        )
        comparisons, comparison_units = {}, {}
        for field, unit in field_units.items():
            differences = []
            for first, second in ((states[0], states[1]), (states[1], states[2])):
                a, b = first[field], second[field]
                expected_length = 4 if field in quaternion_fields else 3
                _require(
                    len(a) == len(b) == expected_length,
                    "Invalid dynamics state vector.",
                )
                difference = math.hypot(*[x - y for x, y in zip(a, b)])
                if field in quaternion_fields:
                    opposite = math.hypot(*[x + y for x, y in zip(a, b)])
                    _require(math.isfinite(opposite), "Nonfinite quaternion difference.")
                    difference = min(difference, opposite)
                _require(math.isfinite(difference), "Nonfinite state difference.")
                differences.append(difference)
            d01, d12 = differences
            order, order_status = None, "UNDEFINED_ZERO_DIFFERENCE"
            if d01 > 0 and d12 > 0:
                order = math.log2(d01) - math.log2(d12)
                _require(math.isfinite(order), "Nonfinite observed order.")
                order_status = "DEFINED_NOT_QUALIFIED"
            comparisons[field] = {
                "coarse_medium": d01,
                "medium_fine": d12,
                "observed_order": order,
                "order_status": order_status,
            }
            comparison_units[field] = {
                "coarse_medium": unit,
                "medium_fine": unit,
                "observed_order": "1",
                "order_status": "not_applicable",
            }

        envelope["outputs"] = {
            "horizon_s": horizon,
            "runs": runs,
            "comparisons": comparisons,
        }
        envelope["output_units"] = {
            "horizon_s": "s",
            "runs": [{
                "label": "not_applicable",
                "dt_s": "s",
                "steps": "1",
                "request_sha256": "not_applicable",
                "result_sha256": "not_applicable",
                "final_state": dict(field_units),
            } for _ in runs],
            "comparisons": comparison_units,
        }
        envelope.update(status="COMPUTED_EXPERIMENTAL", stages=stages, diagnostics_complete=True)
    except Exception:  # noqa: BLE001
        envelope.update(
            status="EXECUTION_FAILED",
            reasons=["Refinement execution failed."],
            stages=[],
            outputs={},
            output_units={},
            diagnostics_complete=False,
        )
    return deepcopy(envelope)
