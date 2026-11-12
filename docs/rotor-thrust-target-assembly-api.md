# Rotor thrust target assembly API

Prefix: `/api/drone/rotor-thrust-target-assembly`; GET `/catalog`, POST `/evaluate`. Bearer/cookie auth; cookie POSTs require same origin (CSRF). Hosted allowlist: exact paths only; no trailing slash/suffix.

Schema: `prescribed_rotor_thrust_target_assembly_v1`; evaluation: `prescribed_rotor_thrust_target_assembly_experimental`.
Root: `evaluation, assembly_template, targets`. Template: accepted rotor assembly; hover nodes omit `angular_speed_rad_s`. Ordered targets, exact keys: `node, target_thrust_n, angular_speed_bracket_rad_s, absolute_thrust_tolerance_n, max_evaluations`.

Limits: 1–15 rotors; per rotor 2–64 integer evaluations, 1–512 annuli; Σ(max_evaluations×annuli)≤32768; final Σannuli≤8192. Positive increasing bracket in rad/s; target>tolerance>0.

Decode strict UTF-8 JSON, reject duplicates/NaN/nonobjects, then `_json(body,budget=32768)`: depth≤10, container≤256, string≤2000, integer≤1023 bits, finite numbers. Violations: 422 `Invalid rotor thrust target assembly request.`
`RotorThrustTargetAssemblyBodyLimit`: body≤131072 bytes, declared/streamed excess 413 before model calls; invalid Content-Length 400.

Call `evaluate_rotor_thrust_target_assembly` via `run_in_threadpool`. Caller thrusts; reference air first binds shared density; final assembly recomputes air+rotors. Every inverse must reach `TARGET_RESIDUAL_MET`; otherwise atomic 200 `EXECUTION_FAILED`, generic reason, empty stages/transfers/outputs/units. Semantic invalidity: 200 `GRAPH_INVALID`, no hashes.

With request hash, add `input_sha256=request_sha256`, then `evaluation_sha256=sha256_record(result)` over the entire result before its own field (success/failure). Stages hash full raw records; inner candidate result SHA is syntax-checked only. No physical proof.

`COMPUTED_EXPERIMENTAL`, unverified; physical/numerical qualification/runtime identity `NOT_ESTABLISHED`; aircraft/feasibility null. Isolated small-angle bisection: no extrapolation, monotonicity/uniqueness proof, interference, loss/Re/Mach polars, trim/control allocation, physical accuracy, electrical power or installed-flight qualification; no new physics.

Python: [core](rotor-thrust-target-assembly.md).
