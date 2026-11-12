# Ledger static wrench API

GET `/api/drone/ledger-static-wrench/catalog`; POST `/api/drone/ledger-static-wrench/evaluate`. Bearer/cookie auth; cookie POST requires same-origin CSRF checks. Exact hosted paths; evaluation runs in a threadpool.

Schema: `ledger_static_wrench_solve_v1`; evaluation: `ledger_static_wrench_solve_experimental`.

Root exactly: `evaluation`, `ledger`, `solve_template`. Ledger: `frozen_mass_ledger_experimental`. Solver retains `evaluation=bounded_static_wrench_solve_experimental` and its template: hover inputs omit `angular_speed_rad_s`; assembly omits `mass_kg` and `cg_body_m`.

Compute actual ledger once; freeze its mass/CG for every solver call. Report inertia; static solving does not use it.

Strict UTF-8 JSON object; reject duplicate keys, NaN/nonfinite numbers. Limits: 128 KiB body, 49152 values, depth 10, 256 items/container, strings 2000 characters, integers 1023 bits. Nested solver: 32768 values; ledger: 128 items. Malformed: 422.

1–15 rotors, 1–512 annuli/rotor. Integer `max_evaluations`: 2–64 actual calls, including finite differences and a reserved fresh final call; `max_evaluations * sum(annuli) <= 32768`.

`RESIDUAL_MET`, `EVALUATION_LIMIT`, `SOLVER_STOPPED` are honest numerical outcomes under `COMPUTED_EXPERIMENTAL`. Residual success requires all six fresh final absolute scaled residuals ≤1. Unsolved is not execution failure.

Invalid preflight: 200 `GRAPH_INVALID`, no hash. Atomic failure: 200 `EXECUTION_FAILED`, empty stages/transfers/outputs/units, request hash retained. `input_sha256=request_sha256`; `evaluation_sha256` hashes the response before itself. Stages hash whole actual ledger/solver inputs and raw results; nested request hashes bind inputs; inner result hashes check syntax only.

No physical qualification, trim, control authority, global feasibility or mass feedback.

[Core](ledger-static-wrench.md).
