import copy
import itertools

import pytest

from physimesh.drone.dependency_invalidation import dependency_invalidation_plan
from physimesh.drone.dependency_plan import dependency_plan


def port(name="value", unit="N", frame="axis"):
    return {"name": name, "unit": unit, "frame": frame}


def model(name, inputs=()):
    return {"id": name, "inputs": [port(p) for p in inputs], "outputs": [port()]}


def edge(source, destination, name="value"):
    return {"from_model": source, "from_port": "value", "to_model": destination, "to_port": name}


def endpoint(model_id, name="value"):
    return {"model": model_id, "port": name}


def diamond():
    return {"models": [model("A"), model("B", ["value"]), model("C", ["value"]),
                       model("D", ["left", "right"]), model("Outside")],
            "connections": [edge("A", "B"), edge("A", "C"), edge("B", "D", "left"),
                            edge("C", "D", "right")]}


def plan(graph, changes, targets=None):
    return dependency_invalidation_plan(graph, [endpoint("D")] if targets is None else targets, changes)


@pytest.mark.parametrize("changes,affected,unaffected", [
    ([endpoint("A")], ["A", "B", "C", "D"], []),
    ([endpoint("B")], ["B", "D"], ["A", "C"]),
    ([endpoint("D")], ["D"], ["A", "B", "C"]),
    ([endpoint("Outside")], [], ["A", "B", "C", "D"]),
    ([], [], ["A", "B", "C", "D"]),
])
def test_diamond(changes, affected, unaffected):
    result = plan(diamond(), changes)
    assert result == {
        "status": "INVALIDATION_PLAN_PROPOSED", "reasons": [], "order": ["A", "B", "C", "D"],
        "targets": [endpoint("D")], "changed_outputs": changes,
        "affected_models": affected, "unaffected_models": unaffected,
        "evidence_level": "unverified", "execution_authorized": False,
        "change_detection": "NOT_PERFORMED", "artifact_freshness": "NOT_ESTABLISHED",
        "physical_validation": "NOT_ESTABLISHED",
    }


def test_chain_two_branches_selected_only_and_unused_output():
    graph = {"models": [model("A"), model("B", ["value"]), model("C", ["value"]),
                        model("X", ["value"]), model("Y", ["value"])],
             "connections": [edge("A", "B"), edge("B", "C"), edge("A", "X"), edge("X", "Y")]}
    graph["models"][1]["outputs"].append(port("unused"))
    result = plan(graph, [endpoint("B", "unused")], [endpoint("C")])
    assert result["order"] == ["A", "B", "C"]
    assert result["affected_models"] == ["B", "C"]
    assert result["unaffected_models"] == ["A"]
    assert plan(graph, [endpoint("Y")], [endpoint("B")])["affected_models"] == []
    all_targets = [endpoint(m["id"]) for m in graph["models"]]
    assert plan(graph, [endpoint("X")], all_targets)["affected_models"] == ["X", "Y"]


def test_deterministic_graph_target_and_change_permutations():
    graph = diamond()
    changes = [endpoint("Outside"), endpoint("B")]
    targets = [endpoint("D"), endpoint("Outside")]
    expected = plan(graph, changes, targets)
    for models in itertools.permutations(graph["models"]):
        for connections in (graph["connections"], list(reversed(graph["connections"]))):
            assert plan({"models": list(models), "connections": connections},
                        list(reversed(changes)), list(reversed(targets))) == expected
    assert expected["changed_outputs"] == [endpoint("B"), endpoint("Outside")]


class Sequence(list):
    pass


class Record(dict):
    pass


class Text(str):
    pass


@pytest.mark.parametrize("changes", [
    None, {}, (), "A", 1, True, Sequence(), [Record(endpoint("A"))], [None], [[]],
    [{}], [{"model": "A"}], [{"port": "value"}], [dict(endpoint("A"), extra=True)],
    [endpoint("Missing")], [endpoint("A", "missing")], [endpoint(1)], [endpoint("123")],
    [endpoint("A", 1)], [endpoint([], "value")], [endpoint("A", [])],
    [endpoint(Text("A"))], [endpoint("A", Text("value"))],
    [endpoint("A"), endpoint("A")], [endpoint("A")] * 129,
])
def test_invalid_changes(changes):
    result = plan(diamond(), changes)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["reasons"] == ["INVALID_CHANGED_OUTPUTS"]
    assert result["changed_outputs"] == result["affected_models"] == result["unaffected_models"] == []


def test_input_port_is_not_output():
    graph = diamond()
    graph["models"][3]["inputs"].append(port("input_only"))
    graph["connections"].append(edge("A", "D", "input_only"))
    assert plan(graph, [endpoint("D", "input_only")])["reasons"] == ["INVALID_CHANGED_OUTPUTS"]


@pytest.mark.parametrize("kind", ["unit", "frame", "missing", "cycle", "unselected_bad", "targets"])
def test_planner_refusal_precedes_changes_and_preserves_result(kind, monkeypatch):
    graph = diamond()
    targets = [endpoint("D")]
    if kind in ("unit", "frame"):
        graph["models"][1]["inputs"][0][kind] = "different"
    elif kind == "missing":
        graph["connections"].pop()
    elif kind == "cycle":
        graph["models"][0]["inputs"].append(port())
        graph["connections"].append(edge("D", "A"))
    elif kind == "unselected_bad":
        graph["models"][-1]["outputs"][0]["unit"] = ""
    else:
        targets = []
    original = dependency_plan(graph, targets)
    before = copy.deepcopy(original)
    monkeypatch.setattr("physimesh.drone.dependency_invalidation.dependency_plan", lambda g, t: original)
    result = dependency_invalidation_plan(graph, targets, object())
    for key, value in before.items():
        assert result[key] == value
    assert result["affected_models"] == result["unaffected_models"] == []
    result["reasons"].clear()
    result["order"].append("changed")
    result["targets"].append(endpoint("changed"))
    assert original == before


def test_structural_failure_without_key_access():
    class Hostile(dict):
        def __getitem__(self, key):
            raise AssertionError("graph keys accessed before planner refusal")
    for graph in (Hostile(), None, [], {"extra": True}):
        result = plan(graph, object())
        assert result["status"] == "MODEL_INAPPLICABLE"
        assert result["reasons"] == ["INVALID_GRAPH"]


def test_unselected_cycle_preserved_and_termination():
    graph = diamond()
    graph["models"] += [model("X", ["value"]), model("Y", ["value"])]
    graph["connections"] += [edge("X", "Y"), edge("Y", "X")]
    assert plan(graph, [endpoint("X")])["affected_models"] == []
    result = plan(graph, [], [endpoint("X")])
    assert result["status"] == "COUPLING_UNSUPPORTED"
    assert result["reasons"] == ["EXPLICIT_COUPLING_STRATEGY_REQUIRED"]


def test_maximum_change_count_and_iterative_chain():
    names = [f"M{i:03}" for i in range(128)]
    graph = {"models": [model(name, [] if i == 0 else ["value"]) for i, name in enumerate(names)],
             "connections": [edge(a, b) for a, b in itertools.pairwise(names)]}
    changes = [endpoint(name) for name in reversed(names)]
    result = plan(graph, changes, [endpoint(names[-1])])
    assert result["affected_models"] == names
    assert result["changed_outputs"] == list(reversed(changes))


def test_nested_input_and_return_mutation_independence():
    graph, targets, changes = diamond(), [endpoint("D")], [endpoint("B")]
    before = copy.deepcopy((graph, targets, changes))
    result = plan(graph, changes, targets)
    expected = copy.deepcopy(result)
    assert (graph, targets, changes) == before
    result["targets"][0]["model"] = "mutated"
    result["changed_outputs"][0]["port"] = "mutated"
    for key in ("order", "reasons", "affected_models", "unaffected_models"):
        result[key].append("mutated")
    assert (graph, targets, changes) == before
    assert plan(graph, changes, targets) == expected
    other = plan(graph, changes, targets)
    graph["models"][0]["outputs"][0]["name"] = "different"
    targets[0]["model"] = "different"
    changes[0]["port"] = "different"
    assert other == expected
