# Simulation kit adoption

Date: 22 October 2026.

The user instructed the agent to read the supplied playbook and `sim-kit.zip`,
install all supplied files in the GitHub repository, and follow this method in
future project work. This records workflow adoption, not a scientist approval of
existing equations, tolerances or results.

## Installed files and sources

The archive's outer `sim-kit/` directory was removed during extraction so its
paths work from the repository root. All 23 file payloads, including hidden
`.claude/` role and command definitions and empty `.gitkeep` files, were extracted
byte for byte. Only `DECISIONS.md` was then extended by appending the adoption
entry; its original bytes remain intact. The pasted playbook matches
`PLAYBOOK.md` after trimming trailing whitespace. The source hashes and per-file hashes are recorded in the
[import manifest](../source/sim-kit-2026-10-22-manifest.json).

- `CLAUDE.md`, `PLAYBOOK.md`, `VALIDATION.md`: standing method and evidence gates.
- `.claude/agents/`: six role definitions, with separate validation and builder
  responsibilities.
- `.claude/commands/`: seven on-demand workflows.
- `templates/`: physics specification and plain-language report templates.
- `specs/`, `validation/reference/`, `reports/`: starter directories.
- `ROADMAP.md`, `DECISIONS.md`: starter tracking and append-only decision log.
- `AGENTS.md`: repository entry point for Codex and other agents.

At import, except for the appended decision entry, the supplied files were unchanged.
The interpretations below resolve wording ambiguities when applying them to
this existing project.

## How to apply the method

1. **Ship question:** the third question in the playbook asks whether someone
   changed an equation, coefficient or tolerance without logging it. The desired
   answer is **no**. Shipping requires an approved spec, satisfactory comparison
   evidence, no unlogged change, and all applicable numeric and review gates.
2. **Evidence before status:** an overlapping plot is useful visual evidence;
   passing requires the declared numeric metric and approved tolerance too.
   Missing evidence is unassessed. The architect's shorthand “no evidence means
   L0” must not be reported as an actual L0 pass.
3. **Proposed numbers:** the starter L1 example of 0.1%, approximate benchmark
   ranges and suggested reference cases are candidates. Verify original sources,
   applicability and licensing before using their data. Obtain scientist
   approval of feature-specific tolerances and do not silently replace existing
   approved thresholds.
4. **Applicable checks:** document the reason for any ladder check that does not
   apply, such as mesh GCI for a model without a spatial mesh. The scientist must
   approve a meaningful substitute or an explicit exception before the feature
   can satisfy its physics acceptance gate. Do not fabricate convergence data.
5. **Validation claims:** L0–L4 is the kit's minimum feature ship gate. L5 compares
   codes; L6 compares measurements. Agreement between two codes alone does not
   establish experimental validation. Describe precisely which checks passed,
   on which case and range, with which uncertainty and reviewer.
6. **Real approval:** preserve the blank scientist/lead approval fields in the
   starter documents. The user's adoption request authorizes this working
   method; it does not approve particular physics specs or results. Requests
   for scientist review should contain the concrete spec and concise questions.
7. **Commands and schedules:** example prompts and the weekly rhythm are
   instructions for using the method when requested. Importing the kit does not
   invoke `/kickoff`, start new domains, contact a scientist or schedule tasks.
   Claude command definitions remain usable in Claude; Codex follows the same
   documents through `AGENTS.md` and its available tools.

## Relationship to existing project records

The current repository is the drone project. The additional domain headings
are empty starter sections, not evidence that those solvers exist. Existing
[ADRs](../decisions/), [validation records](../validation/),
[review records](../reviews/) and [QA receipts](../qa/) remain authoritative for
their recorded scope.

`ROADMAP.md` is the kit's ladder tracker. The
[22 October drone kickoff](../../reports/drone-kickoff-2026-10-22.md) has now
populated it with scoped evidence, linked specs and remaining qualification work.
The active slice table in [`plan.md`](../../plan.md) remains the detailed
implementation/release status record. Neither record promotes physics acceptance
without the required evidence and approvals.

`DECISIONS.md` entry 001 is a supplied placeholder and remains untouched. The
appended adoption entry records the user's workflow decision separately from
scientist sign-off. Link existing ADRs when logging future model changes, so
their history remains traceable.
