# P00.2 independent physics review

The reviewer is Claude Opus 5.5. The final candidate is 0bc092fa160319eab8b4e9113307def3986992c3. This code review does not upgrade immutable machine evidence, establish aircraft validation, or authorize release. The reviewer disclosed historical authorship of inherited reference/integration code.

## Final increment and accepted replay

# Independent physics review, final increment: P00.2 at `0bc092f`

| Item | Value |
|---|---|
| Candidate | `0bc092fa160319eab8b4e9113307def3986992c3` (HEAD) |
| Increment reviewed | `6dbf558..0bc092f`: commits `2dbbe2c` and `0bc092f`; files `plots.py`, `slice_eligibility.py` and `test_slice_eligibility.py` |
| Tree | Clean apart from two `.DS_Store` files and an untracked `docs/qa/baseline-findings-closure.md`. I did not review that document; it is not part of the candidate. |
| Replay | `.backend/p00-findings-accepted` |
| Reviewer | Claude Opus 5.5 (Anthropic). Different model family from the implementing agent. |
| Write scope | Read-only. No source, artifact, git or status changes. |

My earlier record still stands: the P00.2 reviews of `1dbbc51` and `6dbf558`, the independent archive and envelope computations, and the disclosure that this reviewer originally wrote `reference_impl/`, the ancestor of `integrate_surface_loads` and `reconcile`. That earlier PASS was not reused as acceptance. The increment was re-checked from scratch, and the accepted replay was re-verified.

---

## 1. Verdict

**PASS for bounded P00.2 at `0bc092f`.**

- No Critical, High or Medium findings.
- One new Low finding (N-L1, §3). It does not change any published eligibility decision.
- Evidence remains `unverified` and independent review remains `pending` in `results.json`. This review does not upgrade either.
- This is not aircraft validation, human engineering approval, merge or tag approval, or completion of any later roadmap item.

---

## 2. Methods

1. **Code.** Read `git diff 6dbf558 0bc092f` for `src`, `scripts` and `tests`.
2. **Independent re-implementation of the velocity metric.** I wrote my own computation using only `.venv/bin/python` with numpy and scipy. It does not import physimesh.
   - It re-parses each mesh's native `U_yNormal.raw`, after checking each file's SHA-256 against the bound `source_sha256`.
   - It rebuilds the policy grid from the policy text: x from −1.5D to 4D, z from ±1.5D, 180×360 points, with the sphere interior masked out.
   - It interpolates the three velocity components linearly with `griddata`.
   - It forms the span as the norm of the per-component peak-to-peak range, and the change as the magnitude of the vector difference.
   - It computes RMS and peak change at the 1e-6 D and 5e-6 D subsets, and the speed-only metric for comparison.
3. **Overflow and duplicate-point behaviour.** Print-only numpy and scipy probes.
4. **Accepted package.**
   - Hashed all 27 members against `hashes.json`.
   - Recomputed the payload manifest digest, the package revision, and the study binding.
   - Read status, plot set, limitations, and all nine eligibility reports.
5. **Original archive.** Re-hashed `demo-reviewed` `hashes.json`, which gives `e5c2a75c…cbc9` and matches the frozen inventory. Re-hashed all 33 members against it.
6. **Policy pin.** Hashed the policy file as committed at `0bc092f`: `babdcdb9…13a7`, which matches the pinned registry digest.
7. **Not performed.** I did not run pytest, the API, the UI, or the backend.

---

## 3. Increment findings

### Velocity direction sensitivity (`slice_eligibility.py:73-103`, `plots.py:203`)

**The defect being fixed.** On `6dbf558` the speed slice was judged on |U| alone. A complete reversal of U leaves |U| unchanged, so it would have passed. The same speed grid feeds `fine_vectors` and `fine_streamlines`, so those views could have shown a reversed flow while counting as "eligible". I missed this in my earlier passes; the implementer found it.

**The fix.** For a vector field, the change is now the magnitude of the vector difference, |ΔU|, normalised by the norm of the per-component span. Each report records `compared_quantity: world_velocity_vector`. Pressure and vorticity still use signed scalar differences, which already respond to sign. **Correct.**

**Ordinary reversal test.**
- My probe confirms that, for coincident (x, z) points, `griddata` keeps the first duplicate.
  - The baseline grid therefore holds the off-plane U = (−1, 0, 0); both sensitivity subsets hold (+1, 0, 0).
  - Speed change: 0. Vector change: 2.
  - The baseline field is constant, so span = 0, the code falls back to magnitude = 1, and peak change = 2 ≫ 0.05, giving **refused**.
- A speed-only metric would have passed this case.
- Minor fragility: the test depends on how scipy/Qhull resolves duplicate points. If that changed, the test would fail loudly rather than pass silently. A non-coincident reversal fixture would be more robust (Low, test quality only).

**Independent recomputation on the actual data.** My code matches the published values to five significant figures on every mesh.

| Mesh | Span (m/s) | 1e-6 D: RMS / peak change | 5e-6 D: peak change | Speed-only peak, same span | Status |
|---|---|---|---|---|---|
| coarse | 1.50365 | 0.00078 / 0.03296 | 0 (no samples dropped) | 0.03089 | eligible |
| medium | 1.52179 | 0.00674 / 0.15505 | 0.03449 | 0.1218 | refused |
| fine | 1.51933 | 0.00094 / **0.04626** | 0 (no samples dropped) | 0.02983 | eligible |

- External coverage is 1.0 everywhere.
- Retained sample counts match: 3019, 6573/6738, 14059.
- The direction component is physically material on the fine mesh: 0.0463 with direction versus 0.0298 for speed alone.

### Refusal of non-finite norms and metrics

**Span overflow.**
- `np.linalg.norm([2e154, 0, 0])` returns `inf`, because it squares without rescaling; the true value is 2e154 (`math.hypot`).
- The ±1e154 test therefore hits `nonfinite sensitivity normalization`. The function returns before writing any metric, so the report contains no non-finite value and serialises with `allow_nan=False`.
- This refusal is spurious, since the true span is finite. But it fails safe, and such magnitudes are non-physical. Informational only.

**Overflow in the change metrics.**
- A finite difference of 2e200 squares to `inf`, and the peak-to-peak range of ±1e308 is `inf`.
- In both cases the code raises before `item.update`, so the result is a failed subset, a refusal, and no NaN or inf in the report.

**Other guards.**
- Scale is at least `tiny` (the smallest positive double), so 0/0 cannot occur.
- Interpolated vector norms that overflow are excluded through the finiteness mask. That lowers coverage, which in turn leads to refusal.
- `errstate` suppresses only the floating-point warnings; the finiteness checks that follow are explicit. **Correct.**

### N-L1 (Low, new): the metric definition changed under an unchanged policy digest

The policy file is byte-identical (`babdcdb9…`), yet "change relative to the baseline external field span" now means something different for velocity. The vector span (about 1.50 m/s) is larger than the old speed range (about 1.1 m/s), so the same magnitude-only change now scores lower. Coarse speed went from 0.0423 under `6dbf558` to 0.0330 now. For pure magnitude changes the normalisation is about 27% looser, while direction changes are newly caught.

- No published decision changed: the same four views are withheld and the same 11 plots appear.
- Every run is still `retrospective`.
- But the C3 guarantee was "a changed policy cannot silently admit views". Part of the policy's meaning now lives in code that the pinned digest does not cover.

**Recommendation (P01.1):** put the metric definition (`compared_quantity` and normalisation) into the versioned policy or registration record, or bump the version before any run is registered against `sphere_slice_policy_v1`. Reports already state the definition, which mitigates this for now.

---

## 4. Accepted replay (`.backend/p00-findings-accepted`), independently verified

**Package integrity and identity.**
- All 27 members match `hashes.json`.
- Payload manifest digest matches.
- Revision recomputed as **`75967364…71f1`**, matching `publication.json`.
- `study_sha256` equals SHA-256 of `run_group.json` (`acd1b871…ff6a`), equals the provenance hash, and its first 16 characters equal the package ID.
- The revision differs from v3 (`b84b8966…`) because report content changed. That is expected.

**Eligibility, plots and limitations.**
- All nine reports carry policy `babdcdb9…` and `registration: retrospective`.
- The package copy of `slice_eligibility.json` is byte-identical to the replay's copy.
- The plot set is 11, with `coarse_vorticity` and all `medium_*` withheld; each reason names the failing metric.
- The limitation "retrospective replay … not preregistration of the original CFD campaign" is present.

**Moments (unchanged).**
- Maximum errors: 1.09e-14, 3.75e-15 and 2.73e-15 N·m, against a 3.927e-10 N·m floor.
- Discrimination flags: coarse [T, T, T], medium [F, F, T], fine [F, T, T]. These equal my earlier independent derivation.

**Original archive.** Unchanged: `e5c2a75c…`, and all 33 members verified.

---

## 5. Remaining findings and limits

| ID | Severity | Item |
|---|---|---|
| N-L1 | Low | Velocity metric semantics changed under the same policy digest; bind the metric definition into the version before prospective use (§3) |
| N-L2 | Low | Fine speed passes with a thin margin: 0.0463 against a 0.05 limit |
| N-L3 | Low | The reversal test depends on scipy/Qhull keeping the first duplicate point |
| N-I1 | Info | Spurious overflow refusal (2e154 span reported as `inf`); fails safe |
| L1–L9 | Low/Info | Carried from my `6dbf558` review: registration is procedural with no external timestamp; single-version policy loader; thresholds authored retrospectively and the 5e-6 D subset drops no samples on coarse and fine; no registered three-grid campaign yet; q·A·D floor scaling for future adapters; rotor axis vs. force direction unchecked; I did not run the tests, API or UI; the closure document has not been reviewed by me; the raw status literal and the trim model are deferred to P01.1 and P04 |

**Task-observer:** none logged. This is a read-only session, and no writes to the observation log were permitted.

## Earlier full correction review at 6dbf558

# Independent physics review, follow-up: P00.2 final verdict

| Item | Value |
|---|---|
| Candidate | `6dbf558fff3f863d2e43fccddc9a2173c494d0da` (HEAD). The tree was clean apart from two `.DS_Store` files both before and after this review. |
| Compared against | My previous candidate `1dbbc51`. Changes come from commits `4081999` and `6dbf558`, across 22 files. |
| Evidence | Replay in `.backend/p00-findings-v3`, package `results/acd1b8716144aeaa`. Original archive `.backend/demo-reviewed/results/acd1b8716144aeaa`. |
| Reviewer | Claude Opus 5.5, Anthropic. This is a different model family from the implementation agent. |
| Write scope | None. No edits, file writes, git changes, or status changes. |

My previous CONDITIONAL PASS has **not** been carried over as acceptance. Every condition below was re-checked from the pinned code and from evidence I computed myself.

**Independence disclosure (unchanged).** Earlier sessions of this reviewer wrote `reference_impl/`, which is the source of `integrate_surface_loads` and `reconcile`. My review of those two functions is not independent. Everything I verified independently concerns the new code and the new evidence.

---

## 1. Final verdict

**PASS for P00.2's bounded scope.** That scope is the sphere Re = 100 software-verification pipeline plus the labelled illustrative screening.

- Conditions C1, C2 and C3 are closed. Each closure is backed by code at the pinned commit and by evidence I recomputed.
- The residuals R5, R8, R11, RN and the overflow defect at HEAD `1dbbc51` are resolved.
- No Critical, High or Medium findings remain. The pending limitations in §5 are Low or informational, and none blocks the P00.2 gate.
- Evidence stays `unverified` and independent review stays `pending` in the package's `results.json`. **This review does not upgrade any status.**
- This is not aircraft validation, not human engineering approval, and not a statement that production work is complete.

| Item | Verdict |
|---|---|
| F4 / C1 moment floor and discrimination | **PASS** |
| F5 infeasible vs. missing inputs (+ R5) | **PASS** |
| F10 status labels | **PASS** (the raw `ResultsV1` literal stays until P01.1, as the plan allows) |
| F6 / C2 acceleration margin | **PASS** |
| F8 pack consistency (+ R8) | **PASS** |
| F11 trim scope (+ R11, overflow fix) | **PASS** |
| F7 / C3 slice eligibility and registration | **PASS**, with Low limitations L1–L4 |
| N1 publication identity (+ RN) | **PASS**. I verified it independently this time. |

---

## 2. Methods actually used

1. **Code.** I read the full `git diff 1dbbc51 6dbf558` for `src`, `scripts`, `web` and the tests. I also read the input-hashing order in `src/physimesh/solver/runner.py` at the pinned commit with `git show`.
2. **Independent recomputation.** I used read-only inline `python3` with only the standard library (no `physimesh` import), plus `shasum` and `git show`.
3. **Publication identity.**
   - I hashed every member of the v3 package and compared each against `hashes.json`. All 27 matched, with none missing and none extra.
   - I recomputed the payload-manifest digest (every member except `hashes.json` and `publication.json`, canonical JSON) and got **`81d58fd0…43eb`**, which matches.
   - I recomputed the package revision and got **`b84b8966…d8c9`**, which matches `publication.json`.
   - The study digest equals sha256(`run_group.json` bytes) = `acd1b871…ff6a`. It also equals the provenance digest in `results.json`, and its first 16 characters equal both `run_group_id` and the package directory name.
4. **Original archive.**
   - The `hashes.json` digest is `e5c2a75c…cbc9`, which equals the frozen inventory entry at `docs/qa/production-baseline.json:676`.
   - All 33 members match their manifest.
   - No `publication.json` or slice file was added.
5. **Moments.** I recomputed the floor, compared each component's `component_discriminating` flag with my own `|native| ≥ 2·floor` calculation, and worked out sign-flip detectability for every component.
6. **Slices.**
   - I hashed each field's native source and compared it with the per-field `source_sha256`.
   - I checked each mesh's run-record digest against the run group, and whether the run record contains a registration input.
   - I hashed the pinned policy file.
   - I re-counted samples directly from the raw `p_yNormal.raw` files: the total, the count within 10⁻⁶ D, and the count within 5×10⁻⁶ D.
   - I read the metrics, failure names, captions and limitations.
7. **Hand derivations.** Origin transfer of the fixture, the detection threshold implied by the 2·floor flag, and the example cases' kinematics.
8. **Not performed.** I did not run pytest, the API, the backend container, or a full independent griddata re-interpolation of the slice metrics. The slice metrics themselves come from the implementation's code, which assembly now re-derives from verified native bytes.

---

## 3. Findings

### F4 / C1: moment floor and discrimination (PASS)

**Origin-transfer test.** M_o = M₀ − o × ΣF with M₀ = (6, −2, 1) and ΣF = (−2, −3, 0).
- For o = (1, 0, 0): o × ΣF = (0·0 − 0·(−3), 0·(−2) − 1·0, 1·(−3) − 0·(−2)) = (0, 0, −3).
- So M_o = (6, −2, **4**).

`tests/postpro/test_moment_policy.py` now:
- integrates the fixture again with `moment_origin_m=[1,0,0]` and expects (6, −2, 4), which matches my derivation;
- asserts ΣF = (−2, −3, 0);
- uses the real shifted result as the "wrong origin" mutation, which must fail against the origin-0 reference.

An implementation that ignored the origin argument would now fail. The defect I raised against `1dbbc51` is closed.

**Floor and errors on actual data (v3 `load_results.json`).** The floor is q·A·D·10⁻⁹ = 0.5 × (π/4) × 1 × 10⁻⁹ = **3.92699×10⁻¹⁰ N·m**.

| Mesh | Max error (N·m) | Floor / error | `component_discriminating` | My `|n| ≥ 2·floor` | Sign flip detectable |
|---|---|---|---|---|---|
| coarse | 1.09×10⁻¹⁴ | 3.6×10⁴ | [T, T, T] | [T, T, T] | [T, T, T] |
| medium | 3.75×10⁻¹⁵ | 1.0×10⁵ | [F, F, T] | [F, F, T] | [F, F, T] |
| fine | 2.73×10⁻¹⁵ | 1.4×10⁵ | [F, T, T] | [F, T, T] | [F, T, T] |

The published flags agree exactly with my calculation, and with which sign errors the gate can actually detect.

Why 2·floor is a sensible cut. A component is checked against an allowance of floor + 10⁻³·|n|.
- A sign flip makes the error 2|n|, which exceeds the allowance once |n| > 0.5·floor.
- A 100% magnitude error makes the error |n|, which exceeds the allowance once |n| > 1.001·floor.

So at |n| ≥ 2·floor, both sign errors and 100% magnitude errors are guaranteed to be caught. The flag is therefore conservative. The below-floor qualification text is unchanged and correct.

### F5 + R5: infeasible vs. missing inputs (PASS)

- Behaviour is unchanged from my previous check, which I re-confirmed by hand: 20 × 250 × 0.8 × 0.8 × 3600 = 11.52 MJ, and the 600 s hover needs 24 kW × 600 s = 14.4 MJ, so it is energy-infeasible.
- In the v3 example, `energy_limit_request` has a 600 s hover and `usable_energy_j` = 11,520,000.
- **R5 closed.** Each case now carries `eligibility` (`screening.py`, the `CaseCapacity` field and the logic around lines 249–256). Values are `excluded_infeasible`, `excluded_unsupported`, both, or `vertical_screening_only`, and a test covers it.
- The raw diagnostic numbers remain in JSON but are explicitly tagged excluded. No headline is published.

### F6 / C2: acceleration margin limited to 2 s (PASS)

- The limit `MAX_MARGIN_DURATION_S = 2.0` is commented as an illustration policy, not a physical limit.
- It is enforced in two places:
  - `case_scope`: the duration must satisfy 0 < t ≤ 2 for `instantaneous_vertical_margin`, and non-numeric or boolean durations are refused;
  - `capacity_from_cases`: any case with |a_z| > 10⁻⁹ and t > 2 s becomes `unsupported_scope`.
- The 2 s boundary is consistent between the two gates (≤ 2 allowed, > 2 refused).
- 180 s is refused in both layers, with tests.
- The v3 example climb is `acceleration_margin` for 2 s with a_z = 0.6 m/s², giving Δv = 1.2 m/s. Constant-velocity cases are not affected.
- No trajectory or mission-integration claim remains.

### F8 + R8: pack consistency and reserve conventions (PASS)

- The pack-consistency check and its binding to the approved snapshot are unchanged from my previous check.
- **R8 closed.** The screen now names both reserve conventions:
  - `results.js`: "reserve held back from usable pack energy once";
  - `results.html`: the A/B/C exercise "adds reserve as a fraction of mission demand".
- The two conventions are not silently harmonized. At r = 0.2 they allow 11.52 MJ vs. 12.0 MJ, about 4%. This is disclosed, which is acceptable for illustrative screening.
- The pack-parameter reads now sit inside the `try`, with `AttributeError` also caught. A malformed item returns a structured refusal, and a test covers it.

### F11 + R11 + overflow: trim scope (PASS)

- **R11 closed.** The unconditional "Trim eligibility … meets the restricted vertical screen" sentence is gone. It is replaced by "Moment balance, control allocation and payload CG remain unevaluated; any restricted-screen failure withholds the headline" (`api/screening.py:159`).
- **Overflow closed.**
  - The horizontal force sum now uses `math.fsum`, and the scale uses `math.hypot` sums.
  - `OverflowError` and non-finite intermediates are blocked.
  - `_vector3` refuses boolean, string and non-`Real` entries.
  - The 10²⁰⁰ and 10³⁰⁸ side-force regression tests assert that no headline is published.
- All moment, trim, control and CG effects remain explicitly unevaluated, and the scope stays "vertical screening ceiling only".
- No unsupported claim gets through at headline level.
- Unchanged Low note: each rotor's force vector is still not checked against its declared axis. The moment disclaimer covers this.

### F7 / C3: slice eligibility and registration (PASS, with Low limitations)

**Native re-derivation at publication.**
- `validate_native_reports` recomputes every field's report from the raw native cutting-plane bytes. Those bytes are checked against the run record's output hashes, and the run record is checked against the run group's `run_record_sha256`.
- The recomputed report must equal the supplied report exactly.
- `test_slice_publication_gate.py` drives the real `demo_assemble.main()` with a forged `eligible` status and a matching forged plot record. Assembly raises an error before anything is written. Native byte mutation is also refused.

My independent checks:
- All 9 per-field `source_sha256` values match the native files.
- All 3 run-record digests match the run group.
- The package's `slice_eligibility.json` is byte-identical to the replay's copy.

**Pinned policy.**
- `POLICY_DIGESTS['sphere_slice_policy_v1']` = `babdcdb9…13a7`.
- I hashed the policy file at `6dbf558` and got the same value.
- `registered_policy()` raises if the file's bytes no longer match the digest for its version. A test confirms that changing the peak limit to 0.06 under v1 is refused.

**Registration before execution.**
- `demo_run.registered_case_files` adds `system/sliceEligibility.json` (the version and digest record) to the case files.
- `runner.run_case` writes and hashes every input into the artifact store before the first `docker run` (`runner.py:79-85`, before the stage loop at line 87).
- `registration_for_run` requires that the retained file bytes equal the current registration input and the recorded input hash. Otherwise the state is `retrospective`.
- Reuse refuses a group whose policy differs. Assembly refuses a group that claims a `slice_policy` without pre-execution input for every report.

**Actual v3 state, verified.**
- The v3 run group has no `slice_policy`, and none of the 3 run records contains the registration input.
- All 9 reports therefore say `registration.state: retrospective`, and `results.json` keeps the retrospective limitation. This is honest and correct for the original campaign.

**Metrics (re-counted).**

| Mesh | Samples within 10⁻⁶ D / 5×10⁻⁶ D / total | max\|y\| | Withheld fields |
|---|---|---|---|
| coarse | 3019 / 3061 / 3061 | 2.53×10⁻⁶ | vorticity (peak change 0.0565) |
| medium | 6573 / 6738 / 6764 | 9.28×10⁻⁶ | speed, pressure, vorticity (peak changes 0.168, 0.190, 0.153) |
| fine | 14059 / 14281 / 14281 | 4.70×10⁻⁶ | none |

- The per-field failure is now named "normalized peak change failed at 1e-06 D".
- Exactly four views are withheld. The PNG set is 11 plots, with `coarse_vorticity` and every `medium_*` view absent.

**Captions fixed.** The captions now read "Bounds shared only across eligible views: coarse, fine" for speed and pressure, and "…: fine" for vorticity. Fine vorticity's range of ±18.466 equals its own extremum, which is consistent.

### N1 + RN: publication identity (PASS, independently verified)

- See §2, item 3: all 27 members match, and the manifest digest, revision and study binding all match my recomputation.
- The new revision `b84b8966…` differs from the `1dbbc51` replay's `9941775c…` because content changed (captions and reports) while the study is the same. This is the intended behaviour.
- **RN closed** (`api/results.py:108-112`):
  - the manifest's `run_group.json` digest must equal the provenance digest;
  - the identity's `study_id` must equal `run_group_id`;
  - a re-hashed `run_group` that disagrees returns 409, with a test.
- The original archive is unchanged (§2, item 4).
- The identity does not touch review status: the route's qualification text is present, and `results.json` still says `unverified` and `pending`.

---

## 4. Conditions

**C1, C2 and C3 are closed** within the bounded P00.2 plan. No new conditions.

---

## 5. Pending limitations (none blocks P00.2)

- **L1. Registration is enforced by process, not cryptography.** The "pre-execution" claim rests on the runner hashing inputs before execution, plus the retained input hash. There is no external timestamp or signature. I did not inspect the claimed 20-iteration registered backend fixture run. I verified the mechanism in code and tests only.
- **L2. One policy version at a time.** `POLICY_PATH` and `registration_input()` assume a single current version. Introducing v2 would make v1-registered runs fail closed, not re-evaluate under v1. A version registry with multiple loadable policies is needed before a second version exists (P01.1).
- **L3. Retrospective thresholds for existing outputs.** The 1% and 5% thresholds were written with this data visible. Passing margins are thin: speed peak change is 0.042 on coarse and 0.041 on fine, against 0.05. The 5×10⁻⁶ D subset keeps every sample on coarse and fine, so it gives zero information there. The cause of the off-plane coordinates is still not established. My second-order estimate (δ²/2z ≈ 10⁻¹⁰ D) says the geometric error itself is negligible: refusals reflect how sensitive the interpolation is to dropping samples, not wrong geometry.
- **L4. No new three-grid campaign under registration exists.** The first prospective evidence would come from a future run.
- **L5. Moment-floor scale for future adapters.** The floor scales with q·A·D. For adapters that use absolute pressure, the scale should account for Σ|f_face|·L. Revisit in P01/P02.
- **L6. Rotor force direction is not checked against the declared axis** in screening. This is covered by the trim disclaimer.
- **L7. What I did not run.** Test results (claimed: 363 unit, 118 reference, 3 backend) were not re-run by me. I did not exercise the API or UI live, and I did not reproduce the interpolation metrics independently. Integrity, counts and bindings were recomputed.
- **L8. Acceptance document pending.** `docs/qa/baseline-findings-closure.md` (`plan.md:362`) is still to be written from these receipts.
- **L9. Scope.** The raw `numerical_checks_passed` literal and the structured screening successor contract are deferred to P01.1. The trim model is deferred to WP12/P04.

---

**Task-observer:** none logged. You asked for no writes, so the observation log was not touched in this session either.
