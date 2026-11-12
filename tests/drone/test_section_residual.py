"""Synthetic local residual contract checks; no physical qualification."""

import hashlib
import json
import math
from copy import deepcopy

import pytest

from physimesh.drone import section_load as load
from physimesh.drone import section_residual as residual


@pytest.fixture
def request_data():
    return {
        "evaluation": residual.EVALUATION,
        "polar": {
            "airfoil_id": "invented-synthetic", "source": "invented fixture; no dataset",
            "source_kind": "synthetic", "uncertainty_status": "unknown",
            "sampled_mach_number": 0.1, "declared_mach_interval": [0, 0.9],
            "reynolds_tables": [
                {"reynolds_number": re, "rows": [
                    {"alpha_rad": alpha, "cl": 2 * alpha + 0.1, "cd": 0.1}
                    for alpha in (-1.5, 0.0, 1.5)]}
                for re in (1000.0, 10000000.0)],
        },
        "section": {
            "imposed_axial_velocity_m_s": 5, "imposed_tangential_velocity_m_s": 20,
            "psi_rad": 0.6, "tip_radius_m": 0.8, "radius_m": 0.4,
            "pitch_rad": 0.5, "chord_m": 0.1, "density_kg_m3": 1.2,
            "dynamic_viscosity_pa_s": 1.8e-5, "speed_of_sound_m_s": 343, "blade_count": 2,
        },
    }


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reseal(value):
    value["evaluation_sha256"] = _digest({key: item for key, item in value.items()
                                         if key != "evaluation_sha256"})


def test_success_actual_once(request_data, monkeypatch):
    original, calls = load.evaluate_section_load, []

    def child(request):
        calls.append(deepcopy(request))
        return original(request)

    monkeypatch.setattr(load, "evaluate_section_load", child)
    result = residual.evaluate_section_residual(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["load_result_count"] == result["lookup_result_count"] == len(calls) == 1
    output = result["outputs"]
    assert output["actual_load_request"] == calls[0]
    assert output["actual_load_result"] == original(calls[0])
    assert output["residual_state"] == "COMPUTED"


def test_independent_math_closure(request_data):
    result = residual.evaluate_section_residual(request_data)
    output = result["outputs"]
    u = math.hypot(5, 20)
    wa, wt = 2.5 + 0.5 * u * math.sin(0.6), 10 + 0.5 * u * math.cos(0.6)
    wake = (0.4 / 0.8) * wa / wt
    f = (2 / 2) * (1 - 0.4 / 0.8) / wake
    factor = (2 / math.pi) * math.acos(math.exp(-f))
    gamma = (20 - wt) * (4 * math.pi * 0.4 / 2) * factor
    gamma *= math.sqrt(1 + (4 * wake * 0.8 / (math.pi * 2 * 0.4)) ** 2)
    cl = output["actual_load_result"]["outputs"]["actual_lookup_result"]["outputs"]["cl"]
    lift = 0.5 * math.hypot(wa, wt) * 0.1 * cl
    assert output["closure"]["gamma_induced_m2_s"] == pytest.approx(gamma, rel=3e-15)
    assert output["residual_m2_s"] == pytest.approx(gamma - lift, rel=3e-15)


def test_ood_mach_retains_full_child(request_data):
    request_data["polar"].update(sampled_mach_number=0, declared_mach_interval=[0, 0])
    result = residual.evaluate_section_residual(request_data)
    output = result["outputs"]
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["load_result_count"] == result["lookup_result_count"] == 1
    assert output["residual_state"] == "NOT_RUN_OUT_OF_POLAR_DOMAIN"
    assert output["closure"] is output["residual_m2_s"] is None
    assert output["actual_load_result"] == load.evaluate_section_load(output["actual_load_request"])


@pytest.mark.parametrize("psi", [0, math.atan2(5, 20), math.pi / 2])
def test_invalid_psi_before_child(request_data, monkeypatch, psi):
    request_data["section"]["psi_rad"] = psi
    monkeypatch.setattr(load, "evaluate_section_load", lambda _: pytest.fail("unexpected child"))
    result = residual.evaluate_section_residual(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["load_result_count"] == result["lookup_result_count"] == 0
    assert result["request_sha256"] is result["evaluation_sha256"] is None


def test_rehashed_load_tampering_rejected(request_data, monkeypatch):
    original = load.evaluate_section_load

    def child(request):
        result = original(request)
        result["outputs"]["loads"]["dynamic_pressure_pa"] += 1
        _reseal(result)
        return result

    monkeypatch.setattr(load, "evaluate_section_load", child)
    result = residual.evaluate_section_residual(request_data)
    assert result["reasons"] == ["LOAD_BOUNDARY_FAILED"]
    assert result["load_result_count"] == result["lookup_result_count"] == 0
    assert result["outputs"] == result["output_units"] == {}


@pytest.mark.parametrize("key,value", [
    ("imposed_axial_velocity_m_s", -1), ("imposed_tangential_velocity_m_s", 0),
    ("tip_radius_m", 0.4), ("tip_radius_m", 0.3), ("psi_rad", math.pi / 2),
    ("blade_count", True), ("blade_count", 2.0), ("blade_count", 65),
    ("chord_m", math.nextafter(0.0, 1.0)), ("pitch_rad", -1),
])
def test_invalid_section_no_child(request_data, monkeypatch, key, value):
    request_data["section"][key] = value
    monkeypatch.setattr(load, "evaluate_section_load", lambda _: pytest.fail("unexpected child"))
    result = residual.evaluate_section_residual(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["load_result_count"] == result["lookup_result_count"] == 0
    assert result["request_sha256"] is result["evaluation_sha256"] is None


@pytest.mark.parametrize("case", ["extra", "missing", "cycle", "subclass", "late_cd"])
def test_schema_and_bounded_hooks(request_data, monkeypatch, case):
    class ForeignList(list):
        def __deepcopy__(self, memo):
            pytest.fail("foreign copy hook")

    if case == "extra":
        request_data["unexpected"] = 0
    elif case == "missing":
        del request_data["section"]["chord_m"]
    elif case == "cycle":
        request_data["cycle"] = request_data
    elif case == "subclass":
        request_data["polar"]["reynolds_tables"] = ForeignList()
    else:
        request_data["polar"]["reynolds_tables"][-1]["rows"][-1]["cd"] = -1
    monkeypatch.setattr(load, "evaluate_section_load", lambda _: pytest.fail("unexpected child"))
    assert residual.evaluate_section_residual(request_data)["status"] == "MODEL_INAPPLICABLE"


@pytest.mark.parametrize("axis", ["alpha_rad", "reynolds_number", "mach_number", "all"])
def test_ood_axes_and_null_closure(request_data, axis):
    polar = request_data["polar"]
    if axis in ("alpha_rad", "all"):
        for table in polar["reynolds_tables"]:
            for row in table["rows"]:
                row["alpha_rad"] /= 100
    if axis in ("reynolds_number", "all"):
        for table, re in zip(polar["reynolds_tables"], (1, 2), strict=True):
            table["reynolds_number"] = re
    if axis in ("mach_number", "all"):
        polar.update(sampled_mach_number=0, declared_mach_interval=[0, 0])
    result = residual.evaluate_section_residual(request_data)
    output = result["outputs"]
    lookup = output["actual_load_result"]["outputs"]["actual_lookup_result"]
    assert lookup["out_of_domain_axes"] == (
        ["alpha_rad", "reynolds_number", "mach_number"] if axis == "all" else [axis])
    assert output["actual_load_result"] == load.evaluate_section_load(output["actual_load_request"])
    assert output["closure"] is output["residual_m2_s"] is None
    assert result["load_result_count"] == result["lookup_result_count"] == 1


@pytest.mark.parametrize("path,value", [
    (("physical_validation",), "ESTABLISHED"), (("source_urls", 0), "https://invalid.example"),
    (("output_units", "loads", "dynamic_pressure_pa"), "N"),
    (("outputs", "kinematics", "phi_rad"), 0.0),
    (("outputs", "load_state"), "NOT_RUN_OUT_OF_POLAR_DOMAIN"),
    (("lookup_result_count",), True), (("request_sha256",), "0" * 64),
    (("outputs", "actual_lookup_result", "request_sha256"), "0" * 64),
    (("outputs", "actual_lookup_request", "query", "alpha_rad"), -0.0),
])
def test_rehashed_full_child_tampering(request_data, monkeypatch, path, value):
    original = load.evaluate_section_load

    def child(request):
        result = original(request)
        target = result
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        _reseal(result)
        return result

    monkeypatch.setattr(load, "evaluate_section_load", child)
    result = residual.evaluate_section_residual(request_data)
    assert result["reasons"] == ["LOAD_BOUNDARY_FAILED"]
    assert result["load_result_count"] == result["lookup_result_count"] == 0
    assert result["outputs"] == result["output_units"] == {}


def test_native_hashes(request_data):
    request_data["polar"]["source"] = "invented α"
    result = residual.evaluate_section_residual(request_data)
    assert result["request_sha256"] == _digest(request_data)
    assert result["evaluation_sha256"] == _digest({key: value for key, value in result.items()
                                                  if key != "evaluation_sha256"})
    request_data["section"]["imposed_axial_velocity_m_s"] = 5.0
    assert residual.evaluate_section_residual(request_data)["request_sha256"] != result["request_sha256"]


def test_persistent_parent_hash_failure_clears_payload(request_data, monkeypatch):
    original = residual.sha256_record

    def hashing(value):
        if "load_result_count" in value:
            raise ValueError("private hash failure")
        return original(value)

    monkeypatch.setattr(residual, "sha256_record", hashing)
    result = residual.evaluate_section_residual(request_data)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["load_result_count"] == result["lookup_result_count"] == 1
    assert result["request_sha256"] is result["evaluation_sha256"] is None
    assert result["outputs"] == result["output_units"] == {}


def test_baseexception_propagates(request_data, monkeypatch):
    def child(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(load, "evaluate_section_load", child)
    with pytest.raises(KeyboardInterrupt):
        residual.evaluate_section_residual(request_data)


def test_rounded_zero_induction_refused_before_child(request_data, monkeypatch):
    request_data["section"].update(imposed_axial_velocity_m_s=0, psi_rad=1e-9)
    monkeypatch.setattr(load, "evaluate_section_load", lambda _: pytest.fail("unexpected child"))
    result = residual.evaluate_section_residual(request_data)
    assert result["reasons"] == ["SECTION_RESIDUAL_EXECUTION_FAILED"]
    assert result["load_result_count"] == result["lookup_result_count"] == 0


@pytest.mark.parametrize("case", ["small_f", "large_f"])
def test_unresolved_F_fails_closed_after_child(request_data, case):
    if case == "small_f":
        request_data["section"].update(
            imposed_axial_velocity_m_s=1e6, psi_rad=math.nextafter(math.pi / 2, 0),
            tip_radius_m=math.nextafter(0.4, math.inf), speed_of_sound_m_s=1e9)
        request_data["polar"]["reynolds_tables"][-1]["reynolds_number"] = 1e20
    else:
        request_data["section"]["radius_m"] = 1e-4
    result = residual.evaluate_section_residual(request_data)
    assert result["reasons"] == ["SECTION_RESIDUAL_EXECUTION_FAILED"]
    assert result["load_result_count"] == result["lookup_result_count"] == 1
    assert result["outputs"] == result["output_units"] == {}


def test_freshness_input_ownership_and_claims(request_data):
    before = deepcopy(request_data)
    first = residual.evaluate_section_residual(request_data)
    assert request_data == before
    first["outputs"]["actual_load_request"]["polar"]["source"] = "changed"
    first["outputs"]["actual_load_result"]["outputs"]["loads"]["dynamic_pressure_pa"] = -1
    catalog = residual.section_residual_catalog()
    catalog["limits"]["input_json"]["max_depth"] = -1
    catalog["source_urls"].clear()
    second = residual.evaluate_section_residual(request_data)
    assert second["outputs"]["actual_load_request"]["polar"] == before["polar"]
    assert second["outputs"]["actual_load_result"]["outputs"]["loads"]["dynamic_pressure_pa"] > 0
    assert residual.section_residual_catalog()["limits"]["input_json"]["max_depth"] == 10
    assert residual.section_residual_catalog()["source_urls"]
    assert second["physical_validation"] == second["numerical_qualification"] == "NOT_ESTABLISHED"
    assert second["source_classification"] == "UNVERIFIED_CALLER_ASSERTION"
    assert second["mach_interval_status"] == "UNVERIFIED_CALLER_APPLICABILITY_ONLY"
    assert second["aircraft_status"] is second["feasibility"] is None


def test_guard_uses_no_V133_numerical_helpers(request_data, monkeypatch):
    original, calls = load.evaluate_section_load, []

    def forbidden(*args, **kwargs):
        pytest.fail("V133 numerical helper used by residual guard")

    def child(request):
        calls.append(deepcopy(request))
        result = original(request)
        monkeypatch.setattr(load, "_kinematics", forbidden)
        monkeypatch.setattr(load, "_loads", forbidden)
        monkeypatch.setattr(load, "evaluate_section_load", forbidden)
        return result

    monkeypatch.setattr(load, "evaluate_section_load", child)
    result = residual.evaluate_section_residual(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["load_result_count"] == len(calls) == 1


def test_child_subclass_rejected_before_copy(request_data, monkeypatch):
    original = load.evaluate_section_load

    class ForeignDict(dict):
        def __deepcopy__(self, memo):
            pytest.fail("child foreign copy hook")

    def child(request):
        result = original(request)
        result["outputs"]["loads"] = ForeignDict(result["outputs"]["loads"])
        return result

    monkeypatch.setattr(load, "evaluate_section_load", child)
    result = residual.evaluate_section_residual(request_data)
    assert result["reasons"] == ["LOAD_BOUNDARY_FAILED"]
    assert result["load_result_count"] == 0


@pytest.mark.parametrize("fault,expected_count,expected_calls", [
    (1, 0, 0), (2, 0, 1), (3, 0, 1), (4, 1, 1),
])
def test_hash_fault_boundaries(request_data, monkeypatch, fault, expected_count, expected_calls):
    original_hash, original_child = residual.sha256_record, load.evaluate_section_load
    hash_calls, child_calls = [], []

    def hashing(value):
        hash_calls.append(None)
        if len(hash_calls) == fault:
            raise ValueError("private fault")
        return original_hash(value)

    def child(request):
        child_calls.append(None)
        return original_child(request)

    monkeypatch.setattr(residual, "sha256_record", hashing)
    monkeypatch.setattr(load, "evaluate_section_load", child)
    result = residual.evaluate_section_residual(request_data)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["load_result_count"] == result["lookup_result_count"] == expected_count
    assert len(child_calls) == expected_calls
    assert result["outputs"] == result["output_units"] == {}
    if fault == 1:
        assert result["request_sha256"] is result["evaluation_sha256"] is None
    else:
        assert result["request_sha256"] == _digest(request_data)
        assert result["evaluation_sha256"] == _digest({key: value for key, value in result.items()
                                                      if key != "evaluation_sha256"})


@pytest.mark.parametrize("target", ["_velocity", "_closure", "sha256_record"])
def test_parent_baseexceptions_propagate(request_data, monkeypatch, target):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(residual, target, interrupted)
    with pytest.raises(KeyboardInterrupt):
        residual.evaluate_section_residual(request_data)


@pytest.mark.parametrize("options,limit,depth", [
    ({}, 32768, 10), ({"output": True}, 65536, 24), ({"child": True}, 32768, 16),
])
def test_exact_walk_node_and_depth_budgets(options, limit, depth):
    remaining, tree = limit - 1, []
    while remaining:
        nodes = min(257, remaining)
        tree.append([None] * (nodes - 1))
        remaining -= nodes
    residual._walk(tree, **options)
    tree.append([])
    with pytest.raises(ValueError):
        residual._walk(tree, **options)
    tree = None
    for _ in range(depth - 1):
        tree = [tree]
    residual._walk(tree, **options)
    with pytest.raises(ValueError):
        residual._walk([tree], **options)


@pytest.mark.parametrize("value", ["\ud800", "a" * 2001, [None] * 257, 1 << 1023])
def test_utf8_container_and_integer_limits_before_copy(request_data, monkeypatch, value):
    request_data["untrusted"] = value
    monkeypatch.setattr(load, "evaluate_section_load", lambda _: pytest.fail("unexpected child"))
    result = residual.evaluate_section_residual(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["request_sha256"] is result["evaluation_sha256"] is None


def test_maximum_polar_fully_retained(request_data):
    rows = [{"alpha_rad": -1.5 + 3 * i / 255, "cl": 0.25, "cd": 0.1} for i in range(256)]
    request_data["polar"]["reynolds_tables"] = [
        {"reynolds_number": 1000.0 * 10 ** i, "rows": deepcopy(rows)} for i in range(8)]
    result = residual.evaluate_section_residual(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["load_result_count"] == result["lookup_result_count"] == 1
    actual = result["outputs"]["actual_load_result"]
    assert actual["outputs"]["actual_lookup_request"]["polar"] == request_data["polar"]
    assert result["outputs"]["actual_load_request"]["polar"] == request_data["polar"]
    residual._walk(result, output=True)


@pytest.mark.parametrize("cl", [0, -2, 100])
def test_zero_and_signed_lift_residual(request_data, cl):
    for table in request_data["polar"]["reynolds_tables"]:
        for row in table["rows"]:
            row["cl"] = cl
    result = residual.evaluate_section_residual(request_data)
    output = result["outputs"]
    closure = output["closure"]
    assert closure["gamma_induced_m2_s"] > 0
    assert closure["gamma_lift_m2_s"] == pytest.approx(
        0.5 * math.hypot(output["kinematics"]["axial_velocity_m_s"],
                         output["kinematics"]["tangential_velocity_m_s"]) * 0.1 * cl)
    if cl == 0:
        assert closure["gamma_lift_m2_s"] == 0.0
        assert type(closure["gamma_lift_m2_s"]) is float
        assert output["residual_m2_s"] == closure["gamma_induced_m2_s"]
    else:
        assert math.copysign(1, output["residual_m2_s"]) == (-1 if cl == 100 else 1)


def test_orthogonality_velocity_and_dimension_units(request_data):
    result = residual.evaluate_section_residual(request_data)
    output, units = result["outputs"], result["output_units"]
    velocity = output["kinematics"]
    ua, ut, u = 5, 20, math.hypot(5, 20)
    wa, wt = 0.5 * ua + 0.5 * u * math.sin(0.6), 0.5 * ut + 0.5 * u * math.cos(0.6)
    assert velocity["axial_velocity_m_s"] == wa
    assert velocity["tangential_velocity_m_s"] == wt
    va, vt = velocity["induced_axial_velocity_m_s"], velocity["induced_tangential_velocity_m_s"]
    assert abs(va * wa - vt * wt) / (math.hypot(va, vt) * math.hypot(wa, wt)) < 1e-14
    assert units["residual_m2_s"] == units["closure"]["gamma_lift_m2_s"] == "m^2/s"
    for key in ("radius_ratio", "tip_gap", "local_wake_lambda", "f", "F", "geometry_factor"):
        assert units["closure"][key] == "1"


def test_native_large_integer_knot_and_signed_zero(request_data):
    derived = residual.evaluate_section_residual(request_data)["outputs"]["actual_load_result"]["outputs"]
    query = derived["actual_lookup_request"]["query"]
    knot = 2 ** 53 + 1
    request_data["polar"]["reynolds_tables"] = [{
        "reynolds_number": query["reynolds_number"],
        "rows": [{"alpha_rad": query["alpha_rad"], "cl": knot, "cd": -0.0},
                 {"alpha_rad": 1.5, "cl": 0, "cd": 0}],
    }]
    result = residual.evaluate_section_residual(request_data)
    child = result["outputs"]["actual_load_result"]["outputs"]
    lookup = child["actual_lookup_result"]["outputs"]
    assert type(lookup["cl"]) is int and lookup["cl"] == knot
    assert math.copysign(1, lookup["cd"]) == -1
    assert type(child["loads"]["lift_density_n_m"]) is float
    assert math.copysign(1, child["loads"]["drag_density_n_m"]) == -1
