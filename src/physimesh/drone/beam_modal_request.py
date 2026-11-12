"""Closed stateless adapter for the accepted uniform cantilever modal core."""

from copy import deepcopy

from .beam_fem_variable_request import _finite_number
from .beam_modal import _LIMITS, solve_cantilever_modes

EVALUATION = "uniform_cantilever_modal_experimental"
MODEL_ID = "uniform_cantilever_modal_v1"
SCHEMA_VERSION = "beam_modal_request_v1"
_SCALARS = ("length_m", "E_pa", "I_m4", "mass_per_length_kg_m")
_COUNTS = ("elements", "modes")
_DECLARATIONS = ("property_source", "applicability_declaration")
_KEYS = ("evaluation", *_SCALARS, *_COUNTS, *_DECLARATIONS)
_INPUT_UNITS = dict(zip(_SCALARS, ("m", "Pa", "m^4", "kg/m"), strict=True))
_MODE_UNITS = {
    "mode_index": "1", "eigenvalue_dimensionless": "1", "omega_rad_s": "rad/s",
    "frequency_hz": "Hz", "xi": "1", "normalized_deflection": "1",
    "normalized_deflection_derivative_xi": "1",
}
_LIMITATIONS = (
    "Research only: uniform undamped Euler-Bernoulli beam, ideal cantilever, small linear vibration.",
    "No rotation, prestress, damping, aeroelasticity, shear deformation, rotary inertia or tip mass.",
    "Declarations and property sources are unverified text, not validation or evidence.",
    "Numerical diagnostics establish no mesh, frequency or physical error bound.",
    ("Tip-normalized deflection w/w_tip and its derivative with respect to xi imply no amplitude; "
    "the derivative is not physical rotation."),
    "No aircraft support, feasibility, resonance clearance, strength or airworthiness is established.",
)


def _response(status, reasons):
    return {
        "schema_version": SCHEMA_VERSION, "model_id": MODEL_ID, "status": status,
        "physical_validation": "NOT_ESTABLISHED", "numerical_qualification": "NOT_ESTABLISHED",
        "mesh_accuracy": "NOT_ESTABLISHED", "evidence_level": "unverified",
        "aircraft_status": None, "feasibility": None, "reasons": list(reasons),
        "limitations": list(_LIMITATIONS), "limits": deepcopy(_LIMITS),
        "outputs": {}, "output_units": {},
    }


def beam_modal_catalog():
    """Return fresh metadata, including nested limits; never expose shared mutable data."""
    return {
        **_response("RESEARCH_ONLY", []), "evaluation": EVALUATION,
        "required_fields": list(_KEYS), "input_units": {**_INPUT_UNITS, "elements": "1", "modes": "1"},
        "request_contract": {
            "extra_fields": "forbidden", "defaults": {},
            "physical_scalars": "exact builtin int/float; finite positive normal binary64; core validated",
            "counts": "exact builtin int; elements 2..64; modes 1..min(6, 2*elements)",
            "declarations": "required nonblank strings, at most 2000 characters; unverified",
        },
        "mode_units": dict(_MODE_UNITS),
    }


def evaluate_modal_beam(request):
    """Require the entire explicit request and preserve the core's all-or-nothing result."""
    def refuse():
        return _response("MODEL_INAPPLICABLE", ["Invalid uniform modal beam request."])

    if type(request) is not dict or request.keys() != set(_KEYS):
        return refuse()
    if type(request["evaluation"]) is not str:
        return refuse()
    if request["evaluation"] != EVALUATION:
        return _response("SOLVER_UNSUPPORTED", ["Unsupported evaluation."])
    for name in _DECLARATIONS:
        value = request[name]
        if type(value) is not str or not value.strip() or len(value) > 2000:
            return refuse()
    if any(not _finite_number(request[name]) for name in _SCALARS):
        return refuse()
    if any(type(request[name]) is not int or not _finite_number(request[name]) for name in _COUNTS):
        return refuse()
    core = solve_cantilever_modes(**{name: request[name] for name in (*_SCALARS, *_COUNTS)})
    result = _response("COMPUTED_EXPERIMENTAL" if core["status"] == "SUCCESS"
                       else "MODEL_INAPPLICABLE", [])
    result["limits"] = deepcopy(core["limits"])
    if core["status"] != "SUCCESS":
        result["core_refusal"] = deepcopy(core["refusal"])
        result["reasons"] = [core["refusal"]["code"]]
        return result
    result["outputs"] = {key: deepcopy(core[key]) for key in ("inputs", "modes", "diagnostics")}
    result["output_units"] = {
        "inputs": {**_INPUT_UNITS, "elements": "1", "modes": "1"},
        "modes": dict(_MODE_UNITS),
        "diagnostics": {key: "rad/s" if key == "frequency_scale_rad_s" else "1"
                        for key in core["diagnostics"]},
    }
    return result
