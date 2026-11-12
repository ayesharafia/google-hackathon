# Bounded experimental model graph execution

`physimesh.drone.model_graph_execution.evaluate_model_graph` executes a finite,
serial DAG using exactly three code-owned semantic adapters:
`standard_atmosphere`, `isolated_hover_bemt_experimental`, and
`fixed_wing_aerodynamic_screening`. This is a substantive bounded execution
slice toward PDF B M3, not M3 completion or scientific approval.

The exact request is:

```json
{
  "evaluation": "bounded_model_graph_experimental",
  "nodes": [
    {"id": "air", "model": "standard_atmosphere",
     "inputs": {"altitude_m": 1000, "altitude_kind": "geometric"}}
  ],
  "connections": [],
  "targets": [{"node": "air", "port": "density_kg_m3"}]
}
```

Each node's `inputs` has exactly the existing adapter request fields, with
connected numeric fields omitted. Atmosphere requires altitude and its explicit
convention. Hover and fixed-wing retain their existing `evaluation` literals;
fixed-wing also retains `configuration`. An edge has exactly `from_node`,
`from_port`, `to_node`, `to_port`. No caller units, frames, model definitions,
callbacks or import paths are admitted. `adapter_metadata()` returns fresh
code-owned scalar port metadata. Units describe existing quantities, not a
physical applicability check. All exposed ports are scalar quantities without
a spatial frame. Vector diagnostics are retained in hover stage results but
cannot be bound or targeted. Integer annuli can be targeted but cannot transfer
to floating point or count inputs.

For a density branch, omit `density_kg_m3` from a complete hover or fixed-wing
request and connect `air.density_kg_m3` to that field. Both can consume the same
atmosphere output. Multiple independent atmosphere nodes and arbitrary admitted
scalar topology are supported. Shape and geometry fields, counts, property and
applicability declarations, and coefficient envelopes remain literal. Hover
thrust has no compatible force input in this registry, so cannot be connected.
There is no unit conversion, vector/frame transformation, mesh interpolation,
or inferred environmental property.

All nodes, connections and targets are validated before any component call.
Every required field must appear exactly once, as a literal or admissible edge,
even on unselected nodes. This deliberately strict policy catches incomplete
requests independently of selection. Cycles are rejected globally, including
unused cycles. Literal physical-domain decisions remain with the existing
adapters; preflight checks finite numeric types, literal structure, integer
counts and bounded resource use, not physical validity. A valid disconnected
unselected node does not execute. Only target ancestors execute, using
lexicographic Kahn order. Target selection exports only the requested ports.

Limits are 1–16 nodes, at most 64 connections, and 1–32 unique scalar targets.
Identifiers are an ASCII letter followed by ASCII letters, digits or underscores,
up to 64 characters. Requests must be finite builtin JSON with depth at most 10
(root depth one), at most 4096 visited values and keys, strings at most 2000
characters, and containers at most 256 entries. Integers are bounded before
float conversion. Each hover has a literal integer annuli count of 1–2048;
the aggregate across all nodes, including unselected nodes, cannot exceed 8192.
Result payloads have separate bounds of 20000 values/keys and 2048 entries per
container, allowing existing hover diagnostic vectors.

Components receive copied assembled inputs. Atmosphere requires the exact
existing dataclass type, model/evidence identifiers and altitude consistency;
its units are code-owned. Hover reuses the existing workflow's strict private
response validator, which checks its exact response envelope, units, finite
scalars, vector lengths and integer annuli. The graph additionally requires the
successful experimental status. Fixed-wing has its own strict successful schema,
model, status, units, declarations and scalar checks. Any refusal, exception or
malformed response returns `EXECUTION_FAILED`, with sanitized reasons, empty
final `outputs` and `output_units`. Completed stages may remain as explicitly
incomplete diagnostics (`diagnostics_complete: false`); they do not imply a
successful graph. Structural rejection returns `GRAPH_INVALID` with no stages.

Successful runs return `COMPUTED_EXPERIMENTAL`, stage order, copied stage inputs
and full results, and SHA-256 hashes of admitted request data, assembled inputs
and results. Transfer records identify the actual producer node, port, result
hash, value and scalar SI unit. Hashes identify data, not executable identity,
freshness or qualification. Request array order is preserved in the request
hash even though node permutation leaves execution order and numerical outputs
deterministic. Returned snapshots do not alias caller inputs or retained adapter
results. There is no automatic cache, parallel execution, persistence, run CLI,
UI/API integration or revision/freshness guarantee.

All run responses remain `unverified`; physical validation, numerical
qualification and runtime identity are `NOT_ESTABLISHED`. Aircraft status and
feasibility remain null. The atmosphere remains a dry reference atmosphere,
not local weather. Hover remains experimental isolated-hover, small-angle,
attached linear lift without loss factors, swirl, stall, Reynolds polars,
compressibility, ground effects or aircraft interference. Fixed-wing retains
unverified supplied coefficients and declared envelopes, with no stall, trim,
structural or installed-aircraft validation. Shaft power is not electrical
power; aerodynamic drag power is not shaft power. No aircraft force closure or
physical operating envelope is inferred.

Focused tests compare branched graph outputs with separately called component
kernels, check selected execution and deterministic ordering, and exercise
structural, resource, response and mutation boundaries. These checks establish
composition behavior only; they are not independent physical validation or
numerical qualification of the existing kernels. Independent review remains
outstanding.
