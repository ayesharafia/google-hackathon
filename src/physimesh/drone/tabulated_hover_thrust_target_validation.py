"""Pure bounded validation of full actual V108 inverse responses.

Only the selected full forward response is retained and content-verified.
Intermediate full-result digests are producer-reported provenance: their payloads
are absent, so only their strict digest format can be checked. Failure envelopes
are checked atomically and do not attest that any execution occurred.
"""

import math
import sys

from . import tabulated_hover_thrust_target as _inverse
from .hover_bemt import _mul
from .provenance import sha256_record
from .reference_air_tabulated_hover import _exact, _validate_child
from .tabulated_hover_bemt_request import _json_walk, _require

# Trusted code-owned metadata only; never copy caller data or build envelopes.
_CATALOG = _inverse.tabulated_hover_thrust_target_catalog()

_FAILURES = {
    "TARGET_NOT_BRACKETED": "Target is outside the observed endpoint thrust range.",
    "ITERATION_LIMIT": "Actual forward evaluation budget exhausted.",
    "NUMERICAL_LIMIT": "No finite representable strict interior midpoint.",
    "MODEL_INAPPLICABLE": "Actual forward core refused the physical or numerical domain.",
    "EXECUTION_FAILED": "Actual forward target execution failed.",
}
_TRACE_KEYS = frozenset(_inverse._TRACE_UNITS)
_DYNAMIC = frozenset((
    "status", "reasons", "diagnostics_complete", "request_sha256", "evaluation_sha256",
    "evaluation_count", "outputs", "output_units", "trace",
))


def _digest(value):
    _require(type(value) is str and len(value) == 64)
    _require(all(character in "0123456789abcdef" for character in value))


def _admission(request, limits):
    # Before hashing, equality, guards or any derived request, reject foreign
    # containers/scalars. No deepcopy, conversion hook or solver is involved.
    try:
        _json_walk(request, limits)
        _require(type(request) is dict and request.keys() == set(_inverse._REQUEST_KEYS))
        _require(type(request["evaluation"]) is str)
        if request["evaluation"] != _inverse.EVALUATION:
            return "SOLVER_UNSUPPORTED"
        _inverse._preflight(request)
    except ValueError:
        return "MODEL_INAPPLICABLE"
    return "ADMITTED"


def _empty(actual):
    for name, expected in (("outputs", {}), ("output_units", {}), ("trace", []),
                           ("diagnostics_complete", False)):
        _exact(actual[name], expected)


def _success(actual, request, catalog):
    outputs, trace = actual["outputs"], actual["trace"]
    _require(type(outputs) is dict and outputs.keys() == catalog["output_field_units"].keys())
    _exact(actual["diagnostics_complete"], True)
    _exact(actual["reasons"], [])
    count = actual["evaluation_count"]
    _require(2 <= count <= request["max_evaluations"])
    _require(type(trace) is list and len(trace) == count)
    _exact(outputs["evaluations"], count)
    for name in ("target_thrust_n", "absolute_thrust_tolerance_n"):
        _exact(outputs[name], request[name])
    selected_request = outputs["actual_forward_request"]
    _require(type(selected_request) is dict)
    _exact(selected_request, {
        **request["rotor_template"], "angular_speed_rad_s": outputs["angular_speed_rad_s"],
    })
    selected_result = outputs["actual_forward_result"]
    _require(_validate_child(selected_result, selected_request) is True)
    _exact(actual["output_units"], {
        **_inverse._SCALAR_UNITS,
        "actual_forward_request": catalog["output_field_units"]["actual_forward_request"],
        "actual_forward_result": selected_result["output_units"],
    })
    selected_values = selected_result["outputs"]
    _exact(outputs["achieved_thrust_n"], selected_values["thrust_n"])
    target, tolerance = request["target_thrust_n"], request["absolute_thrust_tolerance_n"]
    _exact(outputs["thrust_residual_n"], selected_values["thrust_n"] - target)
    _require(abs(outputs["thrust_residual_n"]) <= tolerance)

    template = request["rotor_template"]
    radius, density = float(template["radius_m"]), float(template["density_kg_m3"])
    area = _mul(math.pi, _mul(radius, radius))
    coefficient = selected_values["thrust_coefficient"]
    for entry in trace:
        _require(type(entry) is dict and entry.keys() == _TRACE_KEYS)
        omega, thrust, residual = (entry[name] for name in (
            "angular_speed_rad_s", "thrust_n", "thrust_residual_n",
        ))
        _inverse._positive_normal(omega)
        _require(type(thrust) is float and (thrust == 0.0 or thrust >= sys.float_info.min))
        _require(type(residual) is float and math.isfinite(residual))
        _exact(residual, thrust - target)
        tip = _mul(float(omega), radius)
        scale = _mul(_mul(density, area), _mul(tip, tip))
        _exact(thrust, _mul(scale, coefficient))
        for name in ("request_sha256", "full_actual_result_sha256"):
            _digest(entry[name])
        _exact(entry["request_sha256"], sha256_record({
            **template, "angular_speed_rad_s": omega,
        }))

    lo, hi = trace[:2]
    for entry, omega in zip((lo, hi), request["angular_speed_bracket_rad_s"], strict=True):
        _exact(entry["angular_speed_rad_s"], omega)
    zero_angle = all(station["blade_angle_rad"] == 0 for station in template["stations"])
    _require(hi["thrust_n"] > lo["thrust_n"] or (
        zero_angle and hi["thrust_n"] == lo["thrust_n"] == 0.0
    ))
    selected = next((entry for entry in (lo, hi)
                     if abs(entry["thrust_residual_n"]) <= tolerance), None)
    if selected is not None:
        _require(count == 2)
    else:
        _require(lo["thrust_n"] < target < hi["thrust_n"])
        for index, entry in enumerate(trace[2:], start=2):
            midpoint = lo["angular_speed_rad_s"] + (
                hi["angular_speed_rad_s"] - lo["angular_speed_rad_s"]
            ) / 2
            _require(math.isfinite(midpoint)
                     and lo["angular_speed_rad_s"] < midpoint < hi["angular_speed_rad_s"])
            _exact(entry["angular_speed_rad_s"], midpoint)
            _require(lo["thrust_n"] <= entry["thrust_n"] <= hi["thrust_n"])
            if abs(entry["thrust_residual_n"]) <= tolerance:
                _require(index == count - 1)
                selected = entry
                break
            if entry["thrust_residual_n"] < 0:
                lo = entry
            else:
                hi = entry
            _require(lo["thrust_residual_n"] < 0 < hi["thrust_residual_n"])
        _require(selected is not None)
    for output_name, trace_name in (
        ("angular_speed_rad_s", "angular_speed_rad_s"),
        ("achieved_thrust_n", "thrust_n"), ("thrust_residual_n", "thrust_residual_n"),
    ):
        _exact(outputs[output_name], selected[trace_name])
    _exact(selected["full_actual_result_sha256"], sha256_record(selected_result))


def validate_tabulated_hover_thrust_target_result(actual, request):
    """Return None for a valid actual contract, otherwise raise ValueError.

    No mutation, copying hooks, solver calls or reconstructed forward responses.
    Unexpected exceptions (including BaseException) from pure dependencies
    propagate. Atomic failures establish envelope consistency, not execution.
    """
    admission = _admission(request, _CATALOG["limits"]["input_json"])
    _json_walk(actual, _CATALOG["limits"]["output_json"])
    catalog = _CATALOG
    root_keys = catalog.keys() - {
        "required_fields", "rotor_template_fields", "input_units", "output_field_units",
        "trace_field_units", "evaluation_count_unit", "request_contract", "algorithm",
        "response_contract",
    }
    _require(type(actual) is dict and actual.keys() == root_keys)
    for name in root_keys - _DYNAMIC:
        _exact(actual[name], catalog[name])
    status, count = actual["status"], actual["evaluation_count"]
    _require(type(status) is str and type(count) is int)
    if admission != "ADMITTED":
        _exact(status, admission)
        _exact(count, 0)
        _exact(actual["request_sha256"], None)
        _exact(actual["evaluation_sha256"], None)
        _exact(actual["reasons"], ["Unsupported evaluation." if admission == "SOLVER_UNSUPPORTED"
                                   else "Invalid bounded target request."])
        _empty(actual)
        return
    _require(0 <= count <= request["max_evaluations"])
    _digest(actual["request_sha256"])
    _exact(actual["request_sha256"], sha256_record(request))
    if status == "MODEL_INAPPLICABLE":
        _exact(actual["evaluation_sha256"], None)
    else:
        _digest(actual["evaluation_sha256"])
        _exact(actual["evaluation_sha256"], sha256_record({
            key: value for key, value in actual.items() if key != "evaluation_sha256"
        }))
    if status == "COMPUTED_EXPERIMENTAL":
        _success(actual, request, catalog)
        return
    _require(status in _FAILURES)
    _exact(actual["reasons"], [_FAILURES[status]])
    _empty(actual)
    budget = request["max_evaluations"]
    if status == "ITERATION_LIMIT":
        _require(count == budget)
    elif status == "TARGET_NOT_BRACKETED":
        _require(count == 2)
    elif status == "NUMERICAL_LIMIT":
        _require(2 <= count < budget)
    elif status == "MODEL_INAPPLICABLE":
        _require(1 <= count <= budget)
    return


def tabulated_hover_thrust_target_validation_catalog():
    """Fresh boundary description; no private mutable metadata escapes."""
    return {
        "evaluation": _inverse.EVALUATION,
        "boundary": "Full actual V108 inverse JSON response and original bounded request.",
        "selected_result_digest": "Content-verified against the retained full actual forward response.",
        "intermediate_result_digests": (
            "Strict lowercase SHA256 format only; producer-reported provenance. "
            "Intermediate full response payloads are not retained and cannot be content-verified."
        ),
        "trace_arithmetic": "Validated selected CT and accepted SI operation order; no model call.",
        "failure_boundary": "Atomic envelope, reason, hash and count bounds only; no execution attestation.",
        "units_scope": "actual_forward_result units cover only actual_forward_result.outputs.",
        "limitations": [
            "No runtime identity, physical validation, numerical qualification or aircraft feasibility.",
            "No intermediate forward envelopes are reconstructed or independently verified.",
        ],
    }
