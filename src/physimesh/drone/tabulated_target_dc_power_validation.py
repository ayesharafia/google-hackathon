"""Pure validation of retained V116 power contracts, a composition prerequisite.

Discarded failure payloads permit necessary bounds, not execution attestation.
"""

import math

from . import tabulated_target_dc_power as _power
from .provenance import sha256_record
from .reference_air_tabulated_hover import _exact
from .tabulated_hover_bemt_request import _json_walk, _require
from .tabulated_thrust_target_assembly_validation import (
    validate_tabulated_thrust_target_assembly_result,
)

# Code-owned metadata captured once, before inspecting caller-owned JSON.
_CATALOG = _power.tabulated_target_dc_power_catalog()
_DYNAMIC = frozenset((
    "status", "diagnostics_complete", "assembly_inverse_result_count",
    "forward_evaluation_count", "motor_result_count", "request_sha256",
    "evaluation_sha256", "reasons", "outputs", "output_units", "stages", "transfers",
))
_STATIC = frozenset((
    "evaluation", "schema_version", "evidence_level", "physical_validation",
    "numerical_qualification", "runtime_identity", "aircraft_status", "feasibility",
    "limitations", "limits",
))


def _admission(request):
    try:
        _json_walk(request, _CATALOG["limits"]["input_json"])
        _require(type(request) is dict and request.keys() == set(_CATALOG["required_fields"]))
        _require(type(request["evaluation"]) is str)
        if request["evaluation"] != _CATALOG["evaluation"]:
            return "SOLVER_UNSUPPORTED"
        _power._preflight(request)
    except (ValueError, OverflowError):
        return "MODEL_INAPPLICABLE"
    return "ADMITTED"


def _empty(actual):
    for name, expected in (("outputs", {}), ("output_units", {}), ("stages", []),
                           ("transfers", []), ("diagnostics_complete", False)):
        _exact(actual[name], expected)


def _assembly_failure_bounds(status, n, forwards, budgets):
    """V115 necessary prefix bounds, without inventing a discarded envelope."""
    _require(0 <= n <= len(budgets) and 0 <= forwards <= sum(budgets[:n]))
    if n == 0:
        _require(status == "EXECUTION_FAILED" and forwards == 0)
        return
    low, high, last = 2 * (n - 1), sum(budgets[:n - 1]), budgets[n - 1]
    if status == "ITERATION_LIMIT":
        _require(low + last <= forwards <= high + last)
    elif status == "TARGET_NOT_BRACKETED":
        _require(low + 2 <= forwards <= high + 2)
    elif status == "NUMERICAL_LIMIT":
        _require(last >= 3 and low + 2 <= forwards <= high + last - 1)
    elif status == "MODEL_INAPPLICABLE":
        _require(low + 1 <= forwards)
    else:
        _require(low <= forwards)


def _failure(actual, request):
    _empty(actual)
    status, reasons = actual["status"], actual["reasons"]
    matrix = _CATALOG["status_reason_matrix"]
    n, forwards, motors = (actual[name] for name in (
        "assembly_inverse_result_count", "forward_evaluation_count", "motor_result_count"))
    budgets = [r["target_template"]["max_evaluations"] for r in request["assembly"]["rotors"]]
    _require(0 <= n <= len(budgets) and 0 <= forwards <= sum(budgets[:n]))
    _require(0 <= motors <= len(budgets))
    if status == "EXECUTION_FAILED" and reasons == [matrix[status][1]]:
        # Trusted assembly counts are assigned only after the full V115 guard.
        _require((n == 0 and forwards == 0 and motors == 0) or
                 (n == len(budgets) and 2 * n <= forwards <= sum(budgets)))
        return
    _require(status in ("MODEL_INAPPLICABLE", "TARGET_NOT_BRACKETED", "ITERATION_LIMIT",
                        "NUMERICAL_LIMIT", "EXECUTION_FAILED"))
    _exact(reasons, [matrix[status][-1]])
    _exact(motors, 0)
    _assembly_failure_bounds(status, n, forwards, budgets)


def _success(actual, request):
    _exact(actual["diagnostics_complete"], True)
    _exact(actual["reasons"], [])
    _exact(actual["output_units"], _CATALOG["output_field_units"])
    outputs = actual["outputs"]
    _require(type(outputs) is dict and outputs.keys() == {"assembly", "power"})
    assembly, supplied = outputs["assembly"], request["assembly"]
    _json_walk(assembly, _CATALOG["limits"]["assembly_output_json"])
    _require(validate_tabulated_thrust_target_assembly_result(assembly, supplied) is None)
    _exact(assembly["status"], "COMPUTED_EXPERIMENTAL")
    _exact(actual["assembly_inverse_result_count"], assembly["inverse_result_count"])
    _exact(actual["forward_evaluation_count"], assembly["forward_evaluation_count"])
    power = outputs["power"]
    _require(type(power) is dict and power.keys() == _CATALOG["output_field_units"]["power"].keys())
    rows, motors = power["motors"], request["motors"]
    _require(type(rows) is list and len(rows) == len(motors))
    _exact(actual["motor_result_count"], len(rows))
    stages, transfers = actual["stages"], actual["transfers"]
    _require(type(stages) is list and len(stages) == len(rows) + 1)
    _require(type(transfers) is list and len(transfers) == 2 * len(rows))
    assembly_digest = sha256_record(assembly)
    _exact(stages[0], {"stage": "assembly", "inputs": supplied,
                       "inputs_sha256": sha256_record(supplied), "result_sha256": assembly_digest})
    for index, (row, motor, rotor) in enumerate(zip(
        rows, motors, assembly["outputs"]["rotors"], strict=True
    )):
        _require(type(row) is dict and row.keys() ==
                 _CATALOG["output_field_units"]["power"]["motors"].keys())
        _exact(row["id"], motor["id"])
        selected = rotor["actual_target_result"]["outputs"]
        forward = selected["actual_forward_result"]["outputs"]
        operating = {
            "angular_speed_rad_s": selected["actual_forward_request"]["angular_speed_rad_s"],
            "shaft_torque_nm": forward["shaft_torque_nm"],
        }
        motor_request, result = row["actual_motor_request"], row["actual_motor_result"]
        _json_walk(motor_request, _CATALOG["limits"]["motor_input_json"])
        _json_walk(result, _CATALOG["limits"]["motor_output_json"])
        _exact(motor_request, {"evaluation": "constant_parameter_dc_motor_experimental",
                              "parameters": motor["parameters"],
                              "declared_limits": motor["declared_limits"],
                              "operating_point": operating})
        _require(_power._validate_motor(result, motor_request) is None)
        values = result["outputs"]
        _require(math.isclose(values["shaft_power_w"], forward["shaft_power_w"],
                              rel_tol=1e-12, abs_tol=1e-12))
        allocated = _power.th.checked_product(values["total_loss_w"], motor["heat_fraction_of_motor_loss"])
        _exact(row["allocated_heat_w"], allocated)
        _exact(row["unallocated_loss_w"], _power.th.checked_difference(values["total_loss_w"], allocated))
        stage, digest = "motor:" + motor["id"], sha256_record(motor_request)
        _exact(stages[index + 1], {"stage": stage, "inputs": motor_request,
                                  "inputs_sha256": digest, "result_sha256": sha256_record(result)})
        base = f"outputs.rotors[{index}].actual_target_result.outputs."
        for offset, (field, producer, unit) in enumerate((
            ("angular_speed_rad_s", "actual_forward_request.angular_speed_rad_s", "rad/s"),
            ("shaft_torque_nm", "actual_forward_result.outputs.shaft_torque_nm", "N*m"),
        )):
            _exact(transfers[2 * index + offset], {
                "from_stage": "assembly", "from_field": base + producer,
                "to_stage": stage, "to_field": "operating_point." + field,
                "value": operating[field], "unit": unit,
                "producer_result_sha256": assembly_digest, "consumer_request_sha256": digest,
            })
    for name, field in (("total_shaft_power_w", "shaft_power_w"),
                        ("total_motor_electrical_power_w", "electrical_power_w"),
                        ("total_motor_loss_w", "total_loss_w")):
        _exact(power[name], _power.dc._power_sum([r["actual_motor_result"]["outputs"][field] for r in rows]))
    for name, field in (("total_allocated_motor_heat_w", "allocated_heat_w"),
                        ("total_unallocated_motor_loss_w", "unallocated_loss_w")):
        _exact(power[name], _power.dc._power_sum([r[field] for r in rows]))
    auxiliary = request["auxiliary"]
    _exact(power["auxiliary_electrical_power_w"], _power.dc._normal(auxiliary["power_w"]))
    _exact(power["auxiliary_heat_w"], _power.th.checked_product(auxiliary["power_w"], auxiliary["heat_fraction"]))
    for name, fields in (
        ("total_electrical_power_w", ("total_motor_electrical_power_w", "auxiliary_electrical_power_w")),
        ("total_heat_w", ("total_allocated_motor_heat_w", "auxiliary_heat_w")),
    ):
        _exact(power[name], _power.dc._power_sum([power[field] for field in fields]))
    _exact(power["all_motors_within_declared_limits"], all(
        r["actual_motor_result"]["outputs"]["declared_limit_status"] == "WITHIN_DECLARED_LIMITS"
        for r in rows))


def validate_tabulated_target_dc_power_result(actual, request):
    """Return None for a valid actual contract, otherwise raise ValueError.

    No models, mutation, copying hooks or fabricated component result envelopes.
    Unexpected pure dependency exceptions, including BaseException, propagate.
    """
    _json_walk(actual, _CATALOG["limits"]["output_json"])
    admission = _admission(request)
    _require(type(actual) is dict and actual.keys() == _STATIC | _DYNAMIC)
    for name in _STATIC:
        _exact(actual[name], _CATALOG[name])
    status = actual["status"]
    _require(type(status) is str and status in _CATALOG["status_reason_matrix"])
    for name in ("assembly_inverse_result_count", "forward_evaluation_count", "motor_result_count"):
        _require(type(actual[name]) is int)
    if admission != "ADMITTED":
        _exact(status, admission)
        for name in ("assembly_inverse_result_count", "forward_evaluation_count", "motor_result_count"):
            _exact(actual[name], 0)
        _exact(actual["request_sha256"], None)
        _exact(actual["evaluation_sha256"], None)
        _exact(actual["reasons"], [_CATALOG["status_reason_matrix"][admission][0]])
        _empty(actual)
        return
    _exact(actual["request_sha256"], sha256_record(request))
    _exact(actual["evaluation_sha256"], None if status == "MODEL_INAPPLICABLE" else
           sha256_record({k: v for k, v in actual.items() if k != "evaluation_sha256"}))
    if status == "COMPUTED_EXPERIMENTAL":
        _success(actual, request)
    else:
        _failure(actual, request)
