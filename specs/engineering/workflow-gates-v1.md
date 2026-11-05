# Gate execution v1, review draft

Extend the current workflow, not its task lifecycle. A manifest version1 names
source hashes, ordered verification commands,1–600second budgets and a repair
attempt limit0–2. Commands run via existing workflow.py check. Each referenced
receipt is retained in the existing evidence folder. Checks pass, fail or block;
missing/stale source, receipt mismatch or infrastructure refusal is blocked.
Numerical/test failures and declared timeouts fail. A passed check sequence stays
blocked for independent review. No self-issued review approval, proof, completion,
repair, code generation, external model call, commit or deployment exists here.

Gate attempts now reserve durably in the existing task's gate_attempts field,
bound to started_at and first fixed budget. A lock serializes competing gate
reservations; atomic write happens before execution, so crashes spend attempts.
Replayed/skipped attempts, manifest budget changes and task-start changes block.
All CLI workflow operations now share that lock across queue read/use/write.
Contention waits at most15seconds then refuses without changing state. A lock
file left by a crashed process is harmless: OS file locks release on process exit.
The lock serializes local CLI commands only; direct edits or external writers that
ignore the protocol remain outside this guarantee. Checks hold the lock while
running; concurrent commands can refuse busy rather than reset the budget.
Manifest commands are executable local verification code, not safe untrusted data.
They require the same reviewed task scope as commands passed to workflow.py.

Acceptance before landing: manifests validated strictly; source changes/missing
paths refused; successes retained without completion; failed gate stops sequence;
inner and outer timeouts distinguished; receipt identity checked; manual repair
budget cannot silently reset within a run; actual existing ledger invocation
exercised. Actual existing-collector subprocess tests now cover successful check/review block,
exit7 failure and declared1second timeout. Receipt acceptance binds taskID, argv,
activeledger started_at and repository; every preexisting evidencefile path is
snapshotted, including nonstandard names/nested files. Existing receipts cannot
be replayed as fresh. Independent review remains required. Persistent budget reservation now has restart/replay, concurrent same-attempt
and budget/start-reset tests. Shared locking tests cover concurrent refresh/block and crashed lockholder.


## Lock budgets, restart and task revalidation

Reservation outer timeout30seconds exceeds the workflow's15second lock budget.
Check outer timeout includes declaredcommandtimeout plus30seconds, leaving lock
contention and receipt overhead separate. Locks held during long checks cause
other CLI operations to refusebusy after15seconds. This is deliberate isolation,
not background command cancellation or a scheduler.

Reserved checks carry optional --gate-start and --gate-attempt arguments. Under
the sharedlock, existing active-task enforcement plus these bindings refuse a
blocked/completed/restarted task or superseded reservation before commandlaunch.
Ordinary check commands without gate options retain prior behavior.

Exhaustion is retained even if taskstarted_at changes. start/reopen never erases
gate_attempts. Do not edit counters, reset budget through a changed manifest or
silently reuse the taskID. New work after exhaustion requires a separately scoped,
reviewed new task in the existing ledger with source evidence and explicit
crossreference to the exhausted task/receipts. A reset operation is intentionally
not implemented. Preserving history beats recovering an attempt lost to a crash.
