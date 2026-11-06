import heapq
import re


def dependency_plan(graph, targets):
    """Propose a dependency plan without executing models or mutating inputs.

    Port declarations are metadata only. Matching them does not validate backend
    availability, mathematical adequacy, physical applicability, convergence, or
    physics. No unit conversion, cost optimization, or tolerance acceptance occurs.
    """
    def result(status, *reasons, order=None, canonical=None):
        return {
            "status": status,
            "reasons": list(reasons),
            "order": [] if order is None else order,
            "targets": [] if canonical is None else canonical,
            "evidence_level": "unverified",
            "execution_authorized": False,
        }

    def record(value, keys):
        return (type(value) is dict
                and all(type(key) is str for key in value)
                and value.keys() == keys)

    def identifier(value):
        return (type(value) is str and 1 <= len(value) <= 80
                and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value) is not None)

    def metadata(value):
        return type(value) is str and 1 <= len(value) <= 80 and bool(value.strip())

    def ports(value):
        if type(value) is not list or len(value) > 128:
            return None
        parsed = {}
        for port in value:
            if not record(port, {"name", "unit", "frame"}):
                return None
            name = port["name"]
            if (not identifier(name) or name in parsed
                    or not metadata(port["unit"]) or not metadata(port["frame"])):
                return None
            parsed[name] = (port["unit"], port["frame"])
        return parsed

    if not record(graph, {"models", "connections"}):
        return result("MODEL_INAPPLICABLE", "INVALID_GRAPH")
    if (type(graph["models"]) is not list or len(graph["models"]) > 128
            or type(graph["connections"]) is not list
            or len(graph["connections"]) > 4096):
        return result("MODEL_INAPPLICABLE", "INVALID_GRAPH")

    models = {}
    for model in graph["models"]:
        if not record(model, {"id", "inputs", "outputs"}):
            return result("MODEL_INAPPLICABLE", "INVALID_GRAPH")
        model_id = model["id"]
        if not identifier(model_id) or model_id in models:
            return result("MODEL_INAPPLICABLE", "INVALID_GRAPH")
        inputs, outputs = ports(model["inputs"]), ports(model["outputs"])
        if inputs is None or outputs is None:
            return result("MODEL_INAPPLICABLE", "INVALID_GRAPH")
        models[model_id] = (inputs, outputs)

    dependencies = {model_id: set() for model_id in models}
    incoming = set()
    connections = set()
    unit_mismatch = frame_mismatch = False
    connection_keys = {"from_model", "from_port", "to_model", "to_port"}
    for connection in graph["connections"]:
        if not record(connection, connection_keys):
            return result("MODEL_INAPPLICABLE", "INVALID_GRAPH")
        edge = tuple(connection[key] for key in
                     ("from_model", "from_port", "to_model", "to_port"))
        if any(type(value) is not str for value in edge):
            return result("MODEL_INAPPLICABLE", "INVALID_GRAPH")
        source, output, destination, input_name = edge
        if (source not in models or destination not in models
                or output not in models[source][1]
                or input_name not in models[destination][0]):
            return result("MODEL_INAPPLICABLE", "INVALID_GRAPH")
        endpoint = (destination, input_name)
        if edge in connections or endpoint in incoming:
            return result("MODEL_INAPPLICABLE", "INVALID_GRAPH")
        connections.add(edge)
        incoming.add(endpoint)
        dependencies[destination].add(source)
        source_unit, source_frame = models[source][1][output]
        target_unit, target_frame = models[destination][0][input_name]
        unit_mismatch |= source_unit != target_unit
        frame_mismatch |= source_frame != target_frame

    if type(targets) is not list or not 1 <= len(targets) <= 128:
        return result("MODEL_INAPPLICABLE", "INVALID_TARGETS")
    selected = set()
    for target in targets:
        if not record(target, {"model", "port"}):
            return result("MODEL_INAPPLICABLE", "INVALID_TARGETS")
        model_id, port = target["model"], target["port"]
        if (type(model_id) is not str or type(port) is not str
                or model_id not in models or port not in models[model_id][1]):
            return result("MODEL_INAPPLICABLE", "INVALID_TARGETS")
        endpoint = (model_id, port)
        if endpoint in selected:
            return result("MODEL_INAPPLICABLE", "INVALID_TARGETS")
        selected.add(endpoint)

    mismatches = []
    if unit_mismatch:
        mismatches.append("UNIT_MISMATCH")
    if frame_mismatch:
        mismatches.append("FRAME_MISMATCH")
    if mismatches:
        return result("MODEL_INAPPLICABLE", *mismatches)

    required = set()
    pending = [model_id for model_id, port in selected]
    while pending:
        model_id = pending.pop()
        if model_id in required:
            continue
        required.add(model_id)
        pending.extend(dependencies[model_id] - required)

    if any((model_id, name) not in incoming
           for model_id in required for name in models[model_id][0]):
        return result("INPUT_INCOMPLETE", "MISSING_REQUIRED_INPUT")

    indegree = {model_id: len(dependencies[model_id]) for model_id in required}
    dependents = {model_id: set() for model_id in required}
    for model_id in required:
        for source in dependencies[model_id]:
            dependents[source].add(model_id)
    ready = [model_id for model_id in required if indegree[model_id] == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        model_id = heapq.heappop(ready)
        order.append(model_id)
        for destination in dependents[model_id]:
            indegree[destination] -= 1
            if indegree[destination] == 0:
                heapq.heappush(ready, destination)
    if len(order) != len(required):
        return result("COUPLING_UNSUPPORTED", "EXPLICIT_COUPLING_STRATEGY_REQUIRED")

    canonical = [{"model": model_id, "port": port}
                 for model_id, port in sorted(selected)]
    return result("PLAN_PROPOSED", order=order, canonical=canonical)
