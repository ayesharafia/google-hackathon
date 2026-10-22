# Drone development roadmap — 14 October 2026

Status: proposal. This document does not approve physics changes, merges, deployment, or real-aircraft claims. `plan.md` remains the authoritative active status tracker; this proposal supplies sequencing and candidate issue scopes.

## Objective and inspected baseline

Deliver a private engineering workspace that evaluates a declared aircraft design across supported required cases and chronological mission segments, identifies the limiting payload constraint, and produces reproducible evidence.

Inspected snapshots: `main` at `802c63a0a9f9b776f92fb94efe24a1708d95ebdb`; `codex/production-platform` at `60c0ab2efa7b2352d02458a517c4fe2fe5969b5b`, draft PR #8, stacked on `codex/next-development-plan`. Open draft PRs #1–#3 preserve earlier baseline/contract review work. An open PR is not proof that its work is absent from main: compare exact commits and files before planning integration. No tests were rerun for this planning exercise.

Read: README, current platform-branch plan.md, 5 October next-development proposal, 6 October platform execution evidence, production upgrade, model review packet, ADR-0005 and aircraft data request.

The current active table supersedes the earlier proposal's unfinished-task assumptions:
- Local workbench: persisted drafts/frozen revisions, rotor maps, mass/CG, trim, capacity, sequence energy, comparisons and reports.
- N1/N2: conditioned noisy maps, shaft/electrical handling, motor-out, matching-inflow climb and deterministic scenarios are implemented with recorded fixture checks, but current independent model acceptance remains pending.
- Platform draft: PostgreSQL/private object adapters, sessions/roles/invitations, bounded queued studies/reports, cancellation, leases, fencing, backup and reproducible packaging have local evidence.
- Pending: current-model review and human engineering acceptance, real aircraft inputs, provider/identity/data policies, long-duration soak, hosted recovery and stateful mission/powertrain.
- Historical evidence reports 529 unit and 118 reference tests; these were not executed in this planning run.
- Reported 50-user submission p95 of 592 ms exceeds the proposed 250 ms goal. The recorded five-minute soak does not satisfy a 24-hour target.
- No fixed 750 kg target: the active plan explicitly removed it.

## Delivery sequence

### M0 — establish an accepted development baseline

1. Reconcile main, model branch and platform PR #8 into a commit-aware status matrix. Link each capability to its implementation commit, evidence, review state and remaining gate.
2. Review the existing current-model packet: conditioning scope, torque discrepancy allowances, endpoint roundoff, failed-rotor semantics, matching-inflow eligibility, scenarios/caps and historical contracts.
3. Reproduce appropriate unit/reference/contract checks in an executable environment. Run exact-pinned backend tests only where the change requires them; record skipped or unavailable execution explicitly.
4. Record an independent review receipt against exact source/model identities. A review agent cannot stand in for human engineering acceptance or claim cross-family independence without actual evidence.
5. Resolve findings through small draft PRs within expressly approved scope. Keep flight-critical fixes approval gated.

Exit: exact baseline and evidence matrix; no hidden review blockers; approval record for the scope being extended. Integration/merge requires the user's separate approval.

### M1 — reliable engineering workspace

Proceed in parallel with real-data preparation, without changing numerical semantics.

1. Profile queued-study submission and metadata access; investigate measured causes of latency. Separate queue admission, database work and computation.
2. Add bounded diagnostics and preserve idempotency, integrity checks, optimistic conflicts and fencing while tuning.
3. Close documented disk-pressure and build/runtime-storage gaps with disposable local drills.
4. Prepare a representative 24-hour soak harness with explicit resource budget, cancellation and retained observations. Execute the long soak only where runtime/time/budget permit; never convert an abbreviated run into a pass.
5. Finish project-scoped hosted CFD ownership before enabling hosted CFD routes; keep denial until every input, job, artifact and download is scoped.
6. Preserve useful compare/report journeys with frozen revisions and clear incomplete/unsupported/unresolved outcomes.

Exit: no stale publication or lost accepted jobs in performed tests; resource limits verified; latency compared with unchanged workload; service goals either met or explicitly unresolved. Provider validation remains separate.

### M2 — real design and data intake

1. Name the human client engineering owner and independent approver.
2. Confirm the pilot claim: supported map-based payload/mission assessment; installed CFD has its own later scope.
3. Collect geometry with units/frames, rotor performance raw files and uncertainty, mass/CG/inertia, payload placement, pack/motor/ESC limits and required cases/segments.
4. Retain source rights, hashes, coverage and missing fields. Provide a machine-readable intake checklist; unknowns block only dependent calculations.
5. Before viewing comparison results, register validation conditions, quantities, tolerance ownership and held-out measurements.
6. Test assembly-to-rotor/CG linkage with the supplied design; round-trip numeric placements and show the governing case/component.

Exit: one source-bound design with explicit scope and complete inputs for the chosen model. Synthetic fixtures remain labelled. Sending the prepared request requires an explicit sending instruction and resolved recipient.

### M3 — stateful mission and powertrain (U05)

Starts only after M0's model review gate and explicit approval for flight-critical changes.

Split U05 into:
1. Versioned input/result contracts and state transition specification, preserving V2/V3/V4 readers.
2. Battery state of charge and chronological energy with one reserve convention; no state reset between segments.
3. Supported voltage/internal-resistance/current model with sourced or labelled parameters and refusal outside coverage.
4. Motor/ESC electrical reconciliation, retaining shaft power = torque × angular speed and applying losses once.
5. Supported battery/motor/ESC thermal state and continuous/transient limits.
6. Coupled mission evaluation at one payload across all required cases and segment states; explicit limiting segment/component.
7. UI/report bindings for state trajectories, assumptions, source coverage and discrepancy.

Acceptance: independently derived constant-load cases, energy conservation, timestep refinement, transition/restart equivalence, depleted-pack/current/thermal refusals, historical compatibility and appropriate independent physics review. Analytic fixture success is not measured aircraft qualification.

### M4 — measured qualification and private pilot

1. Run the preregistered held-out comparison; retain failed comparisons and uncertainty.
2. Limit acceptance to tested designs, operating conditions and quantities.
3. Produce a frozen report matching API/package numbers and identifying governing constraints, coverage, review and approval.
4. Complete human engineer and presenter rehearsals, rather than substituting automated browser journeys.
5. Select provider, region, budget, identity/MFA, residency/retention and expected scale.
6. Complete provider-specific identity/object-policy checks, restore/rollback drills and production-like load tests.
7. Stage and deploy only after the user's explicit deployment approval.

Exit: accepted real-data scope plus independently verified private operations; scoped human release approval. No universal aircraft qualification claim.

### M5 — expand only from demonstrated need

- General adjacent-segment MILP maps only when real curves exceed the conditioning policy; retain bounds/gaps and unresolved solver outcomes.
- Forward-flight trim only with covered edgewise maps, attitude and sourced airframe loads.
- Coupled pack/configuration/CG exploration only after stateful mission qualification; preserve candidate evidence and avoid unproven global-optimum claims.
- CFD: finish preregistered sphere sampling/domain studies, then isolated rotor verification and measured installed interactions. Track source/pressure/shear in one force ledger to prevent double counting.
- Symmetry only for eligible geometry, boundary conditions and rotor/load states; asymmetric fault cases require full-domain treatment.
- Rotating/transient CFD and flight dynamics only where the client question requires them and the independent validation gate exists.

## Candidate bounded issues for the recurring lead

These are proposals, not created or labelled issues. The user approves a safe scope by creating/marking its issue agent-ready. Model review acceptance and flight-critical approval are separate gates.

| Candidate | Scope | Acceptance | Dependency |
|---|---|---|---|
| A01 Baseline status reconciliation | Documentation only; map commits and review states to plan.md | Every status has source/evidence/gate; no invented completion; valid links | None |
| A02 Model review reproducibility checklist | Read-only checks and review instructions; no numerical changes | Exact closure/contract identities; performed/skipped checks separated | Exact candidate selected |
| A03 Submission profiling | Sanitized timing and reproducible workload; no tuning initially | Stage timing, repeats and workload identity; no credentials/design leakage | Executable platform environment |
| A04 Latency improvement | One measured bottleneck from A03 | Comparable before/after measurements; conflict/idempotency/fencing checks pass | A03 |
| A05 Disposable disk-pressure recovery drill | Local test harness against disposable resources | Clean refusal/recovery; no stale publication; bounded resource use | Executable isolated environment |
| A06 Data-intake readiness manifest | Schema/report completeness checks; no invented physical defaults | Missing units/frames/source coverage reported; incomplete inputs remain unknown | Existing intake contracts |
| A07 Long-soak harness | Bounded runner, observations and recovery bookkeeping | Short harness smoke; long run clearly pending unless actually performed | Budget/runtime ceiling |
| A08 Hosted CFD ownership | Scoped job/artifact permissions; no solver changes | Cross-project/session denial and owned-path positives | API/job ownership design |

Pick A01 first, then A02 and A03. Issue scope must be small enough for one reviewable change. Do not split a task by arbitrary lines if that prevents meaningful verification.

## Agent workflow and persistent records

Each scheduled run inspects approved agent-ready issues, branches, PRs and previous issue progress; selects at most one nonoverlapping safe task; and stops when none remain. Use real available implementation, QA and code-review subagents and record what they actually did. If an executable environment or a required independent reviewer is absent, state that blocker.

Issue outcome: baseline/head SHA, branch/PR, changed behavior, performed checks, unverified scope, review findings and next action. Store evidence in the repository, retain accepted artifacts unchanged and update plan.md after accepted progress. Draft PRs are the review boundary. Never merge, enable auto-merge, deploy or change flight-critical logic without explicit user approval.

## Resources and planning

Use existing ChatGPT/Codex access for planning, coding and available subagents; this roadmap requires no new paid LLM API integration. Execution availability and subscription limits must be checked on each run. Physical validation still requires real measurements and a named human engineering owner.

Keep local/disposable fixtures as the development default. Hosting and long CFD/soak work need a stated spend/resource ceiling. Estimate each issue after environment reproduction; do not promise calendar completion from hourly scheduling. Critical path: model acceptance → stateful mission → held-out real-data qualification. Data intake and safe software reliability work can proceed alongside it.

## Decisions needed before dependent work

- Human engineering owner, client scope and validation-tolerance ownership.
- Explicit flight-critical change authorization after model-review findings are known.
- Real aircraft dataset and private transfer/recipient instructions.
- Provider/region/identity/residency/retention choices and spend ceiling before hosting.
- Scale and accepted service targets; the submission target remains unmet in recorded evidence.

This planning change performs no code execution, aircraft analysis, deployment or release approval.
