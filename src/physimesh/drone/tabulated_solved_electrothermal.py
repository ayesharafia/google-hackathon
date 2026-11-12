"""One-way chronological bridge from actual allocated DC heat to lumped screening."""

import math
import sys
from copy import deepcopy

from . import tabulated_solved_dc_energy as energy
from . import thermal
from .provenance import sha256_record
from .tabulated_hover_bemt_request import _json_walk, _require
from .thermal_result_validation import _INPUT_JSON, _OUTPUT_JSON, _OUTPUT_UNITS, validate_thermal_result

EVALUATION = "tabulated_solved_electrothermal_experimental"
SCHEMA_VERSION = "tabulated_solved_electrothermal_v1"
_ENERGY_CATALOG = energy.tabulated_solved_dc_energy_catalog()
_ROOT = ("evaluation", "energy_request", "thermal_body", "thermal_segments")
_BODY = ("mass_kg", "specific_heat_j_kg_k", "initial_temperature_k",
         "lumped_biot_number", "property_source")
_SEGMENT = ("id", "ambient_temperature_k", "conductance_w_k")
_JSON = {"root_depth": 1, "max_string_characters": 2000, "max_integer_bits": 1023,
         "finite_floats_only": True, "valid_utf8_only": True}
_LIMITS = {
    "input_json": {**_JSON, "max_nodes_including_keys": 4194304,
                   "max_depth": 28, "max_container_items": 256},
    "output_json": {**_JSON, "max_nodes_including_keys": 33554432,
                    "max_depth": 40, "max_container_items": 2048},
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
    "execution": "ELECTROTHERMAL_EXECUTION_FAILED",
}
_LIMITATIONS = (
    "Forward one-way allocated-heat temperature screening, not thermal motor feedback or derating.",
    "Caller-prescribed chronology and synthetic or unverified property/source declarations.",
    "No physical temperature, hotspots, measured-parameter or Biot validation is established.",
    "No ESC, battery SOC, reserve, climb, trim, control, stability or real-flight mission model.",
    "No radiation, temperature feedback, motor derating, battery/ESC dynamics or real mission model.",
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
    _require(type(request) is dict and request.keys() == set(_ROOT))
    energy._exact(request["evaluation"], EVALUATION)
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
    _json_walk(result, _LIMITS["output_json"])
    return result


_ENERGY_KEYS = frozenset((
    "evaluation", "schema_version", "status", "evidence_level", "physical_validation",
    "numerical_qualification", "runtime_identity", "aircraft_status", "feasibility",
    "diagnostics_complete", "point_result_count", "solve_result_count",
    "assembly_evaluation_count", "forward_evaluation_count", "motor_result_count",
    "request_sha256", "evaluation_sha256", "reasons", "limitations", "limits",
    "outputs", "output_units", "stages", "transfers",
))
_ENERGY_DYNAMIC = frozenset((
    "status", "diagnostics_complete", *energy._COUNTS, "request_sha256", "evaluation_sha256",
    "reasons", "outputs", "output_units", "stages", "transfers",
))


def _guard_energy_success(actual, request):
    """Pure full V128 success admission, including every actual point exactly once."""
    _json_walk(actual, _LIMITS["energy_output_json"])
    _json_walk(request, _LIMITS["energy_input_json"])
    energy._preflight(request)
    _require(type(actual) is dict and actual.keys() == _ENERGY_KEYS)
    for key in _ENERGY_KEYS - _ENERGY_DYNAMIC:
        energy._exact(actual[key], _ENERGY_CATALOG[key])
    energy._exact(actual["status"], "COMPUTED_EXPERIMENTAL")
    energy._exact(actual["diagnostics_complete"], True)
    energy._exact(actual["reasons"], [])
    for key, maximum in energy._COUNTS.items():
        _require(type(actual[key]) is int and 0 <= actual[key] <= maximum)
    digest = sha256_record(request)
    energy._exact(actual["request_sha256"], digest)
    energy._exact(actual["evaluation_sha256"], sha256_record({
        key: value for key, value in actual.items() if key != "evaluation_sha256"}))
    outputs = actual["outputs"]
    _require(type(outputs) is dict and outputs.keys() == {"points", "energy_state", "energy"})
    points = outputs["points"]
    _require(type(points) is list and len(points) == len(request["segments"]))
    counts, stages, units, all_met = dict.fromkeys(energy._COUNTS, 0), [], [], True
    for row, segment in zip(points, request["segments"], strict=True):
        _require(type(row) is dict and row.keys() == {
            "segment_id", "duration_s", "actual_power_result"})
        energy._exact(row["segment_id"], segment["id"])
        energy._exact(row["duration_s"], segment["duration_s"])
        retained, supplied = row["actual_power_result"], segment["power_request"]
        _require(energy._guard_point_success(retained, supplied) is None)
        counts["point_result_count"] += 1
        for key in energy._COUNTS:
            if key != "point_result_count":
                counts[key] += retained[key]
        stages.append({"stage": "segment:" + segment["id"], "inputs": supplied,
                       "inputs_sha256": sha256_record(supplied),
                       "result_sha256": sha256_record(retained)})
        units.append(energy._point_row_units(retained["output_units"]))
        all_met = all_met and retained["outputs"]["power_state"] == "COMPUTED"
    for key, expected in counts.items():
        energy._exact(actual[key], expected)
    energy._exact(actual["stages"], stages)
    expected_units = {"points": units, "energy_state": "label", "energy": "not_applicable"}
    if not all_met:
        energy._exact(outputs["energy_state"], "NOT_RUN_RESIDUAL_UNMET")
        energy._exact(outputs["energy"], None)
        energy._exact(actual["output_units"], expected_units)
        energy._exact(actual["transfers"], [])
        return
    energy._exact(outputs["energy_state"], "COMPUTED")
    expected_units["energy"] = energy._energy_units()
    energy._exact(actual["output_units"], expected_units)
    rows, transfers, durations = [], [], []
    energies = {key: [] for key in energy._POWER_FIELDS}
    elapsed, cumulative, all_within = 0.0, dict.fromkeys(energy._POWER_FIELDS, 0.0), True
    for index, row in enumerate(points):
        power = row["actual_power_result"]["outputs"]["power"]
        duration, start = row["duration_s"], elapsed
        durations.append(duration)
        elapsed = energy.dc._power_sum(durations)
        _require(elapsed > start)
        joules = {key: thermal.checked_product(power[field], duration)
                  for key, field in energy._POWER_FIELDS.items()}
        previous = cumulative
        for key in energy._POWER_FIELDS:
            energies[key].append(joules[key])
        cumulative = {key: energy.dc._power_sum(values) for key, values in energies.items()}
        for key in energy._POWER_FIELDS:
            _require(joules[key] == 0 or cumulative[key] > previous[key])
        rows.append({"segment_id": row["segment_id"], "start_time_s": start,
                     "end_time_s": elapsed, "energy_j": joules,
                     "cumulative_energy_j": cumulative})
        all_within = all_within and power["all_motors_within_declared_limits"]
        for key, field in energy._POWER_FIELDS.items():
            transfers.append({
                "from_stage": stages[index]["stage"], "from_field": "outputs.power." + field,
                "to_stage": "energy", "to_field": f"outputs.energy.segments[{index}].energy_j.{key}",
                "value": power[field], "unit": "W",
                "producer_result_sha256": stages[index]["result_sha256"],
                "consumer_request_sha256": digest,
            })
    totals = {key: energy.dc._power_sum(values) for key, values in energies.items()}
    energy._exact(outputs["energy"], {
        "segments": rows, "elapsed_s": elapsed, "totals_j": totals,
        "totals_wh": {key: thermal.checked_quotient(value, 3600) for key, value in totals.items()},
        "all_motors_within_declared_limits": all_within,
    })
    energy._exact(actual["transfers"], transfers)


def _stage(name, inputs, actual):
    return {"stage": name, "inputs": deepcopy(inputs), "inputs_sha256": sha256_record(inputs),
            "result_sha256": sha256_record(actual)}


def evaluate_tabulated_solved_electrothermal(request):
    """Admit actual V128 once, then actual thermal once only when every residual is met."""
    try:
        snapshot = _snapshot(request, "input_json")
        _require(type(snapshot) is dict and snapshot.keys() == set(_ROOT))
        _require(type(snapshot["evaluation"]) is str)
        if snapshot["evaluation"] != EVALUATION:
            return _seal(_response("SOLVER_UNSUPPORTED", [_REASONS["unsupported"]]))
        _preflight(snapshot)
    except (ValueError, OverflowError):
        return _seal(_response("MODEL_INAPPLICABLE", [_REASONS["invalid"]]))
    except Exception:  # noqa: BLE001 -- sanitized ordinary admission faults only.
        return _seal(_response("EXECUTION_FAILED", [_REASONS["snapshot"]]))
    digest, counts, phase = None, dict.fromkeys(_COUNTS, 0), "execution"
    try:
        digest = sha256_record(snapshot)
        supplied = snapshot["energy_request"]
        arguments = deepcopy(supplied)
        phase = "energy"
        retained_energy = _snapshot(energy.evaluate_tabulated_solved_dc_energy(arguments),
                                    "energy_output_json")
        _require(_guard_energy_success(retained_energy, supplied) is None)
        counts["energy_result_count"] = 1
        for key in energy._COUNTS:
            counts[key] = retained_energy[key]
        phase = "execution"
        stages = [_stage("energy", supplied, retained_energy)]
        result = _response("COMPUTED_EXPERIMENTAL", [], digest, counts)
        result.update(diagnostics_complete=True, outputs={
            "energy": retained_energy, "thermal_state": "NOT_RUN_RESIDUAL_UNMET", "thermal": None},
            output_units={"energy": {"outputs": deepcopy(retained_energy["output_units"])},
                          "thermal_state": "label", "thermal": "not_applicable"}, stages=stages)
        if retained_energy["outputs"]["energy_state"] == "NOT_RUN_RESIDUAL_UNMET":
            return _seal(result)
        points = retained_energy["outputs"]["points"]
        thermal_request = {"evaluation": "lumped_thermal_screening", **snapshot["thermal_body"],
                           "segments": []}
        for row, declared in zip(points, snapshot["thermal_segments"], strict=True):
            thermal_request["segments"].append({
                "duration_s": row["duration_s"],
                "ambient_temperature_k": declared["ambient_temperature_k"],
                "heat_input_w": row["actual_power_result"]["outputs"]["power"]["total_heat_w"],
                "conductance_w_k": declared["conductance_w_k"],
            })
        _json_walk(thermal_request, _LIMITS["thermal_input_json"])
        arguments = deepcopy(thermal_request)
        phase = "thermal"
        retained_thermal = _snapshot(thermal.screen_thermal(arguments), "thermal_output_json")
        _require(validate_thermal_result(retained_thermal, thermal_request) is None)
        counts["thermal_result_count"] = 1
        result["thermal_result_count"] = 1
        phase = "execution"
        integrated = retained_energy["outputs"]["energy"]
        for row, thermal_row in zip(integrated["segments"],
                                    retained_thermal["outputs"]["segments"], strict=True):
            # Native-int heat may become thermal float only when the actual joules match exactly.
            _require(thermal_row["heat_input_j"] == row["energy_j"]["total_allocated_heat"])
        _require(math.isclose(retained_thermal["outputs"]["total_heat_input_j"],
                              integrated["totals_j"]["total_allocated_heat"],
                              rel_tol=64 * sys.float_info.epsilon, abs_tol=0.0))
        # Each guard establishes its own chronology. Thermal adds converted floats sequentially;
        # V128 uses ordered DC sums of native durations. Their elapsed totals need not be equal.
        stages.append(_stage("thermal", thermal_request, retained_thermal))
        transfers = []
        for index, segment in enumerate(thermal_request["segments"]):
            for source, target, unit in (
                ("actual_power_result.outputs.power.total_heat_w", "heat_input_w", "W"),
                ("duration_s", "duration_s", "s"),
            ):
                transfers.append({
                    "from_stage": "energy", "from_field": f"outputs.points[{index}].{source}",
                    "to_stage": "thermal", "to_field": f"segments[{index}].{target}",
                    "value": segment[target], "unit": unit,
                    "producer_result_sha256": stages[0]["result_sha256"],
                    "consumer_request_sha256": stages[1]["inputs_sha256"],
                })
        result["outputs"].update(thermal_state="COMPUTED", thermal=retained_thermal)
        result["output_units"]["thermal"] = {"outputs": deepcopy(retained_thermal["output_units"])}
        result["transfers"] = transfers
        return _seal(result)
    except Exception:  # noqa: BLE001 -- BaseException intentionally propagates.
        failed = _response("EXECUTION_FAILED", [_REASONS[phase]], digest, counts)
        try:
            return _seal(failed)
        except Exception:  # noqa: BLE001 -- failing digest infrastructure can leave a null hash.
            return failed


def _catalog_units(unmet=False):
    """Describe dynamic energy unit rows; runtime units always come from admitted children."""
    energy_units = deepcopy(_ENERGY_CATALOG["output_field_units"])
    if unmet:
        energy_units["energy"] = "not_applicable"
    return {"energy": {"outputs": energy_units}, "thermal_state": "label",
            "thermal": "not_applicable" if unmet else {"outputs": deepcopy(_OUTPUT_UNITS)}}


def tabulated_solved_electrothermal_catalog():
    """Fresh code-owned policy, dynamic point unit variants and both thermal states."""
    return {
        **_response("RESEARCH_ONLY", []), "required_fields": list(_ROOT), "defaults": {},
        "thermal_body_fields": list(_BODY), "thermal_segment_fields": list(_SEGMENT),
        "energy_catalog": deepcopy(_ENERGY_CATALOG),
        "input_units": {
            "evaluation": "label", "energy_request": deepcopy(_ENERGY_CATALOG["input_units"]),
            "thermal_body": {"mass_kg": "kg", "specific_heat_j_kg_k": "J/(kg*K)",
                             "initial_temperature_k": "K", "lumped_biot_number": "1",
                             "property_source": "label"},
            "thermal_segments": {"id": "label", "ambient_temperature_k": "K",
                                 "conductance_w_k": "W/K"},
        },
        "output_field_units": _catalog_units(),
        "output_field_units_residual_unmet": _catalog_units(unmet=True),
        "thermal_states": ["COMPUTED", "NOT_RUN_RESIDUAL_UNMET"],
        "count_units": dict.fromkeys(_COUNTS, "1"),
        "request_contract": {
            "shape": "Exact evaluation,energy_request,thermal_body,thermal_segments; no defaults.",
            "energy": "Exact V128 evaluation, independent unchanged input budget and full pure preflight before models.",
            "thermal": "Explicit V121 body and ordered segment fields; exact ID/count match to every energy segment before models.",
            "biot": "Declaration in [0,0.1] for screening only; conventional Bi<0.1 is not a new gate or validation.",
            "budgets": "Root input 4M nodes/depth28/container256; output 32M/depth40/container2048; unchanged independent V128 and V119 budgets.",
        },
        "bindings": {
            "energy": "Actual V128 once, immediate bounded full snapshot, pure full success guard; no router, model reruns or fabricated child envelope.",
            "points": "Every actual point full-guarded exactly once per energy guard; native ID/duration types, expected counts, stages, hashes, dynamic units and nine transfers admitted.",
            "unmet": "All mixed points and stages retained; thermal null, state NOT_RUN_RESIDUAL_UNMET, one outer energy stage, no outer transfers or temperature claim.",
            "thermal": "One actual thermal sequence from retained outputs.points with actual total_heat_w and original native durations; explicit matched ambient/conductance; full V119 success guard without integrator reruns.",
            "heat": "Allocated heat only; no new allocation and no substitution of total motor loss.",
            "stages": "Full supplied energy request/full retained result digest; full actual thermal request/full retained result digest.",
            "transfers": "Heat then duration per point from outputs.points[i].actual_power_result.outputs.power.total_heat_w and outputs.points[i].duration_s to thermal segments; full energy result and thermal request digests.",
            "counts": "Increment only after entire child guard; earlier fully guarded child counts survive atomic failures; counts are not attempts or execution attestation.",
        },
        "formulas": {
            "energy": "V128 checked nine W*original-duration products; ordered DC prefix sums, strict positive time/energy increments, J/Wh totals and exact declaration flags.",
            "thermal": "Actual V119 constant-property sequence and full arithmetic guard; endpoint of one row starts the next.",
            "native_conversion": "Thermal injection retains native original duration and actual heat. thermal._number converts builtin int/float to float; row duration is that float. Native integer heat conversion is accepted only if actual per-row joules equal V128 exactly.",
            "heat_j": "Exact per-row thermal heat_input_j == energy.segments[i].energy_j.total_allocated_heat; thermal fsum vs V128 DC total rel_tol=64*binary64 epsilon, abs_tol=0, rounding only.",
            "chronology": "Both full guards establish their own chronology and bind original durations. Do not compare energy elapsed to thermal elapsed: DC sum and naive float additions use different arithmetic.",
        },
        "response_contract": {
            "computed": "Full actual energy and thermal retained once; thermal_state COMPUTED, two stages and two scalar transfers per segment.",
            "unmet_units": "Energy retains actual ordered mixed point unit rows, energy not_applicable; thermal_state label and thermal not_applicable.",
            "failures": "Atomic empty outputs/units/stages/transfers; diagnostics false; only previously fully guarded counts retained; no raw child reasons or causal inference.",
            "sealing": "Builtin JSON bounded before copying and before/after sealing; full root request and result hashes bind data, not execution identity.",
            "exceptions": "Ordinary exceptions sanitized by phase; BaseException propagates.",
        },
        "status_reason_matrix": {
            "COMPUTED_EXPERIMENTAL": [], "SOLVER_UNSUPPORTED": [_REASONS["unsupported"]],
            "MODEL_INAPPLICABLE": [_REASONS["invalid"]],
            "EXECUTION_FAILED": [_REASONS[key] for key in ("snapshot", "energy", "thermal", "execution")],
        },
    }
