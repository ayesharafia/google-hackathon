Root keys are exactly `evaluation`, `ledger`, and `analysis_template`. `evaluation` must be `ledger_solved_wrench_sensitivity_experimental`; `ledger` must be a complete accepted mass-ledger request.

`analysis_template` must be a complete accepted `solved_static_wrench_sensitivity_experimental` request, except `solve.assembly_template` must omit `mass_kg` and `cg_body_m`. Its exact keys are `evaluation`, `graph`, `air_node`, `rotors`, `gravity_direction_body`, and `property_source`.

Validate the root against a 65,536 JSON-value budget before copying. The injected analysis inherits the sensitivity request’s 49,152-value budget and combined work bound:

`sum_annuli * (max_evaluations + 1 + 6*N) <= 32768`

Here, `N` is the rotor count; all nested validation and perturbation constraints apply.

Evaluate and validate the actual ledger once. Freeze its total mass and body-frame CG, inject only those properties into a deep copy of `analysis_template`, then evaluate the actual solved-sensitivity analysis once. Ledger inertia is reported but unused; no feedback updates the frozen properties.

Preserve all three solver outcomes: `RESIDUAL_MET`, `EVALUATION_LIMIT`, and `SOLVER_STOPPED`. Sensitivity states are `COMPUTED_AT_RESIDUAL_MET_POINT` and `NOT_RUN_RESIDUAL_UNMET`. Ordinary residual-unmet solves remain computed results with null sensitivity and no probes.

Successful outputs contain `ledger` and `analysis`, with matching output units. Two outer stages, `ledger` and `solved_sensitivity`, hash each actual whole input and complete raw result using canonical `sha256_record`.

Nested solver-stage and probe raw records are absent. Reconstruct available inner requests and validate their hashes; inner result SHA-256 values receive syntax checks only, providing no independent raw-result proof. Validate metadata, bindings, exact output structures, units, reconstructed candidate algebra, speed bounds, selection, aggregate wrench, sensitivity level normalization, SVD/rank/cutoff, interlevel changes, and nominal equality with the selected solve assembly.

Invalid requests have no request hash. Execution failures retain only the root request hash and publish no partial stages, transfers, outputs, or units; failure is atomic.

`diagnostics_complete` describes data completeness only. `physical_validation`, `numerical_qualification`, and `runtime_identity` remain `NOT_ESTABLISHED`; `evidence_level` remains `unverified`, with null aircraft-status and feasibility verdicts. Results establish no physical trim, control authority, global proof, or error certificate.
