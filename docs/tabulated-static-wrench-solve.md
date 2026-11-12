# Bounded tabulated static wrench allocation

`physimesh.drone.tabulated_static_wrench_solve` adds an experimental bounded
allocation capability for the original PDF phase-2 trim/control gap. It supplies
a local numerical search over actual V112 isolated static loads. Physical
qualification, installed-aircraft trim, control authority and stability remain
unestablished. There are no API or UI additions and no new defaults.

## Closed request

Call `evaluate_tabulated_static_wrench_solve(request)`. Every root field is
required; additional fields are forbidden:

- `evaluation`: exactly `bounded_tabulated_static_wrench_solve_experimental`.
- `assembly_template`: the full V112 root, including its own literal assembly
  evaluation label, explicit air, ordered rotors, mass, CG, gravity direction and
  property source. Each rotor retains its explicit axis, center, spin and full
  tabulated geometry declarations. Omit `angular_speed_rad_s` and
  `density_kg_m3` from every rotor template. Actual reference air supplies density.
- `rotor_speed_bounds`: an ordered list matching rotor IDs exactly, with unique
  IDs. Each closed object contains `id`, `angular_speed_bracket_rad_s: [lo, hi]`
  and `initial_angular_speed_rad_s`. Require positive `lo < hi` and
  `lo <= initial <= hi`; speeds have units rad/s.
- `required_net_force_body_n` and `required_net_moment_cg_body_nm`: explicit
  three-component lists in N and N*m, respectively, in the V112 body frame.
- `absolute_force_tolerance_n` and `absolute_moment_tolerance_nm`: strictly
  positive scalar tolerances in N and N*m.
- `max_evaluations`: a builtin integer from 2 through 64.

Use strict builtin JSON containers and values. Numeric inputs reject bool and
subclasses and require exact conversion to finite binary64 normal values or
zero, where applicable. Unit axes and gravity direction use V112's declaration
tolerance; they are not normalized. V112's right-handed forward/left/up frame,
positive-thrust axis, signed spin and unsigned shaft torque conventions apply.
Gravity is already included in actual **net** force; the target is not a thrust
target. Gravity acts at CG and contributes no moment about CG.

All structural template, bounds, source, classification, frame, spin and mass
checks precede hashing, SciPy and model calls. Preflight injects actual initial
speeds into a structural V112 request and checks it with `_assembly._preflight`;
it performs no dummy physical evaluation. Physical-domain admission remains
with actual child evaluation.

## Limits and arithmetic

The outer input allows 262144 nodes including keys, depth 16 and at most 256
items per container. The output allows 1048576 nodes including keys, depth 28
and at most 2048 items per container. Both cap strings at 2000 characters and
integers at 1023 bits, require finite floats and valid UTF-8, and count root
depth as 1. Entire trees are walked before copying, hashing or equality checks;
foreign objects, copying hooks, cycles and excessive nesting cannot cross the
snapshot boundary.

Independent V112 and forward-child JSON budgets remain in force, as listed by
the fresh catalog. Each actual assembly has 1–8 rotors and at most 4096 total
annuli; each rotor retains V112's per-child limits. Additionally,
`max_evaluations * sum(rotor annuli) <= 65536` must hold before execution.
For example, a structurally legal 4096-annulus assembly with a requested budget
of 17 exceeds the aggregate work bound and is refused before any model call.

For each guarded actual candidate, the six scaled residual components are
computed in this exact order:

```text
(Factual[0:3] - Frequired[0:3]) / absolute_force_tolerance_n
(Mactual[0:3] - Mrequired[0:3]) / absolute_moment_tolerance_nm
```

Each component uses binary64 subtraction followed by division. Intermediate
values must be finite normal or exact zero; overflow and nonzero underflow are
refused. `max(abs(scaled_residual)) <= 1` is inclusive numerical acceptance.
Load reconstruction uses actual retained forward outputs, V112 `_loads`, its
signed products and differences, and componentwise `math.fsum` in V112 order.

## Actual calls, admission and selection

SciPy `least_squares` uses `method="trf"`, `jac="2-point"`, `loss="linear"`,
`x_scale=1`, and `ftol=xtol=gtol=1e-12`, with `max_nfev=max_evaluations`.
The [official SciPy documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)
states that `max_nfev` and reported `nfev` exclude calls for numerical Jacobian
approximation. The objective therefore owns the total hard budget, including
finite differences, and stops before any actual call beyond it. TRF may adjust
an initial point into the bounds; the actual speeds supplied by SciPy are
converted once to finite builtin floats and checked without clipping. SciPy
searches for a local minimum, and its success flag is not the acceptance rule.

Every objective trial calls actual `evaluate_tabulated_rotor_assembly` exactly
once. The entire returned result is immediately bounded, detached and walked
again. A pure full-success guard checks closed root keys, typed metadata,
private code-owned catalog constants, request and result hashes, units,
diagnostics and counts. It validates actual raw air through V115 `_air`, each
full actual forward request/result through the V106 child guard using actual
density, each row's loads, gravity and net sums, and the exact chronological
air/rotor stages and density transfers. The air stage is `air`; a rotor whose ID
is `air` has stage `rotor:air`. No model is rerun during guarding and no typed air
object or success envelope is fabricated.

`evaluation_count` counts only fully guarded V112 success trials.
`rotor_evaluation_count` sums their rotor counts. These are neither attempted
call counts nor execution attestations. Any noncomputed actual assembly,
including a valid physical-domain refusal, lies outside success admission and
produces the same sanitized `ASSEMBLY_BOUNDARY_FAILED` label. Child reasons and
noncomputed status never establish failure causality. Earlier guarded counts
survive a later failure; all failure outputs, units, stages and transfers are
empty and diagnostics are false. Ordinary exceptions are sanitized;
`BaseException` propagates.

The solver retains the earliest candidate achieving a strict minimum of the
maximum absolute scaled residual. It keeps that candidate's full actual request
and full actual result while iterating. There is no extra explicit initial or
final evaluation. Acceptance stops immediately after appending the guarded
candidate whose residual meets the tolerance.

A computed response has one of these outcomes:

- `RESIDUAL_MET`: the retained candidate meets all six component tolerances.
- `EVALUATION_LIMIT`: no candidate met tolerance and the total hard cap was used.
- `SOLVER_STOPPED`: no candidate met tolerance and SciPy stopped below the cap.

A solver return without objective calls is `EXECUTION_FAILED`. None of these
outcomes labels the target infeasible.

## Retained evidence and units

`outputs.candidates` contains every guarded candidate in chronological order:
zero-based index, actual speeds, actual net force and moment vectors, force and
moment residuals, the six scaled residuals, their maximum absolute value, and
full request/result digests. Speed units are rad/s, forces N, moments N*m and
scaled residuals dimensionless.

`outputs.selected_index` selects the earliest best candidate.
`outputs.actual_assembly_request` and `outputs.actual_assembly_result` retain
that full actual pair once. Nested result units describe its `outputs` only;
the result's full envelope carries its own units and metadata. Nonselected
request digests can be recovered from the template and recorded speeds.
Nonselected result digests are format-only producer provenance because those
payloads are absent; they cannot independently verify their discarded content.
The fresh catalog returns closed field lists, units, limits, formulas,
numerical policy, count semantics, source URL and limitations.

The root request digest stays null before admission. Accepted computed and
ordinary failed responses are sealed with an evaluation hash excluding its own
field. Hashes bind JSON data; they establish no runtime identity, provenance
truth, physical validation or execution attestation.

## Runnable actual-model fixture

From the repository root, using the project's prepared Python environment:

```python
from tests.drone.test_tabulated_static_wrench_solve import request
from physimesh.drone.tabulated_static_wrench_solve import (
    evaluate_tabulated_static_wrench_solve,
)

supplied = request(initial=100.0, budget=32)
result = evaluate_tabulated_static_wrench_solve(supplied)
assert result["status"] == "COMPUTED_EXPERIMENTAL", result["reasons"]
assert result["outputs"]["outcome"] == "RESIDUAL_MET"
```

This test fixture derives its required net loads from an actual V112 evaluation
at 120 rad/s, then removes speeds from the template and starts the allocation at
100 rad/s. The setup evaluation is outside the allocation's trial counts.
It is synthetic software evidence, not measured aircraft evidence. The initial
three smoke tests also cover a one-trial initial solution and a two-call hard
budget that includes finite differences. Test execution is a separate step.

Global uniqueness, infeasibility, Jacobian rank, control authority, stability,
motors, thermal limits, structural response, mission performance, interference,
installed validation, physical accuracy and numerical qualification remain
unestablished. The isolated attached-linear small-angle hover model's existing
limitations and all accepted V125 behavior remain in place.

## Governing search and selection policy

The explicit force and moment tolerances convert the six residual components
to dimensionless values. SciPy's fixed linear-loss objective minimizes a sum of
squared scaled residuals (L2). Retained-candidate selection and acceptance use
the maximum absolute scaled component (L-infinity), with the earliest candidate
winning equal maxima. These two criteria can prefer different candidates. The
returned selection is the best observed maximum residual under the fixed call
budget; it establishes no global L-infinity or dimensionless L2 optimality.
