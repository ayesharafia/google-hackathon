"""Bounded, serial semantic DAG execution; no scientific qualification or M3 claim."""

import heapq
import math
import re
from copy import deepcopy
from dataclasses import fields

from .atmosphere_hover_workflow import _valid_hover
from .fixed_wing import screen_fixed_wing
from .hover_bemt_request import evaluate_hover_bemt
from .provenance import sha256_record
from .standard_atmosphere import EARTH_RADIUS_M, MODEL_ID, StandardAtmosphereState, standard_atmosphere

EVALUATION = "bounded_model_graph_experimental"
_ATM = "standard_atmosphere"
_HOVER = "isolated_hover_bemt_experimental"
_WING = "fixed_wing_aerodynamic_screening"
_IDS = {_ATM: MODEL_ID, _HOVER: "isolated_hover_small_angle_bemt_v1",
        _WING: "fixed_wing_supplied_coefficient_screening_v1"}
_ATM_IN = {"altitude_m": "m"}
_ATM_OUT = {"pressure_pa": "Pa", "temperature_k": "K", "density_kg_m3": "kg/m^3",
            "input_altitude_m": "m", "geopotential_altitude_m": "m"}
_HOVER_IN = {"radius_m": "m", "angular_speed_rad_s": "rad/s", "density_kg_m3": "kg/m^3",
             "blade_count": "1", "chord_m": "m", "lift_curve_slope_per_rad": "1/rad",
             "profile_drag_coefficient": "1", "pitch_tip_rad": "rad",
             "root_cutout_fraction": "1", "annuli": "1", "pitch_root_rad": "rad"}
_HOVER_OUT = {"thrust_coefficient": "1", "blade_thrust_coefficient": "1",
              "induced_power_coefficient": "1", "profile_power_coefficient": "1",
              "shaft_power_coefficient": "1", "thrust_n": "N", "shaft_power_w": "W",
              "shaft_torque_nm": "N*m", "thrust_balance_coefficient": "1",
              "max_local_balance_coefficient": "1", "annuli": "1"}
_WING_IN = {"density_kg_m3": "kg/m^3", "airspeed_m_s": "m/s", "wing_area_m2": "m^2",
            "span_m": "m", "characteristic_length_m": "m", "dynamic_viscosity_pa_s": "Pa*s",
            "speed_of_sound_m_s": "m/s", "lift_coefficient": "1",
            "zero_lift_drag_coefficient": "1", "span_efficiency": "1"}
_WING_OUT = {"dynamic_pressure_pa": "Pa", "aspect_ratio": "1", "induced_drag_coefficient": "1",
             "drag_coefficient": "1", "lift_n": "N", "drag_n": "N", "drag_power_w": "W",
             "reynolds_number": "1", "mach_number": "1"}
_INPUTS = {_ATM: _ATM_IN, _HOVER: _HOVER_IN, _WING: _WING_IN}
_OUTPUTS = {_ATM: _ATM_OUT, _HOVER: _HOVER_OUT, _WING: _WING_OUT}
_EXTRA = {_ATM: {"altitude_kind"},
          _HOVER: {"evaluation", "twist_law", "property_source", "applicability_declaration"},
          _WING: {"configuration", "evaluation", "coefficient_source", "coefficient_envelope"}}
_LITERAL = {"radius_m", "chord_m", "root_cutout_fraction", "pitch_tip_rad", "pitch_root_rad",
            "blade_count", "annuli", "wing_area_m2", "span_m", "characteristic_length_m"}
_BOUNDS = {"mach_min", "mach_max", "reynolds_min", "reynolds_max",
           "lift_coefficient_min", "lift_coefficient_max"}
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z", re.ASCII)


def adapter_metadata():
    """Fresh code-owned port declarations, never caller definitions or callables.

    Scalar means no spatial frame; integer counts cannot receive float transfers.
    Vector diagnostics are not graph ports. Geometry and declarations are literal.
    """
    return {model: {"model_id": _IDS[model], "inputs": {
        key: {"unit": unit, "frame": "scalar", "kind": "integer" if key in ("annuli", "blade_count") else "number",
              "connectable": key not in _LITERAL}
        for key, unit in _INPUTS[model].items()}, "outputs": {
            key: {"unit": unit, "frame": "scalar", "kind": "integer" if key == "annuli" else "number"}
            for key, unit in _OUTPUTS[model].items()},
        "literal_fields": sorted(_EXTRA[model] | (_LITERAL & _INPUTS[model].keys()))}
        for model in _IDS}


def _json(value, *, budget=4096, items=256):
    remaining = budget

    def visit(v, depth):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 10:
            raise ValueError("JSON depth or node budget exceeded")
        kind = type(v)
        if kind is str:
            if len(v) > 2000:
                raise ValueError("JSON string limit exceeded")
            v.encode("utf-8")
        elif kind is int:
            if v.bit_length() > 1023:
                raise ValueError("JSON integer limit exceeded")
        elif kind is float:
            if not math.isfinite(v):
                raise ValueError("Nonfinite JSON number")
        elif kind in (list, dict):
            if len(v) > items:
                raise ValueError("JSON container limit exceeded")
            if kind is dict:
                for k, val in v.items():
                    if type(k) is not str:
                        raise ValueError("JSON keys must be strings")
                    visit(k, depth + 1)
                    visit(val, depth + 1)
            else:
                for val in v:
                    visit(val, depth + 1)
        elif v is not None and kind is not bool:
            raise ValueError("Builtin JSON required")
    visit(value, 1)


def _number(v):
    return type(v) in (int, float) and math.isfinite(v)


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _validate(request):
    _json(request)
    _require(type(request) is dict and request.keys() == {"evaluation", "nodes", "connections", "targets"}, "Exact graph schema required")
    _require(request["evaluation"] == EVALUATION, "Unsupported evaluation")
    nodes, edges, targets = (request[k] for k in ("nodes", "connections", "targets"))
    _require(type(nodes) is list and 1 <= len(nodes) <= 16, "Node limit is 1..16")
    _require(type(edges) is list and len(edges) <= 64, "Connection limit is 64")
    _require(type(targets) is list and 1 <= len(targets) <= 32, "Target limit is 1..32")
    indexed = {}
    annuli = 0
    for node in nodes:
        _require(type(node) is dict and node.keys() == {"id", "model", "inputs"}, "Exact node schema required")
        name, model, inputs = (node[k] for k in ("id", "model", "inputs"))
        _require(type(name) is str and _NAME.fullmatch(name) and name not in indexed, "Invalid or duplicate node identifier")
        _require(type(model) is str and model in _IDS, "Unknown semantic adapter")
        _require(type(inputs) is dict and inputs.keys() <= (_INPUTS[model].keys() | _EXTRA[model]), "Unknown input field")
        for key, val in inputs.items():
            if key in _INPUTS[model]:
                _require((key == "pitch_root_rad" and val is None) or _number(val), "Numeric literal required")
                if key in ("annuli", "blade_count"):
                    maximum = 2048 if key == "annuli" else 32
                    _require(type(val) is int and 1 <= val <= maximum, "Integer count outside resource limit")
            elif key == "coefficient_envelope":
                _require(type(val) is dict and val.keys() == _BOUNDS and all(_number(v) for v in val.values()), "Exact numeric coefficient envelope required")
            else:
                _require(type(val) is str and bool(val.strip()), "Literal string declaration required")
        if model == _HOVER:
            _require("annuli" in inputs, "Annuli must be literal")
            annuli += inputs["annuli"]
        indexed[name] = node
    _require(annuli <= 8192, "Aggregate hover annuli limit is 8192")
    incoming = {name: {} for name in indexed}
    children = {name: [] for name in indexed}
    indegree = dict.fromkeys(indexed, 0)
    for edge in edges:
        _require(type(edge) is dict and edge.keys() == {"from_node", "from_port", "to_node", "to_port"}, "Exact connection schema required")
        a, ap, b, bp = (edge[k] for k in ("from_node", "from_port", "to_node", "to_port"))
        _require(all(type(v) is str for v in (a, ap, b, bp)), "Named ports required")
        _require(a in indexed and b in indexed and a != b, "Unknown node or self connection")
        am, bm = indexed[a]["model"], indexed[b]["model"]
        _require(ap in _OUTPUTS[am] and bp in _INPUTS[bm] and bp not in _LITERAL, "Unknown, vector, or literal-only port")
        _require(_OUTPUTS[am][ap] == _INPUTS[bm][bp] and ap != "annuli", "SI unit or scalar kind mismatch")
        _require(bp not in incoming[b] and bp not in indexed[b]["inputs"], "Duplicate destination or literal-edge collision")
        incoming[b][bp] = (a, ap)
        children[a].append(b)
        indegree[b] += 1
    for name, node in indexed.items():
        _require(node["inputs"].keys() | incoming[name].keys() == _INPUTS[node["model"]].keys() | _EXTRA[node["model"]],
                 "Every required input must be supplied exactly once, including unselected nodes")
    seen = set()
    for target in targets:
        _require(type(target) is dict and target.keys() == {"node", "port"}, "Exact target schema required")
        name, port = target["node"], target["port"]
        _require(type(name) is str and type(port) is str and name in indexed, "Unknown target node")
        _require(port in _OUTPUTS[indexed[name]["model"]] and (name, port) not in seen, "Unknown, vector, or duplicate target")
        seen.add((name, port))
    ready = [n for n, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        name = heapq.heappop(ready)
        order.append(name)
        for child in children[name]:
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    _require(len(order) == len(indexed), "Cycles are rejected globally, including unselected nodes")
    closure = {t["node"] for t in targets}
    pending = list(closure)
    while pending:
        for parent, _ in incoming[pending.pop()].values():
            if parent not in closure:
                closure.add(parent)
                pending.append(parent)
    return indexed, incoming, [name for name in order if name in closure]


def _component(model, inputs):
    if model == _ATM:
        state = standard_atmosphere(**deepcopy(inputs))
        _require(type(state) is StandardAtmosphereState, "Invalid component")
        raw = {f.name: getattr(state, f.name) for f in fields(StandardAtmosphereState)}
        _json(raw)
        h = inputs["altitude_m"]
        expected_h = EARTH_RADIUS_M * h / (EARTH_RADIUS_M + h) if inputs["altitude_kind"] == "geometric" else h
        _require(raw["model_id"] == MODEL_ID and raw["evidence_status"] == "REFERENCE_MODEL_NOT_AIRCRAFT_VALIDATION"
                 and raw["altitude_kind"] == inputs["altitude_kind"] and raw["input_altitude_m"] == h
                 and raw["geopotential_altitude_m"] == expected_h
                 and all(_number(raw[k]) for k in _ATM_OUT)
                 and all(raw[k] > 0 for k in ("pressure_pa", "temperature_k", "density_kg_m3")), "Invalid component")
        return raw, {k: raw[k] for k in _ATM_OUT}, dict(_ATM_OUT)
    result = evaluate_hover_bemt(deepcopy(inputs)) if model == _HOVER else screen_fixed_wing(deepcopy(inputs))
    _json(result, budget=20000, items=2048)
    if model == _HOVER:
        # Existing boundary verifies exact envelope, units, vector lengths and integer annuli.
        _require(_valid_hover(result, inputs["annuli"]) and result["status"] == "COMPUTED_EXPERIMENTAL", "Invalid or refused component")
    else:
        keys = {"status", "reasons", "outputs", "output_units", "model_id", "evidence_level",
                "aircraft_status", "feasibility", "coefficient_source", "coefficient_envelope", "source_metadata", "limitations"}
        _require(type(result) is dict and result.keys() == keys, "Invalid or refused component")
        _require(result["status"] == "SCREENING_COMPUTED" and result["model_id"] == _IDS[model]
                 and result["evidence_level"] == "unverified" and result["aircraft_status"] is None
                 and result["feasibility"] is None and result["reasons"] == []
                 and result["coefficient_source"] == inputs["coefficient_source"]
                 and type(result["coefficient_envelope"]) is dict
                 and result["coefficient_envelope"].keys() == _BOUNDS
                 and all(_number(v) for v in result["coefficient_envelope"].values())
                 and result["coefficient_envelope"] == inputs["coefficient_envelope"]
                 and type(result["limitations"]) is list and all(type(v) is str for v in result["limitations"])
                 and type(result["source_metadata"]) is dict
                 and result["source_metadata"].keys() == {"urls", "pdf_reference", "verification"}
                 and type(result["source_metadata"]["urls"]) is list
                 and all(type(v) is str for v in result["source_metadata"]["urls"])
                 and all(type(result["source_metadata"][k]) is str for k in ("pdf_reference", "verification")), "Invalid component")
        _require(type(result["outputs"]) is dict and result["outputs"].keys() == _WING_OUT.keys()
                 and result["output_units"] == _WING_OUT
                 and all(_number(v) for v in result["outputs"].values()), "Invalid component")
    return result, {k: result["outputs"][k] for k in _OUTPUTS[model]}, dict(_OUTPUTS[model])


def evaluate_model_graph(request):
    """Validate all nodes first, then execute only the selected ancestor closure.

    Refusals/exceptions never export partial selected outputs or exception text.
    Completed stages on failure are explicitly incomplete diagnostic data.
    """
    response = {"evaluation": EVALUATION, "schema_version": "bounded_model_graph_v1",
                "status": "GRAPH_INVALID", "evidence_level": "unverified",
                "physical_validation": "NOT_ESTABLISHED", "numerical_qualification": "NOT_ESTABLISHED",
                "runtime_identity": "NOT_ESTABLISHED", "aircraft_status": None, "feasibility": None,
                "reasons": [], "stages": [], "transfers": [], "stage_order": [],
                "diagnostics_complete": False, "failed_node": None, "outputs": {}, "output_units": {}}
    try:
        indexed, incoming, order = _validate(request)
        snapshot = deepcopy(request)
        response["request_sha256"] = sha256_record(snapshot)
        indexed = {node["id"]: node for node in snapshot["nodes"]}
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        response["reasons"] = ["Invalid bounded graph: exact schema, scalar SI bindings, required inputs for all nodes, global acyclicity and resource limits are mandatory."]
        return response
    values = {}
    for name in order:
        node = indexed[name]
        assembled = deepcopy(node["inputs"])
        transfers = []
        for port, (parent, parent_port) in sorted(incoming[name].items()):
            assembled[port] = values[parent][parent_port]
            producer = next(s for s in response["stages"] if s["node"] == parent)
            transfers.append({"from_node": parent, "from_port": parent_port, "to_node": name,
                              "to_port": port, "value": assembled[port], "unit": _INPUTS[node["model"]][port],
                              "frame": "scalar", "producer_result_sha256": producer["result_sha256"]})
        try:
            inputs_copy = deepcopy(assembled)
            raw, outputs, _ = _component(node["model"], inputs_copy)
            record = {"node": name, "adapter": node["model"], "model_id": _IDS[node["model"]],
                      "inputs": deepcopy(assembled), "inputs_sha256": sha256_record(assembled),
                      "result": deepcopy(raw), "result_sha256": sha256_record(raw)}
        except (ValueError, TypeError, OverflowError, ZeroDivisionError, AttributeError,
                KeyError, IndexError, RuntimeError, UnicodeError, RecursionError):
            response.update(status="EXECUTION_FAILED", failed_node=name,
                            reasons=["Component refused, raised an exception, or returned an invalid result; diagnostic stages are incomplete."])
            return deepcopy(response)
        values[name] = deepcopy(outputs)
        response["stages"].append(record)
        response["stage_order"].append(name)
        response["transfers"].extend(transfers)
    for target in snapshot["targets"]:
        name, port = target["node"], target["port"]
        response["outputs"].setdefault(name, {})[port] = values[name][port]
        response["output_units"].setdefault(name, {})[port] = _OUTPUTS[indexed[name]["model"]][port]
    response.update(status="COMPUTED_EXPERIMENTAL", diagnostics_complete=True)
    return deepcopy(response)
