"""Fixed, stateless reference-atmosphere to isolated-hover composition.

Records contain ordinary copied JSON. Semantic model identifiers are bindings,
not verified runtime code hashes; data hashes imply no validation or freshness.
"""

import math
from copy import deepcopy
from dataclasses import asdict

from .hover_bemt_request import evaluate_hover_bemt
from .provenance import sha256_record
from .standard_atmosphere import StandardAtmosphereState, standard_atmosphere

SCHEMA_VERSION = "atmosphere_hover_workflow_v1"
EVALUATION = "standard_atmosphere_isolated_hover_experimental"
ATMOSPHERE_MODEL_ID = "coesa1976.lower-atmosphere.0-30km.v1"
HOVER_MODEL_ID = "isolated_hover_small_angle_bemt_v1"

_ROTOR_KEYS = frozenset((
    "evaluation", "radius_m", "angular_speed_rad_s", "blade_count", "chord_m",
    "lift_curve_slope_per_rad", "profile_drag_coefficient", "pitch_tip_rad",
    "root_cutout_fraction", "twist_law", "annuli", "pitch_root_rad",
    "property_source", "applicability_declaration",
))
_ATMOSPHERE_UNITS = {
    "input_altitude_m": "m", "altitude_kind": "not_applicable",
    "geopotential_altitude_m": "m", "pressure_pa": "Pa",
    "temperature_k": "K", "density_kg_m3": "kg/m^3",
    "model_id": "not_applicable", "evidence_status": "not_applicable",
}
_HOVER_UNITS = {
    "radial_fraction": "1", "inflow_ratio": "1", "pitch_rad": "rad",
    "approx_inflow_angle_rad": "rad", "approx_angle_of_attack_rad": "rad",
    "thrust_coefficient": "1", "blade_thrust_coefficient": "1",
    "induced_power_coefficient": "1", "profile_power_coefficient": "1",
    "shaft_power_coefficient": "1", "thrust_n": "N", "shaft_power_w": "W",
    "shaft_torque_nm": "N*m", "thrust_balance_coefficient": "1",
    "max_local_balance_coefficient": "1", "annuli": "1",
}
_VECTOR_KEYS = frozenset((
    "radial_fraction", "inflow_ratio", "pitch_rad",
    "approx_inflow_angle_rad", "approx_angle_of_attack_rad",
))
_HOVER_ENVELOPE = frozenset((
    "model_id", "status", "physical_validation", "evidence_level",
    "aircraft_status", "feasibility", "reasons", "limitations", "sources",
    "outputs", "output_units",
))
_LIMITATIONS = (
    "Reference standard atmosphere is not local weather or aircraft validation.",
    "Experimental isolated-hover small-angle, attached linear-lift model only.",
    "Small-angle applicability and a physical operating envelope are not established.",
    "No rotor loss factors, swirl, ground effects, or rotor/aircraft interference.",
    "No stall, Reynolds-dependent polars, compressibility, or non-hover flight.",
    "No aircraft qualification, aircraft feasibility, or aircraft force closure.",
    "Shaft power is not electrical input power.",
    "Property sources and applicability declarations are unverified literal text.",
    "Physical validation and numerical qualification are NOT_ESTABLISHED.",
    "This fixed two-node workflow is not a general DAG or M3-complete workflow.",
    "Records are plain copied JSON, without a true immutability guarantee.",
    "Model IDs identify semantic versions, not verified runtime code hashes.",
    "Hashes identify data, not physical validation, freshness, or runtime code.",
)


def _finite_json(value, *, max_nodes=512, max_depth=8, max_items=512):
    """Bound each incoming request/component payload; root depth is one.

    Dictionary keys count as nodes. Aggregated records repeat these bounded
    payloads and are copied, rather than serialized from arbitrary objects.
    """
    remaining = max_nodes

    def visit(item, depth):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > max_depth:
            return False
        kind = type(item)
        if kind is str:
            if len(item) > 2000:
                return False
            try:
                item.encode("utf-8")
            except UnicodeEncodeError:
                return False
            return True
        if kind in (int, float):
            try:
                return math.isfinite(item)
            except (OverflowError, ValueError):
                return False
        if item is None or kind is bool:
            return True
        if kind is list:
            return len(item) <= max_items and all(visit(v, depth + 1) for v in item)
        if kind is dict:
            return len(item) <= max_items and all(
                type(k) is str and visit(k, depth + 1) and visit(v, depth + 1)
                for k, v in item.items()
            )
        return False

    return visit(value, 1)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _response(status, reason):
    return {
        "schema_version": SCHEMA_VERSION,
        "evaluation": EVALUATION,
        "status": status,
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "evidence_level": "unverified",
        "aircraft_status": None,
        "feasibility": None,
        "reasons": [reason] if reason else [],
        "limitations": list(_LIMITATIONS),
        "bindings": {
            "atmosphere": ATMOSPHERE_MODEL_ID,
            "hover": HOVER_MODEL_ID,
        },
        "limits": {
            "input_max_nodes": 512,
            "input_max_depth": 8,
            "max_string_length": 2000,
            "hover_max_annuli": 2048,
            "hover_result_max_nodes": 20000,
            "hover_result_max_items": 2048,
        },
        "transfers": [],
        "stages": [],
        "failed_stage": None,
        "outputs": {},
        "output_units": {},
    }


def _completed(stage_id, model_id, inputs, result):
    inputs_copy = deepcopy(inputs)
    result_copy = deepcopy(result)
    return {
        "stage_id": stage_id,
        "model_id": model_id,
        "inputs": inputs_copy,
        "inputs_sha256": sha256_record(inputs_copy),
        "result": result_copy,
        "result_sha256": sha256_record(result_copy),
    }


def _fail(response, stage, reason, component=None, status="NUMERICAL_FAILED"):
    response["status"] = status
    response["reasons"] = [reason]
    response["failed_stage"] = stage
    response["stage_failure"] = {"stage_id": stage}
    if component is not None:
        response["stage_failure"]["result"] = deepcopy(component)
    response["outputs"] = {}
    response["output_units"] = {}
    return response


def _valid_hover(result, annuli):
    if (not _finite_json(result, max_nodes=20000, max_items=2048)
            or type(result) is not dict):
        return False
    if result.keys() != _HOVER_ENVELOPE:
        return False
    if (type(result["status"]) is not str
            or type(result["model_id"]) is not str
            or type(result["physical_validation"]) is not str
            or type(result["evidence_level"]) is not str
            or result["model_id"] != HOVER_MODEL_ID
            or result["physical_validation"] != "NOT_ESTABLISHED"
            or result["evidence_level"] != "unverified"
            or result["aircraft_status"] is not None
            or result["feasibility"] is not None):
        return False
    for key in ("reasons", "limitations", "sources"):
        if type(result[key]) is not list or any(type(v) is not str for v in result[key]):
            return False
    if type(result["outputs"]) is not dict or type(result["output_units"]) is not dict:
        return False
    if result["status"] in ("MODEL_INAPPLICABLE", "SOLVER_UNSUPPORTED"):
        return (_finite_json(result) and bool(result["reasons"])
                and result["outputs"] == {} and result["output_units"] == {})
    if result["status"] != "COMPUTED_EXPERIMENTAL" or result["reasons"]:
        return False
    outputs = result["outputs"]
    if outputs.keys() != _HOVER_UNITS.keys() or result["output_units"] != _HOVER_UNITS:
        return False
    if (type(annuli) is not int or not 1 <= annuli <= 2048
            or type(outputs["annuli"]) is not int or outputs["annuli"] != annuli):
        return False
    for key, value in outputs.items():
        if key in _VECTOR_KEYS:
            if type(value) is not list or len(value) != annuli or not all(map(_number, value)):
                return False
        elif not _number(value):
            return False
    return True


def evaluate_atmosphere_hover(request):
    """Evaluate atmosphere, transfer only density, then evaluate isolated hover.

    Every physical/count input is explicit. The accepted component solvers own
    their physical-domain decisions. No runtime jobs or external state are used.
    """
    invalid = _response("MODEL_INAPPLICABLE", "Request must satisfy the explicit bounded JSON schema.")
    if not _finite_json(request) or type(request) is not dict:
        return invalid
    if request.keys() != {"evaluation", "atmosphere", "rotor"}:
        return invalid
    if type(request["evaluation"]) is not str or request["evaluation"] != EVALUATION:
        return invalid
    atmosphere = request["atmosphere"]
    rotor = request["rotor"]
    if (type(atmosphere) is not dict
            or atmosphere.keys() != {"altitude_m", "altitude_kind"}
            or type(rotor) is not dict or rotor.keys() != _ROTOR_KEYS):
        return invalid
    altitude = atmosphere["altitude_m"]
    if (type(altitude) not in (int, float) or not 0 <= altitude <= 30000
            or type(atmosphere["altitude_kind"]) is not str
            or atmosphere["altitude_kind"] not in ("geometric", "geopotential")
            or type(rotor["evaluation"]) is not str
            or rotor["evaluation"] != "isolated_hover_bemt_experimental"
            or any(v is None for k, v in rotor.items() if k != "pitch_root_rad")):
        return invalid
    # Only finite builtin JSON with the exact request structure reaches hashing.
    snapshot = deepcopy(request)
    response = _response("COMPUTED_EXPERIMENTAL", None)
    try:
        response["inputs_sha256"] = sha256_record(snapshot)
    except (ValueError, TypeError, OverflowError, UnicodeError):
        return invalid
    atmosphere = snapshot["atmosphere"]
    try:
        state = standard_atmosphere(
            atmosphere["altitude_m"], altitude_kind=atmosphere["altitude_kind"]
        )
        # Inspect builtin field values before asdict can copy arbitrary objects.
        if type(state) is not StandardAtmosphereState:
            return _fail(response, "atmosphere", "Invalid atmosphere component result.")
        fields = {key: getattr(state, key) for key in _ATMOSPHERE_UNITS}
        if not _finite_json(fields):
            return _fail(response, "atmosphere", "Invalid atmosphere component result.")
        state_copy = asdict(state)
        if (not _finite_json(state_copy)
                or state_copy.keys() != _ATMOSPHERE_UNITS.keys()
                or state_copy["model_id"] != ATMOSPHERE_MODEL_ID
                or state_copy["evidence_status"] != "REFERENCE_MODEL_NOT_AIRCRAFT_VALIDATION"
                or state_copy["altitude_kind"] != atmosphere["altitude_kind"]
                or state_copy["input_altitude_m"] != atmosphere["altitude_m"]
                or any(not _number(state_copy[k]) for k in (
                    "input_altitude_m", "geopotential_altitude_m", "pressure_pa",
                    "temperature_k", "density_kg_m3"))
                or state_copy["density_kg_m3"] <= 0
                or state_copy["pressure_pa"] <= 0
                or state_copy["temperature_k"] <= 0):
            return _fail(response, "atmosphere", "Invalid atmosphere component result.")
        record = _completed("atmosphere", ATMOSPHERE_MODEL_ID, atmosphere, state_copy)
        response["stages"].append(record)
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return _fail(response, "atmosphere", "Atmosphere computation failed.")
    except (AttributeError, KeyError, IndexError, RuntimeError):
        return _fail(response, "atmosphere", "Invalid atmosphere component result.")
    try:
        hover_request = deepcopy(snapshot["rotor"])
        hover_request["density_kg_m3"] = state_copy["density_kg_m3"]
        response["transfers"] = [{
            "source": "atmosphere.density_kg_m3",
            "target": "hover.density_kg_m3",
            "unit": "kg/m^3",
            "value": state_copy["density_kg_m3"],
            "operation": "scalar_value_copy",
            "direction": "one_way",
            "interpolation": False,
            "feedback": False,
            "reference": "Reference atmosphere density; not measured local weather.",
            "qualification": "Data identity is not a conservation proof.",
        }]
        result = evaluate_hover_bemt(deepcopy(hover_request))
        if not _valid_hover(result, hover_request["annuli"]):
            return _fail(response, "hover", "Invalid hover component result.")
        if result["status"] != "COMPUTED_EXPERIMENTAL":
            return _fail(response, "hover", "Hover component refused the request.",
                         component=result, status=result["status"])
        response["stages"].append(_completed("hover", HOVER_MODEL_ID, hover_request, result))
        response["outputs"] = {
            "atmosphere": deepcopy(state_copy),
            "hover": deepcopy(result["outputs"]),
        }
        response["output_units"] = {
            "atmosphere": dict(_ATMOSPHERE_UNITS),
            "hover": deepcopy(result["output_units"]),
        }
        return response
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return _fail(response, "hover", "Hover computation failed.")
    except (AttributeError, KeyError, IndexError, RuntimeError):
        return _fail(response, "hover", "Invalid hover component result.")
