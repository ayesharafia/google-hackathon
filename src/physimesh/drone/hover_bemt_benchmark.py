"""Mesh refinement diagnostics for the hover BEMT solver."""

from decimal import Decimal, DecimalException, localcontext
from itertools import pairwise
from math import isfinite, log2
from sys import float_info

from .hover_bemt import solve_hover

_RESULT_FIELDS = (
    "thrust_coefficient", "induced_power_coefficient",
    "profile_power_coefficient", "shaft_power_coefficient", "thrust_n",
    "shaft_power_w", "shaft_torque_nm", "thrust_balance_coefficient",
    "max_local_balance_coefficient",
)
_ROW_KEYS = (
    "CT", "CPi", "CP0", "CP", "thrust_N", "power_W", "torque_Nm",
    "thrust_balance_coefficient", "max_local_balance_coefficient",
)


def _checked(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Unsupported numeric result.") from exc
    if not isfinite(number) or (number != 0 and abs(number) < float_info.min):
        raise ValueError("Unsupported float overflow or underflow.")
    if number == 0 and value != 0:
        raise ValueError("Unsupported float underflow.")
    return number


def _absolute_difference(left, right):
    return _checked(abs(left - right))


def benchmark_refinement(
    *,
    radius_m,
    angular_speed_rad_s,
    density_kg_m3,
    blade_count,
    chord_m,
    lift_curve_slope_per_rad,
    profile_drag_coefficient,
    pitch_tip_rad,
    root_cutout_fraction,
    twist_law="constant",
    annuli_counts=(8, 16, 32, 64, 128),
):
    """Compute refinement diagnostics without establishing physical validity."""
    if (
        type(annuli_counts) is not tuple
        or not 3 <= len(annuli_counts) <= 8
        or any(type(n) is not int or not 1 <= n <= 2048 for n in annuli_counts)
        or any(fine != 2 * coarse for coarse, fine in pairwise(annuli_counts))
    ):
        raise ValueError("annuli_counts must contain 3–8 strictly doubling integers.")
    parameters = {
        "radius_m": radius_m,
        "angular_speed_rad_s": angular_speed_rad_s,
        "density_kg_m3": density_kg_m3,
        "blade_count": blade_count,
        "chord_m": chord_m,
        "lift_curve_slope_per_rad": lift_curve_slope_per_rad,
        "profile_drag_coefficient": profile_drag_coefficient,
        "pitch_tip_rad": pitch_tip_rad,
        "root_cutout_fraction": root_cutout_fraction,
        "twist_law": twist_law,
    }
    first = solve_hover(**parameters, annuli=annuli_counts[0])
    reference = {"CT": None, "CPi": None, "CP0": None}
    if twist_law == "hyperbolic":
        try:
            with localcontext() as context:
                context.prec = 80
                pi = Decimal(
                    "3.141592653589793238462643383279502884197169399375105820"
                    "9749445923078164062862090"
                )
                sig = (Decimal(str(blade_count)) * Decimal(str(chord_m))
                       / (pi * Decimal(str(radius_m))))
                a_coef = sig * Decimal(str(lift_curve_slope_per_rad)) / 8
                b = a_coef * Decimal(str(pitch_tip_rad))
                lam = (2 * b / (a_coef + (a_coef**2 + 4 * b).sqrt())
                       if b > 0 else Decimal(0))
                root = Decimal(str(root_cutout_fraction))
                reference = {
                    "CT": _checked(2 * lam**2 * (1 - root**2)),
                    "CPi": _checked(2 * lam**3 * (1 - root**2)),
                    "CP0": _checked(sig * Decimal(str(profile_drag_coefficient))
                                    / 8 * (1 - root**4)),
                }
        except (DecimalException, OverflowError) as exc:
            raise ValueError("Unsupported reference arithmetic.") from exc
    rows = []
    for index, n in enumerate(annuli_counts):
        result = first if index == 0 else solve_hover(**parameters, annuli=n)
        row = {"annuli": n}
        row.update({
            key: _checked(getattr(result, field))
            for key, field in zip(_ROW_KEYS, _RESULT_FIELDS)
        })
        previous = rows[-1] if rows else None
        for key in ("CT", "CP"):
            row[f"{key}_change"] = (
                _absolute_difference(row[key], previous[key]) if previous else None
            )
        for key, target in reference.items():
            row[f"{key}_absolute_error"] = (
                _absolute_difference(row[key], target) if target is not None else None
            )
        row.update({"CT_observed_order": None, "CPi_observed_order": None,
                    "profile_observed_order": None})
        fine = row["CP0_absolute_error"]
        coarse = previous["CP0_absolute_error"] if previous else None
        if coarse is not None and fine is not None and 0 < fine < coarse:
            row["profile_observed_order"] = _checked(log2(coarse) - log2(fine))
        rows.append(row)
    return {
        "status": "BENCHMARK_COMPUTED",
        "physical_validation": "NOT_ESTABLISHED",
        "reference_kind": ("ideal_hyperbolic_closed_form"
                           if twist_law == "hyperbolic" else "mesh_change_only"),
        "reference": reference,
        "rows": rows,
        "notes": [
            "Uniform annuli with midpoint integration; rough small-angle BEMT.",
            "Small-angle applicability: NOT_ESTABLISHED.",
            ("No qualification for tip effects, swirl, stall, Reynolds number, "
            "compressibility, ground effects, or interference."),
            ("Hyperbolic CT/CPi integrands are linear and midpoint-exact; "
            "roundoff errors do not establish convergence orders."),
            "Errors use rounded float references; cancellation to zero is allowed.",
            "No automatic dispatch or physical pass/fail assessment.",
        ],
        "source_url": "https://sankar.gatech.edu/AE6070/Combined.BE.Momentum.Theory.doc",
    }
