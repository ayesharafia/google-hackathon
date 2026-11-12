"""Invented V136 fixtures: actual children and independent boundary checks only."""

import hashlib
import json
import math
from copy import deepcopy
from decimal import Decimal, localcontext
from itertools import pairwise

import pytest

from physimesh.drone import polar_rotor as rotor
from physimesh.drone import section_solve as solve


@pytest.fixture
def request_data():
    return {
        "evaluation": rotor.EVALUATION,
        "rotor": {
            "tip_radius_m": 0.6, "hub_radius_m": 0.2, "blade_count": 2,
            "angular_speed_rad_s": 50, "imposed_axial_velocity_m_s": 5,
            "density_kg_m3": 1.2, "dynamic_viscosity_pa_s": 1.8e-5,
            "speed_of_sound_m_s": 343, "geometry_source": "invented fixture; no dataset",
            "uncertainty_status": "unknown",
        },
        "annuli": [{
            "radial_inner_m": 0.2, "radial_outer_m": 0.6, "chord_m": 0.1,
            "pitch_rad": 0.5,
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
            "solve": {"psi_lower_rad": 0.35, "psi_upper_rad": 0.9,
                      "angle_tolerance_rad": 0.001, "residual_tolerance_m2_s": 0.01,
                      "max_evaluations": 16},
        }],
    }


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf-8")).hexdigest()


def _reseal(value):
    value["evaluation_sha256"] = _digest({
        key: item for key, item in value.items() if key != "evaluation_sha256"})


def _derived(request, index):
    """Test-owned reconstruction; no rotor derivation helpers."""
    annulus, inputs = request["annuli"][index], request["rotor"]
    width = math.fsum((float(annulus["radial_outer_m"]), -float(annulus["radial_inner_m"])))
    radius = math.fsum((float(annulus["radial_inner_m"]), 0.5 * width))
    section = {key: deepcopy(inputs[key]) for key in (
        "imposed_axial_velocity_m_s", "tip_radius_m", "density_kg_m3",
        "dynamic_viscosity_pa_s", "speed_of_sound_m_s", "blade_count")}
    section.update(imposed_tangential_velocity_m_s=float(inputs["angular_speed_rad_s"]) * radius,
                   radius_m=radius, chord_m=deepcopy(annulus["chord_m"]),
                   pitch_rad=deepcopy(annulus["pitch_rad"]))
    return {"evaluation": solve.EVALUATION,
            "residual_template": {"evaluation": "section_residual_experimental",
                                  "polar": deepcopy(annulus["polar"]), "section": section},
            "solve": deepcopy(annulus["solve"])}


def _record(monkeypatch):
    original, calls = solve.evaluate_section_solve, []

    def child(request):
        calls.append(deepcopy(request))
        return original(request)

    monkeypatch.setattr(solve, "evaluate_section_solve", child)
    return original, calls


def _counts(result, sections, residuals):
    assert type(result["section_solve_result_count"]) is int
    assert result["section_solve_result_count"] == sections
    for key in ("residual_result_count", "load_result_count", "lookup_result_count"):
        assert type(result[key]) is int
        assert result[key] == residuals


def _three_annuli(request):
    template = deepcopy(request["annuli"][0])
    bounds = [0.2, 0.3, 0.45, 0.6]
    request["annuli"] = []
    for inner, outer in pairwise(bounds):
        row = deepcopy(template)
        row.update(radial_inner_m=inner, radial_outer_m=outer)
        radius = math.fsum((inner, 0.5 * math.fsum((outer, -inner))))
        row["solve"].update(psi_lower_rad=math.atan2(5, 50 * radius) + 0.1, psi_upper_rad=1.2)
        request["annuli"].append(row)


def test_actual_single_annulus_full_child_and_decimal95_integration(request_data, monkeypatch):
    original, calls = _record(monkeypatch)
    untouched = deepcopy(request_data)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    output = result["outputs"]
    assert output["rotor_state"] == "COMPUTED"
    assert request_data == untouched
    assert calls == [_derived(request_data, 0)]
    row = output["annuli"][0]
    assert set(row) == {"annulus_index", "radial_inner_m", "radial_outer_m",
                        "midpoint_radius_m", "radial_width_m", "solve_result"}
    assert row["solve_result"] == original(calls[0])
    child = row["solve_result"]
    _counts(result, 1, len(child["outputs"]["evaluations"]))
    assert child["request_sha256"] == _digest(calls[0])
    selected = child["outputs"]["solution"]["evaluation_index"]
    loads = child["outputs"]["evaluations"][selected]["result"]["outputs"][
        "actual_load_result"]["outputs"]["loads"]
    integrated = output["integrated"]
    assert integrated["integration_method"] == "MIDPOINT_PRESCRIBED_ANNULI"
    contribution = integrated["contributions"][0]
    assert contribution["selected_evaluation_index"] == selected
    assert contribution["thrust_density_n_m"] == loads["thrust_density_n_m"]
    assert contribution["torque_density_nm_m"] == loads["torque_density_nm_m"]
    with localcontext() as context:
        context.prec = 95
        width = Decimal.from_float(row["radial_width_m"])
        thrust = float(Decimal.from_float(loads["thrust_density_n_m"]) * width)
        torque = float(Decimal.from_float(loads["torque_density_nm_m"]) * width)
        power = float(Decimal(50) * Decimal.from_float(torque))
    assert integrated["totals"] == {"thrust_n": thrust, "torque_nm": torque, "shaft_power_w": power}
    assert contribution["thrust_n"] == thrust
    assert contribution["torque_nm"] == torque
    assert row["midpoint_radius_m"] == calls[0]["residual_template"]["section"]["radius_m"]
    assert result["request_sha256"] == _digest(request_data)
    assert result["evaluation_sha256"] == _digest({
        key: value for key, value in result.items() if key != "evaluation_sha256"})
    assert result["output_units"]["annuli"][0]["solve_result"]["outputs"] == child["output_units"]
    assert result["output_units"]["integrated"]["totals"]["shaft_power_w"] == "W"
    assert result["physical_validation"] == result["numerical_qualification"] == "NOT_ESTABLISHED"


def test_nonconverged_budget_two_has_no_partial_totals(request_data, monkeypatch):
    request_data["annuli"][0]["solve"]["max_evaluations"] = 2
    _, calls = _record(monkeypatch)
    result = rotor.evaluate_polar_rotor(request_data)
    assert len(calls) == 1
    _counts(result, 1, 2)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["annuli"][0]["solve_result"]["outputs"]["solve_state"] == (
        "EVALUATION_BUDGET_EXHAUSTED")
    assert result["outputs"]["rotor_state"] == "NOT_RUN_SECTION_NOT_CONVERGED"
    assert result["outputs"]["integrated"] is None
    assert result["output_units"]["integrated"] == "not_applicable"


def test_all_annuli_run_after_first_nonconverged(request_data, monkeypatch):
    _three_annuli(request_data)
    request_data["annuli"][0]["solve"]["max_evaluations"] = 2
    _, calls = _record(monkeypatch)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert calls == [_derived(request_data, index) for index in range(3)]
    rows = result["outputs"]["annuli"]
    assert [row["annulus_index"] for row in rows] == [0, 1, 2]
    assert rows[0]["solve_result"]["outputs"]["solve_state"] != "CONVERGED"
    _counts(result, 3, sum(row["solve_result"]["residual_result_count"] for row in rows))
    assert result["outputs"]["integrated"] is None


def test_last_annulus_full_polar_and_endpoint_preflight_before_any_call(request_data, monkeypatch):
    _three_annuli(request_data)
    request_data["annuli"][-1]["polar"]["reynolds_tables"][-1]["rows"][-1]["cd"] = -1
    _, calls = _record(monkeypatch)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert calls == []
    _counts(result, 0, 0)


@pytest.mark.parametrize("mutation", ["state", "bracket", "solution", "metadata", "extra_row"])
def test_rehashed_child_forgery_is_atomic(request_data, monkeypatch, mutation):
    original = solve.evaluate_section_solve

    def child(request):
        value = original(request)
        output = value["outputs"]
        if mutation == "state":
            output["solve_state"] = "NOT_BRACKETED"
        elif mutation == "bracket":
            output["final_bracket"]["angle_width_rad"] = 0.0
        elif mutation == "solution":
            output["solution"]["evaluation_index"] = True
        elif mutation == "metadata":
            value["physical_validation"] = "ESTABLISHED"
        else:
            output["evaluations"].append(deepcopy(output["evaluations"][-1]))
        _reseal(value)
        return value

    monkeypatch.setattr(solve, "evaluate_section_solve", child)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["reasons"] == ["SOLVE_BOUNDARY_FAILED"]
    assert result["outputs"] == result["output_units"] == {}
    _counts(result, 0, 0)


def test_guard_never_reruns_model_or_v135_algorithm_helpers(request_data, monkeypatch):
    request = _derived(request_data, 0)
    actual = solve.evaluate_section_solve(request)

    def forbidden(*args, **kwargs):
        pytest.fail("guard reran a model or V135 numerical/algorithm helper")

    for name in ("evaluate_section_solve", "_bisect", "_output_units", "_bracket", "_solution",
                 "_actual_request"):
        monkeypatch.setattr(solve, name, forbidden)
    monkeypatch.setattr(solve._res, "evaluate_section_residual", forbidden)
    rotor._guard_solve(actual, request)


@pytest.mark.parametrize("field,value", [
    ("tip_radius_m", 0), ("tip_radius_m", True), ("tip_radius_m", math.inf),
    ("hub_radius_m", 0), ("hub_radius_m", -1), ("hub_radius_m", 0.6),
    ("blade_count", True), ("blade_count", 2.0), ("blade_count", 0), ("blade_count", 65),
    ("angular_speed_rad_s", 0), ("angular_speed_rad_s", -1),
    ("angular_speed_rad_s", math.nextafter(0.0, 1.0)),
    ("imposed_axial_velocity_m_s", -1), ("imposed_axial_velocity_m_s", False),
    ("imposed_axial_velocity_m_s", math.nan),
    ("density_kg_m3", 0), ("dynamic_viscosity_pa_s", -1), ("speed_of_sound_m_s", True),
    ("geometry_source", " "), ("geometry_source", "x" * 2001),
    ("uncertainty_status", ""), ("uncertainty_status", 1),
])
def test_invalid_rotor_static_fields_before_calls_or_hash(request_data, monkeypatch, field, value):
    request_data["rotor"][field] = value
    _, calls = _record(monkeypatch)

    def forbidden(*args, **kwargs):
        pytest.fail("invalid request reached hashing")

    monkeypatch.setattr(rotor, "sha256_record", forbidden)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert calls == []
    _counts(result, 0, 0)
    assert result["request_sha256"] is result["evaluation_sha256"] is None


@pytest.mark.parametrize("mutation", ["native_type", "gap", "overlap", "last_tip", "first_hub"])
def test_boundary_continuity_is_full_native_exact(request_data, monkeypatch, mutation):
    _three_annuli(request_data)
    if mutation == "native_type":
        request_data["annuli"][0]["radial_outer_m"] = 1
        request_data["annuli"][1]["radial_inner_m"] = 1.0
        request_data["annuli"][1]["radial_outer_m"] = 1.5
        request_data["annuli"][2].update(radial_inner_m=1.5, radial_outer_m=2.0)
        request_data["rotor"]["tip_radius_m"] = 2.0
    elif mutation == "gap":
        request_data["annuli"][1]["radial_inner_m"] = 0.31
    elif mutation == "overlap":
        request_data["annuli"][1]["radial_inner_m"] = 0.29
    elif mutation == "last_tip":
        request_data["annuli"][-1]["radial_outer_m"] = 0.59
    else:
        request_data["annuli"][0]["radial_inner_m"] = 0.21
    _, calls = _record(monkeypatch)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert calls == []
    _counts(result, 0, 0)


@pytest.mark.parametrize("index", [1, 2])
def test_middle_or_last_bad_upper_branch_preflight_before_any_call(request_data, monkeypatch, index):
    _three_annuli(request_data)
    request_data["annuli"][index]["solve"]["psi_upper_rad"] = math.pi / 2
    _, calls = _record(monkeypatch)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert calls == []


def test_nine_annuli_refused(request_data, monkeypatch):
    request_data["annuli"] *= 9
    _, calls = _record(monkeypatch)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert calls == []


def test_unresolved_midpoint_refused_before_call(request_data, monkeypatch):
    inner, outer = 0.5, math.nextafter(0.5, math.inf)
    request_data["rotor"].update(hub_radius_m=inner, tip_radius_m=outer)
    request_data["annuli"][0].update(radial_inner_m=inner, radial_outer_m=outer)
    _, calls = _record(monkeypatch)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert calls == []


def test_actual_three_converged_decimal95_selected_load_integration(request_data):
    _three_annuli(request_data)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    output = result["outputs"]
    assert output["rotor_state"] == "COMPUTED"
    contributions = output["integrated"]["contributions"]
    expected_thrust, expected_torque = [], []
    with localcontext() as context:
        context.prec = 95
        for row, contribution in zip(output["annuli"], contributions, strict=True):
            child = row["solve_result"]["outputs"]
            selected = child["solution"]["evaluation_index"]
            loads = child["evaluations"][selected]["result"]["outputs"][
                "actual_load_result"]["outputs"]["loads"]
            width = Decimal.from_float(row["radial_width_m"])
            thrust = float(Decimal.from_float(loads["thrust_density_n_m"]) * width)
            torque = float(Decimal.from_float(loads["torque_density_nm_m"]) * width)
            assert contribution["selected_evaluation_index"] == selected
            assert contribution["thrust_n"] == thrust
            assert contribution["torque_nm"] == torque
            expected_thrust.append(Decimal.from_float(thrust))
            expected_torque.append(Decimal.from_float(torque))
        total_thrust = float(sum(expected_thrust, Decimal(0)))
        total_torque = float(sum(expected_torque, Decimal(0)))
        power = float(Decimal(50) * Decimal.from_float(total_torque))
    assert output["integrated"]["totals"] == {
        "thrust_n": total_thrust, "torque_nm": total_torque, "shaft_power_w": power}


@pytest.mark.parametrize("state", ["ood", "not_bracketed"])
def test_middle_ood_or_nonbracket_retains_all_annuli(request_data, monkeypatch, state):
    _three_annuli(request_data)
    polar = request_data["annuli"][1]["polar"]
    if state == "ood":
        polar.update(sampled_mach_number=0, declared_mach_interval=[0, 0])
    else:
        for table in polar["reynolds_tables"]:
            for row in table["rows"]:
                row["cl"] = 0
    _, calls = _record(monkeypatch)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert len(calls) == 3
    rows = result["outputs"]["annuli"]
    expected = "NOT_RUN_OUT_OF_POLAR_DOMAIN" if state == "ood" else "NOT_BRACKETED"
    assert rows[1]["solve_result"]["outputs"]["solve_state"] == expected
    assert rows[1]["solve_result"]["residual_result_count"] == (1 if state == "ood" else 2)
    assert result["outputs"]["integrated"] is None
    assert result["output_units"]["integrated"] == "not_applicable"
    _counts(result, 3, sum(row["solve_result"]["residual_result_count"] for row in rows))


def test_eight_actual_annuli_budget_two_sixteen_residuals(request_data, monkeypatch):
    template = deepcopy(request_data["annuli"][0])
    boundaries = [0.2 + 0.05 * index for index in range(8)] + [0.6]
    request_data["annuli"] = []
    for inner, outer in pairwise(boundaries):
        row = deepcopy(template)
        row.update(radial_inner_m=inner, radial_outer_m=outer)
        radius = math.fsum((inner, 0.5 * math.fsum((outer, -inner))))
        row["solve"].update(psi_lower_rad=math.atan2(5, 50 * radius) + 0.1,
                            psi_upper_rad=1.2, max_evaluations=2)
        request_data["annuli"].append(row)
    _, calls = _record(monkeypatch)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert len(calls) == 8
    _counts(result, 8, 16)
    assert len(result["outputs"]["annuli"]) == 8
    assert result["outputs"]["integrated"] is None


def test_second_child_exception_keeps_only_first_whole_child_count(request_data, monkeypatch):
    _three_annuli(request_data)
    original, accepted = solve.evaluate_section_solve, []

    def child(request):
        if accepted:
            raise ValueError("private child detail")
        value = original(request)
        accepted.append(value)
        return value

    monkeypatch.setattr(solve, "evaluate_section_solve", child)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["reasons"] == ["SOLVE_BOUNDARY_FAILED"]
    _counts(result, 1, accepted[0]["residual_result_count"])
    assert result["outputs"] == result["output_units"] == {}
    assert "private" not in json.dumps(result)


def test_synthetic_integration_only_selects_owned_row_not_last():
    """Pure integration fixture only; these are not actual guarded model responses."""
    def evaluation(thrust, torque):
        return {"result": {"outputs": {"actual_load_result": {"outputs": {"loads": {
            "thrust_density_n_m": thrust, "torque_density_nm_m": torque}}}}}}

    rows = [{"annulus_index": 0, "radial_width_m": 0.25, "solve_result": {"outputs": {
        "solution": {"evaluation_index": 0},
        "evaluations": [evaluation(8.0, -4.0), evaluation(999.0, 999.0)]}}}]
    integrated = rotor._integrate(rows, 50.0)
    assert integrated["contributions"][0]["selected_evaluation_index"] == 0
    assert integrated["totals"] == {"thrust_n": 2.0, "torque_nm": -1.0, "shaft_power_w": -50.0}


def _reseal_tree(value):
    """Test-owned bottom-up rehash, so tamper checks cannot rely on stale digests."""
    if type(value) is dict:
        for child in value.values():
            _reseal_tree(child)
        if "evaluation_sha256" in value:
            _reseal(value)
    elif type(value) is list:
        for child in value:
            _reseal_tree(child)


@pytest.mark.parametrize("mutation", [
    "trace_order", "row_psi", "native_bool", "row_request_hash", "units", "source_urls",
    "false_count", "nested_load", "nested_residual", "solution_owner", "evaluation_digest",
])
def test_rehashed_second_child_forgery_retains_only_previous_count(request_data, monkeypatch, mutation):
    _three_annuli(request_data)
    original, accepted, calls = solve.evaluate_section_solve, [], []

    def child(request):
        value = original(request)
        calls.append(None)
        if len(calls) == 1:
            accepted.append(deepcopy(value))
            return value
        output = value["outputs"]
        rows = output["evaluations"]
        if mutation == "trace_order":
            rows[0], rows[1] = rows[1], rows[0]
            units = value["output_units"]["evaluations"]
            units[0], units[1] = units[1], units[0]
        elif mutation == "row_psi":
            rows[0]["psi_rad"] = math.nextafter(rows[0]["psi_rad"], math.inf)
        elif mutation == "native_bool":
            output["final_bracket"]["lower_evaluation_index"] = True
        elif mutation == "row_request_hash":
            rows[0]["request_sha256"] = "0" * 64
        elif mutation == "units":
            value["output_units"]["solve_state"] = "N"
        elif mutation == "source_urls":
            value["source_urls"][0] = "https://invalid.example/forged"
        elif mutation == "false_count":
            value["residual_result_count"] = True
        elif mutation == "nested_load":
            rows[0]["result"]["outputs"]["actual_load_result"]["outputs"]["loads"][
                "thrust_density_n_m"] += 1.0
        elif mutation == "nested_residual":
            rows[0]["result"]["outputs"]["residual_m2_s"] = 0.0
        elif mutation == "solution_owner":
            output["solution"]["evaluation_index"] = 0
        _reseal_tree(value)
        if mutation == "evaluation_digest":
            value["evaluation_sha256"] = "0" * 64
        return value

    monkeypatch.setattr(solve, "evaluate_section_solve", child)
    result = rotor.evaluate_polar_rotor(request_data)
    assert len(calls) == 2
    assert result["status"] == "EXECUTION_FAILED"
    assert result["reasons"] == ["SOLVE_BOUNDARY_FAILED"]
    _counts(result, 1, accepted[0]["residual_result_count"])
    assert result["outputs"] == result["output_units"] == {}


def test_forged_convergence_cannot_override_tolerances(request_data, monkeypatch):
    request_data["annuli"][0]["solve"].update(
        max_evaluations=2, angle_tolerance_rad=1e-30, residual_tolerance_m2_s=1e-30)
    original = solve.evaluate_section_solve

    def child(request):
        value = original(request)
        output = value["outputs"]
        row = output["evaluations"][0]
        output.update(solve_state="CONVERGED", solution={
            "evaluation_index": 0, "psi_rad": row["psi_rad"],
            "residual_m2_s": row["result"]["outputs"]["residual_m2_s"]})
        value["output_units"]["solution"] = {
            "evaluation_index": "index", "psi_rad": "rad", "residual_m2_s": "m^2/s"}
        _reseal_tree(value)
        return value

    monkeypatch.setattr(solve, "evaluate_section_solve", child)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["reasons"] == ["SOLVE_BOUNDARY_FAILED"]
    _counts(result, 0, 0)


@pytest.mark.parametrize("stage", ["initial_hash", "persistent_seal", "nan_export"])
def test_root_export_failures_are_atomic_with_accepted_counts(request_data, monkeypatch, stage):
    original_hash, calls = rotor.sha256_record, []
    original_child = solve.evaluate_section_solve

    def child(request):
        value = original_child(request)
        calls.append(deepcopy(value))
        return value

    def hashing(value):
        root_seal = (value.get("evaluation") == rotor.EVALUATION
                     and value.get("schema_version") == rotor.SCHEMA_VERSION)
        if stage == "initial_hash" or root_seal:
            raise ValueError("private export detail")
        return original_hash(value)

    monkeypatch.setattr(solve, "evaluate_section_solve", child)
    if stage == "nan_export":
        monkeypatch.setattr(rotor, "_output_units", lambda *args: {"bad": math.nan})
    else:
        monkeypatch.setattr(rotor, "sha256_record", hashing)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["reasons"] == ["POLAR_ROTOR_EXECUTION_FAILED"]
    _counts(result, len(calls), sum(value["residual_result_count"] for value in calls))
    assert result["outputs"] == result["output_units"] == {}
    assert len(calls) == (0 if stage == "initial_hash" else 1)
    if stage != "nan_export":
        assert result["request_sha256"] is result["evaluation_sha256"] is None
    assert "private" not in json.dumps(result)


def test_foreign_hidden_child_refused_without_copy_hook(request_data, monkeypatch):
    class Foreign(dict):
        def __deepcopy__(self, memo):
            pytest.fail("foreign child copy hook ran")

        def items(self):
            pytest.fail("foreign child iteration hook ran")

    original = solve.evaluate_section_solve

    def child(request):
        value = original(request)
        value["outputs"]["hidden"] = Foreign()
        return value

    monkeypatch.setattr(solve, "evaluate_section_solve", child)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["reasons"] == ["SOLVE_BOUNDARY_FAILED"]
    _counts(result, 0, 0)


@pytest.mark.parametrize("stage", ["child", "integration", "hash"])
def test_baseexception_propagates(request_data, monkeypatch, stage):
    class Abort(BaseException):
        pass

    def stop(*args, **kwargs):
        raise Abort

    if stage == "child":
        monkeypatch.setattr(solve, "evaluate_section_solve", stop)
    elif stage == "integration":
        monkeypatch.setattr(rotor, "_integrate", stop)
    else:
        monkeypatch.setattr(rotor, "sha256_record", stop)
    with pytest.raises(Abort):
        rotor.evaluate_polar_rotor(request_data)


@pytest.mark.parametrize("kind", ["cycle", "utf8", "depth"])
def test_whole_input_bounded_before_copy_hash_or_calls(request_data, monkeypatch, kind):
    if kind == "cycle":
        request_data["hidden"] = request_data
    elif kind == "utf8":
        request_data["rotor"]["geometry_source"] = "\ud800"
    else:
        nested = None
        for _ in range(17):
            nested = [nested]
        request_data["hidden"] = nested
    _, calls = _record(monkeypatch)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert calls == []
    _counts(result, 0, 0)


def test_fresh_catalog_and_result_input_alias_isolation(request_data):
    catalog = rotor.polar_rotor_catalog()
    catalog["limits"]["input_json"]["max_depth"] = -1
    catalog["input_units"]["rotor"]["tip_radius_m"] = "wrong"
    assert rotor.polar_rotor_catalog()["limits"]["input_json"]["max_depth"] == 16
    assert rotor.polar_rotor_catalog()["input_units"]["rotor"]["tip_radius_m"] == "m"
    result = rotor.evaluate_polar_rotor(request_data)
    untouched = deepcopy(result)
    request_data["annuli"][0]["polar"]["source"] = "caller mutation"
    assert result == untouched
    result["limitations"].append("caller mutation")
    assert "caller mutation" not in rotor.polar_rotor_catalog()["limitations"]


def test_fresh_v135_catalog_drift_rejected(request_data, monkeypatch):
    original = solve.section_solve_catalog

    def catalog():
        value = original()
        value["runtime_identity"] = "ESTABLISHED"
        return value

    monkeypatch.setattr(solve, "section_solve_catalog", catalog)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["reasons"] == ["SOLVE_BOUNDARY_FAILED"]
    _counts(result, 0, 0)


@pytest.mark.parametrize("path", [(), ("rotor",), ("annuli", 0), ("annuli", 0, "solve")])
@pytest.mark.parametrize("mutation", ["extra", "missing"])
def test_exact_request_schema_before_calls(request_data, monkeypatch, path, mutation):
    target = request_data
    for key in path:
        target = target[key]
    if mutation == "extra":
        target["extra"] = 0
    else:
        target.pop(next(iter(target)))
    _, calls = _record(monkeypatch)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert calls == []
    _counts(result, 0, 0)


@pytest.mark.parametrize("field,value", [
    ("chord_m", False), ("chord_m", 0), ("pitch_rad", -1),
    ("pitch_rad", math.nextafter(math.pi / 2, math.inf)),
])
def test_invalid_annulus_geometry_before_calls(request_data, monkeypatch, field, value):
    request_data["annuli"][0][field] = value
    _, calls = _record(monkeypatch)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert calls == []


def test_actual_sixteen_evaluation_budget_is_retained(request_data, monkeypatch):
    request_data["annuli"][0]["solve"].update(
        angle_tolerance_rad=1e-30, residual_tolerance_m2_s=1e-30)
    _, calls = _record(monkeypatch)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert len(calls) == 1
    _counts(result, 1, 16)
    child = result["outputs"]["annuli"][0]["solve_result"]
    assert child["outputs"]["solve_state"] == "EVALUATION_BUDGET_EXHAUSTED"
    assert len(child["outputs"]["evaluations"]) == 16
    assert result["outputs"]["integrated"] is None


@pytest.mark.parametrize("stage", ["child", "output"])
def test_deep_child_or_export_refused_with_appropriate_counts(request_data, monkeypatch, stage):
    nested = None
    for _ in range(41):
        nested = [nested]
    original, children = solve.evaluate_section_solve, []

    def child(request):
        value = original(request)
        children.append(deepcopy(value))
        if stage == "child":
            value["hidden"] = nested
        return value

    monkeypatch.setattr(solve, "evaluate_section_solve", child)
    if stage == "output":
        monkeypatch.setattr(rotor, "_output_units", lambda *args: {"hidden": nested})
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "EXECUTION_FAILED"
    accepted = 0 if stage == "child" else 1
    _counts(result, accepted, children[0]["residual_result_count"] if accepted else 0)
    assert result["reasons"] == [
        "SOLVE_BOUNDARY_FAILED" if stage == "child" else "POLAR_ROTOR_EXECUTION_FAILED"]
    assert result["outputs"] == result["output_units"] == {}


def _synthetic_integration_rows(densities, width):
    """Pure arithmetic fixtures only; never presented as actual model responses."""
    return [{"annulus_index": index, "radial_width_m": width,
             "solve_result": {"outputs": {
                 "solution": {"evaluation_index": 0}, "evaluations": [{"result": {"outputs": {
                     "actual_load_result": {"outputs": {"loads": {
                         "thrust_density_n_m": thrust, "torque_density_nm_m": torque}}}}}}]}}}
            for index, (thrust, torque) in enumerate(densities)]


@pytest.mark.parametrize("density,width,omega", [
    (1e308, 2.0, 1.0),
    (float.fromhex("0x1.0000000000000p-1022"), 0.25, 1.0),
    (float.fromhex("0x1.0000000000000p-1022"),
     float.fromhex("0x1.0000000000000p-1022"), 1.0),
    (1e308, 1.0, 2.0),
])
def test_synthetic_integration_only_refuses_overflow_and_underflow(density, width, omega):
    rows = _synthetic_integration_rows([(density, density)], width)
    with pytest.raises((ValueError, OverflowError)):
        rotor._integrate(rows, omega)


def test_synthetic_integration_only_allows_zero_and_signed_cancellation():
    rows = _synthetic_integration_rows([(8.0, -4.0), (-8.0, 4.0), (0.0, -0.0)], 0.25)
    result = rotor._integrate(rows, 50.0)
    assert result["totals"] == {"thrust_n": 0.0, "torque_nm": 0.0, "shaft_power_w": 0.0}
    assert result["contributions"][0]["torque_nm"] == -1.0
    assert result["contributions"][1]["thrust_n"] == -2.0


def test_integration_arithmetic_failure_preserves_all_accepted_counts(request_data, monkeypatch):
    _three_annuli(request_data)
    original_child, children = solve.evaluate_section_solve, []
    original_integrate = rotor._integrate

    def child(request):
        value = original_child(request)
        children.append(deepcopy(value))
        return value

    def fail_integration(rows, omega):
        # Inject an arithmetic fault only after all actual child guards have passed.
        assert len(rows) == 3
        return original_integrate(_synthetic_integration_rows([(1e308, 1e308)], 2.0), omega)

    monkeypatch.setattr(solve, "evaluate_section_solve", child)
    monkeypatch.setattr(rotor, "_integrate", fail_integration)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["reasons"] == ["POLAR_ROTOR_EXECUTION_FAILED"]
    _counts(result, 3, sum(value["residual_result_count"] for value in children))
    assert result["outputs"] == result["output_units"] == {}


def test_actual_eight_annuli_128_residual_load_lookup_calls(request_data, monkeypatch):
    template = deepcopy(request_data["annuli"][0])
    boundaries = [0.2 + 0.05 * index for index in range(8)] + [0.6]
    request_data["annuli"] = []
    for inner, outer in pairwise(boundaries):
        annulus = deepcopy(template)
        annulus.update(radial_inner_m=inner, radial_outer_m=outer)
        radius = math.fsum((inner, 0.5 * math.fsum((outer, -inner))))
        annulus["solve"].update(
            psi_lower_rad=math.atan2(5, 50 * radius) + 0.0001, psi_upper_rad=1.5,
            angle_tolerance_rad=1e-30, residual_tolerance_m2_s=1e-30)
        request_data["annuli"].append(annulus)
    calls = {"residual": 0, "load": 0, "lookup": 0}

    def wrapper(original, label):
        def evaluate(request):
            calls[label] += 1
            return original(request)
        return evaluate

    residual, load, polar = solve._res, solve._res._load, solve._res._load._polar
    monkeypatch.setattr(residual, "evaluate_section_residual",
                        wrapper(residual.evaluate_section_residual, "residual"))
    monkeypatch.setattr(load, "evaluate_section_load", wrapper(load.evaluate_section_load, "load"))
    monkeypatch.setattr(polar, "evaluate_section_polar", wrapper(polar.evaluate_section_polar, "lookup"))
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    _counts(result, 8, 128)
    assert calls == {"residual": 128, "load": 128, "lookup": 128}
    assert all(row["solve_result"]["outputs"]["solve_state"] == "EVALUATION_BUDGET_EXHAUSTED"
               for row in result["outputs"]["annuli"])
    assert result["outputs"]["integrated"] is None


def test_actual_maximum_polar_tables_and_rows_fit_declared_bounds(request_data, monkeypatch):
    annulus = request_data["annuli"][0]
    annulus["solve"]["max_evaluations"] = 2
    annulus["polar"]["reynolds_tables"] = [
        {"reynolds_number": 1000.0 * (10 ** index), "rows": [
            {"alpha_rad": -1.5 + 3.0 * row / 255, "cl": 4, "cd": 0.1}
            for row in range(256)]}
        for index in range(8)]
    _, calls = _record(monkeypatch)
    result = rotor.evaluate_polar_rotor(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert len(calls) == 1
    _counts(result, 1, 2)
    child = result["outputs"]["annuli"][0]["solve_result"]
    assert len(child["outputs"]["evaluations"]) == 2
    rotor._walk(request_data)
    solve._walk(calls[0])
    rotor._walk(child, child=True)
    rotor._walk(result, output=True)
