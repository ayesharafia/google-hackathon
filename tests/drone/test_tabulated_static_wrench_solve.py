"""Actual V112 allocation smokes; no substituted physical evaluator."""

import math
from copy import deepcopy
from unittest.mock import patch

import pytest

from physimesh.drone import tabulated_hover_bemt_request as forward
from physimesh.drone import tabulated_rotor_assembly as assembly
from physimesh.drone import tabulated_static_wrench_solve as solve
from physimesh.drone.provenance import sha256_record

from .test_tabulated_rotor_assembly import request as assembly_request


def request(initial=100.0, budget=32):
    template = assembly_request()
    target = assembly.evaluate_tabulated_rotor_assembly(deepcopy(template))
    assert target["status"] == "COMPUTED_EXPERIMENTAL"
    bounds = []
    for rotor in template["rotors"]:
        del rotor["rotor_template"]["angular_speed_rad_s"]
        bounds.append({"id": rotor["id"], "angular_speed_bracket_rad_s": [50.0, 300.0],
                       "initial_angular_speed_rad_s": initial})
    return {"evaluation": solve.EVALUATION, "assembly_template": template,
            "rotor_speed_bounds": bounds,
            "required_net_force_body_n": target["outputs"]["net_force_body_n"],
            "required_net_moment_cg_body_nm": target["outputs"]["net_moment_cg_body_nm"],
            "absolute_force_tolerance_n": 1e-6, "absolute_moment_tolerance_nm": 1e-6,
            "max_evaluations": budget}


def actual_run(supplied):
    before = deepcopy(supplied)
    with (patch.object(assembly, "evaluate_tabulated_rotor_assembly", wraps=assembly.evaluate_tabulated_rotor_assembly) as child,
          patch.object(assembly, "reference_air_properties", wraps=assembly.reference_air_properties) as air,
          patch.object(assembly, "evaluate_tabulated_hover_bemt", wraps=assembly.evaluate_tabulated_hover_bemt) as rotor,
          patch.object(forward, "solve_tabulated_hover", wraps=forward.solve_tabulated_hover) as core):
        result = solve.evaluate_tabulated_static_wrench_solve(supplied)
        assert result["status"] == "COMPUTED_EXPERIMENTAL", result["reasons"]
        count = result["evaluation_count"]
        assert child.call_count == air.call_count == count
        assert rotor.call_count == core.call_count == result["rotor_evaluation_count"] == count * len(before["assembly_template"]["rotors"])
    assert supplied == before
    selected = result["outputs"]
    assert selected["actual_assembly_result"] == assembly.evaluate_tabulated_rotor_assembly(selected["actual_assembly_request"])
    return result


def test_actual_known_solution():
    result = actual_run(request())
    assert result["outputs"]["outcome"] == "RESIDUAL_MET"
    assert 1 < result["evaluation_count"] <= 32


def test_initial_residual_met_uses_one_trial():
    result = actual_run(request(initial=120.0, budget=2))
    assert result["outputs"]["outcome"] == "RESIDUAL_MET"
    assert result["evaluation_count"] == 1


def test_hard_two_budget_includes_finite_difference_calls():
    supplied = request(budget=2)
    supplied["required_net_force_body_n"][0] = 100.0
    result = actual_run(supplied)
    assert result["outputs"]["outcome"] == "EVALUATION_LIMIT"
    assert result["evaluation_count"] == len(result["outputs"]["candidates"]) == 2


@pytest.fixture(scope="module")
def valid_request():
    return request()


def _change(value, path, replacement):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


@pytest.mark.parametrize(("path", "value"), [
    (("evaluation",), 1), (("extra",), None), (("max_evaluations",), True),
    (("max_evaluations",), 1), (("max_evaluations",), 65),
    (("required_net_force_body_n",), [True, 0.0, 0.0]),
    (("absolute_force_tolerance_n",), 0.0), (("absolute_moment_tolerance_nm",), object()),
    (("rotor_speed_bounds", 0, "id"), "left"),
    (("rotor_speed_bounds", 1, "id"), "air"),
    (("rotor_speed_bounds", 0, "angular_speed_bracket_rad_s"), [50.0, 50.0]),
    (("rotor_speed_bounds", 0, "angular_speed_bracket_rad_s"), [300.0, 50.0]),
    (("rotor_speed_bounds", 0, "initial_angular_speed_rad_s"), 301.0),
    (("assembly_template", "evaluation"), "unsupported"),
    (("assembly_template", "rotors", 0, "rotor_template", "angular_speed_rad_s"), 120.0),
    (("assembly_template", "rotors", 0, "rotor_template", "density_kg_m3"), 1.2),
    (("assembly_template", "rotors", 0, "rotor_template", "evaluation"), "unsupported"),
    (("assembly_template", "rotors", 0, "axis_body"), [0.0, 0.0, 2.0]),
    (("assembly_template", "rotors", 0, "rotation_sign"), True),
    (("assembly_template", "mass_kg"), -1.0), (("assembly_template", "property_source"), " "),
    (("assembly_template", "rotors", 0, "rotor_template", "geometry_source"), ""),
    (("assembly_template", "rotors", 0, "rotor_template", "stations"), []),
    (("assembly_template", "rotors", 0, "rotor_template", "annuli"), True),
])
def test_preflight_rejects_before_solver_or_models(valid_request, path, value):
    supplied = deepcopy(valid_request)
    _change(supplied, path, value)
    with (patch.object(solve, "least_squares") as scipy,
          patch.object(assembly, "evaluate_tabulated_rotor_assembly") as child,
          patch.object(assembly, "reference_air_properties") as air,
          patch.object(assembly, "evaluate_tabulated_hover_bemt") as rotor):
        result = solve.evaluate_tabulated_static_wrench_solve(supplied)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["request_sha256"] is result["evaluation_sha256"] is None
    for spy in (scipy, child, air, rotor):
        spy.assert_not_called()


def test_missing_field_and_aggregate_work_preflight(valid_request):
    missing, aggregate = deepcopy(valid_request), deepcopy(valid_request)
    del missing["required_net_force_body_n"]
    aggregate["max_evaluations"] = 64
    for rotor in aggregate["assembly_template"]["rotors"]:
        rotor["rotor_template"]["annuli"] = 1024
    actual = solve._assembly_input(aggregate, [100.0, 100.0])
    assembly._preflight(actual)  # Legal V112 point; aggregate work alone exceeds limit.
    for supplied in (missing, aggregate):
        with patch.object(solve, "least_squares") as scipy, patch.object(assembly, "evaluate_tabulated_rotor_assembly") as child:
            result = solve.evaluate_tabulated_static_wrench_solve(supplied)
        assert result["status"] == "MODEL_INAPPLICABLE"
        scipy.assert_not_called()
        child.assert_not_called()


@pytest.fixture(scope="module")
def actual_pair():
    supplied = assembly_request()
    actual = assembly.evaluate_tabulated_rotor_assembly(deepcopy(supplied))
    assert actual["status"] == "COMPUTED_EXPERIMENTAL"
    return supplied, actual


def _reseal(actual):
    actual["evaluation_sha256"] = sha256_record({
        k: v for k, v in actual.items() if k != "evaluation_sha256"})


@pytest.mark.parametrize(("path", "value"), [
    (("physical_validation",), "ESTABLISHED"), (("status",), "MODEL_INAPPLICABLE"),
    (("rotor_evaluation_count",), True), (("diagnostics_complete",), 1),
    (("request_sha256",), "0" * 64), (("output_units", "net_force_body_n"), "kg"),
    (("outputs", "air", "state", "density_kg_m3"), 1.0),
    (("outputs", "rotors", 0, "force_body_n", 2), 0.0),
    (("outputs", "rotors", 0, "actual_forward_request", "density_kg_m3"), 1.0),
    (("outputs", "rotors", 0, "actual_forward_result", "request_sha256"), "0" * 64),
    (("outputs", "rotors", 0, "actual_forward_result", "outputs", "thrust_n"), 1.0),
    (("stages", 0, "inputs", "altitude_m"), 999.0),
    (("stages", 1, "stage"), "air"), (("transfers", 0, "value"), 1.0),
    (("transfers", 0, "producer_result_sha256"), "0" * 64),
    (("outputs", "gravity_force_body_n", 2), 0.0), (("outputs", "net_force_body_n", 2), 0.0),
])
def test_full_guard_rejects_resealed_corruption_without_models(actual_pair, path, value):
    supplied, source = actual_pair
    actual = deepcopy(source)
    _change(actual, path, value)
    _reseal(actual)
    with (patch.object(assembly, "evaluate_tabulated_rotor_assembly", side_effect=AssertionError("rerun")),
          patch.object(assembly, "reference_air_properties", side_effect=AssertionError("rerun")),
          patch.object(assembly, "evaluate_tabulated_hover_bemt", side_effect=AssertionError("rerun")),
          patch.object(forward, "solve_tabulated_hover", side_effect=AssertionError("rerun"))):
        assert solve._guard_assembly_success(source, supplied) is None
        with pytest.raises(ValueError):
            solve._guard_assembly_success(actual, supplied)


def test_guard_rejects_unsealed_root_digest(actual_pair):
    supplied, source = actual_pair
    actual = deepcopy(source)
    actual["evaluation_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        solve._guard_assembly_success(actual, supplied)


@pytest.mark.parametrize("prior", [False, True])
@pytest.mark.parametrize("fault", ["noncomputed", "exception"])
def test_atomic_boundary_failure_retains_only_guarded_counts(valid_request, prior, fault):
    supplied, calls = deepcopy(valid_request), 0
    supplied["required_net_force_body_n"][0] = 100.0
    original = assembly.evaluate_tabulated_rotor_assembly

    def child(actual_request):
        nonlocal calls
        calls += 1
        if prior and calls == 1:
            return original(actual_request)
        if fault == "exception":
            raise RuntimeError("private failure payload")
        return {"status": "MODEL_INAPPLICABLE", "reasons": ["private failure payload"]}

    with patch.object(assembly, "evaluate_tabulated_rotor_assembly", side_effect=child):
        result = solve.evaluate_tabulated_static_wrench_solve(supplied)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["reasons"] == ["ASSEMBLY_BOUNDARY_FAILED"]
    assert result["evaluation_count"] == int(prior)
    assert result["rotor_evaluation_count"] == int(prior) * 2
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == result["transfers"] == []
    assert result["diagnostics_complete"] is False
    assert "private failure payload" not in str(result)
    assert result["evaluation_sha256"] == sha256_record({
        k: v for k, v in result.items() if k != "evaluation_sha256"})


def test_snapshot_rejects_foreign_hooks_before_copy():
    class Foreign:
        def __deepcopy__(self, memo):
            raise AssertionError("foreign copy hook executed")

        def __eq__(self, other):
            raise AssertionError("foreign equality hook executed")

    with pytest.raises(ValueError):
        solve._assembly_snapshot({"outputs": Foreign()})


def test_candidate_arithmetic_hashes_and_earliest_selection(valid_request):
    result = actual_run(deepcopy(valid_request))
    outputs, candidates = result["outputs"], result["outputs"]["candidates"]
    for index, candidate in enumerate(candidates):
        assert candidate["index"] == index
        actual_request = solve._assembly_input(valid_request, candidate["angular_speeds_rad_s"])
        assert candidate["request_sha256"] == sha256_record(actual_request)
        fr = [a - b for a, b in zip(candidate["net_force_body_n"], valid_request["required_net_force_body_n"], strict=True)]
        mr = [a - b for a, b in zip(candidate["net_moment_cg_body_nm"], valid_request["required_net_moment_cg_body_nm"], strict=True)]
        scaled = [v / valid_request["absolute_force_tolerance_n"] for v in fr] + [v / valid_request["absolute_moment_tolerance_nm"] for v in mr]
        assert candidate["force_residual_n"] == fr
        assert candidate["moment_residual_nm"] == mr
        assert candidate["scaled_residual"] == scaled
        assert candidate["max_scaled_residual"] == max(map(abs, scaled))
    selected = candidates[outputs["selected_index"]]
    assert outputs["selected_index"] == min(range(len(candidates)), key=lambda i: candidates[i]["max_scaled_residual"])
    assert selected["request_sha256"] == sha256_record(outputs["actual_assembly_request"])
    assert selected["result_sha256"] == sha256_record(outputs["actual_assembly_result"])
    assert result["request_sha256"] == sha256_record(valid_request)
    assert result["evaluation_sha256"] == sha256_record({k: v for k, v in result.items() if k != "evaluation_sha256"})


def test_actual_four_rotor_asymmetric_canted_geometry(valid_request):
    template = assembly_request()
    base = deepcopy(template["rotors"][0])
    template["rotors"] = []
    for index, (center, axis, spin) in enumerate([
        ([1.2, 0.7, 0.1], [0.6, 0.0, 0.8], 1),
        ([-0.9, 0.8, -0.1], [-0.6, 0.0, 0.8], -1),
        ([-1.1, -0.6, 0.2], [0.0, 0.6, 0.8], 1),
        ([0.8, -1.0, -0.2], [0.0, -0.6, 0.8], -1),
    ]):
        rotor = deepcopy(base)
        rotor.update(id=f"r{index}", center_body_m=center, axis_body=axis, rotation_sign=spin)
        template["rotors"].append(rotor)
    target = assembly.evaluate_tabulated_rotor_assembly(deepcopy(template))
    assert target["status"] == "COMPUTED_EXPERIMENTAL"
    supplied = deepcopy(valid_request)
    supplied["assembly_template"] = template
    supplied["rotor_speed_bounds"] = []
    for rotor in template["rotors"]:
        del rotor["rotor_template"]["angular_speed_rad_s"]
        supplied["rotor_speed_bounds"].append({"id": rotor["id"], "angular_speed_bracket_rad_s": [50.0, 300.0], "initial_angular_speed_rad_s": 100.0})
    supplied["required_net_force_body_n"] = target["outputs"]["net_force_body_n"]
    supplied["required_net_moment_cg_body_nm"] = target["outputs"]["net_moment_cg_body_nm"]
    supplied["max_evaluations"] = 64
    result = actual_run(supplied)
    assert result["outputs"]["outcome"] == "RESIDUAL_MET"
    rows = result["outputs"]["actual_assembly_result"]["outputs"]["rotors"]
    assert any(row["force_body_n"][0] != 0.0 for row in rows)
    assert any(row["moment_cg_body_nm"][2] != 0.0 for row in rows)


def test_fixed_scipy_arguments_with_actual_objective_chain(valid_request):
    original, calls = solve.least_squares, []

    def wrapped(fun, initial, **kwargs):
        assert kwargs == {"bounds": ([50.0, 50.0], [300.0, 300.0]), "method": "trf", "jac": "2-point", "loss": "linear", "x_scale": 1, "ftol": 1e-12, "xtol": 1e-12, "gtol": 1e-12, "max_nfev": 32}

        def objective(x):
            calls.append(list(x))
            return fun(x)

        return original(objective, initial, **kwargs)

    with patch.object(solve, "least_squares", side_effect=wrapped):
        result = actual_run(deepcopy(valid_request))
    assert len(calls) == result["evaluation_count"]
    assert calls == [c["angular_speeds_rad_s"] for c in result["outputs"]["candidates"]]


@pytest.mark.parametrize("call_objective", [False, True])
def test_solver_return_policy_without_claiming_numerical_convergence(valid_request, call_objective):
    supplied = deepcopy(valid_request)
    supplied["required_net_force_body_n"][0] = 100.0

    def stopped(fun, initial, **kwargs):
        if call_objective:
            fun(initial)
        return object()

    with patch.object(solve, "least_squares", side_effect=stopped):
        result = solve.evaluate_tabulated_static_wrench_solve(supplied)
    if call_objective:
        assert result["status"] == "COMPUTED_EXPERIMENTAL"
        assert result["outputs"]["outcome"] == "SOLVER_STOPPED"
        assert result["evaluation_count"] == 1
    else:
        assert result["status"] == "EXECUTION_FAILED"
        assert result["outputs"] == {}
        assert result["evaluation_count"] == 0


def test_catalog_is_fresh_and_executes_no_children():
    with patch.object(assembly, "evaluate_tabulated_rotor_assembly") as child, patch.object(solve, "least_squares") as scipy:
        first = solve.tabulated_static_wrench_solve_catalog()
        untouched = deepcopy(first)
        first["limits"]["input_json"]["max_depth"] = 0
        first["output_field_units"]["candidates"]["net_force_body_n"] = "wrong"
        first["input_units"]["assembly_template"]["rotors"]["rotor_template"].clear()
        assert solve.tabulated_static_wrench_solve_catalog() == untouched
        child.assert_not_called()
        scipy.assert_not_called()


@pytest.mark.parametrize("error", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("location", ["child", "solver"])
def test_base_exception_propagates(valid_request, error, location):
    owner, name = (assembly, "evaluate_tabulated_rotor_assembly") if location == "child" else (solve, "least_squares")
    with patch.object(owner, name, side_effect=error("private sentinel")), pytest.raises(error):
        solve.evaluate_tabulated_static_wrench_solve(deepcopy(valid_request))


@pytest.mark.parametrize("kind", ["cycle", "depth", "string", "integer", "nan", "subclass", "nodes", "output_container"])
def test_bounded_snapshot_json_extrema(kind):
    limits = deepcopy(solve._LIMITS["output_json"] if kind == "output_container" else solve._LIMITS["input_json"])
    if kind == "cycle":
        value = []
        value.append(value)
    elif kind == "depth":
        value = 0
        for _ in range(limits["max_depth"]):
            value = [value]
    elif kind == "string":
        value = "x" * (limits["max_string_characters"] + 1)
    elif kind == "integer":
        value = 1 << limits["max_integer_bits"]
    elif kind == "nan":
        value = math.nan
    elif kind == "subclass":
        class ForeignInt(int):
            pass
        value = ForeignInt(1)
    elif kind == "nodes":
        shared = [0] * 256
        value = [[shared] * 256] * 4  # Aliases count on every occurrence; helper only.
    else:
        value = [0] * (limits["max_container_items"] + 1)
    with pytest.raises(ValueError):
        solve._bounded_snapshot(value, limits)
