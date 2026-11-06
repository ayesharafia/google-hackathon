---
name: physicore-reviewed-github-update
description: Prepare a scoped PhysiCore GitHub pull request and evaluate repository CI coverage before a permitted merge. Use for release evidence, not scientific certification or deployment authorization.
---

# Reviewed GitHub update

Read `AGENTS.md`, `.physicore/ops/APPROVALS.md`, the affected specification and the current owner-approved scope. Repository records describe project conventions; they do not themselves establish new owner permission. This skill grants no push, merge, deployment, spending or branch-deletion permission.

## Prepare a scoped change

- Inspect Git status, branch, base revision and the proposed cumulative diff. Preserve unrelated work and branches. The PR should explain its engineering purpose and identify the changed behavior.
- Run applicable tests and lint from the package root using the declared runtime and dependencies. Record exact commands, observed results, omissions and unavailable backends. Preserve references, tolerances and scientific evidence.
- Use the existing project evidence workflow and scientific review policy. A software change that affects equations needs the scientific model record and appropriate review, not merely a code diff.

## Review CI coverage

Inspect the current `.github/workflows/ci.yml` for the proposed revision. Map each relevant job to what it checks: root lint, unit tests, reference implementation, service and package smoke tests, browser journeys and backend-specific checks where present. Report failed, pending and skipped jobs distinctly.

A manually dispatched backend job skipped on a normal PR did not execute. A retained fixture is not new solver output. Passing platform CI demonstrates the checked software behavior, not aircraft feasibility or physical validation. The project's supported runtime and locked CI runtime must be distinguished from other local environments.

## Publish only within permission

Use a normal reviewed branch and pull request when publication is authorized. Confirm the actual outgoing diff and intended repository/branch. Do not overwrite unrelated changes, force-push, delete retained branches, bypass protections or suppress checks. Changing the code requires new evidence for the affected scope.

Before a permitted merge, identify the exact current head/base and completed relevant checks, disclose omissions and preserve review evidence. After merging, verify the resulting main revision and its applicable CI status. Report observed commit/PR/workflow links and any pending verification. A merge is not deployment or a scientific acceptance decision.
