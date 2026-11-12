"""Caller-label revision proposals, including inherited fail-closed behavior."""

import copy
import itertools

import pytest

from physimesh.drone.dependency_batches import dependency_batch_plan
from physimesh.drone.dependency_revisions import dependency_revision_plan

from .test_dependency_invalidation import diamond, endpoint, model, port


class Record(dict):
    pass


class Text(str):
    pass


def labels(graph, value="opaque-label"):
    return {item["id"]: value for item in graph["models"]}


def plan(graph, before, after, targets=None):
    return dependency_revision_plan(
        graph, [endpoint("D")] if targets is None else targets, before, after,
    )


def assert_closed(result, reason):
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["reasons"] == [reason]
    for key in ("batches", "affected_models", "unaffected_models", "changed_outputs",
                "external_prerequisites"):
        assert result[key] == []


def assert_states(result, comparison="CALLER_LABELS_COMPARED"):
    assert result["label_comparison"] == comparison
    assert result["implementation_change_detection"] == "NOT_PERFORMED"
    assert result["change_detection"] == "NOT_PERFORMED"
    assert result["artifact_freshness"] == "NOT_ESTABLISHED"
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["execution_authorized"] is False
    assert result["evidence_level"] == "unverified"


@pytest.mark.parametrize("changed,affected,unaffected", [
    ("A", ["A", "B", "C", "D"], []),
    ("B", ["B", "D"], ["A", "C"]),
    ("D", ["D"], ["A", "B", "C"]),
    ("Outside", [], ["A", "B", "C", "D"]),
    (None, [], ["A", "B", "C", "D"]),
])
def test_diamond(changed, affected, unaffected):
    graph = diamond()
    before = labels(graph)
    after = dict(before)
    if changed:
        after[changed] = "another-opaque-label"
    result = plan(graph, before, after)
    outputs = [endpoint(changed)] if changed else []
    expected = dependency_batch_plan(graph, [endpoint("D")], outputs)
    expected.update(status="REVISION_PLAN_PROPOSED",
                    declared_changed_models=[changed] if changed else [],
                    label_comparison="CALLER_LABELS_COMPARED",
                    implementation_change_detection="NOT_PERFORMED")
    assert result == expected
    assert result["affected_models"] == affected
    assert result["unaffected_models"] == unaffected
    assert_states(result)
    assert "opaque-label" not in repr(result)


@pytest.mark.parametrize("old,new,changed", [
    ("Case", "case", True), ("x", " x", True), ("x", "x ", True),
    ("1.0", "1.0.0", True), ("9", "2", True),
    ("arbitrary / label !", "arbitrary / label !", False),
    ("x" * 80, "y" * 80, True), (" x ", " x ", False),
])
def test_exact_opaque_comparison(old, new, changed):
    graph = diamond()
    before, after = labels(graph, old), labels(graph, old)
    after["B"] = new
    result = plan(graph, before, after)
    assert result["status"] == "REVISION_PLAN_PROPOSED"
    assert result["declared_changed_models"] == (["B"] if changed else [])
    assert_states(result)


def invalid_labels(graph):
    valid = labels(graph)
    yield from (None, [], (), "labels", 1, True, Record(valid))
    yield {}
    yield {key: value for key, value in valid.items() if key != "Outside"}
    yield dict(valid, Missing="label")
    yield {Text(key): value for key, value in valid.items()}
    yield {**valid, 1: "label"}
    for value in (None, 1, True, [], {}, b"label", Text("label"), "", " \t\n", "x" * 81):
        yield dict(valid, Outside=value)


@pytest.mark.parametrize("side", ["before", "after"])
def test_invalid_complete_exact_builtin_label_maps(side):
    graph = diamond()
    valid = labels(graph)
    for invalid in invalid_labels(graph):
        before, after = (invalid, valid) if side == "before" else (valid, invalid)
        result = plan(graph, before, after)
        assert_closed(result, "INVALID_REVISION_LABELS")
        assert result["declared_changed_models"] == []
        assert_states(result, "NOT_PERFORMED")


def test_zero_output_model_change_and_expand_every_output():
    graph = diamond()
    graph["models"].append({"id": "Empty", "inputs": [], "outputs": []})
    graph["models"][1]["outputs"].extend([port("z_unused"), port("a_unused")])
    before, after = labels(graph), labels(graph)
    after.update(B="changed-B", Empty="changed-empty")
    result = plan(graph, before, after)
    assert result["status"] == "REVISION_PLAN_PROPOSED"
    assert result["declared_changed_models"] == ["B", "Empty"]
    assert result["changed_outputs"] == [endpoint("B", name) for name in
                                         ("a_unused", "value", "z_unused")]
    after = dict(before, Empty="changed-empty")
    result = plan(graph, before, after)
    assert result["declared_changed_models"] == ["Empty"]
    assert result["changed_outputs"] == result["affected_models"] == []


@pytest.mark.parametrize("count", [128, 129])
def test_expansion_boundary_is_closed_without_partial_results(count):
    graph = {"models": [model(f"M{i:03}") for i in range(128)], "connections": []}
    if count == 129:
        graph["models"][0]["outputs"].append(port("extra"))
    before, after = labels(graph, "before-secret"), labels(graph, "after-secret")
    result = plan(graph, before, after, [endpoint("M127")])
    assert result["declared_changed_models"] == sorted(before)
    assert_states(result)
    if count == 128:
        assert result["status"] == "REVISION_PLAN_PROPOSED"
        assert result["changed_outputs"] == [endpoint(name) for name in sorted(before)]
    else:
        assert_closed(result, "REVISION_EXPANSION_LIMIT")
    assert "before-secret" not in repr(result)
    assert "after-secret" not in repr(result)


@pytest.mark.parametrize("kind", ["graph", "target", "unit", "frame", "cycle"])
def test_inherited_refusal_precedes_label_access(kind, monkeypatch):
    graph, targets = diamond(), [endpoint("D")]
    if kind == "graph":
        graph = None
    elif kind == "target":
        targets = [endpoint("Missing")]
    elif kind in ("unit", "frame"):
        graph["models"][1]["inputs"][0][kind] = "different"
    else:
        graph["models"][0]["inputs"].append(port())
        graph["connections"].append(
            {"from_model": "D", "from_port": "value", "to_model": "A", "to_port": "value"},
        )
    inherited = dependency_batch_plan(graph, targets, [])
    assert inherited["status"] != "BATCH_PLAN_PROPOSED"
    original = copy.deepcopy(inherited)
    monkeypatch.setattr("physimesh.drone.dependency_revisions.dependency_batch_plan",
                        lambda g, t, c: inherited)
    result = plan(graph, object(), object(), targets)
    expected = dict(original, declared_changed_models=[], label_comparison="NOT_PERFORMED",
                    implementation_change_detection="NOT_PERFORMED")
    assert result == expected
    result["reasons"].append("mutated")
    result["targets"].append(endpoint("mutated"))
    assert inherited == original


def test_input_and_return_mutation_independence():
    graph, targets = diamond(), [endpoint("D")]
    before, after = labels(graph), labels(graph)
    after["B"] = "secret-after-B"
    inputs = copy.deepcopy((graph, targets, before, after))
    result = plan(graph, before, after, targets)
    expected = copy.deepcopy(result)
    assert (graph, targets, before, after) == inputs
    for value in result.values():
        if isinstance(value, list):
            value.append({"mutated": True})
    result["targets"][0]["model"] = "mutated"
    result["changed_outputs"][0]["port"] = "mutated"
    assert (graph, targets, before, after) == inputs
    assert plan(graph, before, after, targets) == expected
    other = plan(graph, before, after, targets)
    graph["models"][0]["outputs"][0]["name"] = "mutated"
    targets[0]["model"] = "mutated"
    before["B"] = after["B"] = "mutated"
    assert other == expected


def test_permutation_determinism():
    graph = diamond()
    graph["models"][1]["outputs"].extend([port("z_unused"), port("a_unused")])
    before, after = labels(graph), labels(graph)
    after.update(B="secret-B", Outside="secret-Outside")
    targets = [endpoint("D"), endpoint("Outside")]
    expected = plan(graph, before, after, targets)
    for models in itertools.permutations(graph["models"]):
        for reverse in (False, True):
            permuted = copy.deepcopy({"models": list(models),
                                      "connections": graph["connections"][::-1] if reverse
                                      else graph["connections"]})
            for item in permuted["models"]:
                item["outputs"].reverse()
            assert plan(permuted, dict(reversed(list(before.items()))),
                        dict(reversed(list(after.items()))), targets[::-1]) == expected
    assert "secret-B" not in repr(expected)
    assert "secret-Outside" not in repr(expected)
