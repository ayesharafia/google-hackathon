# Wrench sensitivity API

- `GET /api/drone/wrench-sensitivity/catalog`
- `POST /api/drone/wrench-sensitivity/evaluate`

Schema: `static_wrench_sensitivity_v1`. Evaluation: `static_wrench_sensitivity_experimental`.

The request root contains exactly `evaluation`, `assembly`, `perturbations`, `force_scale_n`, `moment_scale_nm`, and `relative_singular_value_cutoff`.

Supply a complete assembly, including nominal speed, and ordered perturbations specifying node, h, and speed scale. h must be positive and finite; probes must remain distinct at all three levels.

Evaluation executes the actual nominal case plus six calls per perturbation: `1 + 6N`. Limits: 1–15 rotors, 512 annuli per rotor, at most 91 calls, and `calls × sum(annuli) ≤ 32768`.

JSON guards: 128 KiB, 32,768 values, depth 10, 256 items per container, 2,000-character strings, and 1,023-bit integers. Require a UTF-8 object; reject duplicate keys and NaN/nonfinite values.

Bearer/cookie authentication and cookie POST same-origin CSRF checks apply; hosted mode allows only the exact catalog/evaluate paths. Evaluation runs in a thread pool.

Force derivatives use N/(rad/s); moment derivatives use N*m/(rad/s). Form each dimensionless column by multiplying by `speed_scale_rad_s`, then divide force/moment rows by the positive finite force/moment scales. SVD retains values strictly above the relative cutoff times the largest singular value; an all-zero matrix has rank 0.

Three levels and two changes provide no error certificate, control-authority, trim, or global-feasibility proof.

Failures are generic and atomic. Retain the valid request hash on evaluation failure; invalid input has no hash. Hashes bind metadata. Whole actual input and raw stage hashes bind the records used. Only inner graph result_sha256 checks are syntax-only; hashes do not establish physical qualification.

`physical_validation`, `numerical_qualification`, and `runtime_identity` are all `NOT_ESTABLISHED`; `evidence_level` is `unverified`; `aircraft_status` and `feasibility` are both `null`. No deployment or API qualification is established.

See [core documentation](wrench-sensitivity.md).
