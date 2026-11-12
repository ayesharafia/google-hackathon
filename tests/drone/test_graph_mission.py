from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from physimesh.drone import graph_mission as gm
from physimesh.drone.graph_mission import EVALUATION, evaluate_graph_mission
from physimesh.drone.provenance import sha256_record
from physimesh.drone.reference_air_graph import EVALUATION as GRAPH_EVALUATION
from physimesh.drone.reference_air_graph import evaluate_reference_air_graph

from .test_model_graph_execution import edge, hover, node, target, wing


def mission():
    w = wing()
    props = ("density_kg_m3", "dynamic_viscosity_pa_s", "speed_of_sound_m_s")
    for p in props:
        w.pop(p)
    g = {
        "evaluation": GRAPH_EVALUATION,
        "nodes": [
            node("air", "reference_air_properties", {"altitude_m": 1000, "altitude_kind": "geometric"}),
            node("wing", "fixed_wing_aerodynamic_screening", w),
        ],
        "connections": [edge("air", p, "wing", p) for p in props],
        "targets": [target("wing", "drag_power_w")],
    }
    s = {
        "id": "loiter",
        "duration_s": 60,
        "graph": g,
        "power_node": "wing",
        "power_port": "drag_power_w",
        "conversion_efficiency": 0.8,
        "auxiliary_power_w": 100,
        "conversion_source": "Synthetic unverified combined efficiency",
    }
    return {
        "evaluation": EVALUATION,
        "usable_energy_j": 1e7,
        "reserve_fraction": 0.2,
        "segments": [s, s | {"id": "return", "duration_s": 30}],
    }


def test_mission_computes_without_mutating_request():
    request = mission()
    original = deepcopy(request)
    actual = evaluate_graph_mission(request)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL"
    assert request == original
    assert {k: actual["outputs"][k] for k in ("elapsed_s", "held_reserve_j", "mission_budget_j")} == {
        "elapsed_s": 90,
        "held_reserve_j": 2e6,
        "mission_budget_j": 8e6,
    }
    assert actual["outputs"]["total_energy_j"] > 0 and actual["feasibility"] is None


def test_independent_energy_oracle():
    body = mission()
    actual = evaluate_graph_mission(body)
    direct = evaluate_reference_air_graph(body["segments"][0]["graph"])
    power = direct["outputs"]["wing"]["drag_power_w"]
    with localcontext() as ctx:
        ctx.prec = 80
        expected = (Decimal.from_float(power) / Decimal.from_float(0.8) + Decimal(100)) * Decimal(90)
        expected_wh = expected / Decimal(3600)
        remaining = Decimal(8000000) - expected
    outputs = actual["outputs"]
    assert outputs["total_energy_j"] == pytest.approx(float(expected), rel=3e-15)
    assert outputs["total_energy_wh"] == pytest.approx(float(expected_wh), rel=3e-15)
    assert outputs["remaining_budget_j"] == pytest.approx(float(remaining), rel=3e-15)
    assert outputs["budget_status"] == "WITHIN_DECLARED_ENERGY"
    assert actual["output_units"]["total_energy_j"] == "J"
    assert actual["output_units"]["total_energy_wh"] == "Wh"
    assert [s["segment_id"] for s in actual["segments"]] == ["loiter", "return"]
    for source, segment in zip(body["segments"], actual["segments"], strict=True):
        reference = evaluate_reference_air_graph(source["graph"])
        assert segment["graph_request_sha256"] == sha256_record(source["graph"])
        assert segment["graph_result_sha256"] == sha256_record(reference)
    assert actual["request_sha256"] == sha256_record(body)
    for key in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert actual[key] == "NOT_ESTABLISHED"


def test_short_budget():
    body = mission()
    body["usable_energy_j"] = 1
    actual = evaluate_graph_mission(body)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL" and actual["outputs"]["remaining_budget_j"] < 0
    assert actual["outputs"]["budget_status"] == "EXCEEDS_DECLARED_ENERGY" and actual["feasibility"] is None


@pytest.mark.parametrize(
    "defect",
    [
        "bool_duration",
        "bad_efficiency",
        "missing_convention",
        "duplicate_id",
        "wrong_power_port",
        "cycle",
        "extra_field",
    ],
)
def test_preflight_no_execute(monkeypatch, defect):
    b = mission()
    last = b["segments"][-1]
    last["graph"] = deepcopy(last["graph"])
    if defect == "bool_duration":
        last["duration_s"] = True
    elif defect == "bad_efficiency":
        last["conversion_efficiency"] = 0
    elif defect == "missing_convention":
        last["graph"]["nodes"][0]["inputs"].pop("altitude_kind")
    elif defect == "duplicate_id":
        last["id"] = b["segments"][0]["id"]
    elif defect == "wrong_power_port":
        last["power_port"] = "thrust_n"
    elif defect == "cycle":
        last["graph"]["connections"].append(
            {"from_node": "air", "from_port": "gravity_m_s2", "to_node": "air", "to_port": "altitude_m"}
        )
    else:
        b["extra"] = True
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Execution forbidden during preflight")

    monkeypatch.setattr(gm, "evaluate_reference_air_graph", forbidden)
    actual = gm.evaluate_graph_mission(b)
    assert actual["status"] == "GRAPH_INVALID"
    assert actual["outputs"] == {} and actual["output_units"] == {} and actual["segments"] == []
    assert "request_sha256" not in actual and calls == []


def test_second_execution_failure(monkeypatch):
    b = mission()
    original, calls = gm.evaluate_reference_air_graph, []

    def tracked(graph):
        calls.append(graph)
        if len(calls) == 2:
            raise RuntimeError("PRIVATESECRET")
        return original(graph)

    monkeypatch.setattr(gm, "evaluate_reference_air_graph", tracked)
    actual = gm.evaluate_graph_mission(b)
    assert len(calls) == 2
    assert actual["status"] == "EXECUTION_FAILED"
    assert len(actual["segments"]) == 1
    assert actual["outputs"] == {} and actual["output_units"] == {}
    assert actual["diagnostics_complete"] is False and "PRIVATESECRET" not in str(actual)


def test_actual_hover_wing_sequence():
    # Disconnected constant-condition snapshots; no transition or flight closure.
    b = mission()
    baseline = gm.evaluate_graph_mission(deepcopy(b))
    h = hover()
    h.pop("density_kg_m3")
    g = deepcopy(b["segments"][0]["graph"])
    g["nodes"][1] = {"id": "rotor", "model": "isolated_hover_bemt_experimental", "inputs": h}
    g["nodes"][0]["inputs"]["altitude_m"] = 20000
    g["connections"] = [
        {"from_node": "air", "from_port": "density_kg_m3", "to_node": "rotor", "to_port": "density_kg_m3"}
    ]
    g["targets"] = [{"node": "rotor", "port": "shaft_power_w"}]
    first = deepcopy(b["segments"][0])
    first.update(id="hover_snapshot", graph=g, power_node="rotor", power_port="shaft_power_w", duration_s=10)
    wingsegment = deepcopy(b["segments"][0])
    wingsegment.update(id="wing_snapshot", duration_s=20)
    wingsegment["graph"]["nodes"][0]["inputs"]["altitude_m"] = 20000
    b["segments"] = [first, wingsegment]
    actual = gm.evaluate_graph_mission(b)
    direct = [gm.evaluate_reference_air_graph(deepcopy(s["graph"])) for s in b["segments"]]
    expectedtotal = sum(
        (d["outputs"][s["power_node"]][s["power_port"]] / s["conversion_efficiency"] + s["auxiliary_power_w"])
        * s["duration_s"]
        for s, d in zip(b["segments"], direct, strict=True)
    )
    assert actual["status"] == "COMPUTED_EXPERIMENTAL"
    assert actual["outputs"]["total_energy_j"] == pytest.approx(expectedtotal, rel=3e-15)
    assert [s["segment_id"] for s in actual["segments"]] == ["hover_snapshot", "wing_snapshot"]
    assert actual["segments"][1]["cumulative_energy_j"] == actual["outputs"]["total_energy_j"]
    for key in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert actual[key] == baseline[key] == "NOT_ESTABLISHED"
    assert actual["feasibility"] is None
