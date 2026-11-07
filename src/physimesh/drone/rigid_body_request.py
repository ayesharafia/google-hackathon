"""Strict JSON request adapter for the experimental rigid-body kernel."""

import math

from .rigid_body import RigidBodyState, propagate_rigid_body
from .rigid_body import _envelope as _kernel_envelope

_REQUIRED_KEYS = frozenset((
    "evaluation", "initial_state", "mass_kg", "inertia_body_kg_m2",
    "force_body_n", "moment_cg_body_nm", "gravity_enu_m_s2", "dt_s", "steps",
    "property_source", "applicability_declaration",
))
_STATE_FIELDS = (
    ("position_enu_m", 3),
    ("velocity_enu_m_s", 3),
    ("quaternion_body_to_enu", 4),
    ("angular_velocity_body_rad_s", 3),
)
_DECLARATION_LIMITATIONS = (
    "Caller declarations are unverified and do not establish applicability or verification.",
    "The caller's property source is an unverified literal, not validation.",
)


def _refusal(status="MODEL_INAPPLICABLE"):
    result = _kernel_envelope()
    result["status"] = status
    result["reasons"] = ["Request is outside the supported domain."]
    result["limitations"].extend(_DECLARATION_LIMITATIONS)
    return result


def _exact_keys(value, keys):
    return (
        type(value) is dict
        and all(type(key) is str for key in value)
        and value.keys() == keys
    )


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _number_list(value, size):
    return (
        type(value) is list
        and len(value) == size
        and all(_finite_number(item) for item in value)
    )


def _declaration(value):
    return type(value) is str and len(value) <= 2000 and bool(value.strip())


def evaluate_rigid_body(request):
    """Validate literal JSON values, then delegate all physics to the kernel."""
    if not _exact_keys(request, _REQUIRED_KEYS):
        return _refusal()
    evaluation = request["evaluation"]
    if type(evaluation) is not str:
        return _refusal()
    if evaluation != "rigid_body_constant_wrench_experimental":
        return _refusal("SOLVER_UNSUPPORTED")

    state = request["initial_state"]
    if not _exact_keys(state, frozenset(name for name, _ in _STATE_FIELDS)):
        return _refusal()
    if not all(_number_list(state[name], size) for name, size in _STATE_FIELDS):
        return _refusal()
    inertia = request["inertia_body_kg_m2"]
    if (
        type(inertia) is not list
        or len(inertia) != 3
        or not all(_number_list(row, 3) for row in inertia)
    ):
        return _refusal()
    if not all(
        _number_list(request[name], 3)
        for name in ("force_body_n", "moment_cg_body_nm", "gravity_enu_m_s2")
    ):
        return _refusal()
    if not all(_finite_number(request[name]) for name in ("mass_kg", "dt_s")):
        return _refusal()
    if type(request["steps"]) is not int:
        return _refusal()
    if not all(
        _declaration(request[name])
        for name in ("property_source", "applicability_declaration")
    ):
        return _refusal()

    result = propagate_rigid_body(
        initial_state=RigidBodyState(
            position_enu_m=tuple(state["position_enu_m"]),
            velocity_enu_m_s=tuple(state["velocity_enu_m_s"]),
            quaternion_body_to_enu=tuple(state["quaternion_body_to_enu"]),
            angular_velocity_body_rad_s=tuple(state["angular_velocity_body_rad_s"]),
        ),
        mass_kg=request["mass_kg"],
        inertia_body_kg_m2=tuple(tuple(row) for row in inertia),
        force_body_n=tuple(request["force_body_n"]),
        moment_cg_body_nm=tuple(request["moment_cg_body_nm"]),
        gravity_enu_m_s2=tuple(request["gravity_enu_m_s2"]),
        dt_s=request["dt_s"],
        steps=request["steps"],
    )
    return {
        **result,
        "limitations": [*result["limitations"], *_DECLARATION_LIMITATIONS],
    }
