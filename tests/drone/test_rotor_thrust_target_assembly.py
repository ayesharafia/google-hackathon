import math
from copy import deepcopy

import pytest

from physimesh.drone import rotor_thrust_target_assembly as m
from physimesh.drone.provenance import sha256_record

from .test_rotor_assembly import request as assembly_request


def request():
    a = assembly_request()
    for node in a["graph"]["nodes"]:
        if node["model"] == "isolated_hover_bemt_experimental":
            del node["inputs"]["angular_speed_rad_s"]
    return {
        "evaluation": m.EVALUATION,
        "assembly_template": a,
        "targets": [
            {
                "node": r["node"],
                "target_thrust_n": 5.0,
                "angular_speed_bracket_rad_s": [100.0, 500.0],
                "absolute_thrust_tolerance_n": 0.001,
                "max_evaluations": 32,
            }
            for r in a["rotors"]
        ],
    }


def test_real_composition():
    body = request()
    before = deepcopy(body)
    result = m.evaluate_rotor_thrust_target_assembly(body)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert body == before
    assert result["request_sha256"] == sha256_record(before)
    air = m.ag.evaluate_reference_air_graph(m._air_request(body))
    density = air["outputs"][body["assembly_template"]["air_node"]]["density_kg_m3"]
    speeds = {}
    for entry in body["targets"]:
        inverse = m.ht.evaluate_hover_thrust_target(
            m._inverse_request(body, entry, density)
        )
        speeds[entry["node"]] = inverse["outputs"]["best_candidate"]["angular_speed_rad_s"]
    actual = m.ra.evaluate_rotor_assembly(m._assembly_input(body, speeds))
    assert result["outputs"]["assembly"] == actual["outputs"]
    assert result["outputs"]["air"] == air["outputs"]
    for rotor in actual["outputs"]["rotors"]:
        assert math.hypot(*rotor["force_body_n"]) == pytest.approx(5, abs=0.001)
    assert len(result["stages"]) == 4


@pytest.mark.parametrize("defect", [
    "speed_conflict", "target_order", "budget", "missingtarget",
])
def test_preflight(monkeypatch, defect):
    body = deepcopy(request())
    if defect == "speed_conflict":
        node = next(n for n in body["assembly_template"]["graph"]["nodes"]
                    if n["model"] == "isolated_hover_bemt_experimental")
        node["inputs"]["angular_speed_rad_s"] = 100.0
    elif defect == "target_order":
        body["targets"].reverse()
    elif defect == "budget":
        body["targets"][0]["max_evaluations"] = 65
    else:
        body["targets"].pop()
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise RuntimeError("UNEXPECTED_MODEL_CALL")

    monkeypatch.setattr(m.ag, "evaluate_reference_air_graph", forbidden)
    result = m.evaluate_rotor_thrust_target_assembly(body)
    assert result["status"] == "GRAPH_INVALID"
    assert "request_sha256" not in result
    assert result["diagnostics_complete"] is False
    assert [result[k] for k in ("outputs", "output_units", "stages", "transfers")] == [{}, {}, [], {}]
    assert calls == []


def test_unmet_target():
    body = deepcopy(request())
    body["targets"][0]["target_thrust_n"] = 1e9
    result = m.evaluate_rotor_thrust_target_assembly(body)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == sha256_record(body)
    assert result["diagnostics_complete"] is False
    assert [result[k] for k in ("outputs", "output_units", "stages", "transfers")] == [{}, {}, [], {}]


def test_private_exception(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE_INVERSE")
    monkeypatch.setattr(m.ht, "evaluate_hover_thrust_target", fail)
    body = deepcopy(request())
    result = m.evaluate_rotor_thrust_target_assembly(body)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == sha256_record(body)
    assert result["diagnostics_complete"] is False
    assert [result[k] for k in ("outputs", "output_units", "stages", "transfers")] == [{}, {}, [], {}]
    assert "PRIVATE_INVERSE" not in str(result)


@pytest.mark.parametrize('fault', ['air_units', 'inverse_units', 'assembly_units', 'assembly_force', 'late_exception'])
def test_upstream_failure(monkeypatch, fault):
    body = request()
    original = deepcopy(body)
    expected_hash = sha256_record(original)
    if fault == 'air_units':
        target, name = m.ag, 'evaluate_reference_air_graph'
    elif fault == 'inverse_units':
        target, name = m.ht, 'evaluate_hover_thrust_target'
    else:
        target, name = m.ra, 'evaluate_rotor_assembly'
    real = getattr(target, name)

    def wrapped(payload):
        raw = real(payload)
        if fault == 'air_units':
            raw['output_units'][payload['nodes'][0]['id']]['density_kg_m3'] = 'kg'
        elif fault == 'inverse_units':
            raw['output_units']['best_candidate']['thrust_n'] = 'kN'
        elif fault == 'assembly_units':
            raw['output_units']['net_force_body_n'] = 'kN'
        elif fault == 'assembly_force':
            raw['outputs']['rotors'][0]['force_body_n'] = [0, 0, 9]
        else:
            raise RuntimeError('PRIVATE_FINAL')
        return raw

    monkeypatch.setattr(target, name, wrapped)
    result = m.evaluate_rotor_thrust_target_assembly(body)
    assert result['status'] == 'EXECUTION_FAILED'
    assert result['request_sha256'] == expected_hash
    assert result['diagnostics_complete'] is False
    assert result['stages'] == []
    assert result['transfers'] == {}
    assert result['outputs'] == {}
    assert result['output_units'] == {}
    assert 'PRIVATE_FINAL' not in repr(result)
    assert body == original
