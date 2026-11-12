"""Private V140 actual-child solve and independent admission checks."""

import math
from copy import deepcopy

import pytest

from physimesh.drone import stable_section_residual as residual
from physimesh.drone import stable_section_solve as solve

from .test_stable_section_residual import digest, oversized_value, reseal, residual_request


def solve_request():
    template = residual_request()
    del template["section"]["psi_rad"]
    return {"evaluation": solve.EVALUATION, "numerical_policy": deepcopy(solve._POLICY),
            "residual_template": template,
            "solve": {"psi_lower_rad": 0.35, "psi_upper_rad": 0.9,
                      "angle_tolerance_rad": 0.001, "residual_tolerance_m2_s": 0.01,
                      "max_evaluations": 16}}


def test_actual_convergence_native_hash_and_full_nested_units():
    request = solve_request()
    result = solve.evaluate_stable_section_solve(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    output = result["outputs"]
    assert output["solve_state"] == "CONVERGED"
    count = result["residual_result_count"]
    assert count == result["load_result_count"] == result["lookup_result_count"] == len(output["evaluations"])
    assert result["request_sha256"] == digest(request)
    assert result["evaluation_sha256"] == digest({k: v for k, v in result.items() if k != "evaluation_sha256"})
    assert output["final_bracket"]["angle_width_rad"] <= request["solve"]["angle_tolerance_rad"]
    assert abs(output["solution"]["residual_m2_s"]) <= request["solve"]["residual_tolerance_m2_s"]
    for row, units in zip(output["evaluations"], result["output_units"]["evaluations"], strict=True):
        actual = deepcopy(request["residual_template"])
        actual["section"]["psi_rad"] = row["psi_rad"]
        solve._guard_residual(row["result"], actual)
        assert units["result"]["outputs"] == row["result"]["output_units"]


@pytest.mark.parametrize("budget", [1, 33, 2.0, 32.0, True, None, "32"])
def test_strict_native_budget_before_calls(budget, monkeypatch):
    request = solve_request()
    request["solve"]["max_evaluations"] = budget
    monkeypatch.setattr(residual, "evaluate_stable_section_residual", lambda _: pytest.fail("unexpected call"))
    result = solve.evaluate_stable_section_solve(request)
    assert result["status"] == "MODEL_INAPPLICABLE" and result["residual_result_count"] == 0
    assert result["request_sha256"] is result["evaluation_sha256"] is None


@pytest.mark.parametrize("owner", ["root", "template"])
def test_both_policy_dictionaries_exact(owner, monkeypatch):
    request = solve_request()
    policy = request["numerical_policy"] if owner == "root" else request["residual_template"]["numerical_policy"]
    policy["f_max"] = 512.0
    monkeypatch.setattr(residual, "evaluate_stable_section_residual", lambda _: pytest.fail("unexpected call"))
    result = solve.evaluate_stable_section_solve(request)
    assert result["status"] == "MODEL_INAPPLICABLE" and result["residual_result_count"] == 0


@pytest.mark.parametrize("angle,residual_tolerance,state", [
    (1.0, 1e-30, "EVALUATION_BUDGET_EXHAUSTED"),
    (1e-30, 100.0, "EVALUATION_BUDGET_EXHAUSTED"),
    (1.0, 100.0, "CONVERGED")])
def test_both_criteria_are_required(angle, residual_tolerance, state):
    request = solve_request()
    request["solve"].update(max_evaluations=2, angle_tolerance_rad=angle,
                            residual_tolerance_m2_s=residual_tolerance)
    result = solve.evaluate_stable_section_solve(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["solve_state"] == state and result["residual_result_count"] == 2


def test_32_actual_calls_independently_guarded(monkeypatch):
    request = solve_request()
    request["solve"].update(max_evaluations=32, angle_tolerance_rad=1e-30, residual_tolerance_m2_s=1e-30)
    original, actual_calls = residual.evaluate_stable_section_residual, []

    def child(actual):
        actual_calls.append(deepcopy(actual))
        return original(actual)

    monkeypatch.setattr(residual, "evaluate_stable_section_residual", child)
    result = solve.evaluate_stable_section_solve(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["solve_state"] == "EVALUATION_BUDGET_EXHAUSTED"
    rows = result["outputs"]["evaluations"]
    assert result["residual_result_count"] == len(rows) == len(actual_calls) == 32
    assert len({row["psi_rad"] for row in rows}) == 32
    for row, actual in zip(rows, actual_calls, strict=True):
        solve._guard_residual(row["result"], actual)


_FACTOR_FIELDS = tuple(residual._FACTOR_UNITS)
_VELOCITY_FIELDS = tuple(residual._VELOCITY_UNITS)
_CLOSURE_FIELDS = tuple(residual._CLOSURE_UNITS)
_TAMPER_PATHS = ([('outputs', 'factor_representation', key) for key in _FACTOR_FIELDS]
                 + [('outputs', 'kinematics', key) for key in _VELOCITY_FIELDS]
                 + [('outputs', 'closure', key) for key in _CLOSURE_FIELDS]
                 + [(key,) for key in ('status', 'reasons', 'numerical_policy', 'load_result_count',
                                       'lookup_result_count', 'diagnostics_complete', 'physical_validation',
                                       'limits', 'limitations', 'source_urls', 'request_sha256', 'schema_version')]
                 + [('output_units', 'factor_representation', key) for key in _FACTOR_FIELDS]
                 + [('outputs', 'actual_load_result', 'outputs', 'loads', 'dynamic_pressure_pa'),
                    ('outputs', 'actual_load_request', 'section', 'chord_m'),
                    ('outputs', 'residual_m2_s')])


@pytest.mark.parametrize("path", _TAMPER_PATHS)
def test_resealed_all_factor_fields_units_metadata_and_child_rejected(path):
    request = residual_request()
    actual = residual.evaluate_stable_section_residual(request)
    target = actual
    for key in path[:-1]:
        target = target[key]
    old = target[path[-1]]
    if type(old) is float:
        replacement = math.nextafter(old, math.inf)
    elif type(old) is int:
        replacement = True if old == 1 else old + 1
    elif type(old) is bool:
        replacement = not old
    elif type(old) is list:
        replacement = old + ["forged"]
    elif type(old) is dict:
        replacement = {**old, "forged": 0}
    else:
        replacement = "forged"
    target[path[-1]] = replacement
    if path[:2] == ('outputs', 'actual_load_result'):
        reseal(actual["outputs"]["actual_load_result"])
    reseal(actual)
    with pytest.raises(ValueError):
        solve._guard_residual(actual, request)


def test_independent_guard_never_uses_producer_math_or_evaluator(monkeypatch):
    request = residual_request()
    actual = residual.evaluate_stable_section_residual(request)

    def forbidden(*args, **kwargs):
        pytest.fail("producer numerical oracle called")

    for name in ("evaluate_stable_section_residual", "_preflight", "_velocity", "_wake", "_closure",
                 "_representation", "_effect_bound", "_checked", "_product", "_quotient", "_sum"):
        monkeypatch.setattr(residual, name, forbidden)
    solve._guard_residual(actual, request)


@pytest.mark.parametrize("failure_at", [1, 2, 4])
def test_failed_child_atomic_prior_trace_counts(failure_at, monkeypatch):
    request = solve_request()
    original, attempts = residual.evaluate_stable_section_residual, []

    def child(actual_request):
        attempts.append(None)
        result = original(actual_request)
        if len(attempts) == failure_at:
            result["load_result_count"] = True
            reseal(result)
        return result

    monkeypatch.setattr(residual, "evaluate_stable_section_residual", child)
    result = solve.evaluate_stable_section_solve(request)
    assert result["status"] == "EXECUTION_FAILED" and result["reasons"] == ["RESIDUAL_BOUNDARY_FAILED"]
    assert result["residual_result_count"] == len(result["outputs"]["evaluations"]) == failure_at - 1
    assert len(attempts) == failure_at
    assert result["outputs"]["final_bracket"] is result["outputs"]["solution"] is None
    assert result["outputs"]["solve_state"] == "EXECUTION_FAILED"


def test_ood_and_policy_refusal_semantics():
    request = solve_request()
    request["residual_template"]["polar"].update(sampled_mach_number=0, declared_mach_interval=[0, 0])
    result = solve.evaluate_stable_section_solve(request)
    assert result["outputs"]["solve_state"] == "NOT_RUN_OUT_OF_POLAR_DOMAIN"
    assert result["residual_result_count"] == 1
    request["residual_template"]["section"]["radius_m"] = 1e-4
    result = solve.evaluate_stable_section_solve(request)
    assert result["reasons"] == ["RESIDUAL_BOUNDARY_FAILED"] and result["residual_result_count"] == 0
    assert result["outputs"]["evaluations"] == []


@pytest.mark.parametrize("case", ["nodes", "depth", "container", "string", "integer", "utf8", "circular", "bytes"])
def test_solve_input_bound_before_untrusted_copy_hash_model(case, monkeypatch):
    request = solve_request()
    if case == "bytes":
        request["oversized"] = ["\x00" * 2000] * 175
    else:
        request["oversized"] = oversized_value(case, node_limit=65536, depth_limit=18)
    original_copy = solve.deepcopy

    def copying(value, *args, **kwargs):
        if value is request:
            pytest.fail("untrusted request copied before rejection")
        return original_copy(value, *args, **kwargs)  # Trusted refusal metadata only.

    monkeypatch.setattr(solve, "deepcopy", copying)
    monkeypatch.setattr(solve, "sha256_record", lambda _: pytest.fail("unexpected request hash"))
    monkeypatch.setattr(residual, "evaluate_stable_section_residual", lambda _: pytest.fail("unexpected model"))
    result = solve.evaluate_stable_section_solve(request)
    assert result["status"] == "MODEL_INAPPLICABLE" and result["residual_result_count"] == 0
    assert result["outputs"] == result["output_units"] == {}
    assert result["request_sha256"] is result["evaluation_sha256"] is None


def test_actual_not_bracketed():
    request = solve_request()
    for table in request["residual_template"]["polar"]["reynolds_tables"]:
        for row in table["rows"]:
            row["cl"] = 0
    result = solve.evaluate_stable_section_solve(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["solve_state"] == "NOT_BRACKETED"
    assert result["residual_result_count"] == 2 and result["outputs"]["solution"] is None


@pytest.mark.parametrize("failure", ["exception", "baseexception", "hash", "output_bound"])
def test_solve_exception_and_persistent_export_contract(failure, monkeypatch):
    request = solve_request()
    if failure in ("exception", "baseexception"):
        original, attempts = residual.evaluate_stable_section_residual, []

        def child(actual):
            attempts.append(None)
            if len(attempts) == 2:
                if failure == "baseexception":
                    raise KeyboardInterrupt("private interrupt")
                raise RuntimeError("private child detail")
            return original(actual)
        monkeypatch.setattr(residual, "evaluate_stable_section_residual", child)
        if failure == "baseexception":
            with pytest.raises(KeyboardInterrupt):
                solve.evaluate_stable_section_solve(request)
            return
    elif failure == "hash":
        original_hash = solve.sha256_record

        def hashing(value):
            if "residual_result_count" in value:
                raise RuntimeError("private export hash detail")
            return original_hash(value)
        monkeypatch.setattr(solve, "sha256_record", hashing)
    else:
        original_units = solve._output_units

        def too_large(*args):
            units = original_units(*args)
            units["extra"] = "x" * 2001
            return units
        monkeypatch.setattr(solve, "_output_units", too_large)
    result = solve.evaluate_stable_section_solve(request)
    assert result["status"] == "EXECUTION_FAILED"
    if failure == "exception":
        assert result["residual_result_count"] == 1
        assert len(result["outputs"]["evaluations"]) == 1
        assert result["outputs"]["solution"] is result["outputs"]["final_bracket"] is None
    else:
        assert result["residual_result_count"] == 12
        assert result["outputs"] == result["output_units"] == {}
        assert result["request_sha256"] is result["evaluation_sha256"] is None
    assert "private" not in str(result)


@pytest.mark.parametrize("branch", ["zero", "stagnation"])
def test_synthetic_unit_bisect_branches_only(branch):
    """Synthetic unit coverage only: not actual integrated child/guard evidence."""
    lo = 0.5
    hi = math.nextafter(lo, math.inf) if branch == "stagnation" else 0.9
    rows, requests = [], []
    endpoints = [{"section": {"psi_rad": psi}} for psi in (lo, hi)]

    def evaluate(request):
        requests.append(request)
        value = (0.0 if len(rows) == 0 else 1.0) if branch == "zero" else (-1.0 if not rows else 1.0)
        rows.append({"psi_rad": request["section"]["psi_rad"],
                     "result": {"outputs": {"residual_m2_s": value}}})
        return len(rows) - 1

    settings = {"max_evaluations": 32, "angle_tolerance_rad": 1e-30, "residual_tolerance_m2_s": 1e-30}
    state, bracket, solution = solve._bisect(rows, evaluate, endpoints, settings)
    assert len(requests) == 2  # Both endpoints; no retry or repeated float midpoint.
    if branch == "zero":
        assert state == "CONVERGED" and bracket["angle_width_rad"] == 0.0
        assert bracket["lower_evaluation_index"] == bracket["upper_evaluation_index"] == 0
        assert solution["residual_m2_s"] == 0.0
    else:
        assert state == "FLOAT_STAGNATION" and solution is None
