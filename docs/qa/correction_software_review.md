# Correction software review, 2026-10-03

Fixed base: `6dd6dfc19690a595844dc2b30fff844d07684879`.
Candidate: `f19cbebddffaf788df76f8a5cd35adf8b99d3cea`.
Documentation follow-up: `d065729e81d77573b7dccd1ac9f380d5a2e43611`.
Scope: independent physics conditions F1–F3, drift display F9, presenter and
handover documentation. Two read-only reviewers assessed the diff separately.
This record does not review or approve an aircraft or satisfy presentation gates.

## Standards

Two low findings against `plan.md` §1.3/§7.2:

- The new GCI function lacked `Implements: [M-E40]` and explicit dimensionless
  safety-factor units. d065729 adds the equation reference and documents every
  argument/output's units.
- The tiny-drift formatting threshold lacked a source/assumption tag. d065729
  records its two-decimal-percent rounding derivation and display-only role.

Both corrections were independently rechecked; no findings remain in this scope.
The affected 12 tests and Ruff passed. Styling changes were excluded because the
candidate only changes UI text; the actual browser checks remain separate.

## Spec

No findings. F1 requires “Show the GCI at p = min(p_obs, 2) as the primary
figure (or alongside).” The capped value is primary and drives the error bar;
the observed estimate remains visible and qualified. F2 permits labelling
supplied power/energy as physically unchecked; both API results and page do so.
F3 requires correcting both stopping-rule documents; both now match actual
v2606 behavior. F9 requires scientific formatting for small nonzero drift.

No missing requirement, scope creep or incorrect implementation was found in
the correction scope. Labelled examples, the minimum across declared mission
cases and refusal of incomplete inputs remain intact. Rehearsal, backup,
product/client approval and release limits remain open.

Final count: Standards 0 unresolved (2 corrected); Spec 0.
