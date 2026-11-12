# Solved-wrench sensitivity API

See [core documentation](solved-wrench-sensitivity.md).

- `GET /api/drone/solved-wrench-sensitivity/catalog`
- `POST /api/drone/solved-wrench-sensitivity/evaluate`

Schema: `solved_static_wrench_sensitivity_v1`; evaluation: `solved_static_wrench_sensitivity_experimental`.

The exact root keys are `evaluation`, `solve`, `sensitivity_settings`. `solve` carries the complete actual-solver WS request. Settings: `perturbations`, `force_scale_n`, `moment_scale_nm`, `relative_singular_value_cutoff`.

Run the actual solve first. Probe only at `RESIDUAL_MET`. Otherwise return computed `NOT_RUN_RESIDUAL_UNMET`, null sensitivity and no probes; this is not an error. Success is `COMPUTED_AT_RESIDUAL_MET_POINT`; the fresh nominal must match the final solve.

Combined budget: `Σ annuli*(maxeval+1+6N) <= 32768`; limits: 155 max calls, 15 rotors, 512 annuli.

JSON limits: 49,152 values, 128 KiB, depth 10, 256 items, 2,000-character strings, integer bound 1023 bits. Require strict UTF-8 and a root dictionary; reject duplicate keys and NaN. Nested solver/sensitivity limit: 32,768 values.

Bearer/cookie authentication, cookie CSRF and exact hosted paths apply. Computation runs in the threadpool.

`request_sha256` and `input_sha256` bind the whole bridge input. `evaluation_sha256` binds the whole HTTP response before its own field is added. Outer stage hashes bind the actual whole upstream requests and raw responses. Only nested inner-probe result hashes receive syntax checks; they provide no independent raw plus/minus proof. Unexpected failure is atomic and retains hashes; invalid input has no hash.

All three qualifications remain `NOT_ESTABLISHED`, with null verdicts. Results establish neither physical trim, control authority, stability nor global feasibility, and provide no error certificate or API qualification.
