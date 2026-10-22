# AUTONOMY.md : How Agents Work Without Being Told What To Do

When B says anything vague ("develop further", "keep going", "work on something", "next"),
agents run the **Autonomous Cycle** below. B's direction, when given, always overrides the cycle.

## Decision rights (who may decide what)

| Zone | Agents may... | Examples | B / scientist involvement |
|---|---|---|---|
| 🟢 GREEN : decide and do | Act, log it in JOURNAL.md | Refactors, test harness, plotting, mesh tools, UI, docs, performance work that keeps all tests green, drafting specs, finding benchmarks, L0 to L2 checks against exact math answers | Reads daily digest |
| 🟡 YELLOW : decide, do provisionally, flag | Work on a `provisional/<feature>` branch, never merge to main, never call it validated | Building against a spec still AWAITING SCIENTIST; choosing between two published models; new dependency | B approves merge in digest |
| 🔴 RED : stop and ask | Prepare everything, then add to an INBOX and move to other work | Approving a spec, changing a tolerance, changing an equation/assumption after approval, any customer-facing "validated" claim, deleting data or features, spending money, contacting anyone | Scientist or B decides |

Golden rule: **when blocked on RED, never wait. Park it in the inbox and pick the next unblocked task.**

## The Autonomous Cycle (orchestrator runs this)

1. **ORIENT** : Read ROADMAP.md, BACKLOG.md, JOURNAL.md (last 5 entries), INBOX_FOR_B.md, INBOX_FOR_SCIENTIST.md, DECISIONS.md. Run the full validation suite. Note anything that turned red.
2. **REPLENISH** : If BACKLOG.md has fewer than 5 ready tasks, ask physics-architect to generate more from ROADMAP.md and the phase order in PLAYBOOK.md.
3. **CHOOSE** : Pick ONE task with the priority rules below. Write a 5-line plan in JOURNAL.md first: task, why this one now, what "done" means as a number, zone, risks.
4. **EXECUTE** : Route to the right agent chain (see table). Respect zones.
5. **CHECK** : physics-auditor reviews anything touching physics. Validation suite must be at least as green as before. If something got worse, revert.
6. **RECORD** : Update BACKLOG.md, ROADMAP.md, JOURNAL.md. Add RED items to the inboxes.
7. **REPEAT** up to the run budget, then write the DIGEST.

## Priority rules (pick the first that applies)
1. Something that was green is now red (regression). Fix it first.
2. Scientist answered something in INBOX_FOR_SCIENTIST.md. Act on it (his time is the scarcest resource).
3. B gave direction in INBOX_FOR_B.md or the prompt. Do that.
4. Shared foundation gaps (units, mesh, harness, conservation checker, GCI tool). Every domain depends on them.
5. The lowest ladder level in the domain B ranked highest in ROADMAP.md "Priority".
6. Draft the next spec so the scientist always has a queue (keep 2 to 3 waiting, never more).
7. Product layer and performance, only on features at L4+.

Never pick: coupling of two pieces where either is below L4; scaling/GPU of an unvalidated solver; a new domain.

## Routing table
| Task type | Agent chain |
|---|---|
| New physics feature | spec-writer, then (after approval) validation-engineer, solver-builder, physics-auditor, explainer |
| Regression | physics-auditor (diagnose), solver-builder (fix), physics-auditor |
| Foundation / tooling | solver-builder, physics-auditor |
| Find benchmark data | validation-engineer |
| Planning / backlog | physics-architect |
| Report for B | explainer |

## Run budget and stop conditions
- Default run: up to 3 tasks, or until B's stated budget.
- Stop a task after 3 failed attempts at the same problem. Write what was tried and what evidence would settle it, park it, move on.
- Stop the whole run if the validation suite is worse than at start and you cannot revert cleanly.
- Never run more than one task that edits the same module at the same time.

## The Digest (end of every run, top of JOURNAL.md, written by explainer)
```
DIGEST <date>
Done:        (max 3 lines, each with the evidence number)
Health:      🟢 x  🟡 y  🔴 z   (change since last run)
Needs B:     (yes/no decisions only)
Needs scientist: (count, oldest waiting days)
Next up:     (what the next run will do unless B says otherwise)
```
B should be able to read this in 2 minutes and reply with one word per decision.
