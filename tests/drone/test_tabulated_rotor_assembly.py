"""Actual-component vector smokes for literal tabulated static assembly."""

import math
import sys
from copy import deepcopy
from dataclasses import asdict, replace
from unittest.mock import Mock

import pytest

from physimesh.drone import tabulated_hover_bemt_request as forward
from physimesh.drone import tabulated_rotor_assembly as assembly
from physimesh.drone.provenance import sha256_record


def request():
    template = {
        "evaluation": forward.EVALUATION, "radius_m": 1.0, "angular_speed_rad_s": 120.0,
        "blade_count": 2, "root_cutout_m": 0.2, "annuli": 12,
        "lift_curve_slope_per_rad": 5.7, "profile_drag_coefficient": 0.012,
        "stations": [{"radius_m": 0.0, "chord_m": 0.08, "blade_angle_rad": 0.12},
                     {"radius_m": 0.5, "chord_m": 0.06, "blade_angle_rad": 0.10},
                     {"radius_m": 1.0, "chord_m": 0.04, "blade_angle_rad": 0.08}],
        "geometry_source": "explicit synthetic variable chord and twist",
        "geometry_kind": "synthetic", "uncertainty_status": "unknown",
    }
    return {
        "evaluation": assembly.EVALUATION,
        "air": {"altitude_m": 1000.0, "altitude_kind": "geometric"},
        "rotors": [
            {"id": "air", "rotor_template": deepcopy(template), "center_body_m": [1.0, 0.0, 0.0],
             "axis_body": [0.0, 0.0, 1.0], "rotation_sign": 1},
            {"id": "left", "rotor_template": deepcopy(template), "center_body_m": [-1.0, 0.0, 0.0],
             "axis_body": [0.0, 0.0, 1.0], "rotation_sign": -1},
        ],
        "mass_kg": 3.0, "cg_body_m": [0.0, 0.0, 0.0],
        "gravity_direction_body": [0.0, 0.0, -1.0], "property_source": "unverified explicit test inputs",
    }


def actual_run(monkeypatch, supplied):
    air_spy = Mock(wraps=assembly.reference_air_properties)
    forward_spy = Mock(wraps=assembly.evaluate_tabulated_hover_bemt)
    core_spy = Mock(wraps=forward.solve_tabulated_hover)
    monkeypatch.setattr(assembly, "reference_air_properties", air_spy)
    monkeypatch.setattr(assembly, "evaluate_tabulated_hover_bemt", forward_spy)
    monkeypatch.setattr(forward, "solve_tabulated_hover", core_spy)
    before = deepcopy(supplied)
    result = assembly.evaluate_tabulated_rotor_assembly(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL", result["reasons"]
    assert result["rotor_evaluation_count"] == len(supplied["rotors"])
    air_spy.assert_called_once_with(**before["air"])
    assert forward_spy.call_count == core_spy.call_count == len(before["rotors"])
    assert supplied == before
    assert result["request_sha256"] == sha256_record(before)
    assert result["evaluation_sha256"] == sha256_record({
        k: v for k, v in result.items() if k != "evaluation_sha256"
    })
    density = result["outputs"]["air"]["state"]["density_kg_m3"]
    for rotor, row, call in zip(before["rotors"], result["outputs"]["rotors"],
                                forward_spy.call_args_list, strict=True):
        injected = {**rotor["rotor_template"], "density_kg_m3": density}
        assert call.args == (injected,)
        assert row["actual_forward_request"] == injected
        actual = row["actual_forward_result"]
        assert actual["status"] == "COMPUTED_EXPERIMENTAL"
        assert actual["request_sha256"] == sha256_record(injected)
        assert actual["evaluation_sha256"] == sha256_record({
            k: v for k, v in actual.items() if k != "evaluation_sha256"
        })
        assert len(actual["outputs"]["radii_m"]) == injected["annuli"]
        assert len(set(actual["outputs"]["chord_m"])) > 1
        assert len(set(actual["outputs"]["blade_angle_rad"])) > 1
    return result


def test_actual_symmetric_opposite_spins_and_id_air(monkeypatch):
    result = actual_run(monkeypatch, request())
    out = result["outputs"]
    first, second = out["rotors"]
    thrust = first["actual_forward_result"]["outputs"]["thrust_n"]
    torque = first["actual_forward_result"]["outputs"]["shaft_torque_nm"]
    assert thrust > 0.0 and torque > 0.0
    assert first["force_body_n"] == second["force_body_n"] == [0.0, 0.0, thrust]
    assert first["reaction_torque_body_nm"] == [0.0, 0.0, -torque]
    assert second["reaction_torque_body_nm"] == [0.0, 0.0, torque]
    assert first["moment_cg_body_nm"] == [0.0, -thrust, -torque]
    assert second["moment_cg_body_nm"] == [0.0, thrust, torque]
    weight = 3.0 * out["air"]["gravity_m_s2"]
    assert out["gravity_force_body_n"] == [0.0, 0.0, -weight]
    assert out["net_force_body_n"] == [0.0, 0.0, math.fsum([thrust, thrust, -weight])]
    assert out["net_moment_cg_body_nm"] == [0.0, 0.0, 0.0]
    assert [s["stage"] for s in result["stages"]] == ["air", "rotor:air", "rotor:left"]
    assert [t["to_stage"] for t in result["transfers"]] == ["rotor:air", "rotor:left"]


def test_actual_tilted_axes_cg_shift_and_manual_cross(monkeypatch):
    supplied = request()
    supplied["cg_body_m"] = [0.25, -0.4, 0.3]
    supplied["gravity_direction_body"] = [0.0, 0.6, -0.8]
    supplied["rotors"][0].update(axis_body=[0.6, 0.0, 0.8], center_body_m=[1.0, 0.5, -0.2])
    supplied["rotors"][1].update(axis_body=[0.0, -0.8, 0.6], center_body_m=[-0.5, 1.0, 0.7])
    supplied["rotors"][1]["rotor_template"]["angular_speed_rad_s"] = 135.0
    result = actual_run(monkeypatch, supplied)
    expected_forces, expected_moments = [], []
    for rotor, row in zip(supplied["rotors"], result["outputs"]["rotors"], strict=True):
        actual = row["actual_forward_result"]["outputs"]
        force = [actual["thrust_n"] * a for a in rotor["axis_body"]]
        reaction = [-rotor["rotation_sign"] * actual["shaft_torque_nm"] * a for a in rotor["axis_body"]]
        x, y, z = [c - g for c, g in zip(rotor["center_body_m"], supplied["cg_body_m"], strict=True)]
        fx, fy, fz = force
        cross = [y * fz - z * fy, z * fx - x * fz, x * fy - y * fx]
        moment = [math.fsum([c, q]) for c, q in zip(cross, reaction, strict=True)]
        assert row["force_body_n"] == force
        assert row["reaction_torque_body_nm"] == reaction
        assert row["moment_cg_body_nm"] == pytest.approx(moment, rel=1e-15, abs=0.0)
        expected_forces.append(force)
        expected_moments.append(moment)
    weight = supplied["mass_kg"] * result["outputs"]["air"]["gravity_m_s2"]
    gravity = [weight * d for d in supplied["gravity_direction_body"]]
    assert result["outputs"]["gravity_force_body_n"] == gravity
    assert result["outputs"]["net_force_body_n"] == [
        math.fsum([f[i] for f in expected_forces] + [gravity[i]]) for i in range(3)
    ]
    assert result["outputs"]["net_moment_cg_body_nm"] == pytest.approx([
        math.fsum(m[i] for m in expected_moments) for i in range(3)
    ], rel=1e-15, abs=0.0)


def atomic(result, status, supplied=None, count=0):
    assert result["status"] == status
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == result["transfers"] == []
    assert result["diagnostics_complete"] is False
    assert result["rotor_evaluation_count"] == count
    assert result["request_sha256"] == (sha256_record(supplied) if supplied is not None else None)
    assert result["aircraft_status"] is result["feasibility"] is None
    for key in ("physical_validation", "numerical_qualification", "runtime_identity"):
        assert result[key] == "NOT_ESTABLISHED"
    assert result["evaluation_sha256"] == (
        sha256_record({k: v for k, v in result.items() if k != "evaluation_sha256"})
        if status == "EXECUTION_FAILED" and supplied is not None else None)
    assert "PRIVATE_EXCEPTION" not in str(result)


class Foreign:
    def __deepcopy__(self, memo):
        raise AssertionError("foreign copy hook invoked")

    def __float__(self):
        raise AssertionError("foreign numeric hook invoked")


class IntSubclass(int):
    pass


class FloatSubclass(float):
    pass


class ListSubclass(list):
    pass


class StrSubclass(str):
    pass


@pytest.mark.parametrize("path,value", [
    (("rotors", 1, "id"), "air"), (("rotors", 1, "id"), "1bad"),
    (("rotors", 1, "id"), "a" * 33), (("rotors", 1, "id"), StrSubclass("ok")),
    (("rotors", 1, "axis_body"), [0, 0, 2]),
    (("rotors", 1, "axis_body"), [0, True, 1]),
    (("rotors", 1, "axis_body"), [0, 0, FloatSubclass(1)]),
    (("rotors", 1, "axis_body"), ListSubclass([0, 0, 1])),
    (("rotors", 1, "rotation_sign"), True), (("rotors", 1, "rotation_sign"), 1.0),
    (("rotors", 1, "rotation_sign"), 0), (("mass_kg",), 0), (("mass_kg",), True),
    (("mass_kg",), sys.float_info.min / 2), (("mass_kg",), IntSubclass(3)),
    (("cg_body_m",), [2**53 + 1, 0, 0]), (("cg_body_m",), [0, 0, 5e-324]),
    (("gravity_direction_body",), [0, 0, 0]), (("property_source",), " "),
    (("property_source",), "x" * 2001), (("property_source",), "\ud800"),
    (("property_source",), Foreign()), (("mass_kg",), 2**1023),
    (("mass_kg",), math.inf), (("air", "altitude_m"), True),
    (("air", "altitude_m"), -1), (("air", "altitude_m"), 30001),
    (("air", "altitude_kind"), "pressure"),
    (("rotors", 1, "rotor_template", "annuli"), 2049),
    (("rotors", 1, "rotor_template", "annuli"), True),
    (("rotors", 1, "rotor_template", "blade_count"), 33),
    (("rotors", 1, "rotor_template", "blade_count"), 0),
    (("rotors", 1, "rotor_template", "geometry_kind"), "verified"),
    (("rotors", 1, "rotor_template", "geometry_source"), " "),
    (("rotors", 1, "rotor_template", "uncertainty_status"), ""),
    (("rotors", 1, "rotor_template", "density_kg_m3"), 1.225),
    (("rotors", 1, "rotor_template", "radius_m"), False),
    (("rotors", 1, "rotor_template", "stations"), []),
    (("rotors", 1, "rotor_template", "stations", 1, "chord_m"), True),
    (("rotors", 1, "extra"), 1), (("air", "extra"), 1),
])
def test_preflight_all_entries_before_any_component(monkeypatch, path, value):
    supplied = request()
    target = supplied
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    air, adapter, core = Mock(), Mock(), Mock()
    monkeypatch.setattr(assembly, "reference_air_properties", air)
    monkeypatch.setattr(assembly, "evaluate_tabulated_hover_bemt", adapter)
    monkeypatch.setattr(forward, "solve_tabulated_hover", core)
    atomic(assembly.evaluate_tabulated_rotor_assembly(supplied), "MODEL_INAPPLICABLE")
    air.assert_not_called()
    adapter.assert_not_called()
    core.assert_not_called()


@pytest.mark.parametrize("case", ["4097", "nine", "cycle", "depth", "items", "nodes", "empty"])
def test_resource_preflight_no_calls(monkeypatch, case):
    supplied = request()
    if case in ("4097", "nine"):
        supplied["rotors"] = [deepcopy(supplied["rotors"][0]) for _ in range(3 if case == "4097" else 9)]
        for i, rotor in enumerate(supplied["rotors"]):
            rotor["id"] = f"r{i}"
            rotor["rotor_template"]["annuli"] = [2048, 2048, 1][i] if case == "4097" else 1
    elif case == "cycle":
        supplied["property_source"] = supplied
    elif case == "depth":
        value = 0
        for _ in range(12):
            value = [value]
        supplied["property_source"] = value
    elif case == "items":
        supplied["rotors"][1]["rotor_template"]["stations"] *= 86
    elif case == "nodes":
        supplied["property_source"] = [[0] * 256 for _ in range(256)]
    else:
        supplied["rotors"] = []
    air, adapter, core = Mock(), Mock(), Mock()
    monkeypatch.setattr(assembly, "reference_air_properties", air)
    monkeypatch.setattr(assembly, "evaluate_tabulated_hover_bemt", adapter)
    monkeypatch.setattr(forward, "solve_tabulated_hover", core)
    atomic(assembly.evaluate_tabulated_rotor_assembly(supplied), "MODEL_INAPPLICABLE")
    assert air.call_count == adapter.call_count == core.call_count == 0


@pytest.mark.parametrize("count,annuli", [(8, 512), (2, 2048)])
def test_actual_maximum_shapes(monkeypatch, count, annuli):
    supplied = request()
    supplied["rotors"] = [deepcopy(supplied["rotors"][0]) for _ in range(count)]
    for i, rotor in enumerate(supplied["rotors"]):
        rotor["id"] = f"r{i}"
        rotor["rotor_template"].update(annuli=annuli, blade_count=32, stations=[
            {"radius_m": j / 255, "chord_m": 0.08 - 0.04 * j / 255,
             "blade_angle_rad": 0.12 - 0.04 * j / 255} for j in range(256)])
    result = actual_run(monkeypatch, supplied)
    assembly._json(result, result["limits"]["output_json"])
    assert sum(len(r["actual_forward_result"]["outputs"]["radii_m"])
               for r in result["outputs"]["rotors"]) == 4096


@pytest.mark.parametrize("drag", [0.012, 0.0])
def test_actual_zero_angle_retains_profile_torque(drag):
    supplied = request()
    for rotor in supplied["rotors"]:
        rotor["rotor_template"]["profile_drag_coefficient"] = drag
        for station in rotor["rotor_template"]["stations"]:
            station["blade_angle_rad"] = 0.0
    result = assembly.evaluate_tabulated_rotor_assembly(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    for row in result["outputs"]["rotors"]:
        out = row["actual_forward_result"]["outputs"]
        assert out["thrust_n"] == out["induced_power_coefficient"] == 0.0
        assert (out["shaft_torque_nm"] > 0) if drag else (out["shaft_torque_nm"] == 0.0)
        assert row["force_body_n"] == [0.0, 0.0, 0.0]


def test_actual_late_domain_refusal_and_invalid_result_counts(monkeypatch):
    supplied = request()
    supplied["rotors"][1]["rotor_template"]["stations"][1]["chord_m"] = -0.1
    air, adapter, core = (Mock(wraps=assembly.reference_air_properties),
                          Mock(wraps=assembly.evaluate_tabulated_hover_bemt),
                          Mock(wraps=forward.solve_tabulated_hover))
    monkeypatch.setattr(assembly, "reference_air_properties", air)
    monkeypatch.setattr(assembly, "evaluate_tabulated_hover_bemt", adapter)
    monkeypatch.setattr(forward, "solve_tabulated_hover", core)
    atomic(assembly.evaluate_tabulated_rotor_assembly(supplied), "MODEL_INAPPLICABLE", supplied, 2)
    assert air.call_count == 1 and adapter.call_count == core.call_count == 2


@pytest.mark.parametrize("field", ["coherent_state", "gravity_m_s2", "dynamic_viscosity_pa_s"])
def test_typed_air_forgery_rejected(monkeypatch, field):
    supplied = request()
    actual = assembly.reference_air_properties(**supplied["air"])
    if field == "coherent_state":
        state = replace(actual.state, pressure_pa=actual.state.pressure_pa * 2,
                        density_kg_m3=actual.state.density_kg_m3 * 2)
        forged = replace(actual, state=state)
    else:
        forged = replace(actual, **{field: getattr(actual, field) * 2})
    monkeypatch.setattr(assembly, "reference_air_properties", Mock(return_value=forged))
    adapter = Mock()
    monkeypatch.setattr(assembly, "evaluate_tabulated_hover_bemt", adapter)
    atomic(assembly.evaluate_tabulated_rotor_assembly(supplied), "EXECUTION_FAILED", supplied)
    adapter.assert_not_called()


@pytest.mark.parametrize("field", ["thrust_n", "chord_m", "output_units", "physical_validation",
                                    "request_sha256", "extra"])
def test_rehashed_actual_child_forgery_counts_only_prior_validated(monkeypatch, field):
    supplied = request()
    real = assembly.evaluate_tabulated_hover_bemt
    calls = []

    def component(injected):
        actual = real(injected)
        calls.append(actual)
        if len(calls) == 2:
            if field == "thrust_n":
                actual["outputs"][field] *= 2
            elif field == "chord_m":
                actual["outputs"][field][0] *= 2
            elif field == "output_units":
                actual[field]["thrust_n"] = "kg"
            elif field == "physical_validation":
                actual[field] = "ESTABLISHED"
            else:
                actual[field] = "forged"
            actual["evaluation_sha256"] = sha256_record({
                k: v for k, v in actual.items() if k != "evaluation_sha256"})
        return actual

    monkeypatch.setattr(assembly, "evaluate_tabulated_hover_bemt", component)
    atomic(assembly.evaluate_tabulated_rotor_assembly(supplied), "EXECUTION_FAILED", supplied, 1)
    assert len(calls) == 2


def test_immediate_air_and_child_snapshots_survive_next_call_mutation(monkeypatch):
    supplied = request()
    actual_air = assembly.reference_air_properties(**supplied["air"])
    expected_air = asdict(actual_air)
    real = assembly.evaluate_tabulated_hover_bemt
    retained, expected = [], []

    def component(injected):
        if retained:
            retained[0]["outputs"]["thrust_n"] = -999.0
            retained[0]["outputs"]["chord_m"].clear()
        object.__setattr__(actual_air.state, "density_kg_m3", 999.0)
        object.__setattr__(actual_air, "gravity_m_s2", 999.0)
        actual = real(injected)
        retained.append(actual)
        expected.append(deepcopy(actual))
        return actual

    monkeypatch.setattr(assembly, "reference_air_properties", Mock(return_value=actual_air))
    monkeypatch.setattr(assembly, "evaluate_tabulated_hover_bemt", component)
    result = assembly.evaluate_tabulated_rotor_assembly(supplied)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["air"] == expected_air
    for row, actual in zip(result["outputs"]["rotors"], expected, strict=True):
        assert row["actual_forward_result"] == actual
        assert row["actual_forward_request"]["density_kg_m3"] == expected_air["state"]["density_kg_m3"]
    retained[-1]["outputs"].clear()
    assert result["outputs"]["rotors"][-1]["actual_forward_result"] == expected[-1]
    assert result["outputs"]["gravity_force_body_n"][2] == -3.0 * expected_air["gravity_m_s2"]


def test_signed_arithmetic_edges_and_exact_cancellation():
    tiny, huge = sys.float_info.min, sys.float_info.max
    assert assembly._sum([7.0, -7.0]) == assembly._difference(-3.0, -3.0) == 0.0
    assert assembly._mul(-2.0, 3.0) == -6.0
    operations = [lambda: assembly._mul(-huge, 2.0),
                  lambda: assembly._mul(-tiny, 0.5),
                  lambda: assembly._mul(-tiny, tiny),
                  lambda: assembly._difference(tiny, math.nextafter(tiny, math.inf)),
                  lambda: assembly._sum([tiny, -math.nextafter(tiny, math.inf)]),
                  lambda: assembly._sum([huge, huge])]
    for operation in operations:
        with pytest.raises((ValueError, OverflowError)):
            operation()
    rotor = request()["rotors"][0]
    rotor["center_body_m"] = [-huge, 0.0, 0.0]
    with pytest.raises(ValueError):
        assembly._loads(rotor, [huge, 0.0, 0.0], {"thrust_n": 1.0, "shaft_torque_nm": 0.0})


@pytest.mark.parametrize("case", ["mass_overflow", "arm_overflow", "cross_overflow", "product_underflow"])
def test_actual_load_arithmetic_failure_is_atomic(case):
    supplied = request()
    if case == "mass_overflow":
        supplied["mass_kg"] = sys.float_info.max
    elif case == "arm_overflow":
        supplied["cg_body_m"][0] = sys.float_info.max
        supplied["rotors"][0]["center_body_m"][0] = -sys.float_info.max
    elif case == "cross_overflow":
        supplied["rotors"][0]["center_body_m"][0] = sys.float_info.max
    else:
        supplied["rotors"][0]["axis_body"] = [sys.float_info.min, 0.0, 1.0]
        supplied["rotors"][0]["rotor_template"]["profile_drag_coefficient"] = 1e-10
        for station in supplied["rotors"][0]["rotor_template"]["stations"]:
            station["blade_angle_rad"] = 0.0
    atomic(assembly.evaluate_tabulated_rotor_assembly(supplied), "EXECUTION_FAILED", supplied,
           2 if case == "mass_overflow" else 1)


@pytest.mark.parametrize("field,value", [("mass_kg", -sys.float_info.max),
                                         ("axis_body", [sys.float_info.max, 0, 1]),
                                         ("axis_body", [5e-324, 0, 1])])
def test_preflight_extremes_no_air(monkeypatch, field, value):
    supplied = request()
    (supplied if field == "mass_kg" else supplied["rotors"][1])[field] = value
    air = Mock()
    monkeypatch.setattr(assembly, "reference_air_properties", air)
    atomic(assembly.evaluate_tabulated_rotor_assembly(supplied), "MODEL_INAPPLICABLE")
    air.assert_not_called()


@pytest.mark.parametrize("error", [RuntimeError("PRIVATE_EXCEPTION"), ValueError("PRIVATE_EXCEPTION"),
                                  KeyboardInterrupt("PRIVATE_EXCEPTION")])
def test_second_child_exception_sanitized_or_base_propagates(monkeypatch, error):
    supplied, real, calls = request(), assembly.evaluate_tabulated_hover_bemt, []

    def component(injected):
        calls.append(injected)
        if len(calls) == 2:
            raise error
        return real(injected)

    monkeypatch.setattr(assembly, "evaluate_tabulated_hover_bemt", component)
    if isinstance(error, Exception):
        atomic(assembly.evaluate_tabulated_rotor_assembly(supplied), "EXECUTION_FAILED", supplied, 1)
    else:
        with pytest.raises(KeyboardInterrupt, match="PRIVATE_EXCEPTION"):
            assembly.evaluate_tabulated_rotor_assembly(supplied)
    assert len(calls) == 2


@pytest.mark.parametrize("case", ["unsupported", "preflight", "domain", "failed", "computed"])
def test_canonical_hash_status_matrix(monkeypatch, case):
    supplied = request()
    supplied["property_source"] = "unverified Unicode \u03bc"
    if case == "unsupported":
        supplied["evaluation"] = "other"
    elif case == "preflight":
        supplied["mass_kg"] = False
    elif case == "domain":
        supplied["rotors"][0]["rotor_template"]["root_cutout_m"] = 2.0
    elif case == "failed":
        monkeypatch.setattr(assembly, "reference_air_properties", Mock(side_effect=RuntimeError("PRIVATE_EXCEPTION")))
    result = assembly.evaluate_tabulated_rotor_assembly(supplied)
    if case != "computed":
        atomic(result, {"unsupported": "SOLVER_UNSUPPORTED", "preflight": "MODEL_INAPPLICABLE",
                        "domain": "MODEL_INAPPLICABLE", "failed": "EXECUTION_FAILED"}[case],
               supplied if case in ("domain", "failed") else None, int(case == "domain"))
    else:
        assert result["status"] == "COMPUTED_EXPERIMENTAL"
        assert result["request_sha256"] == sha256_record(supplied)
        assert result["evaluation_sha256"] == sha256_record({
            k: v for k, v in result.items() if k != "evaluation_sha256"})


def test_fresh_catalog_deep_mutations_no_component_calls(monkeypatch):
    air, child = Mock(), Mock()
    monkeypatch.setattr(assembly, "reference_air_properties", air)
    monkeypatch.setattr(assembly, "evaluate_tabulated_hover_bemt", child)
    original = assembly.tabulated_rotor_assembly_catalog()
    mutated = assembly.tabulated_rotor_assembly_catalog()
    mutated["input_units"]["rotors"]["rotor_template"]["stations"]["chord_m"] = "bad"
    mutated["output_field_units"]["rotors"]["actual_forward_result"]["outputs"].clear()
    mutated["request_contract"]["template"]["geometry"].clear()
    mutated["limits"]["child_input_json"].clear()
    mutated["limitations"].clear()
    assert assembly.tabulated_rotor_assembly_catalog() == original
    air.assert_not_called()
    child.assert_not_called()
