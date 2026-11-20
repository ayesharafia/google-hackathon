# P01.1 contract acceptance and independent review

Accepted 2026-10-03 for code candidate `831dd2eb81bd9bdf7fea33159cbbd0a0618cf456`, compared with `3cbafece6bab7e3d4f5775ade4da5d002ff9410b`. [Draft PR 3](https://github.com/PhysiCoreEngine12/Drone-Project/pull/3) is stacked on draft PR 2. This records bounded software/schema acceptance, not production release, human engineering approval, aircraft validation or authority to merge/tag.

## Delivered behavior

Seven schema fixtures round-trip: original sphere, incomplete draft, approved synthetic design, infeasible/unsupported/unresolved result and detached review. Actual mission conditions, required cases, reserve kind/convention/units, pack mode and sequence bind to the exact approved design revision. Screening records cannot claim numerical/validated aircraft evidence; result axes, minimum required-case bound and limiting case are checked. Canonical serialization, explicit migration declarations, unknown/null behavior and authenticated read-only schema discovery are documented in [production-data.md](../contracts/production-data.md).

Slice v1/v2 bytes are preserved. Prospective v3 binds exact interpolation/grid/comparison operators and reports NumPy/SciPy versions. All geometry, coverage and RMS/peak limits remain unchanged. Noncoincident analytic vector/scalar reversals independently produce RMS=peak=2 under each retained version. The new 20-iteration native v3 registration is a backend smoke, not a three-grid validation campaign.

## Verification and provenance

415 unit tests passed on the final reserve code. 118 retained reference tests and three real pinned OpenFOAM backend tests passed on the unchanged reference/backend/operator code. Lint passed. [Machine-readable receipts](production-contracts-checks.json) bind exact JUnit file hashes and the post-commit fingerprint of 152 tracked source/script/test/lock/config files. The JUnit timestamps alone do not prove source identity. [GitHub unit/lint workflow](https://github.com/PhysiCoreEngine12/Drone-Project/actions/runs/37119517018) also passed on the pushed code candidate; backend is manually triggered and was verified locally as recorded separately. Earlier failed backend setup lacked the required tutorial environment; the configured runs passed. A dependency deprecation warning remains.

The original 174 native files, three native run records and 33 original archive payload members remain byte-identical. API exports still produce the accepted 27-member package, full revision `75967364f6d48556874bc369ac0175f92ebe3b6fc902e38df71e834ac9b071f1`, SHA-256 `04efb390c8c2b69b21519bf997766cb08f2e906a2c704405a6f6824140d49c0b` and 2,261,416 bytes. This was rechecked after the final reserve correction. Claude independently rechecked native/archive members and package revision; it did not recompute the API ZIP.

No UI files changed in P01.1. The whole applicable design-law and browser review is retained in [baseline-findings-ui-review.md](baseline-findings-ui-review.md); no new browser pass, download or production UX acceptance is claimed.

## Standards

Final read-only review at `831dd2e`: no actionable findings. Reserve kind/convention/units agree; screening accepts the held usable-energy fraction and rejects conflicting explicit conventions while absent convention retains historical behavior. Independent contract/screening-scope verification: 53 passed. Earlier whole contract/slice review at `c42361f`: no findings; 49 focused tests passed.

## Spec

Final read-only review at `831dd2e`: no actionable findings. Exact reserve declarations and supported screening scope satisfy the documented contract. Independent focused verification: 53 passed. Earlier review at `c42361f` found no remaining actionable spec findings; 57 focused tests passed. Scope remains P01.1 only.

## Independent physics/schema review

Claude Opus 5.5 reviewed the contract semantics and metric math. Initial `5547d62` conditional pass identified outcome/status and mission-binding defects. They were corrected and re-reviewed at `c42361f`. That pass retained Low R1 for reserve ambiguity; `831dd2e` closed it. The two final review records are reproduced below, including methods and independence limits. The reviewer authored inherited reference code and the planning critique; this is a different-model review with disclosed lineage, not completely independent engineering validation.

## Plan changes and remaining work

[Pilot-1](../pilots/pilot-1.md) prioritizes local mass ledger, measured-map fixtures, mission cases and bounded payload/limiting-case calculations before hosted rollout. The current frontend remains; migration needs a separate ADR. The client is engineering owner; named engineer/approver, real inputs and acceptance tolerances remain pending. The [client request](../client/aircraft-data-request.md) is prepared, not sent.

P01.2/P01.3 persistence and authenticated identities are not implemented. Contracts alone do not establish chronological validity, trim/search, structural allowance or rotor-map applicability. Case ordering is intentionally hash-significant; zero-width-only review text is not fully classified. Separate SciPy wheel/Qhull build hashes and external registration timestamp/signature are not captured. I01 regular-grid native sampling, I02 controlled domain/refinement and I03 separate evidence/source verification remain pending. The original frozen checker still refuses changed source by design.


## Claude review at c42361f

# Independent review: P01.1 contracts, final candidate `c42361f`

| Item | Value |
|---|---|
| Candidate | `c42361f1e9ab53f31ce0d133081464bba109bd71`. It contains `5547d62` → `3ea9f9f` → `c42361f`. |
| Fixed point | `3cbafece6bab7e3d4f5775ade4da5d002ff9410b` |
| Tree | I checked `git diff c42361f --quiet`: the working tree equals the candidate (only untracked `.DS_Store` files). I imported the code in memory with `PYTHONDONTWRITEBYTECODE=1 -B`. |
| Reviewer | Claude Opus 5.5 (Anthropic), a different model family from the implementing agent. I did not delegate any part. Read-only throughout: no source, artifact, git or status edits, and I ran no tests that write receipts. |
| Independence | Limited. This reviewer earlier wrote `plan.md` and `reference_impl/`. `snapshot_sha256`, `canonical_json` and the load code descend from that work. I also wrote the planning critique attachment, which I re-read at the given path. The new contract and policy code was checked by adversarial execution and by my own recomputation. |

---

## 1. Verdict

**PASS for bounded P01.1** (versioned contracts, revision and mission bindings, status semantics, canonical serialization and migration, slice-policy versioning).

- C1 and C2 are closed. I confirmed this by running adversarial cases myself (§3).
- One Low finding remains (R1: two reserve declarations in one snapshot can disagree). It does not block P01.1. It should be fixed before Pilot-1 code reads reserve from an approved revision.
- This is not aircraft validation, human approval, merge or tag approval, persistence, authentication, or solver acceptance.
- Fixture attestation and validation digests are synthetic. They do not show a real payload or a real human review.

---

## 2. Methods: what I checked myself

1. **Diffs and documents.** Read `git diff 5547d62 c42361f` for source, docs and tests, the v3 policy, and the attachment.
2. **Policy bytes.** Hashed each version with `git show c42361f:… | shasum`:
   - v1 `babdcdb9…13a7`
   - v2 `94a3a591…5a0f`
   - v3 `8744e2b7…d5b1`

   Each equals its pinned registry digest. v1 and v2 are unchanged.
3. **Adversarial checks of status rules, mission binding and study binding.** About 50 records, run in memory against the candidate (§3).
4. **Golden-case math, recomputed separately** with my own numpy/scipy code (no physimesh import), with SciPy 1.17.1 and NumPy 2.4.6:
   - The inner triangle is a Delaunay simplex, so the entire view interpolates to −a.
   - Both subsets keep only the 3 on-plane points, giving +a.
   - The interpolated span is 1.1e-16 (vector) and 8.9e-16 (scalar). Both are below the 64·ε·magnitude cutoff, so the code falls back to scale = a, which equals 1 (vector) and 3 (scalar).
   - Coverage is 1.0. RMS and peak both come to 2.0 (within one rounding step) for vector and signed scalar, at both subset tolerances.
5. **v3 definition text against the code.** Every new field matches `evaluate_slice` and `resample_slice`:
   - Comparison nodes are external nodes finite in both baseline and subset (`overlap`). The span is taken over all finite baseline external nodes.
   - Subset selection is `|y| ≤ f·D`, inclusive.
   - The grid is `meshgrid(linspace(x), linspace(z))`, so rows are z and columns are x, with inclusive bounds.
   - `griddata` fills NaN outside the convex hull and interpolates (N,3) values componentwise.
   - The geometry gate uses `allclose(y, 0, atol=tol, rtol=0)`, i.e. `|y| ≤ tol`.
   - Thresholds use `<` for coverage and `>` for RMS and peak, so equality passes.
   - An unsupported subset raises inside the loop, which refuses the slice.
   - `operator_versions` is recorded only for v3. v1 and v2 reports are unchanged, so existing replays reproduce.
6. **Archives, recomputed by me:**
   - All 174 native input/output files and all 3 run records match `docs/qa/production-baseline.json`.
   - The `demo-reviewed` archive has 33 of 33 members matching, with `hashes.json` = `e5c2a75c…`.
   - The accepted package has 27 of 27 members matching. Revision `75967364…71f1` is confirmed.
7. **Receipts, inspected but not re-run:**

   | Receipt | Timestamp | Result |
   |---|---|---|
   | `unit-final.xml` | 16:46:38 | 410 tests, 0 failures, 0 errors, 0 skipped. It includes the v3 golden, v3 replay and v3/v2 equality tests. |
   | `backend-final.xml` | 16:45:58 | 3 tests, 0 failures |
   | `backend-configured.xml` | 16:33:58 | 3 tests, 0 failures |
   | `backend.xml` | 16:33:38 | 2 failures, both "Set PHYSIMESH_OPENFOAM_TUTORIALS". An environment-configuration failure, superseded by the configured run. |
   | `reference-final.xml` | 16:48:08 | Present: 118 tests, 0 failures |

   - I did **not** recompute the export ZIP SHA `04efb390…`. Doing so needs the API export path, which creates app state. That value comes from the agent's receipt `archive-and-identity.json`.
   - I did not inspect a Ruff receipt; the Ruff pass is as you reported.

---

## 3. Conditions

### C1 (status and evidence axes): CLOSED

**Refused at the candidate:**
- a feasible supplied-point screening result with status `requirement_not_met`, `inputs_incomplete`, `numerically_unverified`, `validation_pending`, or `within_validated_envelope`;
- supplied-point screening carrying `mesh_assessed` or `iteration_converged` evidence, including on an infeasible outcome;
- `measured_map_trim` that is feasible with `screening_only`;
- `within_validated_envelope` without validated evidence;
- `running` together with `mesh_assessed`;
- `not_evaluated` together with `requirement_not_met`.

**Accepted, as intended:**
- trim with `validation_pending`;
- trim with `within_validated_envelope` when evidence is `validated_for_case_family` and an envelope is given;
- `not_evaluated` with `inputs_incomplete`.

### C2 (study mission bound to the approved design): CLOSED

**At approval** (`bound_mission`), these are refused:
- a stale condition hash after a raw case edit;
- a raw required flag that disagrees with the typed mission (including `required: 1`);
- `pack_mode` mismatch;
- `cases` given as a dict;
- a missing `contract_definition`.

**At study binding** (`assert_design_binding`), these are refused with "study mission differs from approved design revision":
- an unrelated case;
- climb demoted to optional;
- climb dropped;
- a changed condition hash;
- reserve 0.2 changed to 0.1;
- pack mode changed to sized;
- an added sequence;
- reordered cases. Order sensitivity fails closed; noted as Info below.

The exact spec binds. The fixtures now carry real condition hashes, and the fixture spec binds the actual revision hash.

### Low fixes from my previous review: confirmed

- Whitespace-only review scope is refused.
- A superseded review must name the attestation it supersedes.
- Withdrawn requires a retained publication identity.
- An infeasible aggregate whose required cases are all feasible requires a `limit_exceeded` reason.
- The legacy-migration docs now say "caller declaration, not detection".

---

## 4. Remaining findings

| ID | Severity | Location | Finding and repro |
|---|---|---|---|
| R1 | **Low** | `projects/contracts.py` `bound_mission`; `drone/screening_scope.py` `pack_consistency` | **Two reserve declarations in one approved snapshot can disagree.** `bound_mission` checks `reserve_policy.convention` and `value`, but not the legacy `reserve_policy.kind` that `pack_consistency` uses. Repro: take the approved fixture, set `reserve_policy.convention = 'additional_mission_demand'` in both the raw snapshot and the contract definition, and keep `kind: 'fraction'`. The revision is **accepted** as approved. The same happens with `held_energy_j`, value 0.2 (meaning 0.2 J), and `kind: 'fraction'`. The screening adapter would then hold back reserve from usable pack energy, while the contract says additional mission demand: about 4% difference at r = 0.2, or a unit mismatch. The docstring says contradictory views are prevented, so this is incomplete. **Fix:** require `kind` to map to `convention`, or remove `kind` for approved revisions, before Pilot-1 code reads reserve. |
| I1 | Info | `MissionDefinitionV1` sequence | An `acceleration_margin` case can appear in an approved sequence for 3600 s, and an approved raw climb case can carry `duration_s: 180`. The 2 s margin cap is enforced only in the screening layer. Chronological validity belongs to P04. |
| I2 | Info | `assert_design_binding` | Case order is significant. A reordered but identical mission is refused. This fails closed. |
| I3 | Info | `ReviewAttestationV1.scope` | A zero-width-space scope (`'\u200b'`) is accepted, because `str.strip()` does not treat U+200B as whitespace. Trivial. |
| I4 | Info | receipts | The receipts do not record a commit SHA. `unit-final.xml` (16:46:38) and `backend-final.xml` (16:45:58) predate the `c42361f` commit time (16:46:47) by 9–49 s, so they came from the working tree just before the commit. That is consistent with the candidate but not proof of it. `reference-final.xml` (16:48:08) postdates it. |

---

## 5. Policy versions and historical preservation

- v1 and v2 bytes are exact and registered under their retained digests.
- The v3 thresholds, geometry and every non-definition field equal v2's. The test asserts this, and my reading confirms it.
- Version selection follows the retained registration. Unregistered data is replayed under v1 retrospective. Unknown or tampered versions fail closed.
- v3 records NumPy and SciPy versions. The SciPy wheel and Qhull build digest are not captured, which the documentation states.
- None of this changes the accepted P00.2 replay. Its package, revision and archives re-verified unchanged (§2, item 6).

---

## 6. Limitations

- I did not re-run tests, Ruff, the backend, or the API/UI. No UI changed in this milestone; earlier UI evidence is retained, not re-executed by me.
- The export ZIP SHA and the `verify_delivery.py` receipt are agent evidence. Separately from them, I recomputed the native files, records, archive members and package revision.
- These remain pending and are not implemented:
  - I01: native regular-grid sampling.
  - I02: preregistered domain and surface refinement for the +2.65% Cd gap.
  - I03: separating source verification from evidence verification.
- Also still missing: an external timestamp or signature on registration, and a prospectively registered three-grid campaign.
- The original frozen checker is intentionally retained, and it refuses the current branch's source.
- The client is confirmed as engineering owner. The named engineer and approver, the real geometry, mass, rotor and mission data (D04–D06), and the acceptance tolerances are absent. The data request is prepared but not sent.
- Persistence, transactional draft versioning (P01.2) and authenticated identity (P01.3) are not delivered. The schema does not authenticate attestation references.

**Task-observer:** none logged. Read-only session.

## Claude reserve follow-up at 831dd2e

# Follow-up review: P01.1 reserve fix (R1), candidate `831dd2e`

| Item | Value |
|---|---|
| Candidate | `831dd2eb81bd9bdf7fea33159cbbd0a0618cf456`. The delta reviewed is `c42361f..831dd2e`, a single commit "require a single consistent reserve convention at approval". |
| Tree | `git diff 831dd2e --quiet -- src tests` succeeded, so source and tests equal the candidate. The only drift is the uncommitted `docs/technical/mvp-code-and-physics-guide.md`, which I treated as bookkeeping and did not review. |
| Reviewer | Claude Opus 5.5 (Anthropic), a different model family from the implementing agent. Read-only, no delegation, in-memory only with `PYTHONDONTWRITEBYTECODE=1 -B`. |

## Verdict

**PASS for bounded P01.1 at `831dd2e`. R1 is closed** and I found no reserve regression. This is not aircraft validation, human approval, merge or tag approval, persistence, authentication, chronological validity, or solver acceptance.

## R1: what changed and what I checked

There are two changes:
- **At approval:** `bound_mission` now requires `reserve_policy.kind` to match the declared convention: `held_usable_energy_fraction` → `fraction`, `held_energy_j` → `energy_j`, `additional_mission_demand` → `additional_mission_demand_fraction`. A revision approved for screening must use the held usable-energy fraction.
- **In the screening pack adapter:** `pack_consistency` now refuses any explicit convention other than held usable-energy fraction. When no convention is given, it keeps the historical held-fraction meaning.

Results of my in-memory checks:

| Case | Result |
|---|---|
| Approved fixture as-is (screening, held fraction, kind `fraction`) | **Accepted** |
| **R1 repro a:** `additional_mission_demand` with kind `fraction` | Refused: "reserve kind disagrees…" |
| **R1 repro b:** `held_energy_j`, value 0.2, kind `fraction` | Refused: "reserve kind disagrees…" |
| Screening approval with additional demand, matching kind | Refused: "screening supports only held usable-energy fraction" |
| Screening approval with `held_energy_j` / `energy_j` | Refused, same reason |
| `kind` removed; `kind: energy_j` under the held-fraction convention | Refused |
| `bound_mission` alone, every convention × kind pair (independent of readiness purpose) | The 3 matching pairs are accepted; the 6 mismatched pairs are refused |
| Legacy pack adapter, convention absent (demo example: `{'kind':'fraction','value':0.2}`) | `consistent`, 11,520,000 J (20 kg × 250 Wh/kg × 0.8 × 0.8 × 3600, same as before) |
| Legacy pack adapter, explicit `held_usable_energy_fraction` | `consistent`, 11,520,000 J |
| Legacy pack adapter, explicit `additional_mission_demand` or `held_energy_j` | Refused, `inputs_incomplete` |
| Legacy pack adapter, explicit `convention: null` | Refused, `inputs_incomplete` (see Info 1) |

**Receipt:** `.backend/p01-contracts/unit-accepted.xml` shows 415 tests, 0 failures, 0 errors, 0 skipped, timestamped 16:53:05. 415 = 410 + 5. All five new tests are named in the receipt: two parametrized `test_approved_reserve_cannot_keep_legacy_fraction_kind_under_other_convention`, `test_screening_approval_refuses_other_reserve_model_even_with_matching_units`, and two parametrized `test_legacy_screening_refuses_conflicting_explicit_reserve_convention`. I inspected the receipt; I did not re-run it.

## Remaining findings (all Info, none actionable for P01.1)

1. **Explicit null convention is now refused by the legacy adapter.** Before, it was ignored. This is conservative and consistent with "null = unknown", but it is a behaviour change for any caller that writes an explicit null.
2. **Non-screening purposes were checked only through `bound_mission`.** The approved fixture is not ready for the `feasibility` or `cfd_run` purposes, so readiness refuses those first. I verified the kind mapping for them by calling `bound_mission` directly; the approval path for those purposes is checked by code reading only.
3. **The receipt does not record a commit SHA.** Its timestamp (16:53:05) is 1 s before the commit time (16:53:06), so it ran on the working tree just before the commit. That is consistent with the candidate but not proof of it.

## Carried forward unchanged from the `c42361f` review

That review remains the record for everything outside this delta:
- C1 and C2 closures and the earlier Low fixes;
- policy v1, v2 and v3 bytes and digests, the v3 definitions matching the code, and my independent golden recomputation (RMS = peak = 2);
- 174 native files, 3 records, 33 archive members and the accepted revision `75967364…`, all re-verified by me;
- Info items I1–I4: sequence and margin-duration validity belongs to P04; case order is significant and fails closed; a zero-width-space review scope is accepted; receipts carry no commit SHA.

The numerical operators, policies, backend and native evidence are unchanged by this delta, which touches only reserve handling.

## Limitations

- I did not re-run the backend, reference tests, Ruff, API or UI.
- These are still not implemented: concurrent draft writes (P01.2), identity authentication (P01.3), chronological mission validity and the solver (P04), and investigations I01–I03.
- Real client data (D04–D06), a named engineer and approver, and acceptance tolerances are still absent.
- Fixture digests show only that the schema accepts the shape. They are not evidence of a real payload or a real human review.
- Independence remains limited: this reviewer wrote the inherited reference code and the planning critique.

**Task-observer:** none logged. Read-only session.
