"""Four trusted scalar SI adapters; bounded reference computation, no qualification.

The frozen three-adapter executor is untouched. Only its JSON boundary, fresh
metadata and existing component boundary are reused; preflight is local.
"""

import heapq
from copy import deepcopy
from dataclasses import asdict

from . import model_graph_execution as _core
from . import reference_air_properties as _air
from .provenance import sha256_record
from .standard_atmosphere import EARTH_RADIUS_M

EVALUATION = "bounded_reference_air_graph_experimental"
_AIR = "reference_air_properties"
_HOVER = "isolated_hover_bemt_experimental"
_json = _core._json
_number = _core._number
_require = _core._require
_NAME = _core._NAME
_BOUNDS = _core._BOUNDS


def adapter_metadata():
    """Return fresh code-owned declarations for exactly four allowed models."""
    metadata = _core.adapter_metadata()
    metadata[_AIR] = {
        "model_id": _air.MODEL_ID,
        "inputs": {"altitude_m": {"unit": "m", "frame": "scalar",
                                   "kind": "number", "connectable": True}},
        "outputs": {key: {"unit": unit, "frame": "scalar", "kind": "number"}
                    for key, unit in {
                        "density_kg_m3": "kg/m^3", "dynamic_viscosity_pa_s": "Pa*s",
                        "speed_of_sound_m_s": "m/s", "gravity_m_s2": "m/s^2",
                        "temperature_k": "K", "pressure_pa": "Pa"}.items()},
        "literal_fields": ["altitude_kind"],
    }
    return metadata


# Private snapshots: no caller metadata or runtime mutation of accepted globals.
_METADATA = adapter_metadata()
_IDS = {model: spec["model_id"] for model, spec in _METADATA.items()}
_INPUTS = {model: {key: port["unit"] for key, port in spec["inputs"].items()}
           for model, spec in _METADATA.items()}
_OUTPUTS = {model: {key: port["unit"] for key, port in spec["outputs"].items()}
            for model, spec in _METADATA.items()}
_EXTRA = {model: set(spec["literal_fields"]) - spec["inputs"].keys()
          for model, spec in _METADATA.items()}
_LITERAL = {key for spec in _METADATA.values() for key, port in spec["inputs"].items()
            if not port["connectable"]}


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
        if model == _AIR:
            _require(inputs.get("altitude_kind") in ("geometric", "geopotential"),
                     "Explicit air altitude convention required")
            if "altitude_m" in inputs:
                _require(0 <= inputs["altitude_m"] <= 30000, "Air altitude outside 0..30000 m")
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
    if model != _AIR:
        return _core._component(model, inputs)
    result = _air.reference_air_properties(**deepcopy(inputs))
    _require(type(result) is _air.ReferenceAirProperties, "Invalid air component type")
    # Validate before asdict: dataclasses recursively erase nested dataclass types.
    _air._validate_state(result.state, float(inputs["altitude_m"]), inputs["altitude_kind"])
    raw = asdict(result)
    _json(raw)
    expected = {"model_id": _air.MODEL_ID, "viscosity_model": _air.VISCOSITY_MODEL,
                "sound_model": _air.SOUND_MODEL, "gravity_model": _air.GRAVITY_MODEL,
                "physical_qualification": "NOT_ESTABLISHED",
                "numerical_qualification": "NOT_ESTABLISHED"}
    _require(all(type(raw[k]) is str and raw[k] == v for k, v in expected.items()),
             "Invalid air identifiers or qualification")
    z = (float(inputs["altitude_m"]) if inputs["altitude_kind"] == "geometric" else
         EARTH_RADIUS_M * result.state.geopotential_altitude_m
         / (EARTH_RADIUS_M - result.state.geopotential_altitude_m))
    _require(type(raw["geometric_altitude_m"]) is float
             and _number(raw["geometric_altitude_m"]) and raw["geometric_altitude_m"] == z,
             "Invalid geometric altitude")
    outputs = {k: raw["state"][k] if k in raw["state"] else raw[k] for k in _OUTPUTS[_AIR]}
    _require(all(type(v) is float and _number(v) and v > 0 for v in outputs.values()),
             "Invalid air scalar outputs")
    return raw, outputs, dict(_OUTPUTS[_AIR])


def evaluate_reference_air_graph(request):
    """Validate all nodes first, then execute only the selected ancestor closure.

    Refusals/exceptions never export partial selected outputs or exception text.
    Completed stages on failure are explicitly incomplete diagnostic data.
    """
    response = {"evaluation": EVALUATION, "schema_version": "bounded_reference_air_graph_v1",
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
