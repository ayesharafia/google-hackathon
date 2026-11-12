from copy import deepcopy

from physimesh.drone.reference_air_graph import EVALUATION, evaluate_reference_air_graph
from physimesh.drone.reference_air_properties import reference_air_properties


def test_air_node():
    request = {
        "evaluation": EVALUATION,
        "nodes": [
            {
                "id": "air",
                "model": "reference_air_properties",
                "inputs": {"altitude_m": 1000, "altitude_kind": "geometric"},
            }
        ],
        "connections": [],
        "targets": [
            {"node": "air", "port": "dynamic_viscosity_pa_s"},
            {"node": "air", "port": "speed_of_sound_m_s"},
            {"node": "air", "port": "gravity_m_s2"},
        ],
    }
    original = deepcopy(request)
    direct = reference_air_properties(altitude_m=1000, altitude_kind="geometric")
    result = evaluate_reference_air_graph(request)

    assert request == original
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["stage_order"] == ["air"]
    for port, unit in {
        "dynamic_viscosity_pa_s": "Pa*s",
        "speed_of_sound_m_s": "m/s",
        "gravity_m_s2": "m/s^2",
    }.items():
        assert result["outputs"]["air"][port] == getattr(direct, port)
        assert result["output_units"]["air"][port] == unit
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["runtime_identity"] == "NOT_ESTABLISHED"
    assert result["numerical_qualification"] == "NOT_ESTABLISHED"
    assert result["aircraft_status"] is None
    assert result["feasibility"] is None


def test_air_to_wing():
    from physimesh.drone.fixed_wing import screen_fixed_wing
    from tests.drone.test_model_graph_execution import edge, node, target, wing

    w = wing()
    props = ("density_kg_m3", "dynamic_viscosity_pa_s", "speed_of_sound_m_s")
    for p in props:
        w.pop(p, None)
    ports = ("reynolds_number", "mach_number", "drag_n")
    request = {
        "evaluation": EVALUATION,
        "nodes": [
            node("air", "reference_air_properties",
                 {"altitude_m": 1000, "altitude_kind": "geometric"}),
            node("wing", "fixed_wing_aerodynamic_screening", w),
        ],
        "connections": [edge("air", p, "wing", p) for p in props],
        "targets": [target("wing", p) for p in ports],
    }
    original = deepcopy(request)
    directair = reference_air_properties(altitude_m=1000, altitude_kind="geometric")
    expected = screen_fixed_wing(w | {p: (directair.state.density_kg_m3 if p == "density_kg_m3" else getattr(directair, p)) for p in props})
    result = evaluate_reference_air_graph(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["stage_order"] == ["air", "wing"]
    assert result["outputs"] == {"wing": {p: expected["outputs"][p] for p in ports}}
    assert result["output_units"] == {
        "wing": {"reynolds_number": "1", "mach_number": "1", "drag_n": "N"}
    }
    assert len(result["transfers"]) == 3
    assert request == original


def test_invalid_graph_executes_nothing(monkeypatch):
    from physimesh.drone import reference_air_graph as graph

    base = {
        "evaluation": graph.EVALUATION,
        "nodes": [{"id": "air", "model": "reference_air_properties",
                   "inputs": {"altitude_m": 1000, "altitude_kind": "geometric"}}],
        "connections": [],
        "targets": [{"node": "air", "port": "gravity_m_s2"}],
    }
    def forbidden(*args, **kwargs):
        raise AssertionError('component executed before rejection')
    monkeypatch.setattr(graph, '_component', forbidden)
    mutations = [
        lambda r: r.update(extra=True),
        lambda r: r["nodes"][0].update(model="unknown"),
        lambda r: r["nodes"][0]["inputs"].update(altitude_m=True),
        lambda r: r["targets"].append(deepcopy(r["targets"][0])),
        lambda r: r["nodes"][0]["inputs"].pop("altitude_kind"),
        lambda r: r["connections"].append({"from_node":"air","from_port":"gravity_m_s2","to_node":"air","to_port":"altitude_m"}),
    ]
    for mutate in mutations:
        request = deepcopy(base)
        mutate(request)
        result = graph.evaluate_reference_air_graph(request)
        assert result["status"] == "GRAPH_INVALID" and result["outputs"] == {} and result["output_units"] == {}
        assert result["stages"] == [] and result["transfers"] == [] and "request_sha256" not in result
