# Dependency invalidation proposal

`dependency_invalidation_plan(graph, targets, changed_outputs)` is a pure,
nonexecuting helper. It calls the existing `dependency_plan` first and preserves
its authoritative graph validation, selected target ancestor ordering, and refusal
status/reasons. On planner refusal, affected and unaffected lists are empty.
The whole graph must pass structural and interface validation, even outside the
selected ancestors. Current selected cycles are unsupported; an unselected cycle
retains the planner's existing semantics. No cycle strategy or coupling is added.

Changes are manual declarations, not detected changes. `changed_outputs` must be
an exact built-in list of 0–128 exact built-in dictionaries, each with exactly
`model` and `port` string keys and exact built-in string values naming a known
model output. Unknown outputs, duplicates, extra or missing keys, and invalid
types produce `MODEL_INAPPLICABLE` / `INVALID_CHANGED_OUTPUTS`. Empty changes are
valid. The returned declarations are fresh copies sorted by model and port.

Declaring any output change affects its entire seed model and every downstream
model through any output edge. This deliberately conservative model granularity
reflects unknown dependencies within a model: even an unused changed output
propagates through that model's other outputs. Iterative traversal visits each
model once within the planner's 128-model and 4096-connection bounds. Reports
include only models in the selected ancestor plan, in its deterministic order.
Known seeds outside that plan are valid and have no selected upstream effect.
To select all models, explicitly target an output of every model; target semantics
remain those of the existing planner.

Success has status `INVALIDATION_PLAN_PROPOSED`, canonical planner `targets` and
`order`, and ordered `affected_models` / `unaffected_models`. Affected does not
mean observed stale, and unaffected does not prove freshness. Every result carries
`evidence_level: "unverified"`, `execution_authorized: false`,
`change_detection: "NOT_PERFORMED"`, `artifact_freshness: "NOT_ESTABLISHED"`, and
`physical_validation: "NOT_ESTABLISHED"`.

This helper adds no API endpoint, execution, job, record, external call, or side
effect. It performs no evaluation, hashing, dynamic import, cached value freshness
proof, or physical validation. Source PDF B §5 and §11.3 provide architecture
context for proposed M3 work only; this helper does not establish M3 completion.

An all-models example (the source has no inputs):

```json
{"graph":{"models":[{"id":"Source","inputs":[],"outputs":[{"name":"value","unit":"N","frame":"axis"}]},{"id":"Sink","inputs":[{"name":"value","unit":"N","frame":"axis"}],"outputs":[{"name":"value","unit":"N","frame":"axis"}]}],"connections":[{"from_model":"Source","from_port":"value","to_model":"Sink","to_port":"value"}]},"targets":[{"model":"Source","port":"value"},{"model":"Sink","port":"value"}],"changed_outputs":[{"model":"Source","port":"value"}]}
```

Passing these three fields to the helper yields `order` and `affected_models` of
`["Source", "Sink"]`, empty `unaffected_models`, and canonical `targets` ordered
Sink then Source. It authorizes no execution and establishes no artifact freshness.
