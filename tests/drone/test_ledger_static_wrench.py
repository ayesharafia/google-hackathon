from copy import deepcopy

import pytest

from physimesh.drone import ledger_static_wrench as m
from physimesh.drone.provenance import sha256_record

from .test_mass_ledger_request import request as ledger_request
from .test_static_wrench_solve import request as solve_request


def request():
    ledger = ledger_request()
    solve = solve_request()
    ledger_outputs = m.ml.evaluate_mass_ledger(ledger)["outputs"]
    template = solve["assembly_template"]
    template["mass_kg"] = ledger_outputs["total_mass_kg"]
    template["cg_body_m"] = deepcopy(ledger_outputs["cg_body_m"])
    assembly = m.ws.ra.evaluate_rotor_assembly(
        m.ws._assembly_input(solve, [300.0, 330.0])
    )["outputs"]
    solve["required_net_force_body_n"] = deepcopy(assembly["net_force_body_n"])
    solve["required_net_moment_cg_body_nm"] = deepcopy(assembly["net_moment_cg_body_nm"])
    for key in ("mass_kg", "cg_body_m"):
        template.pop(key)
    return {"evaluation": m.EVALUATION, "ledger": ledger, "solve_template": solve}






def test_real_composition(monkeypatch):
    body = request()
    before = deepcopy(body)
    original_ledger = m.ml.evaluate_mass_ledger
    original_solver = m.ws.evaluate_static_wrench_solve
    calls = {"ledger": [], "static_wrench_solve": []}

    def ledger_spy(value):
        captured = deepcopy(value)
        raw = original_ledger(value)
        calls["ledger"].append((captured, deepcopy(raw)))
        return raw

    def solver_spy(value):
        captured = deepcopy(value)
        raw = original_solver(value)
        calls["static_wrench_solve"].append((captured, deepcopy(raw)))
        return raw

    monkeypatch.setattr(m.ml, "evaluate_mass_ledger", ledger_spy)
    monkeypatch.setattr(m.ws, "evaluate_static_wrench_solve", solver_spy)
    result = m.evaluate_ledger_static_wrench(body)
    assert body == before
    assert result["evaluation"] == m.EVALUATION
    assert result["request_sha256"] == sha256_record(before)
    assert all(len(captured) == 1 for captured in calls.values())
    ledger_input, ledger_raw = calls["ledger"][0]
    solve_input, solve_raw = calls["static_wrench_solve"][0]
    assert ledger_input == before["ledger"]
    assert solve_input == m._solve_input(before, ledger_raw["outputs"])
    for stage, ((actual_input, raw),) in zip(result["stages"], calls.values(), strict=True):
        assert stage["request_sha256"] == sha256_record(actual_input)
        assert stage["result_sha256"] == sha256_record(raw)
    for name, raw in (("ledger", ledger_raw), ("solve", solve_raw)):
        assert result["outputs"][name] == raw["outputs"]
        assert result["output_units"][name] == raw["output_units"]
    assert result["transfers"] == {"mass_kg": 4, "cg_body_m": [0, 0, 0]}
    assembly = solve_input["assembly_template"]
    assert assembly["mass_kg"] == 4
    assert assembly["cg_body_m"] == [0, 0, 0]
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    solve = result["outputs"]["solve"]
    assert solve["outcome"] == "RESIDUAL_MET"
    assert solve["selected_candidate"]["angular_speeds_rad_s"] == pytest.approx([300, 330])
    assert solve["selected_candidate"]["max_scaled_residual"] <= 1
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["aircraft_status"] is None
    assert result["feasibility"] is None


@pytest.mark.parametrize(
    "case", ["mass_conflict", "cg_conflict", "speed_conflict", "budget", "ledger"]
)
def test_preflight_zero_models(monkeypatch, case):
    body = request()
    template = body["solve_template"]
    if case == "mass_conflict":
        template["assembly_template"]["mass_kg"] = 1.0
    elif case == "cg_conflict":
        template["assembly_template"]["cg_body_m"] = [0.0, 0.0, 0.0]
    elif case == "speed_conflict":
        hover = next(
            node for node in template["assembly_template"]["graph"]["nodes"]
            if node["model"] == "isolated_hover_bemt_experimental"
        )
        hover["inputs"]["angular_speed_rad_s"] = 1.0
    elif case == "budget":
        template["max_evaluations"] = 65
    else:
        body["ledger"]["items"].pop()

    calls = []

    def forbidden(payload):
        calls.append(payload)
        raise AssertionError("Preflight must not call either model")

    monkeypatch.setattr(m.ml, "evaluate_mass_ledger", forbidden)
    monkeypatch.setattr(m.ws, "evaluate_static_wrench_solve", forbidden)
    result = m.evaluate_ledger_static_wrench(body)

    assert calls == []
    assert result["status"] == "GRAPH_INVALID"
    assert not any("hash" in key or "sha256" in key for key in result)
    assert result["outputs"] == {}
    assert result["output_units"] == {}
    assert result["stages"] == []
    assert result["transfers"] == {}





@pytest.mark.parametrize("fault", [
    "ledger_private", "ledger_units", "solver_private",
    "solver_residual", "solver_request_hash", "solver_assembly",
])
def test_atomic(monkeypatch, fault):
    body = request()
    expected_hash = sha256_record(body)
    real_ledger = m.ml.evaluate_mass_ledger
    real_solver = m.ws.evaluate_static_wrench_solve

    def faulty(*args, **kwargs):
        if fault.endswith("_private"):
            raise RuntimeError(
                "PRIVATE_LEDGER" if fault.startswith("ledger") else "PRIVATE_SOLVER"
            )
        raw = deepcopy(real(*args, **kwargs))
        if fault == "ledger_units":
            raw["output_units"]["total_mass_kg"] = "wrong"
        elif fault == "solver_residual":
            raw["outputs"]["selected_candidate"]["force_residual_n"][0] += 1
        elif fault == "solver_request_hash":
            raw["request_sha256"] = "0" * 64
        elif fault == "solver_assembly":
            raw["outputs"]["assembly"]["net_force_body_n"][0] += 1
        return raw

    ledger = fault.startswith("ledger")
    real = real_ledger if ledger else real_solver
    monkeypatch.setattr(m.ml if ledger else m.ws,
                        "evaluate_mass_ledger" if ledger else "evaluate_static_wrench_solve", faulty)
    result = m.evaluate_ledger_static_wrench(body)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == expected_hash
    assert result["diagnostics_complete"] is False
    assert "PRIVATE_" not in repr(result)
    assert result["outputs"] == result["output_units"] == {}
    assert result["transfers"] == {}
    assert result["stages"] == []


def test_honest_unsolved_outcomes():
    body = request()
    body["solve_template"]["max_evaluations"] = 2
    ledger = m.ml.evaluate_mass_ledger(deepcopy(body["ledger"]))
    raw_request = m._solve_input(body, ledger["outputs"])
    raw = m.ws.evaluate_static_wrench_solve(raw_request)
    result = m.evaluate_ledger_static_wrench(body)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["solve"] == raw["outputs"]
    assert result["output_units"]["solve"] == raw["output_units"]
    assert result["outputs"]["solve"]["outcome"] == "EVALUATION_LIMIT"
    assert result["outputs"]["solve"]["evaluations_used"] == 2
    body = request()
    body["solve_template"]["required_net_force_body_n"][0] = 1e9
    result = m.evaluate_ledger_static_wrench(body)
    solve = result["outputs"]["solve"]
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert solve["outcome"] in {"SOLVER_STOPPED", "EVALUATION_LIMIT"}
    assert solve["selected_candidate"]["max_scaled_residual"] > 1
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["aircraft_status"] is None
    assert result["feasibility"] is None
