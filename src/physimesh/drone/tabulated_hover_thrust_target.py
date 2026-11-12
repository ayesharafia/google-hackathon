"""Bounded actual-forward inverse of the accepted tabulated hover request.

Only observed model thrust is targeted. A small residual establishes neither
physical trim nor physical accuracy. No reference-air evaluator is invoked.
"""

import math
import sys
from copy import deepcopy

from . import tabulated_hover_bemt_request as _child
from .provenance import sha256_record
from .reference_air_tabulated_hover import _validate_child
from .tabulated_hover_bemt_request import evaluate_tabulated_hover_bemt

EVALUATION = "tabulated_geometry_hover_thrust_target_experimental"
SCHEMA_VERSION = "tabulated_hover_thrust_target_v1"
_REQUEST_KEYS = (
    "evaluation", "rotor_template", "target_thrust_n",
    "angular_speed_bracket_rad_s", "absolute_thrust_tolerance_n", "max_evaluations",
)
_TEMPLATE_KEYS = frozenset(_child._REQUEST_KEYS) - {"angular_speed_rad_s"}
_REQUIRE = _child._require
_JSON = _child._json_walk
_METADATA = _child.tabulated_hover_bemt_catalog()
_LIMITS = {
    "input_json": {**_METADATA["limits"]["input_json"],
                   "max_depth": 11, "max_nodes_including_keys": 16384},
    "child_input_json": deepcopy(_METADATA["limits"]["input_json"]),
    "child_output_json": deepcopy(_METADATA["limits"]["output_json"]),
    "core_work": {
        "annuli_min": 1, "annuli_max": 512, "blade_count_min": 1, "blade_count_max": 32,
        "stations_min": 2, "stations_max": 256, "max_evaluations_min": 2,
        "max_evaluations_max": 64, "max_evaluations_times_annuli": 32768,
    },
    "output_json": {**_METADATA["limits"]["output_json"],
                    "max_depth": 16, "max_nodes_including_keys": 65536},
}
_SCALAR_UNITS = {
    "angular_speed_rad_s": "rad/s", "target_thrust_n": "N", "achieved_thrust_n": "N",
    "thrust_residual_n": "N", "absolute_thrust_tolerance_n": "N", "evaluations": "1",
}
_TRACE_UNITS = {
    "angular_speed_rad_s": "rad/s", "thrust_n": "N", "thrust_residual_n": "N",
    "request_sha256": "SHA256", "full_actual_result_sha256": "SHA256",
}
_LIMITATIONS = (
    "Local engineering proposal, not an external standard; experimental isolated hover only.",
    "The inverse targets actual accepted forward-model thrust, not physical trim or aircraft feasibility.",
    "Observed thrust ordering establishes no physical monotonicity or accuracy claim.",
    "Small-angle attached linear lift; angle validity and physical accuracy are not established.",
    "Tabulated geometry changes representation only; source and uncertainty are unverified caller assertions.",
    "Density is explicit caller input, not measured weather; no reference-air evaluation is performed.",
    "No Reynolds/Mach feedback, polars, stall, losses, swirl or rotor interaction.",
    "No motor limits, electrical efficiency, aircraft trim, assembly, mission, graph or API integration.",
    "Residual satisfaction and component convergence establish no physical or numerical qualification.",
    "Data hashes establish no code identity, runtime identity, novelty or physical upgrade.",
    "Forward-result units apply only to nested actual_forward_result.outputs, not its envelope.",
)


def _positive_normal(value):
    _REQUIRE(type(value) in (int, float))
    number = float(value)
    _REQUIRE(math.isfinite(number) and number >= sys.float_info.min)


def _preflight(snapshot):
    template = snapshot["rotor_template"]
    _REQUIRE(type(template) is dict and template.keys() == _TEMPLATE_KEYS)
    _REQUIRE(type(template["evaluation"]) is str and template["evaluation"] == _child.EVALUATION)
    for name, maximum in (("annuli", 512), ("blade_count", 32)):
        _REQUIRE(type(template[name]) is int and 1 <= template[name] <= maximum)
    count = snapshot["max_evaluations"]
    _REQUIRE(type(count) is int and 2 <= count <= 64)
    _REQUIRE(count * template["annuli"] <= 32768)
    for name in ("radius_m", "density_kg_m3", "root_cutout_m",
                 "lift_curve_slope_per_rad", "profile_drag_coefficient"):
        _REQUIRE(type(template[name]) in (int, float))
    for name in ("geometry_source", "geometry_kind", "uncertainty_status"):
        _REQUIRE(type(template[name]) is str and bool(template[name].strip()))
    _REQUIRE(template["geometry_kind"] in (
        "measured", "digitized_measurement", "as_designed", "synthetic",
    ))
    stations = template["stations"]
    _REQUIRE(type(stations) is list and 2 <= len(stations) <= 256)
    for station in stations:
        _REQUIRE(type(station) is dict and station.keys() == {"radius_m", "chord_m", "blade_angle_rad"})
        _REQUIRE(all(type(value) in (int, float) for value in station.values()))
    for name in ("target_thrust_n", "absolute_thrust_tolerance_n"):
        _positive_normal(snapshot[name])
    _REQUIRE(snapshot["absolute_thrust_tolerance_n"] < snapshot["target_thrust_n"])
    bracket = snapshot["angular_speed_bracket_rad_s"]
    _REQUIRE(type(bracket) is list and len(bracket) == 2)
    for value in bracket:
        _positive_normal(value)
    _REQUIRE(bracket[0] < bracket[1])


def _response(status, reasons, digest=None, count=0):
    return {
        "evaluation": EVALUATION, "schema_version": SCHEMA_VERSION, "status": status,
        "evidence_level": "unverified", "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None, "feasibility": None, "diagnostics_complete": False,
        "reasons": list(reasons), "limitations": list(_LIMITATIONS), "limits": deepcopy(_LIMITS),
        "request_sha256": digest, "evaluation_sha256": None, "evaluation_count": count,
        "outputs": {}, "output_units": {}, "trace": [],
    }


def _seal(response):
    _REQUIRE(type(response["evaluation_count"]) is int and 0 <= response["evaluation_count"] <= 64)
    _JSON(response, _LIMITS["output_json"])
    if response["request_sha256"] is not None and response["status"] != "MODEL_INAPPLICABLE":
        response["evaluation_sha256"] = sha256_record({
            key: value for key, value in response.items() if key != "evaluation_sha256"
        })
    return response


def tabulated_hover_thrust_target_catalog():
    """Fresh closed request, units, resource bounds, status and digest contracts."""
    return {
        **_response("RESEARCH_ONLY", []),
        "required_fields": list(_REQUEST_KEYS),
        "rotor_template_fields": [key for key in _child._REQUEST_KEYS if key != "angular_speed_rad_s"],
        "input_units": {
            "evaluation": "label", "rotor_template": {
                key: deepcopy(value) for key, value in _METADATA["input_units"].items()
                if key != "angular_speed_rad_s"
            },
            "target_thrust_n": "N", "angular_speed_bracket_rad_s": ["rad/s", "rad/s"],
            "absolute_thrust_tolerance_n": "N", "max_evaluations": "1",
        },
        "output_field_units": {
            **_SCALAR_UNITS,
            "actual_forward_request": deepcopy(_METADATA["input_units"]),
            "actual_forward_result": deepcopy(_METADATA["output_field_units"]),
        },
        "trace_field_units": deepcopy(_TRACE_UNITS), "evaluation_count_unit": "1",
        "request_contract": {
            "extra_fields": "forbidden at every request object", "defaults": {},
            "template_evaluation": _child.EVALUATION,
            "angular_speed_rad_s": "forbidden in template; only actual trial speed is injected",
            "density": "explicit caller density_kg_m3 retained unchanged",
            "preflight": "strict builtin JSON before copying; exact shapes, types, declarations, source class and work",
            "positive_controls": "builtin int/float, no bool; finite normal positive target/tolerance/bracket; tolerance < target",
            "bracket": "exact builtin two-item list; lo < hi; no expansion or defaults",
            "physical_domain": "geometry and physical numerical domain owned by actual accepted forward core",
            "counts": "builtin int only; annuli 1..512, blades 1..32, stations 2..256, evaluations 2..64",
            "child_json": "independent accepted V105 input walk before each actual call and hashing",
        },
        "algorithm": {
            "endpoints": "actual lo then actual hi, including when lo meets tolerance; refusal/exception stops immediately",
            "ordering": "observed T_hi > T_lo, except all-zero blade angles and both thrusts zero",
            "selection": "earliest endpoint meeting absolute tolerance, else actual bounded bisection midpoint",
            "midpoint": "lo + (hi-lo)/2; finite strict representable interior required",
            "monotonicity_guard": "actual midpoint thrust must lie in closed observed endpoint thrust interval; no added tolerance",
            "narrowing": "actual signed thrust residual retains strict target bracket until success",
            "budget": "evaluation_count counts actual calls, including refused/exceptional calls; never exceeds max_evaluations",
        },
        "response_contract": {
            "success": "COMPUTED_EXPERIMENTAL only when abs(actual thrust - target) <= caller tolerance",
            "invalid": "MODEL_INAPPLICABLE without hashes for preflight failure",
            "unsupported": "SOLVER_UNSUPPORTED without hashes for another outer evaluation string",
            "physical_refusal": "MODEL_INAPPLICABLE with accepted outer request hash, no evaluation hash",
            "bounded_refusals": ["TARGET_NOT_BRACKETED", "ITERATION_LIMIT", "NUMERICAL_LIMIT"],
            "failed": "EXECUTION_FAILED for ordinary Exception, malformed actual result or observed ordering failure",
            "atomic": "all failures have empty outputs, output_units and trace; diagnostics_complete false",
            "evaluation_count": "root builtin int 0..max_evaluations on accepted requests; 0 before acceptance",
            "request_sha256": "accepted copied outer request, before any actual call",
            "evaluation_sha256": "all accepted outcomes except MODEL_INAPPLICABLE; entire response omitting itself",
            "encoding": "accepted SHA256 UTF8 sorted compact JSON; ensure_ascii=False, allow_nan=False",
            "trace": "one scalar record per actual call, in call order on success; full_actual_result_sha256 includes child evaluation_sha256",
            "units": "actual_forward_request catalog separate; actual_forward_result units cover only its outputs",
            "alias_boundary": "caller and injected snapshots isolated from call arguments; actual result validated then deep-copied without reconstruction",
            "base_exception": "propagates; ordinary exception text never exported",
        },
    }


class _ForwardRefusal(Exception):
    """Only the accepted guard's legitimate actual domain-refusal branch."""


def evaluate_tabulated_hover_thrust_target(request):
    """Perform bounded actual forward calls; discard all partials on refusal."""
    try:
        _JSON(request, _LIMITS["input_json"])
        snapshot = deepcopy(request)
        _JSON(snapshot, _LIMITS["input_json"])
        _REQUIRE(type(snapshot) is dict and snapshot.keys() == set(_REQUEST_KEYS))
        _REQUIRE(type(snapshot["evaluation"]) is str)
        if snapshot["evaluation"] != EVALUATION:
            return _response("SOLVER_UNSUPPORTED", ["Unsupported evaluation."])
        _preflight(snapshot)
    except ValueError:
        return _response("MODEL_INAPPLICABLE", ["Invalid bounded target request."])
    except Exception:  # noqa: BLE001
        return _response("EXECUTION_FAILED", ["Request snapshot failed."])

    digest, count = None, 0
    try:
        digest = sha256_record(snapshot)
        target = snapshot["target_thrust_n"]
        tolerance = snapshot["absolute_thrust_tolerance_n"]
        budget = snapshot["max_evaluations"]
        trace = []

        def trial(omega):
            nonlocal count
            _REQUIRE(count < budget)
            injected = deepcopy(snapshot["rotor_template"])
            injected["angular_speed_rad_s"] = omega
            _JSON(injected, _LIMITS["child_input_json"])
            request_digest = sha256_record(injected)
            arguments = deepcopy(injected)
            count += 1
            actual = evaluate_tabulated_hover_bemt(arguments)
            if not _validate_child(actual, injected):
                raise _ForwardRefusal
            # Detach immediately: a replacement child may retain/reuse its object.
            # Preserve the full actual envelope and its hash, without reconstruction.
            retained = deepcopy(actual)
            thrust = retained["outputs"]["thrust_n"]
            residual = thrust - target
            _REQUIRE(math.isfinite(residual))
            trace.append({
                "angular_speed_rad_s": omega, "thrust_n": thrust, "thrust_residual_n": residual,
                "request_sha256": request_digest, "full_actual_result_sha256": sha256_record(retained),
            })
            return omega, thrust, residual, injected, retained

        def refusal(status, reason):
            return _seal(_response(status, [reason], digest, count))

        lo = trial(snapshot["angular_speed_bracket_rad_s"][0])
        hi = trial(snapshot["angular_speed_bracket_rad_s"][1])
        zero_angle = all(station["blade_angle_rad"] == 0 for station in snapshot["rotor_template"]["stations"])
        _REQUIRE(hi[1] > lo[1] or (zero_angle and hi[1] == lo[1] == 0.0))
        selected = next((item for item in (lo, hi) if abs(item[2]) <= tolerance), None)
        if selected is None and not lo[1] < target < hi[1]:
            return refusal("TARGET_NOT_BRACKETED", "Target is outside the observed endpoint thrust range.")
        while selected is None:
            if count >= budget:
                return refusal("ITERATION_LIMIT", "Actual forward evaluation budget exhausted.")
            midpoint = lo[0] + (hi[0] - lo[0]) / 2
            if not math.isfinite(midpoint) or not lo[0] < midpoint < hi[0]:
                return refusal("NUMERICAL_LIMIT", "No finite representable strict interior midpoint.")
            current = trial(midpoint)
            _REQUIRE(lo[1] <= current[1] <= hi[1])
            if abs(current[2]) <= tolerance:
                selected = current
            elif current[2] < 0:
                lo = current
            else:
                hi = current
            if selected is None:
                _REQUIRE(lo[2] < 0 < hi[2] and lo[0] < hi[0])
        response = _response("COMPUTED_EXPERIMENTAL", [], digest, count)
        response.update(
            diagnostics_complete=True,
            outputs={
                "angular_speed_rad_s": selected[0], "target_thrust_n": target,
                "achieved_thrust_n": selected[1], "thrust_residual_n": selected[2],
                "absolute_thrust_tolerance_n": tolerance, "evaluations": count,
                "actual_forward_request": selected[3], "actual_forward_result": selected[4],
            },
            output_units={
                **_SCALAR_UNITS, "actual_forward_request": deepcopy(_METADATA["input_units"]),
                "actual_forward_result": deepcopy(selected[4]["output_units"]),
            },
            trace=trace,
        )
        return _seal(response)
    except _ForwardRefusal:
        return _response("MODEL_INAPPLICABLE", ["Actual forward core refused the physical or numerical domain."],
                         digest, count)
    except Exception:  # noqa: BLE001
        return _seal(_response("EXECUTION_FAILED", ["Actual forward target execution failed."], digest, count))
