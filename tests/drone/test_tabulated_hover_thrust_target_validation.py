"""Actual V108 captures followed by solver-forbidden pure validation."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from physimesh.drone import hover_bemt, reference_air_properties, reference_air_tabulated_hover
from physimesh.drone import tabulated_hover_bemt as core
from physimesh.drone import tabulated_hover_bemt_request as child
from physimesh.drone import tabulated_hover_thrust_target as inverse
from physimesh.drone import tabulated_hover_thrust_target_validation as guard
from tests.drone.test_tabulated_hover_thrust_target import request


def forbid_models(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("Validator invoked a model or copy hook"))
    for module, names in (
        (inverse, ("evaluate_tabulated_hover_thrust_target", "evaluate_tabulated_hover_bemt", "deepcopy",
                   "tabulated_hover_thrust_target_catalog", "_response", "_seal")),
        (child, ("evaluate_tabulated_hover_bemt", "solve_tabulated_hover")),
        (core, ("solve_tabulated_hover",)),
        (hover_bemt, ("solve_hover",)),
        (reference_air_tabulated_hover, ("reference_air_properties", "evaluate_reference_air_tabulated_hover",
                                        "evaluate_tabulated_hover_bemt")),
        (reference_air_properties, ("reference_air_properties",)),
    ):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    return forbidden


@pytest.mark.parametrize("case,status", [
    ("interior", "COMPUTED_EXPERIMENTAL"), ("low", "COMPUTED_EXPERIMENTAL"),
    ("high", "COMPUTED_EXPERIMENTAL"), ("zero", "TARGET_NOT_BRACKETED"),
    ("unbracketed", "TARGET_NOT_BRACKETED"), ("budget", "ITERATION_LIMIT"),
    ("refusal", "MODEL_INAPPLICABLE"),
])
def test_actual_smoke_without_models(monkeypatch, case, status):
    supplied = request({"low": 50.0, "high": 150.0, "unbracketed": 175.0}.get(case, 87.5))
    if case == "zero":
        for station in supplied["rotor_template"]["stations"]:
            station["blade_angle_rad"] = 0.0
    elif case == "budget":
        supplied["max_evaluations"] = 3
    elif case == "refusal":
        supplied["rotor_template"]["density_kg_m3"] = -1.0
    actual = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert actual["status"] == status
    before = deepcopy((actual, supplied))
    forbidden = forbid_models(monkeypatch)
    assert guard.validate_tabulated_hover_thrust_target_result(actual, supplied) is None
    assert (actual, supplied) == before
    forbidden.assert_not_called()


def rehash(actual):
    actual["evaluation_sha256"] = guard.sha256_record({
        key: value for key, value in actual.items() if key != "evaluation_sha256"
    })


@pytest.fixture
def captured(monkeypatch):
    supplied = request(87.5)
    actual = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL"
    assert len(actual["trace"]) == 5
    forbidden = forbid_models(monkeypatch)
    yield actual, supplied
    forbidden.assert_not_called()


@pytest.mark.parametrize("forge", [
    lambda a: a.update(extra="forbidden"),
    lambda a: a.pop("schema_version"),
    lambda a: a.update(evaluation="another"),
    lambda a: a.update(schema_version="another"),
    lambda a: a.update(status="RESEARCH_ONLY"),
    lambda a: a.update(evidence_level="validated"),
    lambda a: a.update(physical_validation="ESTABLISHED"),
    lambda a: a.update(numerical_qualification="ESTABLISHED"),
    lambda a: a.update(runtime_identity="ESTABLISHED"),
    lambda a: a.update(aircraft_status="feasible"),
    lambda a: a.update(feasibility=False),
    lambda a: a.update(diagnostics_complete=1),
    lambda a: a.update(reasons=["invented"]),
    lambda a: a["limitations"].pop(),
    lambda a: a["limits"]["input_json"].update(root_depth=True),
    lambda a: a["limits"]["output_json"].update(max_depth=17),
    lambda a: a["limits"]["core_work"].update(annuli_max=513),
    lambda a: a.update(request_sha256="a" * 64),
    lambda a: a.update(request_sha256=None),
    lambda a: a.update(evaluation_count=True),
    lambda a: a.update(evaluation_count=5.0),
    lambda a: a.update(evaluation_count=1),
    lambda a: a["outputs"].update(extra=0),
    lambda a: a["outputs"].pop("actual_forward_result"),
    lambda a: a["outputs"].update(evaluations=5.0),
    lambda a: a["outputs"].update(target_thrust_n=a["outputs"]["target_thrust_n"] * 1.01),
    lambda a: a["outputs"].update(absolute_thrust_tolerance_n=1e-9),
    lambda a: a["outputs"].update(achieved_thrust_n=a["outputs"]["achieved_thrust_n"] * 1.01),
    lambda a: a["outputs"].update(thrust_residual_n=0),
    lambda a: a["outputs"].update(angular_speed_rad_s=True),
    lambda a: a["output_units"].update(thrust_residual_n="kg"),
    lambda a: a["output_units"]["actual_forward_request"].update(density_kg_m3="N"),
    lambda a: a["output_units"]["actual_forward_result"].update(evaluation="label"),
    lambda a: a["outputs"]["actual_forward_request"].update(density_kg_m3=2.0),
    lambda a: a["trace"][0].update(extra=0),
    lambda a: a["trace"][0].pop("thrust_n"),
    lambda a: a["trace"][0].update(thrust_n=0),
    lambda a: a["trace"][0].update(thrust_n=True),
    lambda a: a["trace"][0].update(thrust_residual_n=0),
    lambda a: a["trace"][0].update(thrust_residual_n=a["trace"][0]["thrust_residual_n"] + 1.0),
    lambda a: a["trace"][0].update(request_sha256="b" * 64),
    lambda a: a["trace"].reverse(),
])
def test_coherently_rehashed_root_output_and_trace_forgeries(captured, forge):
    actual, supplied = captured
    forge(actual)
    rehash(actual)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_intermediate_digest_is_reported_provenance_only(captured, index):
    actual, supplied = captured
    actual["trace"][index]["full_actual_result_sha256"] = "0123456789abcdef" * 4
    rehash(actual)
    # V108 did not retain these payloads. A well-formed replacement is accepted;
    # this explicitly does not assert independent intermediate content binding.
    assert guard.validate_tabulated_hover_thrust_target_result(actual, supplied) is None


@pytest.mark.parametrize("value", [None, True, 0, "", "a" * 63, "a" * 65, "A" * 64, "g" * 64, "é" * 64])
@pytest.mark.parametrize("field", ["request_sha256", "full_actual_result_sha256"])
def test_bad_intermediate_digest_format_rejected(captured, value, field):
    actual, supplied = captured
    actual["trace"][0][field] = value
    rehash(actual)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


def test_selected_well_formed_wrong_full_digest_rejected(captured):
    actual, supplied = captured
    actual["trace"][-1]["full_actual_result_sha256"] = "0123456789abcdef" * 4
    rehash(actual)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


def test_entire_outer_envelope_hash_excludes_only_itself(captured):
    actual, supplied = captured
    actual["evaluation_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)
    rehash(actual)
    actual["trace"][0]["full_actual_result_sha256"] = "1" * 64
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


def rebind_selected_result(actual):
    selected = actual["outputs"]["actual_forward_result"]
    rehash(selected)
    actual["trace"][-1]["full_actual_result_sha256"] = guard.sha256_record(selected)
    rehash(actual)


@pytest.mark.parametrize("forge", [
    lambda a: a.update(extra=0),
    lambda a: a.update(model_id="invented"),
    lambda a: a.update(core_version=0.1),
    lambda a: a.update(diagnostics_complete=1),
    lambda a: a.update(runtime_identity="ESTABLISHED"),
    lambda a: a["limitations"].clear(),
    lambda a: a["limits"]["output_json"].update(root_depth=True),
    lambda a: a["output_units"].update(thrust_n="kg"),
    lambda a: a["outputs"].update(annuli=24.0),
    lambda a: a["outputs"]["chord_m"].__setitem__(0, 0.5),
    lambda a: a["outputs"]["inflow_ratio"].__setitem__(0, 0.5),
    lambda a: a["outputs"].update(thrust_coefficient=a["outputs"]["thrust_coefficient"] * 1.01),
    lambda a: a.update(request_sha256="1" * 64),
])
def test_rehashed_selected_full_forward_forgeries(captured, forge):
    actual, supplied = captured
    forge(actual["outputs"]["actual_forward_result"])
    rebind_selected_result(actual)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


def set_trial(actual, supplied, index, omega):
    entry = actual["trace"][index]
    template = supplied["rotor_template"]
    radius, density = float(template["radius_m"]), float(template["density_kg_m3"])
    area = guard._mul(guard.math.pi, guard._mul(radius, radius))
    tip = guard._mul(float(omega), radius)
    scale = guard._mul(guard._mul(density, area), guard._mul(tip, tip))
    thrust = guard._mul(scale, actual["outputs"]["actual_forward_result"]["outputs"]["thrust_coefficient"])
    entry.update(angular_speed_rad_s=omega, thrust_n=thrust,
                 thrust_residual_n=thrust - supplied["target_thrust_n"],
                 request_sha256=guard.sha256_record({**template, "angular_speed_rad_s": omega}))


@pytest.mark.parametrize("index,omega", [(0, 50), (1, 150), (2, 100), (2, 99.0), (3, 125.0), (3, 50.0)])
def test_replay_exact_endpoint_and_midpoint_types_and_values(captured, index, omega):
    actual, supplied = captured
    set_trial(actual, supplied, index, omega)
    rehash(actual)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


def test_trace_cannot_continue_after_first_tolerable_midpoint(captured):
    actual, supplied = captured
    tolerance = abs(actual["trace"][2]["thrust_residual_n"])
    assert 0 < tolerance < supplied["target_thrust_n"]
    supplied["absolute_thrust_tolerance_n"] = tolerance
    actual["outputs"]["absolute_thrust_tolerance_n"] = tolerance
    actual["request_sha256"] = guard.sha256_record(supplied)
    rehash(actual)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


def test_trace_cannot_continue_after_success(captured):
    actual, supplied = captured
    actual["trace"].append(deepcopy(actual["trace"][-1]))
    actual["evaluation_count"] += 1
    actual["outputs"]["evaluations"] += 1
    rehash(actual)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


def test_trace_cannot_stop_without_tolerance(captured):
    actual, supplied = captured
    actual["trace"].pop()
    actual["evaluation_count"] -= 1
    actual["outputs"]["evaluations"] -= 1
    rehash(actual)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


def seal_failure(actual):
    if actual["status"] != "MODEL_INAPPLICABLE":
        rehash(actual)


@pytest.fixture
def failure_captures(monkeypatch):
    captures = {}
    for status, supplied in (
        ("TARGET_NOT_BRACKETED", request(175.0)),
        ("ITERATION_LIMIT", request(87.5, max_evaluations=3)),
        ("MODEL_INAPPLICABLE", request(87.5)),
    ):
        if status == "MODEL_INAPPLICABLE":
            supplied["rotor_template"]["density_kg_m3"] = -1.0
        actual = inverse.evaluate_tabulated_hover_thrust_target(supplied)
        assert actual["status"] == status
        captures[status] = (actual, supplied)
    lo = 50.0
    hi = guard.math.nextafter(lo, guard.math.inf)
    supplied = request(angular_speed_bracket_rad_s=[lo, hi],
                       absolute_thrust_tolerance_n=guard.sys.float_info.min)
    thrusts = [child.evaluate_tabulated_hover_bemt({
        **supplied["rotor_template"], "angular_speed_rad_s": omega,
    })["outputs"]["thrust_n"] for omega in (lo, hi)]
    supplied["target_thrust_n"] = thrusts[0] + (thrusts[1] - thrusts[0]) / 2
    assert thrusts[0] < supplied["target_thrust_n"] < thrusts[1]
    actual = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert actual["status"] == "NUMERICAL_LIMIT"
    captures["NUMERICAL_LIMIT"] = (actual, supplied)
    supplied = request(87.5)
    with monkeypatch.context() as execution:
        execution.setattr(inverse, "evaluate_tabulated_hover_bemt", Mock(side_effect=RuntimeError("private")))
        actual = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert actual["status"] == "EXECUTION_FAILED" and actual["evaluation_count"] == 1
    captures["EXECUTION_FAILED"] = (actual, supplied)
    forbidden = forbid_models(monkeypatch)
    yield captures
    forbidden.assert_not_called()


@pytest.mark.parametrize("status", list(guard._FAILURES))
def test_actual_atomic_failure_captures_validate_without_models(failure_captures, status):
    actual, supplied = failure_captures[status]
    before = deepcopy((actual, supplied))
    assert guard.validate_tabulated_hover_thrust_target_result(actual, supplied) is None
    assert (actual, supplied) == before


@pytest.mark.parametrize("status,count", [
    ("ITERATION_LIMIT", 2), ("ITERATION_LIMIT", 4),
    ("TARGET_NOT_BRACKETED", 1), ("TARGET_NOT_BRACKETED", 3),
    ("NUMERICAL_LIMIT", 0), ("NUMERICAL_LIMIT", 1), ("NUMERICAL_LIMIT", 32),
    ("MODEL_INAPPLICABLE", 0), ("MODEL_INAPPLICABLE", 33),
    ("EXECUTION_FAILED", -1), ("EXECUTION_FAILED", 33),
    *[(status, True) for status in guard._FAILURES],
    *[(status, 2.0) for status in guard._FAILURES],
])
def test_coherently_rehashed_failure_count_forgeries(failure_captures, status, count):
    actual, supplied = failure_captures[status]
    actual["evaluation_count"] = count
    seal_failure(actual)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


@pytest.mark.parametrize("status", list(guard._FAILURES))
@pytest.mark.parametrize("forge", [
    lambda a: a.update(outputs={"angular_speed_rad_s": 100.0}),
    lambda a: a.update(output_units={"angular_speed_rad_s": "rad/s"}),
    lambda a: a.update(trace=[{}]),
    lambda a: a.update(diagnostics_complete=True),
    lambda a: a.update(diagnostics_complete=0),
    lambda a: a.update(reasons=[]),
    lambda a: a.update(reasons=["invented reason"]),
    lambda a: a.update(status="SOLVER_UNSUPPORTED"),
    lambda a: a.update(request_sha256=None),
    lambda a: a.update(request_sha256="1" * 64),
])
def test_coherently_rehashed_atomic_failure_forgeries(failure_captures, status, forge):
    actual, supplied = failure_captures[status]
    forge(actual)
    seal_failure(actual)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


@pytest.mark.parametrize("status,count", [
    ("EXECUTION_FAILED", 0), ("EXECUTION_FAILED", 32),
    ("MODEL_INAPPLICABLE", 32), ("NUMERICAL_LIMIT", 31),
])
def test_history_free_failure_within_bounds_is_not_execution_attestation(failure_captures, status, count):
    actual, supplied = failure_captures[status]
    assert actual["evaluation_count"] != count
    # No retained history can substantiate this change. Acceptance demonstrates
    # envelope consistency only, never proof of calls or reason causation.
    actual["evaluation_count"] = count
    seal_failure(actual)
    assert guard.validate_tabulated_hover_thrust_target_result(actual, supplied) is None


@pytest.mark.parametrize("status", list(guard._FAILURES))
def test_failure_evaluation_hash_nullable_only_for_domain_refusal(failure_captures, status):
    actual, supplied = failure_captures[status]
    actual["evaluation_sha256"] = "0" * 64 if status == "MODEL_INAPPLICABLE" else None
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


@pytest.mark.parametrize("change", [
    lambda r: r.update(evaluation=False),
    lambda r: r.update(extra=0),
    lambda r: r.pop("max_evaluations"),
    lambda r: r.update(rotor_template=[]),
    lambda r: r["rotor_template"].update(angular_speed_rad_s=100.0),
    lambda r: r["rotor_template"].update(evaluation="another"),
    lambda r: r["rotor_template"].update(annuli=True),
    lambda r: r["rotor_template"].update(blade_count=2.0),
    lambda r: r["rotor_template"].update(geometry_source=" "),
    lambda r: r["rotor_template"].update(geometry_kind="unknown"),
    lambda r: r["rotor_template"]["stations"][0].update(chord_m=True),
    lambda r: r.update(target_thrust_n=True),
    lambda r: r.update(target_thrust_n=guard.math.inf),
    lambda r: r.update(target_thrust_n=guard.math.nan),
    lambda r: r.update(target_thrust_n=guard.math.nextafter(0.0, 1.0)),
    lambda r: r.update(absolute_thrust_tolerance_n=r["target_thrust_n"]),
    lambda r: r.update(angular_speed_bracket_rad_s=[100.0, 50.0]),
    lambda r: r.update(angular_speed_bracket_rad_s=(50.0, 150.0)),
    lambda r: r.update(max_evaluations=65),
    lambda r: r.update(max_evaluations=2.0),
    lambda r: r["rotor_template"].update(geometry_source="\ud800"),
    lambda r: r["rotor_template"].update(geometry_source="a" * 2001),
    lambda r: r["rotor_template"].update(radius_m=1 << 1023),
])
def test_actual_invalid_preflight_capture_no_hash_count_zero(monkeypatch, change):
    supplied = request()
    change(supplied)
    actual = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert actual["status"] == "MODEL_INAPPLICABLE" and actual["evaluation_count"] == 0
    assert actual["request_sha256"] is actual["evaluation_sha256"] is None
    forbid_models(monkeypatch)
    hashing = Mock(side_effect=AssertionError("Invalid request must not be hashed"))
    monkeypatch.setattr(guard, "sha256_record", hashing)
    assert guard.validate_tabulated_hover_thrust_target_result(actual, supplied) is None
    hashing.assert_not_called()
    actual["status"] = "EXECUTION_FAILED"
    actual["reasons"] = ["Request snapshot failed."]
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


@pytest.mark.parametrize("malformed_preflight", [False, True])
def test_actual_unsupported_dispatch_before_preflight(monkeypatch, malformed_preflight):
    supplied = request()
    supplied["evaluation"] = "other_outer_evaluation"
    if malformed_preflight:
        supplied["rotor_template"] = None
        supplied["max_evaluations"] = True
    actual = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert actual["status"] == "SOLVER_UNSUPPORTED" and actual["evaluation_count"] == 0
    assert actual["request_sha256"] is actual["evaluation_sha256"] is None
    forbid_models(monkeypatch)
    monkeypatch.setattr(guard, "sha256_record", Mock(side_effect=AssertionError("No hashing")))
    assert guard.validate_tabulated_hover_thrust_target_result(actual, supplied) is None
    actual["status"] = "MODEL_INAPPLICABLE"
    actual["reasons"] = ["Invalid bounded target request."]
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


@pytest.mark.parametrize("forge", [
    lambda a: a.update(evaluation_count=1),
    lambda a: a.update(evaluation_count=False),
    lambda a: a.update(request_sha256="0" * 64),
    lambda a: a.update(evaluation_sha256="0" * 64),
    lambda a: a.update(trace=[{}]),
    lambda a: a.update(outputs={"partial": 1}),
])
@pytest.mark.parametrize("unsupported", [False, True])
def test_nonadmitted_hash_count_and_atomic_forgeries(monkeypatch, forge, unsupported):
    supplied = request()
    supplied["evaluation"] = "another" if unsupported else False
    actual = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    forbid_models(monkeypatch)
    forge(actual)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


def foreign_value(kind, value):
    def hook(*args, **kwargs):
        pytest.fail("Foreign method or deepcopy hook was invoked")

    foreign = type("Foreign", (kind,), {
        "__deepcopy__": hook, "__float__": hook, "__int__": hook,
        "__eq__": hook, "__iter__": hook, "items": hook, "keys": hook,
        "encode": hook,
    })
    return foreign(value)


@pytest.mark.parametrize("kind,value", [(float, 1.0), (int, 1), (dict, {}), (list, []), (str, "x")])
def test_foreign_request_and_response_rejected_without_hooks(captured, kind, value):
    actual, supplied = captured
    alien = foreign_value(kind, value)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(alien, supplied)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, alien)
    actual["outputs"]["angular_speed_rad_s"] = alien
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)
    supplied["target_thrust_n"] = alien
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


def nested(depth):
    value = 0
    for _ in range(depth):
        value = [value]
    return value


def oversized_nodes():
    shared = {str(index): 0 for index in range(32)}
    # Each aliased occurrence counts, exceeding 65536 nodes within depth/items.
    return [shared] * 1024


@pytest.mark.parametrize("bad", [
    lambda: [guard.math.nan], lambda: [guard.math.inf], lambda: ["\ud800"],
    lambda: ["x" * 2001], lambda: [1 << 1023],
    lambda: nested(16), lambda: [0] * 2049, oversized_nodes,
])
def test_actual_output_walk_rejects_before_forward_guard(captured, monkeypatch, bad):
    actual, supplied = captured
    actual["extra"] = bad()
    forward_guard = Mock(side_effect=AssertionError("Output walk must finish before child guard"))
    monkeypatch.setattr(guard, "_validate_child", forward_guard)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)
    forward_guard.assert_not_called()


def test_cycles_fail_without_hooks_or_models(captured):
    actual, supplied = captured
    cycle = []
    cycle.append(cycle)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(cycle, supplied)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, cycle)
    actual["trace"] = cycle
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


@pytest.mark.parametrize("bad", [
    lambda: nested(11), lambda: [0] * 257,
    lambda: [{str(index): 0 for index in range(64)}] * 128,
])
def test_original_request_walk_rejects_depth_items_nodes(captured, monkeypatch, bad):
    actual, supplied = captured
    supplied["rotor_template"]["extra"] = bad()
    hashing = Mock(side_effect=AssertionError("Admission must precede hashing"))
    monkeypatch.setattr(guard, "sha256_record", hashing)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)
    hashing.assert_not_called()


def test_1023_bit_control_conversion_is_finite_and_admitted(monkeypatch):
    supplied = request()
    supplied["target_thrust_n"] = (1 << 1023) - 1
    actual = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert actual["status"] == "TARGET_NOT_BRACKETED"
    assert actual["request_sha256"] == guard.sha256_record(supplied)
    forbid_models(monkeypatch)
    assert guard.validate_tabulated_hover_thrust_target_result(actual, supplied) is None


def test_maximum_work_selected_low_endpoint_and_digest_boundary(monkeypatch):
    supplied = request(100.0, max_evaluations=64, angular_speed_bracket_rad_s=[100, 150])
    template = supplied["rotor_template"]
    template.update(annuli=512, blade_count=32, stations=[
        {"radius_m": index / 255, "chord_m": 0.05, "blade_angle_rad": 0.08}
        for index in range(256)
    ])
    forward = child.evaluate_tabulated_hover_bemt({**template, "angular_speed_rad_s": 100})
    assert forward["status"] == "COMPUTED_EXPERIMENTAL"
    supplied["target_thrust_n"] = forward["outputs"]["thrust_n"]
    actual = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert actual["status"] == "COMPUTED_EXPERIMENTAL" and actual["evaluation_count"] == 2
    assert actual["outputs"]["angular_speed_rad_s"] == 100
    assert len(actual["outputs"]["actual_forward_result"]["outputs"]["radii_m"]) == 512
    forbid_models(monkeypatch)
    assert guard.validate_tabulated_hover_thrust_target_result(actual, supplied) is None
    actual["trace"][1]["full_actual_result_sha256"] = "abcdef0123456789" * 4
    rehash(actual)
    assert guard.validate_tabulated_hover_thrust_target_result(actual, supplied) is None
    actual["trace"][0]["full_actual_result_sha256"] = "abcdef0123456789" * 4
    rehash(actual)
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)


def test_metadata_freshness_and_private_snapshot_unchanged(captured):
    actual, supplied = captured
    baseline = deepcopy(guard._CATALOG)
    metadata = guard.tabulated_hover_thrust_target_validation_catalog()
    assert "producer-reported" in metadata["intermediate_result_digests"]
    assert "cannot be content-verified" in metadata["intermediate_result_digests"]
    assert "Content-verified" in metadata["selected_result_digest"]
    assert "no execution attestation" in metadata["failure_boundary"]
    expected = deepcopy(metadata)
    metadata["limitations"].clear()
    metadata["boundary"] = "changed"
    assert guard.tabulated_hover_thrust_target_validation_catalog() == expected
    assert guard.validate_tabulated_hover_thrust_target_result(actual, supplied) is None
    assert guard._CATALOG == baseline


def test_alias_occurrences_and_hashes_preserved_on_success_and_rejection(captured):
    actual, supplied = captured
    # Shared builtin strings and actual output metadata remain aliased. The
    # validator neither detaches them nor modifies caller data or stored hashes.
    units = actual["outputs"]["actual_forward_result"]["output_units"]
    actual["output_units"]["actual_forward_result"] = units
    source = supplied["rotor_template"]["geometry_source"]
    actual["outputs"]["actual_forward_request"]["geometry_source"] = source
    original = deepcopy((actual, supplied))
    assert guard.validate_tabulated_hover_thrust_target_result(actual, supplied) is None
    assert actual["output_units"]["actual_forward_result"] is units
    assert actual["outputs"]["actual_forward_request"]["geometry_source"] is source
    assert (actual, supplied) == original
    actual["trace"][0]["thrust_residual_n"] += 1.0
    rehash(actual)
    bad = deepcopy((actual, supplied))
    with pytest.raises(ValueError):
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)
    assert (actual, supplied) == bad
    assert actual["output_units"]["actual_forward_result"] is units


def test_alias_lists_preserved_on_atomic_refusal(monkeypatch):
    supplied = request()
    stations = supplied["rotor_template"]["stations"]
    stations[:] = [stations[0]] * 3
    actual = inverse.evaluate_tabulated_hover_thrust_target(supplied)
    assert actual["status"] == "MODEL_INAPPLICABLE" and actual["evaluation_count"] == 1
    # Sharing empty containers does not change their exact failure shapes.
    shared = []
    supplied["angular_speed_bracket_rad_s"] = list(supplied["angular_speed_bracket_rad_s"])
    actual["trace"] = shared
    forbid_models(monkeypatch)
    before = deepcopy((actual, supplied))
    assert guard.validate_tabulated_hover_thrust_target_result(actual, supplied) is None
    assert supplied["rotor_template"]["stations"] is stations
    assert stations[0] is stations[1] is stations[2]
    assert actual["trace"] is shared
    assert (actual, supplied) == before


@pytest.mark.parametrize("exception", [RuntimeError, KeyboardInterrupt, SystemExit])
def test_unexpected_pure_dependency_exception_propagates(captured, monkeypatch, exception):
    actual, supplied = captured
    failure = exception("pure dependency failure")
    monkeypatch.setattr(inverse, "_preflight", Mock(side_effect=failure))
    with pytest.raises(exception) as raised:
        guard.validate_tabulated_hover_thrust_target_result(actual, supplied)
    assert raised.value is failure
