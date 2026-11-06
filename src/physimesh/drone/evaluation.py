"""Draft PDF registry increment; reference atmosphere only.

Eight aircraft configurations are enumerated without aircraft solver support.
"""

from .standard_atmosphere import standard_atmosphere

MODEL_ID = "coesa1976.lower-atmosphere.0-30km.v1"
_CONFIGURATIONS = (
    "multirotor", "coaxial", "helicopter", "fixed_wing",
    "hybrid_vtol", "tiltrotor", "lift_plus_cruise", "custom",
)
_OUTPUTS = ("pressure_pa", "temperature_k", "density_kg_m3")
_UNITS = ("Pa", "K", "kg/m^3")
_REQUIRED = ("configuration", "evaluation", "altitude_m", "altitude_kind")
_ALLOWED = (*_REQUIRED, "outputs")
_KINDS = ("geometric", "geopotential")


def model_catalog():
    """Return fresh registry metadata for the enumerated configurations."""
    return {
        "increment": "pdf-product-v18",
        "status": "DRAFT_FIRST_REGISTRY_INCREMENT",
        "configuration_mapping_status": "CONFIGURATION_ENUMERATED_ONLY",
        "configurations": [
            {
                "id": identifier,
                "name": identifier.replace("_", " ").title().replace("Vtol", "VTOL"),
                "status": "CONFIGURATION_ENUMERATED_ONLY",
                "aircraft_solver_supported": False,
            }
            for identifier in _CONFIGURATIONS
        ],
        "models": [
            {
                "model_id": MODEL_ID,
                "version": "v1",
                "evaluation": "atmosphere",
                "adapter_path": (
                    "physimesh.drone.standard_atmosphere.standard_atmosphere"
                ),
                "status": "REFERENCE_MODEL_NOT_AIRCRAFT_VALIDATION",
                "units": {"altitude_m": "m", **dict(zip(_OUTPUTS, _UNITS))},
                "range": {
                    "altitude_m": {"minimum": 0, "maximum": 30000,
                                   "inclusive": True},
                    "altitude_kinds": list(_KINDS),
                },
                "default_outputs": list(_OUTPUTS),
                "allowed_outputs": list(_OUTPUTS),
                "limitations": [
                    "Standard dry reference air; local weather is unsupported.",
                    "No extrapolation or pressure-altitude inversion.",
                    "No aircraft feasibility, claimed tolerance or physical validation.",
                    "All other model families and aircraft solvers are unsupported.",
                ],
                "source_sha256": (
                    "e594cf50e0ce7d7e31cd07ee90a0d515c06b7c26f9de5a168ea8fe9af1ddd756"
                ),
            }
        ],
        "provenance": {
            "base_commit": "b52072dcf1ece589b57ae94a578bf5c5a8e63549",
            "A": "PHYSIMESH_Drone_Module_Complete_Development_Report.pdf",
            "A_sections": [3, 5, 12, 15],
            "B": (
                "PHYSIMESH_Physics_Driven_Equation_Engine_Technical_Development_Report.pdf"
            ),
            "B_sections": [1, 4, 6, 10, 11],
            "scope": "B M1/M2 registry and selection increment only",
        },
        "limitations": [
            "Configuration enumeration does not advertise aircraft solver support.",
            "Existing routes and sources are unchanged; no new API or UI.",
            "Full project integration and independent API/UI review remain open.",
            "B M3-M8, other A physics/optimisation/aircraft and six-domain horizon remain open.",
        ],
    }


def _result(status, reasons, model_id=None, outputs=None):
    return {
        "status": status,
        "reasons": list(reasons),
        "model_id": model_id,
        "outputs": {} if outputs is None else dict(outputs),
        "feasibility": None,
    }


def evaluate_request(request):
    """Select and explicitly invoke the bounded reference adapter.

    Accept JSON-compatible values; malformed requests return structured results.
    Configuration enumeration conveys no aircraft properties or feasibility evidence.
    """
    if not isinstance(request, dict):
        return _result("MODEL_INAPPLICABLE", ["REQUEST_MUST_BE_OBJECT"])
    if any(key not in _ALLOWED for key in request):
        return _result("MODEL_INAPPLICABLE", ["EXTRA_KEYS"])
    missing = [f"MISSING_{key.upper()}" for key in _REQUIRED if key not in request]
    if missing:
        return _result("INPUT_INCOMPLETE", missing)

    evaluation = request["evaluation"]
    if not isinstance(evaluation, str) or not evaluation:
        return _result("MODEL_INAPPLICABLE", ["INVALID_EVALUATION"])
    if evaluation != "atmosphere":
        return _result("SOLVER_UNSUPPORTED", ["EVALUATION_UNSUPPORTED"])

    configuration = request["configuration"]
    if not isinstance(configuration, str) or configuration not in _CONFIGURATIONS:
        return _result("MODEL_INAPPLICABLE", ["UNKNOWN_CONFIGURATION"], MODEL_ID)
    kind = request["altitude_kind"]
    if not isinstance(kind, str) or kind not in _KINDS:
        return _result("MODEL_INAPPLICABLE", ["INVALID_ALTITUDE_KIND"], MODEL_ID)
    altitude = request["altitude_m"]
    if type(altitude) not in (int, float):
        return _result("MODEL_INAPPLICABLE", ["ALTITUDE_MUST_BE_FINITE_NUMBER"], MODEL_ID)
    # Bounds reject NaN/infinities and huge integers before float conversion.
    if not 0 <= altitude <= 30000:
        return _result("MODEL_INAPPLICABLE", ["ALTITUDE_OUTSIDE_FINITE_RANGE"], MODEL_ID)

    outputs = request.get("outputs", list(_OUTPUTS))
    if (
        not isinstance(outputs, list)
        or not outputs
        or any(not isinstance(name, str) or name not in _OUTPUTS for name in outputs)
        or len(set(outputs)) != len(outputs)
    ):
        return _result("MODEL_INAPPLICABLE", ["INVALID_OUTPUTS"], MODEL_ID)

    try:
        state = standard_atmosphere(float(altitude), altitude_kind=kind)
    except (ArithmeticError, TypeError, ValueError):
        return _result("MODEL_INAPPLICABLE", ["ADAPTER_REJECTED_REQUEST"], MODEL_ID)
    return _result(
        "REFERENCE_COMPUTED",
        ["REFERENCE_MODEL_NOT_AIRCRAFT_VALIDATION"],
        MODEL_ID,
        {name: getattr(state, name) for name in outputs},
    )
