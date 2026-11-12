# Dependency revision proposals

`dependency_revision_plan(graph, targets, before_revisions, after_revisions)`
produces a bounded proposal from caller-supplied opaque labels. Each revision
map must be an exact built-in `dict` containing every graph model ID, including
disconnected models and models with no outputs. Missing or extra IDs are refused.
Keys and values must be exact built-in strings; subclasses are refused. Values
must contain 1–80 characters and at least one non-whitespace character.

Labels are compared by exact string equality. Case and surrounding whitespace
matter; labels are not parsed as semantic versions or ordered by magnitude.
Changed model IDs appear sorted in `declared_changed_models`. Every output of
every changed model expands into a changed endpoint, including unused outputs
and outputs outside the selected target closure. A changed model with no outputs
is declared changed but contributes no endpoints. Downstream effects and batches
are inherited from dependency batch planning for the selected targets.

The expansion limit is exactly 128 output endpoints across all changed models.
128 is accepted; 129 is refused with `MODEL_INAPPLICABLE` and
`REVISION_EXPANSION_LIMIT`. The refusal contains no partial batches, affected or
unaffected models, changed outputs, or external prerequisites. It retains the
changed model declarations and completed label-comparison state. The bound is
not loosened by selecting fewer targets or by disconnected outputs.

Graph and target validation, unit and frame compatibility, and selected cycle
refusals happen before label validation or comparison. Their inherited status
and reasons are preserved. Invalid revision maps produce `MODEL_INAPPLICABLE`
with `INVALID_REVISION_LABELS` and `label_comparison: NOT_PERFORMED`.
Successful comparison sets `label_comparison: CALLER_LABELS_COMPARED`; successful
proposals use `REVISION_PLAN_PROPOSED`. Label values are never returned.

This helper does not execute models, operate a cache, detect implementation
changes automatically, or establish artifact freshness. It does not establish
physical validation or complete M3. Returned states remain
`implementation_change_detection: NOT_PERFORMED`,
`change_detection: NOT_PERFORMED`, `artifact_freshness: NOT_ESTABLISHED`,
`physical_validation: NOT_ESTABLISHED`, `evidence_level: unverified`, and
`execution_authorized: false`. Equal labels cannot prove unchanged code or fresh
artifacts; different labels are caller declarations rather than verified changes.

Input maps, graph, and targets are not mutated. Returned nested structures are
independent of caller inputs and subsequent results. Permuting model, connection,
output, target, or label-map insertion order does not change the proposal.
