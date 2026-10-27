# AI Foundation Implementation Plan

> **For agentic workers:** Use executing-plans inline, following the repository's
> one-implementer rule. The owner already approved foundation and MCP first.

**Goal:** Operate a complete saved design-to-study workflow through shared domain
actions and a real model-neutral MCP server.

**Architecture:** Typed actions share a policy gateway and existing domain
services. An independent metadata migration records scoped grants, proposals,
trusted approvals and invocation receipts. The stdio MCP process accesses only
the authenticated action API. The workbench provides connection, review and
history controls and reuses the same handlers for the migrated operations.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLite/PostgreSQL adapters, official
Python MCP SDK, existing native JavaScript and disposable Chrome checks.

**Spec:** ../specs/2026-10-26-ai-native-foundation-design.md (first stage only).

## Global constraints

- No provider calls/key or code runner in this first stage. No publication or
  deployment. Preserve all branches, original shared service and physical models.
- Default grants: reads/proposals; one project; one-hour default, 24-hour maximum.
- Human confirmation is outside the MCP tools and requires a trusted session,
  exact origin and receipt binding. Grants cannot confirm themselves.
- Proposal application/undo and receipts commit together; conflicts preserve
  inputs. Every request rechecks identity/project authority and expiry.
- Maximum 25 bulk entities and 256 KiB inline response; full JSON exports are
  permission-bound downloads. Advertise only implemented capabilities.
- Full owner interface-law review, real client/API/browser evidence and honest
  local/hosted limitations are acceptance requirements.

### Task 1: Typed action registry and durable authorization

Files: create `src/physimesh/agent/{contracts,registry,store,policy}.py`, tests in
`tests/agent/test_foundation.py`; initialize the service in `api/app.py`.

Interfaces: registry descriptors expose input/output schemas and effects;
`AgentService.context(request)` distinguishes trusted user sessions and grants;
`Store` uses the application's `MetadataDB` and its transactional connections.

- [x] Test public-mode refusal, grant expiry/rotation, cross-project access,
  audience restriction and a viewer read versus forbidden write. Representative:
  `assert client.post('/api/drone/agent/grants', headers=grant).status_code == 403`.
- [x] Implement a version-checked independent schema, bounded grants, actor
  binding and action-specific permissions. Parent hosted sessions remain active.
- [x] Run the targeted test file and retain the command result through workflow.

### Task 2: Reviewed proposals and exact domain operations

Files: `agent/{service,operations}.py`, `projects/sqlite.py`, `projects/service.py`,
`projects/repository.py`, `api/projects.py`, targeted agent tests.

Interfaces: `AgentService.call(context, action, call)` validates typed arguments
and returns a versioned envelope; `prepare` stores an approval candidate;
`confirm` accepts only a trusted session; `call` consumes the approved record.

- [x] Test an explicit duration edit, fake approval refusal, stale application,
  duplicate retry, concurrent application, undo conflict and restart receipts.
  Example: `assert first['receipt_id'] == retried['receipt_id']` and draft version
  advances exactly once.
- [x] Implement units/field allowlists and transactionally save draft plus
  approval/invocation receipt through a shared project repository operation.
- [x] Implement read/inspection/revision/study/job/comparison/export actions using
  existing source and result validation. Interrupted nontransactional operations
  remain uncertain; existing deterministic study/job identities support safe
  explicit reconciliation without automatic replay.
- [x] Route existing inspection/freeze/study/compare handlers through shared
  operations, preserving wire contracts and hosted/local behavior.
- [x] Verify original project/study/job and new domain action regressions.

### Task 3: Authenticated API and MCP server

Files: `agent/api.py`, `agent/mcp.py`, `agent/__init__.py`, `api/app.py`, optional
dependency/lock files, `tests/agent/test_mcp.py`.

Interfaces: `/api/drone/agent` supplies catalog, calls, resources and bounded
records; trusted-only grant/prepare/confirm/revoke routes are separate. CLI
`python -m physimesh.agent.mcp` reads an explicit API URL and protected grant
credential and speaks stdio MCP using the official SDK.

- [x] Resolve/pin the SDK and its optional lock without changing base startup.
- [x] Test real SDK discovery, tools, resources and prompt calls over stdio.
  Assert an edit has no effect before trusted confirmation; exercise a completed
  saved-design/study/export flow and supported legacy/current client protocols.
- [x] Implement SDK adapter and bounded HTTPS/loopback API client, disallow
  redirects, nonloopback HTTP, secrets in tool inputs and raw filesystem reads.
- [x] Check optional package assets and no-SDK base runtime.

### Task 4: Workbench client connection and review

Files: `web/js/agent-workspace.js`, `web/workbench.html`, `web/css/workbench.css`,
`web/js/workbench.js`, `tests/web/test_agent_workspace.mjs` and browser fixture.

Interfaces: native panel receives `api`, current context/read/write callbacks;
it lists capabilities, creates/revokes one-project grants, shows pending exact
diff/action approvals and invocation history. Plain connection configuration is
exportable without embedding the credential. Secret shown once in a password
field, cleared on scope/logout changes.

- [x] Test late-response/context/detached-action guards and text-only rendering.
- [x] Implement native controls in the existing workbench visual language.
- [x] Real browser: create/revoke connection, propose/confirm/apply/undo, preserve
  unsaved input and cross-project context, inspect history and empty/error states.
- [x] Inspect desktop, phone and enlarged-text captures; recheck every design-law
  point and fix faults. Record exact limits rather than claiming native zoom or
  screen-reader qualification from a headless screenshot.

### Task 5: Integration, evidence and handoff

Files: `docs/technical/ai-foundation.md`, QA evidence/interface ledger, optional
MCP setup examples and `.physicore/ops` state/task/approval records.

- [x] Run focused agent/API/MCP and existing affected regressions. Add real
  PostgreSQL checks if a disposable service can be provisioned; otherwise report
  that provider qualification as unverified and keep the adapter checks honest.
- [x] Build a wheel; verify modules/web assets/optional dependency metadata and
  base-runtime import behavior. Check whitespace and credential exclusion.
- [x] Persist workflow proof/completion only for demonstrated scope, update the
  capability inventory with actual availability and leave future adapters clear.
- [x] Commit locally on `codex/ai-native-foundation`; publication is not approved.

Execution decision: inline in the managed isolated worktree, following the
existing one-agent policy. No additional process-choice confirmation is needed.
