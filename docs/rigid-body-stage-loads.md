# Experimental rigid-body stage loads

Module: `physimesh.drone.rigid_body_stage_loads`.
Function: `propagate_rigid_body_stage_loads` (all arguments are keyword-only).

```python
def propagate_rigid_body_stage_loads(
    *, initial_state, mass_kg, inertia_body_kg_m2,
    gravity_enu_m_s2, dt_s, steps, load_function,
):
```

This fixed-step RK4 model integrates position, velocity, attitude and body rate.
Success means `COMPUTED_EXPERIMENTAL`; physical validation is `NOT_ESTABLISHED`,
evidence is `unverified`, and `aircraft_status` and `feasibility` are `None`.
It establishes no aircraft feasibility. The older constant-load kernel is frozen;
exact parity with that kernel is not promised.

ENU axes are East, North, Up; body FLU axes are Forward, Left, Up.
The scalar-first Hamilton quaternion maps body vectors to ENU. Identity aligns
body x with East, y with North and z with Up; positive body-y rotation pitches
nose down. Body angular rate multiplies on the right:
`qdot = 0.5 * (q ⊗ (0, omega_body))`.
Stage rotation and callback attitude use normalized quaternions; quaternion
kinematics use raw stage quaternions. Each completed step projects attitude.

Mass is constant and positive. Supply a full constant body inertia tensor about
the CG as a tuple of three three-tuples. Exact symmetry and scaled Cholesky SPD
are required; physical inertia triangle admissibility is `NOT_ASSESSED`.
Gravity is an explicit ENU acceleration in m/s². Callback force is body-frame N,
excluding gravity; callback moment is body-frame N·m about the CG. No properties
or loads are inferred, and no force-application-point moment is added implicitly.

`load_function(t_s, stage_state)` returns exactly `(F_body_N, M_body_N_m)`:
an exact two-tuple containing exact three-tuples of builtin finite, zero-or-normal
numbers. Each immutable `RigidBodyState` snapshot contains builtin float tuples:
`position_enu_m`, `velocity_enu_m_s`, `quaternion_body_to_enu`, and
`angular_velocity_body_rad_s`; its quaternion is normalized.

Time starts at zero. A successful N-step call makes exactly 4N callbacks at
start, midpoint, midpoint, end per step. The two midpoint states can differ;
a step's end time repeats at the next step's start, whose state can also differ.
There are no dry runs, diagnostic calls, retries or substeps.

Inputs require the exact `RigidBodyState` type, an exact integer `steps` in
1–10000, positive `dt_s`, and an initial quaternion norm within 1e-12 of one.
Finite/normal guards, checked time spacing, and reported arithmetic underflow
(including to zero) can refuse computation; internal LAPACK loss of significance
is not fully detectable. RK4 gives no accuracy, stability, convergence,
conditioning or horizon guarantee; quaternion projection is no error estimate.

Failures return `MODEL_INAPPLICABLE`, generic reasons, and empty `outputs` and
`output_units`: solver outputs are all-or-nothing. Ordinary callback `Exception`
is caught and reported generically; `BaseException` propagates. Callbacks must
be trusted local, pure, deterministic and sufficiently smooth; these obligations
are not verified. There is no sandbox, network enforcement, execution limit or
side-effect rollback. There are no JSON callbacks, API catalogue or persistence
integration for this function.

On success, `outputs` contains exactly these seven keys:
`elapsed_s`, `steps`, `final_state`, `load_evaluations`,
`input_quaternion_norm_correction`, `max_preprojection_quaternion_norm_error`,
and `final_quaternion_norm`. `final_state` has the four state fields above;
`output_units` supplies matching SI units and dimensionless `1` values.

Runnable example: identity attitude, zero initial position, velocity and body
rate, identity inertia, explicit zero gravity, dt = 0.01 s and 10 steps.
The callback returns constant unit body-x force and zero CG moment.

```python
from physimesh.drone.rigid_body import RigidBodyState
from physimesh.drone.rigid_body_stage_loads import propagate_rigid_body_stage_loads


def loads(t_s, stage_state):
    return ((1.0, 0.0, 0.0), (0.0, 0.0, 0.0))


initial = RigidBodyState(
    position_enu_m=(0.0, 0.0, 0.0),
    velocity_enu_m_s=(0.0, 0.0, 0.0),
    quaternion_body_to_enu=(1.0, 0.0, 0.0, 0.0),
    angular_velocity_body_rad_s=(0.0, 0.0, 0.0),
)
result = propagate_rigid_body_stage_loads(
    initial_state=initial, mass_kg=1.0,
    inertia_body_kg_m2=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    gravity_enu_m_s2=(0.0, 0.0, 0.0), dt_s=0.01, steps=10,
    load_function=loads,
)
assert result["status"] == "COMPUTED_EXPERIMENTAL"
```
