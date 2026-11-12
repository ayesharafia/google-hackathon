"""Fixed experimental reference-air density to actual tabulated thrust target.

Only actual component results cross the boundary. Data hashes and necessary
failure-count bounds establish neither execution identity nor qualification.
"""

from copy import deepcopy

from . import reference_air_tabulated_hover as _reference
from . import tabulated_hover_bemt_request as _forward
from . import tabulated_hover_thrust_target as _inverse
from .provenance import sha256_record
from .reference_air_properties import reference_air_properties
from .tabulated_hover_thrust_target import evaluate_tabulated_hover_thrust_target
from .tabulated_hover_thrust_target_validation import validate_tabulated_hover_thrust_target_result

EVALUATION = "reference_air_tabulated_hover_thrust_target_experimental"
SCHEMA_VERSION = "reference_air_tabulated_hover_thrust_target_v1"
_REQUEST_KEYS = ("evaluation", "air", "target_template")
_ROTOR_KEYS = _inverse._TEMPLATE_KEYS - {"density_kg_m3"}
_REQUIRE = _forward._require
_JSON = _forward._json_walk
_METADATA = _inverse.tabulated_hover_thrust_target_catalog()
_LIMITS = {
    "input_json": {**_METADATA["limits"]["input_json"],
                   "max_depth": 12, "max_nodes_including_keys": 32768},
    "inverse_input_json": deepcopy(_METADATA["limits"]["input_json"]),
    "inverse_output_json": deepcopy(_METADATA["limits"]["output_json"]),
    "forward_input_json": deepcopy(_METADATA["limits"]["child_input_json"]),
    "forward_output_json": deepcopy(_METADATA["limits"]["child_output_json"]),
    "core_work": {**_METADATA["limits"]["core_work"],
                  "air_calls_max": 1, "inverse_calls_max": 1, "forward_calls_max": 64},
    "output_json": {**_METADATA["limits"]["output_json"],
                    "max_depth": 20, "max_nodes_including_keys": 131072},
}
_REASONS = {
    "unsupported": "Unsupported evaluation.",
    "invalid": "Invalid bounded reference-air target request.",
    "snapshot": "Request snapshot failed.",
    "refusal": "Actual target refused the physical or numerical domain.",
    "TARGET_NOT_BRACKETED": "Actual target is outside the observed endpoint thrust range.",
    "ITERATION_LIMIT": "Actual target forward evaluation budget exhausted.",
    "NUMERICAL_LIMIT": "Actual target reached a representable numerical limit.",
    "EXECUTION_FAILED": "Reference-air target execution or returned contract failed.",
}
_LIMITATIONS = (
    "Local experimental engineering proposal, not an external standard.",
    "Reference dry air supplies density only; it is not measured weather.",
    "Targets accepted isolated-hover model thrust, not physical trim or aircraft feasibility.",
    "Small-angle attached linear lift; angle validity and physical accuracy are not established.",
    "Source, geometry classification and uncertainty remain unverified caller assertions.",
    "No Reynolds/Mach feedback, polars, stall, swirl, losses or rotor interaction.",
    "No motor or structural limits, attainable RPM, aircraft or mission qualification.",
    "No graph, rotor assembly, trim, mission, API or identity updates.",
    "No 80 percent accuracy, novelty, physical or numerical qualification claim.",
    "Hashes bind plain JSON snapshots, not immutable objects or runtime identity.",
    "Intermediate inverse trace result digests are FORMAT-ONLY producer-reported provenance; payloads absent.",
    "Only the selected retained full forward response is content-verified by the accepted guard.",
    "Failure count bounds are necessary envelope checks, not proof that execution occurred.",
    "Target units cover only outputs.target.outputs; selected forward units retain their nested output scope.",
)


def _preflight(snapshot):
    """Structural V108 admission without fabricated density or angular speed."""
    air, target = snapshot["air"], snapshot["target_template"]
    _REQUIRE(type(air) is dict and air.keys() == {"altitude_m", "altitude_kind"})
    _REQUIRE(type(air["altitude_m"]) in (int, float) and 0 <= air["altitude_m"] <= 30000)
    _REQUIRE(type(air["altitude_kind"]) is str
             and air["altitude_kind"] in ("geometric", "geopotential"))
    _REQUIRE(type(target) is dict and target.keys() == set(_inverse._REQUEST_KEYS))
    _REQUIRE(type(target["evaluation"]) is str and target["evaluation"] == _inverse.EVALUATION)
    rotor = target["rotor_template"]
    _REQUIRE(type(rotor) is dict and rotor.keys() == _ROTOR_KEYS)
    _REQUIRE(type(rotor["evaluation"]) is str and rotor["evaluation"] == _forward.EVALUATION)
    for name, maximum in (("annuli", 512), ("blade_count", 32)):
        _REQUIRE(type(rotor[name]) is int and 1 <= rotor[name] <= maximum)
    count = target["max_evaluations"]
    _REQUIRE(type(count) is int and 2 <= count <= 64)
    _REQUIRE(count * rotor["annuli"] <= 32768)
    for name in ("radius_m", "root_cutout_m", "lift_curve_slope_per_rad", "profile_drag_coefficient"):
        _REQUIRE(type(rotor[name]) in (int, float))
    for name in ("geometry_source", "geometry_kind", "uncertainty_status"):
        _REQUIRE(type(rotor[name]) is str and bool(rotor[name].strip()))
    _REQUIRE(rotor["geometry_kind"] in ("measured", "digitized_measurement", "as_designed", "synthetic"))
    stations = rotor["stations"]
    _REQUIRE(type(stations) is list and 2 <= len(stations) <= 256)
    for station in stations:
        _REQUIRE(type(station) is dict and station.keys() == {"radius_m", "chord_m", "blade_angle_rad"})
        _REQUIRE(all(type(value) in (int, float) for value in station.values()))
    for name in ("target_thrust_n", "absolute_thrust_tolerance_n"):
        _inverse._positive_normal(target[name])
    _REQUIRE(target["absolute_thrust_tolerance_n"] < target["target_thrust_n"])
    bracket = target["angular_speed_bracket_rad_s"]
    _REQUIRE(type(bracket) is list and len(bracket) == 2)
    for value in bracket:
        _inverse._positive_normal(value)
    _REQUIRE(bracket[0] < bracket[1])


def _response(status, reasons, digest=None, count=0):
    return {
        "evaluation": EVALUATION, "schema_version": SCHEMA_VERSION, "status": status,
        "evidence_level": "unverified", "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None, "feasibility": None, "diagnostics_complete": False,
        "reasons": list(reasons), "limitations": list(_LIMITATIONS), "limits": deepcopy(_LIMITS),
        "request_sha256": digest, "evaluation_sha256": None, "inverse_evaluation_count": count,
        "outputs": {}, "output_units": {}, "stages": [], "transfers": [],
    }


def _seal(response):
    count = response["inverse_evaluation_count"]
    _REQUIRE(type(count) is int and 0 <= count <= 64)
    _JSON(response, _LIMITS["output_json"])
    if response["request_sha256"] is not None and response["status"] != "MODEL_INAPPLICABLE":
        response["evaluation_sha256"] = sha256_record({
            key: value for key, value in response.items() if key != "evaluation_sha256"
        })
    return response


def reference_air_tabulated_hover_thrust_target_catalog():
    """Fresh closed schemas, independent budgets, status matrix and bindings."""
    target_units = deepcopy(_METADATA["input_units"])
    del target_units["rotor_template"]["density_kg_m3"]
    return {
        **_response("RESEARCH_ONLY", []),
        "required_fields": list(_REQUEST_KEYS),
        "air_fields": ["altitude_m", "altitude_kind"],
        "target_template_fields": list(_inverse._REQUEST_KEYS),
        "rotor_template_fields": [key for key in _forward._REQUEST_KEYS if key in _ROTOR_KEYS],
        "station_fields": ["radius_m", "chord_m", "blade_angle_rad"],
        "input_units": {"evaluation": "label", "air": {"altitude_m": "m", "altitude_kind": "label"},
                        "target_template": target_units},
        "output_field_units": {"air": deepcopy(_reference._AIR_UNITS),
                               "target": deepcopy(_METADATA["output_field_units"])},
        "inverse_evaluation_count_unit": "1",
        "request_contract": {
            "extra_fields": "forbidden in every request object; density and angular speed forbidden in rotor template",
            "defaults": {}, "air": "explicit finite builtin int/float 0..30000 m; geometric/geopotential",
            "target_evaluation": _inverse.EVALUATION, "rotor_evaluation": _forward.EVALUATION,
            "preflight": "strict builtin JSON before copy; closed shapes, numeric types, counts, declarations and controls",
            "controls": "unchanged V108 caller target, tolerance, bracket and budget; no expansion",
            "positive_controls": "finite normal builtin int/float; tolerance < target; two-item list 0 < lo < hi",
            "physical_domain": "geometry and physical numerical domain belong to actual accepted inverse/forward core",
            "child_budgets": "independent inverse walk after actual density injection; forward walks owned by inverse",
            "work": "at most 64 actual forward calls and max_evaluations * annuli <= 32768; inverse call is not a core call",
        },
        "bindings": {
            "air": "actual frozen air/state dataclasses checked by accepted V106 hydrostatic/transport/type/marker guard",
            "target": "actual full inverse JSON checked by accepted V109 guard returning None; no reruns",
            "snapshots": "raw validated air and density detached before inverse; inverse walked then immediately deep-copied",
            "alias_boundaries": "caller, original injected snapshot and component arguments isolated; plain JSON is mutable",
            "stages": "actual inputs, inputs_sha256 and result_sha256 of actual full result; no result payload copies",
            "transfer": "air.state.density_kg_m3 to target.rotor_template.density_kg_m3; scalar kg/m^3 only",
            "transfer_hashes": "producer actual full air digest; consumer actual injected inverse request digest",
            "units": "air covers full raw air; target only outputs.target.outputs; nested forward units retain scope",
            "provenance": "selected full forward content verified; intermediate trace full-result digests FORMAT-ONLY producer reports",
            "failure_count": "only observed count after full actual inverse guard acceptance; necessary bounds, no execution proof",
        },
        "status_reason_matrix": {
            "COMPUTED_EXPERIMENTAL": [], "SOLVER_UNSUPPORTED": [_REASONS["unsupported"]],
            "MODEL_INAPPLICABLE": [_REASONS["invalid"], _REASONS["refusal"]],
            "EXECUTION_FAILED": [_REASONS["snapshot"], _REASONS["EXECUTION_FAILED"]],
            **{status: [_REASONS[status]] for status in (
                "TARGET_NOT_BRACKETED", "ITERATION_LIMIT", "NUMERICAL_LIMIT",
            )},
        },
        "response_contract": {
            "success": "actual raw air once and unchanged full actual inverse once; diagnostics_complete true",
            "atomic": "every failure: empty outputs/output_units/stages/transfers; diagnostics_complete false",
            "request_sha256": "accepted copied outer request; null before acceptance",
            "evaluation_sha256": "entire outer response omitting itself; accepted success/bounded failure/EXECUTION_FAILED only",
            "refusal_hashes": "accepted actual domain refusal has request hash and no evaluation hash",
            "encoding": "accepted canonical sorted compact UTF8 JSON; ensure_ascii=False, allow_nan=False",
            "count": "builtin 0..64 observed accepted inverse count; 0 before inverse or for invalid inverse result",
            "exceptions": "ordinary Exception sanitized to EXECUTION_FAILED; BaseException propagates",
            "infrastructure": "unexpected inverse copy/hash fault envelopes fail actual V109 validation, yielding EXECUTION_FAILED",
        },
    }


def evaluate_reference_air_tabulated_hover_thrust_target(request):
    """Evaluate actual reference air once, then the bounded actual inverse once."""
    try:
        _JSON(request, _LIMITS["input_json"])
        snapshot = deepcopy(request)
        _JSON(snapshot, _LIMITS["input_json"])
        _REQUIRE(type(snapshot) is dict and snapshot.keys() == set(_REQUEST_KEYS))
        _REQUIRE(type(snapshot["evaluation"]) is str)
        if snapshot["evaluation"] != EVALUATION:
            return _response("SOLVER_UNSUPPORTED", [_REASONS["unsupported"]])
        _preflight(snapshot)
    except ValueError:
        return _response("MODEL_INAPPLICABLE", [_REASONS["invalid"]])
    except Exception:  # noqa: BLE001
        return _response("EXECUTION_FAILED", [_REASONS["snapshot"]])

    digest, count = None, 0
    try:
        digest = sha256_record(snapshot)
        air_snapshot = deepcopy(snapshot["air"])
        actual_air = reference_air_properties(**deepcopy(air_snapshot))
        raw_air = deepcopy(_reference._validate_air(actual_air, air_snapshot))
        density = raw_air["state"]["density_kg_m3"]
        injected = deepcopy(snapshot["target_template"])
        injected["rotor_template"]["density_kg_m3"] = density
        _JSON(injected, _LIMITS["inverse_input_json"])
        actual_inverse = evaluate_tabulated_hover_thrust_target(deepcopy(injected))
        _JSON(actual_inverse, _LIMITS["inverse_output_json"])
        retained = deepcopy(actual_inverse)
        _REQUIRE(validate_tabulated_hover_thrust_target_result(retained, injected) is None)
        count = retained["evaluation_count"]
        status = retained["status"]
        if status != "COMPUTED_EXPERIMENTAL":
            reason = _REASONS["refusal"] if status == "MODEL_INAPPLICABLE" else _REASONS[status]
            return _seal(_response(status, [reason], digest, count))
        air_digest, inverse_digest = sha256_record(raw_air), sha256_record(injected)
        response = _response(status, [], digest, count)
        response.update(
            diagnostics_complete=True, outputs={"air": raw_air, "target": retained},
            output_units={"air": deepcopy(_reference._AIR_UNITS),
                          "target": deepcopy(retained["output_units"])},
            stages=[
                {"stage": "air", "inputs": deepcopy(air_snapshot),
                 "inputs_sha256": sha256_record(air_snapshot), "result_sha256": air_digest},
                {"stage": "target", "inputs": injected, "inputs_sha256": inverse_digest,
                 "result_sha256": sha256_record(retained)},
            ],
            transfers=[{
                "from_stage": "air", "from_field": "state.density_kg_m3", "to_stage": "target",
                "to_field": "rotor_template.density_kg_m3", "value": density, "unit": "kg/m^3",
                "producer_result_sha256": air_digest, "consumer_request_sha256": inverse_digest,
            }],
        )
        return _seal(response)
    except Exception:  # noqa: BLE001 -- sanitized atomic response; BaseException propagates.
        return _seal(_response("EXECUTION_FAILED", [_REASONS["EXECUTION_FAILED"]], digest, count))
