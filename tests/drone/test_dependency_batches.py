import copy
import itertools

import pytest

from physimesh.drone.dependency_batches import dependency_batch_plan
from physimesh.drone.dependency_invalidation import dependency_invalidation_plan
from tests.drone.test_dependency_invalidation import diamond, edge, endpoint, model, port


def plan(graph, changes, targets=None):
    return dependency_batch_plan(graph, [endpoint("D")] if targets is None else targets, changes)


def external(source, destination):
    return {"source_model": source, "destination_model": destination, "unverified": True}


@pytest.mark.parametrize("seed,batches,prerequisites", [
    ("A", [["A"], ["B", "C"], ["D"]], []),
    ("B", [["B"], ["D"]], [external("A", "B"), external("C", "D")]),
    ("D", [["D"]], [external("B", "D"), external("C", "D")]),
    ("Outside", [], []),
    (None, [], []),
])
def test_diamond(seed, batches, prerequisites):
    graph = diamond()
    changes = [] if seed is None else [endpoint(seed)]
    base = dependency_invalidation_plan(graph, [endpoint("D")], changes)
    result = plan(graph, changes)
    assert result == dict(base, status="BATCH_PLAN_PROPOSED", batches=batches,
                          external_prerequisites=prerequisites,
                          readiness="NOT_ESTABLISHED", prerequisites="NOT_VERIFIED")
    assert result["execution_authorized"] is False
    flattened = list(itertools.chain.from_iterable(batches))
    assert len(flattened) == len(set(flattened))
    assert set(flattened) == set(base["affected_models"])


def test_branches_disconnected_selected_and_whole_model_propagation():
    graph = diamond()
    graph["models"] += [model("X"), model("Y", ["value"]), model("Z", ["value"])]
    graph["connections"] += [edge("X", "Y"), edge("B", "Z")]
    graph["models"][1]["outputs"].append(port("unused"))
    result = plan(graph, [endpoint("B", "unused"), endpoint("X")],
                  [endpoint("D"), endpoint("Y")])
    assert result["batches"] == [["B", "X"], ["D", "Y"]]
    assert result["external_prerequisites"] == [external("A", "B"), external("C", "D")]
    assert "Z" not in result["affected_models"]
    assert plan(graph, [endpoint("Y")], [endpoint("B")])["batches"] == []


def test_multiple_ports_deduplicate_model_edges():
    graph = diamond()
    graph["models"][0]["outputs"].append(port("other"))
    graph["models"][1]["inputs"].append(port("other"))
    graph["connections"].append(dict(edge("A", "B", "other"), from_port="other"))
    assert plan(graph, [endpoint("B")])["external_prerequisites"] == [
        external("A", "B"), external("C", "D")]
    assert plan(graph, [endpoint("A"), endpoint("A", "other")])["batches"] == [
        ["A"], ["B", "C"], ["D"]]
    graph["connections"].append(copy.deepcopy(graph["connections"][-1]))
    assert plan(graph, [endpoint("A")])["reasons"] == ["INVALID_GRAPH"]


def test_permutations():
    graph = diamond()
    targets = [endpoint("D"), endpoint("Outside")]
    changes = [endpoint("B"), endpoint("Outside")]
    expected = plan(graph, changes, targets)
    for models in itertools.permutations(graph["models"]):
        for edges in (graph["connections"], list(reversed(graph["connections"]))):
            assert plan({"models": list(models), "connections": edges},
                        list(reversed(changes)), list(reversed(targets))) == expected


@pytest.mark.parametrize("kind", ["graph", "targets", "changes", "cycle", "missing",
                                  "unit", "frame", "model_bound", "edge_bound"])
def test_refusals_propagate(kind):
    graph, targets, changes = diamond(), [endpoint("D")], [endpoint("B")]
    if kind == "graph":
        graph = None
    elif kind == "targets":
        targets = ()
    elif kind == "changes":
        changes = ()
    elif kind == "cycle":
        graph["models"][0]["inputs"].append(port())
        graph["connections"].append(edge("D", "A"))
    elif kind == "missing":
        graph["connections"].pop()
    elif kind in ("unit", "frame"):
        graph["models"][1]["inputs"][0][kind] = "different"
    elif kind == "model_bound":
        graph["models"] = [model(f"M{i}") for i in range(129)]
    else:
        graph["connections"] *= 1025
    base = dependency_invalidation_plan(graph, targets, changes)
    result = dependency_batch_plan(graph, targets, changes)
    assert base["status"] != "INVALIDATION_PLAN_PROPOSED"
    assert result == dict(base, batches=[], external_prerequisites=[],
                          readiness="NOT_ESTABLISHED", prerequisites="NOT_VERIFIED")


@pytest.mark.parametrize("changes", [None, {}, True, [endpoint("Missing")],
                                     [endpoint("A", "missing")], [endpoint("A")] * 2])
def test_invalid_change_types(changes):
    result = plan(diamond(), changes)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["reasons"] == ["INVALID_CHANGED_OUTPUTS"]
    assert result["batches"] == result["external_prerequisites"] == []


def test_refusal_first_and_deep_copy(monkeypatch):
    base = {"status": "COUPLING_UNSUPPORTED", "reasons": ["reason"],
            "nested": {"values": [[]]}, "execution_authorized": False}
    before = copy.deepcopy(base)
    calls = []

    def invalidation(graph, targets, changes):
        calls.append((graph, targets, changes))
        return base

    monkeypatch.setattr("physimesh.drone.dependency_batches.dependency_invalidation_plan",
                        invalidation)
    graph, targets, changes = object(), object(), object()
    result = dependency_batch_plan(graph, targets, changes)
    assert calls == [(graph, targets, changes)]
    result["nested"]["values"][0].append("changed")
    result["reasons"].clear()
    assert base == before


def test_mutation_isolation():
    graph, targets, changes = diamond(), [endpoint("D")], [endpoint("B")]
    before = copy.deepcopy((graph, targets, changes))
    result = plan(graph, changes, targets)
    expected = copy.deepcopy(result)
    assert (graph, targets, changes) == before
    result["batches"][0].append("mutated")
    result["external_prerequisites"][0]["source_model"] = "mutated"
    result["targets"][0]["model"] = "mutated"
    result["changed_outputs"][0]["port"] = "mutated"
    assert (graph, targets, changes) == before
    assert plan(graph, changes, targets) == expected
    other = plan(graph, changes, targets)
    graph["connections"][0]["from_model"] = "mutated"
    targets[0]["model"] = changes[0]["model"] = "mutated"
    assert other == expected


def test_128_chain():
    names = [f"M{i:03}" for i in range(128)]
    graph = {"models": [model(name, [] if i == 0 else ["value"])
                        for i, name in enumerate(names)],
             "connections": [edge(a, b) for a, b in itertools.pairwise(names)]}
    result = plan(graph, [endpoint(names[0])], [endpoint(names[-1])])
    assert result["batches"] == [[name] for name in names]
    assert result["external_prerequisites"] == []
