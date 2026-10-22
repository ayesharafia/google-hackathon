# Working instructions for this repository

The user adopted the simulation kit and its revised autonomy workflow on
22 October 2026. These instructions apply
to Codex and other coding agents working in this repository. Read the documents
below at the start of a task, before planning or editing. Read the complete
applicable role and command definitions before using that workflow.

## Required reading

1. [CLAUDE.md](CLAUDE.md): team responsibilities and the physics delivery loop.
2. [AUTONOMY.md](AUTONOMY.md): decision zones, autonomous cycle and run budget.
3. [VALIDATION.md](VALIDATION.md): verification ladder and reference requirements.
4. [PLAYBOOK.md](PLAYBOOK.md): evidence questions, role separation and phase order.
5. [DECISIONS.md](DECISIONS.md): append-only assumptions and approval log.
6. [Adoption notes](docs/working-method/sim-kit-adoption.md) and
   [autonomy integration](docs/working-method/autonomy-adoption-2026-10-22.md): clarifications and
   how these documents apply to the existing drone project.
7. [ROADMAP.md](ROADMAP.md), [plan.md](plan.md), and relevant existing specs,
   decisions, validation receipts and reports for the requested work.

The `.claude/agents/` and `.claude/commands/` files define workflows that apply
by role and task, even when the current tool does not expose Claude slash
commands. Do not claim a command was installed in Codex or ran automatically.

## Autonomous orchestration

On broad prompts such as “keep working”, “update this project”, “develop further”
or “next”, use [.claude/agents/orchestrator.md](.claude/agents/orchestrator.md).
Read `BACKLOG.md`, the latest digest, the last five journal entries and both inboxes. Choose work
using `AUTONOMY.md`, write the five-line plan first and delegate to specialists.
Route scientific work through the
[scientific orchestrator](.claude/agents/scientific-orchestrator.md).
Default to at most three tasks per prompted run, within available runtime and
the user's budget. Keep only one writer on a module at a time.

GREEN work may proceed and must be logged. YELLOW work, including new
dependencies or provisional physics, stays on `provisional/<feature>` and never
merges without explicit approval for that concrete change. RED decisions go into
the appropriate inbox; continue independent ready work. No response or timeout
counts as approval. Preserve all branches under the user's retention instruction.
Finish with a short digest at the top of `JOURNAL.md`.
After any spec draft, synchronize its backlog and scientist-inbox entry; keep
at most three distinct specs awaiting review, including directly requested drafts.

The scientific orchestrator is an AI coordinator, not a human scientist or an
approval authority. Role separation does not establish cross-family independence.
When tools provide subagents, use them. Otherwise record sequential role handoffs
without claiming an independent review that did not occur. Workflow adoption
does not create a recurring schedule or authorize contacts, spending or deletion.

## Physics work

- Follow spec -> scientist sign-off -> independent validation tests first ->
  solver implementation -> independent audit -> plain-language report -> lead
  decision. Use the supplied templates in `templates/`.
- The new autonomy policy permits provisional implementation of an unapproved
  draft as YELLOW work only. Keep the spec unapproved, freeze independently
  authored experimental checks before builder work, and retain the work off main.
  This is not the approved `/build` path and grants no physics acceptance.
- Keep validation-engineer and solver-builder work separate. The builder must
  not alter validation assertions or reference data anywhere (including `tests/`)
  or approved tolerances. Use a fresh
  auditor for physics acceptance. State who performed each role.
- Record actual human approvals; agent conclusions cannot stand in for scientist
  sign-off or lead acceptance. Advance unblocked preparation while approvals or
  external data are pending.
- Use explicit units and SI internally. Trace constants and coefficients to
  cited sources and the applicable approved spec/configuration.
- Never invent a reference, silently loosen a tolerance, tune a parameter to fit
  a benchmark, or present a successful run as proof of correctness.
- Report errors, approved tolerances, conservation imbalance, convergence,
  comparison plots, valid ranges and missing evidence. Do not label a physics
  feature ready without the applicable ladder evidence and review gates.
- Append changes to assumptions, equations, boundary conditions and tolerances
  to `DECISIONS.md`, linking the relevant existing ADR when applicable. Preserve
  old entries and retained result/source records.
- Apply the interpretation notes in `docs/working-method/sim-kit-adoption.md`.
  The starter benchmark examples and numbers are not approved project inputs.

## Scope and status

The repository currently implements the drone module. Thermal, data center and
battery electrochemistry headings in the starter kit are possible domains, not
instructions to start implementing them. Start the workflow appropriate to the
user's current request; do not run every embedded command or example prompt.

The [22 October drone kickoff](reports/drone-kickoff-2026-10-22.md) populates
`ROADMAP.md` with scoped physics evidence and qualification work. Retain
`plan.md`'s active slice table as the detailed implementation/release status record.
Treat missing ladder evidence as unassessed, not as a passing L0 check. Preserve
earlier evidence and approval scopes; adoption alone does not promote results.

Documentation import, repository maintenance and ordinary UI work do not by
themselves require physics sign-off. Physics behavior and physical claims do.
Continue to honor the user's interface design law on interface tasks.
