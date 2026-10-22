# Scientific credibility — use only when the task touches physical models, outputs or claims

**Verification ≠ validation.** Verification asks whether numerical equations and software were solved/implemented correctly. Validation asks whether the chosen model adequately represents physical reality for the intended use. Benchmark comparison is evidence, not universal certification. A language model cannot confer scientific approval on itself.

## Minimum model record
- Purpose, output to be trusted, intended decision and admissible operating range.
- Equations with identifiable references; explicit variables, SI units, coefficients and citations.
- Modeling assumptions, initial/boundary conditions, known exclusions and failure modes.
- Numerical solver, spatial/time resolution, convergence/stability criteria when applicable.
- Reference case(s), stated comparison quantity/tolerance/rationale; provenance and licenses.
- Uncertainty/sensitivity, reproducible run inputs, environment, test commands and results.
- Reviewer identity/qualification and actual sign-off, if obtained; absent means NOT APPROVED.

## Apply only relevant checks, do not pretend there is one universal ladder
- All physical models: dimensional sanity, input range, internal invariants and regression tests.
- Conservation: only where the model represents conserved mass/energy/momentum/charge; report proper budget and units, with spec-specific tolerances (not default 0.1%).
- Analytical/manufactured solutions: when suitable; no need to force a closed form where none exists.
- Grid/time-step convergence or GCI: only for applicable discretizations with adequate asymptotic behavior; report actual grids and observed order rather than claiming convergence because a finer mesh looks similar.
- Published benchmarks / cross-code: check matched governing equations, configurations, reference uncertainties, and applicable range. Agreement between two codes isn't automatically physical validation.
- Experiments: where predictive credibility for real systems is claimed, compare with suitable measurements, uncertainties, and operating range; qualified review and real-world testing may be required, particularly for safety-related decisions.

## Allowed claim labels
- **PROTOTYPE:** implemented but not proven numerically or physically reliable.
- **SOFTWARE-VERIFIED (scope specified):** evidenced by checks for the implementation and test regime, not a claim of physical accuracy.
- **BENCHMARK-COMPARED (cases specified):** results compared to named published references; include error and applicability limits.
- **EXPERIMENTALLY VALIDATED (scope specified):** traceable relevant experimental comparison, uncertainty analysis, reproducibility, and documented qualified review; does not imply certification.
- **UNVERIFIED:** evidence missing, tests blocked or not executed.

**Never** equate "green tests", two overlapping plot lines, passing an arbitrary 0.1% threshold, or CEO sign-off with scientific proof. The CEO can approve scope and risk but not replace qualified domain review. When no scientist is available, draft and implement reversible prototype work with explicit unverified status; do not silently waive scientific review.

## Reserved approvals
No unapproved changes to scientific acceptance thresholds, controlled specifications or certified/flight-critical code. Propose revisions with rationale, record in `.physicore/ops/APPROVALS.md`, and preserve old thresholds and evidence. Different metrics can require different error measures; do not automatically divide by a reference near zero.
