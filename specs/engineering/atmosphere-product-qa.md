# Atmosphere product QA

Integrate `productQA` into the existing collector, `workflow.py` checks, gate runner, evidence store, and task ledger. Codex is primary; no Claude workflow or parallel approval framework is introduced.

## Source-bound manifest

Use schema version 1 with exactly `schema_version`, `sources`, `gates`, `max_repair_attempts`, and `review_required`. Bind repository-relative SHA-256 hashes for all five reviewed product files, the new productQA script and its refusal/receipt unit tests, this specification, and the existing collector and gate implementation. Enumerate actual paths from the reviewed scope; reject missing, unsafe, symlinked, or changed sources. Source changes require refreshed scope and independent review.

Require `review_required: true`, an integer repair budget of 0–2, and 1–20 uniquely named gates. Each gate contains only `id`, an allowlisted `argv` array, and an integer `timeout_seconds` of 1–600. Commands execute without shell composition.

Include these gates:

- `node --experimental-default-type=module --test tests/web/test_atmosphere_preview.mjs`
- `python -m ruff check scripts/qa/atmosphere_browser.py`

## Ledger and execution

ATMOS-001 remains active for the numerical/API scope, unchanged by this work.
Use distinct productQA task ATMOS-UI-QA-001, cross-referencing ATMOS-001,
for this new QA increment. All TASK_ID placeholders below mean
ATMOS-UI-QA-001, never ATMOS-001. Do not automatically reserve an attempt, reopen completed work, or claim readiness. The existing budget bound of 2 may already be consumed. Run the initial manifest only after explicit new scope/start authorization.

The existing runner accepts `--manifest`, `--task`, and optional `--repair-attempt` (default 0). It requires an existing `in_progress` task with `started_at`, then durably reserves the attempt through `workflow.py reserve-gate-attempt`. Refused, replayed, exhausted, or mismatched reservations block execution.

Route each gate through `workflow.py check --timeout <seconds> --gate-start <started_at> --gate-attempt <attempt> <task> -- <argv>`. Retain fresh collector receipt references and verify task, command, repository, start binding, and integer return code. Stop at the first failure, invalid receipt, timeout, or source change.

A successful manifest remains `blocked`, sets `ready_for_review: true`, keeps `completion_allowed: false`, and exits 2. Failed gates exit 1; invalid or blocked execution exits 2. Retained evidence grants no approval or completion authority. Independent review is never self-issued.

## Browser productQA

Use the existing `agent_fixture` in `local` or `hosted` mode against a caller-created disposable loopback fixture. The caller owns startup, shutdown, and disposable data cleanup.

Require `PHYSIMESH_BROWSER_DISPOSABLE=1` and browser arguments `--base`, `--mode local|hosted`, and `--evidence`. The base must be an HTTP(S) loopback origin without credentials, query, fragment, non-root path, or port 0.

- Local mode requires `--token` or `PHYSIMESH_API_TOKEN`; it creates a fresh example and rejects `--project`.
- Hosted mode requires `--project` and `PHYSIMESH_BROWSER_FIXTURE_PASSWORD`.

Route the browser command through the existing `workflow.py check` under the active ledger task; retain its collector receipt alongside browser `receipt.json` and screenshots. Supply the dynamic base and hosted password at runtime; never commit them.

Local coverage includes preview non-mutation, stale-response invalidation, mobile rendering, unsaved-only apply, disabled freeze/calculation before save, preserved retained studies/revisions, and explicit save/freeze. Hosted coverage verifies synthetic viewer login and disabled editing controls. Browser success exits 0; journey failure exits 1.

## Acceptance boundary

A software UI pass demonstrates only the exercised disposable-fixture behavior. Reference-atmosphere scientific acceptance and aircraft physical validation require separate evidence and review.

Last inspected broad CI remains blocked by 44 Ruff errors in unchanged files. Targeted passes do not clear that blocker or authorize a ready, approved, or complete claim.
## Concrete checks

Source-bound proposal: `specs/engineering/atmosphere-product-qa.json`.
Run with the project-pinned Python and dependencies. Put that environment's bin directory first on PATH before starting the existing collector: its
allowlisted `python` child command resolves through PATH, not automatically
through the parent interpreter. Python Playwright and Chromium
must already be available for browser checks; the script does not install them.

```
python scripts/qa/workflow_gates.py --manifest specs/engineering/atmosphere-product-qa.json --task TASK_ID
```

Do not run that command against a consumed reservation or silently reset the
ledger. The manifest covers unit/refusal tests and lint, not an automatic browser
or physical-acceptance grant. The dynamic fixture browser checks are retained
separately through the same existing collector:

```
PHYSIMESH_BROWSER_DISPOSABLE=1 python .physicore/tools/workflow.py check --timeout 120 TASK_ID -- python scripts/qa/atmosphere_browser.py --base LOOPBACK_ORIGIN --mode local --token SYNTHETIC_TOKEN --evidence .backend/atmosphere-local
PHYSIMESH_BROWSER_DISPOSABLE=1 python .physicore/tools/workflow.py check --timeout 120 TASK_ID -- python scripts/qa/atmosphere_browser.py --base LOOPBACK_ORIGIN --mode hosted --project SYNTHETIC_PROJECT_ID --evidence .backend/atmosphere-viewer
```

The hosted invocation also needs the caller-provided synthetic fixture password
in `PHYSIMESH_BROWSER_FIXTURE_PASSWORD`. Local mode always creates its own fresh
realistic example and refuses `--project`; hosted mode waits for the exact
requested project option, not a placeholder option. Interruption returns 130 and
records failed status, including interruption after successful checks during
cleanup. Refusal/receipt tests do not require a browser installation.
