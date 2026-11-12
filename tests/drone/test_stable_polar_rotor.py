"""Private V141 composition checks; synthetic fixtures, no physical qualification."""

import hashlib
import json
import math
from copy import deepcopy

import pytest

from physimesh.drone import stable_polar_rotor as rotor
from physimesh.drone import stable_section_solve as solve

from .test_polar_rotor import request_data as _legacy_fixture


def rotor_request():
    request = _legacy_fixture.__wrapped__()
    request.update(evaluation=rotor.EVALUATION, numerical_policy=deepcopy(rotor._POLICY))
    request["annuli"][0]["solve"]["max_evaluations"] = 32
    return request


def two_annuli():
    request = rotor_request()
    left = request["annuli"][0]
    right = deepcopy(left)
    left["radial_outer_m"] = right["radial_inner_m"] = 0.4
    request["annuli"].append(right)
    return request


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def reseal(value):
    value["evaluation_sha256"] = digest({key: item for key, item in value.items() if key != "evaluation_sha256"})


def actual_child():
    request = rotor_request()
    requests, _ = rotor._preflight(request)
    return requests[0], solve.evaluate_stable_section_solve(requests[0])


def test_actual_integration_native_hash_units_and_ownership():
    request = rotor_request()
    before = deepcopy(request)
    result = rotor.evaluate_stable_polar_rotor(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["rotor_state"] == "COMPUTED"
    assert result["section_solve_result_count"] == 1 and result["residual_result_count"] == 12
    assert result["load_result_count"] == result["lookup_result_count"] == 12
    assert result["request_sha256"] == digest(request)
    assert result["evaluation_sha256"] == digest({k: v for k, v in result.items() if k != "evaluation_sha256"})
    row = result["outputs"]["annuli"][0]
    child = row["actual_solve_result"]["outputs"]
    selected = child["evaluations"][child["solution"]["evaluation_index"]]["result"]["outputs"]
    loads = selected["actual_load_result"]["outputs"]["loads"]
    width = math.fsum((0.6, -0.2))
    assert row["contribution"] == {"thrust_n": loads["thrust_density_n_m"] * width,
                                    "torque_nm": loads["torque_density_nm_m"] * width}
    totals = result["outputs"]["integrated"]
    assert totals["total_thrust_n"] == row["contribution"]["thrust_n"]
    assert totals["shaft_power_w"] == 50.0 * totals["total_torque_nm"]
    units = result["output_units"]["annuli"][0]
    assert units["actual_solve_result"]["outputs"] == row["actual_solve_result"]["output_units"]
    assert units["actual_solve_request"] == solve.stable_section_solve_catalog()["input_units"]
    assert row["actual_solve_request"]["numerical_policy"] == rotor._POLICY
    assert row["actual_solve_request"]["residual_template"]["numerical_policy"] == rotor._POLICY
    assert request == before
    request["rotor"]["angular_speed_rad_s"] = 50.0
    assert rotor.evaluate_stable_polar_rotor(request)["request_sha256"] != result["request_sha256"]


@pytest.mark.parametrize("kind", ["budget", "ood"])
def test_all_annuli_retained_all_contributions_null(kind, monkeypatch):
    request = two_annuli()
    if kind == "budget":
        for row in request["annuli"]:
            row["solve"].update(max_evaluations=2, angle_tolerance_rad=1e-30, residual_tolerance_m2_s=1e-30)
    else:
        request["annuli"][-1]["polar"].update(sampled_mach_number=0, declared_mach_interval=[0, 0])
    original, calls = solve.evaluate_stable_section_solve, []

    def actual(request):
        calls.append(None)
        return original(request)

    monkeypatch.setattr(solve, "evaluate_stable_section_solve", actual)
    result = rotor.evaluate_stable_polar_rotor(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL", result["reasons"]
    assert len(calls) == result["section_solve_result_count"] == len(result["outputs"]["annuli"]) == 2
    assert result["outputs"]["rotor_state"] == "NOT_RUN_SECTION_NOT_CONVERGED"
    assert result["outputs"]["integrated"] is None and result["output_units"]["integrated"] == "not_applicable"
    assert all(row["contribution"] is None for row in result["outputs"]["annuli"])
    assert all(row["contribution"] == "not_applicable" for row in result["output_units"]["annuli"])


@pytest.mark.parametrize("case", ["policy_type", "policy_extra", "budget_bool", "budget_float", "budget33",
                                  "ninth_annulus", "late_polar", "gap", "native_boundary_type", "extra"])
def test_complete_static_preflight_before_any_call(case, monkeypatch):
    request = two_annuli()
    if case == "policy_type":
        request["numerical_policy"]["f_max"] = 512.0
    elif case == "policy_extra":
        request["numerical_policy"]["extra"] = 0
    elif case.startswith("budget"):
        request["annuli"][-1]["solve"]["max_evaluations"] = {"budget_bool": True, "budget_float": 32.0, "budget33": 33}[case]
    elif case == "ninth_annulus":
        request["annuli"] = request["annuli"] * 4 + [deepcopy(request["annuli"][0])]
    elif case == "late_polar":
        request["annuli"][-1]["polar"]["reynolds_tables"][-1]["rows"][-1]["cd"] = -1
    elif case == "gap":
        request["annuli"][-1]["radial_inner_m"] = 0.41
    elif case == "native_boundary_type":
        request["rotor"]["hub_radius_m"] = 1
    else:
        request["extra"] = 0
    monkeypatch.setattr(solve, "evaluate_stable_section_solve", lambda _: pytest.fail("unexpected model call"))
    result = rotor.evaluate_stable_polar_rotor(request)
    assert result["status"] == "MODEL_INAPPLICABLE" and result["section_solve_result_count"] == 0
    assert result["outputs"] == result["output_units"] == {}
    assert result["request_sha256"] is result["evaluation_sha256"] is None


@pytest.mark.parametrize("case", ["count", "policy", "units", "metadata", "status", "limits", "request_hash",
                                  "reordered", "missing", "duplicate", "extra_row", "residual_resealed",
                                  "endpoint_native", "bracket", "solution", "full_child_extra"])
def test_independent_solve_guard_resealed_tampering(case):
    request, actual = actual_child()
    rows = actual["outputs"]["evaluations"]
    if case == "count":
        actual["residual_result_count"] = True
    elif case == "policy":
        actual["numerical_policy"]["f_max"] = 512.0
    elif case == "units":
        actual["output_units"]["evaluations"][0]["psi_rad"] = "m"
    elif case == "metadata":
        actual["physical_validation"] = "ESTABLISHED"
    elif case == "status":
        actual["status"] = "EXECUTION_FAILED"
    elif case == "limits":
        actual["limits"]["output_json"]["max_depth"] += 1
    elif case == "request_hash":
        actual["request_sha256"] = "0" * 64
    elif case == "reordered":
        rows[0], rows[1] = rows[1], rows[0]
    elif case == "missing":
        rows.pop()
    elif case in ("duplicate", "extra_row"):
        rows.append(deepcopy(rows[0] if case == "duplicate" else rows[-1]))
    elif case == "residual_resealed":
        child = rows[0]["result"]
        child["outputs"]["residual_m2_s"] = math.nextafter(child["outputs"]["residual_m2_s"], math.inf)
        reseal(child)
    elif case == "endpoint_native":
        rows[0]["psi_rad"] = "0.35"
    elif case == "bracket":
        actual["outputs"]["final_bracket"]["angle_width_rad"] = 0.0
    elif case == "solution":
        actual["outputs"]["solution"]["evaluation_index"] = True
    else:
        actual["extra"] = "forged full child"
    reseal(actual)
    with pytest.raises(ValueError):
        rotor._guard_solve(actual, request)


def test_trace_engine_avoids_solve_producer_oracles(monkeypatch):
    request, actual = actual_child()

    def forbidden(*args, **kwargs):
        pytest.fail("solve producer used as admission oracle")

    for name in ("evaluate_stable_section_solve", "_bisect", "_preflight", "_actual_request",
                 "_bracket", "_solution", "_output_units", "_seal"):
        monkeypatch.setattr(solve, name, forbidden)
    rotor._guard_solve(actual, request)


@pytest.mark.parametrize("quota_kind", ["bytes", "nodes"])
def test_raw_quota_refusal_before_parent_copy_hash_guard(quota_kind, monkeypatch):
    """Synthetic LOWER quota, actual precomputed child; not configured crossing evidence."""
    _, actual = actual_child()
    quota = rotor._ChildQuota()
    measurement = quota.measure(actual)
    constant, field = (("_CHILD_BYTES_MAX", "serialized_bytes") if quota_kind == "bytes"
                       else ("_CHILD_NODES_MAX", "nodes"))
    monkeypatch.setattr(rotor, constant, measurement[field] - 1)
    monkeypatch.setattr(rotor, "deepcopy", lambda _: pytest.fail("over-quota child copied"))
    monkeypatch.setattr(rotor, "sha256_record", lambda _: pytest.fail("over-quota child hashed"))
    monkeypatch.setattr(rotor, "_guard_solve", lambda *args: pytest.fail("over-quota child guarded"))
    with pytest.raises(rotor._ResourceBudgetExceeded):
        rotor._snapshot_child(actual, quota)
    assert quota.bytes_used == quota.nodes_used == 0


def test_intrinsic_violation_is_not_quota_exception(monkeypatch):
    _, actual = actual_child()
    limits = {**rotor._CHILD_LIMITS, "max_nodes_including_keys": 1}
    monkeypatch.setattr(rotor, "_CHILD_LIMITS", limits)
    monkeypatch.setattr(rotor, "deepcopy", lambda _: pytest.fail("intrinsically invalid child copied"))
    with pytest.raises(ValueError):
        rotor._snapshot_child(actual, rotor._ChildQuota())


def test_quota_counts_whole_child_and_snapshot_metrics():
    _, actual = actual_child()
    quota = rotor._ChildQuota()
    retained, measured = rotor._snapshot_child(actual, quota)
    assert retained == actual and retained is not actual
    assert measured["serialized_bytes"] == len(json.dumps(actual, sort_keys=True, separators=(",", ":"),
                                                         ensure_ascii=False, allow_nan=False).encode("utf-8"))
    assert measured["serialized_bytes"] > len(json.dumps(actual["outputs"]).encode("utf-8"))
    assert quota.bytes_used == quota.nodes_used == 0
    quota.commit(measured)
    assert quota.bytes_used == measured["serialized_bytes"] and quota.nodes_used == measured["nodes"]


def test_atomic_resource_receipt_prior_whole_counts(monkeypatch):
    """Synthetic lowered quota after first real admission; configured probe remains mandatory."""
    request = two_annuli()
    original_guard, guarded = rotor._guard_solve, []

    def guard(actual, actual_request):
        result = original_guard(actual, actual_request)
        guarded.append(actual["residual_result_count"])
        return result

    original_commit = rotor._ChildQuota.commit

    def commit(quota, measurement):
        original_commit(quota, measurement)
        monkeypatch.setattr(rotor, "_CHILD_BYTES_MAX", quota.bytes_used)

    monkeypatch.setattr(rotor, "_guard_solve", guard)
    monkeypatch.setattr(rotor._ChildQuota, "commit", commit)
    result = rotor.evaluate_stable_polar_rotor(request)
    assert result["reasons"] == ["RESOURCE_BUDGET_EXCEEDED"] and result["status"] == "EXECUTION_FAILED"
    assert result["section_solve_result_count"] == len(guarded) == 1
    assert result["residual_result_count"] == guarded[0]
    assert result["outputs"] == result["output_units"] == {}
    assert result["request_sha256"] == digest(request) and result["evaluation_sha256"] is not None


@pytest.mark.parametrize("failure", ["exception", "malformed", "hash", "baseexception", "export"])
def test_atomic_failure_hash_and_baseexception(failure, monkeypatch):
    request = two_annuli() if failure in ("exception", "malformed", "baseexception") else rotor_request()
    if failure in ("exception", "malformed", "baseexception"):
        original, attempts = solve.evaluate_stable_section_solve, []

        def child(actual):
            attempts.append(None)
            if len(attempts) == 2:
                if failure == "baseexception":
                    raise KeyboardInterrupt("private-detail")
                if failure == "exception":
                    raise RuntimeError("private-detail")
                result = original(actual)
                result["residual_result_count"] = True
                reseal(result)
                return result
            return original(actual)
        monkeypatch.setattr(solve, "evaluate_stable_section_solve", child)
        if failure == "baseexception":
            with pytest.raises(KeyboardInterrupt):
                rotor.evaluate_stable_polar_rotor(request)
            return
    elif failure == "hash":
        original_hash = rotor.sha256_record

        def hashing(value):
            if value.get("evaluation") == rotor.EVALUATION and "section_solve_result_count" in value:
                raise RuntimeError("private-detail")
            return original_hash(value)
        monkeypatch.setattr(rotor, "sha256_record", hashing)
    else:
        original_units = rotor._output_units

        def units(*args):
            result = original_units(*args)
            result["extra"] = "x" * 2001
            return result
        monkeypatch.setattr(rotor, "_output_units", units)
    result = rotor.evaluate_stable_polar_rotor(request)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["section_solve_result_count"] == 1
    assert result["residual_result_count"] > 0
    assert result["load_result_count"] == result["lookup_result_count"] == result["residual_result_count"]
    assert result["outputs"] == result["output_units"] == {} and "private-detail" not in str(result)
    if failure == "hash":
        assert result["request_sha256"] is result["evaluation_sha256"] is None
    else:
        assert result["request_sha256"] == digest(request)
        assert result["evaluation_sha256"] == digest({k: v for k, v in result.items() if k != "evaluation_sha256"})


@pytest.mark.parametrize("case", ["nodes", "bytes", "depth", "container", "string", "integer", "utf8", "cycle"])
def test_native_refusal_before_untrusted_copy_hash_model(case, monkeypatch):
    request = rotor_request()
    if case == "nodes":
        value = [[[None] * 256] * 256] * 4
    elif case == "bytes":
        value = [["\x00" * 2000] * 256] * 3
    elif case == "depth":
        value = None
        for _ in range(18):
            value = [value]
    elif case == "cycle":
        value = []
        value.append(value)
    else:
        value = {"container": [None] * 257, "string": "x" * 2001,
                 "integer": 1 << 1023, "utf8": "\ud800"}[case]
    request["untrusted"] = value
    original_copy = rotor.deepcopy

    def copying(value, *args, **kwargs):
        if value is request:
            pytest.fail("untrusted root copied before native rejection")
        return original_copy(value, *args, **kwargs)  # Trusted refusal metadata copies permitted.

    monkeypatch.setattr(rotor, "deepcopy", copying)
    monkeypatch.setattr(rotor, "sha256_record", lambda _: pytest.fail("unexpected root hash"))
    monkeypatch.setattr(solve, "evaluate_stable_section_solve", lambda _: pytest.fail("unexpected model"))
    result = rotor.evaluate_stable_polar_rotor(request)
    assert result["status"] == "MODEL_INAPPLICABLE" and result["section_solve_result_count"] == 0
    assert result["outputs"] == result["output_units"] == {}
    assert result["request_sha256"] is result["evaluation_sha256"] is None
