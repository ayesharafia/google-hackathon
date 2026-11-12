from copy import deepcopy

import pytest

from physimesh.drone import rotor_assembly as assembly
from physimesh.drone.provenance import sha256_record
from physimesh.drone.reference_air_graph import EVALUATION as GRAPH_EVALUATION
from physimesh.drone.reference_air_graph import evaluate_reference_air_graph

from .test_model_graph_execution import edge, hover, node, target


def request():
    h = hover()
    h.pop("density_kg_m3")
    g = {
        "evaluation": GRAPH_EVALUATION,
        "nodes": [
            node("air", "reference_air_properties", {"altitude_m": 20000, "altitude_kind": "geometric"})
        ]
        + [node(n, "isolated_hover_bemt_experimental", deepcopy(h)) for n in ("r1", "r2")],
        "connections": [edge("air", "density_kg_m3", n, "density_kg_m3") for n in ("r1", "r2")],
        "targets": [target("air", "gravity_m_s2")]
        + [target(n, k) for n in ("r1", "r2") for k in ("thrust_n", "shaft_torque_nm")],
    }
    return {
        "evaluation": assembly.EVALUATION,
        "graph": g,
        "air_node": "air",
        "rotors": [
            {"node": n, "center_body_m": [x, 0, 0], "axis_body": [0, 0, 1], "rotation_sign": sign}
            for n, x, sign in (("r1", -1, 1), ("r2", 1, -1))
        ],
        "mass_kg": 10,
        "cg_body_m": [0, 0, 0],
        "gravity_direction_body": [0, 0, -1],
        "property_source": "Synthetic unverified assembly",
    }


def test_rotor_assembly():
    body = request()
    original = deepcopy(body)
    result = assembly.evaluate_rotor_assembly(body)
    assert body == original
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    direct = evaluate_reference_air_graph(body["graph"])["outputs"]
    g, t, q = direct["air"]["gravity_m_s2"], direct["r1"]["thrust_n"], direct["r1"]["shaft_torque_nm"]
    outputs = result["outputs"]
    assert outputs["net_force_body_n"] == pytest.approx([0, 0, 2 * t - 10 * g])
    assert outputs["net_moment_cg_body_nm"] == [0, 0, 0]
    assert outputs["rotors"][0]["moment_cg_body_nm"] == pytest.approx([0, t, -q])
    assert outputs["rotors"][1]["moment_cg_body_nm"] == pytest.approx([0, -t, q])
    assert result["request_sha256"] == sha256_record(body)
    assert [result[k] for k in ("physical_validation", "numerical_qualification", "runtime_identity")] == [
        "NOT_ESTABLISHED"
    ] * 3
    assert result["feasibility"] is None
    assert result["output_units"]["net_force_body_n"] == "N"


def test_cg_spin_and_axis():
    b = request()
    b["cg_body_m"] = [0.25, 0, 0]
    b["rotors"][1]["rotation_sign"] = 1
    direct = evaluate_reference_air_graph(b["graph"])["outputs"]
    t = direct["r1"]["thrust_n"]
    q = direct["r1"]["shaft_torque_nm"]
    g = direct["air"]["gravity_m_s2"]
    a = assembly.evaluate_rotor_assembly(b)
    assert a["status"] == "COMPUTED_EXPERIMENTAL"
    assert a["outputs"]["net_moment_cg_body_nm"] == pytest.approx([0, 0.5 * t, -2 * q])
    b["cg_body_m"] = [0, 0, 0]
    for rotor, center in zip(b["rotors"], ([0, -1, 0], [0, 1, 0]), strict=True):
        rotor["axis_body"] = [1, 0, 0]
        rotor["center_body_m"] = center
    a = assembly.evaluate_rotor_assembly(b)
    assert a["status"] == "COMPUTED_EXPERIMENTAL"
    assert a["outputs"]["net_force_body_n"] == pytest.approx([2 * t, 0, -10 * g])
    assert a["outputs"]["net_moment_cg_body_nm"] == pytest.approx([-2 * q, 0, 0])
    assert a["physical_validation"] == "NOT_ESTABLISHED"


@pytest.mark.parametrize(
    "defect", ["axis", "spin_bool", "duplicate_rotor", "wrong_target", "literal_density"]
)
def testinvalidpreflight(monkeypatch, defect):
    b = request()
    if defect == "axis":
        b["rotors"][-1]["axis_body"] = [0, 0, 2]
    elif defect == "spin_bool":
        b["rotors"][-1]["rotation_sign"] = True
    elif defect == "duplicate_rotor":
        b["rotors"][-1]["node"] = "r1"
    elif defect == "wrong_target":
        b["graph"]["targets"].append({"node": "r1", "port": "thrust_n"})
    else:
        b["graph"]["nodes"][1]["inputs"]["density_kg_m3"] = 1.0
    calls = []

    def forbidden(*args):
        calls.append(args)
        raise AssertionError

    monkeypatch.setattr(assembly, "evaluate_reference_air_graph", forbidden)
    actual = assembly.evaluate_rotor_assembly(b)
    assert actual["status"] == "GRAPH_INVALID"
    assert actual["outputs"] == actual["output_units"] == {}
    assert "request_sha256" not in actual
    assert calls == []


def testupstreamfailure(monkeypatch):
    def forbidden(*args):
        raise RuntimeError("PRIVATESECRET")

    monkeypatch.setattr(assembly, "evaluate_reference_air_graph", forbidden)
    actual = assembly.evaluate_rotor_assembly(request())
    assert (
        actual["status"] == "EXECUTION_FAILED"
        and actual["outputs"] == actual["output_units"] == {}
        and actual["diagnostics_complete"] is False
        and "PRIVATE" not in str(actual)
    )
