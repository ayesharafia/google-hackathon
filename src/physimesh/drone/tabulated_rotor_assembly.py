"""Literal isolated tabulated-rotor static loads in a right-handed FLU frame."""

import math
import re
from copy import deepcopy

from . import reference_air_tabulated_hover as _reference
from . import tabulated_hover_bemt_request as _forward
from .hover_bemt import _mul, _normal
from .provenance import sha256_record
from .reference_air_properties import reference_air_properties
from .tabulated_hover_bemt_request import evaluate_tabulated_hover_bemt

EVALUATION = "literal_tabulated_rotor_static_assembly_experimental"
SCHEMA_VERSION = "tabulated_rotor_static_assembly_v1"
_require = _forward._require
_json = _forward._json_walk
_ROOT = ("evaluation", "air", "rotors", "mass_kg", "cg_body_m",
         "gravity_direction_body", "property_source")
_ROTOR = ("id", "rotor_template", "center_body_m", "axis_body", "rotation_sign")
_META = _forward.tabulated_hover_bemt_catalog()
_LIMITS = {
    "input_json": {**_META["limits"]["input_json"], "max_depth": 12,
                   "max_nodes_including_keys": 65536},
    "output_json": {**_META["limits"]["output_json"], "max_depth": 20,
                    "max_nodes_including_keys": 262144},
    "child_input_json": deepcopy(_META["limits"]["input_json"]),
    "child_output_json": deepcopy(_META["limits"]["output_json"]),
    "core_work": {**_META["limits"]["core_work"], "rotors_min": 1,
                  "rotors_max": 8, "total_annuli_max": 4096},
}
_LIMITATIONS = (
    "Static linear superposition of isolated attached-linear small-angle hover rotors.",
    "No interference, installed losses, trim, control authority, stability, safety or feasibility.",
    "No Reynolds/Mach polars, stall, loss factors, swirl, ground effect or coefficient feedback.",
    "No motors, structural model, dynamics, gyroscopic loads, inertia evolution or mission.",
    "Reference air supplies density and gravity only, not measured weather.",
    "Sources, geometry classifications, frame and spin are unverified caller declarations; no fetch.",
    "Unit norm tolerance is a numerical declaration gate, not calibration or physical validation.",
    "No physical, numerical, runtime, publication, 80 percent accuracy or novelty upgrade.",
    "Hashes bind JSON data only; counts do not attest execution or runtime identity.",
    "No complete PDF or external standard claim; this is a local experimental contract.",
)
_VECTOR_UNITS = {"gravity_force_body_n": "N", "net_force_body_n": "N",
                 "net_moment_cg_body_nm": "N*m"}
_ROW_UNITS = {
    "id": "label", "force_body_n": "N", "reaction_torque_body_nm": "N*m",
    "moment_cg_body_nm": "N*m", "actual_forward_request": _META["input_units"],
    "actual_forward_result": {"outputs": _META["output_field_units"]},
}


def _number(value):
    _require(type(value) in (int, float))
    converted = _normal(float(value), zero=True)
    _require(converted == value)
    return converted


def _vector(value, *, unit=False):
    _require(type(value) is list and len(value) == 3)
    result = [_number(v) for v in value]
    if unit:
        _require(abs(math.hypot(*result) - 1.0) <= 1e-12)
    return result


def _preflight(snapshot):
    _require(type(snapshot) is dict and snapshot.keys() == set(_ROOT))
    _require(type(snapshot["evaluation"]) is str)
    _require(type(snapshot["rotors"]) is list and 1 <= len(snapshot["rotors"]) <= 8)
    _require(_number(snapshot["mass_kg"]) > 0.0)
    _vector(snapshot["cg_body_m"])
    _vector(snapshot["gravity_direction_body"], unit=True)
    _require(type(snapshot["property_source"]) is str and bool(snapshot["property_source"].strip()))
    seen, total = set(), 0
    for rotor in snapshot["rotors"]:
        _require(type(rotor) is dict and rotor.keys() == set(_ROTOR))
        name = rotor["id"]
        _require(type(name) is str and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", name) is not None)
        _require(name not in seen)
        seen.add(name)
        _reference._preflight({"air": snapshot["air"], "rotor_template": rotor["rotor_template"]})
        _vector(rotor["center_body_m"])
        _vector(rotor["axis_body"], unit=True)
        _require(type(rotor["rotation_sign"]) is int and rotor["rotation_sign"] in (-1, 1))
        total += rotor["rotor_template"]["annuli"]
    _require(total <= 4096)


def _sum(values):
    # Signed cancellation to exact zero is legitimate; subnormal results are not.
    return _normal(math.fsum(values), zero=True)


def _difference(left, right):
    return _normal(left - right, zero=True)


def _loads(rotor, cg, outputs):
    axis = _vector(rotor["axis_body"], unit=True)
    force = [_mul(outputs["thrust_n"], a) for a in axis]
    reaction = [_mul(_mul(-float(rotor["rotation_sign"]), outputs["shaft_torque_nm"]), a)
                for a in axis]
    arm = [_difference(c, g) for c, g in zip(_vector(rotor["center_body_m"]), cg, strict=True)]
    cross = [_difference(_mul(arm[j], force[k]), _mul(arm[k], force[j]))
             for j, k in ((1, 2), (2, 0), (0, 1))]
    return {"id": rotor["id"], "force_body_n": force, "reaction_torque_body_nm": reaction,
            "moment_cg_body_nm": [_sum([a, b]) for a, b in zip(cross, reaction, strict=True)]}


def _response(status, reasons, digest=None, count=0):
    return {
        "evaluation": EVALUATION, "schema_version": SCHEMA_VERSION, "status": status,
        "evidence_level": "unverified", "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None, "feasibility": None, "diagnostics_complete": False,
        "rotor_evaluation_count": count, "reasons": list(reasons), "limitations": list(_LIMITATIONS),
        "limits": deepcopy(_LIMITS), "request_sha256": digest, "evaluation_sha256": None,
        "outputs": {}, "output_units": {}, "stages": [], "transfers": [],
    }


def _seal(response):
    _json(response, _LIMITS["output_json"])
    if response["request_sha256"] is not None and response["status"] in (
        "COMPUTED_EXPERIMENTAL", "EXECUTION_FAILED",
    ):
        response["evaluation_sha256"] = sha256_record({
            k: v for k, v in response.items() if k != "evaluation_sha256"
        })
    return response


def evaluate_tabulated_rotor_assembly(request):
    """Call actual air once and each ordered actual forward adapter once.

    Full returned JSON is bounded and detached immediately, before validation
    and use. A count records only fully guarded envelopes, including refusal.
    """
    try:
        _json(request, _LIMITS["input_json"])
        snapshot = deepcopy(request)
        _json(snapshot, _LIMITS["input_json"])
        _require(type(snapshot) is dict and snapshot.keys() == set(_ROOT))
        _require(type(snapshot["evaluation"]) is str)
        if snapshot["evaluation"] != EVALUATION:
            return _response("SOLVER_UNSUPPORTED", ["Unsupported evaluation."])
        _preflight(snapshot)
    except (ValueError, OverflowError):
        return _response("MODEL_INAPPLICABLE", ["Invalid bounded assembly request."])
    except Exception:  # noqa: BLE001
        return _response("EXECUTION_FAILED", ["Request snapshot failed."])

    digest, count = None, 0
    try:
        digest = sha256_record(snapshot)
        actual_air = reference_air_properties(**deepcopy(snapshot["air"]))
        raw_air = deepcopy(_reference._validate_air(actual_air, snapshot["air"]))
        density, gravity = raw_air["state"]["density_kg_m3"], raw_air["gravity_m_s2"]
        air_digest = sha256_record(raw_air)
        stages = [{"stage": "air", "inputs": deepcopy(snapshot["air"]),
                   "inputs_sha256": sha256_record(snapshot["air"]), "result_sha256": air_digest}]
        rows, transfers = [], []
        cg = _vector(snapshot["cg_body_m"])
        for rotor in snapshot["rotors"]:
            injected = deepcopy(rotor["rotor_template"])
            injected["density_kg_m3"] = density
            _json(injected, _LIMITS["child_input_json"])
            actual = evaluate_tabulated_hover_bemt(deepcopy(injected))
            _json(actual, _LIMITS["child_output_json"])
            actual = deepcopy(actual)
            _json(actual, _LIMITS["child_output_json"])
            accepted = _reference._validate_child(actual, injected)
            count += 1
            if not accepted:
                return _response("MODEL_INAPPLICABLE", ["Actual rotor refused the physical or numerical domain."],
                                 digest, count)
            row = _loads(rotor, cg, actual["outputs"])
            row.update(actual_forward_request=injected, actual_forward_result=actual)
            rows.append(row)
            request_digest = sha256_record(injected)
            stage = "rotor:" + rotor["id"]
            stages.append({"stage": stage, "inputs": deepcopy(injected),
                           "inputs_sha256": request_digest, "result_sha256": sha256_record(actual)})
            transfers.append({"from_stage": "air", "from_field": "state.density_kg_m3",
                              "to_stage": stage, "to_field": "density_kg_m3", "value": density,
                              "unit": "kg/m^3", "producer_result_sha256": air_digest,
                              "consumer_request_sha256": request_digest})
        gravity_force = [_mul(_mul(_number(snapshot["mass_kg"]), gravity), d)
                         for d in _vector(snapshot["gravity_direction_body"], unit=True)]
        response = _response("COMPUTED_EXPERIMENTAL", [], digest, count)
        response.update(
            diagnostics_complete=True,
            outputs={"air": raw_air, "rotors": rows, "gravity_force_body_n": gravity_force,
                     "net_force_body_n": [_sum([r["force_body_n"][i] for r in rows] + [gravity_force[i]])
                                          for i in range(3)],
                     "net_moment_cg_body_nm": [_sum([r["moment_cg_body_nm"][i] for r in rows])
                                              for i in range(3)]},
            output_units={"air": deepcopy(_reference._AIR_UNITS), "rotors": deepcopy(_ROW_UNITS),
                          **_VECTOR_UNITS}, stages=stages, transfers=transfers,
        )
        return _seal(response)
    except Exception:  # noqa: BLE001 -- atomic, sanitized; BaseException propagates.
        return _seal(_response("EXECUTION_FAILED", ["Assembly execution or returned contract failed."],
                               digest, count))


def tabulated_rotor_assembly_catalog():
    """Fresh schema and data-binding contract; no evaluator or source fetch."""
    return {
        **_response("RESEARCH_ONLY", []), "required_fields": list(_ROOT),
        "air_fields": ["altitude_m", "altitude_kind"], "rotor_fields": list(_ROTOR),
        "rotor_template_fields": [k for k in _forward._REQUEST_KEYS if k != "density_kg_m3"],
        "input_units": {"evaluation": "label", "air": {"altitude_m": "m", "altitude_kind": "label"},
                        "rotors": {"id": "label", "rotor_template": {
                            k: deepcopy(v) for k, v in _META["input_units"].items() if k != "density_kg_m3"},
                            "center_body_m": "m", "axis_body": "1", "rotation_sign": "1"},
                        "mass_kg": "kg", "cg_body_m": "m", "gravity_direction_body": "1",
                        "property_source": "text"},
        "output_field_units": {"air": deepcopy(_reference._AIR_UNITS), "rotors": deepcopy(_ROW_UNITS),
                               **_VECTOR_UNITS},
        "request_contract": {
            "extra_fields": "forbidden at every object; density_kg_m3 MUST be omitted from all templates",
            "defaults": {}, "air": "explicit finite builtin int/float 0..30000; geometric or geopotential",
            "rotors": "ordered builtin list 1..8; unique builtin id [A-Za-z][A-Za-z0-9_]{0,31}",
            "template": deepcopy(_META["request_contract"]),
            "preflight": "all structural JSON, exact types, counts, declarations, classifications, numeric types, frame, spin and mass before air",
            "physical_domain": "actual accepted forward core only; no dummy calls or inverse solve",
            "vectors": "builtin list3; signed finite normal or zero; exact binary64 conversion; no bool/subclasses",
            "mass": "positive finite normal builtin int/float; exact binary64 conversion",
            "unit_vectors": "abs(hypot-1)<=1e-12; declaration gate only; no normalization",
            "property_source": "mandatory nonblank unverified builtin string; no fetch",
        },
        "frame": "right-handed forward/left/up; axis_body is positive thrust direction",
        "spin": "builtin int +/-1; +1 angular velocity right-hand about positive axis; hub reaction opposes spin",
        "formulas": {"force": "F_i=T_i*axis_i", "reaction": "Qreact_i=-rotation_sign_i*Qshaft_i*axis_i",
                     "moment": "M_i=(center_i-CG) cross F_i + Qreact_i",
                     "gravity": "F_g=mass*g_actual*gravity_direction; acts at CG; zero gravity moment",
                     "net": "per-component math.fsum of rotor forces plus gravity; fsum rotor moments",
                     "arithmetic": "signed finite normal or exact zero at every arm/product/difference/sum; reject overflow and nonzero underflow"},
        "bindings": {
            "air": "actual typed V106 hydrostatic/transport guard once; immediate raw/density/gravity snapshot",
            "rotors": "actual V105 once each; immediate bounded JSON snapshot; full V106 envelope guard; unchanged result once per row",
            "units": "full raw air and vectors; request units; forward result units apply ONLY to nested outputs",
            "stages": "air then rotor:<id> (including rotor:air): actual inputs, inputs_sha256, result_sha256 only; no result arrays",
            "transfers": "density scalar air to each actual request; producer actual air digest and consumer request digest",
            "snapshots": "detached mutable builtin JSON; no immutable claim",
        },
        "response_contract": {
            "success": "COMPUTED_EXPERIMENTAL after all guarded components and load arithmetic",
            "invalid": "MODEL_INAPPLICABLE for preflight or guarded actual core refusal",
            "unsupported": "SOLVER_UNSUPPORTED for different outer evaluation string",
            "failed": "EXECUTION_FAILED for ordinary exceptions or invalid actual components; BaseException propagates",
            "atomic": "all failures: outputs/output_units empty; stages/transfers empty; diagnostics_complete false; no exception text",
            "hashes": "request null before acceptance; accepted refusal request only; accepted failure/success evaluation hash omits itself; canonical SHA256 UTF8 JSON",
            "count": "trusted zero initially; increments ONLY after full child guard acceptance, including valid domain refusal; not attempted-call count or execution attestation",
        },
    }
