"""Prescribed isolated tabulated thrust targets and static FLU assembly loads."""

import re
from copy import deepcopy

from . import reference_air_tabulated_hover as _reference
from . import reference_air_tabulated_hover_thrust_target as _air_target
from . import tabulated_hover_thrust_target as _inverse
from . import tabulated_rotor_assembly as _assembly
from .hover_bemt import _mul
from .provenance import sha256_record
from .reference_air_properties import reference_air_properties
from .tabulated_hover_thrust_target import evaluate_tabulated_hover_thrust_target
from .tabulated_hover_thrust_target_validation import validate_tabulated_hover_thrust_target_result

EVALUATION = "prescribed_tabulated_rotor_thrust_target_assembly_experimental"
SCHEMA_VERSION = "tabulated_thrust_target_static_assembly_v1"
_ROOT = ("evaluation", "air", "rotors", "mass_kg", "cg_body_m",
         "gravity_direction_body", "property_source")
_ROTOR = ("id", "target_template", "center_body_m", "axis_body", "rotation_sign")
_require = _assembly._require
_json = _assembly._json
_META = _inverse.tabulated_hover_thrust_target_catalog()
_LIMITS = {
    "input_json": {**_META["limits"]["input_json"], "max_depth": 14,
                   "max_nodes_including_keys": 65536},
    "inverse_input_json": deepcopy(_META["limits"]["input_json"]),
    "inverse_output_json": deepcopy(_META["limits"]["output_json"]),
    "forward_input_json": deepcopy(_META["limits"]["child_input_json"]),
    "forward_output_json": deepcopy(_META["limits"]["child_output_json"]),
    "output_json": {**_META["limits"]["output_json"], "max_depth": 24,
                    "max_nodes_including_keys": 524288},
    "core_work": {**_META["limits"]["core_work"], "air_calls_max": 1,
                  "rotors_min": 1, "rotors_max": 8, "inverse_calls_max": 8,
                  "forward_calls_max": 512, "total_annuli_max": 4096,
                  "total_forward_annuli_max": 32768},
}


def _preflight(snapshot):
    """Admit all rotor declarations before air, without fabricated inputs."""
    _require(type(snapshot["rotors"]) is list and 1 <= len(snapshot["rotors"]) <= 8)
    _require(_assembly._number(snapshot["mass_kg"]) > 0.0)
    _assembly._vector(snapshot["cg_body_m"])
    _assembly._vector(snapshot["gravity_direction_body"], unit=True)
    _require(type(snapshot["property_source"]) is str and bool(snapshot["property_source"].strip()))
    seen, work = set(), 0
    for rotor in snapshot["rotors"]:
        _require(type(rotor) is dict and rotor.keys() == set(_ROTOR))
        name = rotor["id"]
        _require(type(name) is str and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", name) is not None)
        _require(name not in seen)
        seen.add(name)
        _air_target._preflight({"air": snapshot["air"], "target_template": rotor["target_template"]})
        _assembly._vector(rotor["center_body_m"])
        _assembly._vector(rotor["axis_body"], unit=True)
        _require(type(rotor["rotation_sign"]) is int and rotor["rotation_sign"] in (-1, 1))
        target = rotor["target_template"]
        work += target["max_evaluations"] * target["rotor_template"]["annuli"]
    _require(work <= 32768)


_LIMITATIONS = (
    "Static superposition of prescribed isolated attached-linear small-angle hover targets.",
    "All target tolerances met does not imply zero net trim residual.",
    "No Reynolds/Mach polars, stall, losses, swirl, interference or installed physics.",
    "No attainable RPM, motors, trim, control, stability, safety, feasibility, dynamics or mission.",
    "Reference air supplies density and gravity only, not measured weather.",
    "Source, geometry classification, uncertainty, properties, frame and spin are unverified declarations.",
    "No physical accuracy, numerical, runtime, publication, 80 percent or novelty qualification.",
    "Hashes bind mutable JSON snapshots, not code identity or execution attestation.",
    "Intermediate trace full-result digests are FORMAT-ONLY producer-reported provenance; payloads absent.",
    "Selected retained full forward content and trace arithmetic are checked without a second model call.",
    "Failure counts are necessary guarded-envelope bounds, not execution attestation.",
    "Inverse units cover only actual_target_result.outputs; forward units only its selected forward.outputs.",
    "Separate local experimental contract; no identity, API, graph, trim, mission or accepted-source changes.",
)
_REASONS = {
    "unsupported": "Unsupported evaluation.",
    "invalid": "Invalid bounded target assembly request.",
    "snapshot": "Request snapshot failed.",
    "refusal": "Actual target refused the physical or numerical domain.",
    "TARGET_NOT_BRACKETED": "Actual target is outside the observed endpoint thrust range.",
    "ITERATION_LIMIT": "Actual target forward evaluation budget exhausted.",
    "NUMERICAL_LIMIT": "Actual target reached a representable numerical limit.",
    "EXECUTION_FAILED": "Target assembly execution or returned contract failed.",
}
_VECTOR_UNITS = {"gravity_force_body_n": "N", "net_force_body_n": "N",
                 "net_moment_cg_body_nm": "N*m"}
_ROW_UNITS = {
    "id": "label", "force_body_n": "N", "reaction_torque_body_nm": "N*m",
    "moment_cg_body_nm": "N*m", "actual_target_request": deepcopy(_META["input_units"]),
    "actual_target_result": {"outputs": {
        **deepcopy(_META["output_field_units"]),
        "actual_forward_result": {"outputs": deepcopy(_META["output_field_units"]["actual_forward_result"])},
    }},
}


def _response(status, reasons, digest=None, inverses=0, forwards=0):
    return {
        "evaluation": EVALUATION, "schema_version": SCHEMA_VERSION, "status": status,
        "evidence_level": "unverified", "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None, "feasibility": None, "diagnostics_complete": False,
        "inverse_result_count": inverses, "forward_evaluation_count": forwards,
        "reasons": list(reasons), "limitations": list(_LIMITATIONS), "limits": deepcopy(_LIMITS),
        "request_sha256": digest, "evaluation_sha256": None,
        "outputs": {}, "output_units": {}, "stages": [], "transfers": [],
    }


def _seal(response):
    _require(type(response["inverse_result_count"]) is int and 0 <= response["inverse_result_count"] <= 8)
    _require(type(response["forward_evaluation_count"]) is int
             and 0 <= response["forward_evaluation_count"] <= 512)
    _json(response, _LIMITS["output_json"])
    if response["request_sha256"] is not None and response["status"] != "MODEL_INAPPLICABLE":
        response["evaluation_sha256"] = sha256_record({
            key: value for key, value in response.items() if key != "evaluation_sha256"
        })
    return response


def tabulated_thrust_target_assembly_catalog():
    """Fresh closed schemas, independent budgets and actual-result bindings."""
    target_units = deepcopy(_META["input_units"])
    del target_units["rotor_template"]["density_kg_m3"]
    return {
        **_response("RESEARCH_ONLY", []), "required_fields": list(_ROOT),
        "air_fields": ["altitude_m", "altitude_kind"], "rotor_fields": list(_ROTOR),
        "target_template_fields": list(_inverse._REQUEST_KEYS),
        "rotor_template_fields": [k for k in _inverse._child._REQUEST_KEYS if k in _air_target._ROTOR_KEYS],
        "station_fields": ["radius_m", "chord_m", "blade_angle_rad"],
        "input_units": {
            "evaluation": "label", "air": {"altitude_m": "m", "altitude_kind": "label"},
            "rotors": {"id": "label", "target_template": target_units, "center_body_m": "m",
                       "axis_body": "1", "rotation_sign": "1"},
            "mass_kg": "kg", "cg_body_m": "m", "gravity_direction_body": "1", "property_source": "text",
        },
        "output_field_units": {"air": deepcopy(_reference._AIR_UNITS), "rotors": deepcopy(_ROW_UNITS),
                               **_VECTOR_UNITS},
        "trace_field_units": deepcopy(_META["trace_field_units"]),
        "count_units": {"inverse_result_count": "1", "forward_evaluation_count": "1"},
        "request_contract": {
            "extra_fields": "forbidden in every request object; no defaults", "defaults": {},
            "air": "builtin finite int/float altitude 0..30000 m; geometric or geopotential",
            "rotors": "ordered builtin list 1..8; unique builtin id [A-Za-z][A-Za-z0-9_]{0,31}; air allowed",
            "target_template": "exact V108 root request; rotor_template omits density_kg_m3 and angular_speed_rad_s",
            "target_evaluation": _inverse.EVALUATION, "rotor_evaluation": _inverse._child.EVALUATION,
            "controls": "all targets, tolerances, brackets and budgets explicit; unchanged V108 controls; no expansion",
            "positive_controls": "finite normal builtin int/float, no bool; tolerance < target; bracket 0 < lo < hi",
            "preflight": "strict builtin JSON before copy; actual V110 preflight for EVERY rotor before ANY model call",
            "declarations": "all structure, numeric types, counts, sources, classifications, frame and spin before air",
            "physical_domain": "geometry and physical numerical domain remain owned by actual accepted core",
            "vectors": "builtin list3; signed finite normal or zero; exact binary64 conversion; no bool/subclasses",
            "mass": "positive finite normal builtin int/float with exact binary64 conversion",
            "unit_vectors": "abs(hypot-1)<=1e-12; declaration gate only; no normalization or epsilon clamp",
            "sources": "mandatory nonblank unverified declarations; no fetch",
            "work": "SUM over ALL rotors(max_evaluations * annuli) <= 32768 before calls; no selected subset",
            "counts": "annuli 1..512; stations 2..256; blades 1..32; max_evaluations 2..64; rotors 1..8",
            "child_budgets": "independent inverse input/output; accepted inverse owns independent forward walks",
        },
        "frame": "right-handed forward/left/up; axis_body is positive THRUST direction",
        "spin": "builtin int +/-1; +1 right-hand angular velocity about axis; reaction opposes spin",
        "formulas": {
            "force": "F_i=T_actual_selected_i*axis_i",
            "reaction": "Qreact_i=-rotation_sign_i*Q_actual_selected_i*axis_i",
            "moment": "M_i=(center_i-CG) cross F_i + Qreact_i",
            "gravity": "mass*g_actual*gravity_direction at CG; zero added gravity moment",
            "net": "componentwise math.fsum of rotor forces plus gravity; fsum of rotor moments",
            "arithmetic": "signed finite normal or exact zero; reject overflow/nonzero underflow; exact cancellation allowed",
        },
        "bindings": {
            "air": "actual reference_air_properties ONCE; V106 typed hydrostatic/transport guard; immediate raw/density/gravity snapshot",
            "targets": "actual inverse ONCE per ordered rotor; bound and snapshot full actual inverse immediately; V109 pure guard returns None",
            "loads": "V112 _loads on actual selected forward outputs only; no V112 evaluator or model reruns",
            "preservation": "unchanged full actual inverse once per row; selected full forward only inside inverse",
            "snapshots": "caller, injected snapshot, arguments and retained results isolated; mutable builtin JSON",
            "stages": "air then rotor:<id>, including rotor:air; actual inputs, inputs_sha256, result_sha256 only; no result arrays",
            "transfers": "density scalar kg/m^3: air.state.density_kg_m3 to rotor target.rotor_template.density_kg_m3",
            "transfer_hashes": "producer full actual raw-air digest; consumer actual injected inverse request digest",
            "units": "air covers full raw air; vectors N/N*m; actual_target_request full input units; inverse units ONLY actual_target_result.outputs; forward units ONLY its actual_forward_result.outputs",
            "provenance": "intermediate trace full-result digests FORMAT-ONLY producer-reported provenance; absent payloads; selected full forward content verified",
            "trace": "accepted V109 validates scalar trace arithmetic and bound without a second model evaluation",
            "failure_guard": "necessary envelope/count bounds only; no execution attestation; narrow V109 infrastructure copy/hash fault admission unchanged",
        },
        "status_reason_matrix": {
            "COMPUTED_EXPERIMENTAL": [], "SOLVER_UNSUPPORTED": [_REASONS["unsupported"]],
            "MODEL_INAPPLICABLE": [_REASONS["invalid"], _REASONS["refusal"]],
            "EXECUTION_FAILED": [_REASONS["snapshot"], _REASONS["EXECUTION_FAILED"]],
            **{s: [_REASONS[s]] for s in ("TARGET_NOT_BRACKETED", "ITERATION_LIMIT", "NUMERICAL_LIMIT")},
        },
        "response_contract": {
            "success": "actual raw air once, ordered full inverses once and selected loads; diagnostics_complete true",
            "stop": "first guarded noncomputed inverse stops; same accepted status propagated atomically",
            "atomic": "all failures: outputs/output_units {}; stages/transfers []; diagnostics_complete false; no partial payload or exception text",
            "inverse_result_count": "builtin 0..8; increments ONLY after full inverse guard, including valid failure",
            "forward_evaluation_count": "builtin 0..512; sum actual guarded child evaluation_count ONLY after full guard; invalid payload adds zero",
            "counts": "guarded envelopes only, not attempted calls or execution attestation; prior guarded counts survive later failure",
            "request_sha256": "accepted actual copied outer request; preflight/unsupported/snapshot failure null",
            "evaluation_sha256": "full response omitting itself for accepted success/bounded failure/EXECUTION_FAILED; MODEL_INAPPLICABLE null",
            "encoding": "accepted canonical SHA256 sorted compact UTF8 JSON; ensure_ascii=False, allow_nan=False",
            "exceptions": "ordinary Exception sanitized to EXECUTION_FAILED; BaseException propagates",
            "qualification": "target tolerance satisfaction does not establish net trim zero or any physical qualification",
        },
    }


def evaluate_tabulated_thrust_target_assembly(request):
    """Run actual air once, each actual inverse once, and assemble selected loads."""
    try:
        _json(request, _LIMITS["input_json"])
        snapshot = deepcopy(request)
        _json(snapshot, _LIMITS["input_json"])
        _require(type(snapshot) is dict and snapshot.keys() == set(_ROOT))
        _require(type(snapshot["evaluation"]) is str)
        if snapshot["evaluation"] != EVALUATION:
            return _response("SOLVER_UNSUPPORTED", [_REASONS["unsupported"]])
        _preflight(snapshot)
    except (ValueError, OverflowError):
        return _response("MODEL_INAPPLICABLE", [_REASONS["invalid"]])
    except Exception:  # noqa: BLE001
        return _response("EXECUTION_FAILED", [_REASONS["snapshot"]])

    digest, inverses, forwards = None, 0, 0
    try:
        digest = sha256_record(snapshot)
        air_request = deepcopy(snapshot["air"])
        actual_air = reference_air_properties(**deepcopy(air_request))
        raw_air = deepcopy(_reference._validate_air(actual_air, air_request))
        density, gravity = raw_air["state"]["density_kg_m3"], raw_air["gravity_m_s2"]
        air_digest = sha256_record(raw_air)
        stages = [{"stage": "air", "inputs": deepcopy(air_request),
                   "inputs_sha256": sha256_record(air_request), "result_sha256": air_digest}]
        rows, transfers = [], []
        cg = _assembly._vector(snapshot["cg_body_m"])
        for rotor in snapshot["rotors"]:
            injected = deepcopy(rotor["target_template"])
            injected["rotor_template"]["density_kg_m3"] = density
            _json(injected, _LIMITS["inverse_input_json"])
            actual = evaluate_tabulated_hover_thrust_target(deepcopy(injected))
            _json(actual, _LIMITS["inverse_output_json"])
            retained = deepcopy(actual)
            _require(validate_tabulated_hover_thrust_target_result(retained, injected) is None)
            inverses += 1
            forwards += retained["evaluation_count"]
            status = retained["status"]
            if status != "COMPUTED_EXPERIMENTAL":
                reason = _REASONS["refusal"] if status == "MODEL_INAPPLICABLE" else _REASONS[status]
                return _seal(_response(status, [reason], digest, inverses, forwards))
            selected = retained["outputs"]["actual_forward_result"]["outputs"]
            row = _assembly._loads(rotor, cg, selected)
            row.update(actual_target_request=injected, actual_target_result=retained)
            rows.append(row)
            stage, request_digest = "rotor:" + rotor["id"], sha256_record(injected)
            stages.append({"stage": stage, "inputs": deepcopy(injected),
                           "inputs_sha256": request_digest, "result_sha256": sha256_record(retained)})
            transfers.append({"from_stage": "air", "from_field": "state.density_kg_m3",
                              "to_stage": stage, "to_field": "rotor_template.density_kg_m3",
                              "value": density, "unit": "kg/m^3",
                              "producer_result_sha256": air_digest,
                              "consumer_request_sha256": request_digest})
        gravity_force = [_mul(_mul(_assembly._number(snapshot["mass_kg"]), gravity), direction)
                         for direction in _assembly._vector(snapshot["gravity_direction_body"], unit=True)]
        response = _response("COMPUTED_EXPERIMENTAL", [], digest, inverses, forwards)
        response.update(
            diagnostics_complete=True,
            outputs={"air": raw_air, "rotors": rows, "gravity_force_body_n": gravity_force,
                     "net_force_body_n": [_assembly._sum([r["force_body_n"][i] for r in rows]
                                                         + [gravity_force[i]]) for i in range(3)],
                     "net_moment_cg_body_nm": [_assembly._sum([r["moment_cg_body_nm"][i] for r in rows])
                                              for i in range(3)]},
            output_units={"air": deepcopy(_reference._AIR_UNITS), "rotors": deepcopy(_ROW_UNITS),
                          **_VECTOR_UNITS}, stages=stages, transfers=transfers,
        )
        return _seal(response)
    except Exception:  # noqa: BLE001 -- atomic sanitized boundary; BaseException propagates.
        return _seal(_response("EXECUTION_FAILED", [_REASONS["EXECUTION_FAILED"]],
                               digest, inverses, forwards))
