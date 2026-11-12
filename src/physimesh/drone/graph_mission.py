import math
import sys
from copy import deepcopy

from .model_graph_execution import _json
from .provenance import sha256_record
from .reference_air_graph import (
    EVALUATION as GRAPH_EVALUATION,
)
from .reference_air_graph import (
    _validate,
    evaluate_reference_air_graph,
)

EVALUATION = "constant_condition_graph_mission_experimental"


def _require(condition):
    if not condition:
        raise ValueError("invalid graph mission request")


def _num(v):
    _require(type(v) in (int, float))
    try:
        finite = math.isfinite(v)
    except OverflowError:
        finite = False
    _require(finite)
    return v


def _normal(v):
    _num(v)
    _require(v == 0 or abs(v) >= sys.float_info.min)
    return v


def _preflight(request):
    _json(request, budget=32768)
    snapshot = deepcopy(request)
    _require(
        type(snapshot) is dict
        and set(snapshot)
        == {
            "evaluation",
            "usable_energy_j",
            "reserve_fraction",
            "segments",
        }
    )
    _require(snapshot["evaluation"] == EVALUATION)
    _require(_normal(snapshot["usable_energy_j"]) > 0)
    _require(0 <= _num(snapshot["reserve_fraction"]) < 1)
    segments = snapshot["segments"]
    _require(type(segments) is list and 1 <= len(segments) <= 32)
    ids, node_count, annuli_count = set(), 0, 0
    allowed = {
        ("isolated_hover_bemt_experimental", "shaft_power_w"),
        ("fixed_wing_aerodynamic_screening", "drag_power_w"),
    }
    for segment in segments:
        _require(
            type(segment) is dict
            and set(segment)
            == {
                "id",
                "duration_s",
                "graph",
                "power_node",
                "power_port",
                "conversion_efficiency",
                "auxiliary_power_w",
                "conversion_source",
            }
        )
        sid = segment["id"]
        _require(type(sid) is str and bool(sid.strip()) and len(sid) <= 64)
        _require(sid not in ids)
        ids.add(sid)
        _require(_normal(segment["duration_s"]) > 0)
        _require(0 < _normal(segment["conversion_efficiency"]) <= 1)
        _require(_normal(segment["auxiliary_power_w"]) >= 0)
        source = segment["conversion_source"]
        _require(type(source) is str and bool(source.strip()) and len(source) <= 2000)
        graph = segment["graph"]
        _require(type(graph) is dict and graph.get("evaluation") == GRAPH_EVALUATION)
        _validate(graph)
        node_id, port = segment["power_node"], segment["power_port"]
        _require(type(node_id) is str and type(port) is str)
        _require(graph.get("targets") == [{"node": node_id, "port": port}])
        matches = [node for node in graph["nodes"] if node["id"] == node_id]
        _require(len(matches) == 1 and (matches[0]["model"], port) in allowed)
        node_count += len(graph["nodes"])
        _require(node_count <= 128)
        for node in graph["nodes"]:
            if node["model"] == "isolated_hover_bemt_experimental":
                annuli = node.get("inputs", {}).get("annuli", 0)
                _require(type(annuli) is int and annuli >= 0)
                annuli_count += annuli
                _require(annuli_count <= 8192)
    return snapshot


def _run_segment(segment):
    result = evaluate_reference_air_graph(deepcopy(segment["graph"]))
    _require(type(result) is dict)
    _require(result.get("status") == "COMPUTED_EXPERIMENTAL")
    _require(result.get("diagnostics_complete") is True)
    _require(result.get("evaluation") == GRAPH_EVALUATION)
    _require(result.get("evidence_level") == "unverified")
    _require(type(result.get("reasons")) is list and result["reasons"] == [])
    _require(result.get("request_sha256") == sha256_record(segment["graph"]))
    for name in ("physical_validation", "numerical_qualification", "runtime_identity"):
        _require(result.get(name) == "NOT_ESTABLISHED")
    for name in ("feasibility", "aircraft_status"):
        _require(name in result and result[name] is None)
    n, p = segment["power_node"], segment["power_port"]
    outputs = result.get("outputs")
    _require(type(outputs) is dict)
    _require(outputs.keys() == {n})
    _require(type(outputs[n]) is dict)
    _require(outputs[n].keys() == {p})
    units = result.get("output_units")
    _require(type(units) is dict)
    _require(units.keys() == {n})
    _require(type(units[n]) is dict)
    _require(units[n].keys() == {p})
    _require(units[n][p] == "W")
    power = _normal(result["outputs"][n][p])
    _require(power >= 0)
    converted = _normal(power / segment["conversion_efficiency"])
    _require(power == 0 or converted > 0)
    aux = segment["auxiliary_power_w"]
    electrical = _normal(converted + aux)
    _require(aux == 0 or electrical > converted)
    _require(converted == 0 or electrical > aux)
    energy = _normal(electrical * segment["duration_s"])
    _require(electrical == 0 or energy > 0)
    return result, power, electrical, energy


def evaluate_graph_mission(request):
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
        "segments": [],
        "outputs": {},
        "output_units": {},
        "limitations": [
            "Constant-condition segments only; no dynamics, force, mass, thermal or fuel-state closure.",
            "Efficiency, auxiliary power and usable energy are caller declarations, unverified.",
            "Energy budget status is not aircraft feasibility or airworthiness.",
            "Hashes identify data, not physical validation or runtime identity.",
        ],
    }
    try:
        snapshot = _preflight(request)
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError, KeyError, ZeroDivisionError):
        result["reasons"].append("Invalid request.")
        return result
    result["request_sha256"] = sha256_record(snapshot)
    try:
        usable = snapshot["usable_energy_j"]
        reserve = snapshot["reserve_fraction"]
        budget = _normal(usable * (1 - reserve))
        held = _normal(usable - budget)
        _require(budget > 0)
        _require(reserve == 0 or (held > 0 and budget < usable))
        energies, durations = [], []
        consumed = elapsed = 0.0
        for segment in snapshot["segments"]:
            raw, power, electrical, energy = _run_segment(segment)
            energies.append(energy)
            durations.append(segment["duration_s"])
            newconsumed = _normal(math.fsum(energies))
            newelapsed = _normal(math.fsum(durations))
            _require(newelapsed > elapsed and (energy == 0 or newconsumed > consumed))
            consumed, elapsed = newconsumed, newelapsed
            remaining = _normal(budget - consumed)
            result["segments"].append(
                {
                    "segment_id": segment["id"],
                    "duration_s": segment["duration_s"],
                    "power_node": segment["power_node"],
                    "power_port": segment["power_port"],
                    "component_power_w": power,
                    "electrical_power_w": electrical,
                    "segment_energy_j": energy,
                    "cumulative_energy_j": consumed,
                    "remaining_budget_j": remaining,
                    "graph_request_sha256": sha256_record(segment["graph"]),
                    "graph_result_sha256": sha256_record(raw),
                }
            )
        wh = _normal(consumed / 3600)
        _require(consumed == 0 or wh > 0)
        result["outputs"] = {
            "elapsed_s": elapsed,
            "total_energy_j": consumed,
            "total_energy_wh": wh,
            "held_reserve_j": held,
            "mission_budget_j": budget,
            "remaining_budget_j": remaining,
            "budget_status": "WITHIN_DECLARED_ENERGY" if remaining >= 0 else "EXCEEDS_DECLARED_ENERGY",
        }
        result["output_units"] = {
            "elapsed_s": "s",
            "total_energy_j": "J",
            "total_energy_wh": "Wh",
            "held_reserve_j": "J",
            "mission_budget_j": "J",
            "remaining_budget_j": "J",
            "budget_status": "not_applicable",
        }
        result["status"] = "COMPUTED_EXPERIMENTAL"
        result["diagnostics_complete"] = True
    except Exception:  # noqa: BLE001 - contain graph/component failures without partial final outputs
        result["status"] = "EXECUTION_FAILED"
        result["reasons"] = ["Graph mission execution refused."]
        result["outputs"] = {}
        result["output_units"] = {}
    return deepcopy(result)
