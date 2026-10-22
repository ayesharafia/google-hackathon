# Autonomous backlog

Priority: **1. Drone payload/mission; 2. Shared foundations supporting drone.**
Thermal, data-center and electrochemical domains are not selected. This carries
forward B's confirmed drone direction, not a new scientific acceptance.

Default run budget: up to three tasks. Choose one task at a time using
`AUTONOMY.md`. The first suggested run is SC001, SC002, SC003 unless a regression
or new user direction takes priority. Seven preparation tasks are ready.

The numbers below measure preparation completeness. They are not approved
physical error tolerances or automatic ladder passes. Preserve all branches.

| ID | Task / specialist | Domain | Zone | Done means (a number) | Blocked by | Status |
|---|---|---|---|---|---|---|
| SC001 | Inventory baseline constants and numerical guards; validation-engineer, coordinated scientifically | shared/drone | GREEN | Cover all 5 modules: atmosphere, performance, trim, capacity, mission_capacity. Classify 100% of discovered physical constants/guards as cited, definition, historical software policy or UNVERIFIED; explain exclusions. Change 0 values. | None; inventory only, migration is separate | ready |
| SC002 | Map DR-01 evidence to its proposed protocol; physics-architect | drone | GREEN | All 5 levels L0-L4 mapped to existing evidence/reference, metric, proposed criterion and approval gap; 0 inferred passes and 0 new tolerances | None; document missing evidence explicitly | ready |
| SC003 | Index kickoff reproducibility evidence; validation-engineer | shared/drone | GREEN | Index all 7 retained assets with hashes, commands, source identity and runtime; report every mismatch; distinguish synthetic diagnostics from approved validation | None; use reports/assets/drone-kickoff-2026-10-22 | ready |
| SC004 | Audit existing GCI capability/applicability; physics-architect, fresh auditor | shared/drone | GREEN | 1 implementation/test inventory; all 3 historical sphere mesh records linked with assumptions; 0 new convergence/aircraft claims; distinguish pending DR-01 algebraic exception | None; inspect existing tools before proposing replacement | ready |
| SC005 | Research one isolated-propeller benchmark candidate; validation-engineer | drone | GREEN | 1 source package: exact URL/date, bytes/hash where rights permit, revision/rights, units, RPM, diameter, condition and uncertainty metadata. Classify every required field present/missing; invent 0 density/efficiency/duty values | None for research; acceptance/source-use gaps stay explicit | ready |
| SC006 | Refresh V4 independent-review handoff; scientific-orchestrator | drone | GREEN | 1 current-commit packet covering 7 topics: conditioning, torque allowances, endpoints, failure state, axial coverage, scenarios/caps, historical compatibility. Each has source/test/evidence/gap links; 0 invented approvals | None; preparation does not perform external review | ready |
| SC007 | Register proposed DR-01 invariance campaign; validation-engineer, fresh auditor reviews plan | drone | GREEN | Document 4 proposed segment subdivisions plus map-knot/scaling variants, independent reference derivations and outputs; 0 implementation changes or adopted tolerances | None for registration; execution/acceptance depends on zone and approval | ready |
| SC008 | Draft source-bound DR-02 isolated-map qualification; spec-writer | drone | GREEN | Exactly 12 template sections, at most 5 questions, AWAITING SCIENTIST, explicit missing metadata/bands and preregistered holdout protocol | SC005 | blocked |
| SC009 | Human DR-01 decisions: scope, arithmetic criteria and L3 exception | drone | RED | 1 named reviewer and explicit answers recorded for the existing spec; no AI substitutes | [Scientist inbox](INBOX_FOR_SCIENTIST.md), reviewer unassigned | parked |

## Existing work and restrictions

- [ROADMAP.md](ROADMAP.md) records physics evidence. [plan.md](plan.md) records
  application/release work; neither is reset by this backlog.
- [DR-01](specs/drone-hover-payload-baseline.md) remains AWAITING SCIENTIST.
  Approved execution is blocked; experiments require a classified YELLOW task
  and a `provisional/` branch. None is started by setup.
- No new dependency, physical constant migration, changed equation/tolerance,
  stateful battery coupling or new domain is implied by these GREEN tasks.
- Product work follows AUTONOMY's priority/eligibility rules. Existing software
  checks do not establish L4 aircraft qualification.
- Replenish to at least five ready tasks when the count falls below five. Count
  only dependency-free ready work. Keep at most three distinct specs awaiting
  scientist review.
