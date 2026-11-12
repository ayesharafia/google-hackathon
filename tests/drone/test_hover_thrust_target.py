from copy import deepcopy

import pytest

from physimesh.drone import hover_thrust_target as m
from physimesh.drone.provenance import sha256_record

from .test_hover_bemt_request import valid_request


def request():
    h = valid_request()
    del h["angular_speed_rad_s"]
    return {
        "evaluation": m.EVALUATION,
        "rotor_template": h,
        "target_thrust_n": 10.,
        "angular_speed_bracket_rad_s": [100., 400.],
        "absolute_thrust_tolerance_n": .001,
        "max_evaluations": 32,
    }


def test_target_matches_forward(monkeypatch):
    actual = m.hb.evaluate_hover_bemt
    calls = []

    def wrapped(payload):
        raw = actual(payload)
        calls.append((deepcopy(payload), deepcopy(raw)))
        return raw

    monkeypatch.setattr(m.hb, "evaluate_hover_bemt", wrapped)
    body = request()
    before = deepcopy(body)
    result = m.evaluate_hover_thrust_target(body)
    outputs = result["outputs"]
    candidates = outputs["candidates"]
    stages = result["stages"]

    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert outputs["outcome"] == "TARGET_RESIDUAL_MET"
    assert abs(outputs["best_candidate"]["residual_n"]) <= body["absolute_thrust_tolerance_n"]
    assert len(calls) == outputs["evaluations_used"] == len(candidates) == len(stages)
    for candidate, stage, (inp, raw) in zip(candidates, stages, calls):
        for key in ("thrust_n", "shaft_power_w", "shaft_torque_nm"):
            assert candidate[key] == raw["outputs"][key]
        assert candidate["residual_n"] == candidate["thrust_n"] - body["target_thrust_n"]
        assert candidate["request_sha256"] == sha256_record(inp)
        assert stage["request_sha256"] == sha256_record(inp)
        assert candidate["result_sha256"] == sha256_record(raw)
        assert stage["result_sha256"] == sha256_record(raw)
    assert body == before
    assert result["request_sha256"] == sha256_record(before)
    for key in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert result[key] == "NOT_ESTABLISHED"
    assert result["evidence_level"] == "unverified"
    assert result["feasibility"] is None


def test_outcomes():
    for case, expected in (
        ("unbracketed", "TARGET_NOT_BRACKETED"),
        ("limit", "EVALUATION_LIMIT"),
        ("endpoint", "TARGET_RESIDUAL_MET"),
    ):
        body = request()
        if case == "unbracketed":
            body["target_thrust_n"] = 1e9
        elif case == "limit":
            body["max_evaluations"] = 2
            body["absolute_thrust_tolerance_n"] = 1e-10
        else:
            actual = m.hb.evaluate_hover_bemt({
                **body["rotor_template"], "angular_speed_rad_s": 100.
            })
            body["target_thrust_n"] = actual["outputs"]["thrust_n"]
        result = m.evaluate_hover_thrust_target(body)
        assert result["status"] == "COMPUTED_EXPERIMENTAL"
        assert result["outputs"]["outcome"] == expected
        assert result["outputs"]["evaluations_used"] == 2
        assert result["feasibility"] is None


@pytest.mark.parametrize(
    "defect", ["booltarget", "budget65", "annuli513", "reversebracket", "templateomega"]
)
def test_preflight(monkeypatch, defect):
    body = deepcopy(request())
    if defect == "booltarget":
        body["target_thrust_n"] = True
    elif defect == "budget65":
        body["max_evaluations"] = 65
    elif defect == "annuli513":
        body["rotor_template"]["annuli"] = 513
    elif defect == "reversebracket":
        body["angular_speed_bracket_rad_s"] = [400, 100]
    else:
        body["rotor_template"]["angular_speed_rad_s"] = 300
    calls = []

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("BEMT must not run during invalid preflight")

    monkeypatch.setattr(m.hb, "evaluate_hover_bemt", spy)
    result = m.evaluate_hover_thrust_target(body)
    assert result["status"] == "GRAPH_INVALID"
    assert "request_sha256" not in result
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == []
    assert calls == []


def test_private_exception(monkeypatch):
    body = deepcopy(request())

    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE_SENTINEL")

    monkeypatch.setattr(m.hb, "evaluate_hover_bemt", fail)
    result = m.evaluate_hover_thrust_target(body)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == sha256_record(body)
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == []
    assert "PRIVATE_SENTINEL" not in repr(result)


@pytest.mark.parametrize('fault', ['units', 'hashmetadata', 'thirdexception'])
def test_failed_forward_is_atomic(monkeypatch, fault):
    body = request()
    original = deepcopy(body)
    real = m.hb.evaluate_hover_bemt
    counter = 0

    def wrapped(payload):
        nonlocal counter
        counter += 1
        if counter == 3 and fault == 'thirdexception':
            raise RuntimeError('PRIVATE_LATE')
        raw = real(payload)
        if fault == 'units':
            raw['output_units']['thrust_n'] = 'kN'
        elif fault == 'hashmetadata':
            raw['evidence_level'] = 'verified'
        return raw

    monkeypatch.setattr(m.hb, 'evaluate_hover_bemt', wrapped)
    result = m.evaluate_hover_thrust_target(body)
    assert result['status'] == 'EXECUTION_FAILED'
    assert result['request_sha256'] == sha256_record(original)
    assert result['diagnostics_complete'] is False
    assert result['stages'] == []
    assert result['outputs'] == {}
    assert result['output_units'] == {}
    assert body == original
    assert 'PRIVATE_LATE' not in str(result)
