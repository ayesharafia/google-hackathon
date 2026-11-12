"""Experimental prescribed tabulated target to constant-parameter DC power bridge."""

import math
import sys
from copy import deepcopy

from . import dc_motor as dc
from . import tabulated_thrust_target_assembly as assembly
from . import thermal as th
from .provenance import sha256_record
from .reference_air_tabulated_hover import _exact
from .tabulated_hover_bemt_request import _json_walk, _require
from .tabulated_thrust_target_assembly_validation import (
    validate_tabulated_thrust_target_assembly_result,
)

EVALUATION = "prescribed_tabulated_target_dc_power_experimental"
SCHEMA_VERSION = "tabulated_target_dc_power_v1"
_ASSEMBLY_CATALOG = assembly.tabulated_thrust_target_assembly_catalog()
_ROOT = ("evaluation", "assembly", "motors", "auxiliary")
_PARAMETERS = {
    "motor_constant_si": "N*m/A", "terminal_resistance_ohm": "ohm",
    "zero_torque_current_a": "A", "parameter_source": "text",
    "applicability_declaration": "label",
}
_DECLARED = {
    "maximum_current_a": "A", "maximum_terminal_voltage_v": "V",
    "maximum_angular_speed_rad_s": "rad/s", "maximum_shaft_torque_nm": "N*m",
    "limit_source": "text",
}
_MOTOR_FIELDS = (
    "id", "parameters", "declared_limits", "heat_fraction_of_motor_loss", "heat_source",
)
_JSON = {
    "root_depth": 1, "max_string_characters": 2000, "max_integer_bits": 1023,
    "finite_floats_only": True, "valid_utf8_only": True,
}
_LIMITS = {
    "input_json": {**_JSON, "max_depth": 16, "max_nodes_including_keys": 131072,
                   "max_container_items": 256},
    "assembly_input_json": {**_JSON, "max_depth": 14, "max_nodes_including_keys": 65536,
                            "max_container_items": 256},
    "assembly_output_json": {**_JSON, "max_depth": 24, "max_nodes_including_keys": 524288,
                             "max_container_items": 2048},
    "motor_input_json": {**_JSON, "max_depth": 10, "max_nodes_including_keys": 4096,
                         "max_container_items": 256},
    "motor_output_json": {**_JSON, "max_depth": 12, "max_nodes_including_keys": 8192,
                          "max_container_items": 2048},
    "output_json": {**_JSON, "max_depth": 28, "max_nodes_including_keys": 1048576,
                    "max_container_items": 2048},
    "core_work": {"rotors_min": 1, "rotors_max": 8, "assembly_calls_max": 1,
                  "air_calls_max": 1, "inverse_calls_max": 8, "forward_calls_max": 512,
                  "total_forward_annuli_max": 32768, "motor_calls_max": 8},
}
# Code-owned exact constants from the accepted DC evaluator; no dummy execution.
_MOTOR_STATIC = {
    "evaluation": "constant_parameter_dc_motor_experimental",
    "status": "COMPUTED_EXPERIMENTAL", "evidence_level": "unverified",
    "physical_validation": "NOT_ESTABLISHED", "numerical_qualification": "NOT_ESTABLISHED",
    "runtime_identity": "NOT_ESTABLISHED", "aircraft_status": None, "feasibility": None,
    "diagnostics_complete": True, "reasons": [], "stages": [], "transfers": [],
    "sources": [{"url": "https://web.mit.edu/drela/Public/web/qprop/motor1_theory.pdf",
                 "scope": "Steady constant-parameter DC-equivalent equations"}],
    "limitations": [
        "Caller-declared constant R and zero-torque current; no speed or temperature correction.",
        "No BLDC phase conversion, ESC, battery, bus current, SOC or regeneration model.",
        "Declared limits are not continuous thermal ratings or aircraft feasibility.",
        "Sources identify equations, not measured or qualified parameters.",
    ],
}
_MOTOR_UNITS = {
    "current_a": "A", "back_emf_v": "V", "terminal_voltage_v": "V",
    "shaft_power_w": "W", "electrical_power_w": "W", "copper_loss_w": "W",
    "friction_equivalent_loss_w": "W", "total_loss_w": "W",
    "power_balance_residual_w": "W", "efficiency": "1",
    "declared_limit_status": "not_applicable",
    "limit_checks": {key: "not_applicable" for key in (
        "current", "terminal_voltage", "angular_speed", "shaft_torque")},
}
_MOTOR_REQUEST_UNITS = {
    "evaluation": "label", "parameters": _PARAMETERS, "declared_limits": _DECLARED,
    "operating_point": {"angular_speed_rad_s": "rad/s", "shaft_torque_nm": "N*m"},
}


def _scalar(value, *, positive=False, fraction=False):
    """Match accepted DC numeric admission, without a fabricated operating point."""
    _require(type(value) in (int, float))
    _require(value == 0 or sys.float_info.min <= abs(value) <= sys.float_info.max)
    number = dc._normal(value)
    _require(math.isfinite(number))
    _require(number > 0 if positive else number >= 0)
    if fraction:
        _require(number <= 1)
    return number


def _source(value):
    _require(type(value) is str and bool(value.strip()) and len(value) <= 2000)


def _motor_preflight(motor, rotor):
    _require(type(motor) is dict and motor.keys() == set(_MOTOR_FIELDS))
    _exact(motor["id"], rotor["id"])
    parameters, declared = motor["parameters"], motor["declared_limits"]
    _require(type(parameters) is dict and parameters.keys() == _PARAMETERS.keys())
    _require(type(declared) is dict and declared.keys() == _DECLARED.keys())
    _scalar(parameters["motor_constant_si"], positive=True)
    _scalar(parameters["terminal_resistance_ohm"])
    _scalar(parameters["zero_torque_current_a"])
    _source(parameters["parameter_source"])
    _exact(parameters["applicability_declaration"], "constant_parameter_dc_equivalent_only")
    for name in _DECLARED:
        if name != "limit_source":
            _scalar(declared[name], positive=True)
    _source(declared["limit_source"])
    _scalar(motor["heat_fraction_of_motor_loss"], fraction=True)
    _source(motor["heat_source"])


def _preflight(snapshot):
    """Admit the entire actual V114 request and every motor before model calls."""
    supplied = snapshot["assembly"]
    _json_walk(supplied, _LIMITS["assembly_input_json"])
    _require(type(supplied) is dict and supplied.keys() == set(assembly._ROOT))
    _exact(supplied["evaluation"], assembly.EVALUATION)
    assembly._preflight(supplied)
    motors = snapshot["motors"]
    _require(type(motors) is list and 1 <= len(motors) <= 8)
    _require(len(motors) == len(supplied["rotors"]))
    for motor, rotor in zip(motors, supplied["rotors"], strict=True):
        _motor_preflight(motor, rotor)
    auxiliary = snapshot["auxiliary"]
    _require(type(auxiliary) is dict and auxiliary.keys() == {"power_w", "heat_fraction", "source"})
    _scalar(auxiliary["power_w"])
    _scalar(auxiliary["heat_fraction"], fraction=True)
    _source(auxiliary["source"])


def _validate_motor(actual, request):
    """Check the full actual return contract, without invoking either model."""
    _require(type(actual) is dict and actual.keys() == (
        _MOTOR_STATIC.keys() | {"request_sha256", "outputs", "output_units"}))
    for name, expected in _MOTOR_STATIC.items():
        _exact(actual[name], expected)
    _exact(actual["request_sha256"], sha256_record(request))
    _exact(actual["output_units"], _MOTOR_UNITS)
    outputs = actual["outputs"]
    _require(type(outputs) is dict and outputs.keys() == _MOTOR_UNITS.keys())
    p, op, limits = request["parameters"], request["operating_point"], request["declared_limits"]
    k = _scalar(p["motor_constant_si"], positive=True)
    resistance = _scalar(p["terminal_resistance_ohm"])
    idle = _scalar(p["zero_torque_current_a"])
    omega = _scalar(op["angular_speed_rad_s"], positive=True)
    torque = _scalar(op["shaft_torque_nm"])
    # Same accepted operation order: return-contract arithmetic, not a model rerun.
    current = dc._power_sum([th.checked_quotient(torque, k), idle])
    emf = th.checked_product(k, omega)
    voltage = dc._power_sum([emf, th.checked_product(current, resistance)])
    shaft = th.checked_product(torque, omega)
    electrical = th.checked_product(voltage, current)
    copper = (0.0 if resistance == 0 else
              th.checked_product(th.checked_product(current, current), resistance))
    friction = th.checked_product(emf, idle)
    loss = dc._power_sum([copper, friction])
    accounted = dc._power_sum([shaft, loss])
    residual = th.checked_difference(electrical, accounted)
    norm = max(electrical, accounted)
    if norm > 0:
        _require(abs(th.checked_quotient(residual, norm)) <=
                 th.checked_product(64, sys.float_info.epsilon))
    else:
        _require(residual == 0)
    eta = th.checked_quotient(shaft, accounted) if accounted > 0 else None
    if eta is None:
        _require(shaft == 0 and loss == 0 and electrical == 0)
    else:
        _require(0 <= eta <= 1)
    for name, expected in (
        ("current_a", current), ("back_emf_v", emf), ("terminal_voltage_v", voltage),
        ("shaft_power_w", shaft), ("electrical_power_w", electrical),
        ("copper_loss_w", copper), ("friction_equivalent_loss_w", friction),
        ("total_loss_w", loss), ("power_balance_residual_w", residual), ("efficiency", eta),
    ):
        _exact(outputs[name], expected)
    checks = outputs["limit_checks"]
    _require(type(checks) is dict and checks.keys() == _MOTOR_UNITS["limit_checks"].keys())
    for name, value, maximum in (
        ("current", current, "maximum_current_a"),
        ("terminal_voltage", voltage, "maximum_terminal_voltage_v"),
        ("angular_speed", omega, "maximum_angular_speed_rad_s"),
        ("shaft_torque", torque, "maximum_shaft_torque_nm"),
    ):
        _exact(checks[name], value <= dc._normal(limits[maximum]))
    _exact(outputs["declared_limit_status"], "WITHIN_DECLARED_LIMITS" if all(checks.values())
           else "EXCEEDS_DECLARED_LIMITS")


_LIMITATIONS = (
    "Prescribed isolated tabulated targets and caller-declared constant DC-equivalent parameters only.",
    "Synthetic parameters are not measured or qualified motor data; sources are declarations, not fetched.",
    "Motor loss includes copper and friction-equivalent loss; only the declared fraction is allocated heat.",
    "Shaft power is not heat; auxiliary electrical demand and allocated auxiliary heat are separate.",
    "No ESC loss, battery bus, temperature integration, interference, trim, control or stability model.",
    "Declared limit exceedance remains computed; no attainable RPM, safety or aircraft feasibility claim.",
    "No physical, numerical, runtime, publication, 80 percent or novelty qualification.",
    "Hashes bind full actual JSON snapshots, not execution attestation or code identity.",
    "Counts cover guarded returned contracts only; V115 narrow infrastructure fault admission is unchanged.",
    "Shaft power cross-binding tolerance rel=1e-12 abs=1e-12 W accounts for multiply order only.",
    "Separate experimental local contract; no API, graph, mission or accepted-source changes.",
)
_REASONS = {
    "unsupported": "Unsupported evaluation.", "invalid": "Invalid bounded target DC power request.",
    "snapshot": "Request snapshot failed.", "execution": "Target DC power execution or returned contract failed.",
    "assembly": "Actual target assembly returned a noncomputed result.",
}
_TOTAL_FIELDS = (
    "total_shaft_power_w", "total_motor_electrical_power_w", "total_motor_loss_w",
    "total_allocated_motor_heat_w", "total_unallocated_motor_loss_w",
    "auxiliary_electrical_power_w", "auxiliary_heat_w", "total_electrical_power_w", "total_heat_w",
)


def _response(status, reasons, digest=None, inverses=0, forwards=0, motors=0):
    return {
        "evaluation": EVALUATION, "schema_version": SCHEMA_VERSION, "status": status,
        "evidence_level": "unverified", "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None, "feasibility": None, "diagnostics_complete": False,
        "assembly_inverse_result_count": inverses, "forward_evaluation_count": forwards,
        "motor_result_count": motors, "request_sha256": digest, "evaluation_sha256": None,
        "reasons": list(reasons), "limitations": list(_LIMITATIONS), "limits": deepcopy(_LIMITS),
        "outputs": {}, "output_units": {}, "stages": [], "transfers": [],
    }


def _seal(result):
    for key, maximum in (("assembly_inverse_result_count", 8), ("forward_evaluation_count", 512),
                         ("motor_result_count", 8)):
        _require(type(result[key]) is int and 0 <= result[key] <= maximum)
    _json_walk(result, _LIMITS["output_json"])
    if result["request_sha256"] is not None and result["status"] != "MODEL_INAPPLICABLE":
        result["evaluation_sha256"] = sha256_record({
            k: v for k, v in result.items() if k != "evaluation_sha256"})
    return result


def _snapshot(actual, limit):
    _json_walk(actual, _LIMITS[limit])
    retained = deepcopy(actual)
    _json_walk(retained, _LIMITS[limit])
    return retained


def _power_units():
    return {
        "assembly": {"outputs": deepcopy(_ASSEMBLY_CATALOG["output_field_units"])},
        "power": {
            "motors": {"id": "label", "actual_motor_request": deepcopy(_MOTOR_REQUEST_UNITS),
                       "actual_motor_result": {"outputs": deepcopy(_MOTOR_UNITS)},
                       "allocated_heat_w": "W", "unallocated_loss_w": "W"},
            **{key: "W" for key in _TOTAL_FIELDS}, "all_motors_within_declared_limits": "1",
        },
    }


def evaluate_tabulated_target_dc_power(request):
    """Bind one actual assembly to one actual DC evaluation per selected rotor."""
    try:
        _json_walk(request, _LIMITS["input_json"])
        snapshot = deepcopy(request)
        _json_walk(snapshot, _LIMITS["input_json"])
        _require(type(snapshot) is dict and snapshot.keys() == set(_ROOT))
        _require(type(snapshot["evaluation"]) is str)
        if snapshot["evaluation"] != EVALUATION:
            return _response("SOLVER_UNSUPPORTED", [_REASONS["unsupported"]])
        _preflight(snapshot)
    except (ValueError, OverflowError):
        return _response("MODEL_INAPPLICABLE", [_REASONS["invalid"]])
    except Exception:  # noqa: BLE001
        return _response("EXECUTION_FAILED", [_REASONS["snapshot"]])
    digest, inverses, forwards, count = None, 0, 0, 0
    try:
        digest = sha256_record(snapshot)
        supplied = snapshot["assembly"]
        actual = assembly.evaluate_tabulated_thrust_target_assembly(deepcopy(supplied))
        retained = _snapshot(actual, "assembly_output_json")
        _require(validate_tabulated_thrust_target_assembly_result(retained, supplied) is None)
        inverses = retained["inverse_result_count"]
        forwards = retained["forward_evaluation_count"]
        if retained["status"] != "COMPUTED_EXPERIMENTAL":
            return _seal(_response(retained["status"], [_REASONS["assembly"]],
                                   digest, inverses, forwards))
        assembly_digest = sha256_record(retained)
        stages = [{"stage": "assembly", "inputs": deepcopy(supplied),
                   "inputs_sha256": sha256_record(supplied), "result_sha256": assembly_digest}]
        rows, transfers = [], []
        for index, (motor, rotor) in enumerate(zip(
            snapshot["motors"], retained["outputs"]["rotors"], strict=True
        )):
            selected = rotor["actual_target_result"]["outputs"]
            forward = selected["actual_forward_result"]["outputs"]
            operating = {
                "angular_speed_rad_s": selected["actual_forward_request"]["angular_speed_rad_s"],
                "shaft_torque_nm": forward["shaft_torque_nm"],
            }
            motor_request = {
                "evaluation": dc.EVALUATION, "parameters": deepcopy(motor["parameters"]),
                "declared_limits": deepcopy(motor["declared_limits"]), "operating_point": operating,
            }
            _json_walk(motor_request, _LIMITS["motor_input_json"])
            actual_motor = dc.evaluate_dc_motor(deepcopy(motor_request))
            motor_result = _snapshot(actual_motor, "motor_output_json")
            _require(_validate_motor(motor_result, motor_request) is None)
            count += 1
            values = motor_result["outputs"]
            _require(math.isclose(values["shaft_power_w"], forward["shaft_power_w"],
                                  rel_tol=1e-12, abs_tol=1e-12))
            allocated = th.checked_product(values["total_loss_w"], motor["heat_fraction_of_motor_loss"])
            unallocated = th.checked_difference(values["total_loss_w"], allocated)
            rows.append({"id": motor["id"], "actual_motor_request": motor_request,
                         "actual_motor_result": motor_result, "allocated_heat_w": allocated,
                         "unallocated_loss_w": unallocated})
            stage, request_digest = "motor:" + motor["id"], sha256_record(motor_request)
            stages.append({"stage": stage, "inputs": deepcopy(motor_request),
                           "inputs_sha256": request_digest, "result_sha256": sha256_record(motor_result)})
            base = f"outputs.rotors[{index}].actual_target_result.outputs."
            for field, producer, unit in (
                ("angular_speed_rad_s", "actual_forward_request.angular_speed_rad_s", "rad/s"),
                ("shaft_torque_nm", "actual_forward_result.outputs.shaft_torque_nm", "N*m"),
            ):
                transfers.append({"from_stage": "assembly", "from_field": base + producer,
                                  "to_stage": stage, "to_field": "operating_point." + field,
                                  "value": operating[field], "unit": unit,
                                  "producer_result_sha256": assembly_digest,
                                  "consumer_request_sha256": request_digest})
        totals = {}
        for name, field in (
            ("total_shaft_power_w", "shaft_power_w"),
            ("total_motor_electrical_power_w", "electrical_power_w"),
            ("total_motor_loss_w", "total_loss_w"),
        ):
            totals[name] = dc._power_sum([r["actual_motor_result"]["outputs"][field] for r in rows])
        totals["total_allocated_motor_heat_w"] = dc._power_sum([r["allocated_heat_w"] for r in rows])
        totals["total_unallocated_motor_loss_w"] = dc._power_sum([r["unallocated_loss_w"] for r in rows])
        aux = snapshot["auxiliary"]
        totals["auxiliary_electrical_power_w"] = dc._normal(aux["power_w"])
        totals["auxiliary_heat_w"] = th.checked_product(aux["power_w"], aux["heat_fraction"])
        totals["total_electrical_power_w"] = dc._power_sum([
            totals["total_motor_electrical_power_w"], totals["auxiliary_electrical_power_w"]])
        totals["total_heat_w"] = dc._power_sum([
            totals["total_allocated_motor_heat_w"], totals["auxiliary_heat_w"]])
        totals["all_motors_within_declared_limits"] = all(
            r["actual_motor_result"]["outputs"]["declared_limit_status"] == "WITHIN_DECLARED_LIMITS"
            for r in rows)
        result = _response("COMPUTED_EXPERIMENTAL", [], digest, inverses, forwards, count)
        result.update(diagnostics_complete=True, outputs={"assembly": retained,
                      "power": {"motors": rows, **totals}}, output_units=_power_units(),
                      stages=stages, transfers=transfers)
        return _seal(result)
    except Exception:  # noqa: BLE001 -- sanitized atomic failure; BaseException propagates.
        return _seal(_response("EXECUTION_FAILED", [_REASONS["execution"]],
                               digest, inverses, forwards, count))


def tabulated_target_dc_power_catalog():
    """Fresh code-owned metadata only; no model execution or fabricated result."""
    return {
        **_response("RESEARCH_ONLY", []), "required_fields": list(_ROOT),
        "motor_fields": list(_MOTOR_FIELDS), "parameter_fields": list(_PARAMETERS),
        "declared_limit_fields": list(_DECLARED), "auxiliary_fields": ["power_w", "heat_fraction", "source"],
        "assembly_catalog": deepcopy(_ASSEMBLY_CATALOG),
        "input_units": {
            "evaluation": "label", "assembly": deepcopy(_ASSEMBLY_CATALOG["input_units"]),
            "motors": {"id": "label", "parameters": deepcopy(_PARAMETERS),
                       "declared_limits": deepcopy(_DECLARED), "heat_fraction_of_motor_loss": "1",
                       "heat_source": "text"},
            "auxiliary": {"power_w": "W", "heat_fraction": "1", "source": "text"},
        },
        "output_field_units": _power_units(),
        "count_units": {"assembly_inverse_result_count": "1", "forward_evaluation_count": "1",
                        "motor_result_count": "1"},
        "request_contract": {
            "shape": "exact root and nested fields; no defaults; full unchanged actual V114 request",
            "motors": "builtin ordered list 1..8, exact assembly rotor IDs and order",
            "preflight": "strict builtin JSON before copy; actual V114 pure structural preflight, all rotors and SUM(max_evaluations*annuli)<=32768 before any calls",
            "parameters": "k>0; R>=0; I0>=0; builtin finite normal numbers or allowed zero; no bool",
            "declared_limits": "four strictly positive finite normal maxima; inclusive checks, not attainable RPM or feasibility",
            "sources": "nonblank unverified declarations; applicability exactly constant_parameter_dc_equivalent_only",
            "heat": "builtin finite normal or zero fractions 0..1; auxiliary power>=0; no operating point in motor declarations",
        },
        "formulas": {
            "current": "I=Q/k+I0", "back_emf": "Eb=k*omega", "voltage": "V=Eb+I*R",
            "shaft": "Pshaft=Q*omega", "electrical": "Pelec=V*I",
            "copper": "Pcopper=I*I*R, or exact 0.0 when R=0",
            "friction_equivalent": "Pfriction=Eb*I0", "loss": "Ploss=Pcopper+Pfriction",
            "balance": "accounted=Pshaft+Ploss; residual=Pelec-accounted; abs(residual/max(Pelec,accounted))<=64*binary64_epsilon, or exact zero when norm=0",
            "efficiency": "Pshaft/accounted; null only when accounted, shaft, loss and electrical are zero",
            "allocation": "allocated=actual_loss*fraction; unallocated=actual_loss-allocated",
            "auxiliary": "electrical=declared_power once; heat=power*heat_fraction",
            "totals": "accepted DC power_sum over actual rows; total_electrical=motor_electrical+auxiliary_electrical; total_heat=allocated_motor_heat+auxiliary_heat",
            "arithmetic": "accepted operation order and checked helpers; reject overflow/nonzero underflow; no model reruns",
        },
        "bindings": {
            "calls": "actual V114 assembly once; V115 pure guard returns None; actual DC evaluator once and its compute once per rotor",
            "operating_point": "actual retained selected forward request omega and outputs unsigned Q; assembly spin does not negate motor Q",
            "motor_guard": "full actual envelope and static metadata, exact native scalar types/values/units, arithmetic and inclusive limit checks; no DC compute call",
            "preservation": "full actual assembly once and full actual motor result once per row, unchanged hashes; actual motor has no evaluation_sha256",
            "snapshots": "independent bounded walks then immediate detached snapshots before guards; arguments detached",
            "shaft_cross_binding": "rel_tol=1e-12 abs_tol=1e-12 W for multiply order only, not a physical threshold",
            "stages": "actual assembly and motor:<id> inputs with request/full-result digests only",
            "transfers": "scalar omega/Q; full actual assembly producer digest and actual motor request consumer digest",
            "units": "assembly units ONLY outputs.assembly.outputs; motor units ONLY actual_motor_result.outputs; actual motor request units cover all parameters/limits/operating point and sources",
            "provenance": "equation source is declared accepted DC MIT Drela URL/scope; caller parameters and heat sources unverified; no fetching",
        },
        "status_reason_matrix": {
            "COMPUTED_EXPERIMENTAL": [], "SOLVER_UNSUPPORTED": [_REASONS["unsupported"]],
            "MODEL_INAPPLICABLE": [_REASONS["invalid"], _REASONS["assembly"]],
            "EXECUTION_FAILED": [_REASONS["snapshot"], _REASONS["execution"], _REASONS["assembly"]],
            **{s: [_REASONS["assembly"]] for s in ("TARGET_NOT_BRACKETED", "ITERATION_LIMIT", "NUMERICAL_LIMIT")},
        },
        "response_contract": {
            "atomic": "all failures outputs/units {}, stages/transfers [], diagnostics false; no exception text",
            "stop": "guarded noncomputed assembly status propagates with zero motors; invalid assembly counts discarded",
            "counts": "assembly_inverse_result_count 0..8, forward_evaluation_count 0..512 trusted only after V115 guard; motor_result_count 0..8 increments only after full success guard; previous guarded counts survive later failure; no execution attestation",
            "hashes": "request_sha256 binds actual snapshot; evaluation_sha256 hashes full outer response omitting itself; MODEL_INAPPLICABLE request-only/null evaluation; preflight and unsupported both null",
            "exceptions": "ordinary exceptions sanitized; BaseException propagates; V115 narrow infrastructure copy/hash fault admission unchanged",
            "limits": "independent JSON input/output walks for outer, assembly and motor; no HTTP byte limits",
        },
    }
