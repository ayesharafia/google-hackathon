---
name: physicore-numerical-regression
description: Design and check PhysiCore equation and numerical regression changes, including units, analytical references, floating-point edge cases and refusal boundaries. Use for model kernels and their tests, not as physical validation or permission to change scientific thresholds.
---

# Numerical regression

Read `AGENTS.md`, `.physicore/ops/SCIENTIFIC_GATES.md`, the affected specification, kernel and tests. Use the existing `$scientific-review` skill for the evidence and qualified-review boundary. Keep this procedure limited to the changed model.

## Establish the contract

1. State the engineering quantity, equations and identifiable sources, variables, SI units, frames/sign conventions, assumptions and excluded mechanisms. Distinguish caller declarations from independently checked applicability.
2. Identify valid, incomplete, inapplicable, unsupported and numerical-refusal outcomes. Preserve existing evidence labels. A configuration name is not an aircraft solver; a declared model dependency is not an available backend.

## Build meaningful checks

- Write ordinary cases with an independent expected result: derive it separately from the implementation, use a suitable analytical/manufactured solution or a traceable reference dataset. Explain why the comparison applies. Do not copy the kernel's arithmetic into an allegedly independent oracle.
- Check dimensions and limiting cases. For same-direction cantilever loads, check zero load, linear superposition, root force/moment balance and the bending-depth convention. This does not test buckling, joints, fatigue or yield.
- For constant-segment lumped thermal models, check zero conductance, equilibrium and near-equilibrium, continuity across segments and the energy budget. A small arithmetic residual is not an accuracy estimate or experimental evidence.
- Check finite values, booleans/strings, huge integers, zeros, negative values, overflow, normal/subnormal transitions, nonzero terms rounded to zero and cancellation. Explicitly distinguish conservative refusal from a supported extended-range algorithm.
- Use high-precision arithmetic when appropriate and document precision, input representation, sampled range and seed. Near zero, choose a justified absolute or mixed error criterion rather than dividing blindly by the reference.
- Retain every discovered counterexample and rejected implementation as regression evidence. Fix the algorithm or its stated support range, not the expected answer to make the test pass. No threshold, reference hash or acceptance-policy weakening without the required project approval.

## Deliver the evidence

Run the applicable tests from the real package root and its supported runtime. Record exact commands, environment, result counts, seeds, maximum discrepancies and refusals. Run changed-file lint and the repository-required checks. Identify unavailable tests or backend limits explicitly.

Ask for a separate scientific/code review of the exact diff and evidence. Label self-review as internal. A checklist, green CI, reference link, hash or caller declaration cannot award scientific approval. Report only the supported scope: implementation checks, named benchmark comparisons or qualified experimental evidence as actually obtained.
