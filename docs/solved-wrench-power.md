# Solved wrench power

The available core function is `evaluate_solved_wrench_power` in `physimesh.drone.solved_wrench_power`. Its evaluation identifier is `solved_static_wrench_power_experimental`. No API is available yet.

The request is a builtin JSON dictionary with exactly `evaluation`, `solve`, and `conversion`. Unknown fields are rejected. `solve` is a complete accepted `bounded_static_wrench_solve_experimental` request; callers do not provide a second graph or a separate selected-speed vector.

`conversion` has exactly `rotors`, `auxiliary_power_w`, and `auxiliary_source`. Its rotor list follows the assembly rotor order and has exactly one entry per rotor. Each entry has exactly `node`, `conversion_efficiency`, and `conversion_source`; node identifiers must match that order. Efficiency is finite and satisfies `0 < eta <= 1`. Auxiliary power is finite and nonnegative. Boolean values are rejected for these numeric fields. Both source fields are nonblank strings of at most 2000 characters. Numeric validation also rejects nonzero subnormal values.

The nested solve has exactly `evaluation`, `assembly_template`, `rotor_speed_bounds`, `required_net_force_body_n`, `required_net_moment_cg_body_nm`, `absolute_force_tolerance_n`, `absolute_moment_tolerance_nm`, and `max_evaluations`. Bounds follow rotor order and contain exactly `node`, `angular_speed_bracket_rad_s`, and `initial_angular_speed_rad_s`. Bracket endpoints satisfy `0 < lower < upper`; the initial speed lies inside the closed bracket. Speeds are rad/s. Required force and moment are body-frame three-vectors in N and N*m about the CG; absolute tolerances are positive.

The assembly template retains its strict rotor-assembly contract: shared reference air, mass, CG, gravity direction, rotor geometry, axes, and rotation signs. Hover nodes use `isolated_hover_bemt_experimental` and omit `angular_speed_rad_s`; the solver supplies speeds. The graph retains thrust and shaft-torque targets for every rotor and the shared-air gravity target.

The entire request permits at most 49152 visited JSON values, counting dictionary keys and containers. Maximum depth is 10 with the root at depth 1; each container holds at most 256 entries, and every string, including keys, has at most 2000 characters. Strings must encode as UTF-8, floats must be finite, and integers have at most 1023 bits. Only builtin JSON types are accepted.

Nested limits remain independently enforced: 32768 values for the solve, 16384 for the assembled rotor request, and 4096 for the graph. The solver permits 1–15 rotors, integer annuli counts of 1–512 per rotor, and integer `max_evaluations` of 2–64. Its work bound is `sum_annuli * max_evaluations <= 32768`. This wrapper additionally requires `sum_annuli * (max_evaluations + 1) <= 32768`, reserving work for one power graph. Graph limits include 16 nodes, 64 connections, 32 targets, and 8192 aggregate annuli. The augmented graph needs at least `3*N + 1` targets, so its target limit further restricts this wrapper to at most 10 rotors.

All request validation, including validation of the augmented graph at initial speeds, occurs before model execution. Invalid preflight returns `GRAPH_INVALID`, no request hash, empty stages, transfers, outputs, and units, and incomplete diagnostics. It executes no models.

After preflight, the function runs the actual static-wrench solver exactly once and validates its returned contract. That single outer `solve` stage includes the solver's bounded internal assembly evaluations. Only an actual `RESIDUAL_MET` outcome permits power evaluation.

At that selected point, the function builds a fresh graph from the assembly template and selected speeds, retaining thrust, shaft torque, and shared-air gravity targets while adding each rotor's `shaft_power_w` target. It executes this graph once and validates its actual results. There is no caller-supplied duplicate graph or speed selection.

Successful execution returns `COMPUTED_EXPERIMENTAL` with complete diagnostics. `outputs` contains `solve`, `power_state`, and `power`, with corresponding `output_units`. Power has exactly two states: `COMPUTED_AT_RESIDUAL_MET_POINT` includes calculated power and stages `solve`, `power_graph`; `NOT_RUN_RESIDUAL_UNMET` includes the computed solve, null power and power units, only the `solve` stage, empty transfers, and zero power-graph executions. Unmet residuals, including `EVALUATION_LIMIT` or `SOLVER_STOPPED`, do not establish infeasibility.

Computed transfers contain the selected `angular_speeds_rad_s` and source `solve_selected_candidate`. Each power row reports node, angular speed, shaft power, shaft torque, efficiency, and electrical power. Totals report shaft power, electrical power, and auxiliary power.

The fresh graph must produce finite positive thrust and angular speed, nonnegative torque and shaft power, and exact expected output fields and units. Shaft power must agree with `Q * omega`. Loads are reconstructed from thrust, axis, signed reaction torque, rotor arm about the CG, mass, and shared-air gravity. Every rotor force, reaction torque, and moment, plus gravity force, total force, and total moment, is cross-checked against the solve assembly. Comparisons use relative and absolute tolerances of `1e-12`. These checks establish arithmetic consistency, not physical evidence.

Per-rotor electrical power is `shaft_power_w / conversion_efficiency`. Total electrical power sums those contributions and adds auxiliary power exactly once. Total shaft power excludes auxiliary power.

Every positive rotor/auxiliary contribution must remain distinguishable in accumulated power; if floating-point addition loses one, execution is refused rather than publishing a rounded-away load.

The request hash covers the validated complete request. Outer stages hash the actual complete solve request/result and, when executed, the actual complete power-graph request/result. Nested solver stage request hashes are reconstructed and checked, but their result hashes are checked only for lowercase hexadecimal SHA-256 syntax; the wrapper does not independently reconstruct every nested raw result. Hashes do not establish physical validity.

Handled runtime or returned-contract failures produce atomic `EXECUTION_FAILED`: no partial stages, transfers, outputs, or units are published, diagnostics remain incomplete, and an already established request hash is retained.

This is an isolated-hover computation with caller-declared conversion assumptions. Evidence remains `unverified`; physical validation, numerical qualification, and runtime identity remain `NOT_ESTABLISHED`; feasibility and aircraft status remain null. It establishes no installed interference, voltage, current, battery behavior, mission energy, thermal adequacy, physical validation, trim, or control authority.
