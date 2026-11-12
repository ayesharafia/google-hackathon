# Static wrench solve API

GET `/api/drone/static-wrench-solve/catalog`; POST `/api/drone/static-wrench-solve/evaluate`. Bearer/cookie auth; cookie POST requires same-origin CSRF checks. Hosted paths are exact. Evaluation runs in a threadpool.

Schema: `bounded_static_wrench_solve_v1`. Exact root:
`evaluation, assembly_template, rotor_speed_bounds, required_net_force_body_n, required_net_moment_cg_body_nm, absolute_force_tolerance_n, absolute_moment_tolerance_nm, max_evaluations`.
Evaluation: `bounded_static_wrench_solve_experimental`.

Template: accepted rotor assembly; hover nodes omit `angular_speed_rad_s`. Bounds follow rotor order; exact keys: `node, angular_speed_bracket_rad_s, initial_angular_speed_rad_s`. Positive increasing bracket, initial inside; rad/s. Body-frame target 3-vectors: force N, moment about CG N*m; positive absolute tolerances.

Strict UTF-8 JSON object; reject duplicates/NaN/nonfinite numbers. Limits: 128 KiB, 32768 values, depth 10, 256 items/container, strings 2000 characters, integers 1023 bits. Malformed: 422.

1–15 rotors, 1–512 annuli/rotor; integer `max_evaluations` 2–64 counts actual calls, including finite differences and one reserved fresh final call. `max_evaluations * sum(annuli) <= 32768`.

Outcomes `RESIDUAL_MET`, `EVALUATION_LIMIT`, `SOLVER_STOPPED` return `COMPUTED_EXPERIMENTAL`. Only fresh final six scaled residuals all absolute <=1 permit residual success. Numerically unsolved is not execution failure.

Preflight: 200 `GRAPH_INVALID`, no hash. Private execution errors: atomic 200 `EXECUTION_FAILED`, empty stages/outputs/units, request hash retained. `input_sha256=request_sha256`; `evaluation_sha256` hashes the response before itself. Stages hash actual raw records; inner graph result SHA checks syntax only.

Unverified; no physical trim, uniqueness, global feasibility, control authority, installed-flight or physical qualification.

[Core](static-wrench-solve.md).
