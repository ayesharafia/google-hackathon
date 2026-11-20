# MVP implementation gates

## Day 1 software gate, 2026-10-02

Three pinned v2606 sphere runs completed at 812 iterations. All checkMesh stages
explicitly reported Mesh OK. Actual cells, residuals, time and memory are in
`docs/validation/sphere_re100_runs.md`. Vendor-derived dictionaries retain source
paths and original hashes. Native parser fixtures retain full coarse files,
losslessly compressed, with byte hashes. Unit and backend smoke checks passed.

## Day 2 software gate, 2026-10-02

All three runs pass native pressure/viscous/net-force, origin-moment and Cd
reconciliation. All pass last-two-200-iteration drag drift. Unequal effective
ratios are reported instead of nominal background ratio. Observed order 4.327
and GCI 0.1099% are qualified; asymptotic convergence and total accuracy are not
claimed. Frozen correlation difference remains +2.6463% on fine mesh.

Fifteen real-data plots have recipes, verified source-byte hashes, array hashes,
shared contour ranges and full captions. Visual observations and the nominal
slice coordinate caveat are in `sphere_re100_plot_review.md`. Results envelope
rejects status upgrades and nonfinite metrics. Unit suite: 261 passed, 3 backend
tests deselected. Lint passes. Backend suite: 3 passed in 12.82 s with
`PHYSIMESH_OPENFOAM_TUTORIALS=.backend/vendor/v2606/tutorials`. A first invocation
without that required configuration refused the two vendor-dependent tests;
configuration was corrected, with no solver or test changes. No aircraft data or physics certification exists.

## Review still required (status before 2026-10-03 review)

These are implementation checks by the primary GPT-family agent. They do not
satisfy the master plan's independent different-family or human physics review.
Evidence remains unverified, and the branch must stay unmerged until that review
and the Day 3 product/reproduction gate are complete.

## Day 3 software gate, 2026-10-02

The evidence desk, native face-constant 3D, source-bound galleries, screening,
missing-input refusals, geometry intake and export are implemented. Browser QA
covers desktop and phone layouts, actual controls and the design-law recheck.
Brave saved an actual evidence ZIP; every listed member matches its digest.

A fresh clone from GitHub at 58a9596 reproduced all three sphere solves, native
checks, fifteen plots and native surface. The completed-run reuse path verified
inputs/outputs, rebuilt derived artifacts and re-published identical bytes.
The clone's API/export and synthetic capacity/refusal checks passed. Local unit
suite: 285 passed; pinned backend fixtures: 3 passed. Ruff and JS syntax pass.
See `fresh_clone_reproduction.md` and `results_page_checklist.md`.

This software gate is a primary-agent implementation record. Independent physics
review and product sign-off, two timed presentation rehearsals and a backup screen
recording remain pending. No release tag or main merge has been performed.

The manual Linux GitHub backend workflow on 73ee812 also passed after the numeric
host UID/GID mapping fix. See the portability follow-up in the reproduction record.

## Independent review follow-up, 2026-10-03

At the user's request, Claude Opus 5.5 reviewed commit 6dd6dfc and independently
recomputed native loads with a new parser. Its report is
`docs/qa/independent_physics_review.md`: conditional pass for the bounded sphere
and illustrative screening scope, no critical/high findings. Claude disclosed
that it authored the original plans/reference code; its fresh recomputation is
recorded, and human aircraft engineering approval remains separate.

The candidate addresses required F1–F3: nominal-order-capped GCI 0.40844% is
primary while observed-order GCI 0.10989% remains visible; supplied power and
energy are explicitly labelled physically unchecked; the documented stop rule
now matches v2606 source and iteration 412/812 logs. Tiny drift uses scientific
notation (F9). New plots and results were published in a separate immutable
local root, preserving earlier packages and original solver outputs.

Candidate verification: 290 unit tests and 118 reference tests passed; Ruff
and JavaScript syntax passed. Backend/solver inputs were unchanged, so previous
three pinned backend tests and Linux checks remain the applicable runtime
evidence. Browser checks confirm missing climb inputs remove the headline and
the complete example still returns 52.23 kg; 390/1280 layouts have no document
overflow. The revised export has 33 hash-verified members, 2,579,327 bytes,
SHA-256 `c3fe646f64e44a80d2ecb176aef374fcf475e08ff7b7fda31f8043ed193bf6c7`.

Claude's §6 follow-up independently verifies F1–F3/F9 and issues **PASS for the
bounded MVP at f19cbeb**. It reran 290 unit and 118 reference tests, Ruff and JS
syntax checks, verified the new package and unchanged native evidence, and
visually inspected the corrected chart. Low findings remain recorded without
status upgrades. Two-axis software review: Spec has no findings; Standards found
two documentation omissions, both corrected in d065729 and verified. GitHub
checks passed for f19cbeb and d065729. Code-review acceptance is separate from
machine package review attestation, which remains pending/unverified.

Use `.backend/demo-reviewed` for this retained demo. Historical packages share
the run-group ID; cite the root and ZIP hash to distinguish revisions (N1).

The presenter guide is `docs/demo/presenter-guide.md`. Both timed full
walkthroughs and a playable backup recording remain pending: native QuickTime
recording controls could not be exposed through the available automation.
Product gate sign-off and human approval of final client wording also remain
pending. No merge or release tag is authorized by these software checks.
