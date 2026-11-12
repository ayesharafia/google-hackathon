# V148 acceptance note: adversarial stable-composition contract evidence (tests only)

Spec sha256 35c840cab479e12ec80e7b3144b9d6c03a23f0bdf8add54205af009b2eecebc6 (accepted for build 2026-11-12).
Candidate = landed file tests/drone/test_stable_polar_rotor_composition_adversarial.py (228 lines)
sha256 a9c9e9ac17bd3f9317c58abd99b5390954e177ccd38e792ec4c295f4207d7ba8. Zero source modifications.
Basis 0be1c8e9a957679a5c7551ac8be559e086787ebf. Reviewer: independently accepted 2026-11-12.

## Regression selection named for the record (task agent's run)
893 passed in 62.77s across exactly these 13 files:
test_stable_polar_rotor.py, test_stable_polar_rotor_composition_adversarial.py (the 3 new),
test_stable_section_residual.py, test_stable_section_solve.py, test_atmosphere_auth_contract.py,
test_polar_rotor.py, test_polar_rotor_api.py, test_polar_rotor_disk_pressure.py,
test_polar_rotor_disk_pressure_export.py, test_section_load.py, test_section_polar.py,
test_section_residual.py, test_section_solve.py.
Plus whole-suite collection: 9797 tests, zero collection errors.
Reviewer's independent decomposition (accepted): 3 new; 884 family across 12 name-matched files;
136 API pass; 9797 collection. Selections differ by named files; both are recorded here.

## Case C narrowed acceptance (preserves the original spec mismatch)
Original spec wording "refusal BEFORE untrusted copy/hash work" is NOT true for this path and is
not claimed. Accepted semantics, narrowed explicitly by the reviewer: after native-shape/raw-quota
admission, at most one bounded snapshot of the valid failure child is taken; it is uncommitted and
unretained on rejection; no pre-admission parent hash occurs. The test asserts zero quota commits,
zero retained counts and no quota misclassification. No demonstrated security defect; no source
fix made or needed. This mismatch between spec wording and accepted behavior is preserved here
deliberately, per reviewer instruction.

## Verified terminal states (independently reproduced)
Case A: 4x EVALUATION_BUDGET_EXHAUSTED, counts (32,32,32,32), aggregate 128 <= 256, rotor
NOT_RUN_SECTION_NOT_CONVERGED. Case B: (CONVERGED, CONVERGED, NOT_BRACKETED x6), counts
(12,12,2,2,2,2,2,2): NOT_BRACKETED = exactly 2 evaluations, early same-sign termination, never
budget exhaustion. Case C: real binary64-adjacent inputs straddle f=512 (512.0 admitted;
512.0000000000001 refused) with refusal chain NUMERICAL_POLICY_REFUSED/F_OUTSIDE_NUMERICAL_POLICY
-> RESIDUAL_BOUNDARY_FAILED -> SOLVE_BOUNDARY_FAILED.

## Labels and limits
Stable composition may be described as contract-tested for the declared matrix. NOT
production-ready, NOT physically validated; no superiority claims; no exhaustive
reachable-real-input coverage claim (declared contract matrix, not exhaustive numerical proof).
FLOAT_STAGNATION remains deferred-bounded; no global unreachability asserted. API integration
remains held; the API continues to serve legacy polar_rotor only.
