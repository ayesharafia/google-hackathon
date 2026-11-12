# Experimental section solve (V135)

`section_solve.py` adds bounded bisection of the accepted V134 prescribed-psi
residual. It is a local Python module only. V134 and the existing package files
are unchanged. There is no API, UI, nonlinear rotor integration, dataset access,
or publication.

Call `evaluate_section_solve(request)`; obtain fresh metadata with
`section_solve_catalog()`. The evaluation is `section_solve_experimental`, schema
`section_solve_v1`. Catalog access never evaluates a model or fetches a source.

The root contains exactly `evaluation`, `residual_template`, and `solve`.
`residual_template` contains exactly V134's `evaluation`, `polar`, and `section`.
Its evaluation must be `section_residual_experimental`. The section is exactly
V134's section except that **`psi_rad` must be absent**. Extra fields, psi overrides,
and alternative polar representations are refused. Each actual request is a copy
of that template with precisely one `psi_rad` added.

`solve` contains exactly these fields:

| Field | Contract |
| --- | --- |
| `psi_lower_rad` | Positive normal builtin int/float, radians |
| `psi_upper_rad` | Positive normal builtin int/float, radians |
| `angle_tolerance_rad` | Positive finite normal builtin int/float, radians |
| `residual_tolerance_m2_s` | Positive finite normal builtin int/float, m²/s |
| `max_evaluations` | Builtin int, 2 through 16; bool refused |

Both native and binary64 endpoint comparisons must satisfy lower < upper.
The entire interval must satisfy `atan2(Ua, Ut) < lower < upper < pi/2`.
Both complete actual endpoint requests pass V134 `_preflight`, including every
static polar table, before any model call. Endpoint native number types are
retained; computed midpoints are floats. The whole native root is hashed.

The solver calls actual V134 exactly once per attempted evaluation. It immediately
bounds and copies each returned result, checks fresh catalog metadata against a
frozen catalog, independently reconstructs velocity and closure using V134's
checked arithmetic order, compares the complete derived V133 request, and reuses
only the accepted pure `_res._guard_load` for the nested result. It reconstructs
the complete expected V134 response, including units, OOD unit changes, metadata,
counts and hashes. It never reruns V134's velocity, closure or evaluator as a guard.

The closure uses `U=hypot(Ua,Ut)`, `Wa=.5Ua+.5U*sin(psi)`,
`Wt=.5Ut+.5U*cos(psi)`, `va=Wa-Ua`, and `vt=Ut-Wt`.
With `lambda_w=(r/R)*(Wa/Wt)`, it reconstructs
`f=(B/2)*(1-r/R)/lambda_w`, `F=(2/pi)*acos(exp(-f))`, and
`Gamma=vt*(4*pi*r/B)*F*hypot(1,4*lambda_w*R/(pi*B*r))`.
The actual residual is `Gamma - .5*W*c*Cl`, in m²/s. No residual interpolation,
constant-Cl iteration, clamping, derivative approximation or extrapolation occurs.
Checked arithmetic refuses unrepresentable intermediates; no full-range promise
or hidden Prandtl-factor limit is added.

Lower is evaluated before upper. Lower OOD stops immediately after one accepted
row; otherwise upper is evaluated, even if lower has exact binary64 zero.
After both computed endpoints, exact zero collapses the bracket to that row.
Otherwise opposite signs are required using comparisons, never a product.
No sign change returns `NOT_BRACKETED`, with both rows and no solution.

For a sign-changing bracket, convergence requires **both** width <= angle tolerance
and at least one endpoint absolute residual <= residual tolerance. The endpoint
with smaller absolute residual wins; a tie selects the earlier evaluation index.
Each further evaluation uses checked `lo + .5*(hi-lo)`, strictly inside the current
bracket. Exact zero collapses the bracket. Other computed residuals replace the
endpoint of the same sign. An unrepresentable interior midpoint yields
`FLOAT_STAGNATION`. Exhausting the caller budget yields
`EVALUATION_BUDGET_EXHAUSTED`, with no solution even if one tolerance passes.

Successful root status is `COMPUTED_EXPERIMENTAL`. Its outputs contain exactly:

- `evaluations`: ordered unique actual rows `{psi_rad, request_sha256, result}`.
  Every row retains the complete guarded V134 response and its full nested child.
- `solve_state`: `CONVERGED`, `NOT_BRACKETED`, `NOT_RUN_OUT_OF_POLAR_DOMAIN`,
  `FLOAT_STAGNATION`, or `EVALUATION_BUDGET_EXHAUSTED`.
- `final_bracket`: `{lower_evaluation_index, upper_evaluation_index, angle_width_rad}`.
  Indices own exact retained evaluations. A zero bracket repeats one index.
- `solution`: null unless converged; then
  `{evaluation_index, psi_rad, residual_m2_s}` owned by that row.

OOD retains every admitted row and stops without recovery. Before two computed
endpoints the bracket is null. Interior OOD retains the prior valid bracket.
`NOT_BRACKETED` retains the tested endpoint interval for diagnosis, not a claim
that it brackets a root. No separate full requests or original root are retained;
row psi plus the caller template reconstructs requests, and full hashes bind them.

All three counts (`residual_result_count`, `load_result_count`,
`lookup_result_count`) equal the number of fully guarded admitted rows, including
OOD. They are accepted-result counts, never attempt counts. Unexpected V134
statuses, malformed responses, rehashed tampering or representational child failure
cause atomic `EXECUTION_FAILED` / `RESIDUAL_BOUNDARY_FAILED`: empty outputs and
units, earlier accepted counts only. No child failure cause is trusted. Parent
arithmetic/export failures are sanitized as `SECTION_SOLVE_EXECUTION_FAILED`.
Ordinary exceptions are sanitized; `BaseException` propagates. Persistent hash
failure clears both hashes and all payload. Output walks bracket sealing.

Input JSON is bounded before copying or hashing: 32,768 nodes including keys,
depth 12, 256 items per container, 2,000 characters per string, strict UTF-8,
1,023 integer bits, exact builtin types, and finite floats. Each actual V134
request separately meets 32,768 nodes/depth 10. Each child response meets
65,536 nodes/depth 24. Root outputs allow 2,097,152 nodes/depth 32, covering sixteen
full children (at most 1,048,576 child nodes) plus metadata and unit traces without
duplicating full requests. Static polar limits remain eight tables × 256 rows;
aggregate work is bounded by 16 × 8 × 256 rows. There are no hidden model calls.

Native request hashes and full response hashes use sorted compact UTF-8 JSON,
`ensure_ascii=False`, `allow_nan=False`; only `evaluation_sha256` is omitted from
the evaluation digest. Fresh catalogs and responses do not share mutable caller
objects. Source URLs and units come from accepted local catalogs; no source fetch
is performed. Hashes do not authenticate the caller, source, author or runtime.

This is numerical convergence of sampled binary64 residuals, not a root error
bound or proof of mathematical continuity, continuous polar coverage, physical
validity, aircraft feasibility, or a blanket Ning convergence guarantee. Exact
binary64 zero is not a mathematical proof. V134's positive-branch, wake-model,
polar applicability and empirical Prandtl limitations remain in force. Physical
validation, numerical qualification and runtime identity stay `NOT_ESTABLISHED`.

The tests separate actual V134 evaluations from synthetic algorithm callbacks.
Exact-zero endpoint/midpoint, adjacent-float stagnation, and interior-OOD branches
are exercised directly through `_bisect` with explicitly fake test callbacks.
Those fixtures make no claim that an actual guarded V134 request produces these
branches. Actual endpoint OOD, two-tolerance convergence, sixteen-call exhaustion,
full child traces and bracket replay use real V134 evaluation on invented polar
values. Tampering and failure injection verify refusal rather than physical
behavior or validation.
