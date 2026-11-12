"""Actual-component and bounded-contract checks for prescribed static targets."""

import math
import sys
from copy import deepcopy
from dataclasses import asdict
from unittest.mock import Mock

import pytest

from physimesh.drone import tabulated_hover_bemt_request as forward
from physimesh.drone import tabulated_hover_thrust_target as inverse
from physimesh.drone import tabulated_rotor_assembly as literal
from physimesh.drone import tabulated_thrust_target_assembly as workflow
from physimesh.drone.provenance import sha256_record
from physimesh.drone.reference_air_properties import reference_air_properties


def request():
    """Caller-prescribed fixed 100 N; no forward model generates this target."""
    template = {
        "evaluation": inverse.EVALUATION,
        "rotor_template": {
            "evaluation": forward.EVALUATION, "radius_m": 1.0, "blade_count": 2,
            "root_cutout_m": 0.2, "annuli": 12, "lift_curve_slope_per_rad": 5.7,
            "profile_drag_coefficient": 0.012,
            "stations": [
                {"radius_m": 0.0, "chord_m": 0.08, "blade_angle_rad": 0.12},
                {"radius_m": 0.5, "chord_m": 0.06, "blade_angle_rad": 0.10},
                {"radius_m": 1.0, "chord_m": 0.04, "blade_angle_rad": 0.08},
            ],
            "geometry_source": "explicit synthetic variable chord and twist",
            "geometry_kind": "synthetic", "uncertainty_status": "unknown",
        },
        "target_thrust_n": 100.0, "angular_speed_bracket_rad_s": [50.0, 300.0],
        "absolute_thrust_tolerance_n": 0.001, "max_evaluations": 32,
    }
    return {
        "evaluation": workflow.EVALUATION,
        "air": {"altitude_m": 1000.0, "altitude_kind": "geometric"},
        "rotors": [
            {"id": "air", "target_template": deepcopy(template),
             "center_body_m": [1.0, 0.0, 0.0], "axis_body": [0.0, 0.0, 1.0], "rotation_sign": 1},
            {"id": "left", "target_template": deepcopy(template),
             "center_body_m": [-1.0, 0.0, 0.0], "axis_body": [0.0, 0.0, 1.0], "rotation_sign": -1},
        ],
        "mass_kg": 3.0, "cg_body_m": [0.0, 0.0, 0.0],
        "gravity_direction_body": [0.0, 0.0, -1.0], "property_source": "unverified explicit fixture",
    }


def baseline(supplied):
    air = asdict(reference_air_properties(**supplied["air"]))
    injected, results = [], []
    for rotor in supplied["rotors"]:
        target = deepcopy(rotor["target_template"])
        target["rotor_template"]["density_kg_m3"] = air["state"]["density_kg_m3"]
        injected.append(target)
        results.append(inverse.evaluate_tabulated_hover_thrust_target(deepcopy(target)))
    return air, injected, results


def spies(monkeypatch):
    calls = [Mock(wraps=workflow.reference_air_properties),
             Mock(wraps=workflow.evaluate_tabulated_hover_thrust_target),
             Mock(wraps=inverse.evaluate_tabulated_hover_bemt),
             Mock(wraps=forward.solve_tabulated_hover),
             Mock(wraps=workflow.validate_tabulated_hover_thrust_target_result)]
    for module, name, call in zip(
        (workflow, workflow, inverse, forward, workflow),
        ("reference_air_properties", "evaluate_tabulated_hover_thrust_target",
         "evaluate_tabulated_hover_bemt", "solve_tabulated_hover", "validate_tabulated_hover_thrust_target_result"),
        calls, strict=True,
    ):
        monkeypatch.setattr(module, name, call)
    monkeypatch.setattr(literal, "evaluate_tabulated_rotor_assembly", Mock(side_effect=AssertionError("rerun")))
    return calls


def assert_digest(result):
    assert result["evaluation_sha256"] == sha256_record({
        k: v for k, v in result.items() if k != "evaluation_sha256"
    })


def assert_success(result, supplied, air, injected, results):
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["diagnostics_complete"] is True
    assert result["request_sha256"] == sha256_record(supplied)
    assert_digest(result)
    assert result["inverse_result_count"] == len(results)
    assert result["forward_evaluation_count"] == sum(r["evaluation_count"] for r in results)
    assert result["outputs"]["air"] == air
    expected_stages = [{"stage": "air", "inputs": supplied["air"],
                        "inputs_sha256": sha256_record(supplied["air"]), "result_sha256": sha256_record(air)}]
    expected_transfers = []
    expected_forces, expected_moments = [], []
    for rotor, row, target, direct in zip(supplied["rotors"], result["outputs"]["rotors"],
                                         injected, results, strict=True):
        assert direct["status"] == "COMPUTED_EXPERIMENTAL"
        assert row["actual_target_request"] == target
        assert row["actual_target_result"] == direct
        assert row.keys() == {"id", "force_body_n", "reaction_torque_body_nm", "moment_cg_body_nm",
                              "actual_target_request", "actual_target_result"}
        assert abs(direct["outputs"]["thrust_residual_n"]) <= target["absolute_thrust_tolerance_n"]
        selected = direct["outputs"]["actual_forward_result"]["outputs"]
        force = [selected["thrust_n"] * a for a in rotor["axis_body"]]
        reaction = [-rotor["rotation_sign"] * selected["shaft_torque_nm"] * a for a in rotor["axis_body"]]
        x, y, z = [c - g for c, g in zip(rotor["center_body_m"], supplied["cg_body_m"], strict=True)]
        fx, fy, fz = force
        cross = [y * fz - z * fy, z * fx - x * fz, x * fy - y * fx]
        moment = [math.fsum([c, r]) for c, r in zip(cross, reaction, strict=True)]
        assert row["id"] == rotor["id"]
        assert row["force_body_n"] == force
        assert row["reaction_torque_body_nm"] == reaction
        assert row["moment_cg_body_nm"] == moment
        expected_forces.append(force)
        expected_moments.append(moment)
        stage = "rotor:" + rotor["id"]
        expected_stages.append({"stage": stage, "inputs": target, "inputs_sha256": sha256_record(target),
                                "result_sha256": sha256_record(direct)})
        expected_transfers.append({
            "from_stage": "air", "from_field": "state.density_kg_m3", "to_stage": stage,
            "to_field": "rotor_template.density_kg_m3", "value": air["state"]["density_kg_m3"],
            "unit": "kg/m^3", "producer_result_sha256": sha256_record(air),
            "consumer_request_sha256": sha256_record(target),
        })
    gravity = [supplied["mass_kg"] * air["gravity_m_s2"] * d for d in supplied["gravity_direction_body"]]
    assert result["outputs"]["gravity_force_body_n"] == gravity
    assert result["outputs"]["net_force_body_n"] == [
        math.fsum([v[i] for v in expected_forces] + [gravity[i]]) for i in range(3)
    ]
    assert result["outputs"]["net_moment_cg_body_nm"] == [
        math.fsum([v[i] for v in expected_moments]) for i in range(3)
    ]
    assert result["stages"] == expected_stages
    assert result["transfers"] == expected_transfers


@pytest.mark.parametrize("tilted", [False, True])
def test_actual_smoke_direct_inverse_and_manual_vectors(monkeypatch, tilted):
    supplied = request()
    if tilted:
        supplied["cg_body_m"] = [0.25, -0.5, 0.75]
        supplied["rotors"][0].update(axis_body=[0.6, 0.0, 0.8], center_body_m=[1.0, 2.0, -0.25])
        supplied["rotors"][1].update(axis_body=[0.0, -0.8, 0.6], rotation_sign=1)
        supplied["gravity_direction_body"] = [0.0, 0.6, -0.8]
    air, injected, direct = baseline(supplied)
    before = deepcopy(supplied)
    air_call, target, trial, core, guard = spies(monkeypatch)
    result = workflow.evaluate_tabulated_thrust_target_assembly(supplied)
    assert_success(result, supplied, air, injected, direct)
    assert supplied == before
    assert [call.call_count for call in (air_call, target, trial, core, guard)] == [
        1, 2, result["forward_evaluation_count"], result["forward_evaluation_count"], 2,
    ]
    assert [call.args[0] for call in target.call_args_list] == injected
    if not tilted:
        assert result["outputs"]["net_moment_cg_body_nm"] == [0.0, 0.0, 0.0]
        assert result["outputs"]["net_force_body_n"][2] != 0.0


def assert_atomic(result, status, inverses=0, forwards=0, supplied=None):
    assert result["status"] == status
    assert result["diagnostics_complete"] is False
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == result["transfers"] == []
    assert type(result["inverse_result_count"]) is type(result["forward_evaluation_count"]) is int
    assert (result["inverse_result_count"], result["forward_evaluation_count"]) == (inverses, forwards)
    assert result["request_sha256"] == (sha256_record(supplied) if supplied is not None else None)
    if supplied is None or status == "MODEL_INAPPLICABLE":
        assert result["evaluation_sha256"] is None
    else:
        assert_digest(result)


@pytest.mark.parametrize("case", ["last_spin", "last_axis", "last_type", "last_source", "work33280"])
def test_late_invalid_or_global_work_fails_before_any_model(monkeypatch, case):
    supplied = request()
    last = supplied["rotors"][-1]
    if case == "last_spin":
        last["rotation_sign"] = True
    elif case == "last_axis":
        last["axis_body"] = [0.0, 0.0, 2.0]
    elif case == "last_type":
        last["target_template"]["rotor_template"]["stations"][-1]["chord_m"] = "0.04"
    elif case == "last_source":
        last["target_template"]["rotor_template"]["geometry_source"] = " "
    else:
        supplied["rotors"] = [deepcopy(last) for _ in range(8)]
        for i, rotor in enumerate(supplied["rotors"]):
            rotor["id"] = "r" + str(i)
            rotor["target_template"]["rotor_template"]["annuli"] = 512
            rotor["target_template"]["max_evaluations"] = 8 + (i == 7)
        assert sum(r["target_template"]["max_evaluations"] * r["target_template"]["rotor_template"]["annuli"]
                   for r in supplied["rotors"]) == 33280
    calls = spies(monkeypatch)
    assert_atomic(workflow.evaluate_tabulated_thrust_target_assembly(supplied), "MODEL_INAPPLICABLE")
    for call in calls:
        call.assert_not_called()


def test_actual_maximum_payload_and_exact_global_boundary(monkeypatch):
    supplied = request()
    rotor = supplied["rotors"][0]
    template = rotor["target_template"]["rotor_template"]
    template.update(annuli=512, blade_count=32, stations=[
        {"radius_m": i / 255, "chord_m": 0.08 - 0.04 * (i / 255),
         "blade_angle_rad": 0.12 - 0.04 * (i / 255)} for i in range(256)
    ])
    # Actual direct test preparation selects a known endpoint, outside measured calls.
    air = asdict(reference_air_properties(**supplied["air"]))
    known = forward.evaluate_tabulated_hover_bemt({
        **deepcopy(template), "density_kg_m3": air["state"]["density_kg_m3"], "angular_speed_rad_s": 50.0,
    })
    assert known["status"] == "COMPUTED_EXPERIMENTAL"
    rotor["target_template"].update(target_thrust_n=known["outputs"]["thrust_n"], max_evaluations=8)
    supplied["rotors"] = [deepcopy(rotor) for _ in range(8)]
    for i, entry in enumerate(supplied["rotors"]):
        entry["id"] = "r" + str(i)
        entry["rotation_sign"] = 1 if i % 2 == 0 else -1
    assert sum(r["target_template"]["max_evaluations"] * r["target_template"]["rotor_template"]["annuli"]
               for r in supplied["rotors"]) == 32768
    air, injected, direct = baseline(supplied)
    calls = spies(monkeypatch)
    result = workflow.evaluate_tabulated_thrust_target_assembly(supplied)
    assert_success(result, supplied, air, injected, direct)
    assert [c.call_count for c in calls] == [1, 8, 16, 16, 8]
    assert result["inverse_result_count"] == 8 and result["forward_evaluation_count"] == 16
    limits = workflow.tabulated_thrust_target_assembly_catalog()["limits"]
    workflow._json(supplied, limits["input_json"])
    workflow._json(result, limits["output_json"])
    assert (limits["input_json"]["max_nodes_including_keys"], limits["input_json"]["max_depth"]) == (65536, 14)
    assert (limits["output_json"]["max_nodes_including_keys"], limits["output_json"]["max_depth"]) == (524288, 24)
    assert len(result["outputs"]["rotors"]) == 8
    assert all(len(r["actual_target_result"]["outputs"]["actual_forward_result"]["outputs"]["radii_m"]) == 512
               for r in result["outputs"]["rotors"])


def test_catalog_deep_fresh_and_no_model_calls(monkeypatch):
    calls = spies(monkeypatch)
    original = workflow.tabulated_thrust_target_assembly_catalog()
    fresh = workflow.tabulated_thrust_target_assembly_catalog()
    fresh["input_units"]["rotors"]["target_template"]["rotor_template"]["stations"]["chord_m"] = "bad"
    fresh["output_field_units"]["rotors"]["actual_target_result"]["outputs"][
        "actual_forward_result"]["outputs"]["radii_m"] = "bad"
    fresh["limits"]["inverse_input_json"]["max_depth"] = -1
    fresh["status_reason_matrix"]["MODEL_INAPPLICABLE"].clear()
    fresh["limitations"].clear()
    assert workflow.tabulated_thrust_target_assembly_catalog() == original
    assert original["required_fields"] == list(request())
    assert original["rotor_fields"] == list(request()["rotors"][0])
    assert "density_kg_m3" not in original["rotor_template_fields"]
    assert "angular_speed_rad_s" not in original["rotor_template_fields"]
    for call in calls:
        call.assert_not_called()


@pytest.mark.parametrize("late", [False, True])
@pytest.mark.parametrize("case,status,count", [
    ("zero_angle", "TARGET_NOT_BRACKETED", 2),
    ("budget", "ITERATION_LIMIT", 2),
    ("negative_chord", "MODEL_INAPPLICABLE", 1),
])
def test_actual_failures_stop_atomically_and_count_only_guarded(monkeypatch, late, case, status, count):
    supplied = request()
    failing = supplied["rotors"][int(late)]["target_template"]
    if case == "zero_angle":
        for station in failing["rotor_template"]["stations"]:
            station["blade_angle_rad"] = 0.0
    elif case == "budget":
        failing["max_evaluations"] = 2
    else:
        failing["rotor_template"]["stations"][0]["chord_m"] = -1.0
    sentinel = deepcopy(supplied["rotors"][0])
    sentinel["id"] = "uncalled"
    supplied["rotors"].append(sentinel)
    _, injected, direct = baseline(supplied)
    assert direct[int(late)]["status"] == status
    assert direct[int(late)]["evaluation_count"] == count
    calls = spies(monkeypatch)
    result = workflow.evaluate_tabulated_thrust_target_assembly(supplied)
    expected_count = sum(r["evaluation_count"] for r in direct[:int(late) + 1])
    assert_atomic(result, status, int(late) + 1, expected_count, supplied)
    assert [c.call_count for c in calls] == [1, int(late) + 1, expected_count, expected_count, int(late) + 1]
    assert [c.args[0] for c in calls[1].call_args_list] == injected[:int(late) + 1]


@pytest.mark.parametrize("late", [False, True])
def test_actual_inverse_execution_failure_is_guarded_and_counted(monkeypatch, late):
    supplied = request()
    _, _, direct = baseline(supplied)
    prior = direct[0]["evaluation_count"] if late else 0
    calls = spies(monkeypatch)
    real_trial = inverse.evaluate_tabulated_hover_bemt._mock_wraps

    def fail_trial(arguments):
        if calls[2].call_count == prior + 1:
            raise RuntimeError("private infrastructure detail")
        return real_trial(arguments)

    calls[2].side_effect = fail_trial
    result = workflow.evaluate_tabulated_thrust_target_assembly(supplied)
    assert_atomic(result, "EXECUTION_FAILED", int(late) + 1, prior + 1, supplied)
    assert [c.call_count for c in calls] == [1, int(late) + 1, prior + 1, prior, int(late) + 1]
    assert "private infrastructure detail" not in str(result)


@pytest.mark.parametrize("component", ["air", "inverse", "second_inverse", "guard"])
def test_ordinary_exception_discards_partials_and_untrusted_counts(monkeypatch, component):
    supplied = request()
    _, _, direct = baseline(supplied)
    calls = spies(monkeypatch)
    failure = RuntimeError("secret private payload")
    if component == "second_inverse":
        calls[1].side_effect = [direct[0], failure]
    else:
        calls[{"air": 0, "inverse": 1, "guard": 4}[component]].side_effect = failure
    result = workflow.evaluate_tabulated_thrust_target_assembly(supplied)
    prior = component == "second_inverse"
    assert_atomic(result, "EXECUTION_FAILED", int(prior), direct[0]["evaluation_count"] if prior else 0, supplied)
    assert "secret private payload" not in str(result)


@pytest.mark.parametrize("component", ["air", "inverse", "guard"])
def test_base_exception_propagates(monkeypatch, component):
    supplied = request()
    calls = spies(monkeypatch)
    calls[{"air": 0, "inverse": 1, "guard": 4}[component]].side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        workflow.evaluate_tabulated_thrust_target_assembly(supplied)


def rehash(actual):
    actual["evaluation_sha256"] = sha256_record({k: v for k, v in actual.items() if k != "evaluation_sha256"})


@pytest.mark.parametrize("case", ["coherent_pressure_density", "viscosity", "sound", "gravity", "type"])
def test_actual_air_forgeries_stop_before_inverse(monkeypatch, case):
    supplied = request()
    air = reference_air_properties(**supplied["air"])
    if case == "coherent_pressure_density":
        object.__setattr__(air.state, "pressure_pa", air.state.pressure_pa * 1.01)
        object.__setattr__(air.state, "density_kg_m3", air.state.density_kg_m3 * 1.01)
    elif case == "type":
        air = asdict(air)
    else:
        name = {"viscosity": "dynamic_viscosity_pa_s", "sound": "speed_of_sound_m_s",
                "gravity": "gravity_m_s2"}[case]
        object.__setattr__(air, name, getattr(air, name) * 1.01)
    calls = spies(monkeypatch)
    calls[0].side_effect = lambda **kwargs: air
    result = workflow.evaluate_tabulated_thrust_target_assembly(supplied)
    assert_atomic(result, "EXECUTION_FAILED", supplied=supplied)
    assert [c.call_count for c in calls] == [1, 0, 0, 0, 0]


@pytest.mark.parametrize("late", [False, True])
@pytest.mark.parametrize("case", ["selected", "trace", "count", "request_hash", "units"])
def test_rehashed_actual_inverse_forgeries_discard_unvalidated_count(monkeypatch, late, case):
    supplied = request()
    _, _, direct = baseline(supplied)
    damaged = deepcopy(direct[int(late)])
    if case == "selected":
        child = damaged["outputs"]["actual_forward_result"]
        child["outputs"]["radii_m"][0] += 0.001
        rehash(child)
        damaged["trace"][-1]["full_actual_result_sha256"] = sha256_record(child)
    elif case == "trace":
        damaged["trace"][0]["thrust_residual_n"] += 1.0
    elif case == "count":
        damaged["evaluation_count"] = 2
    elif case == "request_hash":
        damaged["request_sha256"] = "0" * 64
    else:
        damaged["output_units"]["achieved_thrust_n"] = "kg"
    rehash(damaged)
    calls = spies(monkeypatch)
    calls[1].side_effect = [direct[0], damaged] if late else [damaged]
    result = workflow.evaluate_tabulated_thrust_target_assembly(supplied)
    assert_atomic(result, "EXECUTION_FAILED", int(late), direct[0]["evaluation_count"] if late else 0, supplied)
    assert [c.call_count for c in calls] == [1, int(late) + 1, 0, 0, int(late) + 1]


def test_intermediate_full_result_digest_is_format_only(monkeypatch):
    supplied = request()
    air, injected, direct = baseline(supplied)
    direct[0]["trace"][0]["full_actual_result_sha256"] = "0123456789abcdef" * 4
    rehash(direct[0])
    calls = spies(monkeypatch)
    calls[1].side_effect = direct
    result = workflow.evaluate_tabulated_thrust_target_assembly(supplied)
    assert_success(result, supplied, air, injected, direct)
    assert any("FORMAT-ONLY" in limitation for limitation in result["limitations"])
    assert [c.call_count for c in calls] == [1, 2, 0, 0, 2]


def test_retained_air_and_first_inverse_detached_before_next_call(monkeypatch):
    supplied = request()
    air, injected, direct = baseline(supplied)
    retained_air = reference_air_properties(**supplied["air"])
    retained_results = deepcopy(direct)
    calls = spies(monkeypatch)
    calls[0].side_effect = lambda **kwargs: retained_air

    def next_inverse(arguments):
        if calls[1].call_count == 2:
            object.__setattr__(retained_air.state, "density_kg_m3", 999.0)
            object.__setattr__(retained_air, "gravity_m_s2", 999.0)
            retained_results[0]["outputs"]["actual_forward_result"]["outputs"]["radii_m"][0] = -999.0
            retained_results[0]["trace"].clear()
        return retained_results[calls[1].call_count - 1]

    calls[1].side_effect = next_inverse
    result = workflow.evaluate_tabulated_thrust_target_assembly(supplied)
    assert_success(result, supplied, air, injected, direct)
    before = deepcopy(result)
    retained_results[1].clear()
    supplied["rotors"][0]["target_template"].clear()
    assert result == before


@pytest.mark.parametrize("reason", ["Request snapshot failed.", "private copy/hash fault"])
def test_narrow_guard_excludes_actual_inverse_infrastructure_faults(monkeypatch, reason):
    supplied = request()
    _, injected, direct = baseline(supplied)
    with monkeypatch.context() as patch:
        patch.setattr(inverse, "evaluate_tabulated_hover_bemt", Mock(side_effect=RuntimeError("private")))
        damaged = inverse.evaluate_tabulated_hover_thrust_target(deepcopy(injected[1]))
    assert damaged["status"] == "EXECUTION_FAILED" and damaged["evaluation_count"] == 1
    damaged["reasons"] = [reason]
    rehash(damaged)
    calls = spies(monkeypatch)
    calls[1].side_effect = [direct[0], damaged]
    result = workflow.evaluate_tabulated_thrust_target_assembly(supplied)
    assert_atomic(result, "EXECUTION_FAILED", 1, direct[0]["evaluation_count"], supplied)
    assert reason not in str(result)
    assert [c.call_count for c in calls] == [1, 2, 0, 0, 2]


def reject_without_models(monkeypatch, supplied, *, before_copy=False, status="MODEL_INAPPLICABLE"):
    calls = spies(monkeypatch)
    copying = Mock(wraps=workflow.deepcopy)
    monkeypatch.setattr(workflow, "deepcopy", copying)
    assert_atomic(workflow.evaluate_tabulated_thrust_target_assembly(supplied), status)
    for call in calls:
        call.assert_not_called()
    if before_copy:
        assert all(call.args[0] is not supplied for call in copying.call_args_list)


@pytest.mark.parametrize("case", ["cycle", "depth", "nodes", "items", "string", "utf8", "integer",
                                  "nan", "inf", "negative_inf"])
def test_strict_json_boundaries_before_copy_and_models(monkeypatch, case):
    limits = workflow.tabulated_thrust_target_assembly_catalog()["limits"]["input_json"]
    boundary, excessive = 0, None
    if case == "cycle":
        excessive = []
        excessive.append(excessive)
    elif case == "depth":
        for _ in range(13):
            boundary = [boundary]
        excessive = [boundary]
    elif case == "nodes":
        excessive = [[0] * 255 for _ in range(256)]  # 65537 values, root included.
        boundary = deepcopy(excessive)
        boundary[-1].pop()  # Exactly 65536 nodes.
    elif case == "items":
        boundary, excessive = [0] * 256, [0] * 257
    elif case == "string":
        boundary, excessive = "é" * 2000, "é" * 2001
    elif case == "utf8":
        boundary, excessive = "é", "\ud800"
    elif case == "integer":
        boundary, excessive = 1 << 1022, 1 << 1023
    else:
        excessive = {"nan": float("nan"), "inf": float("inf"), "negative_inf": -float("inf")}[case]
    workflow._json(boundary, limits)
    with pytest.raises(ValueError):
        workflow._json(excessive, limits)
    reject_without_models(monkeypatch, excessive, before_copy=True)


@pytest.mark.parametrize("base,value", [(dict, {}), (list, []), (str, "source"), (int, 1), (float, 1.0),
                                      (object, None)])
def test_foreign_copy_hooks_and_subclasses_rejected_before_copy(monkeypatch, base, value):
    hook = Mock(side_effect=AssertionError("foreign copy hook invoked"))
    foreign = type("Foreign", (base,), {"__deepcopy__": hook})
    supplied = request()
    supplied["property_source"] = foreign() if base is object else foreign(value)
    reject_without_models(monkeypatch, supplied, before_copy=True)
    hook.assert_not_called()


@pytest.mark.parametrize("level", ["root", "rotor", "target", "template", "station"])
@pytest.mark.parametrize("extra", [False, True])
def test_closed_shapes_reject_missing_and_extra_fields(monkeypatch, level, extra):
    supplied = request()
    rotor = supplied["rotors"][-1]
    target = rotor["target_template"]
    template = target["rotor_template"]
    selected = {"root": supplied, "rotor": rotor, "target": target, "template": template,
                "station": template["stations"][-1]}[level]
    selected.update(unexpected=0) if extra else selected.pop(next(iter(selected)))
    reject_without_models(monkeypatch, supplied)


@pytest.mark.parametrize("case", ["unsupported", "density", "omega", "annuli", "blades", "budget", "stations",
                                  "duplicate_id", "axis_zero", "mass_zero", "mass_negative", "mass_bool"])
def test_omissions_bool_counts_and_declarations(monkeypatch, case):
    supplied = request()
    rotor = supplied["rotors"][-1]
    target = rotor["target_template"]
    template = target["rotor_template"]
    if case == "unsupported":
        supplied["evaluation"] = "unsupported"
    elif case in ("density", "omega"):
        template["density_kg_m3" if case == "density" else "angular_speed_rad_s"] = 1.0
    elif case in ("annuli", "blades", "stations"):
        template[{"annuli": "annuli", "blades": "blade_count", "stations": "stations"}[case]] = True
    elif case == "budget":
        target["max_evaluations"] = True
    elif case == "duplicate_id":
        rotor["id"] = supplied["rotors"][0]["id"]
    elif case == "axis_zero":
        rotor["axis_body"] = [0.0, 0.0, 0.0]
    else:
        supplied["mass_kg"] = {"mass_zero": 0.0, "mass_negative": -1.0, "mass_bool": True}[case]
    reject_without_models(monkeypatch, supplied,
                          status="SOLVER_UNSUPPORTED" if case == "unsupported" else "MODEL_INAPPLICABLE")


def test_actual_units_cover_raw_air_and_only_nested_output_scopes():
    result = workflow.evaluate_tabulated_thrust_target_assembly(request())
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    catalog = workflow.tabulated_thrust_target_assembly_catalog()
    units = result["output_units"]
    assert units == catalog["output_field_units"]
    assert units["air"].keys() == result["outputs"]["air"].keys()
    assert units["air"]["state"].keys() == result["outputs"]["air"]["state"].keys()
    assert catalog["trace_field_units"] == inverse.tabulated_hover_thrust_target_catalog()["trace_field_units"]
    for row in result["outputs"]["rotors"]:
        actual = row["actual_target_result"]
        assert units["rotors"]["actual_target_request"] == inverse.tabulated_hover_thrust_target_catalog()["input_units"]
        assert units["rotors"]["actual_target_result"].keys() == {"outputs"}
        expected = deepcopy(actual["output_units"])
        expected["actual_forward_result"] = {"outputs": actual["outputs"]["actual_forward_result"]["output_units"]}
        assert units["rotors"]["actual_target_result"]["outputs"] == expected


@pytest.mark.parametrize("case", ["gravity_overflow", "arm_overflow", "cross_overflow", "subnormal", "zero_underflow"])
def test_actual_load_arithmetic_failure_preserves_guarded_counts(monkeypatch, case):
    supplied = request()
    rotor = supplied["rotors"][0]
    if case == "gravity_overflow":
        supplied["mass_kg"] = sys.float_info.max
    elif case == "arm_overflow":
        rotor["center_body_m"][0], supplied["cg_body_m"][0] = sys.float_info.max, -sys.float_info.max
    elif case == "cross_overflow":
        rotor["center_body_m"][0] = sys.float_info.max
    else:
        rotor.update(center_body_m=[0.0, sys.float_info.min, 0.0],
                     axis_body=[1e-8 if case == "subnormal" else 1e-200, 0.0, 1.0])
    _, _, direct = baseline(supplied)
    calls = spies(monkeypatch)
    guarded = 2 if case == "gravity_overflow" else 1
    count = sum(r["evaluation_count"] for r in direct[:guarded])
    assert_atomic(workflow.evaluate_tabulated_thrust_target_assembly(supplied), "EXECUTION_FAILED", guarded, count, supplied)
    assert [c.call_count for c in calls] == [1, guarded, count, count, guarded]
