"""Experimental coupled rigid-body RK4 with trusted local stage loads.

Scalar-first Hamilton attitude maps forward/left/up body axes to ENU;
identity points body x East and positive body-y rotation pitches nose down.
Physical rotation and callback views use normalized stage quaternions, while
quaternion derivatives use raw stages. Completed steps project attitude.
Exact constant-kernel parity is not promised. No API catalogue or persistence
integration is provided. All arguments, including gravity and SI units, are
explicit; no loads or physical properties are inferred.
"""

import math
import sys

import numpy as np

from .rigid_body import (
    RigidBodyState,
    _checked,
    _cross,
    _Inapplicable,
    _mv,
    _norm,
    _number,
    _project,
    _rotation,
    _state_dict,
    _vector,
)


class _LoadFailure(_Inapplicable):
    """Unsupported callback execution or return data."""


def _envelope():
    # Construct every container anew; no shared mutable result metadata.
    return {
        "model_id": "rigid_body_stage_loads_normalized_attitude_rk4_v1",
        "status": "MODEL_INAPPLICABLE",
        "physical_validation": "NOT_ESTABLISHED",
        "evidence_level": "unverified",
        "aircraft_status": None,
        "feasibility": None,
        "inertia_physical_admissibility": "NOT_ASSESSED",
        "reasons": [],
        "limitations": [
            "Finite experimental numerical model; physical validation is not established.",
            "Constant positive mass, full constant body inertia about the CG, explicit "
            "ENU gravity and caller-supplied body force and CG moment only. Force "
            "excludes gravity; no inferred aircraft loads or aircraft qualification.",
            "Exact symmetry and scaled Cholesky SPD restrict numerical support; "
            "physical inertia triangle admissibility is not assessed.",
            "Conservative finite/normal checks and reported underflow, including "
            "underflow to zero, can refuse arithmetic. Internal LAPACK loss of "
            "significance is not fully detectable; diagnostic differences may be tiny.",
            "Fixed-step RK4 supplies no accuracy, stability, convergence, condition-number "
            "or horizon guarantee. Quaternion projection is not an error estimate.",
            "Stage rotation and callback attitude are normalized, but quaternion "
            "kinematics use raw stages. Exact constant-kernel parity is not promised.",
            "Caller purity, determinism and sufficient smoothness are required and "
            "not verified. Finite loads do not establish physical validity.",
            "Callbacks are trusted local Python with unbounded runtime: no sandbox, "
            "network enforcement, execution time limit or side-effect rollback. "
            "Returned solver outputs are all-or-nothing.",
            "Public sources support numerical formulations only; evidence for this "
            "exact module and its load models remains unverified.",
        ],
        "sources": [
            "https://arc.aiaa.org/doi/10.2514/1.G004578",
            "https://ancs.eng.buffalo.edu/pdf/ancs_papers/2013/geom_int.pdf",
        ],
        "outputs": {},
        "output_units": {},
    }


def propagate_rigid_body_stage_loads(
    *, initial_state, mass_kg, inertia_body_kg_m2,
    gravity_enu_m_s2, dt_s, steps, load_function,
):
    """Integrate 13 coupled components with exactly four load calls per step.

    ``load_function(t_s, stage_state)`` returns an exact pair of exact three-
    tuples of builtin finite, zero-or-normal numbers: body force in N and CG
    body moment in N*m. Time starts at zero. Each immutable stage record uses
    builtin float tuples and normalized attitude. The caller must supply pure,
    deterministic, sufficiently smooth trusted local code; these obligations
    are not verified. Runtime is unbounded, without sandbox or side-effect
    rollback. There are no dry runs, diagnostics calls, retries or substeps.
    Ordinary callback exceptions refuse generically; BaseException propagates.
    """
    result = _envelope()
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise", under="raise"):
            outputs = _propagate(
                initial_state, mass_kg, inertia_body_kg_m2,
                gravity_enu_m_s2, dt_s, steps, load_function,
            )
    except _LoadFailure:
        result["reasons"] = ["Load callback failed or returned unsupported data."]
        return result
    except (_Inapplicable, FloatingPointError, OverflowError, np.linalg.LinAlgError):
        result["reasons"] = ["Input or numerical arithmetic is outside the supported domain."]
        return result
    result["status"] = "COMPUTED_EXPERIMENTAL"
    result["outputs"] = outputs
    result["output_units"] = {
        "elapsed_s": "s",
        "steps": "1",
        "final_state": {
            "position_enu_m": "m",
            "velocity_enu_m_s": "m/s",
            "quaternion_body_to_enu": "1",
            "angular_velocity_body_rad_s": "rad/s",
        },
        "load_evaluations": "1",
        "input_quaternion_norm_correction": "1",
        "max_preprojection_quaternion_norm_error": "1",
        "final_quaternion_norm": "1",
    }
    return result


def _time_grid(dt, steps):
    half = _checked(np.float64(dt) * 0.5)
    sixth = _checked(np.float64(dt) / 6.0)
    duration = float(_checked(np.float64(dt) * steps))
    if half <= 0 or sixth <= 0 or duration <= 0:
        raise _Inapplicable
    grid = []
    previous = 0.0
    for index in range(steps):
        start = float(_checked(np.float64(dt) * index))
        end = float(_checked(np.float64(dt) * (index + 1)))
        middle = float(_checked(np.float64(start) + half))
        local_end = float(_checked(np.float64(start) + dt))
        second_end = float(_checked(np.float64(middle) + half))
        tolerance = 8 * sys.float_info.epsilon * (index + 1)
        if start != previous or not start < middle < end:
            raise _Inapplicable
        if local_end <= start or second_end <= middle:
            raise _Inapplicable
        if not math.isclose(local_end, end, rel_tol=tolerance, abs_tol=0.0):
            raise _Inapplicable
        if not math.isclose(second_end, end, rel_tol=tolerance, abs_tol=0.0):
            raise _Inapplicable
        grid.append((start, middle, end))
        previous = end
    return half, sixth, duration, grid


def _loads(function, time, value, attitude):
    snapshot = RigidBodyState(
        tuple(float(x) for x in value[:3]),
        tuple(float(x) for x in value[3:6]),
        tuple(float(x) for x in attitude),
        tuple(float(x) for x in value[10:]),
    )
    try:
        returned = function(time, snapshot)
    except Exception:
        raise _LoadFailure from None
    try:
        if type(returned) is not tuple or len(returned) != 2:
            raise _Inapplicable
        force, moment = _vector(returned[0]), _vector(returned[1])
    except (_Inapplicable, OverflowError, FloatingPointError):
        raise _LoadFailure from None
    return force, moment


def _propagate(initial, mass, tensor, gravity, dt, steps, load_function):
    if type(initial) is not RigidBodyState or type(steps) is not int:
        raise _Inapplicable
    if not 1 <= steps <= 10000:
        raise _Inapplicable
    if not callable(load_function):
        raise _LoadFailure
    mass, dt = _number(mass), _number(dt)
    if mass <= 0 or dt <= 0:
        raise _Inapplicable
    half, sixth, duration, grid = _time_grid(dt, steps)
    if type(tensor) is not tuple or len(tensor) != 3:
        raise _Inapplicable
    inertia = np.array([_vector(row) for row in tensor])
    if not np.array_equal(inertia, inertia.T):
        raise _Inapplicable
    scale = float(np.max(np.abs(inertia)))
    if scale == 0:
        raise _Inapplicable
    scaled = _checked(inertia / scale)
    factor = _checked(np.linalg.cholesky(scaled))
    if np.any(np.diag(factor) <= 0):
        raise _Inapplicable
    gravity = _vector(gravity)
    state = np.concatenate((
        _vector(initial.position_enu_m),
        _vector(initial.velocity_enu_m_s),
        _vector(initial.quaternion_body_to_enu, 4),
        _vector(initial.angular_velocity_body_rad_s),
    ))
    original_norm = _norm(state[6:10])
    correction = abs(original_norm - 1.0)
    if original_norm == 0 or correction > 1e-12:
        raise _Inapplicable
    state[6:10], _ = _project(state[6:10])

    def rhs(time, value):
        _checked(value)
        q, omega = value[6:10], value[10:]
        attitude, _ = _project(q)
        force, moment = _loads(load_function, time, value, attitude)
        acceleration = _checked(_checked(_mv(_rotation(attitude), force) / mass) + gravity)
        scalar = -_checked(np.sum(_checked(q[1:] * omega)))
        vector = _checked(_checked(q[0] * omega) + _cross(q[1:], omega))
        qdot = _checked(0.5 * np.concatenate(([scalar], vector)))
        angular = _mv(inertia, omega)
        residual = _checked(moment - _cross(omega, angular))
        scaled_rhs = _checked(residual / scale)
        intermediate = _checked(np.linalg.solve(factor, scaled_rhs))
        omega_dot = _checked(np.linalg.solve(factor.T, intermediate))
        return _checked(np.concatenate((value[3:6], acceleration, qdot, omega_dot)))

    max_error = 0.0
    for start, middle, end in grid:
        k1 = rhs(start, state)
        k2 = rhs(middle, _checked(state + _checked(half * k1)))
        k3 = rhs(middle, _checked(state + _checked(half * k2)))
        k4 = rhs(end, _checked(state + _checked(dt * k3)))
        weighted = _checked(_checked(k1 + _checked(2.0 * k2)) + _checked(2.0 * k3))
        weighted = _checked(weighted + k4)
        state = _checked(state + _checked(sixth * weighted))
        state[6:10], raw_norm = _project(state[6:10])
        max_error = max(max_error, abs(raw_norm - 1.0))
    return {
        "elapsed_s": duration,
        "steps": steps,
        "final_state": _state_dict(state),
        "load_evaluations": 4 * steps,
        "input_quaternion_norm_correction": correction,
        "max_preprojection_quaternion_norm_error": max_error,
        "final_quaternion_norm": _norm(state[6:10]),
    }
