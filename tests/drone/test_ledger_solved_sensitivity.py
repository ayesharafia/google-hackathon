from copy import deepcopy

import pytest

from physimesh.drone import ledger_solved_sensitivity as m
from physimesh.drone.provenance import sha256_record

from .test_ledger_static_wrench import request as ledger_solve_request
from .test_solved_wrench_sensitivity import request as sensitivity_request


def request():
    ls = ledger_solve_request()
    analysis = sensitivity_request()
    analysis["solve"] = ls["solve_template"]
    return {
        "evaluation": m.EVALUATION,
        "ledger": ls["ledger"],
        "analysis_template": analysis,
    }


def assert_unqualified(result):
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["numerical_qualification"] == "NOT_ESTABLISHED"
    assert result["runtime_identity"] == "NOT_ESTABLISHED"
    assert result["aircraft_status"] is None
    assert result["feasibility"] is None
    assert result["evidence_level"] == "unverified"


def test_actual_composition(monkeypatch):
    payload = request()
    original = deepcopy(payload)
    calls = {"ledger": [], "analysis": [], "assembly": []}

    def spy(owner, name, label):
        actual = getattr(owner, name)

        def evaluate(value):
            before = deepcopy(value)
            raw = actual(value)
            calls[label].append((before, deepcopy(raw)))
            assert value == before
            return raw

        monkeypatch.setattr(owner, name, evaluate)

    spy(m.ml, "evaluate_mass_ledger", "ledger")
    spy(m.ss, "evaluate_solved_wrench_sensitivity", "analysis")
    spy(m.ss.ws.ra, "evaluate_rotor_assembly", "assembly")
    result = m.evaluate_ledger_solved_sensitivity(payload)
    assert payload == original
    assert result["request_sha256"] == sha256_record(original)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["diagnostics_complete"] is True
    assert len(calls["ledger"]) == len(calls["analysis"]) == 1
    ledger_input, ledger_raw = calls["ledger"][0]
    analysis_input, analysis_raw = calls["analysis"][0]
    assert ledger_input == original["ledger"]
    expected = deepcopy(original["analysis_template"])
    expected["solve"]["assembly_template"]["mass_kg"] = 4
    expected["solve"]["assembly_template"]["cg_body_m"] = [0, 0, 0]
    assert analysis_input == expected
    assert calls["assembly"]
    for assembly_input, _ in calls["assembly"]:
        assert assembly_input["mass_kg"] == 4
        assert assembly_input["cg_body_m"] == [0, 0, 0]
    for label, raw in (("ledger", ledger_raw), ("analysis", analysis_raw)):
        assert result["outputs"][label] == raw["outputs"]
        assert result["output_units"][label] == raw["output_units"]
    stages = result["stages"]
    assert [(s["stage_id"], s["request_sha256"], s["result_sha256"]) for s in stages] == [
        ("ledger", sha256_record(ledger_input), sha256_record(ledger_raw)),
        ("solved_sensitivity", sha256_record(analysis_input), sha256_record(analysis_raw)),
    ]
    analysis = result["outputs"]["analysis"]
    assert analysis["solve"]["outcome"] == "RESIDUAL_MET"
    assert analysis["sensitivity_state"] == "COMPUTED_AT_RESIDUAL_MET_POINT"
    assert analysis["sensitivity"]["nominal_assembly"] == analysis["solve"]["assembly"]
    assert_unqualified(result)


@pytest.mark.parametrize("case", ["limit", "unreachable"])
def test_unsolved_skips_sensitivity(monkeypatch, case):
    payload = request()
    solve = payload["analysis_template"]["solve"]
    if case == "limit":
        solve["max_evaluations"] = 2
        for bound, speed in zip(solve["rotor_speed_bounds"], [250, 270]):
            bound["initial_angular_speed_rad_s"] = speed
    else:
        solve["required_net_force_body_n"][0] = 1e9
    original = deepcopy(payload)

    def forbidden(*args, **kwargs):
        pytest.fail("Sensitivity must not run when the solve residual is unmet")

    monkeypatch.setattr(m.ss.sn, "evaluate_wrench_sensitivity", forbidden)
    result = m.evaluate_ledger_solved_sensitivity(payload)
    assert payload == original
    assert result["request_sha256"] == sha256_record(original)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["diagnostics_complete"] is True
    assert result["outputs"]["analysis"]["sensitivity_state"] == "NOT_RUN_RESIDUAL_UNMET"
    assert result["outputs"]["analysis"]["sensitivity"] is None
    assert_unqualified(result)


@pytest.mark.parametrize("case", [
    "mass", "cg", "ledger", "hzero", "unknown", "budget", "jsonbudget",
])
def test_invalid_request_never_executes(case, monkeypatch):
    req = deepcopy(request())
    if case == "mass":
        req["analysis_template"]["solve"]["assembly_template"]["mass_kg"] = 1
    elif case == "cg":
        req["analysis_template"]["solve"]["assembly_template"]["cg_body_m"] = [0, 0, 0]
    elif case == "ledger":
        req["ledger"]["items"].pop()
    elif case == "hzero":
        req["analysis_template"]["sensitivity_settings"]["perturbations"][0]["half_step_rad_s"] = 0
    elif case == "unknown":
        req["unknown"] = 1
    elif case == "budget":
        for node in req["analysis_template"]["solve"]["assembly_template"]["graph"]["nodes"]:
            if node["model"] == "isolated_hover_bemt_experimental":
                node["inputs"]["annuli"] = 400
    elif case == "jsonbudget":
        req["padding"] = [0] * 65537
    calls = []
    monkeypatch.setattr(
        m.ml, "evaluate_mass_ledger",
        lambda *a, **k: calls.append("ledger") or pytest.fail("Forbidden execution"),
    )
    monkeypatch.setattr(
        m.ss, "evaluate_solved_wrench_sensitivity",
        lambda *a, **k: calls.append("analysis") or pytest.fail("Forbidden execution"),
    )
    result = m.evaluate_ledger_solved_sensitivity(req)
    assert result["status"] == "GRAPH_INVALID"
    assert result["diagnostics_complete"] is False
    assert "request_sha256" not in result
    assert result["outputs"] == {}
    assert result["output_units"] == {}
    assert result["transfers"] == {}
    assert result["stages"] == []
    assert calls == []


@pytest.mark.parametrize(
    "case", ["residual", "boolean", "rank", "matrix", "nominal", "hash", "units", "private"]
)
def test_rejects_corrupted_sensitivity_results(monkeypatch, case):
    payload = request()
    request_hash = sha256_record(payload)
    good = m.evaluate_ledger_solved_sensitivity(deepcopy(payload))
    assert good["status"] == "COMPUTED_EXPERIMENTAL"
    assert good["diagnostics_complete"] is True
    assert set(good["outputs"]) == {"ledger", "analysis"}
    analysis = good["outputs"]["analysis"]
    assert analysis["solve"]["outcome"] == "RESIDUAL_MET"
    assert analysis["sensitivity_state"] == "COMPUTED_AT_RESIDUAL_MET_POINT"
    assert [stage["stage_id"] for stage in good["stages"]] == [
        "ledger", "solved_sensitivity"
    ]

    actual = m.ss.evaluate_solved_wrench_sensitivity

    def corrupted(*args, **kwargs):
        raw = deepcopy(actual(*args, **kwargs))
        if case == "private":
            raise RuntimeError("PRIVATE")
        if case == "residual":
            raw["outputs"]["solve"]["candidates"][0]["force_residual_n"][0] += 1
        elif case == "boolean":
            raw["outputs"]["solve"]["assembly"]["net_force_body_n"][0] = False
        elif case == "rank":
            raw["outputs"]["sensitivity"]["levels"][0]["numerical_rank"] = 99
        elif case == "matrix":
            raw["outputs"]["sensitivity"]["levels"][0]["dimensionless_jacobian"][0][0] += 1
        elif case == "nominal":
            raw["outputs"]["sensitivity"]["nominal_assembly"]["net_force_body_n"][0] += 1
        elif case == "hash":
            raw["stages"][0]["request_sha256"] = "0" * 64
        elif case == "units":
            raw["output_units"]["solve"]["evaluations_used"] = "bad"
        return raw

    monkeypatch.setattr(m.ss, "evaluate_solved_wrench_sensitivity", corrupted)
    result = m.evaluate_ledger_solved_sensitivity(deepcopy(payload))
    assert result["status"] == "EXECUTION_FAILED"
    assert result["diagnostics_complete"] is False
    assert result["reasons"] == ["Execution failed."]
    assert result["request_sha256"] == request_hash
    assert result["outputs"] == {}
    assert result["output_units"] == {}
    assert result["stages"] == []
    assert "PRIVATE" not in repr(result)
