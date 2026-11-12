`evaluate_solved_wrench_sensitivity` contract:

- Exact root keys: `evaluation`, `solve`, `sensitivity_settings`. Evaluation: `solved_static_wrench_sensitivity_experimental`. `solve` is a complete accepted static-wrench request. Settings: `perturbations`, `force_scale_n`, `moment_scale_nm`, `relative_singular_value_cutoff`.
- Run the actual solve first. If residual unmet, return the computed solve, `sensitivity_state: NOT_RUN_RESIDUAL_UNMET`, and `sensitivity: null`; run no probes.
- If residual met, evaluate actual three-resolution sensitivity at selected speeds. Require a fresh nominal assembly matching the actual solve assembly. State: `COMPUTED_AT_RESIDUAL_MET_POINT`.
- Combined preflight: `sum_annuli * (max_solver_evaluations + 1 + 6N) <= 32768`; maximum 155 calls and 49152 JSON values.
- Require `lower_bracket - h > 0` and representable perturbations at both bracket ends. Validate the selected actual request again.
- Hash complete actual-solve and sensitivity raw records. Inner probe-result SHA checks establish syntax/data integrity only; nested outputs provide no independent raw central-difference proof.
- Unexpected failures are atomic and retain the hash. Invalid requests have no hash.
- Hold air, geometry, mass, and CG fixed. Physical trim, control authority, stability, global feasibility, and error certification are not established; `physical_validation`, `numerical_qualification`, and `runtime_identity` are each `NOT_ESTABLISHED`, `evidence_level` is `unverified`, and `aircraft_status` and `feasibility` are null.
- No API or deployment qualification is established.
