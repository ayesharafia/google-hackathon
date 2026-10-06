# Private engineering platform upgrade

Authorized 6 October 2026. `plan.md` is the sole status tracker. This specification
supersedes the earlier conditional mission-work trigger: complete missions and
powertrain lead the next engineering capability. Real aircraft data and a named
client engineering owner remain unavailable.

## Reviewable delivery slices

- U01 / N0.5, N1, IP07, IP10: retain a fresh V4 baseline before tuning; package
  application and worker resources, locked dependencies, immutable build identity,
  migration/version checks and CI. Preserve historical artifacts. Independently
  review endpoint roundoff and the conditioning claim before extending physics.
- U02 / N3.2, IP16: bounded inventory/history, verified report reuse keyed by the
  accepted result, frozen inputs and renderer/dependencies; reuse identical accepted
  study specifications only after source integrity checks. Re-run the baseline.
- U03 / IP13: PostgreSQL metadata and private S3-compatible artifact adapters;
  local SQLite remains explicit. Exercise migrations, concurrent optimistic saves,
  object corruption and cross-project denial. No provider is selected implicitly.
- U04 / IP14–IP15, IP17: individual revocable sessions, organizations, project
  roles, expiring one-use invitations, authenticated reviews; deny access by default.
  Durable bounded jobs, attempts, progress, cancellation, leases and fencing prevent
  stale result publication. Exercise worker loss and restart.
- U05 / N2.4, IP05, IP11: after current model review, deliver a separately versioned
  analytic battery/mission profile with shared SOC, voltage/resistance/temperature,
  current and thermal checks, ordered transitions and reserve exactly once. Independent
  constant-load/energy/convergence checks precede any engineering qualification.

## Follow-on engineering gates

Rotor operating domains require sourced RPM, pitch, density, axial/edgewise inflow
and electrical conditions. Reject gaps and extrapolation. Retain Pshaft = Q × Ω;
interpolating torque and watts independently cannot violate it. General curves use
adjacent-segment MILP with retained bounds/gaps/unresolved outcomes. Forward-flight
trim needs covered edgewise maps and sourced airframe loads. Static fault authority
must remain distinct from transient control with declared inertia and dynamics.

Qualified mission studies lead to bounded configuration enumeration, coupled pack
mass/energy/voltage/thermal sizing, CG exploration, sensitivity and Pareto comparisons.
Retain every candidate's sources, model and execution. Do not claim global physical
optimality without appropriate bounds; probabilities need distributions and
correlation evidence. Deterministic scenarios remain separate.

CFD proceeds through I01/I02 sphere domain/sampling checks, isolated rotor source
verification, installed interactions and independent measurements; rotating/transient
methods only where needed. Retain mesh/domain/convergence evidence, pressure/shear,
source forces and resource use. A single force ledger prevents double counting.
Capacity coupling requires qualification. Assembly STL cannot supply blade geometry
and airfoil polars for BEM.

## Verification and operating targets

Baseline: fresh V4, five cold starts, three repeats at 1/10/25/50 concurrent users,
startup, full-body p50/p95/p99, throughput/failures, CPU and high-water RAM. Label
first-render and repeated PDFs separately. Simulation: three coarse/medium sphere
runs, wall/CPU/peak memory by mesh, solve and postprocess stages. Profiling is separate
from timing. Retain raw observations and exact workload/model/build identities.

Proposed hosted targets (not measurements): reads p95 500 ms/p99 1 s; saves p95
750 ms; submissions p95 250 ms; bounded 1,000-project inventories; RPO 15 minutes,
RTO 60 minutes demonstrated by restore; no lost accepted jobs/stale publication;
24-hour representative soak with bounded memory, queue and storage. CFD turnaround
follows compute-budget and mesh measurements. Local experiments do not prove hosted
SLOs. Restore and rollback drills, browser keyboard/mobile/native 200% zoom, expired
sessions, conflicts and downloads join unit/reference/integration CI.

## Decisions and release limits

D01–D03 and D07: provider/region/budget, identity/MFA policy, confidentiality,
residency/retention and expected scale are required before external deployment.
D04–D06: measured inputs, named owner and preregistered engineer-owned held-out
validation tolerances are required for real engineering claims. Current independent
review and human engineering acceptance are required before a physics merge/tag.
Build provider-neutral local adapters and synthetic integration now; retain all
failures. A software pass cannot promote aircraft evidence or satisfy an external
review. Old V2/V3/V4 result contracts remain readable, with no in-place migration of
historical evidence.
