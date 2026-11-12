`ledger_static_wrench_solve_experimental/evaluate_ledger_static_wrench`

Root keys exactly: `evaluation`, `ledger`, `solve_template`.

- `ledger` accepts a `frozen_mass_ledger_experimental` request.
- `solve_template` is a complete `bounded_static_wrench_solve_experimental` request, including its `evaluation`; its `assembly_template` omits `mass_kg` and `cg_body_m`.
- Compute the actual ledger once, with actual weighted CG and inertia. Insert its frozen mass/CG into every actual solve evaluation. Report inertia in the ledger; static solving does not use it. Placeholder 1 kg/zero CG is structural only, never physics.
- Inherited bounds: 15 rotors, 512 annuli; 2–64 actual calls, counting finite differences and a reserved final call; total evaluated Σannuli ≤32768. Limit JSON to 49152 values before copying.
- Return one honestly computed outcome: `RESIDUAL_MET`, `EVALUATION_LIMIT`, or `SOLVER_STOPPED`. An unsolved result is not an execution failure.
- Guards check every candidate, residual, selection, final assembly, and raw-request binding without rerunning the model.
- Use actual two-stage whole hashes. Nested candidate/inner hashes establish data/syntax consistency only, not independent proof against the raw request. Atomic execution failure retains its hash; invalid input has no hash.

No mass feedback/evolution, trim, control authority, global feasibility, physical qualification, or API claim.
