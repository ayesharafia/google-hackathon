# hover-thrust-target-api.md

Authenticated hosted routes (existing CSRF rules):
- GET `/api/drone/hover-thrust-target/catalog`
- POST `/api/drone/hover-thrust-target/evaluate`

Exact root keys: `evaluation`, `rotor_template`, `target_thrust_n`, `angular_speed_bracket_rad_s`, `absolute_thrust_tolerance_n`, `max_evaluations`. Evaluation: `isolated_hover_thrust_target_experimental`.

Template: accepted BEMT request minus angular speed; all other inputs fixed. Actual forward solves at both endpoints, then bisection in an explicit positive increasing bracket in rad/s, **not RPM**. Target > tolerance > 0. Integer max evaluations 2–64; annuli 1–512; product ≤32768. Body ≤128 KiB; JSON ≤8192 values, depth ≤10.

All four outcomes have `COMPUTED_EXPERIMENTAL`, never feasibility:

- `TARGET_RESIDUAL_MET`: model residual only; no physical accuracy, trim or power feasibility.
- `TARGET_NOT_BRACKETED`: no extrapolation.
- `EVALUATION_LIMIT`: budget exhausted.
- `FLOATING_POINT_STAGNATION`: no representable midpoint.

Strict malformed JSON: HTTP 422. Semantic invalidity: HTTP 200 `GRAPH_INVALID`, no hash. Execution failure: HTTP 200 `EXECUTION_FAILED`; stages, outputs and units cleared, request hash retained; generic exception reason.

`input_sha256` aliases `request_sha256`; `evaluation_sha256` hashes the response before its own field. Candidate/stage hashes cover actual forward inputs/raw results; no runtime identity or physical proof.

No losses, Re/Mach polars, interference or electrical inference. No API qualification or deployment. Unrelated to ledger/dynamics refinement or frames.
