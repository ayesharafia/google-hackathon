# Ledger dynamics refinement

`evaluate_ledger_dynamics_refinement` evaluates `ledger_dynamics_timestep_refinement_experimental`. The request root contains exactly `evaluation` and `dynamics`; `dynamics` is an accepted `ledger_rotor_dynamics` request.

Run three actual accepted kernel compositions with `(dt, N)`, `(dt/2, 2N)`, and `(dt/4, 4N)`. Require integer `N` in `1..250`, keeping every run within 1000 steps. All three must have the same exact floating-point horizon. Complete all preflight checks before the first model call. Repeat full ledger/assembly evaluation for each resolution; do not reuse cached physics.

Compare adjacent resolutions using Euclidean final-position, final-velocity, and final-angular-velocity differences. For quaternions, use the sign-invariant chord `min(norm(qA-qB), norm(qA+qB))`, not a rotation angle.

For each quantity, compute observed order as `log2(d01) - log2(d12)` only when both differences are positive; otherwise report a null observed order with UNDEFINED_ZERO_DIFFERENCE. Zero differences do not establish accuracy. This is no exact-error estimate, tolerance pass, physical validation, or universal fourth-order guarantee. Do not estimate an exact solution or report a Richardson pass.

Limit JSON input to 65,536 values; existing inner caps still apply. Any resolution failure atomically clears all outputs and stages while retaining the request hash. Invalid preflight produces no hash.

Qualifiers remain flat and unverified. Stage hashes identify data only, not runtime identity. Existing nested-provenance guard limits apply: inherited metadata is not an independent nested-result SHA.

Inherit frozen-body-load, raw-stage RK4, and ledger assumptions. No installed-flight, air-feedback, energy/thermal, or control-stability validation is provided. No HTTP/API or deployment.
