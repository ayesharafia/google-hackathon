# Independent Claude follow-up review

Candidate: `f0e4c62b2ae9a865ba0b11de1c20e5cbf31d8ed3`. User-authorized Claude textual review; no execution. Packet SHA-256: `ca052acec12c76a259b88717b91e5ee8b8f48fa18922d7b8d2a27b0663a9d4c8`.

The full reply below applies to the candidate named above. A separate standards review found historical V2 compatibility and PDF renderer-identity defects. These are corrected in a successor local V3 contract and source-bound PDF bytes; neither this receipt nor the earlier pass qualifies those later edits. Native/aircraft validation and human engineering approval remain pending.

# Independent physics review: candidate `f0e4c62b2ae9a865ba0b11de1c20e5cbf31d8ed3`

**Verdict: PASS_BOUNDED_LOCAL**

**Basis.** I reviewed only the supplied text (diff plus full files for `capacity.py`, `trim.py`, `local_results.py` and the two test files). I used no tools, did no execution, and did not check that the packet is byte-identical to the commit. I did not see `mission_capacity.py` (`solve_sequence`, `sequence_case_inputs`, `prepare_sequence`), so statements that depend on it are marked. Instructions inside the source were treated as evidence only. The baseline is the accepted `3f9b01d`.

## Requested checks: all satisfied

1. **Runtime exceptions after input eligibility become `unresolved`.**
   - `solve_hover` now catches `recompute` exceptions and returns `unresolved`. This closes prior Low #1(a), including the ε-outside-coverage inverse-interpolation case.
   - The `allocation()` wrapper converts any remaining `solve_hover` exception to `unresolved`. It is used on all three allocation paths:
     - the per-case loop;
     - the sequence `participating` solves, which closes prior Low #1(b);
     - the alternative-case headline checks.
   - Exceptions from `prepare_hover` still map to `unsupported`. The `try` structure keeps eligibility failures separate from allocation failures, which is the right split.
   - `solve_sequence` exceptions are now `unresolved` instead of `unsupported`. This is correct because `prepare_sequence` has already established eligibility. It is unverified only to the extent that `solve_sequence` might raise input-type errors that `prepare_sequence` does not pre-check.
2. **Disagreement between the joint result and participating bounds becomes `unresolved` and is retained.** This closes prior Low #2. The record carries `payload_lower_bound_kg=None`, `participating_case_bounds` and the joint `headline_candidate_checks`. It satisfies the non-feasible branch of `LocalCapacityV2`, so it is retained instead of aborting `run()`. The logic is correct:
   - A joint result above min(individual) + 1e-7 is impossible in exact arithmetic, because the joint program contains every participating case's rows. It is now refused in every situation.
   - When energy does not bind, the joint result must equal min(individual) within 1e-7. When energy binds, the joint result may lie below min(individual), and the limit is correctly attributed to `sequence_energy`. This matches the projection and interval argument from the prior review.
3. **The typed aggregate checks every participating upper bound.** This closes prior Low #3. When sequence evidence is present, the validator requires:
   - exactly one bound per case, with the key set equal to required ∪ segment cases;
   - every bound to be `feasible`;
   - headline ≤ each bound + 1e-7.

   The `or` short-circuit ensures `candidate` is non-null, because a feasible `CaseEvidence` requires one. The non-sequence path was already covered by the required-case loop. The 1e-7 kg tolerance matches between the producer and the validator.
4. **Recomputed RPM is checked explicitly.** This closes prior Low #5 (first part). After recompute, `command['rpm'] > max_rpm` is a violation, so the candidate is `unresolved`.

**Precedence.** When failures are mixed, `infeasible` still wins over `unresolved`. That is sound: one required case with a gap-free physical certificate makes the mission infeasible whatever the others report.

**Physics.** No equation, row, bound, certificate classification or energy convention changed. The physics checks from the prior review carry forward unchanged.

## Remaining findings

**Critical / High / Medium:** none.

**Low**

1. **The strict RPM comparison can produce false `unresolved` results when the RPM limit binds.** When `max_rpm` lies between two map samples, the thrust bound is `evaluate(max_rpm)`. The LP often returns thrust exactly at that bound, and converting thrust back to RPM with `np.interp` can come out one ulp above `max_rpm`. The new check has zero tolerance, so the physically interesting case where RPM is the limiter can come back `unresolved`.
   - This fails closed and is not unsound.
   - The existing fixture misses it because `max_rpm=500` sits exactly on a sample.
   - Suggested fix: use a relative tolerance of about 1e-9·`max_rpm`, or compare thrust against `thrust_bounds[i][1]`. The new test (+1e-8 on 1000 RPM) would need to keep its margin above any tolerance chosen.
2. **The exception whitelist is narrow.** `ArithmeticError` (for example `ZeroDivisionError`, or `FloatingPointError` under a non-default numpy error state) and `IndexError` from map or interp code still propagate. In that case the run aborts with no retained `unresolved` record. This fails closed. Catching these in `allocation` and in the joint solve would make retention complete.
3. **Old retained records may no longer validate.** The tightened validator now requires `participating_case_bounds` for every V2 sequence record. A record retained by earlier code with `aggregate_limit='sequence_energy'` and no bounds would now fail validation on read or export. That refusal is fail-closed and is bound to the source fingerprint, but it should be stated in the retained-record compatibility note.
4. **Mixed units in `classify_certificate` remain (prior Low #4, unchanged).** The second dependency test still compares an unscaled `|combined[i]|·(hi−lo)` with a guard in scaled units. Its only effect is extra `unsupported` labels.
5. **Test gaps:**
   - No test covers the branch where the joint payload exceeds a participating bound while energy binds.
   - No test covers a `solve_sequence` exception becoming `unresolved`.
   - None of the new `unresolved` refusals is pushed through `LocalCapacityV2` or the API to prove the "retained" claim end to end.
   - No mixed optional-segment sequence record is validated against the new key-set equality. Equality between `selected.keys()` and required ∪ segment cases depends on `sequence_case_inputs`, which I have not seen.
   - Prior gaps carry forward: no binding standalone required-case energy row inside a sequence, and no near-tie labelling between energy and a case bound.
6. **Cosmetic:** `test_local_studies.py` has a re-indented line inside the final `with` block. It is valid Python but inconsistent with the rest of the file.
7. **No minimum or idle RPM (prior scope note, unchanged).** Feasible points may command a stopped rotor.

**Resolved or accepted from earlier reviews:** Low #1 (both parts), #2, #3 and #5 (RPM recheck part). Prior Low #6 on model naming is accepted as documented: the full source fingerprint, not `MODEL_VERSION` alone, binds each study.

## Reviewed scope

The scope is unchanged from the `3f9b01d` pass:
- static hover only: zero attitude, motion and inflow; no ground effect; z-up frames; one payload point;
- fixed-condition, single-interval, strictly increasing thrust maps with affine nondecreasing torque and convex nondecreasing piecewise-linear electrical power; shaft maps only with constant torque;
- a fixed pack on a declared constant bus, with required alternative cases and ordered constant-power segments.

The outcome semantics are tightened as follows:
- `feasible` means an independently recomputed wrench, power and RPM within limits.
- `infeasible` means a gap-free, physical-bound Farkas certificate.
- `unsupported` means an eligibility or coverage/domain refusal.
- `unresolved` means any numerical failure after eligibility, or disagreement between the joint result and an independent bound.

This pass covers analytic software fixture scope only. It is not installed-aircraft validation, measured-map accuracy, operational payload allowance or flight approval. `engineering_approval` remains `pending`. Retained records are first-accepted observations, and their certificates are not re-verified by the contract.
