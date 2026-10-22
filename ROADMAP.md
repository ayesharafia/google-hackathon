# Physics evidence roadmap

## Priority and current work

Priority: **Drone payload/mission first; shared foundation work supports it.**
This carries forward B's confirmed direction. Other domains remain unselected.
Use the [v3 Work protocol](.physicore/ops/WORKFLOW.md),
[state](.physicore/ops/STATE.md) and [task ledger](.physicore/ops/TASKS.json)
for current task selection. The tables below preserve the earlier kickoff audit;
the v3 policy supersedes its generic operating rules, without promoting evidence
or changing any feature's approved numerical thresholds.

Drone kickoff: 22 October 2026, source `73793c9`. The user confirmed the drone
payload project: required mission cases, plots and an evidence report. The
scientist reviewer, customer accuracy requirement and scientist's assessment of
the main weakness remain unknown. Proposed choices must be labelled as proposals.

This file tracks physics evidence and the next qualification specifications.
[`plan.md`](plan.md) retains detailed implementation and release status.
See the [kickoff report](reports/drone-kickoff-2026-10-22.md) for actual checks,
sources, limits and the first three tasks.

Historical audit status: 🔴 absent or unassessed; 🟡 scoped evidence, acceptance pending.
Future claims use the case-appropriate [v3 scientific gates](.physicore/ops/SCIENTIFIC_GATES.md).
Listed checks are not a contiguous accepted ladder. Missing evidence is not a
passing L0. Spatial mesh convergence requires a documented applicability decision
for algebraic models and exact constant-power integration.

## Drone (rotor aero + turbulence)
| Phase | Feature | Ladder | Status | Spec | Report |
|---|---|---|---|---|---|
| Foundation / DR-01 | Existing static-hover payload and fixed-pack constant-segment energy | Selected L0, L1 equilibrium/energy and L2 analytic software checks; L3 applicability and L4 comparison/approval pending | 🟡 167 targeted tests passed; customer accuracy unknown | [Awaiting scientist](specs/drone-hover-payload-baseline.md) | [Fresh kickoff evidence](reports/drone-kickoff-2026-10-22.md) |
| Foundation / DR-02 | Isolated rotor source traceability and held-out map comparison | Synthetic source/interpolation checks exist; published held-out campaign unrun | 🟡 Draft next after DR-01; real metadata and tolerance policy required | Not yet drafted; [data requirements](docs/client/aircraft-data-request.md) | [Limits of present map evidence](docs/validation/capacity-uncertainty.md) |
| Restricted physics / DR-03 | Conditioned maps, axial climb, motor-out and correlated scenarios | Selected L0/L1/L2 synthetic checks; current-model independent acceptance and physical benchmarks pending | 🟡 Review existing V4 before extending physics | Not yet drafted; [existing ADR-0005](docs/decisions/ADR-0005-conditioned-axial-profile.md) | [Historical author verification](docs/validation/capacity-uncertainty.md) |
| CFD tool verification | Laminar sphere at Re=100 | Recorded three-mesh sensitivity and correlation comparison; complete accepted ladder not established | 🟡 Historical fine Cd 1.120620183; +2.6463% frozen-correlation gap; no fresh CFD run | [Existing investigation protocol](docs/validation/sphere-investigation-registration.md) | [Native loads and qualified GCI](docs/validation/sphere_re100_loads.md) |
| Aerodynamics | Integrated rotor CFD, turbulence and blade-element prediction | Unassessed as integrated capabilities; separate reference code is not an accepted aircraft solver | 🔴 Scope and validated prerequisites required | Not specified | [Reference-code scope](reference_impl/README.md) |
| Coupling / U05 | Stateful battery, sag, thermal and variable-power mission | Not established by current constant-bus, constant-segment model | 🔴 Await existing-model review and a separately approved spec | [Authorized direction and dependency](docs/production/upgrade.md) | Not accepted |
| Customer validation | Installed-aircraft payload allowance | L6 missing; actual source inputs, held-out measurements and human acceptance absent | 🔴 No operational payload claim | [Client input requirements](docs/client/aircraft-data-request.md) | Not available |

## Thermal
| Phase | Feature | Ladder | Status | Spec | Report |
|---|---|---|---|---|---|
| Not selected | No thermal-domain kickoff in this repository | Unassessed | 🔴 | None | None |

## Data center cooling
| Phase | Feature | Ladder | Status | Spec | Report |
|---|---|---|---|---|---|
| Not selected | No data-center-domain kickoff in this repository | Unassessed | 🔴 | None | None |

## Battery
| Phase | Feature | Ladder | Status | Spec | Report |
|---|---|---|---|---|---|
| Current drone input | Declared fixed-pack usable energy at constant voltage | Selected L1/L2 bookkeeping evidence; no electrochemical or thermal validation | 🟡 | [DR-01](specs/drone-hover-payload-baseline.md) | [Existing energy scope](docs/validation/local-hover-and-energy.md) |
| Not selected | Electrochemistry and battery thermal solver | Unassessed | 🔴 | None | None |

## Shared foundation (all domains depend on this)
| Feature | Ladder | Status |
|---|---|---|
| Units / SI config with cited constants | Selected L0/L2 unit/frame tests; constants and thresholds remain distributed and need a source ledger | 🟡 |
| Mesh generation + quality checks | Historical sphere meshes/quality receipts; no current aircraft mesh qualification | 🟡 |
| Validation harness (run + plot vs reference) | 167 targeted + 118 development-reference tests freshly passed; 15-point synthetic diagnostic and comparison plot retained | 🟡 |
| Conservation checker | Static force/moment and constant-power energy checks exist; global fluid conservation not established by force reconciliation alone | 🟡 |
| Mesh convergence (GCI) tool | Analytic estimator tests and qualified sphere sensitivity record; not total accuracy or installed-aircraft evidence | 🟡 |
