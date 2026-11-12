"""Synthetic V135 boundary and bisection checks; no physical qualification."""

import hashlib
import json
import math
from copy import deepcopy

import pytest

from physimesh.drone import section_residual as residual
from physimesh.drone import section_solve as solve


@pytest.fixture
def request_data():
    return {
        "evaluation": solve.EVALUATION,
        "residual_template": {
            "evaluation": residual.EVALUATION,
            "polar": {
                "airfoil_id": "invented-synthetic", "source": "invented fixture; no dataset",
                "source_kind": "synthetic", "uncertainty_status": "unknown",
                "sampled_mach_number": 0.1, "declared_mach_interval": [0, 0.9],
                "reynolds_tables": [
                    {"reynolds_number": re, "rows": [
                        {"alpha_rad": alpha, "cl": 4, "cd": 0.1}
                        for alpha in (-1.5, 0.0, 1.5)]}
                    for re in (1000.0, 10000000.0)],
            },
            "section": {
                "imposed_axial_velocity_m_s": 5, "imposed_tangential_velocity_m_s": 20,
                "tip_radius_m": 0.8, "radius_m": 0.4, "pitch_rad": 0.5,
                "chord_m": 0.1, "density_kg_m3": 1.2, "dynamic_viscosity_pa_s": 1.8e-5,
                "speed_of_sound_m_s": 343, "blade_count": 2,
            },
        },
        "solve": {"psi_lower_rad": 0.35, "psi_upper_rad": 0.9,
                  "angle_tolerance_rad": 0.001, "residual_tolerance_m2_s": 0.01,
                  "max_evaluations": 16},
    }


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf-8")).hexdigest()


def _reseal(value):
    value["evaluation_sha256"] = _digest({
        key: item for key, item in value.items() if key != "evaluation_sha256"})


def _actual(request, psi):
    actual = deepcopy(request["residual_template"])
    actual["section"]["psi_rad"] = psi
    return actual


def _record(monkeypatch):
    original, calls = residual.evaluate_section_residual, []

    def child(request):
        calls.append(deepcopy(request))
        return original(request)

    monkeypatch.setattr(residual, "evaluate_section_residual", child)
    return original, calls


def _counts(result, count):
    assert type(result["residual_result_count"]) is int
    assert result["residual_result_count"] == result["load_result_count"] == count
    assert result["lookup_result_count"] == count


def test_actual_unique_once_trace_hash_and_both_tolerances(request_data, monkeypatch):
    original, calls = _record(monkeypatch)
    result = solve.evaluate_section_solve(request_data)
    output = result["outputs"]
    rows = output["evaluations"]
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert output["solve_state"] == "CONVERGED"
    _counts(result, len(rows))
    assert 2 < len(rows) <= 16
    assert len(calls) == len(rows) == len({row["psi_rad"] for row in rows})
    assert [row["psi_rad"] for row in rows[:2]] == [0.35, 0.9]
    for row, actual in zip(rows, calls, strict=True):
        assert actual == _actual(request_data, row["psi_rad"])
        assert row["request_sha256"] == _digest(actual)
        assert row["result"] == original(actual)
        assert row["result"]["request_sha256"] == row["request_sha256"]
    bracket, solution = output["final_bracket"], output["solution"]
    lo, hi = (rows[bracket[key]]["psi_rad"] for key in (
        "lower_evaluation_index", "upper_evaluation_index"))
    assert bracket["angle_width_rad"] == hi - lo <= 0.001
    assert abs(solution["residual_m2_s"]) <= 0.01
    owner = rows[solution["evaluation_index"]]
    assert solution["psi_rad"] == owner["psi_rad"]
    assert solution["residual_m2_s"] == owner["result"]["outputs"]["residual_m2_s"]
    assert result["request_sha256"] == _digest(request_data)
    assert result["evaluation_sha256"] == _digest({
        key: value for key, value in result.items() if key != "evaluation_sha256"})


def test_two_call_budget_no_solution(request_data, monkeypatch):
    request_data["solve"]["max_evaluations"] = 2
    _, calls = _record(monkeypatch)
    result = solve.evaluate_section_solve(request_data)
    _counts(result, 2)
    assert len(calls) == 2
    assert result["outputs"]["solve_state"] == "EVALUATION_BUDGET_EXHAUSTED"
    assert result["outputs"]["solution"] is None


def test_not_bracketed_zero_cl(request_data):
    for table in request_data["residual_template"]["polar"]["reynolds_tables"]:
        for row in table["rows"]:
            row["cl"] = 0
    result = solve.evaluate_section_solve(request_data)
    _counts(result, 2)
    assert result["outputs"]["solve_state"] == "NOT_BRACKETED"
    assert result["outputs"]["solution"] is None
    assert all(row["result"]["outputs"]["residual_m2_s"] > 0
               for row in result["outputs"]["evaluations"])
    assert result["feasibility"] is None


def test_lower_ood_stops_after_one_actual_call(request_data, monkeypatch):
    request_data["residual_template"]["polar"].update(
        sampled_mach_number=0, declared_mach_interval=[0, 0])
    _, calls = _record(monkeypatch)
    result = solve.evaluate_section_solve(request_data)
    _counts(result, 1)
    assert len(calls) == 1
    output = result["outputs"]
    assert output["solve_state"] == "NOT_RUN_OUT_OF_POLAR_DOMAIN"
    assert output["final_bracket"] is output["solution"] is None
    assert output["evaluations"][0]["result"]["outputs"]["residual_m2_s"] is None
    assert result["output_units"]["evaluations"][0]["result"]["outputs"]["closure"] == (
        "not_applicable")


def test_upper_ood_stops_after_two_actual_calls(request_data, monkeypatch):
    ua, ut = 5, 20
    u, phi = math.hypot(ua, ut), math.atan2(ua, ut)
    mach = [u * math.cos((psi - phi) / 2) / 343 for psi in (0.35, 0.9)]
    request_data["residual_template"]["polar"]["declared_mach_interval"] = [sum(mach) / 2, 0.9]
    _, calls = _record(monkeypatch)
    result = solve.evaluate_section_solve(request_data)
    _counts(result, 2)
    assert len(calls) == 2
    output = result["outputs"]
    assert output["solve_state"] == "NOT_RUN_OUT_OF_POLAR_DOMAIN"
    assert output["final_bracket"] is output["solution"] is None
    assert output["evaluations"][0]["result"]["outputs"]["residual_state"] == "COMPUTED"
    assert output["evaluations"][1]["result"]["outputs"]["residual_m2_s"] is None


def test_bad_upper_preflight_before_any_actual_call(request_data, monkeypatch):
    request_data["solve"]["psi_upper_rad"] = math.pi / 2
    _, calls = _record(monkeypatch)
    result = solve.evaluate_section_solve(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    _counts(result, 0)
    assert calls == []
    assert result["request_sha256"] is result["evaluation_sha256"] is None


def test_rehashed_child_tampering_rejected(request_data, monkeypatch):
    original = residual.evaluate_section_residual

    def child(request):
        result = original(request)
        result["outputs"]["closure"]["gamma_induced_m2_s"] += 1
        _reseal(result)
        return result

    monkeypatch.setattr(residual, "evaluate_section_residual", child)
    result = solve.evaluate_section_solve(request_data)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["reasons"] == ["RESIDUAL_BOUNDARY_FAILED"]
    _counts(result, 0)
    assert result["outputs"] == result["output_units"] == {}


def test_pure_guard_uses_no_v134_numerical_helpers(request_data, monkeypatch):
    request = _actual(request_data, 0.6)
    result = residual.evaluate_section_residual(request)

    def forbidden(*args, **kwargs):
        pytest.fail("V134 numerical helper or evaluator rerun by guard")

    for name in ("_velocity", "_closure", "evaluate_section_residual"):
        monkeypatch.setattr(residual, name, forbidden)
    solve._guard_residual(result, request)


@pytest.mark.parametrize("angle,residual_tolerance", [(1.0, 1e-30), (1e-30, 100.0)])
def test_actual_one_tolerance_alone_never_converges(request_data, angle, residual_tolerance):
    request_data["solve"].update(max_evaluations=2, angle_tolerance_rad=angle,
                                 residual_tolerance_m2_s=residual_tolerance)
    result = solve.evaluate_section_solve(request_data)
    output = result["outputs"]
    _counts(result, 2)
    assert output["solve_state"] == "EVALUATION_BUDGET_EXHAUSTED"
    width_passes = output["final_bracket"]["angle_width_rad"] <= angle
    residual_passes = min(abs(row["result"]["outputs"]["residual_m2_s"])
                          for row in output["evaluations"]) <= residual_tolerance
    assert width_passes != residual_passes
    assert output["solution"] is None


def test_actual_sixteen_call_budget_and_independent_bracket_replay(request_data, monkeypatch):
    request_data["solve"].update(angle_tolerance_rad=1e-30, residual_tolerance_m2_s=1e-30)
    _, calls = _record(monkeypatch)
    result = solve.evaluate_section_solve(request_data)
    output = result["outputs"]
    rows = output["evaluations"]
    _counts(result, 16)
    assert len(rows) == len(calls) == 16
    assert output["solve_state"] == "EVALUATION_BUDGET_EXHAUSTED"
    assert output["solution"] is None
    lower, upper = 0, 1
    for index in range(2, len(rows)):
        lo, hi = rows[lower]["psi_rad"], rows[upper]["psi_rad"]
        assert rows[index]["psi_rad"] == lo + 0.5 * (hi - lo)
        rlo = rows[lower]["result"]["outputs"]["residual_m2_s"]
        middle = rows[index]["result"]["outputs"]["residual_m2_s"]
        assert middle != 0
        if (rlo < 0 < middle) or (middle < 0 < rlo):
            upper = index
        else:
            lower = index
    assert output["final_bracket"] == {
        "lower_evaluation_index": lower, "upper_evaluation_index": upper,
        "angle_width_rad": rows[upper]["psi_rad"] - rows[lower]["psi_rad"],
    }


def _synthetic_bisect(values, *, lower=0.35, upper=0.9, angle=1e-12, tolerance=1e-12, budget=16):
    """TEST ONLY: fake callback exercises algorithm branches, never actual V134 validity."""
    rows, calls = [], []

    def fake_callback(request):
        psi = request["section"]["psi_rad"]
        value = values[len(rows)]
        calls.append(psi)
        rows.append({"psi_rad": psi, "result": {"outputs": {"residual_m2_s": value}}})
        return len(rows) - 1

    state, bracket, solution = solve._bisect(
        rows, fake_callback, [{"section": {"psi_rad": psi}} for psi in (lower, upper)],
        {"angle_tolerance_rad": angle, "residual_tolerance_m2_s": tolerance,
         "max_evaluations": budget})
    return state, bracket, solution, rows, calls


@pytest.mark.parametrize("values,index", [([0.0, 1.0], 0), ([-1.0, -0.0], 1), ([0.0, 0.0], 0)])
def test_synthetic_algorithm_only_exact_endpoint_zero(values, index):
    state, bracket, solution, rows, calls = _synthetic_bisect(values)
    assert state == "CONVERGED"
    assert calls == [0.35, 0.9]
    assert bracket == {"lower_evaluation_index": index, "upper_evaluation_index": index,
                       "angle_width_rad": 0.0}
    assert solution == {"evaluation_index": index, "psi_rad": rows[index]["psi_rad"],
                        "residual_m2_s": values[index]}


def test_synthetic_algorithm_only_exact_midpoint_zero():
    state, bracket, solution, _, calls = _synthetic_bisect([-1.0, 1.0, 0.0])
    assert state == "CONVERGED"
    assert calls == [0.35, 0.9, 0.35 + 0.5 * (0.9 - 0.35)]
    assert bracket == {"lower_evaluation_index": 2, "upper_evaluation_index": 2,
                       "angle_width_rad": 0.0}
    assert solution["evaluation_index"] == 2


def test_synthetic_algorithm_only_float_stagnation():
    lower, upper = 0.5, math.nextafter(0.5, math.inf)
    state, bracket, solution, _, calls = _synthetic_bisect(
        [-1.0, 1.0], lower=lower, upper=upper, angle=1e-30, tolerance=1e-30)
    assert state == "FLOAT_STAGNATION"
    assert calls == [lower, upper]
    assert bracket["angle_width_rad"] == upper - lower
    assert solution is None


def test_synthetic_algorithm_only_interior_ood_preserves_valid_bracket():
    state, bracket, solution, rows, calls = _synthetic_bisect([-1.0, 1.0, None])
    assert state == "NOT_RUN_OUT_OF_POLAR_DOMAIN"
    assert len(rows) == len(calls) == 3
    assert rows[-1]["result"]["outputs"]["residual_m2_s"] is None
    assert bracket == {"lower_evaluation_index": 0, "upper_evaluation_index": 1,
                       "angle_width_rad": 0.9 - 0.35}
    assert solution is None


@pytest.mark.parametrize("values,expected", [([-1.0, 1.0], 0), ([2.0, -1.0], 1)])
def test_synthetic_algorithm_only_endpoint_selection_and_tie(values, expected):
    state, _, solution, _, calls = _synthetic_bisect(values, angle=1.0, tolerance=2.0)
    assert state == "CONVERGED"
    assert solution["evaluation_index"] == expected
    assert len(calls) == 2


@pytest.mark.parametrize("values", [[-1e308, 1e308], [1e308, -1e308]])
def test_synthetic_algorithm_only_sign_comparison_avoids_product_overflow(values):
    state, _, solution, _, _ = _synthetic_bisect(values, budget=2)
    assert state == "EVALUATION_BUDGET_EXHAUSTED"
    assert solution is None


@pytest.mark.parametrize("path,value", [
    (("solve", "max_evaluations"), True), (("solve", "max_evaluations"), 2.0),
    (("solve", "max_evaluations"), 1), (("solve", "max_evaluations"), 17),
    (("solve", "psi_lower_rad"), True), (("solve", "psi_lower_rad"), 0),
    (("solve", "psi_lower_rad"), -1), (("solve", "psi_lower_rad"), math.atan2(5, 20)),
    (("solve", "psi_lower_rad"), 0.9), (("solve", "psi_lower_rad"), 1),
    (("solve", "psi_upper_rad"), math.pi / 2), (("solve", "psi_upper_rad"), False),
    (("solve", "angle_tolerance_rad"), 0), (("solve", "angle_tolerance_rad"), -1),
    (("solve", "angle_tolerance_rad"), math.nextafter(0.0, 1.0)),
    (("solve", "residual_tolerance_m2_s"), False),
    (("solve", "residual_tolerance_m2_s"), math.inf),
    (("solve", "residual_tolerance_m2_s"), math.nan),
    (("residual_template", "section", "psi_rad"), 0.6),
    (("residual_template", "section", "blade_count"), True),
    (("residual_template", "evaluation"), "section_load_experimental"),
    (("residual_template", "polar", "reynolds_tables", 1, "rows", 2, "cd"), -1),
])
def test_invalid_static_fields_before_hash_or_model(request_data, monkeypatch, path, value):
    target = request_data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    def forbidden(*args, **kwargs):
        pytest.fail("invalid input reached hashing or evaluator")

    monkeypatch.setattr(solve, "sha256_record", forbidden)
    monkeypatch.setattr(residual, "evaluate_section_residual", forbidden)
    result = solve.evaluate_section_solve(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    _counts(result, 0)
    assert result["outputs"] == result["output_units"] == {}
    assert result["request_sha256"] is result["evaluation_sha256"] is None


@pytest.mark.parametrize("path", [(), ("solve",), ("residual_template",),
                                  ("residual_template", "section")])
@pytest.mark.parametrize("mutation", ["extra", "missing"])
def test_exact_schema_at_every_request_level(request_data, monkeypatch, path, mutation):
    target = request_data
    for key in path:
        target = target[key]
    if mutation == "extra":
        target["unexpected"] = 1
    else:
        target.pop(next(iter(target)))
    _, calls = _record(monkeypatch)
    result = solve.evaluate_section_solve(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert calls == []
    _counts(result, 0)


@pytest.mark.parametrize("value", ["\ud800", "a" * 2001, [None] * 257, 1 << 1023])
def test_whole_json_limits_before_copy_hash_and_model(request_data, monkeypatch, value):
    request_data["untrusted"] = value
    _, calls = _record(monkeypatch)
    result = solve.evaluate_section_solve(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert calls == []
    assert result["request_sha256"] is result["evaluation_sha256"] is None


def test_cycle_refused_before_copy(request_data, monkeypatch):
    request_data["untrusted"] = request_data
    _, calls = _record(monkeypatch)
    result = solve.evaluate_section_solve(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert calls == []


def test_foreign_input_hooks_never_run(request_data, monkeypatch):
    class ForeignDict(dict):
        def __deepcopy__(self, memo):
            pytest.fail("foreign copy hook")

        def items(self):
            pytest.fail("foreign iteration hook")

    request_data["residual_template"]["section"] = ForeignDict(
        request_data["residual_template"]["section"])
    _, calls = _record(monkeypatch)
    result = solve.evaluate_section_solve(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert calls == []


@pytest.mark.parametrize("failure_call,accepted", [(1, 0), (3, 2)])
def test_ordinary_child_failure_is_atomic(request_data, monkeypatch, failure_call, accepted):
    original, calls = residual.evaluate_section_residual, []

    def child(request):
        calls.append(None)
        if len(calls) == failure_call:
            raise ValueError("private child failure")
        return original(request)

    monkeypatch.setattr(residual, "evaluate_section_residual", child)
    result = solve.evaluate_section_solve(request_data)
    _counts(result, accepted)
    assert len(calls) == failure_call
    assert result["status"] == "EXECUTION_FAILED"
    assert result["reasons"] == ["RESIDUAL_BOUNDARY_FAILED"]
    assert result["outputs"] == result["output_units"] == {}
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("path,value", [
    (("physical_validation",), "ESTABLISHED"), (("load_result_count",), True),
    (("lookup_result_count",), True), (("outputs", "closure", "F"), 0.5),
    (("outputs", "residual_m2_s"), 0.0), (("source_urls", 0), "https://invalid.example"),
    (("request_sha256",), "0" * 64), (("schema_version",), "wrong"),
    (("output_units", "residual_m2_s"), "N"),
    (("outputs", "actual_load_result", "lookup_result_count"), True),
    (("outputs", "actual_load_result", "outputs", "loads", "dynamic_pressure_pa"), 1.0),
    (("outputs", "actual_load_request", "section", "blade_count"), 2.0),
    (("outputs", "kinematics", "imposed_axial_velocity_m_s"), 5),
])
def test_second_child_rehashed_tampering_keeps_only_prior_count(request_data, monkeypatch, path, value):
    original, calls = residual.evaluate_section_residual, []

    def child(request):
        result = original(request)
        calls.append(None)
        if len(calls) == 2:
            target = result
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            _reseal(result)
        return result

    monkeypatch.setattr(residual, "evaluate_section_residual", child)
    result = solve.evaluate_section_solve(request_data)
    _counts(result, 1)
    assert len(calls) == 2
    assert result["reasons"] == ["RESIDUAL_BOUNDARY_FAILED"]
    assert result["outputs"] == result["output_units"] == {}


def test_forged_ood_cannot_pass_full_guard(request_data, monkeypatch):
    original = residual.evaluate_section_residual

    def child(request):
        result = original(request)
        result["outputs"].update(residual_state="NOT_RUN_OUT_OF_POLAR_DOMAIN",
                                  closure=None, residual_m2_s=None)
        _reseal(result)
        return result

    monkeypatch.setattr(residual, "evaluate_section_residual", child)
    result = solve.evaluate_section_solve(request_data)
    _counts(result, 0)
    assert result["reasons"] == ["RESIDUAL_BOUNDARY_FAILED"]
    assert result["outputs"] == {}


def test_child_subclass_refused_before_copy_hook(request_data, monkeypatch):
    original = residual.evaluate_section_residual

    class ForeignDict(dict):
        def __deepcopy__(self, memo):
            pytest.fail("foreign child copy hook")

    def child(request):
        result = original(request)
        result["outputs"]["closure"] = ForeignDict(result["outputs"]["closure"])
        return result

    monkeypatch.setattr(residual, "evaluate_section_residual", child)
    result = solve.evaluate_section_solve(request_data)
    _counts(result, 0)
    assert result["reasons"] == ["RESIDUAL_BOUNDARY_FAILED"]


def test_fresh_child_catalog_tamper_refused(request_data, monkeypatch):
    original = residual.section_residual_catalog

    def catalog():
        result = original()
        result["source_urls"].clear()
        return result

    monkeypatch.setattr(residual, "section_residual_catalog", catalog)
    result = solve.evaluate_section_solve(request_data)
    _counts(result, 0)
    assert result["reasons"] == ["RESIDUAL_BOUNDARY_FAILED"]


def test_persistent_root_hash_failure_clears_payload_and_both_hashes(request_data, monkeypatch):
    request_data["solve"]["max_evaluations"] = 2
    original = solve.sha256_record

    def hashing(value):
        if "residual_result_count" in value:
            raise ValueError("private export failure")
        return original(value)

    monkeypatch.setattr(solve, "sha256_record", hashing)
    result = solve.evaluate_section_solve(request_data)
    _counts(result, 2)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["outputs"] == result["output_units"] == {}
    assert result["request_sha256"] is result["evaluation_sha256"] is None


def test_first_hash_failure_has_no_child_call(request_data, monkeypatch):
    _, calls = _record(monkeypatch)

    def hashing(_):
        raise ValueError("private input hash failure")

    monkeypatch.setattr(solve, "sha256_record", hashing)
    result = solve.evaluate_section_solve(request_data)
    _counts(result, 0)
    assert calls == []
    assert result["outputs"] == result["output_units"] == {}
    assert result["request_sha256"] is result["evaluation_sha256"] is None


@pytest.mark.parametrize("target", ["child", "closure", "parent_hash"])
def test_baseexceptions_propagate(request_data, monkeypatch, target):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    if target == "child":
        monkeypatch.setattr(residual, "evaluate_section_residual", interrupted)
    else:
        monkeypatch.setattr(solve, "_closure" if target == "closure" else "sha256_record", interrupted)
    with pytest.raises(KeyboardInterrupt):
        solve.evaluate_section_solve(request_data)


def test_catalog_is_fresh_without_evaluation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("catalog invoked evaluator")

    monkeypatch.setattr(residual, "evaluate_section_residual", forbidden)
    first = solve.section_solve_catalog()
    first["source_urls"].clear()
    first["limits"]["input_json"]["max_depth"] = -1
    first["input_units"]["residual_template"]["section"].clear()
    second = solve.section_solve_catalog()
    assert second["status"] == "RESEARCH_ONLY"
    _counts(second, 0)
    assert second["request_sha256"] is second["evaluation_sha256"] is None
    assert second["source_urls"]
    assert second["limits"]["input_json"]["max_depth"] == 12
    assert second["input_units"]["residual_template"]["section"]["pitch_rad"] == "rad"
    assert "psi_rad" not in second["input_units"]["residual_template"]["section"]


def test_input_and_results_deeply_detached(request_data):
    request_data["solve"]["max_evaluations"] = 2
    before = deepcopy(request_data)
    first = solve.evaluate_section_solve(request_data)
    assert request_data == before
    rows = first["outputs"]["evaluations"]
    rows[0]["result"]["outputs"]["actual_load_request"]["polar"]["source"] = "changed"
    assert rows[1]["result"]["outputs"]["actual_load_request"]["polar"] == (
        before["residual_template"]["polar"])
    assert rows[0]["result"]["outputs"]["actual_load_result"]["outputs"][
        "actual_lookup_request"]["polar"] == before["residual_template"]["polar"]
    first["limits"]["output_json"]["max_depth"] = -1
    first["output_units"]["evaluations"][0]["result"]["outputs"].clear()
    second = solve.evaluate_section_solve(request_data)
    assert second["limits"]["output_json"]["max_depth"] == 32
    assert second["outputs"]["evaluations"][0]["result"]["outputs"][
        "actual_load_request"]["polar"] == before["residual_template"]["polar"]
    assert second["output_units"]["evaluations"][0]["result"]["outputs"]
    assert second["physical_validation"] == second["numerical_qualification"] == "NOT_ESTABLISHED"
    assert second["runtime_identity"] == "NOT_ESTABLISHED"
    assert second["feasibility"] is second["aircraft_status"] is None


def _node_tree(nodes):
    """Exact node count with at most 256 children per list and no giant container."""
    if nodes == 1:
        return None
    cap = 1 if nodes <= 257 else (257 if nodes <= 65793 else 65793)
    remaining, result = nodes - 1, []
    while remaining:
        child_nodes = min(cap, remaining)
        result.append(_node_tree(child_nodes))
        remaining -= child_nodes
    return result


@pytest.mark.parametrize("options,limit,depth", [
    ({}, 32768, 12), ({"request": True}, 32768, 10),
    ({"child": True}, 65536, 24), ({"output": True}, 2097152, 32),
])
def test_exact_walk_node_and_depth_limits(options, limit, depth):
    tree = _node_tree(limit)
    solve._walk(tree, **options)
    tree.append(None)
    with pytest.raises(ValueError):
        solve._walk(tree, **options)
    tree = None
    for _ in range(depth - 1):
        tree = [tree]
    solve._walk(tree, **options)
    with pytest.raises(ValueError):
        solve._walk([tree], **options)


def test_maximum_polar_two_actual_full_traces(request_data, monkeypatch):
    rows = [{"alpha_rad": -1.5 + 3 * index / 255, "cl": 4, "cd": 0.1}
            for index in range(256)]
    request_data["residual_template"]["polar"]["reynolds_tables"] = [
        {"reynolds_number": 1000.0 * 10 ** index, "rows": deepcopy(rows)} for index in range(8)]
    request_data["solve"]["max_evaluations"] = 2
    original, calls = _record(monkeypatch)
    result = solve.evaluate_section_solve(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    _counts(result, 2)
    assert len(calls) == 2
    for row, request in zip(result["outputs"]["evaluations"], calls, strict=True):
        assert row["result"] == original(request)
        assert row["result"]["outputs"]["actual_load_request"]["polar"] == (
            request_data["residual_template"]["polar"])
        solve._walk(row["result"], child=True)
    solve._walk(result, output=True)


def test_actual_v134_closure_failure_is_not_a_guarded_residual(request_data, monkeypatch):
    request_data["residual_template"]["section"]["radius_m"] = 1e-4
    original, returned = residual.evaluate_section_residual, []

    def child(request):
        result = original(request)
        returned.append(result)
        return result

    monkeypatch.setattr(residual, "evaluate_section_residual", child)
    result = solve.evaluate_section_solve(request_data)
    assert len(returned) == 1
    assert returned[0]["status"] == "EXECUTION_FAILED"
    assert returned[0]["load_result_count"] == 1
    _counts(result, 0)
    assert result["reasons"] == ["RESIDUAL_BOUNDARY_FAILED"]
    assert result["outputs"] == result["output_units"] == {}


def test_native_large_integer_knot_and_signed_zero_survive_full_guard(request_data):
    probe = residual.evaluate_section_residual(_actual(request_data, 0.35))
    query = probe["outputs"]["actual_load_result"]["outputs"]["actual_lookup_request"]["query"]
    knot = 2 ** 53 + 1
    request_data["residual_template"]["polar"]["reynolds_tables"] = [{
        "reynolds_number": query["reynolds_number"],
        "rows": [{"alpha_rad": query["alpha_rad"], "cl": knot, "cd": -0.0},
                 {"alpha_rad": 1.5, "cl": 0, "cd": 0}],
    }]
    result = solve.evaluate_section_solve(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    lookup = result["outputs"]["evaluations"][0]["result"]["outputs"][
        "actual_load_result"]["outputs"]["actual_lookup_result"]["outputs"]
    assert type(lookup["cl"]) is int and lookup["cl"] == knot
    assert type(lookup["cd"]) is float and math.copysign(1, lookup["cd"]) == -1


def test_signed_zero_request_tampering_rejected(request_data, monkeypatch):
    request_data["residual_template"]["section"]["pitch_rad"] = -0.0
    original = residual.evaluate_section_residual

    def child(request):
        result = original(request)
        result["outputs"]["actual_load_request"]["section"]["pitch_rad"] = 0.0
        _reseal(result)
        return result

    monkeypatch.setattr(residual, "evaluate_section_residual", child)
    result = solve.evaluate_section_solve(request_data)
    _counts(result, 0)
    assert result["reasons"] == ["RESIDUAL_BOUNDARY_FAILED"]


def test_native_int_float_change_binds_distinct_root_hash(request_data):
    request_data["solve"]["max_evaluations"] = 2
    first = solve.evaluate_section_solve(request_data)
    request_data["residual_template"]["section"]["imposed_axial_velocity_m_s"] = 5.0
    second = solve.evaluate_section_solve(request_data)
    assert first["request_sha256"] != second["request_sha256"]
    assert second["request_sha256"] == _digest(request_data)


def test_nonfinite_export_is_atomic(request_data, monkeypatch):
    request_data["solve"]["max_evaluations"] = 2
    monkeypatch.setattr(solve, "_output_units", lambda _: {"bad": math.nan})
    result = solve.evaluate_section_solve(request_data)
    _counts(result, 2)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["outputs"] == result["output_units"] == {}
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("value", [True, -1, 17])
def test_seal_rejects_invalid_count_types_and_bounds(value):
    result = solve._response("RESEARCH_ONLY", [])
    for key in ("residual_result_count", "load_result_count", "lookup_result_count"):
        result[key] = value
    with pytest.raises(ValueError):
        solve._seal(result)
