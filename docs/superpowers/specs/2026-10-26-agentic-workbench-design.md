# Agentic workbench: project control and app development

Status: PROPOSED for owner review, 26 October 2026. No AI implementation or
provider activation is approved by this document. Baseline: main commit
`5de743c9fd682fd799b4d7abbdfd13b8e858aa11`.

## Owner intent and first release

The owner wants natural-language control inside PhysiCore. When asked which
changes it should support, the owner explicitly selected **both project designs
and the app's own features/code**. The proposed release delivers two bounded
workflows through one assistant entry point:

1. Project assistant: inspect the selected saved design and retained evidence,
   explain recorded blockers, propose explicit input edits, and save the exact
   reviewed proposal after confirmation.
2. App developer: accept an owner-authorized feature request, prepare frontend
   code changes on an isolated review branch, and present the patch and recorded
   checks. Updating main or the running application is a separate release action.

Example project request: "Set the existing battery mass item to 3 kg and the
mission duration to 8 minutes." The assistant identifies the existing item,
converts the explicit duration to 480 seconds, displays each original and
proposed value, and asks for confirmation before saving. These are user-supplied
example values, not measurements or recommended aircraft parameters.

Example app request: "Add a title filter to the project selector." The developer
reads the allowed source, proposes an implementation, writes an isolated branch,
runs permitted checks, and returns a diff with its limitations. The current app
does not silently update itself.

## Observed foundations and unknowns

- The app is FastAPI/Python with native browser JavaScript. No model provider,
  agent runtime, or AI UI exists in the inspected source/dependencies.
- `ProjectService.save` retains canonical snapshots and verifies geometry.
  `SQLiteProjects.save` rejects a stale expected draft version. Hosted access
  already checks project membership and write permission.
- Existing inspection, frozen revisions, retained studies, source provenance,
  and job status can supply evidence. Passing software checks does not establish
  physical validity or human engineering approval.
- The current shared local token has one shared workspace permission. It cannot
  establish that a visitor is the owner. It must not authorize code development.
- Docker responded with server version 29.5.2 during read-only capability
  discovery. This does not establish that a restricted runner is implemented or
  qualified. The existing application image lacks the full proposed code-check
  environment and is not automatically a suitable development sandbox.
- No AI provider configuration names were present in the inspected process
  environment. No credential was read or sent to a model for this design.
- Customer benefit, live-model reliability, provider budget, model choice,
  sandbox isolation and real-aircraft applicability are not yet established.

## Approaches considered

| Approach | Useful outcome | Tradeoff |
| --- | --- | --- |
| One backend orchestrator with typed project tools and a separate development runner, recommended | Actual project edits and code branches through one interface | Requires explicit capability checks, a proposal store and sandbox qualification |
| Read-only chat over project summaries | Fast explanations and onboarding | Cannot perform the requested project or code changes |
| Hosted autonomous development platform | Remote development capacity and durable execution | Adds infrastructure, operational dependencies, data transfer and spending decisions |

Use the existing backend and a small tool registry. Keep project operations and
code operations as separate capability groups. Start with one agent run at a
time rather than introducing recursive agents or unattended company operations.

## Architecture and boundaries

The browser calls an authenticated assistant API. A broker binds every run to
its actor, mode, project or configured repository, base version/commit, provider
and explicit resource limits. A provider adapter supplies structured function
tools. The broker validates every requested operation against its own registry;
the model's explanation does not grant authority.

The project adapter uses existing project services. The development adapter
uses a dedicated worker, a sanitized source export and container checks. The
web-facing API must not receive a Docker socket or unrestricted filesystem/shell
tool. An operator starts the development worker explicitly; a web request cannot
provision itself into a host administrator.

Proposed modules are `physimesh.assistant` for orchestration/contracts/context,
project-scoped assistant routes, a separately started development worker and
browser modules for conversation, proposal review and code review. Use a
versioned persistence migration with SQLite and hosted PostgreSQL parity.
Development requests are operator-scoped; linking one to a project does not
make its source, patch or logs readable by ordinary project members.

## Permissions and model access

- Project runs require existing project write permission in v1. This matches
  the current POST authorization and avoids reclassifying all POSTs as reads.
  Read-only members retain the existing project/evidence views.
- Development requires a separate server-authorized operator capability in
  addition to ordinary access. In local mode, use a distinct operator secret
  to establish an eight-hour HttpOnly operator session. Never reuse the shared
  workspace token or keep this secret in browser storage/chat messages.
- Hosted mode uses an explicit configured operator identity allowlist, checked
  against authenticated server identity. Organization/project roles or model
  output cannot grant this capability. Default is no development operators.
- Operator session creation and state-changing requests need same-origin/CSRF
  protection, expiration, revocation and rate limiting. Recheck membership and
  operator permission when accepting work, dispatching tools and accepting a
  result. Local shared access is not an individual identity audit.
- AI is disabled until a server operator configures the provider, model and
  usage limits. Never substitute a scripted answer and label it live AI.
- Proposed first adapter: OpenAI Responses with explicit strict function
  schemas and server-side semantic validation. Pin its optional SDK dependency
  and locks during implementation; existing non-AI startup must keep working.
- Store the key on the server outside tracked files. Show users the configured
  provider and context being sent. Project context and source code are separate
  disclosure scopes. Upload binaries, other projects, credentials, cookies,
  environment contents and database files are excluded.
- Explicitly set provider response storage off where supported. This does not
  promise zero provider retention; display/link the provider's actual policy.
  Live paid requests and private-data transfer need owner activation and a
  configured budget. Design approval alone does not authorize spending.

## Project assistant workflow

1. Select a project and save or explicitly discard browser edits before starting.
   Never discard inputs automatically. Pin the saved draft version and canonical
   snapshot hash. A selected retained study is separately pinned by identity.
2. Allow reads of that draft, its deterministic inspection, selected retained
   study/summary and referenced source metadata. Each tool independently checks
   the run's project binding and permission; model-supplied IDs cannot expand it.
3. Answer with links to the actual fields and retained records used. Recorded
   numerical outcomes and validation labels come from deterministic evidence
   rendering. Missing measurements stay missing; imported text is untrusted data.
4. For edits, create a server-owned proposal restricted initially to payload
   mass, mission duration, and mass/CG values of uniquely identified existing
   mass items. Require explicit user values and units. Reject ambiguous targets,
   unsupported conversions, unknown fields, nonfinite values and whole-snapshot
   replacement. Adding records, changing source hashes/geometry/model settings,
   or relaxing tolerances is outside this first edit allowlist.
5. Validate the proposed snapshot through existing contracts and geometry/source
   integrity checks. Show each before/after value with units, the bound draft
   version and available deterministic input checks. Distinguish schema-valid
   from scientifically qualified. No solver result is invented for a proposal.
6. The human selects **Apply reviewed changes**. The request identifies the
   stored proposal, not a replacement patch supplied by the browser. Atomically
   recheck permission, expiry, original version/hash and approval identity, then
   use the same canonical/source validation as `ProjectService.save`. Add a
   narrow repository operation that saves the draft and proposal receipt in one
   transaction in both SQLite and PostgreSQL; writing a broker receipt after an
   independent save is insufficient. Repeated requests return that same receipt.
   Proposals expire after 15 minutes and require fresh review after a conflict.
7. Undo creates a new draft after explicit approval, only if the current version
   and hash still match that proposal's saved result. It cannot erase later
   edits, historical revisions, sources or retained studies.

Project switching, logout, editor changes, permission loss and replacement
requests invalidate pending browser actions. Delayed responses cannot overwrite
another project or local edits. Freeze, evaluate, source binding, job recovery
and review decisions remain existing explicit controls in this release.

## App developer workflow

1. Owner enters Development mode and authorizes the requested change. Record the
   configured repository and clean base commit; no arbitrary filesystem path or
   repository URL can be supplied by a visitor.
2. Export tracked, permitted source into a private disposable work area. Do not
   mount the owner's home, original checkout, Git credentials, `.git`, `.backend`,
   `.venv`, provider credentials, Docker socket or production data into checks.
   Enforce normalized paths, resolved containment and rejection of symlinks,
   traversal, submodules and binary writes at every file tool.
3. First release permits changes in authored `web/` assets, related `tests/web/`
   tests and `docs/technical/`. Exclude vendored code, policy/instruction files,
   dependencies, deployment, authentication, physics source and tolerances.
   Requests requiring these areas become a clearly described scope-review item.
4. Model tools are bounded source listing/reading, structured file edits and
   named checks. There is no arbitrary host shell, package installation, network
   fetch, source deletion outside the proposal or credential-reading tool.
5. Run approved checks in a dedicated pinned container: non-root, no network,
   read-only root, restricted capabilities, bounded temporary storage, CPU,
   memory, process count and wall time. Only the disposable source area is
   writable. Treat test code and filenames as potentially hostile. A missing
   suitable image disables execution with a reason; it never falls back to host
   execution. Build/dependency preparation is a separate operator action.
6. Preserve the resulting patch and content hashes, base commit, files changed,
   exact named checks, bounded logs, exit status and limitations. An independent
   deterministic verifier checks paths/bounds before any branch is created.
7. After the owner confirms the exact patch, create a new `codex/` review branch
   through the trusted worker and commit only the verified allowed bytes. Use
   Git object/ref operations without checkout, hooks or content filters so
   untrusted generated code never executes on the host during branch creation.
   Create a fresh ref without overwriting a prior ref. Keep the running
   checkout/main unchanged. Concurrent repository changes cannot
   cause the patch to apply to a different base; conflicts require a new review.
   Existing branches are retained. Test success does not authorize release.

The result is a real local code branch plus reviewable evidence. GitHub push,
merge, deployment and runtime restart are separate explicit owner release steps.
No generated JavaScript is served under the authenticated app's origin as a
preview. Any later interactive preview requires a separate credential-free
origin and a dedicated isolation design.

## Runs, history, limits and recovery

Persist run state, user instruction, sanitized context manifest/hashes, provider
and model identity, user-visible answers, validated tool calls/results, proposals,
decisions and actual token usage when supplied. Do not collect hidden chain of
thought or secrets. Project transcripts follow project permissions; development
transcripts/logs follow operator permissions. They may themselves be private.

Use explicit states: queued, running, awaiting_review, completed, failed,
cancelled and interrupted. Terminal states include an honest reason. New run
dispatch and state transitions require atomic ownership, preventing duplicate
execution. Restart leaves unfinished work interrupted until an explicit user
retry; it cannot replay an edit. Approval and application are idempotent.

Proposed policy bounds, subject to implementation checks: six model responses,
24 tool calls and one proposal per run; one concurrent development run; 256 KiB
of source context; five changed files and 1,000 changed lines per code proposal;
512 KiB per patch; 64 KiB of retained output per named check; 8 KiB per user
message; 120 seconds per named check; ten minutes per development run. Provider request
and token limits are explicit configuration with finite server maxima. No
automatic retries or unbounded follow-up loops. Stop prevents subsequent tools;
an already dispatched provider call can still incur usage. A proposal cannot be
applied after its run was cancelled or interrupted.

## Interface direction

Use a workbench assistant panel that stays beside the actual selected project.
Identify Project or Development mode, selected project/base version and provider
as plain text. Chat answers, current action and reviewable changes have distinct
roles. Show user-visible tool activity and exact evidence without decorative
agent personas, fake progress, guessed ETA, repeated status pills or a mock app.

Project proposals use aligned before/after rows with units and one clear apply
action. Development uses file navigation, a readable diff and check results.
Controls work by keyboard and pointer; pending and permission states are explicit.
Readable content is visible by default. Follow the full owner interface law,
including real desktop/phone/enlarged-text interaction and visual review before
shipping. A design document is not proof of a finished interface review.

## Delivery sequence and acceptance

Deliver in order within the approved architecture:

1. Typed contracts, provider adapter, capability checks and durable run/proposal
   records, with AI disabled by default.
2. Project read/explain/propose/review/apply/undo workflow and browser UI.
3. Separate operator authentication, sanitized development workspace, bounded
   container checks and confirmed review-branch creation.
4. Targeted API/permission/concurrency tests, provider-transport fixtures,
   container escape/resource-bound checks, real browser workflows and the full
   interface-law audit. Package/lock/resource checks cover the added optional
   integration and migration behavior.

Acceptance must demonstrate an actual saved project edit and safe undo; stale,
double-apply, cross-project and permission refusal; malicious uploaded/source
instructions unable to grant tools; provider timeout/invalid output and missing
configuration; run cancellation/restart; and an actual allowed frontend change
on a new local branch with retained checks, while a shared visitor cannot use
development tools. Verify no live checkout, credential, source evidence, physics
formula or prior branch was changed by the development run.

Offline provider fixtures prove application behavior only. A separately authorized
live-model run is needed to claim the configured AI connection works. Successful
code checks never grant engineering approval. No production readiness, unattended
operation or real-aircraft accuracy claim follows from this release.

## Sources consulted

Official documentation accessed 26 October 2026:

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling):
  application tools and strict schemas; server semantic checks remain necessary.
- [OpenAI agent safety guidance](https://developers.openai.com/api/docs/guides/agent-builder-safety):
  isolate untrusted content and explicitly authorize sensitive operations. This
  project proposes its own tool broker, not a dependency on the legacy builder.
- [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data):
  response storage settings do not by themselves promise zero provider retention.

These sources establish available integration patterns, not customer demand,
account eligibility, spending authorization or the correctness of this design.
