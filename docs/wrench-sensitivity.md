`evaluate_wrench_sensitivity` is a Python function with evaluation `static_wrench_sensitivity_experimental`.

- Root keys are exactly `evaluation`, `assembly`, `perturbations`, `force_scale_n`, `moment_scale_nm`, `relative_singular_value_cutoff`.
- `assembly` contains the complete accepted rotor request, including nominal angular speeds. Ordered `perturbations` entries contain `node`, `half_step_rad_s`, and `speed_scale_rad_s`.
- Evaluate the actual nominal assembly, then six fresh full-assembly probes per rotor at ±h, ±h/2, and ±h/4. Compute central force derivatives in N/(rad/s) and moment derivatives separately in N·m/(rad/s).
- Normalize dimensionlessly using caller speed, force, and moment scales. SVD rank counts singular values strictly above the relative cutoff times the largest; an all-zero matrix has rank 0. The two adjacent resolution changes across the three levels are observed differences, not derivative-error estimates or convergence proof.
- Require positive scales and steps with representable perturbations. A zero-speed failed rotor is unsupported.
- Limits: 1–15 rotors; 1–512 annuli per rotor; calls = 1+6N ≤91; summed annuli × calls ≤32768; JSON ≤32768 values.
- Hash the whole actual request and raw stages. Validate inner graph result SHA syntax only; this does not verify provenance. Failure is atomic: retain the request hash for a valid request that fails evaluation; invalid requests receive no hash.
- All qualification is `NOT_ESTABLISHED`; `evidence_level` is `unverified`; `aircraft_status` is `null`; `feasibility` is `null`. Results establish no control authority, trim, stability, installed physics, or global feasibility proof. No API qualification is established.
