# Ledger solved sensitivity API

GET `/api/drone/ledger-solved-sensitivity/catalog`; POST `/api/drone/ledger-solved-sensitivity/evaluate`.
These are the exact hosted paths. Evaluation runs in a threadpool under authentication and CSRF protection.

CATALOG `schema_version` is `ledger_solved_wrench_sensitivity_v1`; this is not a request field.
Request fields are exactly `evaluation`, `ledger`, and `analysis_template`.
Root EVALUATION is `ledger_solved_wrench_sensitivity_experimental`.
Analysis root fields are `evaluation`, `solve`, and `sensitivity_settings`.
In `solve.assembly_template`, omit `mass_kg` and `cg_body_m`.
The actual ledger is evaluated once, freezing mass and CG into the actual analysis once; inertia is unused.

Malformed, duplicate-key, nonfinite, nonobject, depth or value-budget JSON returns HTTP 422: `Invalid ledger solved sensitivity request.`
Core `GRAPH_INVALID` returns HTTP 200 without a hash.

Limits: body 131072 bytes; root 65536 values including keys; nested analysis 49152 values.
Solver and sensitivity budgets are 32768 each.
Maximum depth is 10, container size 256, string length 2000, and integer size 1023 bits.
Allow at most 15 rotors and 512 annuli per rotor; `max_evaluations` ranges from 2 through 64.
Combined work requires `sum_annuli * (max_evaluations + 1 + 6 * N) <= 32768`.

Solver outcomes are `RESIDUAL_MET`, `EVALUATION_LIMIT`, and `SOLVER_STOPPED`; only `RESIDUAL_MET` computes sensitivity.
Ordinary unmet outcomes remain `COMPUTED_EXPERIMENTAL` with null sensitivity and zero probes.

Outer hashes cover whole actual objects. Inner result SHA validation checks syntax only:
raw data is absent, providing no independent proof. Execution failure is atomic and preserves the request hash.
Unqualified physical, numerical, and runtime claims remain `NOT_ESTABLISHED`; evidence is unverified and feasibility null.

See the [core documentation](ledger-solved-sensitivity.md).
