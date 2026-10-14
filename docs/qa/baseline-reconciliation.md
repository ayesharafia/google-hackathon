# Development baseline reconciliation — 14 October 2026

Documentation-only implementation of roadmap A01. `plan.md` remains the active task tracker. This matrix distinguishes the integrated local checkpoint from unmerged review-branch work; it does not accept the model or authorize integration.

## Inspected identities

| Snapshot | Exact identity | Role |
|---|---|---|
| Integrated main | `802c63a0a9f9b776f92fb94efe24a1708d95ebdb` | Local saved-design/static-hover checkpoint and historical evidence |
| Platform candidate | `60c0ab2efa7b2352d02458a517c4fe2fe5969b5b` | `codex/production-platform`, draft PR #8; stacked model/platform work |
| Model parent recorded by review packet | `5e8cf066eea164398dbd94380175ae7d00a4279c` | `codex/next-development-plan`; current model acceptance pending |
| Roadmap proposal | `b5209946d11d3a73b6f5cc83cb815d1980847275` | Open draft PR #9, `codex/development-roadmap-2026-10-14`, based on platform `60c0ab2`; proposed sequence, not accepted capability |

Rows bind capabilities to inspected snapshots where they are present, not to an inferred first implementation commit. Dated receipts may describe earlier source revisions and must not be treated as a fresh exact-head test pass. Both inspected recursive trees were complete and contained no `AGENTS.md`.

Read-only repository QA for this implementation also compared Git ancestry: open draft PR #1 head `966d99d3`, #2 head `3cbafece` and #3 head `b5243400` are ancestors of main `802c63a0`. Their open draft state is not evidence that their changes remain absent. Main → model parent is six commits ahead/zero behind; model parent → platform is ten commits ahead. The 18 declared numerical-module blob identities match model parent → platform. This verifies declared-file byte equality, not completeness of the dependency closure or numerical acceptance.

## Capability, evidence and remaining gate

| Capability | Commit-aware presence | Evidence at platform snapshot | Review/status and next gate |
|---|---|---|---|
| Saved projects, frozen revisions, mass/CG, retained maps, static-hover trim, fixed-pack constant segments, comparisons/reports | Main `802c63a0`; also platform `60c0ab2` | [Local checkpoint](local-workbench-merge.md), [bounded model review](../reviews/2026-10-05-local-hover-claude.md) | Integrated historical synthetic scope; no aircraft or human engineering acceptance |
| Semantic numerical identity; V2/V3 historical readers and opt-in V4 | Platform `60c0ab2`, stacked model parent above | [Model execution](next-development-execution-2026-10-05.md), `src/physimesh/projects/studies.py`, [review packet](production-model-review-packet.md) | Independent closure/contract review pending; compare exact candidate bytes and dependencies |
| Raw/conditioned maps, varying-torque shaft handling, residual/power envelopes | Platform `60c0ab2`; absent from main's documented supported scope | [ADR-0005](../decisions/ADR-0005-conditioned-axial-profile.md), [validation](../validation/capacity-uncertainty.md) | Fixture implementation, independent physics review pending; envelope does not prove general physical payload conservatism |
| Failed-rotor trim, exact matching-inflow axial climb | Platform `60c0ab2` | [Model execution](next-development-execution-2026-10-05.md), [validation](../validation/capacity-uncertainty.md) | Review pending; endpoint roundoff, unsupported motion/coverage and failure semantics require review |
| Joint deterministic scenarios and separately sourced external caps | Platform `60c0ab2` | [Validation](../validation/capacity-uncertainty.md), `tests/projects/test_scenario_limits.py` | Review pending; no probability or authenticated engineering approval inferred |
| Explicit-unit STL/link preview, governing rotors, completed downloads/zoom/conflict journey | Platform `60c0ab2`; main retains earlier browser limitations | [Model execution](next-development-execution-2026-10-05.md), [audit](local-workbench-design-audit.md) | Recorded synthetic Chromium journeys; real geometry and client UX acceptance pending |
| PostgreSQL/private objects, migrations, sessions/roles/invitations | Platform `60c0ab2` | [Platform execution](production-platform-execution-2026-10-06.md) | Local integration evidence; provider, identity/MFA and private-bucket qualification pending |
| Queued bounded studies/PDF, cancellation/retry/leases/fencing, backup/restore | Platform `60c0ab2` | [Platform execution](production-platform-execution-2026-10-06.md), [operations](../production/operations.md) | Local fixture recovery verified historically; hosted CFD ownership, provider DR and long soak pending |
| Locked wheels/resources and bounded release images | Platform `60c0ab2` | [Release receipt](production-release-2026-10-06.json) | Historical Linux/amd64 builds at `84fc72b`; exact current-head reproduction and deployment approval remain separate |
| Performance qualification | Platform `60c0ab2` contains retained measurements | [Repeat audit](production-performance-2026-10-06.md) | Recorded 50-user submission p95 592.1 ms exceeds proposed 250 ms; 303.8-second single-client soak is not 24-hour acceptance |
| Stateful battery/motor/ESC and chronological mission U05 | Not implemented as accepted capability in inspected plan | [Review prerequisite](production-model-review-packet.md), [upgrade](../production/upgrade.md) | Current-model review and explicit flight-critical approval precede extension; do not reset state or invent parameters |
| Real-aircraft qualification/private deployment | No accepted capability established by either snapshot | [Data request](../client/aircraft-data-request.md), [active tracker](../../plan.md#active-slice-status) | Real source-labelled inputs, named engineering owner, held-out validation, hosting/data decisions and explicit deployment approval |
| Sphere CFD/sampling investigations | Main retains sphere foundation; platform adds capability-only grid probe | [Execution receipt](next-development-execution-2026-10-05.md) | Sphere is verification; I02 campaign unrun; no installed-aircraft validation or inferred cause of +2.65% gap |

## Documentation drift to preserve explicitly

Main's README says scenarios/caps are the next independent model work and individual identity/recoverable jobs are pending. Platform's active table and receipts report implementations with unclosed acceptance gates. These statements describe different commits. Use the platform table for planning its candidate, and main's records for integrated behavior. Historical dated plans remain specifications rather than independent queues. Do not merge the platform merely to reconcile prose.

Historical receipts report 511 model-branch unit tests, then 529 platform unit tests, and 118 reference tests; none were rerun for this documentation exercise. Historical Claude reviews cover their recorded bounded predecessors, not the current V4 model. The release source revision is `84fc72b`, not the final inspected platform `60c0ab2`; the historical 529/118 record is not a current-head execution claim. Current read-only module comparison verifies only the declared 18-file source equality.

## Next bounded actions

1. Follow [the exact-candidate review checklist](model-review-checklist.md); attach actual command results and identities to an issue/PR receipt.
2. Resolve independent model findings within expressly approved scope; human engineering acceptance remains a separate record.
3. Profile submission before tuning, preserving conflicts, source integrity, idempotency and fencing. Keep real-data intake preparation separate from sending or inventing inputs.
4. Review and approve integration explicitly. No merge, release, flight-critical change or deployment is authorized by this reconciliation.
