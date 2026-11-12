# Experimental polar rotor (V136)

`evaluate_polar_rotor(request)` in `physimesh.drone.polar_rotor` evaluates an
isolated axial rotor over caller-prescribed finite annuli using actual V135
section solves. Evaluation is `polar_rotor_experimental`, schema `polar_rotor_v1`.
`polar_rotor_catalog()` returns fresh metadata without model calls or data access.
This local Python module adds no API, UI, mission, motor, or publication workflow.

The exact root fields are `evaluation`, `rotor`, and `annuli`. No defaults or
extra fields are accepted. All input containers and scalars must be exact native
JSON types; booleans and subclasses cannot substitute for numbers.

`rotor` contains exactly these fields:

| Field | Unit and contract |
| --- | --- |
| `tip_radius_m`, `hub_radius_m` | m; positive normal, native and float tip > hub > 0 |
| `blade_count` | dimensionless; exact builtin int 1..64 |
| `angular_speed_rad_s` | rad/s; positive normal |
| `imposed_axial_velocity_m_s` | m/s; nonnegative normal or zero |
| `density_kg_m3` | kg/m³; positive normal |
| `dynamic_viscosity_pa_s` | Pa·s; positive normal |
| `speed_of_sound_m_s` | m/s; positive normal |
| `geometry_source`, `uncertainty_status` | nonblank strings, at most 2,000 characters; unverified |

`annuli` is a list of 1..8 exact dictionaries with `radial_inner_m`,
`radial_outer_m`, `chord_m`, `pitch_rad`, `polar`, and `solve`. Radii and chord
are positive normal metres; pitch is normal or zero in [0, π/2] radians.
`polar` is the complete exact V132 polar representation. `solve` is the exact
five-field V135 solve configuration, including its 2..16 evaluation budget.

The first inner boundary must match the hub, the last outer boundary the tip,
and each inner boundary its predecessor's outer boundary. These matches include
native number type and floating zero sign. Gaps, overlaps, and equivalent values
with different native types are refused. Native and float inner < outer are
both required. The hub cutoff is explicit; there is no hub-loss model.

Geometry uses checked binary64 operations in this order:
`dr = math.fsum((outer, -inner))`, `r = math.fsum((inner, .5*dr))`,
`Ut = omega*r`, and `Ua = V`. Width and tangential speed must be positive normal;
the midpoint must lie strictly inside its annulus after rounding.
All complete derived V135 requests pass both endpoint preflights before any
actual model call. The inherited positive velocity/wake branch remains required.

Each request contains the original polar, chord, pitch, solve configuration,
native imposed axial velocity, native tip radius, native fluid properties and
blade count, plus the computed float midpoint and tangential velocity.
Exactly one actual V135 evaluation runs per annulus, followed immediately by
a bounded defensive copy of its full response.

The pure parent guard compares fresh V135 catalog metadata to a frozen snapshot.
It guards every retained actual V134 residual through the accepted pure nested
guard, reconstructing each request and checking its hash. An independent state
engine then consumes the exact lower/upper/midpoint sequence and checks native
psi types, uniqueness, signs before updates, both tolerances, budgets, stagnation,
OOD exits, exact-zero decisions, bracket and solution ownership, and no trailing
calls after termination. It rebuilds the full child response, units and hashes.
The guard neither reruns a model nor invokes V135's bisection/output helpers.

Successful outputs contain `rotor_state`, `annuli`, and `integrated`. Every
annulus row contains `annulus_index`, native `radial_inner_m`/`radial_outer_m`,
float `midpoint_radius_m`/`radial_width_m`, and the full guarded `solve_result`.
All annuli run even after a guarded nonconverged or OOD section. Any such section
sets `rotor_state` to `NOT_RUN_SECTION_NOT_CONVERGED` and `integrated` to null,
with `not_applicable` units. No partial thrust or torque total is returned.

When all sections are `CONVERGED`, `rotor_state` is `COMPUTED`.
`integrated.integration_method` is `MIDPOINT_PRESCRIBED_ANNULI`. Each contribution
contains its annulus and selected evaluation indices, thrust density in N/m,
torque density in N·m/m, radial width in m, thrust in N, and torque in N·m.
The selected index comes from `solve_result.outputs.solution.evaluation_index`.
Its retained actual V134 result owns `actual_load_result.outputs.loads`, whose
`thrust_density_n_m` and `torque_density_nm_m` already include **all blades**.
Multiplication by `dr` occurs once, with **no extra blade-count factor**.

Totals use `math.fsum` over contributions in annulus order; shaft power is
`angular_speed_rad_s * total_torque_nm`, in watts. Products and intermediates
must be finite normal or zero; nonzero product underflow is refused. Signed
loads and cancellation are allowed. A zero `fsum` of rounded contributions is
allowed without a physical cancellation claim. No positive-prefix requirement,
force-unity assumption, or efficiency calculation is imposed.

[Drela's QPROP formulation](https://web.mit.edu/drela/Public/web/qprop/qprop_theory.pdf),
equations 64–65, describes radial load integration with a simple midpoint rule.
The ΩQ denominator of equation 66 is mechanical shaft power. This implementation
does not reproduce QPROP's global Newton solver or powerplant analysis. Signed
shaft power does not establish DC power, regeneration, or motor feasibility.

Counts report fully guarded whole children, including OOD: 0..8 section solves
and 0..128 equal residual/load/lookup counts. They never report attempts. An
unexpected child status, malformed response, rehashed forgery, or exception
causes `EXECUTION_FAILED` / `SOLVE_BOUNDARY_FAILED`: empty outputs and units,
with counts from previous accepted annuli only. Arithmetic/export failures use
`POLAR_ROTOR_EXECUTION_FAILED`, retaining all previously accepted counts.
Ordinary exceptions are sanitized; `BaseException` propagates.

Input bounds are 262,144 nodes including keys, depth 16, 256 container items,
2,000 string characters, strict UTF-8, 1,023 integer bits, and finite floats.
Each derived V135 request separately meets 32,768 nodes/depth 12. Each full child
response meets 2,097,152 nodes/depth 32. Parent output permits 33,554,432 nodes
and depth 40, retaining all traces without truncation or duplicate full requests.
At most 8 × 16 = 128 actual residual/load/lookup evaluations are permitted.

Hashes bind the complete validated native root and complete response, omitting
only `evaluation_sha256` from its own digest, using sorted compact UTF-8 JSON.
Persistent export failure clears both hashes and payload but keeps accepted
counts. Hashes authenticate no source, identity, runtime or scientific claim.
Caller geometry and polar sources remain unverified; the evaluator fetches no
dataset and establishes no data-source permission or redistribution right.

No CFD, radial interaction, rotor-data validation, discretization error estimate,
continuous polar coverage, or convergence guarantee is established. All inherited
local wake, tip-factor, polar and sampled-root limitations apply. Physical
validation, numerical qualification and runtime identity remain `NOT_ESTABLISHED`.
