"""One-way chronological bridge from actual allocated DC heat to lumped screening."""

import math
import sys
from copy import deepcopy

from . import tabulated_target_dc_energy as energy
from . import thermal
from .provenance import sha256_record
from .tabulated_hover_bemt_request import _json_walk, _require
from .tabulated_target_dc_energy_validation import validate_tabulated_target_dc_energy_result
from .thermal_result_validation import _INPUT_JSON, _OUTPUT_JSON, _OUTPUT_UNITS, validate_thermal_result

EVALUATION = "prescribed_tabulated_dc_electrothermal_experimental"
SCHEMA_VERSION = "tabulated_electrothermal_v1"
_ENERGY_CATALOG = energy.tabulated_target_dc_energy_catalog()
_ROOT = ("evaluation", "energy_request", "thermal_body", "thermal_segments")
_BODY = ("mass_kg", "specific_heat_j_kg_k", "initial_temperature_k",
         "lumped_biot_number", "property_source")
_SEGMENT = ("id", "ambient_temperature_k", "conductance_w_k")
_JSON = {"root_depth": 1, "max_string_characters": 2000, "max_integer_bits": 1023,
         "finite_floats_only": True, "valid_utf8_only": True}
_LIMITS = {
    "input_json": {**_JSON, "max_nodes_including_keys": 1048576,
                   "max_depth": 24, "max_container_items": 256},
    "output_json": {**_JSON, "max_nodes_including_keys": 8388608,
                    "max_depth": 36, "max_container_items": 2048},
    "energy_input_json": deepcopy(_ENERGY_CATALOG["limits"]["input_json"]),
    "energy_output_json": deepcopy(_ENERGY_CATALOG["limits"]["output_json"]),
    "thermal_input_json": deepcopy(_INPUT_JSON),
    "thermal_output_json": deepcopy(_OUTPUT_JSON),
}
_COUNTS = {"energy_result_count": 1, "thermal_result_count": 1, **energy._COUNTS}
_REASONS = {
    "invalid": "Invalid bounded tabulated electrothermal request.",
    "unsupported": "Unsupported evaluation.", "snapshot": "Request snapshot or preflight failed.",
    "energy": "ENERGY_BOUNDARY_FAILED", "thermal": "THERMAL_BOUNDARY_FAILED",
    "execution": "Electrothermal execution or provenance failed.",
}
_LIMITATIONS = (
    "Forward one-way allocated-heat temperature screening, not thermal motor feedback or derating.",
    "Caller-prescribed chronology and synthetic or unverified property/source declarations.",
    "No physical temperature, hotspots, measured-parameter or Biot validation is established.",
    "No ESC, battery SOC, reserve, climb, trim, control, stability or real-flight mission model.",
    "No aircraft feasibility, API, publication, novelty, accuracy or numerical qualification.",
    "Declared motor limit exceedance remains computed with its nested flag false.",
    "Full child sources and limitations remain applicable; hashes bind data, not execution identity.",
    "Counts describe fully guarded successes, not calls, attempts or proof of no call.",
    "Unvalidated child status and reasons are discarded; boundary failure establishes no causality.",
)


def _snapshot(actual, limit):
    """Walk the full builtin JSON before deepcopy can encounter any foreign hook."""
    _json_walk(actual, _LIMITS[limit])
    retained = deepcopy(actual)
    _json_walk(retained, _LIMITS[limit])
    return retained


def _preflight(request):
    supplied = request["energy_request"]
    _json_walk(supplied, _LIMITS["energy_input_json"])
    _require(type(supplied) is dict and supplied.keys() == set(energy._ROOT))
    _require(type(supplied["evaluation"]) is str and supplied["evaluation"] == energy.EVALUATION)
    energy._preflight(supplied)  # Every point/motor and aggregate work, before any model call.
    body = request["thermal_body"]
    _require(type(body) is dict and body.keys() == set(_BODY))
    mass, cp, temperature, biot = map(thermal._number, (body[name] for name in _BODY[:4]))
    _require(min(mass, cp, temperature) > 0 and 0 <= biot <= 0.1)
    _require(thermal.checked_product(mass, cp) > 0)
    source = body["property_source"]
    _require(type(source) is str and bool(source.strip()) and len(source) <= 2000)
    segments = request["thermal_segments"]
    _require(type(segments) is list and len(segments) == len(supplied["segments"]))
    for segment, point in zip(segments, supplied["segments"], strict=True):
        _require(type(segment) is dict and segment.keys() == set(_SEGMENT))
        _require(type(segment["id"]) is str and segment["id"] == point["id"])
        ambient, conductance = map(thermal._number, (
            segment["ambient_temperature_k"], segment["conductance_w_k"]))
        _require(ambient > 0 and conductance >= 0)


def _response(status, reasons, digest=None, counts=None):
    return {
        "evaluation": EVALUATION, "schema_version": SCHEMA_VERSION, "status": status,
        "evidence_level": "unverified", "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None, "feasibility": None, "diagnostics_complete": False,
        **(dict.fromkeys(_COUNTS, 0) if counts is None else counts),
        "request_sha256": digest, "evaluation_sha256": None, "reasons": list(reasons),
        "limitations": list(_LIMITATIONS), "limits": deepcopy(_LIMITS),
        "outputs": {}, "output_units": {}, "stages": [], "transfers": [],
    }


def _seal(result):
    for key, maximum in _COUNTS.items():
        _require(type(result[key]) is int and 0 <= result[key] <= maximum)
    _json_walk(result, _LIMITS["output_json"])
    if result["request_sha256"] is not None and result["status"] != "MODEL_INAPPLICABLE":
        result["evaluation_sha256"] = sha256_record({
            key: value for key, value in result.items() if key != "evaluation_sha256"})
    return result


def _output_units():
    return {"energy": {"outputs": deepcopy(_ENERGY_CATALOG["output_field_units"])},
            "thermal": {"outputs": deepcopy(_OUTPUT_UNITS)}}


def evaluate_tabulated_electrothermal(request):
    """Run each actual child once; retain only full, detached, guarded successes."""
    try:
        snapshot = _snapshot(request, "input_json")
        _require(type(snapshot) is dict and snapshot.keys() == set(_ROOT))
        _require(type(snapshot["evaluation"]) is str)
        if snapshot["evaluation"] != EVALUATION:
            return _response("SOLVER_UNSUPPORTED", [_REASONS["unsupported"]])
        _preflight(snapshot)
    except (ValueError, OverflowError):
        return _response("MODEL_INAPPLICABLE", [_REASONS["invalid"]])
    except Exception:  # noqa: BLE001 -- foreign exception text is never exported.
        return _response("EXECUTION_FAILED", [_REASONS["snapshot"]])
    digest, counts, phase = None, dict.fromkeys(_COUNTS, 0), "execution"
    try:
        digest = sha256_record(snapshot)
        supplied = snapshot["energy_request"]
        arguments = deepcopy(supplied)
        phase = "energy"
        actual = energy.evaluate_tabulated_target_dc_energy(arguments)
        retained_energy = _snapshot(actual, "energy_output_json")
        _require(type(retained_energy) is dict and
                 type(retained_energy.get("status")) is str and
                 retained_energy["status"] == "COMPUTED_EXPERIMENTAL")
        _require(validate_tabulated_target_dc_energy_result(retained_energy, supplied) is None)
        counts["energy_result_count"] = 1
        for key in energy._COUNTS:
            counts[key] = retained_energy[key]
        phase = "execution"
        rows = retained_energy["outputs"]["segments"]
        thermal_request = {"evaluation": "lumped_thermal_screening", **snapshot["thermal_body"],
                           "segments": []}
        for row, declared in zip(rows, snapshot["thermal_segments"], strict=True):
            thermal_request["segments"].append({
                "duration_s": row["duration_s"],
                "ambient_temperature_k": declared["ambient_temperature_k"],
                "heat_input_w": row["actual_power_result"]["outputs"]["power"]["total_heat_w"],
                "conductance_w_k": declared["conductance_w_k"],
            })
        _json_walk(thermal_request, _LIMITS["thermal_input_json"])
        arguments = deepcopy(thermal_request)
        phase = "thermal"
        actual = thermal.screen_thermal(arguments)
        retained_thermal = _snapshot(actual, "thermal_output_json")
        _require(type(retained_thermal) is dict and
                 type(retained_thermal.get("status")) is str and
                 retained_thermal["status"] == "SCREENING_COMPUTED")
        _require(validate_thermal_result(retained_thermal, thermal_request) is None)
        counts["thermal_result_count"] = 1
        phase = "execution"
        for row, thermal_row in zip(rows, retained_thermal["outputs"]["segments"], strict=True):
            _require(thermal_row["heat_input_j"] == row["energy_j"]["total_allocated_heat"])
        # V118 sums sequentially; thermal uses fsum. This permits rounding only.
        _require(math.isclose(retained_thermal["outputs"]["total_heat_input_j"],
                              retained_energy["outputs"]["totals_j"]["total_allocated_heat"],
                              rel_tol=64 * sys.float_info.epsilon, abs_tol=0.0))
        stages = [{"stage": name, "inputs": deepcopy(inputs),
                   "inputs_sha256": sha256_record(inputs), "result_sha256": sha256_record(result)}
                  for name, inputs, result in (("energy", supplied, retained_energy),
                                               ("thermal", thermal_request, retained_thermal))]
        transfers = []
        for index, segment in enumerate(thermal_request["segments"]):
            for source, target, unit in (
                ("actual_power_result.outputs.power.total_heat_w", "heat_input_w", "W"),
                ("duration_s", "duration_s", "s"),
            ):
                transfers.append({
                    "from_stage": "energy", "from_field": f"outputs.segments[{index}].{source}",
                    "to_stage": "thermal", "to_field": f"segments[{index}].{target}",
                    "value": segment[target], "unit": unit,
                    "producer_result_sha256": stages[0]["result_sha256"],
                    "consumer_request_sha256": stages[1]["inputs_sha256"],
                })
        result = _response("COMPUTED_EXPERIMENTAL", [], digest, counts)
        result.update(diagnostics_complete=True, outputs={"energy": retained_energy,
                      "thermal": retained_thermal}, output_units=_output_units(),
                      stages=stages, transfers=transfers)
        return _seal(result)
    except Exception:  # noqa: BLE001 -- BaseException intentionally propagates.
        failed = _response("EXECUTION_FAILED", [_REASONS[phase]], digest, counts)
        try:
            return _seal(failed)
        except Exception:  # noqa: BLE001 -- digest infrastructure can leave a null result hash.
            return failed


def tabulated_electrothermal_catalog():
    """Return fresh code-owned metadata without executing either child model."""
    return {
        **_response("RESEARCH_ONLY", []), "required_fields": list(_ROOT),
        "thermal_body_fields": list(_BODY), "thermal_segment_fields": list(_SEGMENT),
        "energy_catalog": deepcopy(_ENERGY_CATALOG), "output_field_units": _output_units(),
        "count_units": dict.fromkeys(_COUNTS, "1"),
        "bindings": {
            "children": "actual V118 once, full snapshot/V120; actual thermal once, full snapshot/V119",
            "heat": "actual allocated total_heat_w and actual duration; no reallocation or reconstruction",
            "chronology": "all ordered segments in one actual thermal request; native declarations retained",
            "counts": "full success guards only; no attempt count or execution attestation",
            "transfers": "heat then duration per segment; full energy result and thermal request digests",
            "declarations": "ambient and conductance bind through full root and thermal request hashes",
            "heat_j": "exact per row; total relative tolerance 64 binary64 eps, absolute tolerance zero",
        },
    }
