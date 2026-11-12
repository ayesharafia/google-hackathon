from copy import deepcopy

import pytest

from physimesh.drone import ledger_dynamics_refinement as m
from physimesh.drone.provenance import sha256_record

from .test_ledger_rotor_dynamics import request as dynamics_request


def request():
    return {"evaluation": m.EVALUATION, "dynamics": dynamics_request()}


def test_real_runs(monkeypatch):
    body = request()
    original = deepcopy(body)
    real = m.ld.evaluate_ledger_rotor_dynamics
    calls = []

    def wrapped(input):
        result = real(input)
        calls.append((deepcopy(input), deepcopy(result)))
        return result

    monkeypatch.setattr(m.ld, "evaluate_ledger_rotor_dynamics", wrapped)
    result = m.evaluate_ledger_dynamics_refinement(body)

    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert body == original
    assert len(calls) == 3
    assert [input["dt_s"] for input, _ in calls] == [
        0.01, 0.005, 0.0025
    ]
    assert [input["steps"] for input, _ in calls] == [10, 20, 40]
    assert len(result["outputs"]["runs"]) == len(result["stages"]) == 3

    for run, stage, (input, raw) in zip(
        result["outputs"]["runs"], result["stages"], calls
    ):
        assert input["dt_s"] * input["steps"] == pytest.approx(0.1)
        assert result["outputs"]["horizon_s"] == pytest.approx(0.1)
        assert run["final_state"] == raw["outputs"]["frozen_dynamics"]["dynamics"]["final_state"]
        assert stage["request_sha256"] == sha256_record(input)
        assert stage["result_sha256"] == sha256_record(raw)

    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["evidence_level"] == "unverified"
    assert result["feasibility"] is None


@pytest.mark.parametrize(
    "defect", ["steps251", "boolsteps", "rootextra", "zerodt", "underflowdt"]
)
def test_bad_preflight(monkeypatch, defect):
    body = deepcopy(request())
    if defect == "steps251":
        body["dynamics"]["steps"] = 251
    elif defect == "boolsteps":
        body["dynamics"]["steps"] = True
    elif defect == "rootextra":
        body["extra"] = 1
    elif defect == "zerodt":
        body["dynamics"]["dt_s"] = 0
    else:
        body["dynamics"].update(dt_s=2.2250738585072014e-308, steps=1)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Evaluator must not run")

    monkeypatch.setattr(m.ld, "evaluate_ledger_rotor_dynamics", forbidden)
    result = m.evaluate_ledger_dynamics_refinement(body)
    assert result["status"] == "GRAPH_INVALID"
    assert "request_sha256" not in result
    assert result["stages"] == []
    assert result["outputs"] == result["output_units"] == {}
    assert calls == []


def test_late_failure(monkeypatch):
    body = deepcopy(request())
    expected_hash = sha256_record(body)
    actual = m.ld.evaluate_ledger_rotor_dynamics
    calls = 0

    def fail_third(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("PRIVATE_FAILURE")
        return actual(*args, **kwargs)

    monkeypatch.setattr(m.ld, "evaluate_ledger_rotor_dynamics", fail_third)
    result = m.evaluate_ledger_dynamics_refinement(body)
    assert calls == 3
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == expected_hash
    assert result["stages"] == []
    assert result["outputs"] == result["output_units"] == {}
    assert result["diagnostics_complete"] is False
    assert "PRIVATE_FAILURE" not in repr(result)
    assert "RuntimeError" not in repr(result)


def test_comparison_math(monkeypatch):
    real_state = m._state

    def synthetic_state(raw, run_request):
        state = real_state(raw, run_request)
        factor = .01 / run_request["dt_s"]
        state.update(
            position_enu_m=[factor**-4, 0, 0],
            velocity_enu_m_s=[0, 0, 0],
            angular_velocity_body_rad_s=[0, 0, 0],
            quaternion_body_to_enu=[-1, 0, 0, 0] if factor == 2 else [1, 0, 0, 0],
        )
        return state

    monkeypatch.setattr(m, "_state", synthetic_state)
    result = m.evaluate_ledger_dynamics_refinement(request())
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    c = result["outputs"]["comparisons"]
    assert c["position_enu_m"]["coarse_medium"] == pytest.approx(15 / 16)
    assert c["position_enu_m"]["medium_fine"] == pytest.approx(15 / 256)
    assert c["position_enu_m"]["observed_order"] == pytest.approx(4)
    assert c["position_enu_m"]["order_status"] == "DEFINED_NOT_QUALIFIED"
    for name in ("quaternion_body_to_enu", "velocity_enu_m_s", "angular_velocity_body_rad_s"):
        assert c[name]["coarse_medium"] == c[name]["medium_fine"] == 0
        assert c[name]["observed_order"] is None
        assert c[name]["order_status"] == "UNDEFINED_ZERO_DIFFERENCE"
    assert "tolerance_pass" not in repr(result)
    assert "aircraft_qualification" not in repr(result)


@pytest.mark.parametrize("fault", ["unit", "quaternion", "elapsed"])
def test_bad_upstream(monkeypatch, fault):
    real = m.ld.evaluate_ledger_rotor_dynamics

    def wrapper(rawinput):
        result = real(rawinput)
        if fault == "unit":
            result["output_units"]["frozen_dynamics"]["dynamics"]["final_state"]["position_enu_m"] = "cm"
        elif fault == "quaternion":
            result["outputs"]["frozen_dynamics"]["dynamics"]["final_state"]["quaternion_body_to_enu"] = [2, 0, 0, 0]
        else:
            result["outputs"]["frozen_dynamics"]["dynamics"]["elapsed_s"] = 99
        return result

    monkeypatch.setattr(m.ld, "evaluate_ledger_rotor_dynamics", wrapper)
    body = request()
    before = deepcopy(body)
    result = m.evaluate_ledger_dynamics_refinement(body)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == sha256_record(body)
    assert result["diagnostics_complete"] is False
    assert result["stages"] == []
    assert result["outputs"] == {}
    assert result["output_units"] == {}
    assert body == before
