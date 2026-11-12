"""Numerical verification of the tabulated closure; no physical qualification."""

import math
import sys
from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext
from itertools import pairwise

import pytest

from physimesh.drone.hover_bemt import solve_hover
from physimesh.drone.tabulated_hover_bemt import solve_tabulated_hover


def inputs(**overrides):
    """Fresh SI request, including fresh station dictionaries for every call."""
    return {
        "radius_m": 1.0,
        "angular_speed_rad_s": 100.0,
        "density_kg_m3": 1.225,
        "blade_count": 2,
        "root_cutout_m": 0.25,
        "annuli": 24,
        "lift_curve_slope_per_rad": 5.7,
        "profile_drag_coefficient": 0.01,
        "stations": [
            {"radius_m": 0.0, "chord_m": 0.04, "blade_angle_rad": 0.10},
            {"radius_m": 0.625, "chord_m": 0.08, "blade_angle_rad": 0.04},
            {"radius_m": 1.0, "chord_m": 0.02, "blade_angle_rad": 0.08},
        ],
        "geometry_source": "synthetic numerical fixture, revision 1; true SI radius",
        "geometry_kind": "synthetic",
        "uncertainty_status": "unknown; numerical verification only",
        **overrides,
    }


def decimal_oracle(request):
    """Independent 80-digit interpolation, quadratic root, loads and SI scales.

    Use the direct positive quadratic root, unlike the kernel's rationalized
    expression. Decimal inputs preserve the exact binary input values; pi is
    supplied independently at higher precision than binary64.
    """
    with localcontext() as context:
        context.prec = 80
        d = Decimal
        pi = d("3.141592653589793238462643383279502884197169399375105820974944592307816406286208998")
        radius, cutout = d(request["radius_m"]), d(request["root_cutout_m"])
        omega, density = d(request["angular_speed_rad_s"]), d(request["density_kg_m3"])
        slope, drag = d(request["lift_curve_slope_per_rad"]), d(request["profile_drag_coefficient"])
        stations = [tuple(d(s[key]) for key in ("radius_m", "chord_m", "blade_angle_rad"))
                    for s in request["stations"]]
        step = (radius - cutout) / request["annuli"]
        rows = []
        totals = [d(0)] * 4
        for index in range(request["annuli"]):
            radial = cutout + (d(index) + d("0.5")) * step
            left, right = next((left, right) for left, right in pairwise(stations)
                               if left[0] <= radial <= right[0])
            weight = (radial - left[0]) / (right[0] - left[0])
            chord = left[1] + (right[1] - left[1]) * weight
            theta = left[2] + (right[2] - left[2]) * weight
            x = radial / radius
            sigma = request["blade_count"] * chord / (pi * radius)
            q = sigma * slope / 8
            inflow = ((q * q + 4 * q * theta * x).sqrt() - q) / 2
            phi = inflow / x
            momentum = 4 * inflow**2 * x
            blade = sigma * slope / 2 * (theta * x**2 - inflow * x)
            induced = 4 * inflow**3 * x
            profile = sigma * drag / 2 * x**3
            rows.append(tuple(float(v) for v in
                              (radial, x, chord, theta, sigma, inflow, phi, theta - phi, momentum)))
            for slot, term in enumerate((momentum, blade, induced, profile)):
                totals[slot] += term * step / radius
        ct, ctb, cpi, cp0 = totals
        cp = cpi + cp0
        thrust = density * pi * radius**2 * (omega * radius)**2 * ct
        power = density * pi * radius**2 * (omega * radius)**3 * cp
        return rows, tuple(float(v) for v in (ct, ctb, cpi, cp0, cp, thrust, power, power / omega))


@pytest.mark.parametrize("annuli", [1, 7, 64, 2048])
@pytest.mark.parametrize("radius,density,omega", [(0.125, 0.8, 170.0), (1.0, 1.225, 100.0), (3.7, 2.4, 34.0)])
@pytest.mark.parametrize("law", ["constant", "linear"])
def test_constant_chord_reductions(annuli, radius, density, omega, law):
    cutout, chord = 0.2 * radius, 0.05 * radius
    root, tip = (0.08, 0.08) if law == "constant" else (0.11, 0.04)
    request = inputs(radius_m=radius, density_kg_m3=density, angular_speed_rad_s=omega,
                     root_cutout_m=cutout, annuli=annuli, stations=[
                         {"radius_m": cutout, "chord_m": chord, "blade_angle_rad": root},
                         {"radius_m": radius, "chord_m": chord, "blade_angle_rad": tip},
                     ])
    result = solve_tabulated_hover(**request)
    accepted = solve_hover(
        radius_m=radius, angular_speed_rad_s=omega, density_kg_m3=density,
        blade_count=2, chord_m=chord, lift_curve_slope_per_rad=5.7,
        profile_drag_coefficient=0.01, pitch_tip_rad=tip, root_cutout_fraction=0.2,
        twist_law=law, annuli=annuli, **({"pitch_root_rad": root} if law == "linear" else {}),
    )
    for field in ("radial_fraction", "inflow_ratio", "approx_inflow_angle_rad",
                  "approx_angle_of_attack_rad", "thrust_coefficient", "blade_thrust_coefficient",
                  "induced_power_coefficient", "profile_power_coefficient", "shaft_power_coefficient",
                  "thrust_n", "shaft_power_w", "shaft_torque_nm"):
        assert getattr(result, field) == pytest.approx(getattr(accepted, field), rel=4e-13, abs=1e-16)
    assert result.blade_angle_rad == pytest.approx(accepted.pitch_rad, rel=4e-13)


@pytest.mark.parametrize("annuli", [1, 3, 17, 96])
def test_variable_geometry_against_independent_decimal_equations(annuli):
    request = inputs(annuli=annuli)
    result = solve_tabulated_hover(**request)
    rows, totals = decimal_oracle(request)
    arrays = (result.radii_m, result.radial_fraction, result.chord_m, result.blade_angle_rad,
              result.local_solidity, result.inflow_ratio, result.approx_inflow_angle_rad,
              result.approx_angle_of_attack_rad)
    for column, actual in enumerate(arrays):
        assert actual == pytest.approx([row[column] for row in rows], rel=4e-13, abs=0)
    actual_totals = (result.thrust_coefficient, result.blade_thrust_coefficient,
                     result.induced_power_coefficient, result.profile_power_coefficient,
                     result.shaft_power_coefficient, result.thrust_n,
                     result.shaft_power_w, result.shaft_torque_nm)
    assert actual_totals == pytest.approx(totals, rel=4e-13, abs=0)
    for balance, row in zip(result.local_balance_coefficient, rows):
        assert abs(balance) <= 4e-13 * row[8]
    assert abs(result.thrust_balance_coefficient) <= 4e-13 * totals[0]
    assert result.max_local_balance_coefficient == max(map(abs, result.local_balance_coefficient))


def exact_profile_integral(request):
    """Integrate each affine chord segment times x**3 analytically."""
    with localcontext() as context:
        context.prec = 80
        d = Decimal
        radius, cutout = d(request["radius_m"]), d(request["root_cutout_m"])
        integral = d(0)
        for left, right in pairwise(request["stations"]):
            r0, r1 = d(left["radius_m"]), d(right["radius_m"])
            lower, upper = max(r0, cutout), min(r1, radius)
            if lower >= upper:
                continue
            slope = (d(right["chord_m"]) - d(left["chord_m"])) / (r1 - r0)
            intercept = d(left["chord_m"]) - slope * r0
            integral += (intercept * (upper**4 - lower**4) / 4
                         + slope * (upper**5 - lower**5) / 5) / radius**4
        pi = d("3.141592653589793238462643383279502884197169399375105820974944592307816406286208998")
        return float(request["blade_count"] * d(request["profile_drag_coefficient"])
                     / (2 * pi * radius) * integral)


@pytest.mark.parametrize("drag", [0.0, 0.01])
def test_zero_angle_profile_integral_and_midpoint_convergence(drag):
    request = inputs(profile_drag_coefficient=drag)
    for station in request["stations"]:
        station["blade_angle_rad"] = 0.0
    exact = exact_profile_integral(request)
    errors = []
    for annuli in (8, 16, 32, 64):
        result = solve_tabulated_hover(**{**request, "annuli": annuli})
        assert result.thrust_coefficient == result.blade_thrust_coefficient == result.thrust_n == 0
        assert result.induced_power_coefficient == 0
        assert result.inflow_ratio == result.approx_angle_of_attack_rad == (0.0,) * annuli
        assert result.local_balance_coefficient == (0.0,) * annuli
        assert result.thrust_balance_coefficient == result.max_local_balance_coefficient == 0
        assert result.shaft_power_coefficient == result.profile_power_coefficient
        if drag == 0:
            assert result.shaft_power_w == result.shaft_torque_nm == result.profile_power_coefficient == 0
        else:
            assert result.shaft_power_w > 0
            errors.append(abs(result.profile_power_coefficient - exact))
    if errors:
        assert all(coarse > fine > 0 for coarse, fine in pairwise(errors))
        for coarse, fine in pairwise(errors):
            assert coarse / fine == pytest.approx(4, rel=0.03)


@pytest.mark.parametrize("density_factor,omega_factor,length_factor", [(2.3, 1, 1), (1, 1.7, 1), (1, 1, 2.5)])
def test_dimensional_scaling(density_factor, omega_factor, length_factor):
    request = inputs()
    base = solve_tabulated_hover(**request)
    request["density_kg_m3"] *= density_factor
    request["angular_speed_rad_s"] *= omega_factor
    request["radius_m"] *= length_factor
    request["root_cutout_m"] *= length_factor
    for station in request["stations"]:
        station["radius_m"] *= length_factor
        station["chord_m"] *= length_factor
    scaled = solve_tabulated_hover(**request)
    for field in ("thrust_coefficient", "blade_thrust_coefficient", "induced_power_coefficient",
                  "profile_power_coefficient", "shaft_power_coefficient", "inflow_ratio", "local_solidity"):
        assert getattr(scaled, field) == pytest.approx(getattr(base, field), rel=4e-13)
    assert scaled.thrust_n == pytest.approx(base.thrust_n * density_factor * omega_factor**2 * length_factor**4)
    assert scaled.shaft_power_w == pytest.approx(
        base.shaft_power_w * density_factor * omega_factor**3 * length_factor**5)
    assert scaled.shaft_torque_nm == pytest.approx(
        base.shaft_torque_nm * density_factor * omega_factor**2 * length_factor**5)
    assert scaled.radii_m == pytest.approx([r * length_factor for r in base.radii_m])
    assert scaled.chord_m == pytest.approx([c * length_factor for c in base.chord_m])


def test_exact_knot_and_active_interval_endpoints():
    result = solve_tabulated_hover(**inputs(annuli=3))
    assert result.radii_m == (0.375, 0.625, 0.875)
    assert result.chord_m[1] == 0.08
    assert result.blade_angle_rad[1] == 0.04
    assert all(r > 0.25 for r in result.radii_m)  # Station at zero creates no hub annulus.
    request = inputs(annuli=3)
    request["stations"][0]["radius_m"] = request["root_cutout_m"]
    covered = solve_tabulated_hover(**request)
    assert covered.stations[0].radius_m == covered.root_cutout_m
    assert covered.stations[-1].radius_m == covered.radius_m
    assert covered.radii_m == result.radii_m


def test_immutable_output_and_input_copy_isolation():
    request = inputs()
    result = solve_tabulated_hover(**request)
    assert result.model == "tabulated_geometry_hover_experimental"
    assert result.version == "0.1"
    assert result.status == "COMPUTED_EXPERIMENTAL"
    assert result.physical_validation == "NOT_ESTABLISHED"
    snapshot = result.stations
    geometry = (result.radii_m, result.chord_m, result.blade_angle_rad)
    request["stations"][0]["chord_m"] = 99
    request["stations"].clear()
    assert result.stations == snapshot
    assert result.stations[0].chord_m == 0.04
    assert (result.radii_m, result.chord_m, result.blade_angle_rad) == geometry
    with pytest.raises(FrozenInstanceError):
        result.thrust_n = 0
    with pytest.raises(FrozenInstanceError):
        result.stations[0].chord_m = 0
    with pytest.raises(TypeError):
        result.chord_m[0] = 0


class CustomFloat(float):
    pass


class CustomInt(int):
    pass


class CustomList(list):
    pass


class CustomDict(dict):
    pass


class CustomStr(str):
    pass


SCALAR_FIELDS = (
    "radius_m", "angular_speed_rad_s", "density_kg_m3", "root_cutout_m",
    "lift_curve_slope_per_rad", "profile_drag_coefficient",
)
BAD_NUMBERS = [
    True, False, None, "1", Decimal(1), CustomFloat(1), CustomInt(1),
    -1.0, math.nan, math.inf, -math.inf, math.ulp(0.0), 10**400,
]
BAD_NUMBER_IDS = [
    "true", "false", "none", "string", "decimal", "float-subclass", "int-subclass",
    "negative", "nan", "positive-inf", "negative-inf", "subnormal", "int-overflow",
]


@pytest.mark.parametrize("field", SCALAR_FIELDS)
@pytest.mark.parametrize("value", BAD_NUMBERS, ids=BAD_NUMBER_IDS)
def test_rejects_unsupported_scalar_numbers(field, value):
    with pytest.raises(ValueError):
        solve_tabulated_hover(**inputs(**{field: value}))


@pytest.mark.parametrize("field", SCALAR_FIELDS[:-1])
def test_positive_scalar_fields_reject_zero(field):
    with pytest.raises(ValueError):
        solve_tabulated_hover(**inputs(**{field: 0}))


@pytest.mark.parametrize("field,maximum", [("annuli", 2048), ("blade_count", 32)])
@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, CustomInt(1), "1", None])
def test_integer_fields_are_strict_builtin_ints(field, maximum, value):
    with pytest.raises(ValueError):
        solve_tabulated_hover(**inputs(**{field: value}))


@pytest.mark.parametrize("field,maximum", [("annuli", 2048), ("blade_count", 32)])
def test_rejects_integer_work_limit_excess(field, maximum):
    with pytest.raises(ValueError, match=f"1..{maximum}"):
        solve_tabulated_hover(**inputs(**{field: maximum + 1}))


@pytest.mark.parametrize("field", ["radius_m", "chord_m", "blade_angle_rad"])
@pytest.mark.parametrize("value", BAD_NUMBERS, ids=BAD_NUMBER_IDS)
def test_rejects_unsupported_station_numbers(field, value):
    request = inputs()
    request["stations"][0][field] = value
    with pytest.raises(ValueError):
        solve_tabulated_hover(**request)


@pytest.mark.parametrize("field,value", [("chord_m", 0), ("chord_m", -0.0), ("blade_angle_rad", -0.01)])
def test_station_chord_positive_and_angle_nonnegative(field, value):
    request = inputs()
    request["stations"][1][field] = value
    with pytest.raises(ValueError):
        solve_tabulated_hover(**request)


@pytest.mark.parametrize("container", [tuple, CustomList, dict])
def test_station_list_requires_exact_builtin_type(container):
    request = inputs()
    request["stations"] = container(enumerate(request["stations"])) if container is dict else container(
        request["stations"])
    with pytest.raises(ValueError, match="builtin list"):
        solve_tabulated_hover(**request)


@pytest.mark.parametrize("change", ["custom-dict", "custom-str-key", "integer-key", "missing", "extra"])
def test_station_dict_and_keys_are_exact(change):
    request = inputs()
    station = request["stations"][0]
    if change == "custom-dict":
        request["stations"][0] = CustomDict(station)
    elif change == "custom-str-key":
        value = station.pop("radius_m")
        station[CustomStr("radius_m")] = value
    elif change == "integer-key":
        station[0] = station.pop("radius_m")
    elif change == "missing":
        del station["chord_m"]
    else:
        station["airfoil"] = "unspecified"
    with pytest.raises(ValueError, match="builtin dict"):
        solve_tabulated_hover(**request)


@pytest.mark.parametrize("count", [0, 1, 257])
def test_station_count_bounds(count):
    stations = [{"radius_m": index / max(1, count - 1), "chord_m": 0.05, "blade_angle_rad": 0.08}
                for index in range(count)]
    with pytest.raises(ValueError, match="2..256"):
        solve_tabulated_hover(**inputs(stations=stations))


@pytest.mark.parametrize("station_count,annuli,blades", [(2, 1, 1), (256, 2048, 32)])
def test_supported_work_limit_boundaries(station_count, annuli, blades):
    stations = [{"radius_m": index / (station_count - 1), "chord_m": 0.05, "blade_angle_rad": 0.08}
                for index in range(station_count)]
    result = solve_tabulated_hover(**inputs(stations=stations, annuli=annuli, blade_count=blades))
    assert len(result.stations) == station_count
    assert len(result.radii_m) == result.annuli == annuli
    assert result.local_solidity == pytest.approx([blades * 0.05 / math.pi] * annuli, rel=1e-14)


@pytest.mark.parametrize("radii", [
    [math.nextafter(0.25, math.inf), 1.0],  # Even one ULP of uncovered root is rejected.
    [0.0, math.nextafter(1.0, 0.0)],
    [0.0, math.nextafter(1.0, math.inf)],
    [-0.01, 1.0], [0.0, 0.0, 1.0], [0.0, 0.8, 0.5, 1.0],
])
def test_exact_coverage_and_strict_monotonicity(radii):
    stations = [{"radius_m": r, "chord_m": 0.05, "blade_angle_rad": 0.08} for r in radii]
    with pytest.raises(ValueError):
        solve_tabulated_hover(**inputs(stations=stations))


@pytest.mark.parametrize("cutout", [0, -0.1, 1.0, math.nextafter(1.0, math.inf)])
def test_cutout_strictly_inside_rotor(cutout):
    with pytest.raises(ValueError):
        solve_tabulated_hover(**inputs(root_cutout_m=cutout))


@pytest.mark.parametrize("field", ["geometry_source", "uncertainty_status"])
@pytest.mark.parametrize("value", [None, True, 1, "", " \t\n", "x" * 2001, CustomStr("source"),
                                  "\ud800", "\ud83d\ude00"])
def test_provenance_requires_bounded_nonblank_utf8_builtin_text(field, value):
    with pytest.raises(ValueError):
        solve_tabulated_hover(**inputs(**{field: value}))


@pytest.mark.parametrize("kind", ["measured", "digitized_measurement", "as_designed", "synthetic"])
def test_provenance_records_caller_assertions_without_normalizing(kind):
    source = "  révision 🛠; true radius  "
    result = solve_tabulated_hover(**inputs(geometry_kind=kind, geometry_source=source,
                                           uncertainty_status="u" * 2000))
    assert result.geometry_kind == kind
    assert result.geometry_source == source
    assert len(result.uncertainty_status) == 2000
    assert result.physical_validation == "NOT_ESTABLISHED"


@pytest.mark.parametrize("kind", [None, True, "Measured", "unknown", CustomStr("synthetic")])
def test_geometry_kind_is_strict(kind):
    with pytest.raises(ValueError):
        solve_tabulated_hover(**inputs(geometry_kind=kind))


def test_unknown_top_level_fields_are_rejected():
    with pytest.raises(TypeError, match="unexpected keyword"):
        solve_tabulated_hover(**inputs(airfoil="unspecified"))


@pytest.mark.parametrize("field,value", [
    ("angular_speed_rad_s", 1e200), ("angular_speed_rad_s", sys.float_info.min),
    ("density_kg_m3", 1e308), ("profile_drag_coefficient", sys.float_info.min),
])
def test_derived_overflow_and_underflow_are_rejected(field, value):
    with pytest.raises(ValueError, match="supported|finite-normal"):
        solve_tabulated_hover(**inputs(**{field: value}))


@pytest.mark.parametrize("field,value", [
    ("chord_m", 1e308), ("chord_m", sys.float_info.min),
    ("blade_angle_rad", 1e308), ("blade_angle_rad", sys.float_info.min),
])
def test_derived_station_arithmetic_extremes_are_rejected(field, value):
    request = inputs()
    for station in request["stations"]:
        station[field] = value
    with pytest.raises(ValueError, match="supported|finite-normal"):
        solve_tabulated_hover(**request)


@pytest.mark.parametrize("length_factor", [1e-200, 1e200])
def test_dimensional_area_underflow_and_overflow_rejected(length_factor):
    request = inputs(radius_m=length_factor, root_cutout_m=0.25 * length_factor)
    for station in request["stations"]:
        station["radius_m"] *= length_factor
        station["chord_m"] *= length_factor
    with pytest.raises(ValueError, match="supported|finite-normal"):
        solve_tabulated_hover(**request)


@pytest.mark.parametrize("annuli", [1, 2048])
def test_thin_annulus_collapsed_coordinates_rejected(annuli):
    with pytest.raises(ValueError, match="not distinguishable"):
        solve_tabulated_hover(**inputs(root_cutout_m=math.nextafter(1.0, 0.0), annuli=annuli))


def test_station_coordinates_collapsed_by_normalization_rejected():
    radii = [0.0, math.nextafter(1.0, 0.0), 1.0, 1.5]
    stations = [{"radius_m": r, "chord_m": 0.05, "blade_angle_rad": 0.08} for r in radii]
    with pytest.raises(ValueError, match="Normalized station radii are not distinguishable"):
        solve_tabulated_hover(**inputs(radius_m=1.5, stations=stations))


def test_excessive_load_cancellation_rejected_without_angle_threshold():
    request = inputs()
    for station in request["stations"]:
        station["blade_angle_rad"] = 1e-12
    with pytest.raises(ValueError, match="Subtractive cancellation"):
        solve_tabulated_hover(**request)
