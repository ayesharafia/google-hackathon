"""Bounded, manual dependency invalidation proposals; no execution or freshness proof."""

from physimesh.drone.dependency_plan import dependency_plan


def dependency_invalidation_plan(graph, targets, changed_outputs):
    """Conservatively mark selected descendants of manually declared output changes.

    The existing planner owns graph validation and selection semantics. Affected
    models are candidates for reconsideration, not observations of stale values.
    """
    plan = dependency_plan(graph, targets)
    result = {
        **plan,
        "reasons": list(plan["reasons"]),
        "order": list(plan["order"]),
        "targets": [dict(target) for target in plan["targets"]],
        "changed_outputs": [],
        "affected_models": [],
        "unaffected_models": [],
        "change_detection": "NOT_PERFORMED",
        "artifact_freshness": "NOT_ESTABLISHED",
        "physical_validation": "NOT_ESTABLISHED",
    }
    if plan["status"] != "PLAN_PROPOSED":
        return result

    def invalid_changes():
        result["status"] = "MODEL_INAPPLICABLE"
        result["reasons"] = ["INVALID_CHANGED_OUTPUTS"]
        return result

    if type(changed_outputs) is not list or len(changed_outputs) > 128:
        return invalid_changes()
    outputs = {model["id"]: {port["name"] for port in model["outputs"]}
               for model in graph["models"]}
    changed = set()
    for entry in changed_outputs:
        if (type(entry) is not dict
                or any(type(key) is not str for key in entry)
                or entry.keys() != {"model", "port"}):
            return invalid_changes()
        model, port = entry["model"], entry["port"]
        if (type(model) is not str or type(port) is not str
                or model not in outputs or port not in outputs[model]
                or (model, port) in changed):
            return invalid_changes()
        changed.add((model, port))

    downstream = {model: set() for model in outputs}
    for edge in graph["connections"]:
        downstream[edge["from_model"]].add(edge["to_model"])
    affected = {model for model, port in changed}
    pending = list(affected)
    while pending:
        model = pending.pop()
        for descendant in downstream[model]:
            if descendant not in affected:
                affected.add(descendant)
                pending.append(descendant)

    result["status"] = "INVALIDATION_PLAN_PROPOSED"
    result["changed_outputs"] = [{"model": model, "port": port} for model, port in sorted(changed)]
    result["affected_models"] = [model for model in plan["order"] if model in affected]
    result["unaffected_models"] = [model for model in plan["order"] if model not in affected]
    return result
