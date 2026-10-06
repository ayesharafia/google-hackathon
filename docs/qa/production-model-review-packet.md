# Current-model review prerequisite

The production upgrade is stacked on `codex/next-development-plan` at
`5e8cf066eea164398dbd94380175ae7d00a4279c`. The numerical model source modules
remain unchanged in this platform slice. Historical results and the supported
V2/V3/V4 contracts remain readable; platform review decisions are separate records.

Required independent review and human engineering acceptance remain pending.
`plan.md` requires: **“Do not merge or tag a physics release without its required
independent review and human engineering acceptance.”** U05 follows closing this
review, as the user explicitly requested. No reviewer identity or approval is
invented. Analytic fixture implementation can resume after this model gate; real
engineering qualification additionally needs D04-D06.

The reviewer should examine the [current execution receipt](next-development-execution-2026-10-05.md),
[conditioning proof scope](../decisions/ADR-0005-conditioned-axial-profile.md),
[capacity uncertainty validation](../validation/capacity-uncertainty.md),
model-source semantic closure, exact endpoint behavior and historical compatibility.
The retained evidence reports endpoint roundoff and limits of the conservatism
argument explicitly. Do not clamp an endpoint failure or generalize conditioned
compatible-family bounds to all measured operating curves. Require explicit
unsupported/unresolved outcomes where the argument is not established.

The [fresh V4 baseline](production-baseline-2026-10-06.md) establishes local
performance before platform changes. Its six pinned sphere executions preserve
mesh, stage, source and native load evidence; they do not qualify installed-aircraft
CFD. New platform tests exercise reuse, source corruption, optimistic versions,
authorization and stale-worker fencing, without changing the physical solver.

After review, U05 must introduce a distinct stateful analytic profile and result
version: battery SOC, measured/labelled voltage, internal resistance, temperature,
motor/ESC electrical reconciliation, current/continuous/transient limits, ordered
transitions and reserve exactly once. Independent constant-load solutions, energy
accounting and timestep convergence precede supported release. Preserve
`Pshaft = Q × Ω` and existing profiles; no unsourced density scaling or state resets.
