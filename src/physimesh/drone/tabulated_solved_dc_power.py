"""Experimental actual tabulated coupled solve to constant-parameter DC power."""

import math
from copy import deepcopy

from . import dc_motor as dc
from . import tabulated_static_wrench_solve as solve
from . import tabulated_target_dc_power as power
from . import thermal as th
from .hover_bemt import _normal
from .provenance import sha256_record
from .reference_air_tabulated_hover import _exact
from .tabulated_hover_bemt_request import _json_walk, _require

EVALUATION = "tabulated_solved_dc_power_experimental"
SCHEMA_VERSION = "tabulated_solved_dc_power_v1"
_SOLVE_CATALOG = solve.tabulated_static_wrench_solve_catalog()
_ROOT = ("evaluation", "solve", "motors", "auxiliary")
_LIMITS = {
    "input_json": {**power._JSON, "max_nodes_including_keys": 262144,
                   "max_depth": 20, "max_container_items": 256},
    "solve_input_json": deepcopy(solve._LIMITS["input_json"]),
    "solve_output_json": deepcopy(solve._LIMITS["output_json"]),
    "motor_input_json": deepcopy(power._LIMITS["motor_input_json"]),
    "motor_output_json": deepcopy(power._LIMITS["motor_output_json"]),
    "output_json": {**power._JSON, "max_nodes_including_keys": 2097152,
                    "max_depth": 32, "max_container_items": 2048},
    "core_work": {"rotors_min": 1, "rotors_max": 8, "solve_calls_max": 1,
                  "assembly_evaluations_max": 64, "forward_evaluations_max": 512,
                  "evaluation_annuli_product_max": 65536, "motor_calls_max": 8},
}
_LIMITATIONS = (
    "Experimental isolated tabulated static allocation and declared constant DC-equivalent parameters only.",
    "Residual acceptance establishes no physical control, stability, attainability or aircraft feasibility.",
    "No global convergence, global infeasibility, thermal integration or mission claim.",
    "No battery, ESC feedback, installed interference or temperature-dependent parameters.",
    "Declared motor limit exceedance remains computed, not authority or feasibility evidence.",
    "Sources and heat fractions are unverified caller declarations, not fetched or qualified data.",
    "Only allocated fractions of actual motor losses and auxiliary power are heat; shaft power is not heat.",
    "Hashes bind retained full JSON, not execution attestation, runtime identity or code identity.",
    "Counts represent fully guarded accepted results, not attempted calls or trusted failure causality.",
    "Nonselected solve result digests are format-only provenance without retained payloads.",
    "Shaft cross-binding rel=1e-12 abs=1e-12 W allows multiply-order rounding only.",
)
_REASONS = {
    "unsupported": "Unsupported evaluation.", "invalid": "Invalid bounded solved DC power request.",
    "admission": "Request admission failed.", "solve": "SOLVE_BOUNDARY_FAILED",
    "motor": "MOTOR_BOUNDARY_FAILED", "execution": "POWER_EXECUTION_FAILED",
}


def _snapshot(actual, limit):
    """Walk the whole builtin JSON before copy hooks, hashes or equality."""
    _json_walk(actual, _LIMITS[limit])
    retained = deepcopy(actual)
    _json_walk(retained, _LIMITS[limit])
    return retained


def _preflight(snapshot):
    _require(type(snapshot) is dict and snapshot.keys() == set(_ROOT))
    _exact(snapshot["evaluation"], EVALUATION)
    supplied = snapshot["solve"]
    _json_walk(supplied, _LIMITS["solve_input_json"])
    solve._preflight(supplied)
    motors, rotors = snapshot["motors"], supplied["assembly_template"]["rotors"]
    _require(type(motors) is list and 1 <= len(motors) == len(rotors) <= 8)
    for motor, rotor in zip(motors, rotors, strict=True):
        power._motor_preflight(motor, rotor)
    aux = snapshot["auxiliary"]
    _require(type(aux) is dict and aux.keys() == {"power_w", "heat_fraction", "source"})
    power._scalar(aux["power_w"])
    power._scalar(aux["heat_fraction"], fraction=True)
    power._source(aux["source"])


def _response(status, reasons, digest=None, solves=0, assemblies=0, forwards=0, motors=0):
    return {
        "evaluation": EVALUATION, "schema_version": SCHEMA_VERSION, "status": status,
        "evidence_level": "unverified", "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None, "feasibility": None, "diagnostics_complete": False,
        "solve_result_count": solves, "assembly_evaluation_count": assemblies,
        "forward_evaluation_count": forwards, "motor_result_count": motors,
        "request_sha256": digest, "evaluation_sha256": None, "reasons": list(reasons),
        "limitations": list(_LIMITATIONS), "limits": deepcopy(_LIMITS),
        "outputs": {}, "output_units": {}, "stages": [], "transfers": [],
    }


def _seal(result):
    for key, maximum in (("solve_result_count", 1), ("assembly_evaluation_count", 64),
                         ("forward_evaluation_count", 512), ("motor_result_count", 8)):
        _require(type(result[key]) is int and 0 <= result[key] <= maximum)
    _json_walk(result, _LIMITS["output_json"])
    if result["request_sha256"] is not None and result["status"] in (
        "COMPUTED_EXPERIMENTAL", "EXECUTION_FAILED"
    ):
        result["evaluation_sha256"] = sha256_record({
            key: value for key, value in result.items() if key != "evaluation_sha256"})
    _json_walk(result, _LIMITS["output_json"])
    return result


_SOLVE_KEYS = frozenset((
    "evaluation", "schema_version", "status", "evidence_level", "physical_validation",
    "numerical_qualification", "runtime_identity", "aircraft_status", "feasibility",
    "diagnostics_complete", "evaluation_count", "rotor_evaluation_count", "reasons",
    "limitations", "limits", "request_sha256", "evaluation_sha256", "outputs",
    "output_units", "stages", "transfers",
))
_SOLVE_DYNAMIC = frozenset((
    "status", "diagnostics_complete", "evaluation_count", "rotor_evaluation_count",
    "reasons", "request_sha256", "evaluation_sha256", "outputs", "output_units",
))


def _digest_format(value):
    _require(type(value) is str and len(value) == 64)
    _require(all(c in "0123456789abcdef" for c in value))


def _trace_vector(value, size):
    _require(type(value) is list and len(value) == size)
    for component in value:
        _require(type(component) is float)
        _normal(component, zero=True)
    return value


def _guard_solve_success(actual, request):
    """Pure full V126 success admission, without fabricated child envelopes."""
    _json_walk(actual, _LIMITS["solve_output_json"])
    _json_walk(request, _LIMITS["solve_input_json"])
    solve._preflight(request)
    _require(type(actual) is dict and actual.keys() == _SOLVE_KEYS)
    for key in _SOLVE_KEYS - _SOLVE_DYNAMIC:
        _exact(actual[key], _SOLVE_CATALOG[key])
    _exact(actual["status"], "COMPUTED_EXPERIMENTAL")
    _exact(actual["diagnostics_complete"], True)
    _exact(actual["reasons"], [])
    _exact(actual["request_sha256"], sha256_record(request))
    _exact(actual["evaluation_sha256"], sha256_record({
        key: value for key, value in actual.items() if key != "evaluation_sha256"}))
    units = _SOLVE_CATALOG["output_field_units"]
    _exact(actual["output_units"], units)
    outputs = actual["outputs"]
    _require(type(outputs) is dict and outputs.keys() == units.keys())
    candidates, bounds = outputs["candidates"], request["rotor_speed_bounds"]
    _require(type(candidates) is list and 1 <= len(candidates) <= request["max_evaluations"])
    _exact(actual["evaluation_count"], len(candidates))
    _exact(actual["rotor_evaluation_count"], len(candidates) * len(bounds))
    required_force = solve._assembly._vector(request["required_net_force_body_n"])
    required_moment = solve._assembly._vector(request["required_net_moment_cg_body_nm"])
    ft = solve._assembly._number(request["absolute_force_tolerance_n"])
    mt = solve._assembly._number(request["absolute_moment_tolerance_nm"])
    for index, row in enumerate(candidates):
        _require(type(row) is dict and row.keys() == units["candidates"].keys())
        _exact(row["index"], index)
        speeds = _trace_vector(row["angular_speeds_rad_s"], len(bounds))
        for speed, bound in zip(speeds, bounds, strict=True):
            lo, hi = [solve._assembly._number(v) for v in bound["angular_speed_bracket_rad_s"]]
            _require(lo <= speed <= hi)
        force = _trace_vector(row["net_force_body_n"], 3)
        moment = _trace_vector(row["net_moment_cg_body_nm"], 3)
        fr = [_normal(a - b, zero=True) for a, b in zip(force, required_force, strict=True)]
        mr = [_normal(a - b, zero=True) for a, b in zip(moment, required_moment, strict=True)]
        scaled = [_normal(v / ft, zero=True) for v in fr] + [_normal(v / mt, zero=True) for v in mr]
        _require(all(v == 0.0 or r != 0.0 for v, r in zip(fr + mr, scaled, strict=True)))
        for key, expected in (("force_residual_n", fr), ("moment_residual_nm", mr),
                              ("scaled_residual", scaled),
                              ("max_scaled_residual", max(abs(v) for v in scaled))):
            _exact(row[key], expected)
        recovered = solve._assembly_input(request, speeds)
        _json_walk(recovered, solve._LIMITS["assembly_input_json"])
        _exact(row["request_sha256"], sha256_record(recovered))
        _digest_format(row["result_sha256"])
        # The producer stops on the first accepted residual, without another trial.
        _require(index == len(candidates) - 1 or row["max_scaled_residual"] > 1.0)
    best = min(range(len(candidates)), key=lambda i: candidates[i]["max_scaled_residual"])
    _exact(outputs["selected_index"], best)
    selected = candidates[best]
    injected = outputs["actual_assembly_request"]
    _json_walk(injected, solve._LIMITS["assembly_input_json"])
    _exact(injected, solve._assembly_input(request, selected["angular_speeds_rad_s"]))
    retained = outputs["actual_assembly_result"]
    _json_walk(retained, solve._LIMITS["assembly_output_json"])
    _require(solve._guard_assembly_success(retained, injected) is None)
    _exact(selected["request_sha256"], sha256_record(injected))
    _exact(selected["result_sha256"], sha256_record(retained))
    for key in ("net_force_body_n", "net_moment_cg_body_nm"):
        _exact(selected[key], retained["outputs"][key])
    outcome = ("RESIDUAL_MET" if selected["max_scaled_residual"] <= 1.0 else
               "EVALUATION_LIMIT" if len(candidates) == request["max_evaluations"] else
               "SOLVER_STOPPED")
    _exact(outputs["outcome"], outcome)


def _power_units(ran=True):
    return {
        "solve": {"outputs": deepcopy(_SOLVE_CATALOG["output_field_units"])},
        "power_state": "label",
        "power": ({
            "motors": {"id": "label", "actual_motor_request": deepcopy(power._MOTOR_REQUEST_UNITS),
                       "actual_motor_result": {"outputs": deepcopy(power._MOTOR_UNITS)},
                       "allocated_heat_w": "W", "unallocated_loss_w": "W"},
            **dict.fromkeys(power._TOTAL_FIELDS, "W"), "all_motors_within_declared_limits": "1",
        } if ran else "not_applicable"),
    }


def evaluate_tabulated_solved_dc_power(request):
    """Retain one actual coupled solve, then actual DC results if residuals pass."""
    try:
        snapshot = _snapshot(request, "input_json")
        _require(type(snapshot) is dict and snapshot.keys() == set(_ROOT))
        _require(type(snapshot["evaluation"]) is str)
        if snapshot["evaluation"] != EVALUATION:
            return _seal(_response("SOLVER_UNSUPPORTED", [_REASONS["unsupported"]]))
        _preflight(snapshot)
    except (ValueError, OverflowError):
        return _seal(_response("MODEL_INAPPLICABLE", [_REASONS["invalid"]]))
    except Exception:  # noqa: BLE001 -- ordinary admission faults only.
        return _seal(_response("EXECUTION_FAILED", [_REASONS["admission"]]))
    digest, solves, assemblies, forwards, motors = None, 0, 0, 0, 0
    boundary = "execution"
    try:
        digest = sha256_record(snapshot)
        supplied = snapshot["solve"]
        boundary = "solve"
        retained = _snapshot(solve.evaluate_tabulated_static_wrench_solve(deepcopy(supplied)),
                             "solve_output_json")
        _require(_guard_solve_success(retained, supplied) is None)
        solves, assemblies, forwards = 1, retained["evaluation_count"], retained["rotor_evaluation_count"]
        boundary = "execution"
        solve_digest = sha256_record(retained)
        stages = [{"stage": "solve", "inputs": deepcopy(supplied),
                   "inputs_sha256": sha256_record(supplied), "result_sha256": solve_digest}]
        if retained["outputs"]["outcome"] != "RESIDUAL_MET":
            result = _response("COMPUTED_EXPERIMENTAL", [], digest, solves, assemblies, forwards)
            result.update(diagnostics_complete=True, outputs={"solve": retained,
                          "power_state": "NOT_RUN_RESIDUAL_UNMET", "power": None},
                          output_units=_power_units(False), stages=stages)
            return _seal(result)
        rows, transfers = [], []
        rotors = retained["outputs"]["actual_assembly_result"]["outputs"]["rotors"]
        for index, (entry, rotor) in enumerate(zip(snapshot["motors"], rotors, strict=True)):
            forward = rotor["actual_forward_result"]["outputs"]
            operating = {"angular_speed_rad_s": rotor["actual_forward_request"]["angular_speed_rad_s"],
                         "shaft_torque_nm": forward["shaft_torque_nm"]}
            injected = {"evaluation": dc.EVALUATION, "parameters": deepcopy(entry["parameters"]),
                        "declared_limits": deepcopy(entry["declared_limits"]), "operating_point": operating}
            _json_walk(injected, _LIMITS["motor_input_json"])
            boundary = "motor"
            actual = _snapshot(dc.evaluate_dc_motor(deepcopy(injected)), "motor_output_json")
            _require(power._validate_motor(actual, injected) is None)
            motors += 1
            boundary = "execution"
            values = actual["outputs"]
            _require(math.isclose(values["shaft_power_w"], forward["shaft_power_w"],
                                  rel_tol=1e-12, abs_tol=1e-12))
            allocated = th.checked_product(values["total_loss_w"], entry["heat_fraction_of_motor_loss"])
            unallocated = th.checked_difference(values["total_loss_w"], allocated)
            _require(0 <= allocated <= values["total_loss_w"] and unallocated >= 0)
            rows.append({"id": entry["id"], "actual_motor_request": injected,
                         "actual_motor_result": actual, "allocated_heat_w": allocated,
                         "unallocated_loss_w": unallocated})
            stage, request_digest = "motor:" + entry["id"], sha256_record(injected)
            stages.append({"stage": stage, "inputs": deepcopy(injected),
                           "inputs_sha256": request_digest, "result_sha256": sha256_record(actual)})
            base = f"outputs.actual_assembly_result.outputs.rotors[{index}]."
            for field, producer, unit in (
                ("angular_speed_rad_s", "actual_forward_request.angular_speed_rad_s", "rad/s"),
                ("shaft_torque_nm", "actual_forward_result.outputs.shaft_torque_nm", "N*m"),
            ):
                transfers.append({"from_stage": "solve", "from_field": base + producer,
                                  "to_stage": stage, "to_field": "operating_point." + field,
                                  "value": operating[field], "unit": unit,
                                  "producer_result_sha256": solve_digest,
                                  "consumer_request_sha256": request_digest})
        totals = {}
        for name, field in (("total_shaft_power_w", "shaft_power_w"),
                            ("total_motor_electrical_power_w", "electrical_power_w"),
                            ("total_motor_loss_w", "total_loss_w")):
            totals[name] = dc._power_sum([r["actual_motor_result"]["outputs"][field] for r in rows])
        totals["total_allocated_motor_heat_w"] = dc._power_sum([r["allocated_heat_w"] for r in rows])
        totals["total_unallocated_motor_loss_w"] = dc._power_sum([r["unallocated_loss_w"] for r in rows])
        aux = snapshot["auxiliary"]
        totals["auxiliary_electrical_power_w"] = dc._normal(aux["power_w"])
        totals["auxiliary_heat_w"] = th.checked_product(aux["power_w"], aux["heat_fraction"])
        _require(0 <= totals["auxiliary_heat_w"] <= totals["auxiliary_electrical_power_w"])
        totals["total_electrical_power_w"] = dc._power_sum([
            totals["total_motor_electrical_power_w"], totals["auxiliary_electrical_power_w"]])
        totals["total_heat_w"] = dc._power_sum([
            totals["total_allocated_motor_heat_w"], totals["auxiliary_heat_w"]])
        totals["all_motors_within_declared_limits"] = all(
            r["actual_motor_result"]["outputs"]["declared_limit_status"] == "WITHIN_DECLARED_LIMITS"
            for r in rows)
        result = _response("COMPUTED_EXPERIMENTAL", [], digest, solves, assemblies, forwards, motors)
        result.update(diagnostics_complete=True, outputs={"solve": retained, "power_state": "COMPUTED",
                      "power": {"motors": rows, **totals}}, output_units=_power_units(),
                      stages=stages, transfers=transfers)
        return _seal(result)
    except Exception:  # noqa: BLE001 -- atomic ordinary failures; BaseException propagates.
        return _seal(_response("EXECUTION_FAILED", [_REASONS[boundary]],
                               digest, solves, assemblies, forwards, motors))


def tabulated_solved_dc_power_catalog():
    """Fresh closed metadata, dynamic units, bounded policy; no model calls."""
    return {
        **_response("RESEARCH_ONLY", []), "required_fields": list(_ROOT), "defaults": {},
        "motor_fields": list(power._MOTOR_FIELDS), "parameter_fields": list(power._PARAMETERS),
        "declared_limit_fields": list(power._DECLARED),
        "auxiliary_fields": ["power_w", "heat_fraction", "source"],
        "solve_catalog": deepcopy(_SOLVE_CATALOG),
        "input_units": {"evaluation": "label", "solve": deepcopy(_SOLVE_CATALOG["input_units"]),
                        "motors": {"id": "label", "parameters": deepcopy(power._PARAMETERS),
                                   "declared_limits": deepcopy(power._DECLARED),
                                   "heat_fraction_of_motor_loss": "1", "heat_source": "text"},
                        "auxiliary": {"power_w": "W", "heat_fraction": "1", "source": "text"}},
        "output_field_units": _power_units(),
        "output_field_units_residual_unmet": _power_units(False),
        "count_units": dict.fromkeys(("solve_result_count", "assembly_evaluation_count",
                                      "forward_evaluation_count", "motor_result_count"), "1"),
        "request_contract": {
            "shape": "Exact builtin root evaluation,solve,motors,auxiliary; full unchanged V126 solve; no defaults.",
            "preflight": "Whole JSON before copy/hash/equality; independent V126 budgets and pure preflight, all ordered motor IDs/parameters/limits/fractions/sources and auxiliary before any model call.",
            "motors": "Ordered 1..8 matching solve.assembly_template.rotors; V116 declarations only, no operating point input.",
            "numbers": "V116 k>0,R>=0,I0>=0; four positive inclusive maxima; fractions 0..1; auxiliary power>=0; finite normal builtin numbers or allowed zero, no bool.",
            "sources": "Nonblank caller declarations; applicability exactly constant_parameter_dc_equivalent_only.",
        },
        "bindings": {
            "solve": "Actual V126 once, immediate bounded full snapshot, pure full success guard; no model reruns or fabricated envelopes.",
            "trace": "All counts, native types, bounds, residual arithmetic, recoverable request hashes, earliest minimum and outcome policy checked; nonselected result digests format-only.",
            "initial": "SciPy TRF may adjust the first speed inside bounds; no proof that first trial equals declared initial speeds.",
            "selected": "Full template plus speeds cross-bound to actual selected V112 full success guard, vectors and full digest.",
            "motor": "Actual selected V112 forward request omega and unsigned forward output Q injected directly; actual DC once per rotor then V116 full pure guard; no invented motor evaluation_sha256.",
            "preservation": "Full solve once, full motor request/result once per output row; stages retain actual inputs and request/full-result digests only.",
            "transfers": "Two scalars per motor from full solve digest and actual_assembly_result rotor forward paths to operating_point fields; consumer full request hash.",
            "shaft": "Actual forward shaft P cross-bound rel_tol=1e-12 abs_tol=1e-12 W for rounding only.",
        },
        "formulas": {
            "dc": "V116 checked return-contract arithmetic: I=Q/k+I0; Eb=k*omega; V=Eb+I*R; shaft=Q*omega; electrical=V*I; loss=I*I*R+Eb*I0.",
            "heat": "allocated=actual_motor_loss*fraction; unallocated=loss-allocated; auxiliary electrical=power once, auxiliary heat=power*heat_fraction once.",
            "totals": "Nine V116 watt totals using accepted DC power_sum; total_electrical=motor_electrical+auxiliary; total_heat=allocated_motor_heat+auxiliary_heat; all_motors_within_declared_limits is a boolean declaration check.",
        },
        "response_contract": {
            "dynamic": "RESIDUAL_MET gives power_state COMPUTED and full power units; otherwise COMPUTED_EXPERIMENTAL with full solve, power_state NOT_RUN_RESIDUAL_UNMET, power null, power unit not_applicable, zero motors/transfers.",
            "failures": "Raw noncomputed/malformed/exception child returns only SOLVE_BOUNDARY_FAILED or MOTOR_BOUNDARY_FAILED; no child failure causality trusted; other execution faults POWER_EXECUTION_FAILED.",
            "atomic": "All failures empty outputs/units/stages/transfers, diagnostics false; prior fully guarded counts survive; zero accepted count does not mean zero calls.",
            "counts": "solve_result_count 0..1 only after full success guard; assembly/forward counts copied from guarded V126; motor_result_count 0..8 only after V116 full guard.",
            "hashes": "Request snapshot hash; success/execution failure seal hashes entire root omitting itself; before admission both hashes null; strict bounded output before and after seal.",
            "exceptions": "Ordinary exceptions sanitized, no exception text; BaseException propagates.",
        },
        "status_reason_matrix": {
            "COMPUTED_EXPERIMENTAL": [], "SOLVER_UNSUPPORTED": [_REASONS["unsupported"]],
            "MODEL_INAPPLICABLE": [_REASONS["invalid"]],
            "EXECUTION_FAILED": [_REASONS[k] for k in ("admission", "solve", "motor", "execution")],
        },
    }
