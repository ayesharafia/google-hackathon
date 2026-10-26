# Job Activity & Recovery

In an authenticated **hosted-mode** project, use the sidebar's **Jobs** list.
Choose a job to inspect it without waiting for completion. The workbench moves
focus to its job detail sheet. This flow is unavailable in local/public mode,
whose existing synchronous execution path is unchanged.

## Inspect and refresh

Rows show job type, recorded state, short job ID and attempts started. The
selected sheet includes the full project/job identity, recorded timestamps in
UTC, failure reason, current attempt limit and ordered attempt history. A
missing finish time stays **Not recorded**. Zero progress and epoch timestamps
are preserved. **Exact job record** exposes the returned JSON.

**Refresh selected job** requests its current record. **Refresh job history**
replaces the current list page; **Load older jobs** follows the server cursor.
Refreshing/paging history keeps the selected detail usable. Its last-checked
timestamp describes the detail fetch, not the list fetch. There is no new
automatic polling, progress animation or estimate of remaining time. Progress
percentages express each attempt's reported fraction, not physical validity.

Inspecting and refreshing do not submit or retry work or replace draft inputs.
The existing detail endpoint can repair publication of an already accepted
result; this server behavior is retained. Inspection is not a promise that a
GET is free of that existing materialization step.

## Explicit recovery

An engineer can **Cancel selected job** while the recorded state is queued or
running. **Retry selected job** is offered for failed/cancelled jobs below the
existing server's five-started-attempt manual retry limit. The displayed current
attempt limit is the retained `max_attempts`, not a new policy or a count of
additional retries. The server remains authoritative and can refuse a stale,
unauthorized or overloaded request. Retry may run computation again.

Recovery is never automatic. While its request is pending, duplicate recovery
and job reselection are disabled in the inspector. An ambiguous/failed response
clears action authority until the job is explicitly refreshed. A viewer can
inspect and refresh; viewing grants no cancellation or retry permission.

Succeeded study/report jobs offer **Open associated retained study** only when
the returned receipt supplies the applicable binding. Navigation uses existing
project-authorized study loading and keeps unsaved draft text. It does not
automatically download a report or re-run an analysis. Missing/malformed binding
evidence provides no study link.

Job/project/logout changes invalidate prior detail, delayed responses and detached
actions. Signing out does not cancel admitted server work. A short ID helps
identify a list entry; it is not a credential or an authorization check.

Implementation: `web/js/job-activity.js`, integrated into the existing workbench.
No new API, dependency, queue/worker rule, access policy, scientific model or
tolerance. [Executed evidence and limits](../qa/job-activity-2026-10-26.md).
