# Software engineering loop inside Drone-Project

Scope: software implementation and evidence, not choosing a final aircraft.
Use the existing `.physicore/tools/workflow.py` task ledger and proof collector.
Do not import a second starter or treat a reviewer's agreement as physics proof.

1. Read existing `next` task and source spec; one active writer. Capture exact
   base commit and dirty state. Stop on unowned concurrent changes.
2. Research only the task's unresolved scientific/software inputs. Record exact
   sources and applicability, not a generic web corpus. Example: atmosphere
   layers, SI altitude conventions, table rounding and domain limits.
3. Implement the smallest bounded change plus refusal/regression tests. No
   implicit model escalation, unsupported configuration or changed grant.
4. Execute checks through existing `workflow.py check TASK -- ...`, on Python and
   dependencies pinned by the project. Retain failures as well as passes.
5. Separate reviewer reads exact diff and relevant contracts, not just a summary.
   Check model validity, input scope, units, auth, provenance and failure paths.
6. Repair reproducible findings only, then rerun the affected check and baseline.
   Limit repair rounds (initially two). New unrelated work becomes a new task.
7. Use existing proof/complete only when all task-specific gates are met. A
   partial-source test is not full CI; software-ready is not aircraft-validated.
8. Re-read current remote base before commit. Never overwrite concurrent work.
   Monitor the resulting CI and inspect failures before calling it landed.

Use `python scripts/qa/atmosphere_loop.py --task ATMOS-001` after a source-backed
task is started. It runs only checks, records receipts in the existing collector
and stops on failure. It does not auto-repair or complete a task.

Current execution: local implementer produced atmosphere module/router, actual
legacy snapshot-readiness tests and import repairs. Separate private reviewer is
in progress.21tests+17subtests pass on exact CI Python3.11.16 and hash-verified locked dependencies.
Real create_app local/hosted authentication tests now pass with real SQLite identity.
A broader drone/projects/platform/API run passes475tests (3deselected),17subtests.
Binary solver fixtures remain unrecovered; no full CI/backend claim follows.
No model API or external coding session is required for numerical execution.

Stop conditions: exhausted round budget, missing source/authority, unresolved
review finding, failed baseline, changed source hashes or no adequate physical
model. Preserve the failure and ask for only the decision actually needed.
