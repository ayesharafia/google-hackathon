"""Read-only JSON adapter for the experimental isolated-hover BEMT solver."""

from dataclasses import asdict

from .hover_bemt import solve_hover

_PHYSICAL_KEYS = (
    "radius_m", "angular_speed_rad_s", "density_kg_m3", "blade_count",
    "chord_m", "lift_curve_slope_per_rad", "profile_drag_coefficient",
    "pitch_tip_rad", "root_cutout_fraction", "twist_law", "annuli",
    "pitch_root_rad",
)
_DECLARATIONS = ("property_source", "applicability_declaration")
_REQUEST_KEYS = frozenset(_PHYSICAL_KEYS + _DECLARATIONS + ("evaluation",))
_SOURCES = (
    "https://sankar.gatech.edu/AE6070/Combined.BE.Momentum.Theory.doc",
    "https://kumar-sumeet.github.io/HeliAeroNotes/Lectures/2_BET/2_BEMT.html",
)
_LIMITATIONS = (
    "Experimental isolated-hover, small-angle, attached linear-lift model.",
    "Small-angle applicability and a physical operating envelope are not established.",
    ("Numerical guards and balance diagnostics do not certify an angle envelope "
    "or establish physical validation."),
    ("Property sources and applicability declarations are unverified literal text; "
    "neither establishes validation or promotes the evidence level."),
    "No rotor loss factors or swirl are modeled.",
    "No stall, Reynolds-dependent polars, or compressibility are modeled.",
    "No non-hover flight, ground effects, or rotor/aircraft interference are modeled.",
    "No aircraft strength or structural qualification is established.",
    "No electrical efficiency is modeled; shaft power is not electrical input power.",
    "Results do not establish aircraft status or feasibility.",
)
_OUTPUT_UNITS = {
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


def _response(status, reasons):
    return {
        "model_id": "isolated_hover_small_angle_bemt_v1",
        "status": status,
        "physical_validation": "NOT_ESTABLISHED",
        "evidence_level": "unverified",
        "aircraft_status": None,
        "feasibility": None,
        "reasons": list(reasons),
        "limitations": list(_LIMITATIONS),
        "sources": list(_SOURCES),
        "outputs": {},
        "output_units": {},
    }


def evaluate_hover_bemt(request):
    """Evaluate one explicit request without changing inputs or qualifying physics."""
    if type(request) is not dict or request.keys() != _REQUEST_KEYS:
        return _response("MODEL_INAPPLICABLE", ["Request must have the exact required keys."])
    if (type(request["evaluation"]) is not str
            or request["evaluation"] != "isolated_hover_bemt_experimental"):
        return _response("SOLVER_UNSUPPORTED", ["Unsupported evaluation."])
    for name in _DECLARATIONS:
        value = request[name]
        if type(value) is not str or not value.strip() or len(value) > 2000:
            return _response("MODEL_INAPPLICABLE", [
                "Declarations must be nonblank builtin strings of at most 2000 characters."
            ])
    try:
        solution = solve_hover(**{name: request[name] for name in _PHYSICAL_KEYS})
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return _response("MODEL_INAPPLICABLE", [
            "Request is outside the core solver's supported input or numerical domain."
        ])
    outputs = asdict(solution)
    status = outputs.pop("status")
    outputs.pop("physical_validation")
    response = _response(status, [])
    response["outputs"] = {
        name: list(value) if isinstance(value, tuple) else value
        for name, value in outputs.items()
    }
    response["output_units"] = dict(_OUTPUT_UNITS)
    return response
