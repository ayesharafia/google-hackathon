"""Dependency-only batch proposals; no execution or prerequisite verification."""

from copy import deepcopy

from physimesh.drone.dependency_invalidation import dependency_invalidation_plan


def dependency_batch_plan(graph, targets, changed_outputs):
    """Layer affected selected models after the authoritative invalidation plan.

    External prerequisites are assumed dependencies, never verified available or
    valid. A batch confers no readiness, freshness, or parallel-run permission.
    """
    result = deepcopy(dependency_invalidation_plan(graph, targets, changed_outputs))
    result.update(batches=[], external_prerequisites=[], readiness="NOT_ESTABLISHED",
                  prerequisites="NOT_VERIFIED", execution_authorized=False)
    if result["status"] != "INVALIDATION_PLAN_PROPOSED":
        return result

    affected = set(result["affected_models"])
    predecessors = {model: set() for model in affected}
    successors = {model: set() for model in affected}
    external = set()
    for edge in graph["connections"]:
        source, destination = edge["from_model"], edge["to_model"]
        if destination not in affected:
            continue
        if source in affected:
            predecessors[destination].add(source)
            successors[source].add(destination)
        else:
            external.add((source, destination))

    indegree = {model: len(parents) for model, parents in predecessors.items()}
    ready = sorted(model for model, degree in indegree.items() if degree == 0)
    while ready:
        result["batches"].append(ready)
        next_ready = []
        for source in ready:
            for destination in successors[source]:
                indegree[destination] -= 1
                if indegree[destination] == 0:
                    next_ready.append(destination)
        ready = sorted(next_ready)

    result["external_prerequisites"] = [
        {"source_model": source, "destination_model": destination, "unverified": True}
        for source, destination in sorted(external)
    ]
    result["status"] = "BATCH_PLAN_PROPOSED"
    return result
