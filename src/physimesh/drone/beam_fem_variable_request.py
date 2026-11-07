"""Stateless request adapter for the experimental variable-inertia beam core."""

import math
from dataclasses import asdict

from .beam_fem_variable import evaluate_variable_solution, solve_beam_variable

_SCALARS = (
    "length_m", "E_pa", "outer_fibre_m", "tip_force_n", "uniform_load_n_m",
    "ramp_load_root_n_m", "ramp_load_tip_n_m", "tip_moment_n_m",
)
_ARRAYS = ("second_moments_m4", "nodes_m")
_DECLARATIONS = ("property_source", "applicability_declaration")
_KEYS = frozenset(_SCALARS + _ARRAYS + _DECLARATIONS + ("evaluation", "probes"))
_LIMITATIONS = (
    ("Experimental straight static ideal-clamped Euler-Bernoulli beam with constant E "
     "and continuous piecewise-linear nodal second moment of area."),
    "Small displacement is assumed and shear deformation is neglected.",
    "Inputs, property sources and applicability declarations are unverified; literal text is not evidence.",
    "Jump inertia is not represented.",
    "One-sided probe stress can jump at interelement boundaries; no smoothing is applied.",
    "Nominal stress does not establish strength, fatigue, buckling or aeroelastic certification.",
    "The residual measures arithmetic balance only, not mesh or physics error.",
    "No aircraft feasibility or physical validation is established.",
)
_PROBE_UNITS = {
    "element_index": "1", "local_coordinate": "1", "x_m": "m",
    "deflection_m": "m", "rotation_rad": "rad", "curvature_1_m": "1/m",
    "nominal_bending_stress_pa": "Pa",
}
_UNITS = {
    "elements": "1", "nodes_m": "m", "second_moments_m4": "m^4",
    "displacements_m": "m", "rotations_rad": "rad", "root_force_n": "N",
    "root_moment_nm": "N*m", "normalized_linear_residual": "1",
    "probes": _PROBE_UNITS,
}


def _response(status, reasons):
    return {
        "model_id": "variable_inertia_cantilever_fem_v1", "status": status,
        "physical_validation": "NOT_ESTABLISHED", "evidence_level": "unverified",
        "aircraft_status": None, "feasibility": None, "reasons": list(reasons),
        "limitations": list(_LIMITATIONS),
        "sources": ["https://ceae.colorado.edu/~regueiro/courses/CVEN4511_5511_notes.pdf"],
        "outputs": {}, "output_units": {},
    }


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    if type(value) is int and value.bit_length() > 1024:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def evaluate_variable_beam(request):
    """Evaluate all probes or return an empty refusal without changing the request."""
    def refuse():
        return _response("MODEL_INAPPLICABLE", ["Invalid or unsupported variable beam input domain."])

    if type(request) is not dict or request.keys() != _KEYS:
        return refuse()
    if type(request["evaluation"]) is not str:
        return refuse()
    if request["evaluation"] != "variable_beam_fem_experimental":
        return _response("SOLVER_UNSUPPORTED", ["Unsupported evaluation."])
    for name in _DECLARATIONS:
        value = request[name]
        if type(value) is not str or not value.strip() or len(value) > 2000:
            return refuse()
    if any(not _finite_number(request[name]) for name in _SCALARS):
        return refuse()
    for name in _ARRAYS:
        values = request[name]
        if type(values) is not list or not 2 <= len(values) <= 65:
            return refuse()
        if any(not _finite_number(value) for value in values):
            return refuse()
    probes = request["probes"]
    if type(probes) is not list or not 1 <= len(probes) <= 128:
        return refuse()
    for probe in probes:
        if type(probe) is not dict or probe.keys() != {"element_index", "local_coordinate"}:
            return refuse()
        if type(probe["element_index"]) is not int or probe["element_index"].bit_length() > 1024:
            return refuse()
        coordinate = probe["local_coordinate"]
        if not _finite_number(coordinate) or not 0 <= coordinate <= 1:
            return refuse()
    try:
        solution = solve_beam_variable(
            **{name: request[name] for name in _SCALARS},
            **{name: tuple(request[name]) for name in _ARRAYS},
        )
        points = [
            {**probe, **asdict(evaluate_variable_solution(
                solution, probe["element_index"], probe["local_coordinate"]))}
            for probe in probes
        ]
    except (ValueError, OverflowError, FloatingPointError):
        return refuse()
    response = _response("COMPUTED_EXPERIMENTAL", [])
    response["outputs"] = {
        "elements": solution.n, "nodes_m": list(solution.nodes),
        "second_moments_m4": list(solution.second_moments_m4),
        "displacements_m": list(solution.displacements), "rotations_rad": list(solution.rotations),
        "root_force_n": solution.root_force_n, "root_moment_nm": solution.root_moment_nm,
        "normalized_linear_residual": solution.normalized_linear_residual, "probes": points,
    }
    response["output_units"] = {**_UNITS, "probes": dict(_PROBE_UNITS)}
    return response
