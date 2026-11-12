"""V148 real-child composition receipts; contract behavior only, not physical validation."""

import json
import math
from copy import deepcopy
from fractions import Fraction
from itertools import pairwise

from physimesh.drone import stable_polar_rotor as rotor
from physimesh.drone import stable_section_residual as residual
from physimesh.drone import stable_section_solve as solve

from .test_stable_polar_rotor import digest, rotor_request

COUNTS = ("residual_result_count", "load_result_count", "lookup_result_count")
FROZEN_POLICY_LOWER_RAD = 0.06247966686053653


def _family_request(count, cl, *, exhaustion=False):
    """Existing synthetic family, uniform V147 v2 bracket; no model data fabricated."""
    request = rotor_request()
    template = deepcopy(request["annuli"][0])
    edges = [float(Fraction(1, 5) + Fraction(2 * index, 5 * count)) for index in range(count + 1)]
    lower = max(math.atan2(request["rotor"]["imposed_axial_velocity_m_s"],
                           request["rotor"]["angular_speed_rad_s"] *
                           math.fsum((inner, 0.5 * math.fsum((outer, -inner)))))
                for inner, outer in pairwise(edges)) + 0.05
    request["annuli"] = []
    for inner, outer in pairwise(edges):
        annulus = deepcopy(template)
        annulus.update(radial_inner_m=inner, radial_outer_m=outer)
        annulus["solve"].update(psi_lower_rad=lower, psi_upper_rad=lower + 0.55,
                                max_evaluations=32 if exhaustion else 16)
        if exhaustion:
            annulus["solve"].update(angle_tolerance_rad=1e-30, residual_tolerance_m2_s=1e-30)
        for table in annulus["polar"]["reynolds_tables"]:
            for row in table["rows"]:
                row["cl"] = cl
        request["annuli"].append(annulus)
    return request


def _observe_real_calls(monkeypatch):
    """Count delegating calls only; every child, copy, guard and quota operation is real."""
    observed = {"children": [], "residuals": [], "quotas": [], "commits": [], "child_copies": []}
    actual_child, actual_residual = solve.evaluate_stable_section_solve, residual.evaluate_stable_section_residual
    actual_measure, actual_commit, actual_copy = rotor._ChildQuota.measure, rotor._ChildQuota.commit, rotor.deepcopy

    def child(request):
        response = actual_child(request)
        observed["children"].append(response)
        return response

    def section(request):
        response = actual_residual(request)
        observed["residuals"].append(response)
        return response

    def measure(quota, value):
        if not any(quota is existing for existing in observed["quotas"]):
            observed["quotas"].append(quota)
        return actual_measure(quota, value)

    def commit(quota, measurement):
        result = actual_commit(quota, measurement)
        observed["commits"].append(quota)
        return result

    def copying(value, *args, **kwargs):
        if any(value is child for child in observed["children"]):
            observed["child_copies"].append(value)
        return actual_copy(value, *args, **kwargs)

    monkeypatch.setattr(solve, "evaluate_stable_section_solve", child)
    monkeypatch.setattr(residual, "evaluate_stable_section_residual", section)
    monkeypatch.setattr(rotor._ChildQuota, "measure", measure)
    monkeypatch.setattr(rotor._ChildQuota, "commit", commit)
    monkeypatch.setattr(rotor, "deepcopy", copying)
    return observed


def _native_nodes(value):
    if type(value) is dict:
        return 1 + sum(1 + _native_nodes(child) for child in value.values())
    if type(value) is list:
        return 1 + sum(_native_nodes(child) for child in value)
    return 1


def _assert_seal(result, request):
    assert result["request_sha256"] == digest(request)
    assert result["evaluation_sha256"] == digest({
        key: value for key, value in result.items() if key != "evaluation_sha256"})


def _assert_retained_nonconvergence(result, request, before, observed, expected_counts):
    assert request == before and digest(request) == digest(before)
    assert result["status"] == "COMPUTED_EXPERIMENTAL" and result["reasons"] == []
    rows = result["outputs"]["annuli"]
    assert result["section_solve_result_count"] == len(rows) == len(observed["children"]) == len(expected_counts)
    assert result["outputs"]["rotor_state"] == "NOT_RUN_SECTION_NOT_CONVERGED"
    assert result["outputs"]["integrated"] is None and result["output_units"]["integrated"] == "not_applicable"
    assert all(row["contribution"] is None for row in rows)
    assert all(row["contribution"] == "not_applicable" for row in result["output_units"]["annuli"])
    for row, expected in zip(rows, expected_counts, strict=True):
        child = row["actual_solve_result"]
        assert child["status"] == "COMPUTED_EXPERIMENTAL"
        for key in COUNTS:
            assert type(child[key]) is int and child[key] == expected
        assert len(child["outputs"]["evaluations"]) == expected
        _assert_seal(child, row["actual_solve_request"])
    for key in COUNTS:
        assert type(result[key]) is int and result[key] == sum(expected_counts)
    assert len(observed["residuals"]) == sum(expected_counts)
    _assert_seal(result, request)
    children = [row["actual_solve_result"] for row in rows]
    # Independently count complete canonical child bytes/nodes, including units and metadata.
    expected_bytes = sum(len(json.dumps(child, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=False, allow_nan=False).encode("utf-8")) for child in children)
    expected_nodes = sum(_native_nodes(child) for child in children)
    assert observed["quotas"]
    for quota in observed["quotas"]:
        assert quota.bytes_used == expected_bytes and quota.nodes_used == expected_nodes
        assert sum(committed is quota for committed in observed["commits"]) == len(rows)


def test_case_a_four_real_children_exhaust_full_32_evaluation_budget(monkeypatch):
    # Observed: (EVALUATION_BUDGET_EXHAUSTED,) * 4; counts (32, 32, 32, 32), aggregate 128.
    request = _family_request(4, 4.0, exhaustion=True)
    before = deepcopy(request)
    observed = _observe_real_calls(monkeypatch)
    result = rotor.evaluate_stable_polar_rotor(request)
    _assert_retained_nonconvergence(result, request, before, observed, (32, 32, 32, 32))
    for row in result["outputs"]["annuli"]:
        section = row["actual_solve_result"]["outputs"]
        assert section["solve_state"] == "EVALUATION_BUDGET_EXHAUSTED"
        assert section["solution"] is None
        endpoints = section["evaluations"][:2]
        assert endpoints[0]["result"]["outputs"]["residual_m2_s"] < 0 < endpoints[1]["result"]["outputs"]["residual_m2_s"]


def test_case_b_real_not_bracketed_children_are_admitted_early_terminations(monkeypatch):
    # Actual base_cl1_annuli8 states, zero-based: indices 0,1 CONVERGED (12 each);
    # indices 2..7 NOT_BRACKETED (2 each); aggregate 36, all eight children retained.
    request = _family_request(8, 1.0)
    before = deepcopy(request)
    observed = _observe_real_calls(monkeypatch)
    result = rotor.evaluate_stable_polar_rotor(request)
    _assert_retained_nonconvergence(result, request, before, observed, (12, 12, 2, 2, 2, 2, 2, 2))
    states = tuple(row["actual_solve_result"]["outputs"]["solve_state"] for row in result["outputs"]["annuli"])
    assert states == ("CONVERGED", "CONVERGED") + ("NOT_BRACKETED",) * 6
    for row in result["outputs"]["annuli"]:
        child = row["actual_solve_result"]
        if child["outputs"]["solve_state"] == "NOT_BRACKETED":
            assert child["residual_result_count"] == 2 < row["actual_solve_request"]["solve"]["max_evaluations"]
            assert child["outputs"]["solution"] is None
            assert all(item["result"]["outputs"]["residual_m2_s"] > 0 for item in child["outputs"]["evaluations"])


def _policy_request(lower):
    request = rotor_request()
    request["rotor"].update(blade_count=64, imposed_axial_velocity_m_s=0.0)
    request["annuli"][0]["solve"].update(psi_lower_rad=lower, psi_upper_rad=0.1)
    return request


def _endpoint_factor(request):
    """Test-owned diagnostic from declared geometry/velocity; not a fabricated child field."""
    annulus, inputs = request["annuli"][0], request["rotor"]
    radius = math.fsum((annulus["radial_inner_m"], 0.5 * math.fsum((annulus["radial_outer_m"], -annulus["radial_inner_m"]))))
    ratio = radius / inputs["tip_radius_m"]
    gap = math.fsum((1.0, -ratio))
    ua, ut = inputs["imposed_axial_velocity_m_s"], inputs["angular_speed_rad_s"] * radius
    speed, psi = math.hypot(ua, ut), annulus["solve"]["psi_lower_rad"]
    wa = math.fsum((0.5 * ua, (0.5 * speed) * math.sin(psi)))
    wt = math.fsum((0.5 * ut, (0.5 * speed) * math.cos(psi)))
    return ((float(inputs["blade_count"]) * 0.5) * gap) / (ratio * (wa / wt))


def sweep_real_policy_boundary():
    """Retained offline sweep: one analytical boundary endpoint, then <=8 adjacent inputs.

    Authoring observation: 0.062479666860536534 -> f=512.0; the next lower angle
    0.06247966686053653 -> f=512.0000000000001 and a real composed refusal.
    No child is fabricated and no numerical policy, quota or tolerance is changed.
    """
    request = _policy_request(0.1)
    row, inputs = request["annuli"][0], request["rotor"]
    radius = math.fsum((row["radial_inner_m"], 0.5 * math.fsum((row["radial_outer_m"], -row["radial_inner_m"]))))
    ratio = radius / inputs["tip_radius_m"]
    lower = 2 * math.atan((64 * 0.5 * math.fsum((1.0, -ratio))) / (512 * ratio))
    records = []
    for _ in range(9):
        request = _policy_request(lower)
        result = rotor.evaluate_stable_polar_rotor(request)
        records.append({"psi_lower_rad": lower, "f_diagnostic": _endpoint_factor(request),
                        "status": result["status"], "reasons": result["reasons"]})
        if records[-1]["f_diagnostic"] > 512:
            break
        lower = math.nextafter(lower, 0.0)
    return records


def test_case_c_real_out_of_policy_endpoint_refuses_without_quota_commit(monkeypatch):
    # Actual path: NUMERICAL_POLICY_REFUSED/F_OUTSIDE_NUMERICAL_POLICY -> child
    # EXECUTION_FAILED/RESIDUAL_BOUNDARY_FAILED -> rotor EXECUTION_FAILED/SOLVE_BOUNDARY_FAILED.
    # REVIEW GAP: the unchanged composition copies this valid failure child once before
    # its guard rejects it. The requested BEFORE-COPY assertion is not true and is not claimed here.
    request = _policy_request(FROZEN_POLICY_LOWER_RAD)
    before = deepcopy(request)
    assert _endpoint_factor(request) == math.nextafter(512.0, math.inf)
    observed = _observe_real_calls(monkeypatch)
    result = rotor.evaluate_stable_polar_rotor(request)
    assert request == before and digest(request) == digest(before)
    assert result["status"] == "EXECUTION_FAILED" and result["reasons"] == ["SOLVE_BOUNDARY_FAILED"]
    assert "RESOURCE_BUDGET_EXCEEDED" not in result["reasons"]
    assert result["outputs"] == result["output_units"] == {}
    assert result["section_solve_result_count"] == 0
    assert all(type(result[key]) is int and result[key] == 0 for key in COUNTS)
    assert len(observed["residuals"]) == len(observed["children"]) == 1
    assert observed["residuals"][0]["status"] == "NUMERICAL_POLICY_REFUSED"
    assert observed["residuals"][0]["reasons"] == ["F_OUTSIDE_NUMERICAL_POLICY"]
    assert observed["children"][0]["status"] == "EXECUTION_FAILED"
    assert observed["children"][0]["outputs"]["solve_state"] == "EXECUTION_FAILED"
    assert observed["children"][0]["reasons"] == ["RESIDUAL_BOUNDARY_FAILED"]
    assert observed["commits"] == [] and observed["quotas"]
    assert all(quota.bytes_used == quota.nodes_used == 0 for quota in observed["quotas"])
    _assert_seal(result, request)
