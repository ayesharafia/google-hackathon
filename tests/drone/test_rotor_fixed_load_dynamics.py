from copy import deepcopy

import pytest

from physimesh.drone import rotor_fixed_load_dynamics as m
from physimesh.drone.rigid_body_request import evaluate_rigid_body

from .test_rotor_assembly import request as assembly_request


def request():
    return {
        "evaluation": m.EVALUATION,
        "assembly": assembly_request(),
        "initial_state": {
            "position_enu_m": [0, 0, 0],
            "velocity_enu_m_s": [0, 0, 0],
            "quaternion_body_to_enu": [1, 0, 0, 0],
            "angular_velocity_body_rad_s": [0, 0, 0],
        },
        "inertia_body_kg_m2": [[1, 0, 0], [0, 2, 0], [0, 0, 3]],
        "dt_s": .01,
        "steps": 10,
        "applicability_declaration": "Synthetic frozenloads",
    }


def test_real_composition():
    b = request()
    before = deepcopy(b)
    direct = m.ra.evaluate_rotor_assembly(b["assembly"])
    force, moment, gravity = m._assembly_loads(direct, b["assembly"])
    dynamic, raw = m._run_dynamics(b, force, moment, gravity)
    r = m.evaluate_rotor_fixed_load_dynamics(b)
    assert r["status"] == "COMPUTED_EXPERIMENTAL"
    assert r["outputs"]["assembly"] == direct["outputs"]
    assert r["outputs"]["dynamics"] == raw["outputs"]
    assert raw == evaluate_rigid_body(dynamic)
    assert b == before
    assert r["request_sha256"] == m.sha256_record(b)
    assert len(r["stages"]) == 2
    assert r["transfers"]["gravity_enu_m_s2"] == list(gravity)
    assert gravity[:2] == (0, 0) and gravity[2] < 0
    assert r["evidence_level"] == "unverified"
    assert all(r[k] == "NOT_ESTABLISHED" for k in ("physical_validation", "numerical_qualification", "runtime_identity"))
    assert r["feasibility"] is None


def test_vertical_analytic_gravity_once():
    b = request()
    direct = m.ra.evaluate_rotor_assembly(b["assembly"])
    force, moment, gravity = m._assembly_loads(direct, b["assembly"])
    assert force[:2] == (0, 0) and moment == (0, 0, 0)
    dynamic, raw = m._run_dynamics(b, force, moment, gravity)
    acceleration = force[2] / dynamic["mass_kg"] + gravity[2]
    final = raw["outputs"]["final_state"]
    assert final["velocity_enu_m_s"][2] == pytest.approx(acceleration * .1, rel=1e-12, abs=1e-12)
    assert final["position_enu_m"][2] == pytest.approx(.5 * acceleration * .1**2, rel=1e-12, abs=1e-12)


@pytest.mark.parametrize("bad", ["axisgravity", "quat", "booldt", "steps", "inertia"])
def test_invalid_requests(monkeypatch, bad):
    b, calls = request(), []
    original = m.ra.evaluate_rotor_assembly
    def record(assembly):
        calls.append(deepcopy(assembly))
        return original(assembly)
    monkeypatch.setattr(m.ra, "evaluate_rotor_assembly", record)
    if bad == "axisgravity": b["assembly"]["gravity_direction_body"] = [0, -9.81, 0]
    elif bad == "quat": b["initial_state"]["quaternion_body_to_enu"] = [0, 1, 0, 0]
    elif bad == "booldt": b["dt_s"] = True
    elif bad == "steps": b["steps"] = 1001
    else: b["inertia_body_kg_m2"][0][0] = -1
    r = m.evaluate_rotor_fixed_load_dynamics(b)
    assert r["outputs"] == {}
    assert len(calls) == (1 if bad == "inertia" else 0)
    assert r["status"] == ("EXECUTION_FAILED" if bad == "inertia" else "GRAPH_INVALID")


@pytest.mark.parametrize("fault", ["assembly_units", "dynamics_units", "dynamics_state", "late_exception"])
def test_execution_failure_is_atomic(monkeypatch, fault):
    import physimesh.drone.rigid_body_request as q

    payload = request()
    original = deepcopy(payload)
    target = m.ra if fault == "assembly_units" else q
    name = "evaluate_rotor_assembly" if fault == "assembly_units" else "evaluate_rigid_body"
    real = getattr(target, name)

    def wrapped(*args, **kwargs):
        raw = real(*args, **kwargs)
        if fault == "assembly_units":
            raw["output_units"]["net_force_body_n"] = "kN"
        elif fault == "dynamics_units":
            raw["output_units"]["elapsed_s"] = "ms"
        elif fault == "dynamics_state":
            raw["outputs"]["final_state"]["quaternion_body_to_enu"] = [2, 0, 0, 0]
        else:
            raise RuntimeError("private")
        return raw

    monkeypatch.setattr(target, name, wrapped)
    result = m.evaluate_rotor_fixed_load_dynamics(payload)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["diagnostics_complete"] is False
    assert result["stages"] == []
    assert result["transfers"] == {}
    assert result["outputs"] == {}
    assert result["output_units"] == {}
    assert result["request_sha256"]
    assert "private" not in str(result)
    assert payload == original
