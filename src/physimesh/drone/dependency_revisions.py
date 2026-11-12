"""Plan downstream work from caller-supplied opaque revision labels.

Label comparisons provide neither implementation change detection nor a
freshness guarantee. Revision label values are never included in the result.
"""

from copy import deepcopy

from physimesh.drone.dependency_batches import dependency_batch_plan


def dependency_revision_plan(graph, targets, before_revisions, after_revisions):
    """Expand changed caller labels into outputs and propose dependency batches."""
    base = deepcopy(dependency_batch_plan(graph, targets, []))
    base.update(
        declared_changed_models=[],
        label_comparison="NOT_PERFORMED",
        implementation_change_detection="NOT_PERFORMED",
    )
    if base.get("status") != "BATCH_PLAN_PROPOSED":
        return base

    models = {model["id"]: model for model in graph["models"]}
    model_ids = set(models)

    def valid_labels(labels):
        return (
            type(labels) is dict
            and all(type(key) is str for key in labels)
            and set(labels) == model_ids
            and all(
                type(value) is str and 1 <= len(value) <= 80 and value.strip()
                for value in labels.values()
            )
        )

    def closed(reason):
        base.update(
            status="MODEL_INAPPLICABLE",
            reasons=[reason],
            batches=[],
            affected_models=[],
            unaffected_models=[],
            changed_outputs=[],
            external_prerequisites=[],
        )
        return base

    if not valid_labels(before_revisions) or not valid_labels(after_revisions):
        return closed("INVALID_REVISION_LABELS")

    changed = sorted(
        model_id
        for model_id in model_ids
        if before_revisions[model_id] != after_revisions[model_id]
    )
    base.update(
        declared_changed_models=changed,
        label_comparison="CALLER_LABELS_COMPARED",
    )
    expanded = [
        {"model": model_id, "port": port}
        for model_id in changed
        for port in sorted(port["name"] for port in models[model_id]["outputs"])
    ]
    if len(expanded) > 128:
        return closed("REVISION_EXPANSION_LIMIT")

    result = deepcopy(dependency_batch_plan(graph, targets, expanded))
    if result.get("status") == "BATCH_PLAN_PROPOSED":
        result["status"] = "REVISION_PLAN_PROPOSED"
    result.update(
        declared_changed_models=changed,
        label_comparison="CALLER_LABELS_COMPARED",
        implementation_change_detection="NOT_PERFORMED",
    )
    return result
