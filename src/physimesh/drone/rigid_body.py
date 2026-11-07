"""Experimental constant-body-wrench rigid-body integration in ENU.

Body axes are forward/left/up. Scalar-first Hamilton q maps body to ENU;
identity points body x East, and positive Ry pitch points the nose down.
Classical RK4 advances all 13 components; only completed steps project q.
Raw stage quaternions use the polynomial rotation matrix, so stage rotations
need not be orthogonal. Projection is not an integration-error estimate and
cannot change the uncoupled angular velocity or rotational energy itself.

Arithmetic checks conservatively reject nonfinite/subnormal computed state,
RHS, products and scaled solves, and NumPy-reported underflow (including
underflow to zero). They cannot detect every loss of significance inside
LAPACK. Diagnostic differences/norms may legitimately be zero or tiny.
There is no condition-number, angle, horizon or convergence guarantee.
"""

import math
import sys
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RigidBodyState:
    """Passive state record; propagation validates exact tuple/number types."""

    position_enu_m: tuple
    velocity_enu_m_s: tuple
    quaternion_body_to_enu: tuple
    angular_velocity_body_rad_s: tuple


class _Inapplicable(ValueError):
    """Expected unsupported input or numerical range failure."""


_MIN_NORMAL = sys.float_info.min
_FIELDS = (
    "position_enu_m",
    "velocity_enu_m_s",
    "quaternion_body_to_enu",
    "angular_velocity_body_rad_s",
)
_STATE_UNITS = dict(zip(_FIELDS, ("m", "m/s", "1", "rad/s")))
_LIMITATIONS = (
    "Finite experimental numerical kernel; physical validation is not established.",
    (
        "Constant caller-supplied mass, full body inertia, body force, CG body moment "
        "and ENU gravity only; no inferred loads or aircraft qualification."
    ),
    (
        "Fixed-step classical RK4 requires step refinement; no accuracy or horizon "
        "guarantee, and invariants need not be conserved."
    ),
    (
        "Raw RK4 stage quaternions use a polynomial rotation that need not be "
        "orthogonal; completed-step normalization is not an error estimate."
    ),
    (
        "Quaternion-only projection does not change uncoupled omega or kinetic "
        "energy, but affects attitude and world angular momentum diagnostics."
    ),
    (
        "Exact tensor symmetry and scaled Cholesky SPD are numerical support "
        "restrictions; inertia physical triangle admissibility is not assessed."
    ),
    (
        "Conservative finite/normal intermediate checks and reported underflow "
        "checks can refuse extreme arithmetic; diagnostic differences may be tiny. "
        "Not every internal LAPACK loss of significance is detectable."
    ),
)
_SOURCES = (
    "https://arxiv.org/abs/1711.02508",
    (
        "https://phys.libretexts.org/Bookshelves/Classical_Mechanics/"
        "Variational_Principles_in_Classical_Mechanics_(Cline)/"
        "13%3A_Rigid-body_Rotation/"
        "13.21%3A_Torque-free_rotation_of_an_asymmetric_rigid_rotor"
    ),
)


def _envelope():
    return {
        "model_id": "rigid_body_constant_body_wrench_rk4_v1",
        "status": "MODEL_INAPPLICABLE",
        "physical_validation": "NOT_ESTABLISHED",
        "evidence_level": "unverified",
        "aircraft_status": None,
        "feasibility": None,
        "inertia_physical_admissibility": "NOT_ASSESSED",
        "reasons": [],
        "limitations": list(_LIMITATIONS),
        "sources": list(_SOURCES),
        "outputs": {},
        "output_units": {},
    }


def _number(value):
    if type(value) not in (int, float):
        raise _Inapplicable
    result = float(value)
    if not math.isfinite(result) or (result != 0 and abs(result) < _MIN_NORMAL):
        raise _Inapplicable
    return result


def _vector(value, size=3):
    if type(value) is not tuple or len(value) != size:
        raise _Inapplicable
    return np.array([_number(item) for item in value], dtype=float)


def _checked(value):
    array = np.asarray(value)
    if not np.isfinite(array).all():
        raise _Inapplicable
    if np.any((array != 0) & (np.abs(array) < _MIN_NORMAL)):
        raise _Inapplicable
    return value


def _mv(matrix, vector):
    # Explicit products expose underflow/overflow that BLAS may not report.
    products = _checked(matrix * vector[np.newaxis, :])
    return _checked(np.sum(products, axis=1))


def _cross(left, right):
    a = _checked(left[[1, 2, 0]] * right[[2, 0, 1]])
    b = _checked(left[[2, 0, 1]] * right[[1, 2, 0]])
    return _checked(a - b)


def _rotation(q):
    w, x, y, z = q
    xx, yy, zz = _checked(q[1:] * q[1:])
    xy, xz, yz = _checked(np.array([x, x, y]) * np.array([y, z, z]))
    wx, wy, wz = _checked(w * q[1:])
    return _checked(np.array([
        [1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)],
        [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)],
        [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)],
    ]))


def _norm(vector):
    # Scaled hypot avoids spurious overflow/underflow in diagnostic squares.
    result = math.hypot(*(float(item) for item in vector))
    if not math.isfinite(result):
        raise _Inapplicable
    return result


def _project(q):
    norm = _norm(q)
    if norm == 0:
        raise _Inapplicable
    return _checked(q / norm), norm


def _state_dict(state):
    return dict(zip(_FIELDS, (
        state[:3].tolist(), state[3:6].tolist(),
        state[6:10].tolist(), state[10:].tolist(),
    )))


def _invariants(state, inertia):
    angular = _mv(inertia, state[10:])
    products = _checked(state[10:] * angular)
    energy = float(_checked(0.5 * _checked(np.sum(products))))
    if energy < 0:
        raise _Inapplicable
    momentum = _mv(_rotation(state[6:10]), angular)
    return energy, momentum


def _relative(difference, baseline):
    if baseline == 0:
        if difference == 0:
            return 0.0
        raise _Inapplicable
    # Differences and diagnostic ratios may be legitimately tiny/subnormal.
    result = difference / baseline
    if not math.isfinite(result):
        raise _Inapplicable
    return result


def propagate_rigid_body(
    *, initial_state, mass_kg, inertia_body_kg_m2, force_body_n,
    moment_cg_body_nm, gravity_enu_m_s2, dt_s, steps,
):
    """Return an all-or-nothing experimental envelope for a constant wrench.

    Quaternion kinematics: Sola, p.46, equations 198--201, body angular
    velocity/right Hamilton multiplication. Euler dynamics and torque-free
    invariants: Cline, section 13.21 (source URLs in every envelope).
    All arguments are explicit; inputs are never mutated. Expected validation,
    floating-point range and linear-algebra failures produce generic refusals.
    """
    result = _envelope()
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise", under="raise"):
            outputs = _propagate(
                initial_state, mass_kg, inertia_body_kg_m2, force_body_n,
                moment_cg_body_nm, gravity_enu_m_s2, dt_s, steps,
            )
    except (_Inapplicable, FloatingPointError, OverflowError, np.linalg.LinAlgError):
        result["reasons"] = ["Input or numerical arithmetic is outside the supported domain."]
        return result
    result["status"] = "COMPUTED_EXPERIMENTAL"
    result["outputs"] = outputs
    result["output_units"] = {
        "elapsed_s": "s",
        "steps": "1",
        "initial_state": dict(_STATE_UNITS),
        "final_state": dict(_STATE_UNITS),
        "input_quaternion_norm_correction": "1",
        "max_preprojection_quaternion_norm_error": "1",
        "final_quaternion_norm": "1",
        "initial_rotational_kinetic_energy_j": "J",
        "final_rotational_kinetic_energy_j": "J",
        "initial_angular_momentum_enu_kg_m2_s": "kg*m^2/s",
        "final_angular_momentum_enu_kg_m2_s": "kg*m^2/s",
        "torque_free_relative_energy_drift": "1",
        "torque_free_relative_angular_momentum_drift": "1",
    }
    return result


def _propagate(initial, mass, tensor, force, moment, gravity, dt, steps):
    if type(initial) is not RigidBodyState or type(steps) is not int:
        raise _Inapplicable
    if not 1 <= steps <= 10000:
        raise _Inapplicable
    mass, dt = _number(mass), _number(dt)
    if mass <= 0 or dt <= 0:
        raise _Inapplicable
    duration = float(_checked(np.float64(dt) * steps))
    if duration <= 0:
        raise _Inapplicable
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
    force, moment, gravity = _vector(force), _vector(moment), _vector(gravity)
    state = np.concatenate((
        _vector(initial.position_enu_m), _vector(initial.velocity_enu_m_s),
        _vector(initial.quaternion_body_to_enu, 4),
        _vector(initial.angular_velocity_body_rad_s),
    ))
    original_norm = _norm(state[6:10])
    correction = abs(original_norm - 1.0)
    if original_norm == 0 or correction > 1e-12:
        raise _Inapplicable
    state[6:10], _ = _project(state[6:10])
    start = state.copy()
    energy0, momentum0 = _invariants(start, inertia)

    def rhs(value):
        _checked(value)
        q, omega = value[6:10], value[10:]
        acceleration = _checked(_checked(_mv(_rotation(q), force) / mass) + gravity)
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
    time = 0.0
    previous_target = 0.0
    half_dt = _checked(np.float64(dt) * 0.5)
    sixth_dt = _checked(np.float64(dt) / 6.0)
    for index in range(1, steps + 1):
        next_time = float(_checked(np.float64(time) + dt))
        target = float(_checked(np.float64(dt) * index))
        if next_time <= time or target <= previous_target:
            raise _Inapplicable
        if not math.isclose(next_time, target, rel_tol=8 * sys.float_info.epsilon * index):
            raise _Inapplicable
        k1 = rhs(state)
        k2 = rhs(_checked(state + _checked(half_dt * k1)))
        k3 = rhs(_checked(state + _checked(half_dt * k2)))
        k4 = rhs(_checked(state + _checked(dt * k3)))
        weighted = _checked(_checked(k1 + _checked(2.0 * k2)) + _checked(2.0 * k3))
        weighted = _checked(weighted + k4)
        state = _checked(state + _checked(sixth_dt * weighted))
        state[6:10], raw_norm = _project(state[6:10])
        max_error = max(max_error, abs(raw_norm - 1.0))
        time, previous_target = next_time, target
    energy1, momentum1 = _invariants(state, inertia)
    energy_drift = momentum_drift = None
    if not np.any(moment != 0):
        # Diagnostic cancellation is allowed; no invented tiny-error threshold.
        with np.errstate(under="ignore"):
            energy_drift = _relative(abs(energy1 - energy0), energy0)
            momentum_drift = _relative(_norm(momentum1 - momentum0), _norm(momentum0))
    return {
        "elapsed_s": duration,
        "steps": steps,
        "initial_state": _state_dict(start),
        "final_state": _state_dict(state),
        "input_quaternion_norm_correction": correction,
        "max_preprojection_quaternion_norm_error": max_error,
        "final_quaternion_norm": _norm(state[6:10]),
        "initial_rotational_kinetic_energy_j": energy0,
        "final_rotational_kinetic_energy_j": energy1,
        "initial_angular_momentum_enu_kg_m2_s": momentum0.tolist(),
        "final_angular_momentum_enu_kg_m2_s": momentum1.tolist(),
        "torque_free_relative_energy_drift": energy_drift,
        "torque_free_relative_angular_momentum_drift": momentum_drift,
}
