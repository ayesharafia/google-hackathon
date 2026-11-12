from copy import deepcopy

from .graph_mission import (
    _normal,
    evaluate_graph_mission,
)
from .graph_mission import (
    _preflight as _energy_preflight,
)
from .graph_mission import (
    _require as _energy_require,
)
from .model_graph_execution import _json
from .multi_rotor_mission import (
    EVALUATION as MULTI_ROTOR_EVALUATION,
)
from .multi_rotor_mission import (
    _preflight as _multi_energy_preflight,
)
from .multi_rotor_mission import (
    evaluate_multi_rotor_mission,
)
from .provenance import sha256_record
from .thermal import MODEL_ID as THERMAL_MODEL_ID
from .thermal import screen_thermal

EVALUATION = "constant_condition_electrothermal_mission_experimental"


def _require(condition, message=None):
    _energy_require(condition)


def _preflight(request):
    _json(request, budget=49152)
    snapshot = deepcopy(request)
    _require(
        type(snapshot) is dict
        and set(snapshot) == {"evaluation", "energy_mission", "thermal_body", "thermal_segments"},
        "Invalid electrothermal mission fields",
    )
    _require(snapshot["evaluation"] == EVALUATION, "Invalid evaluation")
    if (
        type(snapshot["energy_mission"]) is dict
        and snapshot["energy_mission"].get("evaluation") == MULTI_ROTOR_EVALUATION
    ):
        _multi_energy_preflight(snapshot["energy_mission"])
    else:
        _energy_preflight(snapshot["energy_mission"])

    def scalar(value, name, lower, upper=None, positive=False):
        _require(
            type(value) in (int, float) and _normal(value) is not None,
            name + " must be a finite normal builtin number",
        )
        _require(value > lower if positive else value >= lower, name + " is below its allowed range")
        _require(upper is None or value <= upper, name + " is above its allowed range")

    def source(value, name):
        _require(
            type(value) is str and bool(value.strip()) and len(value) <= 2000,
            name + " must be a nonblank string of at most 2000 characters",
        )

    body = snapshot["thermal_body"]
    _require(
        type(body) is dict
        and set(body)
        == {
            "mass_kg",
            "specific_heat_j_kg_k",
            "initial_temperature_k",
            "lumped_biot_number",
            "property_source",
        },
        "Invalid thermal_body fields",
    )
    for key in ("mass_kg", "specific_heat_j_kg_k", "initial_temperature_k"):
        scalar(body[key], key, 0, positive=True)
    scalar(body["lumped_biot_number"], "lumped_biot_number", 0, 0.1)
    source(body["property_source"], "property_source")
    segments = snapshot["thermal_segments"]
    energy_segments = snapshot["energy_mission"]["segments"]
    _require(
        type(segments) is list and len(segments) == len(energy_segments),
        "thermal_segments must match the energy segment count",
    )
    for segment, energy_segment in zip(segments, energy_segments, strict=True):
        _require(
            type(segment) is dict
            and set(segment)
            == {
                "id",
                "ambient_temperature_k",
                "conductance_w_k",
                "heat_fraction_of_electrical_input",
                "heat_source",
            },
            "Invalid thermal segment fields",
        )
        _require(segment["id"] == energy_segment["id"], "Thermal segment IDs must match energy segment order")
        scalar(segment["ambient_temperature_k"], "ambient_temperature_k", 0, positive=True)
        scalar(segment["conductance_w_k"], "conductance_w_k", 0)
        scalar(segment["heat_fraction_of_electrical_input"], "heat_fraction_of_electrical_input", 0, 1)
        source(segment["heat_source"], "heat_source")
    return snapshot


def _thermal_request(snapshot, energy):
    _json(energy, budget=49152, items=2048)
    _require(type(energy) is dict)
    _require(energy.get("status") == "COMPUTED_EXPERIMENTAL")
    _require(energy.get("diagnostics_complete") is True)
    mission = snapshot["energy_mission"]
    _require(energy.get("evaluation") == mission["evaluation"])
    _require(energy.get("evidence_level") == "unverified")
    for key in ("physical_validation", "numerical_qualification", "runtime_identity"):
        _require(energy.get(key) == "NOT_ESTABLISHED")
    _require("feasibility" in energy and energy["feasibility"] is None)
    _require("aircraft_status" in energy and energy["aircraft_status"] is None)
    _require(energy.get("request_sha256") == sha256_record(mission))
    rows = energy.get("segments")
    declared = mission["segments"]
    thermal = snapshot["thermal_segments"]
    _require(type(rows) is list and len(rows) == len(declared) == len(thermal))
    request = {"evaluation": "lumped_thermal_screening", **deepcopy(snapshot["thermal_body"]), "segments": []}
    transfers = []
    for t, row, d in zip(thermal, rows, declared, strict=True):
        _require(type(row) is dict and row.get("segment_id") == d["id"])
        duration, power = row.get("duration_s"), row.get("electrical_power_w")
        _require(type(duration) in (int, float) and _normal(duration) == d["duration_s"])
        _require(type(power) in (int, float) and _normal(power) >= 0)
        fraction = t["heat_fraction_of_electrical_input"]
        heat = _normal(power * fraction)
        _require((fraction == 0 or power == 0 or heat > 0) and heat <= power)
        request["segments"].append(
            {
                "duration_s": d["duration_s"],
                "ambient_temperature_k": t["ambient_temperature_k"],
                "heat_input_w": heat,
                "conductance_w_k": t["conductance_w_k"],
            }
        )
        transfers.append(
            {
                "segment_id": d["id"],
                "electrical_power_w": power,
                "heat_fraction_of_electrical_input": fraction,
                "heat_input_w": heat,
                "heat_source": t["heat_source"],
            }
        )
    out = energy.get("outputs")
    units = energy.get("output_units")
    expected_units = {
        "elapsed_s": "s",
        "total_energy_j": "J",
        "total_energy_wh": "Wh",
        "held_reserve_j": "J",
        "mission_budget_j": "J",
        "remaining_budget_j": "J",
        "budget_status": "not_applicable",
    }
    if type(out) is not dict or out.keys() != expected_units.keys():
        raise ValueError("Invalid admitted energy outputs")
    if type(units) is not dict or units != expected_units:
        raise ValueError("Invalid admitted energy output units")
    for key in expected_units:
        if key == "budget_status":
            continue
        value = out[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value != _normal(value):
            raise ValueError(f"Invalid admitted energy output: {key}")
    total = _normal(
        math.fsum(
            row["electrical_power_w"] * declared["duration_s"]
            for row, declared in zip(rows, mission["segments"], strict=True)
        )
    )
    budget = _normal(mission["usable_energy_j"] * (1 - mission["reserve_fraction"]))
    held = _normal(mission["usable_energy_j"] - budget)
    remaining = budget - total
    expected_status = "WITHIN_DECLARED_ENERGY" if remaining >= 0 else "EXCEEDS_DECLARED_ENERGY"
    if (
        out["total_energy_j"] != total
        or out["total_energy_wh"] != total / 3600
        or out["mission_budget_j"] != budget
        or out["held_reserve_j"] != held
        or out["remaining_budget_j"] != remaining
        or out["elapsed_s"] != math.fsum(declared["duration_s"] for declared in mission["segments"])
        or type(out["budget_status"]) is not str
        or out["budget_status"] != expected_status
    ):
        raise ValueError("Admitted energy totals do not match the mission")
    return request, transfers


import math


def _validated_thermal(raw, request):
    check = _require
    _json(raw, budget=49152, items=2048)
    check(
        type(raw) is dict
        and set(raw)
        == {
            "model_id",
            "status",
            "evidence_level",
            "aircraft_status",
            "feasibility",
            "outputs",
            "output_units",
            "limitations",
            "reasons",
            "sources",
        }
    )
    check(raw["model_id"] == THERMAL_MODEL_ID and raw["status"] == "SCREENING_COMPUTED")
    check(raw["evidence_level"] == "unverified")
    check(raw["aircraft_status"] is None and raw["feasibility"] is None)
    check(type(raw["reasons"]) is list and raw["reasons"] == [])
    check(type(raw["limitations"]) is list and type(raw["sources"]) is list)
    subunits = {
        "index": "1",
        "duration_s": "s",
        "cumulative_elapsed_s": "s",
        "start_temperature_k": "K",
        "end_temperature_k": "K",
        "ambient_temperature_k": "K",
        "heat_input_j": "J",
        "thermal_storage_change_j": "J",
        "convective_exchange_j": "J",
        "energy_balance_residual_j": "J",
    }
    totals = {
        "total_heat_input_j": "heat_input_j",
        "total_convective_exchange_j": "convective_exchange_j",
        "total_storage_change_j": "thermal_storage_change_j",
    }
    units = dict(
        segments=subunits,
        elapsed_s="s",
        final_temperature_k="K",
        maximum_temperature_k="K",
        **{k: "J" for k in totals},
        total_energy_balance_residual_j="J",
    )
    out, actual_units = raw["outputs"], raw["output_units"]
    check(type(out) is dict and set(out) == set(units))
    check(type(actual_units) is dict and set(actual_units) == set(units))
    check(type(actual_units["segments"]) is dict and actual_units == units)
    rows = out["segments"]
    check(type(rows) is list and len(rows) == len(request["segments"]) and bool(rows))
    elapsed, previous = 0.0, request["initial_temperature_k"]
    temperatures = [previous]
    for i, (row, segment) in enumerate(zip(rows, request["segments"], strict=True)):
        check(type(row) is dict and set(row) == set(subunits))
        check(type(row["index"]) is int and row["index"] == i)
        for key in subunits.keys() - {"index"}:
            check(type(row[key]) in (int, float) and _normal(row[key]) is not None)
        check(
            all(
                row[k] > 0
                for k in (
                    "duration_s",
                    "cumulative_elapsed_s",
                    "start_temperature_k",
                    "end_temperature_k",
                    "ambient_temperature_k",
                )
            )
        )
        check(
            row["duration_s"] == segment["duration_s"]
            and row["ambient_temperature_k"] == segment["ambient_temperature_k"]
        )
        elapsed += row["duration_s"]
        if row["heat_input_j"] != segment["heat_input_w"] * segment["duration_s"]:
            raise ValueError("Thermal row heat input does not match the segment")
        if (
            row["energy_balance_residual_j"]
            != row["heat_input_j"] - row["thermal_storage_change_j"] - row["convective_exchange_j"]
        ):
            raise ValueError("Thermal row energy balance residual is inconsistent")
        check(row["cumulative_elapsed_s"] == elapsed and row["start_temperature_k"] == previous)
        previous = row["end_temperature_k"]
        temperatures.append(previous)
    for key in out.keys() - {"segments"}:
        check(type(out[key]) in (int, float) and _normal(out[key]) is not None)
    check(out["final_temperature_k"] == previous and out["maximum_temperature_k"] == max(temperatures))
    check(out["elapsed_s"] == elapsed == rows[-1]["cumulative_elapsed_s"])
    for total, field in totals.items():
        check(out[total] == math.fsum(row[field] for row in rows))
    check(
        out["total_energy_balance_residual_j"]
        == out["total_heat_input_j"] - out["total_storage_change_j"] - out["total_convective_exchange_j"]
    )
    return raw


def evaluate_electrothermal_mission(request):
    result = {
        "evaluation": EVALUATION,
        "status": "GRAPH_INVALID",
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "diagnostics_complete": False,
        "reasons": [],
        "stages": [],
        "transfers": [],
        "outputs": {},
        "output_units": {},
        "limitations": [
            "Constant-condition energy-to-lumped-heat composition; no dynamic flight or mass closure.",
            "Heat fraction, ambient and conductance are caller declarations, not inferred from propulsive loss.",
            "No battery chemistry, radiation, hotspots, threshold/safety or aircraft feasibility.",
            "Data hashes do not establish validation or runtime identity.",
        ],
    }
    try:
        snapshot = _preflight(request)
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError, KeyError, ZeroDivisionError):
        result["reasons"] = ["Invalid electrothermal mission request"]
        return deepcopy(result)
    result["request_sha256"] = sha256_record(snapshot)
    try:
        if (
            type(snapshot["energy_mission"]) is dict
            and snapshot["energy_mission"].get("evaluation") == MULTI_ROTOR_EVALUATION
        ):
            energy = evaluate_multi_rotor_mission(deepcopy(snapshot["energy_mission"]))
        else:
            energy = evaluate_graph_mission(deepcopy(snapshot["energy_mission"]))
        thermalreq, transfers = _thermal_request(snapshot, energy)
        result["stages"].append(
            {
                "stage_id": "energy",
                "request_sha256": sha256_record(snapshot["energy_mission"]),
                "result_sha256": sha256_record(energy),
            }
        )
        thermal = _validated_thermal(screen_thermal(deepcopy(thermalreq)), thermalreq)
        result["stages"].append(
            {
                "stage_id": "thermal",
                "request_sha256": sha256_record(thermalreq),
                "result_sha256": sha256_record(thermal),
            }
        )
        result.update(
            outputs={"energy": deepcopy(energy["outputs"]), "thermal": deepcopy(thermal["outputs"])},
            output_units={
                "energy": deepcopy(energy["output_units"]),
                "thermal": deepcopy(thermal["output_units"]),
            },
            transfers=deepcopy(transfers),
            status="COMPUTED_EXPERIMENTAL",
            diagnostics_complete=True,
        )
    except Exception:  # noqa: BLE001
        result.update(
            status="EXECUTION_FAILED",
            diagnostics_complete=False,
            reasons=["Electrothermal mission execution failed"],
            outputs={},
            output_units={},
            transfers=[],
        )
    return deepcopy(result)
