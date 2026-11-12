from copy import deepcopy
from decimal import Decimal

import pytest

from physimesh.drone import multi_rotor_mission as m

from .test_model_graph_execution import edge, hover, node, target


@pytest.fixture
def mission():
    inputs = hover()
    inputs.pop("density_kg_m3")
    graph = {
        "evaluation": m.GRAPH_EVALUATION,
        "nodes": [
            node("air", "reference_air_properties",
                 {"altitude_m": 20000, "altitude_kind": "geometric"}),
            *[node(r, "isolated_hover_bemt_experimental", deepcopy(inputs))
              for r in ("r1", "r2")],
        ],
        "connections": [edge("air", "density_kg_m3", r, "density_kg_m3")
                        for r in ("r1", "r2")],
        "targets": [target(r, "shaft_power_w") for r in ("r1", "r2")],
    }
    return {
        "evaluation": m.EVALUATION, "usable_energy_j": 1e6, "reserve_fraction": .2,
        "segments": [
            {"id": sid, "duration_s": duration, "graph": deepcopy(graph),
             "rotors": [{"node": r, "conversion_efficiency": efficiency,
                         "conversion_source": "synthetic"}
                        for r, efficiency in (("r1", .8), ("r2", .5))],
             "auxiliary_power_w": 11}
            for sid, duration in (("first", 10), ("second", 20))
        ],
    }


def test_graph_energy_order_metadata_and_isolation(mission, monkeypatch):
    original = deepcopy(mission)
    real = m.evaluate_reference_air_graph
    direct = [real(deepcopy(s["graph"])) for s in mission["segments"]]
    captured = []

    def wrapper(graph):
        raw = real(graph)
        captured.append(raw)
        graph["nodes"].clear()
        return raw

    monkeypatch.setattr(m, "evaluate_reference_air_graph", wrapper)
    result = m.evaluate_multi_rotor_mission(mission)
    assert mission == original
    assert len(captured) == 2
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["diagnostics_complete"] is True and result["reasons"] == []
    assert result["evaluation"] == m.EVALUATION
    assert result["evidence_level"] == "unverified" and result["limitations"]
    for key in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert result[key] == "NOT_ESTABLISHED"
    assert result["aircraft_status"] is None and result["feasibility"] is None
    assert result["request_sha256"] == m.sha256_record(original)
    cumulative = Decimal(0)
    budget = Decimal(1000000) * (1 - Decimal(".2"))
    assert [r["segment_id"] for r in result["segments"]] == ["first", "second"]
    for segment, row, raw in zip(original["segments"], result["segments"], direct):
        converted = []
        assert [r["node"] for r in row["rotors"]] == ["r1", "r2"]
        for declaration, rotor in zip(segment["rotors"], row["rotors"]):
            power = raw["outputs"][declaration["node"]]["shaft_power_w"]
            efficiency = declaration["conversion_efficiency"]
            converted.append(Decimal(str(power)) / Decimal(str(efficiency)))
            assert rotor["shaft_power_w"] == power
            assert rotor["conversion_efficiency"] == efficiency
            assert rotor["electrical_power_w"] == pytest.approx(
                float(converted[-1]), rel=2e-14, abs=1e-10
            )
        electrical = sum(converted) + Decimal(11)
        energy = electrical * Decimal(segment["duration_s"])
        cumulative += energy
        assert row["duration_s"] == segment["duration_s"]
        assert row["auxiliary_power_w"] == 11
        for key, expected in (("electrical_power_w", electrical), ("segment_energy_j", energy),
                              ("cumulative_energy_j", cumulative),
                              ("remaining_budget_j", budget - cumulative)):
            assert row[key] == pytest.approx(float(expected), rel=2e-14, abs=1e-10)
        assert row["graph_request_sha256"] == m.sha256_record(segment["graph"])
        assert row["graph_result_sha256"] == m.sha256_record(raw)
    outputs = result["outputs"]
    for key, expected in (("elapsed_s", 30), ("total_energy_j", float(cumulative)),
                          ("total_energy_wh", float(cumulative / 3600)),
                          ("held_reserve_j", 200000), ("mission_budget_j", float(budget)),
                          ("remaining_budget_j", float(budget - cumulative))):
        assert outputs[key] == pytest.approx(expected, rel=2e-14, abs=1e-10)
    assert outputs["budget_status"] == ("WITHIN_DECLARED_ENERGY" if cumulative <= budget
                                        else "EXCEEDS_DECLARED_ENERGY")
    assert result["output_units"] == {
        "elapsed_s": "s",
        "total_energy_j": "J",
        "total_energy_wh": "Wh",
        "held_reserve_j": "J",
        "mission_budget_j": "J",
        "remaining_budget_j": "J",
        "budget_status": "not_applicable",
    }
    captured[0]["outputs"]["r1"]["shaft_power_w"] = -1
    assert result["segments"][0]["rotors"][0]["shaft_power_w"] >= 0


@pytest.mark.parametrize("fault", ["unknownroot", "duplicateid", "duplicate_rotor",
    "literal_density", "wrongtarget", "badauxbool", "badeffNaN", "hugeint", "lateinvalid"])
def test_complete_preflight_before_execution(mission, monkeypatch, fault):
    later = mission["segments"][1]
    if fault == "unknownroot": mission["unknown"] = 1
    elif fault == "duplicateid": later["id"] = mission["segments"][0]["id"]
    elif fault == "duplicate_rotor": later["rotors"].append(deepcopy(later["rotors"][0]))
    elif fault == "literal_density": later["graph"]["nodes"][1]["inputs"]["density_kg_m3"] = 1
    elif fault == "wrongtarget": later["graph"]["targets"][0]["port"] = "thrust_n"
    elif fault == "badauxbool": later["auxiliary_power_w"] = True
    elif fault == "badeffNaN": later["rotors"][0]["conversion_efficiency"] = float("nan")
    elif fault == "hugeint": later["duration_s"] = 10 ** 400
    else: later["duration_s"] = 0
    calls = []
    monkeypatch.setattr(m, "evaluate_reference_air_graph", lambda graph: calls.append(graph))
    result = m.evaluate_multi_rotor_mission(mission)
    assert calls == [] and result["status"] == "GRAPH_INVALID"
    assert not result["diagnostics_complete"] and result["reasons"]
    assert result["segments"] == [] and result["outputs"] == result["output_units"] == {}


@pytest.mark.parametrize("fault", ["evaluation", "status", "diagnostics_complete",
    "evidence_level", "reasons", "request_sha256", "physical_validation",
    "numerical_qualification", "runtime_identity", "feasibility", "aircraft_status",
    "units", "negativepower", "second_exception"])
def test_execution_failure_is_atomic(mission, monkeypatch, fault):
    real, calls = m.evaluate_reference_air_graph, []
    def wrapper(graph):
        calls.append(graph)
        if fault == "second_exception" and len(calls) == 2: raise RuntimeError("synthetic")
        raw = real(graph)
        if fault == "units": raw["output_units"]["r1"]["shaft_power_w"] = "kW"
        elif fault == "negativepower": raw["outputs"]["r1"]["shaft_power_w"] = -1
        elif fault != "second_exception": raw[fault] = "malformed"
        return raw
    monkeypatch.setattr(m, "evaluate_reference_air_graph", wrapper)
    result = m.evaluate_multi_rotor_mission(mission)
    assert len(calls) == (2 if fault == "second_exception" else 1)
    assert result["status"] == "EXECUTION_FAILED" and result["diagnostics_complete"] is False
    assert result["reasons"] == ["Multi-rotor mission execution refused."]
    assert result["segments"] == [] and result["outputs"] == result["output_units"] == {}
    assert result["request_sha256"] == m.sha256_record(mission)


@pytest.fixture
def tiny_budget(mission):
    mission["usable_energy_j"] = 1.0
    return mission


def test_budget_crossing_keeps_complete_results(tiny_budget):
    result = m.evaluate_multi_rotor_mission(tiny_budget)
    assert result["status"] == "COMPUTED_EXPERIMENTAL" and len(result["segments"]) == 2
    assert result["outputs"]["budget_status"] == "EXCEEDS_DECLARED_ENERGY"
    assert result["outputs"]["remaining_budget_j"] < 0
    assert result["outputs"]["mission_budget_j"] == pytest.approx(.8, rel=2e-14, abs=1e-10)
    assert result["outputs"]["held_reserve_j"] == pytest.approx(.2, rel=2e-14, abs=1e-10)
