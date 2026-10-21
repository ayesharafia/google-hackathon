# Client production delivery specification — 21 October 2026

Approved by the user in the planning conversation and authorized for implementation.
`plan.md` remains the status tracker; this file defines the accepted delivery work.
Starting main: `d2e78627d404c4dd945e068d9e7ecf9a0f0d079f` (PR #20).

## Outcomes and defaults

Deliver an engineering application connecting aircraft geometry, rotor commands,
mission state and limiting payload, with reproducible client reports. Deliver
three separately accepted milestones: M1 polished local fixture workflow; M2
reviewed real-data engineering candidate; M3 privately operated client service.

Use labelled fixtures while client data is unavailable, quality-based milestones,
the PhysiCore identity, the existing FastAPI/Python/plain-JS/three.js stack, and
separate bounded workers. Hosting selection remains the user's later decision.
Keep PostgreSQL/private object adapters, local SQLite and immutable historical
records. No fixed payload target, framework rewrite or implicit aircraft approval.

Calculation outcome, numerical verification, model validation, engineering approval,
workflow review and deployment status remain separate. Four agents may run at once;
lead, model, product, platform and independent QA responsibilities rotate through
those slots. Cross-family model review and human engineering acceptance are external
requirements, not implied by same-family agent roles.

## Phase work packages

Each package must bind an owner, dependencies, interfaces, failure cases, tests,
retained evidence and reviewer before implementation. Effort is engineering days,
excluding external reviews, measurements and client waiting time.

### C00: Baseline and acceptance contract (3–5 days)

- Reconcile main, exact source/library identities, existing fixtures and CI receipts.
- Maintain one active roadmap and an explicit implemented/verified/accepted/deployed distinction.
- Establish the named engineering, independent review, product and operational owners.
- Map client requirements to task IDs, evidence and release approvers.
- Reproduce the software baseline and retain unknowns without invented client decisions.

Exit: reproducible baseline and scoped acceptance ledger; missing external owners
block their gates while independent software work continues.

### C01: Independent current-model acceptance (5–10 days plus remediation)

Depends on C00. Review V4 conditioning scope, torque discrepancy treatment, frame
conventions, six-component balance, mass/CG, shaft/electrical identity, failed rotors,
matching-inflow climb, common-payload scenarios/caps and chronological energy.
Review floating-point endpoints and infeasible/unsupported/unresolved distinctions;
retain historical contract semantics. Use exact model hashes and independent
derivations. Exit: cross-family review and required human scope acceptance recorded.

### C02: Engineering intake and provenance (8–15 days)

Build structured assembly, mass, rotor/electrical, mission, uncertainty and allowable
intake. Retain original bytes before normalization, explicit units/configuration,
calibration/uncertainty/rights/applicability and source revision bindings. Provide
source catalog and raw/conditioned inspection; conditioning requires an explicit
policy. Save incomplete drafts, group actionable blockers and retain gap ownership.
Exit: complete and incomplete fixture round trips, restart/export identity and no
silent replacement or approval of missing inputs.

### C03: Client workbench (20–35 days)

Depend on C00 and C02 interfaces. Add Design/Sources/Mission/Readiness/Runs/Results/
Review navigation, explicit draft/revision/study context, linked component/rotor/case
selection, visibility/isolation, independent component instances, frame/axis legends,
CG/payload markers and precise numeric/viewport placement. Implement reviewed repair
proposal/apply/revert with original retention. Replace expert-only scenario/cap JSON
with sourced forms. Historical studies display frozen geometry. Dirty context switches,
conflicts, late responses, reconnect and save status preserve work. Share licensed
typography, units, colors and chart treatment across reports/UI.

Exit: no-JSON fixture journey, keyboard and 200% zoom acceptance; desktop authoring
at 1280/1440 and mobile review at 390px; no stale geometry or silent data loss.
Target WCAG 2.2 AA and verify meaningful numeric alternatives to 3D interactions.

### C04: Stateful mission/powertrain (30–60 days)

Depends on C01 and C02. Introduce a new stateful profile/result V5 without modifying
V4 semantics. Version sourced discharge-only OCV/resistance/lumped-thermal battery,
pack topology, charge/SOC, temperature, initial conditions, motor/ESC continuous/burst
limits and auxiliary loads. Reconcile electrical boundaries and losses once. Carry
state through ordered constant segments and supported ramps; re-evaluate operating
points, source coverage, cutoff/thermal/current events and reserve exactly once.
Retain trajectory/conservation/integration/convergence evidence and limiting event.
Use bounded deterministic payload exploration without unproved monotonicity/global
optimality claims. Unsupported regeneration/swaps/resets/flight regimes refuse.

Exit: independently derived constant-load/limit/order-sensitive/convergence fixtures,
reviewed search semantics and complete persisted UI/API/export slice. Numerical
failure is unresolved computation, never proof of physical infeasibility.

### C05: Required operating-envelope extensions (15–40 days per extension)

Data-triggered before qualification. Version map families and covered interpolation
regions/holes for RPM/pitch/density/inflow/electrical conditions. Add adjacent-segment
MILP only when eligible real curves need it; retain bounds/gaps/commands and recompute
identities including shaft power = torque × angular speed. Forward flight requires
sourced airframe loads and covered rotor data. Static failure allocation is separate
from transient recovery/controller authority. Exit: supported coverage for every
required client condition, held-out component checks and independent review.

### C06: Results, reports and engineering attestations (12–20 days)

Build one server summary for UI/PDF with separately labelled nominal, scenario and
checked allowable bounds. Show limiting cases/segments/components, margins, residuals,
source coverage and viewer/timeline links. Compare named entities/constraints while
withholding incompatible numeric deltas. Deliver executive report, engineering detail,
figures, complete evidence bundle, readable Unicode/long content and trusted integrity
receipts. Bind authenticated engineering attestations to exact sources/model/results
and supersession history; workflow reviews remain separate. Publish selected immutable
client packages with publication-scoped access, preserving historical bytes/renderers.
Exit: API/UI/PDF equality, inspected pages and negative publication-permission tests.

### C07: Security, accounting and recovery (20–35 days)

Track recoverable artifact reservation/persistence/acceptance/materialization and
separate logical project accounting from physical storage. Reconcile interrupted
writes; shared or accepted evidence must survive cleanup. Implement policy-bound
archive/retention/legal hold/deletion and append-only security/audit actions. Use
database lease authority for multi-host time, preserve generation fences and test
every crash/cancellation/outage boundary. Maintain bounded authenticated polling and
reopened job/attempt state. Logout alone preserves admitted work; loss of run permission
cancels queued/fences affected running work. Complete all-route authorization, body/
multipart/complexity/concurrency limits, dependency readiness and actionable monitoring.
Map applicable controls to OWASP ASVS 5.0 Level 2. Exit: accounting convergence, no
stale acceptance/tenant leakage, safe recovery and retained negative-test evidence.

### C08: Performance, endurance and disaster qualification (10–20 days plus campaigns)

Profile actual bottlenecks. Repeat 1/10/25/50-user workloads with cold/warm/first-export
separation; retain full-response latency, errors/overloads, throughput and resources.
Existing proposed targets: reads p95 500ms/p99 1s; saves p95 750ms; admission p95 250ms
at the declared supported load. Perform budgeted 24-hour mixed-tenant studies/reports,
resource and service outages, retry storms, restore/migration/rollback and accepted-job
checks. Inventory dependencies/licenses/SBOM/vulnerabilities, pin reviewed CI actions
and restrict workflow permissions. Exit: measured targets/recovery/resource behavior;
short smoke, sampled thresholds and injected ENOSPC do not replace full qualification.

### C09: Real aircraft validation (10–20 analysis days plus measurements)

Requires reviewed models and client data/owner. Approve source/configuration/mass/CG/
electrical intake; preregister observations, uncertainty and engineer-owned tolerances.
Separate calibration from held-out validation. Validate component → powertrain →
installed propulsion → mission → payload, retaining failures and unsupported regions.
Bind human acceptance to exact scope/configuration/cases/reserve/faults/allowables.
Exit: reproducible accepted real-design report; fixtures/sphere cannot satisfy it.

### C10: Hosting qualification (10–20 days after user's decisions)

Record provider/region/budget/residency/retention/identity/scale before execution.
Use isolated staging/production, versioned infrastructure, private IAM/encryption,
PostgreSQL/object backups and bounded Linux workers. Complete OIDC code/PKCE and
same-origin server sessions; secure cookies, CSRF/origin/redirect handling, rotation,
revocation/MFA and no browser persistent provider credentials. Add TLS, distributed
abuse limits, private monitoring/alerts and production fixture-login restrictions.
Demonstrate coordinated restore/rollback and proposed RPO15m/RTO60m before commitments.
Exit: selected-provider security, recovery, capacity and operator acceptance.

### C11: Client acceptance and launch (5–10 days)

Requires applicable prior gates. Complete UAT, two human narrated rehearsals and
backup replay; observe unaided workflow/result/scope comprehension. Resolve blockers,
freeze identities, provide user/method/validation/operations/restore guides and
known limits. Launch one explicitly approved invited client workspace with rollback,
production smoke and ten business days of monitored support. Exit: signed scope-bound
client acceptance and transferred ownership/escalation/backlog.

### C12: Separately qualified advanced capabilities

Move into the critical path only when the required client claim depends on it.
Bounded configuration/CG/pack exploration must couple mass, energy, voltage and
thermal state and retain every candidate. Probability needs sourced distributions/
correlations. CFD proceeds from sphere investigations to isolated rotor sources,
installed interactions and measurements with one force ledger, before capacity
coupling. Rotating/transient methods need use-case validation; blade methods need
blade geometry/polars. Structural allowables may be ingested; FEA/certification and
flight-control implementation require separate scope and qualification.

## Interfaces and compatibility

- Keep the existing project/revision/study routes and derive methods from frozen inputs.
- Separate original geometry assets from independently identified instances.
- Add versioned source catalog, powertrain/mission/state and V5 trajectory contracts.
- Add read-only study summary, engineering attestation and publication contracts.
- Preserve existing V1–V4 retained bytes; no in-place semantic upgrades.
- Bind source/renderer/font/library changes into new immutable publication identities.

## Acceptance ledger

| Requirement | Evidence and approval |
|---|---|
| Unknown/unsupported inputs | Saved incomplete fixtures; precise refusal; no dependent headline |
| Nominal/scenario/allowable interpretation | Independent projection tests; API/UI/PDF equality; no approval promotion |
| Historical geometry/source identity | Edited-draft/frozen-study browser regression and unchanged exports |
| Conflicts/context changes | Two-tab 409, dirty org/session cancel/confirm and late-response tests |
| Stateful conservation/search | Independent analytic/event/order/refinement tests and model review |
| Private publication/access | Per-resource negative tests, revocation and exact package bindings |
| Write/job failure | Storage admission, partial write, cancellation, generation and crash matrix |
| Restore/performance/endurance | Measured recovery/workload receipts, exact versions and skipped-check separation |
| Real aircraft claim | Held-out source measurements, preregistered tolerances and named engineering approval |
| Client launch | Usability/rehearsal/UAT receipts, operator readiness and signed release scope |

External engineering/model approvers, real client inputs and provider/policy decisions
remain unassigned/unavailable until actually provided. No acceptance field is filled
with an inference-account identity or an invented approval. Hosting is deferred;
safe local software work continues. Review progress weekly by completed evidence,
remaining effort, external blockers and the next client-visible increment.
