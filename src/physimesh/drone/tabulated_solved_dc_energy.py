"""Bounded chronological energy from guarded actual tabulated solved DC points."""

import math
from copy import deepcopy

from . import dc_motor as dc
from . import tabulated_solved_dc_power as point
from . import thermal as th
from .provenance import sha256_record
from .reference_air_tabulated_hover import _exact
from .tabulated_hover_bemt_request import _json_walk, _require

EVALUATION = "tabulated_solved_dc_energy_experimental"
SCHEMA_VERSION = "tabulated_solved_dc_energy_v1"
_POINT_CATALOG = point.tabulated_solved_dc_power_catalog()
_ROOT = ("evaluation", "segments")
_SEGMENT = ("id", "duration_s", "power_request")
# Literal V118 mapping: total_heat_w denotes allocated heat only.
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
_LIMITS = {
    "input_json": {**point.power._JSON, "max_nodes_including_keys": 1048576,
                   "max_depth": 24, "max_container_items": 256},
    "output_json": {**point.power._JSON, "max_nodes_including_keys": 16777216,
                    "max_depth": 36, "max_container_items": 2048},
    "point_input_json": deepcopy(_POINT_CATALOG["limits"]["input_json"]),
    "point_output_json": deepcopy(_POINT_CATALOG["limits"]["output_json"]),
    "core_work": {"segments_min": 1, "segments_max": 8, "point_calls_max": 8,
                  "solve_results_max": 8, "assembly_evaluations_max": 512,
                  "forward_evaluations_max": 4096, "motor_results_max": 64,
                  "point_evaluation_annuli_product_max": 65536,
                  "total_evaluation_annuli_product_max": 65536},
}
_COUNTS = {"point_result_count": 8, "solve_result_count": 8,
           "assembly_evaluation_count": 512, "forward_evaluation_count": 4096,
           "motor_result_count": 64}
_LIMITATIONS = (
    "Experimental prescribed chronological durations and isolated static solved points only.",
    "Heterogeneous settings and source declarations are preserved, not a coupled physical mission.",
    "No temperatures, reserve, battery, flight dynamics, interpolation, control or mass feedback.",
    "No mission qualification, physical feasibility, global infeasibility or publication claim.",
    "Electrical energy is terminal DC-equivalent demand; allocated heat energy is not temperature.",
    "Actual point limitations and unverified caller declarations still apply; no source fetching.",
    "Positive durations and positive energy increments must resolve strictly in their ordered sums.",
    "Counts describe fully guarded accepted results, not attempted calls; zero does not mean no call.",
    "Hashes bind retained full JSON, not code, runtime identity or execution attestation.",
    "Nonselected solve result digests are format-only provenance through the guarded point.",
)
_REASONS = {"unsupported": "Unsupported evaluation.",
            "invalid": "Invalid bounded solved DC energy request.",
            "admission": "Request admission failed.", "point": "POINT_BOUNDARY_FAILED",
            "execution": "ENERGY_EXECUTION_FAILED"}


def _snapshot(actual, limit):
    """Bound builtin JSON before copy hooks, equality or hashing."""
    _json_walk(actual, _LIMITS[limit])
    retained = deepcopy(actual)
    _json_walk(retained, _LIMITS[limit])
    return retained


def _preflight(snapshot):
    _require(type(snapshot) is dict and snapshot.keys() == set(_ROOT))
    _exact(snapshot["evaluation"], EVALUATION)
    segments = snapshot["segments"]
    _require(type(segments) is list and 1 <= len(segments) <= 8)
    seen, work = set(), 0
    for segment in segments:
        _require(type(segment) is dict and segment.keys() == set(_SEGMENT))
        identifier = segment["id"]
        point.power._source(identifier)
        _require(len(identifier) <= 1992 and identifier not in seen)
        seen.add(identifier)
        point.power._scalar(segment["duration_s"], positive=True)
        supplied = segment["power_request"]
        _json_walk(supplied, _LIMITS["point_input_json"])
        point._preflight(supplied)
        spec = supplied["solve"]
        work += spec["max_evaluations"] * sum(
            rotor["rotor_template"]["annuli"] for rotor in spec["assembly_template"]["rotors"])
    _require(work <= 65536)


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
    if result["request_sha256"] is not None and result["status"] in (
        "COMPUTED_EXPERIMENTAL", "EXECUTION_FAILED"
    ):
        result["evaluation_sha256"] = sha256_record({
            k: v for k, v in result.items() if k != "evaluation_sha256"})
    _json_walk(result, _LIMITS["output_json"])
    return result


_POINT_KEYS = frozenset((
    "evaluation", "schema_version", "status", "evidence_level", "physical_validation",
    "numerical_qualification", "runtime_identity", "aircraft_status", "feasibility",
    "diagnostics_complete", "solve_result_count", "assembly_evaluation_count",
    "forward_evaluation_count", "motor_result_count", "request_sha256", "evaluation_sha256",
    "reasons", "limitations", "limits", "outputs", "output_units", "stages", "transfers",
))
_POINT_DYNAMIC = frozenset((
    "status", "diagnostics_complete", "solve_result_count", "assembly_evaluation_count",
    "forward_evaluation_count", "motor_result_count", "request_sha256", "evaluation_sha256",
    "reasons", "outputs", "output_units", "stages", "transfers",
))


def _guard_point_success(actual, request):
    """Pure full V127 success admission; no evaluator or model computation calls."""
    _json_walk(actual, _LIMITS["point_output_json"])
    _json_walk(request, _LIMITS["point_input_json"])
    point._preflight(request)
    _require(type(actual) is dict and actual.keys() == _POINT_KEYS)
    for key in _POINT_KEYS - _POINT_DYNAMIC:
        _exact(actual[key], _POINT_CATALOG[key])
    _exact(actual["status"], "COMPUTED_EXPERIMENTAL")
    _exact(actual["diagnostics_complete"], True)
    _exact(actual["reasons"], [])
    for key, maximum in (("solve_result_count", 1), ("assembly_evaluation_count", 64),
                         ("forward_evaluation_count", 512), ("motor_result_count", 8)):
        _require(type(actual[key]) is int and 0 <= actual[key] <= maximum)
    _exact(actual["request_sha256"], sha256_record(request))
    _exact(actual["evaluation_sha256"], sha256_record({
        key: value for key, value in actual.items() if key != "evaluation_sha256"}))
    outputs = actual["outputs"]
    _require(type(outputs) is dict and outputs.keys() == {"solve", "power_state", "power"})
    solved, supplied = outputs["solve"], request["solve"]
    _require(point._guard_solve_success(solved, supplied) is None)
    _exact(actual["solve_result_count"], 1)
    _exact(actual["assembly_evaluation_count"], solved["evaluation_count"])
    _exact(actual["forward_evaluation_count"], solved["rotor_evaluation_count"])
    solve_digest = sha256_record(solved)
    stages = [{"stage": "solve", "inputs": supplied, "inputs_sha256": sha256_record(supplied),
               "result_sha256": solve_digest}]
    transfers = []
    if solved["outputs"]["outcome"] != "RESIDUAL_MET":
        _exact(outputs["power_state"], "NOT_RUN_RESIDUAL_UNMET")
        _exact(outputs["power"], None)
        _exact(actual["motor_result_count"], 0)
        _exact(actual["output_units"], _POINT_CATALOG["output_field_units_residual_unmet"])
        _exact(actual["stages"], stages)
        _exact(actual["transfers"], [])
        return
    _exact(outputs["power_state"], "COMPUTED")
    _exact(actual["output_units"], _POINT_CATALOG["output_field_units"])
    power = outputs["power"]
    _require(type(power) is dict and power.keys() == (
        set(_POWER_FIELDS.values()) | {"motors", "all_motors_within_declared_limits"}))
    rows = power["motors"]
    rotors = solved["outputs"]["actual_assembly_result"]["outputs"]["rotors"]
    _require(type(rows) is list and len(rows) == len(request["motors"]) == len(rotors))
    _exact(actual["motor_result_count"], len(rows))
    for index, (row, entry, rotor) in enumerate(zip(rows, request["motors"], rotors, strict=True)):
        _require(type(row) is dict and row.keys() == {
            "id", "actual_motor_request", "actual_motor_result", "allocated_heat_w", "unallocated_loss_w"})
        _exact(row["id"], entry["id"])
        forward = rotor["actual_forward_result"]["outputs"]
        operating = {"angular_speed_rad_s": rotor["actual_forward_request"]["angular_speed_rad_s"],
                     "shaft_torque_nm": forward["shaft_torque_nm"]}
        injected = {"evaluation": dc.EVALUATION, "parameters": entry["parameters"],
                    "declared_limits": entry["declared_limits"], "operating_point": operating}
        actual_request, motor = row["actual_motor_request"], row["actual_motor_result"]
        _json_walk(actual_request, _POINT_CATALOG["limits"]["motor_input_json"])
        _exact(actual_request, injected)
        _json_walk(motor, _POINT_CATALOG["limits"]["motor_output_json"])
        _require(point.power._validate_motor(motor, actual_request) is None)
        values = motor["outputs"]
        _require(math.isclose(values["shaft_power_w"], forward["shaft_power_w"],
                              rel_tol=1e-12, abs_tol=1e-12))
        allocated = th.checked_product(values["total_loss_w"], entry["heat_fraction_of_motor_loss"])
        unallocated = th.checked_difference(values["total_loss_w"], allocated)
        _require(0 <= allocated <= values["total_loss_w"] and unallocated >= 0)
        _exact(row["allocated_heat_w"], allocated)
        _exact(row["unallocated_loss_w"], unallocated)
        stage, request_digest = "motor:" + entry["id"], sha256_record(actual_request)
        stages.append({"stage": stage, "inputs": actual_request,
                       "inputs_sha256": request_digest, "result_sha256": sha256_record(motor)})
        base = f"outputs.actual_assembly_result.outputs.rotors[{index}]."
        for field, producer, unit in (
            ("angular_speed_rad_s", "actual_forward_request.angular_speed_rad_s", "rad/s"),
            ("shaft_torque_nm", "actual_forward_result.outputs.shaft_torque_nm", "N*m"),
        ):
            transfers.append({"from_stage": "solve", "from_field": base + producer,
                              "to_stage": stage, "to_field": "operating_point." + field,
                              "value": operating[field], "unit": unit,
                              "producer_result_sha256": solve_digest,
                              "consumer_request_sha256": request_digest})
    totals = {}
    for name, field in (("total_shaft_power_w", "shaft_power_w"),
                        ("total_motor_electrical_power_w", "electrical_power_w"),
                        ("total_motor_loss_w", "total_loss_w")):
        totals[name] = dc._power_sum([r["actual_motor_result"]["outputs"][field] for r in rows])
    totals["total_allocated_motor_heat_w"] = dc._power_sum([r["allocated_heat_w"] for r in rows])
    totals["total_unallocated_motor_loss_w"] = dc._power_sum([r["unallocated_loss_w"] for r in rows])
    aux = request["auxiliary"]
    totals["auxiliary_electrical_power_w"] = dc._normal(aux["power_w"])
    totals["auxiliary_heat_w"] = th.checked_product(aux["power_w"], aux["heat_fraction"])
    _require(0 <= totals["auxiliary_heat_w"] <= totals["auxiliary_electrical_power_w"])
    totals["total_electrical_power_w"] = dc._power_sum([
        totals["total_motor_electrical_power_w"], totals["auxiliary_electrical_power_w"]])
    totals["total_heat_w"] = dc._power_sum([
        totals["total_allocated_motor_heat_w"], totals["auxiliary_heat_w"]])
    totals["all_motors_within_declared_limits"] = all(
        r["actual_motor_result"]["outputs"]["declared_limit_status"] == "WITHIN_DECLARED_LIMITS"
        for r in rows)
    for key, expected in totals.items():
        _exact(power[key], expected)
    _exact(actual["stages"], stages)
    _exact(actual["transfers"], transfers)


def _energy_units():
    joules = dict.fromkeys(_POWER_FIELDS, "J")
    return {
        "segments": {"segment_id": "label", "start_time_s": "s", "end_time_s": "s",
                     "energy_j": joules, "cumulative_energy_j": deepcopy(joules)},
        "elapsed_s": "s", "totals_j": deepcopy(joules),
        "totals_wh": dict.fromkeys(_POWER_FIELDS, "Wh"),
        "all_motors_within_declared_limits": "1",
    }


def _point_row_units(actual_units):
    return {"segment_id": "label", "duration_s": "s",
            "actual_power_result": {"outputs": deepcopy(actual_units)}}


def evaluate_tabulated_solved_dc_energy(request):
    """Evaluate each point once, admit its full snapshot, then integrate all met points."""
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
        return _seal(_response("EXECUTION_FAILED", [_REASONS["admission"]]))
    digest, counts, boundary = None, dict.fromkeys(_COUNTS, 0), "execution"
    try:
        digest = sha256_record(snapshot)
        points, stages, point_units = [], [], []
        all_met = True
        for segment in snapshot["segments"]:
            supplied = segment["power_request"]
            boundary = "point"
            retained = _snapshot(point.evaluate_tabulated_solved_dc_power(deepcopy(supplied)),
                                 "point_output_json")
            _require(_guard_point_success(retained, supplied) is None)
            # Accept no partial solve/motor counts from a point whose full guard failed.
            counts["point_result_count"] += 1
            for key in _COUNTS:
                if key != "point_result_count":
                    counts[key] += retained[key]
            boundary = "execution"
            points.append({"segment_id": segment["id"], "duration_s": segment["duration_s"],
                           "actual_power_result": retained})
            stage = "segment:" + segment["id"]
            stages.append({"stage": stage, "inputs": deepcopy(supplied),
                           "inputs_sha256": sha256_record(supplied),
                           "result_sha256": sha256_record(retained)})
            point_units.append(_point_row_units(retained["output_units"]))
            all_met = all_met and retained["outputs"]["power_state"] == "COMPUTED"
        result = _response("COMPUTED_EXPERIMENTAL", [], digest, counts)
        result.update(diagnostics_complete=True, stages=stages,
                      outputs={"points": points, "energy_state": "NOT_RUN_RESIDUAL_UNMET",
                               "energy": None},
                      output_units={"points": point_units, "energy_state": "label",
                                    "energy": "not_applicable"})
        if not all_met:
            return _seal(result)
        rows, transfers, durations = [], [], []
        energies = {key: [] for key in _POWER_FIELDS}
        elapsed, cumulative, all_within = 0.0, dict.fromkeys(_POWER_FIELDS, 0.0), True
        for index, row in enumerate(points):
            actual = row["actual_power_result"]
            power, duration, start = actual["outputs"]["power"], row["duration_s"], elapsed
            durations.append(duration)
            elapsed = dc._power_sum(durations)
            _require(elapsed > start)
            energy = {key: th.checked_product(power[field], duration)
                      for key, field in _POWER_FIELDS.items()}
            previous = cumulative
            for key in _POWER_FIELDS:
                energies[key].append(energy[key])
            cumulative = {key: dc._power_sum(values) for key, values in energies.items()}
            for key in _POWER_FIELDS:
                _require(energy[key] == 0 or cumulative[key] > previous[key])
            rows.append({"segment_id": row["segment_id"], "start_time_s": start,
                         "end_time_s": elapsed, "energy_j": energy,
                         "cumulative_energy_j": cumulative})
            all_within = all_within and power["all_motors_within_declared_limits"]
            for key, field in _POWER_FIELDS.items():
                transfers.append({
                    "from_stage": stages[index]["stage"], "from_field": "outputs.power." + field,
                    "to_stage": "energy", "to_field": f"outputs.energy.segments[{index}].energy_j.{key}",
                    "value": power[field], "unit": "W",
                    "producer_result_sha256": stages[index]["result_sha256"],
                    "consumer_request_sha256": digest,
                })
        totals = {key: dc._power_sum(values) for key, values in energies.items()}
        energy = {"segments": rows, "elapsed_s": elapsed, "totals_j": totals,
                  "totals_wh": {key: th.checked_quotient(value, 3600) for key, value in totals.items()},
                  "all_motors_within_declared_limits": all_within}
        result["outputs"].update(energy_state="COMPUTED", energy=energy)
        result["output_units"]["energy"] = _energy_units()
        result["transfers"] = transfers
        return _seal(result)
    except Exception:  # noqa: BLE001 -- atomic ordinary failures; BaseException propagates.
        return _seal(_response("EXECUTION_FAILED", [_REASONS[boundary]], digest, counts))


def tabulated_solved_dc_energy_catalog():
    """Fresh private policy and both point unit variants; no component calls."""
    return {
        **_response("RESEARCH_ONLY", []), "required_fields": list(_ROOT), "defaults": {},
        "segment_fields": list(_SEGMENT), "point_catalog": deepcopy(_POINT_CATALOG),
        "input_units": {"evaluation": "label", "segments": {
            "id": "label", "duration_s": "s", "power_request": deepcopy(_POINT_CATALOG["input_units"])}},
        "output_field_units": {
            "points": {"layout": "ordered parallel list, one unit row per actual point",
                       "row_variants": {
                           "COMPUTED": _point_row_units(_POINT_CATALOG["output_field_units"]),
                           "NOT_RUN_RESIDUAL_UNMET": _point_row_units(
                               _POINT_CATALOG["output_field_units_residual_unmet"])}},
            "energy_state": "label", "energy": _energy_units()},
        "output_field_units_residual_unmet": {"energy": "not_applicable"},
        "count_units": dict.fromkeys(_COUNTS, "1"),
        "energy_states": ["COMPUTED", "NOT_RUN_RESIDUAL_UNMET"],
        "power_fields": deepcopy(_POWER_FIELDS),
        "request_contract": {
            "shape": "Exact evaluation,segments; 1..8 ordered exact id,duration_s,power_request rows; no defaults.",
            "identifiers": "Unique nonblank builtin strings <=1992 characters, leaving segment: within 2000.",
            "duration": "Positive finite normal V116 builtin int/float; retained native in points.",
            "preflight": "Every whole V127 input walk and preflight, all motors/auxiliary, before any call.",
            "work": "Sum solve.max_evaluations * sum rotor annuli <=65536; each V126 bound separately.",
            "budgets": "Root and each point input/output use independent unchanged private catalog budgets.",
        },
        "bindings": {
            "points": "Actual V127 once per segment, immediate full bounded detached snapshot, pure full success guard.",
            "solve": "Full actual solve admitted by V127._guard_solve_success, without evaluation or model reruns.",
            "motor": "Selected native omega/Q, full request/ID/hash/V116 motor guard, shaft rel/abs 1e-12, allocations and nine totals.",
            "stages": "One segment stage per admitted point, full actual power request, request/full-result digests; full results only in points.",
            "transfers": "Nine actual W scalars per segment from outputs.power fields to outputs.energy.segments[i].energy_j keys; full point digest and root request hash. Duration binds through root request.",
            "point_units": "Literal ordered parallel list of actual point unit rows, including null-power not_applicable variant.",
        },
        "formulas": {
            "time": "Ordered dc._power_sum of every prefix of original native durations; strictly increasing.",
            "energy": "checked_product(actual watts,native duration); ordered dc._power_sum of individual segment energies for every prefix and total.",
            "resolution": "Every positive energy increment must increase that key's prefix; zero may stay unchanged. Accepted DC sum also rejects absorption of a positive prior total.",
            "wh": "checked_quotient(total joules,3600); auxiliary is included once through guarded actual power.",
        },
        "response_contract": {
            "unmet": "Evaluate all points even after residual unmet; computed root with full points, energy_state NOT_RUN_RESIDUAL_UNMET, energy null, no elapsed or energy transfers; no invalid/global infeasibility claim.",
            "computed": "Only after all points pass and all residuals are met: energy rows, elapsed, nine J/Wh totals and declaration-limit boolean; no duplicated full points in energy.",
            "counts": "Fully guarded point prefix only; point<=8 solve<=8 assembly<=512 forward<=4096 motor<=64, never attempts.",
            "failure": "Noncomputed/malformed/exception point gives only POINT_BOUNDARY_FAILED; earlier fully guarded counts survive, outputs/units/stages/transfers empty and diagnostics false.",
            "hashes": "Bound before copy/hash/equality; root request hash and entire response hash omitting evaluation_sha256; bounded before and after seal.",
            "exceptions": "Ordinary faults sanitized; BaseException propagates.",
        },
        "status_reason_matrix": {
            "COMPUTED_EXPERIMENTAL": [], "SOLVER_UNSUPPORTED": [_REASONS["unsupported"]],
            "MODEL_INAPPLICABLE": [_REASONS["invalid"]],
            "EXECUTION_FAILED": [_REASONS[k] for k in ("admission", "point", "execution")],
        },
    }
