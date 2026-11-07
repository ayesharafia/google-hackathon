# Experimental rigid-body request

`evaluate_rigid_body(request)` is a Python adapter for `propagate_rigid_body`.
There is no frontend API endpoint yet. This is a constant-input numerical
experiment: physical validation is `NOT_ESTABLISHED`, evidence is `unverified`,
and neither aircraft feasibility nor flight qualification is established.

## Exact JSON request

```json
{
  "evaluation": "rigid_body_constant_wrench_experimental",
  "initial_state": {
    "position_enu_m": [0, 0, 0],
    "velocity_enu_m_s": [0, 0, 0],
    "quaternion_body_to_enu": [1, 0, 0, 0],
    "angular_velocity_body_rad_s": [0, 0, 0]
  },
  "mass_kg": 1,
  "inertia_body_kg_m2": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
  "force_body_n": [1, 0, 0],
  "moment_cg_body_nm": [0, 0, 0],
  "gravity_enu_m_s2": [0, 0, -9.81],
  "dt_s": 0.01,
  "steps": 10,
  "property_source": "Unverified illustrative caller-supplied mass and inertia.",
  "applicability_declaration": "Unverified constant-input rigid-body numerical example."
}
```

Both declaration fields are required literal strings: nonblank after stripping
whitespace and at most 2,000 characters each. They remain unverified caller
statements; they do not establish property validity, applicability or verification.
The adapter does not resolve a property source or interpret declaration contents.

## Units, frames and loads

- ENU means East, North, Up. Position is in metres; velocity is in m/s.
- Body axes are forward, left, up. Angular velocity is expressed in body axes,
  in rad/s. Identity attitude aligns body x/y/z with East/North/Up.
- `quaternion_body_to_enu` is dimensionless, scalar-first Hamilton `[w,x,y,z]`.
  It maps body vectors into ENU: `v_enu = R(q) v_body`.
  The kinematics use right multiplication, `q_dot = 0.5 q ⊗ [0, omega_body]`.
  Positive rotation about body y pitches the nose down from identity.
- Mass is in kg. The full 3×3 body inertia tensor is in kg·m², about the CG
  in the same body axes as angular velocity and moment.
- `force_body_n` is a constant body-frame force in N; its ENU direction changes
  with attitude. `moment_cg_body_nm` is a constant body-frame moment about the
  centre of gravity (CG), in N·m. A constant body wrench is not generally constant
  in ENU.
- `gravity_enu_m_s2` is an explicit constant ENU acceleration in m/s².
  Translation uses `a_enu = R(q) force_body_n / mass_kg + gravity_enu_m_s2`.
  Gravity is added separately; do not include it again in the supplied force.
- Rotation uses `I omega_dot = moment_cg_body_nm - omega × (I omega)`.
  For a force applied away from the CG, the caller must include its body-frame
  `r_from_cg × force` contribution in the supplied total CG moment. No application
  point, load inference or automatic moment translation is provided.
- `dt_s` is the fixed step in seconds; `steps` is a dimensionless integer.
  Mass, inertia, body force, CG body moment and ENU gravity remain constant.

## Strict validation and results

The top-level object and `initial_state` must have exactly the keys shown; missing
or extra keys are refused. Arrays must be literal lists with the displayed sizes:
three entries per vector, four per quaternion, and three rows of three for inertia.
Numbers must be built-in finite `int` or `float` values; booleans, numeric strings,
NumPy scalars and tuples are not accepted by the adapter. `steps` must be a
built-in integer, excluding booleans, from 1 through 10,000.

The kernel additionally requires positive mass and `dt_s`, finite positive
`dt_s * steps`, exact tensor symmetry and a successful scaled Cholesky
positive-definiteness check. Inertia physical triangle admissibility is
`NOT_ASSESSED`. Input numbers must be zero or normal finite binary64 values;
nonzero subnormals are refused. The quaternion must be nonzero with
`abs(norm(q) - 1) <= 1e-12`; accepted input is normalized. Intermediate arithmetic,
time advancement or diagnostic failures can also refuse an otherwise well-shaped
request. There is no conditioning, angle, horizon or convergence guarantee.

Unsupported string values for `evaluation` return `SOLVER_UNSUPPORTED` after the
top-level keys pass validation. Other validation failures return
`MODEL_INAPPLICABLE`; refusal outputs and output units are empty objects.
Early adapter refusals preserve the kernel limitations and sources, and append
the adapter limitations about unverified caller declarations and property sources. A
successful numerical evaluation returns `COMPUTED_EXPERIMENTAL` and model ID
`rigid_body_constant_body_wrench_rk4_v1`. Every result retains
`physical_validation: "NOT_ESTABLISHED"`, `evidence_level: "unverified"`,
`aircraft_status: null`, `feasibility: null`, and
`inertia_physical_admissibility: "NOT_ASSESSED"`.

Successful `outputs` contain elapsed seconds, step count, initial/final states,
quaternion normalization diagnostics, initial/final rotational kinetic energy (J),
and initial/final ENU angular momentum (kg·m²/s). Dimensionless relative energy
and angular-momentum drifts are computed only for exactly zero supplied moment;
otherwise both are null. `output_units` supplies the corresponding units.

The kernel advances all 13 state components with fixed-step classical RK4 and
normalizes quaternions after completed steps. Raw stage rotations need not be
orthogonal. Normalization is not an integration-error estimate; step refinement
is required, and invariant conservation or accuracy is not guaranteed. Numerical
success supplies no flight qualification or aircraft feasibility finding.

## Runnable Python example

Run this Python code in an environment where `physimesh` and NumPy are available.
The request is self-contained and matches the JSON example above. No frontend or
HTTP API is required.

```python
import json

from physimesh.drone.rigid_body_request import evaluate_rigid_body

request = json.loads(r'''
{
  "evaluation": "rigid_body_constant_wrench_experimental",
  "initial_state": {
    "position_enu_m": [0, 0, 0],
    "velocity_enu_m_s": [0, 0, 0],
    "quaternion_body_to_enu": [1, 0, 0, 0],
    "angular_velocity_body_rad_s": [0, 0, 0]
  },
  "mass_kg": 1,
  "inertia_body_kg_m2": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
  "force_body_n": [1, 0, 0],
  "moment_cg_body_nm": [0, 0, 0],
  "gravity_enu_m_s2": [0, 0, -9.81],
  "dt_s": 0.01,
  "steps": 10,
  "property_source": "Unverified illustrative caller-supplied mass and inertia.",
  "applicability_declaration": "Unverified constant-input rigid-body numerical example."
}
''')

result = evaluate_rigid_body(request)
assert result["status"] == "COMPUTED_EXPERIMENTAL", result
assert result["physical_validation"] == "NOT_ESTABLISHED"
print(json.dumps(result, indent=2, allow_nan=False))
```
