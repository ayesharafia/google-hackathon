"""Bounded chronological integration of guarded actual tabulated DC power points."""

from copy import deepcopy

from . import dc_motor as dc
from . import tabulated_target_dc_power as point
from . import thermal as th
from .provenance import sha256_record
from .tabulated_hover_bemt_request import _json_walk, _require
from .tabulated_target_dc_power_validation import validate_tabulated_target_dc_power_result

EVALUATION = "prescribed_tabulated_target_dc_energy_experimental"
SCHEMA_VERSION = "tabulated_target_dc_energy_v1"
_POINT_CATALOG = point.tabulated_target_dc_power_catalog()
_ROOT = ("evaluation", "segments")
_SEGMENT = ("id", "duration_s", "power_request")
# Each energy key binds exactly one actual V116 power field. total_heat_w is allocated heat.
_POWER_FIELDS = {
    "shaft": "total_shaft_power_w",
    "motor_electrical": "total_motor_electrical_power_w",
    "motor_loss": "total_motor_loss_w",
    "allocated_motor_heat": "total_allocated_motor_heat_w",
    "unallocated_motor_loss": "total_unallocated_motor_loss_w",
    "auxiliary_electrical": "auxiliary_electrical_power_w",
    "auxiliary_heat": "auxiliary_heat_w",
    "total_electrical": "total_electrical_power_w",
    "total_allocated_heat": "total_heat_w",
}
_JSON = {
    "root_depth": 1, "max_string_characters": 2000, "max_integer_bits": 1023,
    "finite_floats_only": True, "valid_utf8_only": True,
}
_LIMITS = {
    "input_json": {**_JSON, "max_depth": 20, "max_nodes_including_keys": 524288,
                   "max_container_items": 256},
    "output_json": {**_JSON, "max_depth": 32, "max_nodes_including_keys": 4194304,
                    "max_container_items": 2048},
    "point_input_json": deepcopy(_POINT_CATALOG["limits"]["input_json"]),
    "point_output_json": deepcopy(_POINT_CATALOG["limits"]["output_json"]),
    "core_work": {"segments_min": 1, "segments_max": 8, "point_calls_max": 8,
                  "assembly_inverse_results_max": 64, "forward_evaluations_max": 4096,
                  "motor_results_max": 64, "point_forward_annuli_max": 32768,
                  "total_forward_annuli_max": 65536},
}
_COUNTS = {"point_result_count": 8, "assembly_inverse_result_count": 64,
           "forward_evaluation_count": 4096, "motor_result_count": 64}
_LIMITATIONS = (
    "Caller-prescribed durations and static isolated points, not a solved mission profile.",
    "Changing altitude does not add interpolation, time dynamics or mass/geometry coupling.",
    "Electrical energy is terminal DC-equivalent demand, not battery energy or SOC.",
    "Allocated heat energy is not temperature; no thermal temperature integration.",
    "No ESC, battery, trim, flight dynamics, reserve budget or available-power model.",
    "No attainability, safety or aircraft feasibility claim; declared exceedance remains computed.",
    "No physical, numerical, runtime, publication, accuracy or novelty qualification.",
    "Actual point limitations and unverified caller parameter/source declarations still apply.",
    "Counts describe guarded returned contracts, not attempts or execution attestation.",
    "Hashes bind full JSON data, not code identity or a compute graph attestation.",
)
_REASONS = {
    "unsupported": "Unsupported evaluation.", "invalid": "Invalid bounded target DC energy request.",
    "snapshot": "Request snapshot failed.",
    "execution": "Target DC energy execution or returned contract failed.",
    "point": "Actual target DC power point returned a noncomputed result.",
}


def _snapshot(actual, limit):
    """Reject foreign hooks before copying, then bound the detached full value."""
    _json_walk(actual, _LIMITS[limit])
    retained = deepcopy(actual)
    _json_walk(retained, _LIMITS[limit])
    return retained


def _preflight(snapshot):
    segments = snapshot["segments"]
    _require(type(segments) is list and 1 <= len(segments) <= 8)
    seen, work = set(), 0
    for segment in segments:
        _require(type(segment) is dict and segment.keys() == set(_SEGMENT))
        identifier = segment["id"]
        point._source(identifier)
        _require(len(identifier) <= 1992)
        _require(identifier not in seen)
        seen.add(identifier)
        point._scalar(segment["duration_s"], positive=True)
        supplied = segment["power_request"]
        _json_walk(supplied, _LIMITS["point_input_json"])
        _require(type(supplied) is dict and supplied.keys() == set(point._ROOT))
        _require(type(supplied["evaluation"]) is str and supplied["evaluation"] == point.EVALUATION)
        point._preflight(supplied)
        work += sum(r["target_template"]["max_evaluations"] *
                    r["target_template"]["rotor_template"]["annuli"]
                    for r in supplied["assembly"]["rotors"])
    _require(work <= _LIMITS["core_work"]["total_forward_annuli_max"])


def _response(status, reasons, digest=None, counts=None):
    return {
        "evaluation": EVALUATION, "schema_version": SCHEMA_VERSION, "status": status,
        "evidence_level": "unverified", "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED", "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None, "feasibility": None, "diagnostics_complete": False,
        **(counts if counts is not None else dict.fromkeys(_COUNTS, 0)),
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
            k: v for k, v in result.items() if k != "evaluation_sha256"})
    return result


def _output_units():
    energy = dict.fromkeys(_POWER_FIELDS, "J")
    return {
        "segments": {"segment_id": "label", "duration_s": "s", "start_time_s": "s",
                     "end_time_s": "s", "actual_power_result": {
                         "outputs": deepcopy(_POINT_CATALOG["output_field_units"])},
                     "energy_j": energy, "cumulative_energy_j": deepcopy(energy)},
        "elapsed_s": "s", "totals_j": deepcopy(energy),
        "totals_wh": dict.fromkeys(_POWER_FIELDS, "Wh"),
        "all_motors_within_declared_limits": "1",
    }


def evaluate_tabulated_target_dc_energy(request):
    """Call each actual V116 point once, snapshot and guard once, then integrate."""
    try:
        snapshot = _snapshot(request, "input_json")
        _require(type(snapshot) is dict and snapshot.keys() == set(_ROOT))
        _require(type(snapshot["evaluation"]) is str)
        if snapshot["evaluation"] != EVALUATION:
            return _response("SOLVER_UNSUPPORTED", [_REASONS["unsupported"]])
        _preflight(snapshot)
    except (ValueError, OverflowError):
        return _response("MODEL_INAPPLICABLE", [_REASONS["invalid"]])
    except Exception:  # noqa: BLE001 -- sanitized snapshot failure, no foreign exception text.
        return _response("EXECUTION_FAILED", [_REASONS["snapshot"]])
    digest, counts = None, dict.fromkeys(_COUNTS, 0)
    try:
        digest = sha256_record(snapshot)
        rows, stages, transfers, durations = [], [], [], []
        energies = {key: [] for key in _POWER_FIELDS}
        elapsed, all_within = 0.0, True
        for index, segment in enumerate(snapshot["segments"]):
            supplied = segment["power_request"]
            actual = point.evaluate_tabulated_target_dc_power(deepcopy(supplied))
            retained = _snapshot(actual, "point_output_json")
            _require(validate_tabulated_target_dc_power_result(retained, supplied) is None)
            # No counts from the returned point are trusted until its entire guard passed.
            counts["point_result_count"] += 1
            for key in _COUNTS:
                if key != "point_result_count":
                    counts[key] += retained[key]
            if retained["status"] != "COMPUTED_EXPERIMENTAL":
                return _seal(_response(retained["status"], [_REASONS["point"]], digest, counts))
            power = retained["outputs"]["power"]
            duration, start = segment["duration_s"], elapsed
            durations.append(duration)
            elapsed = dc._power_sum(durations)
            _require(elapsed > start)
            energy = {key: th.checked_product(power[field], duration)
                      for key, field in _POWER_FIELDS.items()}
            for key in _POWER_FIELDS:
                energies[key].append(energy[key])
            cumulative = {key: dc._power_sum(values) for key, values in energies.items()}
            rows.append({"segment_id": segment["id"], "duration_s": duration,
                         "start_time_s": start, "end_time_s": elapsed,
                         "actual_power_result": retained, "energy_j": energy,
                         "cumulative_energy_j": cumulative})
            all_within = all_within and power["all_motors_within_declared_limits"]
            stage, result_digest = "segment:" + segment["id"], sha256_record(retained)
            stages.append({"stage": stage, "inputs": deepcopy(supplied),
                           "inputs_sha256": sha256_record(supplied), "result_sha256": result_digest})
            for key, field in _POWER_FIELDS.items():
                transfers.append({
                    "from_stage": stage, "from_field": "outputs.power." + field,
                    "to_stage": "energy", "to_field": f"outputs.segments[{index}].energy_j.{key}",
                    "value": power[field], "unit": "W", "producer_result_sha256": result_digest,
                    "consumer_request_sha256": digest,
                })
        totals = {key: dc._power_sum(values) for key, values in energies.items()}
        watt_hours = {key: th.checked_quotient(value, 3600) for key, value in totals.items()}
        result = _response("COMPUTED_EXPERIMENTAL", [], digest, counts)
        result.update(diagnostics_complete=True, outputs={
            "segments": rows, "elapsed_s": elapsed, "totals_j": totals, "totals_wh": watt_hours,
            "all_motors_within_declared_limits": all_within,
        }, output_units=_output_units(), stages=stages, transfers=transfers)
        return _seal(result)
    except Exception:  # noqa: BLE001 -- atomic failure; BaseException intentionally propagates.
        failed = _response("EXECUTION_FAILED", [_REASONS["execution"]], digest, counts)
        try:
            return _seal(failed)
        except Exception:  # noqa: BLE001 -- infrastructure digest failure retains null result hash.
            return failed


def tabulated_target_dc_energy_catalog():
    """Return fresh metadata from the import-time catalog; never execute a model."""
    return {
        **_response("RESEARCH_ONLY", []), "required_fields": list(_ROOT),
        "segment_fields": list(_SEGMENT), "power_fields": dict(_POWER_FIELDS),
        "point_catalog": deepcopy(_POINT_CATALOG),
        "input_units": {"evaluation": "label", "segments": {
            "id": "label", "duration_s": "s", "power_request": deepcopy(_POINT_CATALOG["input_units"])}},
        "output_field_units": _output_units(), "count_units": dict.fromkeys(_COUNTS, "1"),
        "request_contract": {
            "shape": "exact root and segment fields; ordered list 1..8; unique nonblank IDs <=1992 characters",
            "duration": "positive builtin finite normal int/float, no bool; no defaults",
            "preflight": "full actual V116 request and every motor for every segment before first call",
            "work": "all rotors of all points SUM(max_evaluations*annuli)<=65536; each point<=32768",
            "json": "strict bounded builtin JSON walk before deepcopy; independent point input/output budgets",
        },
        "formulas": {
            "energy_j": "checked_product(actual outputs.power[field], duration_s)",
            "cumulative_energy_j": "accepted DC power_sum of all individual segment energies in prefix order",
            "totals_j": "accepted DC power_sum of all individual segment energies in order",
            "totals_wh": "checked_quotient(totals_j[key], 3600)",
            "elapsed_s": "accepted DC power_sum of duration prefix; end_time_s must exceed start_time_s",
            "heat": "total_heat_w maps to total_allocated_heat, not all motor loss",
        },
        "bindings": {
            "point": "actual V116 once per segment; immediate full bounded snapshot then full pure V117 guard once",
            "retention": "full actual point exactly once in row; full power_request only in stage inputs",
            "stages": "segment:<id>, actual full point inputs and request/full-result digests",
            "transfers": "nine actual W scalars per point to outer energy fields; consumer digest is full root request",
            "duration": "bound by full root request digest; not duplicated as a scalar transfer",
            "counts": "guarded returned points including noncomputed failure point; never attempts",
        },
        "response_contract": {
            "atomic": "failure clears outputs/units/stages/transfers; earlier trusted counts survive",
            "stop": "guard-valid noncomputed point status propagates with point reason; no later calls",
            "hashes": "full snapshot request digest; full result omitting itself; MODEL_INAPPLICABLE result hash null",
            "preflight": "invalid/unsupported before calls have zero counts and both hashes null",
            "exceptions": "ordinary exceptions sanitized; BaseException propagates; digest infrastructure failure null hash",
        },
        "status_reason_matrix": {
            "COMPUTED_EXPERIMENTAL": [], "SOLVER_UNSUPPORTED": [_REASONS["unsupported"]],
            "MODEL_INAPPLICABLE": [_REASONS["invalid"], _REASONS["point"]],
            "EXECUTION_FAILED": [_REASONS["snapshot"], _REASONS["execution"], _REASONS["point"]],
            **{s: [_REASONS["point"]] for s in ("TARGET_NOT_BRACKETED", "ITERATION_LIMIT", "NUMERICAL_LIMIT")},
        },
    }
