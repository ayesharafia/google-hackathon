# Dependency batch proposal (candidate, unaccepted pending review)

`dependency_batch_plan(graph, targets, changed_outputs)` proposes dependency
layers for affected selected models. It calls the accepted
`dependency_invalidation_plan` first and deep-copies its entire result. All base
fields and refusal status/reasons are preserved; refusals return `batches: []`
and `external_prerequisites: []`. Only `INVALIDATION_PLAN_PROPOSED` becomes
`BATCH_PLAN_PROPOSED`. Every result carries `readiness: "NOT_ESTABLISHED"`,
`prerequisites: "NOT_VERIFIED"`, and `execution_authorized: false`.

Success uses Kahn layers over the affected selected subgraph only. Each affected
model appears exactly once, after its affected predecessors. Each batch is sorted
lexicographically. Multiple port connections between the same models count as
one dependency; exact duplicate connections remain invalid under the accepted
planner. Graph, target, port, and change ordering do not change the result.
Empty changes are valid and yield empty batches and external prerequisites.
Unchanged ancestors are not included in batches.

`external_prerequisites` lists actual direct edges from unaffected models into
affected selected models, deduplicated at model granularity and sorted by source
then destination. Each record has `source_model`, `destination_model`, and
`unverified: true`. These are assumed external, unverified prerequisites; neither
availability nor validity is assumed. Edges into unaffected models are omitted.
For the diamond A → B, A → C, B → D, C → D, targeting D:

| Changed output's model | Batches | External prerequisite edges |
| --- | --- | --- |
| A | `[ ["A"], ["B", "C"], ["D"] ]` | none |
| B | `[ ["B"], ["D"] ]` | A → B, C → D |
| D | `[ ["D"] ]` | B → D, C → D |
| none | `[]` | none |

Manual output declarations conservatively propagate through whole models and
all their descendants, then intersect the selected ancestor plan. There is no
port-level dependency inference. Validation, exact built-in type restrictions,
128-model/4096-connection bounds, target selection, and selected-cycle refusal
are inherited without a separate planner or coupling strategy. Unselected cycles
retain existing planner semantics.

This is a proposal only. Models in a batch are independent only by declared
dependency; this does not authorize actual parallel runs or guarantee parallel
safety or optimal scheduling. The helper executes no models, creates no files,
makes no network calls, and persists no records at runtime. It establishes no
execution readiness, resource permission, artifact freshness, or physical
validation. Manual changes are not detected. Model state and version changes are
not handled. Neither unaffected status nor a batch plan proves freshness.

Source PDF B §5 and §11.3 are architecture context for this focused M3 proposal
only. This candidate does not establish M3 completion and remains unaccepted
until review.
