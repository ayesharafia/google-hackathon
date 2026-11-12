from copy import deepcopy

import pytest

from physimesh.drone import solved_wrench_sensitivity as m
from physimesh.drone.provenance import sha256_record

from .test_static_wrench_solve import request as solve_request


def request():
    return {
        "evaluation": m.EVALUATION,
        "solve": solve_request(),
        "sensitivity_settings": {
            "perturbations": [
                {"node": node, "half_step_rad_s": 1.0, "speed_scale_rad_s": 300.0}
                for node in ("r1", "r2")
            ],
            "force_scale_n": 100.0,
            "moment_scale_nm": 100.0,
            "relative_singular_value_cutoff": 1e-8,
        },
    }


def test_actual_composition(monkeypatch):
    body = request()
    saved = deepcopy(body)
    actual_solve = m.ws.evaluate_static_wrench_solve
    actual_sensitivity = m.sn.evaluate_wrench_sensitivity
    calls = {"solve": [], "sensitivity": []}

    def spy(stage_id, actual):
        def wrapped(req):
            captured_input = deepcopy(req)
            raw = actual(req)
            calls[stage_id].append((captured_input, deepcopy(raw)))
            return raw
        return wrapped

    monkeypatch.setattr(m.ws, "evaluate_static_wrench_solve", spy("solve", actual_solve))
    monkeypatch.setattr(m.sn, "evaluate_wrench_sensitivity", spy("sensitivity", actual_sensitivity))
    result = m.evaluate_solved_wrench_sensitivity(body)
    assert body == saved
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["request_sha256"] == sha256_record(saved)
    assert result["evaluation"] == m.EVALUATION
    assert len(calls["solve"]) == len(calls["sensitivity"]) == 1
    solve_input, solve_raw = calls["solve"][0]
    sensitivity_input, _dummy = calls["sensitivity"][0]
    assert solve_input == saved["solve"]
    speeds = solve_raw["outputs"]["selected_candidate"]["angular_speeds_rad_s"]
    assert sensitivity_input == m._sensitivity_input(saved, speeds)
    outputs = result["outputs"]
    assert set(outputs) == {"sensitivity_state", "solve", "sensitivity"}
    assert outputs["sensitivity_state"] == "COMPUTED_AT_RESIDUAL_MET_POINT"
    stages = {stage["stage_id"]: stage for stage in result["stages"]}
    assert len(result["stages"]) == 2
    assert set(stages) == {"solve", "sensitivity"}
    for name, (stage_input, raw) in (("solve", calls["solve"][0]), ("sensitivity", calls["sensitivity"][0])):
        assert stages[name]["request_sha256"] == sha256_record(stage_input)
        assert stages[name]["result_sha256"] == sha256_record(raw)
        assert outputs[name] == raw["outputs"]
        assert result["output_units"][name] == raw["output_units"]
    assert outputs["sensitivity"]["nominal_assembly"] == outputs["solve"]["assembly"]
    assert outputs["sensitivity"]["evaluations_used"] == 13
    assert len(outputs["sensitivity"]["levels"]) == 3
    assert len(outputs["sensitivity"]["changes"]) == 2
    assert result["transfers"]["selected_angular_speeds_rad_s"] == list(speeds)
    assert result["physical_validation"] == result["numerical_qualification"] == result["runtime_identity"] == "NOT_ESTABLISHED"
    assert result["evidence_level"] == "unverified"
    assert result["aircraft_status"] is None and result["feasibility"] is None


@pytest.mark.parametrize("case", ["limit", "unreachable"])
def test_unsolved_skips_probes(monkeypatch, case):
    body = request()
    if case == "limit":
        body["solve"]["max_evaluations"] = 2
    else:
        body["solve"]["required_net_force_body_n"][0] = 1e9
    original = deepcopy(body)
    probe_calls = 0

    def forbidden_probe(*args, **kwargs):
        nonlocal probe_calls
        probe_calls += 1
        pytest.fail("Sensitivity probes must not run when the residual is unmet")

    monkeypatch.setattr(m.sn, "evaluate_wrench_sensitivity", forbidden_probe)
    result = m.evaluate_solved_wrench_sensitivity(body)
    assert result["status"] == "COMPUTED_EXPERIMENTAL" and result["diagnostics_complete"] is True
    assert result["request_sha256"] == sha256_record(original)
    assert set(result["outputs"]) == {"sensitivity_state", "solve", "sensitivity"}
    assert result["outputs"]["sensitivity_state"] == "NOT_RUN_RESIDUAL_UNMET"
    assert result["outputs"]["sensitivity"] is None
    assert result["output_units"]["sensitivity"] == "not_applicable"
    assert result["outputs"]["solve"]["outcome"] in {"EVALUATION_LIMIT", "SOLVER_STOPPED"}
    assert [stage["stage_id"] for stage in result["stages"]] == ["solve"] and probe_calls == 0


@pytest.mark.parametrize("case", ["hzero", "settings_extra", "order", "bracket_h", "combined_budget"])
def test_invalid_preflight_zero_models(monkeypatch, case):
    body = request()
    settings = body["sensitivity_settings"]
    calls = []

    def mappings(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from mappings(child)
        elif isinstance(value, list):
            for child in value:
                yield from mappings(child)

    if case == "hzero":
        settings["perturbations"][0]["half_step_rad_s"] = 0.
    elif case == "settings_extra":
        settings["unknown_key"] = True
    elif case == "order":
        settings["perturbations"].reverse()
    elif case == "bracket_h":
        settings["perturbations"][0]["half_step_rad_s"] = 150.
    else:
        for item in mappings(body["solve"]["assembly_template"]["graph"]["nodes"]):
            if "annuli" in item:
                item["annuli"] = 400
        for item in mappings(body["solve"]):
            if "max_evaluations" in item:
                item["max_evaluations"] = 32

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        pytest.fail("Preflight invoked a model evaluation")
    monkeypatch.setattr(m.ws, "evaluate_static_wrench_solve", forbidden)
    monkeypatch.setattr(m.sn, "evaluate_wrench_sensitivity", forbidden)
    result = m.evaluate_solved_wrench_sensitivity(body)
    assert result["status"] == "GRAPH_INVALID"
    assert "request_sha256" not in result
    assert not any(result[key] for key in ("stages", "transfers", "outputs", "output_units"))
    assert calls == []


@pytest.mark.parametrize("case", [
    "solver_private", "sensitivity_private", "nominal_drift",
    "matrix", "singular_rank", "stage_requesthash",
])
def test_atomic(monkeypatch, case):
    body = request()
    expected_hash = sha256_record(body)
    real_sn = m.sn.evaluate_wrench_sensitivity

    def patched_solve(reqdict):
        raise RuntimeError("PRIVATE_SOLVE")

    def patched_sensitivity(reqdict):
        if case == "sensitivity_private":
            raise RuntimeError("PRIVATE_SENSITIVITY")
        raw = deepcopy(real_sn(reqdict))
        if case == "nominal_drift":
            raw["outputs"]["nominal_assembly"]["net_force_body_n"][0] += 1
        elif case == "matrix":
            raw["outputs"]["levels"][0]["dimensionless_jacobian"][0][0] += 1
        elif case == "singular_rank":
            raw["outputs"]["levels"][0]["numerical_rank"] = 0
        elif case == "stage_requesthash":
            raw["stages"][1]["request_sha256"] = "0" * 64
        return raw

    if case == "solver_private":
        monkeypatch.setattr(m.ws, "evaluate_static_wrench_solve", patched_solve)
    else:
        monkeypatch.setattr(m.sn, "evaluate_wrench_sensitivity", patched_sensitivity)

    result = m.evaluate_solved_wrench_sensitivity(body)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["evaluation"] == m.EVALUATION
    assert result["diagnostics_complete"] is False
    assert result["request_sha256"] == expected_hash
    for key in ("stages", "transfers", "outputs", "output_units"):
        assert not result[key], key
    assert "PRIVATE_SOLVE" not in repr(result)
    assert "PRIVATE_SENSITIVITY" not in repr(result)
