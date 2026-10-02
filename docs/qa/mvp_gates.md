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

## Review still required

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
