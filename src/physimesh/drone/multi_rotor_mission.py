"""Frozen-condition isolated-rotor energy sums; no aircraft qualification."""

import math
from copy import deepcopy

from .graph_mission import _normal, _num, _require
from .model_graph_execution import _json
from .provenance import sha256_record
from .reference_air_graph import EVALUATION as GRAPH_EVALUATION
from .reference_air_graph import _validate, evaluate_reference_air_graph

EVALUATION = "constant_condition_multi_rotor_mission_experimental"


def _preflight(request):
    _json(request, budget=32768)
    pending = [request]
    while pending:
        value = pending.pop()
        _require(type(value) is not bool)
        if type(value) in (int, float):
            _normal(value)
        elif type(value) is dict:
            pending.extend(value.values())
        elif type(value) is list:
            pending.extend(value)
    snapshot = deepcopy(request)
    _require(type(snapshot) is dict and snapshot.keys() == {
        "evaluation", "usable_energy_j", "reserve_fraction", "segments"})
    _require(snapshot["evaluation"] == EVALUATION)
    _require(_normal(snapshot["usable_energy_j"]) > 0)
    _require(0 <= _num(snapshot["reserve_fraction"]) < 1)
    segments = snapshot["segments"]
    _require(type(segments) is list and 1 <= len(segments) <= 32)
    ids, node_count, annuli_count = set(), 0, 0
    for segment in segments:
        _require(type(segment) is dict and segment.keys() == {
            "id", "duration_s", "graph", "rotors", "auxiliary_power_w"})
        sid = segment["id"]
        _require(type(sid) is str and bool(sid.strip()) and len(sid) <= 64 and sid not in ids)
        ids.add(sid)
        _require(_normal(segment["duration_s"]) > 0)
        _require(_normal(segment["auxiliary_power_w"]) >= 0)
        rotors, graph = segment["rotors"], segment["graph"]
        _require(type(rotors) is list and 1 <= len(rotors) <= 15)
        _require(type(graph) is dict and graph.get("evaluation") == GRAPH_EVALUATION)
        _validate(graph)
        nodes = {node["id"]: node for node in graph["nodes"]}
        air = [node["id"] for node in graph["nodes"]
               if node["model"] == "reference_air_properties"]
        _require(len(air) == 1)
        seen, edges, targets = {air[0]}, set(), set()
        for rotor in rotors:
            _require(type(rotor) is dict and rotor.keys() == {
                "node", "conversion_efficiency", "conversion_source"})
            name = rotor["node"]
            _require(type(name) is str and name not in seen and name in nodes)
            node = nodes[name]
            _require(node["model"] == "isolated_hover_bemt_experimental")
            _require("density_kg_m3" not in node["inputs"])
            _require(0 < _normal(rotor["conversion_efficiency"]) <= 1)
            source = rotor["conversion_source"]
            _require(type(source) is str and bool(source.strip()) and len(source) <= 2000)
            seen.add(name)
            edges.add((air[0], "density_kg_m3", name, "density_kg_m3"))
            targets.add((name, "shaft_power_w"))
            annuli_count += node["inputs"]["annuli"]
        _require(set(nodes) == seen)
        _require(len(graph["connections"]) == len(rotors) and {
            (e["from_node"], e["from_port"], e["to_node"], e["to_port"])
            for e in graph["connections"]} == edges)
        _require({(t["node"], t["port"]) for t in graph["targets"]} == targets)
        node_count += len(nodes)
        _require(node_count <= 128 and annuli_count <= 8192)
    return snapshot


def _run_segment(segment):
    raw = evaluate_reference_air_graph(deepcopy(segment["graph"]))
    _json(raw, budget=262144, items=2048)
    _require(type(raw) is dict)
    _require(raw.get("evaluation") == GRAPH_EVALUATION)
    _require(raw.get("status") == "COMPUTED_EXPERIMENTAL")
    _require(raw.get("diagnostics_complete") is True)
    _require(raw.get("evidence_level") == "unverified")
    _require(type(raw.get("reasons")) is list and raw["reasons"] == [])
    _require(raw.get("request_sha256") == sha256_record(segment["graph"]))
    for name in ("physical_validation", "numerical_qualification", "runtime_identity"):
        _require(raw.get(name) == "NOT_ESTABLISHED")
    for name in ("feasibility", "aircraft_status"):
        _require(name in raw and raw[name] is None)
    names = {rotor["node"] for rotor in segment["rotors"]}
    outputs, units = raw.get("outputs"), raw.get("output_units")
    _require(type(outputs) is dict and outputs.keys() == names)
    _require(type(units) is dict and units.keys() == names)
    rows, powers, total = [], [], 0.0
    for rotor in segment["rotors"]:
        name, efficiency = rotor["node"], rotor["conversion_efficiency"]
        _require(type(outputs[name]) is dict and outputs[name].keys() == {"shaft_power_w"})
        _require(type(units[name]) is dict and units[name] == {"shaft_power_w": "W"})
        power = _normal(outputs[name]["shaft_power_w"])
        _require(power >= 0)
        converted = _normal(power / efficiency)
        _require(power == 0 or converted > 0)
        powers.append(converted)
        newtotal = _normal(math.fsum(powers))
        _require(converted == 0 or newtotal > total)
        _require(total == 0 or newtotal > converted)
        total = newtotal
        rows.append({"node": name, "shaft_power_w": power,
                     "conversion_efficiency": efficiency, "electrical_power_w": converted})
    aux = segment["auxiliary_power_w"]
    electrical = _normal(total + aux)
    _require(aux == 0 or electrical > total)
    _require(total == 0 or electrical > aux)
    energy = _normal(electrical * segment["duration_s"])
    _require(electrical == 0 or energy > 0)
    return raw, rows, electrical, energy


def evaluate_multi_rotor_mission(request):
    """Preflight the complete schedule, then execute each graph exactly once."""
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
            "Frozen-condition energy sums in declared chronological order; no schedule reordering.",
            "Isolated hover rotors only; no installed effects, rotor interference, trim or dynamics.",
            "No mass, fuel-state or thermal closure; no aircraft pass or feasibility verdict.",
            "Efficiency, auxiliary power and usable energy are unverified caller declarations.",
            "Literal source notes are not authority or evidence of physical qualification.",
            "Shared auxiliary power is added once per segment; reserve is held once per mission.",
            "Hashes identify data, not physical validation or runtime identity.",
        ],
    }
    try:
        snapshot = _preflight(request)
        result["request_sha256"] = sha256_record(snapshot)
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError, KeyError, ZeroDivisionError):
        result["reasons"] = ["Invalid multi-rotor mission request."]
        return result
    try:
        usable, reserve = snapshot["usable_energy_j"], snapshot["reserve_fraction"]
        budget = _normal(usable * (1 - reserve))
        held = _normal(usable - budget)
        _require(budget > 0)
        _require(reserve == 0 or (held > 0 and budget < usable))
        energies, durations = [], []
        consumed = elapsed = 0.0
        for segment in snapshot["segments"]:
            raw, rotors, electrical, energy = _run_segment(segment)
            energies.append(energy)
            durations.append(segment["duration_s"])
            newconsumed = _normal(math.fsum(energies))
            newelapsed = _normal(math.fsum(durations))
            _require(newelapsed > elapsed and (energy == 0 or newconsumed > consumed))
            consumed, elapsed = newconsumed, newelapsed
            remaining = _normal(budget - consumed)
            result["segments"].append({
                "segment_id": segment["id"],
                "duration_s": segment["duration_s"],
                "rotors": rotors,
                "auxiliary_power_w": segment["auxiliary_power_w"],
                "electrical_power_w": electrical,
                "segment_energy_j": energy,
                "cumulative_energy_j": consumed,
                "remaining_budget_j": remaining,
                "graph_request_sha256": sha256_record(segment["graph"]),
                "graph_result_sha256": sha256_record(raw),
            })
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
        result.update(status="COMPUTED_EXPERIMENTAL", diagnostics_complete=True)
    except Exception:  # noqa: BLE001 - refuse graph failures and unrepresentable arithmetic
        result.update(status="EXECUTION_FAILED", diagnostics_complete=False,
                      reasons=["Multi-rotor mission execution refused."],
                      segments=[], outputs={}, output_units={})
    return deepcopy(result)
