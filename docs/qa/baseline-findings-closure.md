# P00.2: baseline findings, implementation and review evidence

Status: P00.2 complete within the bounded baseline-correction scope. Claude independently passed code candidate `0bc092fa160319eab8b4e9113307def3986992c3`; software reviewers have no remaining actionable findings. Do not interpret this document as production readiness, aircraft validation, human engineering approval, or permission to merge/tag.

Scope: the retained Re=100 sphere verification pipeline and explicitly illustrative vertical payload screening. The original native runs and published packages remain intact. Real geometry, rotor performance and aircraft mass data remain unavailable.

## Findings and corrections

| Finding | Implementation | Evidence |
|---|---|---|
| F4 | `postpro/loads3d.py` and `results.py` use a 1e-9 qAD moment floor, separate units and per-component discrimination. Relative allowance remains 1e-3. The floor is numerical comparison policy for the 12-digit, gauge-pressure sphere adapter, not an accuracy estimate. | Asymmetric analytical forces (-2,0,0) at (0,2,1), (0,-3,0) at (1,0,2) give F=(-2,-3,0), M=(6,-2,1). Reintegrating about (1,0,0) gives M=(6,-2,4). Sign, magnitude and actual origin mutations fail. Three retained meshes pass tighter native reconciliation. |
| F5 | `drone/screening.py` reports `infeasible_limits`, actual versus supplied limits and exclusion tags. Missing/invalid data stays `inputs_incomplete`. Existing status literals remain unchanged. | Complete 600 s hover inputs require 14.4 MJ versus 11.52 MJ supplied energy and withhold the headline. A missing required case separately withholds it. |
| F6 | The retained `climb` identifier now describes a labelled, two-second instantaneous acceleration margin. Both API eligibility and domain calculation refuse longer acceleration margins. No trajectory is integrated. | 180 s margin regression refused; the example retains 52.232730994 kg vertical ceiling, with a 44,800 J constant-power illustration. |
| F7 | Versioned slice geometry, coverage and sensitivity policy; exact native source hashes and recomputation at publication. Registered input is placed in each new solver job before execution. Old runs remain retrospective. | Geometry/coverage/outlier mutations, fabricated eligible reports and changed native bytes are refused. Full world-velocity differences detect equal-speed reversals; extreme finite norms and metrics refuse explicitly without nonfinite report values. The final replay still withholds coarse vorticity and all three medium slices. |
| F8 | Explicit battery mass-item selection and usable pack energy derivation, bound to the approved snapshot. | 20 kg × 250 Wh/kg × 0.8 × (1-0.2) × 3600 = 11.52 MJ. Changing battery mass to 10 kg while keeping energy is refused. Both reserve conventions on the separate battery exercise and capacity example are named. |
| F10 | `ResultsV1` literals are preserved; the UI says numerical consistency passed, validation pending. Evidence and machine review remain separate. | No result is upgraded from `unverified` / `pending` by identity, software tests or external review. |
| F11 | Restricted vertical-screen eligibility rejects tilt, tilted axes, horizontal motion, unresolved lateral force and overflow. Moment trim, allocation, structure and payload CG remain unevaluated. | Huge finite side forces (1e200 and 1e308 N) cannot overflow into a positive headline. Tilt and horizontal residual regressions refuse capacity. |
| N1 | `postpro/publication.py` adds `publication_identity_v1` beside frozen `ResultsV1`. Full revision binds version, full study hash and every authenticated payload-member hash. The envelope and hash-manifest files are excluded from their own identity to avoid circular hashing. | Changed recipe content produces a new full revision even under the same study ID. A stale envelope with a rehashed manifest is rejected. Legacy identities/export envelopes are derived without modifying archived files. Study provenance must match actual `run_group.json` bytes. |

## Bounds of the screening number

The headline is the lowest vertical force ceiling across all required alternative operating points. It is not a sequential mission result or a trimmed aircraft carrying capacity.

For each point, supported total mass is `(sum rotor Fz + body Fz)/(g0 + az)`, with `g0=9.80665 m/s²`. Subtract the empty ledger mass, and retain the minimum raw margin across complete points. Electrical checks compare each rotor's power with its sustained limit, total electrical power with available power, and constant-point power × duration with declared usable energy. Missing data, infeasible limits and unsupported scope withhold the headline. Excluded cases keep explicitly tagged diagnostic arithmetic.

The hover example gives `(4×350-40)/9.80665-65 = 73.681404965 kg`. The short acceleration margin gives `(4×320-60)/(9.80665+0.6)-65 = 52.232730994 kg`. No rotor geometry-to-performance inference, battery measurement, aerodynamic validation or full trim is claimed.

The two-second limit is an illustrative adapter policy, not a claim that forces remain physically constant throughout a two-second trajectory. Future mission and trim work is P04.

## Preservation and reproduction

The old reviewed package's raw `hashes.json` SHA-256 remains `e5c2a75cca8b009aa69fce0205fced8e74442bab12aa26f0a42a5a335348cbc9`. The 33 original payload members and 174 native input/output files, plus three execution records, were checked against the frozen P00.1 inventory. Two old roots (`demo-reviewed`, `demo-final`) remain API-readable and have distinct derived content identities for the same study ID.

P00.1's inventory and launcher are intentionally frozen for their original source snapshot. Reproduce that baseline from its recorded checkout. The current branch's changed source must not be substituted into the old inventory or the reviewed launch preset.

Current reconstruction uses the same byte-identical retained `run_group.json` and its original absolute native case locations. Run `demo_loads.py`, `demo_plots.py`, `demo_surface.py`, `demo_seed.py`, then `demo_assemble.py` into a NEW output root; no old package is overwritten. These local CFD outputs are ignored artifacts, not GitHub-delivered solver evidence. The native original solver provenance remains separate from the new postprocessing source revision.

## Review and remaining work

The initial software reviews found a slice-status bypass and a horizontal-force overflow bypass. Both were corrected with regressions. The next spec review identified magnitude-only velocity sensitivity; full vector comparison closes it. Standards review then reproduced extreme-finite normalization overflow; explicit finite checks and a serializable-refusal regression close it. Final spec and standards review at `0bc092f` each have zero remaining actionable findings (independent focused runs: 32 and 8 tests respectively).

Claude's initial physics review was CONDITIONAL PASS at `1dbbc514e9d9fd86b4155d8a076c31bc17d92195`. Conditions C1-C3 led to real origin tests, component discrimination, a duration cap, policy pinning and job-input registration, native reprocessing and corrected captions. Follow-up review passed at `6dbf558`; the final direction/overflow increment was separately reviewed and passed at `0bc092f`. Claude independently rebuilt interpolation metrics using numpy/scipy without importing physimesh, recomputed all 27 package members and identity, and rechecked the original 33-member archive. See [the full physics review](baseline-findings-physics-review.md). The reviewer historically authored inherited reference code; that independence limitation must remain disclosed.

Human release approval, actual aircraft validation, timed presenter rehearsals and inspected backup video remain separate pending work. The rest of the production roadmap is not completed by P00.2.

## Final verification receipts

- Code candidate: `0bc092fa160319eab8b4e9113307def3986992c3`. Later documentation commits do not change this reviewed code.
- Unit suite: 365 passed, three backend tests deselected. Reference suite: 118 passed. Actual pinned-container backend suite: three passed, including a 20-iteration job with the policy file retained in its pre-execution input hashes. Backend receipt is at `6dbf558`; subsequent changes affect visual sensitivity postprocessing only. Ruff passed. One dependency deprecation warning remains in the test client.
- Reconstructed root: `.backend/p00-findings-accepted`. Study: `acd1b8716144aeaa045019515bdf377018ae4a74ce3a0403cf50c52da007ff6a`. Revision: `75967364f6d48556874bc369ac0175f92ebe3b6fc902e38df71e834ac9b071f1`.
- Export: 2,261,416 bytes; SHA-256 `04efb390c8c2b69b21519bf997766cb08f2e906a2c704405a6f6824140d49c0b`. All 27 listed members match, including the publication envelope; ZIP also contains its hash manifest. Both old roots remain readable and unchanged after GET/identity/export.
- 11 plots published. Four field-level refusals have no published slice: coarse vorticity; medium speed, pressure and vorticity. Fine velocity peak change is 0.04626 against the 0.05 visualization threshold; this thin margin is documented, not called accuracy.
- Browser: calculation, missing-case and energy-limit actions, field/mesh controls, reset/orbit, disclosures, synthetic STL import/readiness and ZIP preparation were clicked. Desktop 944 px and phone 390 px have no page overflow. Mobile capacity unit label was fixed. In-app download capture timed out; the prepared Save link and full revision filename were verified, and actual response bytes/ZIP members were verified through the API. A browser-saved file is not claimed.
- Detailed anti-slop review: [UI review](baseline-findings-ui-review.md). Machine-readable receipt: [checks](baseline-findings-checks.json).

## Explicit follow-up constraints

Before a prospective production CFD campaign, P01.1 must put the full sensitivity metric definition into the versioned policy/registration, with a compatible multi-version loader. The velocity bug fix changed metric semantics under the old policy digest; no decisions changed in this entirely retrospective replay. The backend smoke proves input retention only. It is not a registered three-grid evidence campaign.

Keep the initial policy values frozen; do not silently tune thresholds to admit withheld views. Investigate slice sample sensitivity and acquire prospective evidence under the fully bound successor policy. Additional limitations are the lack of external registration timestamp/signature, duplicate-point regression dependence on SciPy, no installed rotor force-axis validation, no moment trim, and future moment scaling for absolute-pressure adapters. These are named in the independent review and allocated to P01/P04; they do not upgrade the present screening result.

Next work order: P01.1, versioned project and study contracts. P00.1's frozen source/evidence inventory remains unchanged. No merge, release tag, production deployment or client-aircraft certification is part of this closure.
