import math
from copy import deepcopy

import pytest

from physimesh.drone import static_wrench_solve as m
from physimesh.drone.provenance import sha256_record

from .test_rotor_assembly import request as assembly_request


def request():
    assembly = deepcopy(assembly_request())

    def walk(value, key=None):
        if isinstance(value, dict):
            yield key, value
            for name, child in value.items():
                yield from walk(child, name)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    rotors = [(key, node) for key, node in walk(assembly)
              if "angular_speed_rad_s" in node.get("inputs", {})]
    speeds = {node.get("node", node.get("node_id", node.get("id", key))):
              node["inputs"]["angular_speed_rad_s"] for key, node in rotors}
    actual = m.ra.evaluate_rotor_assembly(assembly)
    outputs = next(value for _, value in walk(actual)
                   if {"net_force_body_n", "net_moment_cg_body_nm"} <= value.keys())
    for _, node in rotors:
        del node["inputs"]["angular_speed_rad_s"]
    return {
        "evaluation": m.EVALUATION, "assembly_template": assembly,
        "rotor_speed_bounds": [{"node": node, "angular_speed_bracket_rad_s": [150.0, 600.0],
                               "initial_angular_speed_rad_s": 240.0} for node in speeds],
        "required_net_force_body_n": deepcopy(outputs["net_force_body_n"]),
        "required_net_moment_cg_body_nm": deepcopy(outputs["net_moment_cg_body_nm"]),
        "absolute_force_tolerance_n": 1e-6, "absolute_moment_tolerance_nm": 1e-6,
        "max_evaluations": 32,
    }


def test_real_solve_and_hashes(monkeypatch):
    body = request()
    saved = deepcopy(body)
    real = m.ra.evaluate_rotor_assembly
    calls = []

    def spy(actual_request):
        captured_request = deepcopy(actual_request)
        raw = real(actual_request)
        calls.append((captured_request, deepcopy(raw)))
        return raw

    monkeypatch.setattr(m.ra, "evaluate_rotor_assembly", spy)
    result = m.evaluate_static_wrench_solve(body)
    outputs = result["outputs"]
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert outputs["outcome"] == "RESIDUAL_MET"
    assert body == saved
    assert result["request_sha256"] == sha256_record(saved)
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["numerical_qualification"] == "NOT_ESTABLISHED"
    assert result["runtime_identity"] == "NOT_ESTABLISHED"
    assert result["evidence_level"] == "unverified"
    assert result["aircraft_status"] is None
    assert result["feasibility"] is None
    candidates, stages = outputs["candidates"], result["stages"]
    assert 2 < outputs["evaluations_used"] == len(calls) == len(candidates) == len(stages) <= 32
    assert [s["stage_id"] for s in stages] == [
        f"evaluation_{i}" for i in range(1, len(stages))
    ] + ["final"]
    for stage, candidate, (actual_request, raw) in zip(stages, candidates, calls):
        speeds = candidate["angular_speeds_rad_s"]
        assert len(speeds) == len(body["rotor_speed_bounds"])
        assert all(b["angular_speed_bracket_rad_s"][0] <= speed <=
                   b["angular_speed_bracket_rad_s"][1]
                   for speed, b in zip(speeds, body["rotor_speed_bounds"]))
        assert actual_request == m._assembly_input(saved, speeds)
        assert stage["request_sha256"] == sha256_record(actual_request)
        assert stage["result_sha256"] == sha256_record(raw)
        for key in ("net_force_body_n", "net_moment_cg_body_nm"):
            assert candidate[key] == pytest.approx(raw["outputs"][key])
    selected = outputs["selected_candidate"]
    assert calls[-1][0] == m._assembly_input(saved, selected["angular_speeds_rad_s"])
    assert outputs["assembly"] == calls[-1][1]["outputs"]
    assert result["output_units"]["assembly"] == calls[-1][1]["output_units"]
    assert selected["max_scaled_residual"] <= 1
    assert selected["angular_speeds_rad_s"] == pytest.approx([300.0, 300.0], abs=1e-3)


def test_nonzero_reachable_wrench():
    body = request()
    target = m.ra.evaluate_rotor_assembly(m._assembly_input(body, [300.0, 330.0]))["outputs"]
    body["required_net_force_body_n"] = deepcopy(target["net_force_body_n"])
    body["required_net_moment_cg_body_nm"] = deepcopy(target["net_moment_cg_body_nm"])
    assert any(abs(v) > 1e-6 for v in body["required_net_moment_cg_body_nm"])
    result = m.evaluate_static_wrench_solve(body)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["outcome"] == "RESIDUAL_MET"
    selected = result["outputs"]["selected_candidate"]
    actual = m.ra.evaluate_rotor_assembly(m._assembly_input(body, selected["angular_speeds_rad_s"]))["outputs"]
    residuals = [a - b for key in ("net_force_body_n", "net_moment_cg_body_nm")
                 for a, b in zip(actual[key], target[key])]
    assert len(residuals) == 6 and all(math.isfinite(v) and abs(v) <= 1e-6 for v in residuals)


def test_evaluation_limit():
    body = request()
    body["max_evaluations"] = 2
    result = m.evaluate_static_wrench_solve(body)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    outputs = result["outputs"]
    assert outputs["outcome"] == "EVALUATION_LIMIT"
    assert outputs["evaluations_used"] == 2
    selected_candidate = outputs["selected_candidate"]
    assert selected_candidate["max_scaled_residual"] > 1
    last_stage = result["stages"][-1]
    assert last_stage["stage_id"] == "final"


def test_solver_stopped():
    body = request()
    for bounds in body["rotor_speed_bounds"]:
        bounds["initial_angular_speed_rad_s"] = 300.0
    body["required_net_force_body_n"][0] = 10.0
    result = m.evaluate_static_wrench_solve(body)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    outputs = result["outputs"]
    assert outputs is not None
    assert outputs["outcome"] == "SOLVER_STOPPED"
    assert outputs["selected_candidate"]["max_scaled_residual"] > 1.0
    assert result["evidence_level"] == "unverified"
    assert result["aircraft_status"] is None
    assert result["feasibility"] is None
    assert result["physical_validation"] == "NOT_ESTABLISHED"


@pytest.mark.parametrize("defect", [
    "speed_conflict", "target_order", "budget", "maxeval_boolean",
    "bad_tolerance", "bad_target", "bad_initial", "extra_key",
])
def test_preflight_zero_models(monkeypatch, defect):
    body = deepcopy(request())

    def dictionaries(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from dictionaries(child)
        elif isinstance(value, list):
            for child in value:
                yield from dictionaries(child)

    hover = [node for node in dictionaries(body["assembly_template"])
             if "annuli" in node]
    if defect == "speed_conflict":
        hover[0]["angular_speed_rad_s"] = 1
    elif defect == "target_order":
        body["rotor_speed_bounds"].reverse()
    elif defect == "budget":
        for node in hover:
            node["annuli"] = 512
        body["max_evaluations"] = 64
    elif defect == "maxeval_boolean":
        body["max_evaluations"] = True
    elif defect == "bad_tolerance":
        body["absolute_force_tolerance_n"] = 0
    elif defect == "bad_target":
        body["required_net_force_body_n"] = [True, 0, 0]
    elif defect == "bad_initial":
        body["rotor_speed_bounds"][0]["initial_angular_speed_rad_s"] = 700
    else:
        body["extra_key"] = True
    calls = []
    def forbidden(request):
        calls.append(request)
        raise AssertionError("preflight invoked a model")
    monkeypatch.setattr(m.ra, "evaluate_rotor_assembly", forbidden)
    result = m.evaluate_static_wrench_solve(body)
    assert result["status"] == "GRAPH_INVALID"
    assert calls == []
    assert result.get("request_sha256") is None and result.get("result_sha256") is None
    assert result["outputs"] == {} and result["output_units"] == {} and result["stages"] == []


@pytest.mark.parametrize("fault", [
    "private_exception", "units", "request_hash", "net_force", "final_drift",
])
def test_execution_atomic(monkeypatch, fault):
    body = deepcopy(request())
    for bound in body["rotor_speed_bounds"]:
        bound["initial_angular_speed_rad_s"] = 300.0
    speeds = [300.0 for bound in body["rotor_speed_bounds"]]
    original = m.ra.evaluate_rotor_assembly
    initial = original(m._assembly_input(body, speeds))
    body["required_net_force_body_n"] = deepcopy(initial["outputs"]["net_force_body_n"])
    body["required_net_moment_cg_body_nm"] = deepcopy(
        initial["outputs"]["net_moment_cg_body_nm"]
    )
    request_hash = sha256_record(body)
    calls = []

    def faulty(requestdict):
        calls.append(deepcopy(requestdict))
        if fault == "private_exception":
            raise RuntimeError("PRIVATE_WRENCH")
        result = deepcopy(original(requestdict))
        if fault == "units":
            result["output_units"]["net_force_body_n"] = "wrong"
        elif fault == "request_hash":
            result["request_sha256"] = "0" * 64
        elif fault == "net_force":
            result["outputs"]["net_force_body_n"][0] += 1.0
        elif fault == "final_drift" and len(calls) == 2:
            result["outputs"]["rotors"][0]["force_body_n"][2] += 0.01
            result["outputs"]["net_force_body_n"][2] += 0.01
        return result

    monkeypatch.setattr(m.ra, "evaluate_rotor_assembly", faulty)
    result = m.evaluate_static_wrench_solve(body)
    assert len(calls) == (2 if fault == "final_drift" else 1)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == request_hash
    assert "PRIVATE_WRENCH" not in str(result)
    assert "RuntimeError" not in str(result)
    assert result["outputs"] == {}
    assert result["output_units"] == {}
    assert result["stages"] == []
    assert result["diagnostics_complete"] is False
