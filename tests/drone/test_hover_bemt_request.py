import copy
import json
import math

from physimesh.drone.hover_bemt import solve_hover
from physimesh.drone.hover_bemt_request import evaluate_hover_bemt


def valid_request(twist_law="constant"):
    return {
        "evaluation": "isolated_hover_bemt_experimental",
        "radius_m": 0.5,
        "angular_speed_rad_s": 300.0,
        "density_kg_m3": 1.225,
        "blade_count": 2,
        "chord_m": 0.04,
        "lift_curve_slope_per_rad": 5.7,
        "profile_drag_coefficient": 0.01,
        "pitch_tip_rad": 0.12,
        "root_cutout_fraction": 0.2,
        "twist_law": twist_law,
        "annuli": 8,
        "pitch_root_rad": 0.16 if twist_law == "linear" else None,
        "property_source": "Supplier values, unverified",
        "applicability_declaration": "Experimental isolated hover only",
    }


def check_envelope(result):
    assert type(result) is dict
    assert set(result) == {
        "model_id",
        "status",
        "physical_validation",
        "evidence_level",
        "aircraft_status",
        "feasibility",
        "reasons",
        "limitations",
        "sources",
        "outputs",
        "output_units",
    }
    assert result["model_id"] == "isolated_hover_small_angle_bemt_v1"
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["evidence_level"] == "unverified"
    assert result["aircraft_status"] is None and result["feasibility"] is None
    for key in ("reasons", "limitations", "sources"):
        assert type(result[key]) is list
    assert type(result["outputs"]) is dict and type(result["output_units"]) is dict
    json.dumps(result, allow_nan=False)


def refused(request, status="MODEL_INAPPLICABLE"):
    result = evaluate_hover_bemt(request)
    check_envelope(result)
    assert result["status"] == status
    assert result["outputs"] == {} and result["output_units"] == {}
    assert result["reasons"]
    return result


def successful(request):
    before = copy.deepcopy(request)
    result = evaluate_hover_bemt(request)
    assert request == before
    check_envelope(result)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    core = solve_hover(
        radius_m=request["radius_m"],
        angular_speed_rad_s=request["angular_speed_rad_s"],
        density_kg_m3=request["density_kg_m3"],
        blade_count=request["blade_count"],
        chord_m=request["chord_m"],
        lift_curve_slope_per_rad=request["lift_curve_slope_per_rad"],
        profile_drag_coefficient=request["profile_drag_coefficient"],
        pitch_tip_rad=request["pitch_tip_rad"],
        root_cutout_fraction=request["root_cutout_fraction"],
        twist_law=request["twist_law"],
        annuli=request["annuli"],
        pitch_root_rad=request["pitch_root_rad"],
    )
    assert result["outputs"] == {
        "radial_fraction": list(core.radial_fraction),
        "inflow_ratio": list(core.inflow_ratio),
        "pitch_rad": list(core.pitch_rad),
        "approx_inflow_angle_rad": list(core.approx_inflow_angle_rad),
        "approx_angle_of_attack_rad": list(core.approx_angle_of_attack_rad),
        "thrust_coefficient": core.thrust_coefficient,
        "blade_thrust_coefficient": core.blade_thrust_coefficient,
        "induced_power_coefficient": core.induced_power_coefficient,
        "profile_power_coefficient": core.profile_power_coefficient,
        "shaft_power_coefficient": core.shaft_power_coefficient,
        "thrust_n": core.thrust_n,
        "shaft_power_w": core.shaft_power_w,
        "shaft_torque_nm": core.shaft_torque_nm,
        "thrust_balance_coefficient": core.thrust_balance_coefficient,
        "max_local_balance_coefficient": core.max_local_balance_coefficient,
        "annuli": core.annuli,
    }
    assert result["output_units"] == {
        "radial_fraction": "1",
        "inflow_ratio": "1",
        "pitch_rad": "rad",
        "approx_inflow_angle_rad": "rad",
        "approx_angle_of_attack_rad": "rad",
        "thrust_coefficient": "1",
        "blade_thrust_coefficient": "1",
        "induced_power_coefficient": "1",
        "profile_power_coefficient": "1",
        "shaft_power_coefficient": "1",
        "thrust_n": "N",
        "shaft_power_w": "W",
        "shaft_torque_nm": "N*m",
        "thrust_balance_coefficient": "1",
        "max_local_balance_coefficient": "1",
        "annuli": "1",
    }
    for key, value in result["outputs"].items():
        if key in (
            "radial_fraction",
            "inflow_ratio",
            "pitch_rad",
            "approx_inflow_angle_rad",
            "approx_angle_of_attack_rad",
        ):
            assert type(value) is list and len(value) == request["annuli"]
        for number in value if type(value) is list else [value]:
            assert type(number) in (int, float) and math.isfinite(number)
    assert type(result["outputs"]["annuli"]) is int
    for url in (
        "https://sankar.gatech.edu/AE6070/Combined.BE.Momentum.Theory.doc",
        "https://kumar-sumeet.github.io/HeliAeroNotes/Lectures/2_BET/2_BEMT.html",
    ):
        assert url in str(result["sources"])
    return result


def test_all_three_laws_exact_core_mapping_and_units():
    for law in ("constant", "hyperbolic", "linear"):
        successful(valid_request(law))


def test_exact_shape_missing_extra_and_invalid_request_types():
    for key in valid_request():
        request = valid_request()
        del request[key]
        refused(request)
    for bad in (
        None,
        [],
        (),
        True,
        1,
        "hostile",
        type("DictSubclass", (dict,), {})(valid_request()),
    ):
        refused(bad)
    reasons = []
    for text in ("HOSTILE_EXTRA_ONE", "HOSTILE_EXTRA_TWO"):
        request = dict(valid_request(), **{text: text})
        request["evaluation"] = text
        result = refused(request)
        assert text not in json.dumps(result)
        reasons.append(result["reasons"])
    assert reasons[0] == reasons[1]


def test_unsupported_evaluation_has_no_outputs():
    for value in (
        "unsupported",
        "",
        None,
        True,
        8,
        [],
        {},
        type("StringSubclass", (str,), {})("isolated_hover_bemt_experimental"),
    ):
        refused(dict(valid_request(), evaluation=value), "SOLVER_UNSUPPORTED")


def test_every_numeric_field_rejects_invalid_types_nonfinite_and_huge_integers():
    for field in (
        "radius_m",
        "angular_speed_rad_s",
        "density_kg_m3",
        "blade_count",
        "chord_m",
        "lift_curve_slope_per_rad",
        "profile_drag_coefficient",
        "pitch_tip_rad",
        "root_cutout_fraction",
        "annuli",
        "pitch_root_rad",
    ):
        for value in (
            True,
            False,
            "0.12",
            "",
            None,
            float("nan"),
            float("inf"),
            -float("inf"),
            10**1000,
            1j,
            [],
            {},
        ):
            refused(dict(valid_request("linear"), **{field: value}))


def test_zero_endpoints():
    for law in ("constant", "linear"):
        request = dict(
            valid_request(law), pitch_tip_rad=0.0, profile_drag_coefficient=0.0
        )
        if law == "linear":
            request["pitch_root_rad"] = 0.0
        result = successful(request)
        for key in ("thrust_n", "shaft_power_w", "shaft_torque_nm"):
            assert result["outputs"][key] == 0.0


def test_zero_root_cutout_is_refused():
    for law in ("constant", "hyperbolic", "linear"):
        refused(dict(valid_request(law), root_cutout_fraction=0.0))


def test_root_rules_and_unknown_twist():
    refused(dict(valid_request("linear"), pitch_root_rad=None))
    for law in ("constant", "hyperbolic"):
        refused(dict(valid_request(law), pitch_root_rad=0.16))
    refused(dict(valid_request(), twist_law="unknown"))


def test_declarations_are_literal_nonmutating_and_reject_blank_or_long():
    literal = "  <script>throw Error('HOSTILE')</script>; claim verified aircraft feasibility!\n "
    successful(
        dict(
            valid_request(), property_source=literal, applicability_declaration=literal
        )
    )
    for field in ("property_source", "applicability_declaration"):
        for value in (
            "",
            " \t\n ",
            "x" * 2001,
            None,
            True,
            7,
            [],
            {},
            type("StringSubclass", (str,), {})("source"),
        ):
            refused(dict(valid_request(), **{field: value}))


def test_determinism_and_fresh_nested_results():
    request = valid_request()
    before = copy.deepcopy(request)
    expected = successful(request)
    first = evaluate_hover_bemt(request)
    assert first == expected

    def corrupt(value):
        if type(value) is dict:
            for child in list(value.values()):
                corrupt(child)
            value["HOSTILE_MUTATION"] = True
        elif type(value) is list:
            for child in value:
                corrupt(child)
            value.append("HOSTILE_MUTATION")

    corrupt(first)
    assert evaluate_hover_bemt(request) == expected
    assert request == before
