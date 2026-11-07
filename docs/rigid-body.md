# Rigid-body propagation

`rigid_body.py` is a finite experimental numerical kernel using local NumPy. It advances translation and rotation with constant caller-supplied mass, full body inertia,
force in body axes, moment about the centre of gravity in body axes, and ENU gravity.
No gravity, wrench, or other loads are inferred. Physical validation is not established.

## API and inputs

```python
@dataclass(frozen=True)
class RigidBodyState:
    position_enu_m: tuple
    velocity_enu_m_s: tuple
    quaternion_body_to_enu: tuple
    angular_velocity_body_rad_s: tuple

propagate_rigid_body(*, initial_state, mass_kg, inertia_body_kg_m2,
                     force_body_n, moment_cg_body_nm, gravity_enu_m_s2,
                     dt_s, steps) -> dict
```

Every keyword is required. The state constructor is passive; propagation validates it. `initial_state` must have exactly type `RigidBodyState`, excluding subclasses.
Its fields must be exact built-in tuples of lengths 3, 3, 4, and 3 respectively.
Force, moment, and gravity must each be exact built-in 3-tuples. Inertia must be an
exact built-in 3-tuple of exact built-in 3-tuples, with entries in kg·m².
Numeric entries, mass, and step size must be built-in `int` or `float`, excluding
booleans and subclasses, convertible to finite floating-point values, normal when nonzero.
Mass and `dt_s` must be positive; `steps` must be a built-in integer from 1 through 10000.
Inertia must be exactly symmetric and pass finite scaled Cholesky positive-definiteness
checks. Exact symmetry can reject rotated tensors that are asymmetric due to roundoff; no silent symmetrization is performed.
These numerical restrictions do not assess physical triangle admissibility.
The quaternion must be nonzero with `abs(norm(q) - 1) <= 1e-12`; it is explicitly
normalized. Both signs are accepted without sign canonicalization. Inputs are not mutated.

## Frames and integration

ENU means East, North, Up; body axes are forward, left, up. The scalar-first Hamilton
quaternion maps body vectors into ENU. Identity points forward East; positive rotation
about body y pitches the nose down. Body angular velocity gives
`qdot = 0.5 * Hamilton(q, (0, wx, wy, wz))`, with right multiplication.
The other equations are `pdot = v`, `vdot = R(q) F / mass + gravity`, and
`I wdot = M - cross(w, I w)`. Scaled triangular solves are used without a matrix inverse.

Classical fixed-step RK4 advances all 13 state components. Stage quaternions remain raw:
for `q = (s, u)`, `R(q) = identity + 2*s*[u]x + 2*[u]x²`, where `[u]x` is the cross-product
matrix. This polynomial need not be orthogonal for a raw stage quaternion.
Only each completed step projects the quaternion to unit norm. Projection is not an
integration-error estimate; step refinement remains necessary. Quaternion-only projection
does not itself change the uncoupled angular velocity or rotational kinetic energy.
It can affect attitude and ENU angular momentum diagnostics; conservation is not guaranteed.

Inputs, stages, states, products, scaled solves, and derived quantities receive conservative
finite/normal checks; detectable overflow, subnormal arithmetic, and reported underflow
can cause refusal. Zero and tiny legitimate diagnostic differences remain allowed.
`dt_s * steps` must be finite, positive, and normal; incremental timestamps must advance
and agree with step-count durations within the implementation's floating-point tolerance.
These guards provide no angle, horizon, conditioning, or convergence guarantee and cannot
detect every internal linear-algebra loss of significance.

## Results and units

The exact envelope keys are `model_id`, `status`, `physical_validation`, `evidence_level`,
`aircraft_status`, `feasibility`, `inertia_physical_admissibility`, `reasons`, `limitations`,
`sources`, `outputs`, and `output_units`. The model ID is
`rigid_body_constant_body_wrench_rk4_v1`; status is `COMPUTED_EXPERIMENTAL` or
`MODEL_INAPPLICABLE`. Physical validation is `NOT_ESTABLISHED`, evidence is `unverified`,
admissibility is `NOT_ASSESSED`, and `aircraft_status` and `feasibility` are `None`.
Reasons, limitations, and sources are lists. Expected input/numerical failures return a
generic nonempty reasons list and empty outputs/units, with no partial success.

| Exact success output key(s) | `output_units` value |
| --- | --- |
| `elapsed_s` | `s` |
| `steps` | `1` |
| `initial_state`, `final_state` | Nested map: `position_enu_m: m`, `velocity_enu_m_s: m/s`, `quaternion_body_to_enu: 1`, `angular_velocity_body_rad_s: rad/s` |
| `input_quaternion_norm_correction`, `max_preprojection_quaternion_norm_error`, `final_quaternion_norm` | `1` |
| `initial_rotational_kinetic_energy_j`, `final_rotational_kinetic_energy_j` | `J` |
| `initial_angular_momentum_enu_kg_m2_s`, `final_angular_momentum_enu_kg_m2_s` | `kg*m^2/s` |
| `torque_free_relative_energy_drift`, `torque_free_relative_angular_momentum_drift` | `1` |

State outputs are plain dictionaries with the four field names and list values; initial state contains the normalized initial quaternion. Input correction is `abs(original_norm-1)`;
maximum preprojection error measures completed raw steps only, before projection.
Energy is `E = 0.5*w·I*w`; ENU angular momentum is `L = R(q)*I*w`. For exactly zero moment, drifts are `abs(Efinal-Einitial)/Einitial` and
`norm(Lfinal-Linitial)/norm(Linitial)`. A zero baseline with zero difference yields zero;
otherwise an undefined/nonfinite ratio refuses the whole result. For any nonzero moment,
both drift fields are `None`; initial/final energy and momentum are still reported.

## Runnable example

```python
from physimesh.drone.rigid_body import RigidBodyState, propagate_rigid_body
state = RigidBodyState((0, 0, 0), (0, 0, 0), (1, 0, 0, 0), (0, 0, 0))
result = propagate_rigid_body(initial_state=state, mass_kg=1,
    inertia_body_kg_m2=((1, 0, 0), (0, 1, 0), (0, 0, 1)), force_body_n=(0, 0, 0),
    moment_cg_body_nm=(0, 0, 0), gravity_enu_m_s2=(0, 0, 0), dt_s=0.1, steps=10)
print(result["status"], result["outputs"]["elapsed_s"])  # COMPUTED_EXPERIMENTAL 1.0
```

Equations: [Solà, actual PDF p. 46, equations 198–201](https://arxiv.org/abs/1711.02508)
for body angular velocity/right Hamilton multiplication; [Cline §13.21](https://phys.libretexts.org/Bookshelves/Classical_Mechanics/Variational_Principles_in_Classical_Mechanics_(Cline)/13%3A_Rigid-body_Rotation/13.21%3A_Torque-free_rotation_of_an_asymmetric_rigid_rotor)
for Euler dynamics and torque-free invariants. These references support equations, not numerical validation.
