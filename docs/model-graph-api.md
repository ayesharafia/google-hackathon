# Experimental model graph API

Authenticated clients can use `GET /api/drone/model-graph/catalog` to discover the
code-owned adapters, their scalar SI ports, literal fields, and resource limits.
`POST /api/drone/model-graph/evaluate` evaluates a bounded directed acyclic graph.
The catalog supplies the required `evaluation` identifier.

The request has exactly four fields: `evaluation`, `nodes`, `connections`, and
`targets`. Each node has `id`, `model`, and `inputs`. Each connection has
`from_node`, `from_port`, `to_node`, and `to_port`; each target has `node` and
`port`. Use the catalog's adapter identifiers and input declarations. Geometry
and declarations remain literal; connections do not perform unit or frame
conversion. All nodes are validated, including unused nodes. Only selected
targets and their ancestors execute, serially.

Successful computations return `COMPUTED_EXPERIMENTAL`, selected `outputs` and
`output_units`, stage records, execution order, and transfer provenance.
Semantic graph refusals return HTTP 200 with `GRAPH_INVALID`, empty outputs,
and no executed stages or transfers. Component execution refusals return
`EXECUTION_FAILED`; selected outputs are withheld.

Malformed JSON, duplicate keys, nonfinite numbers, and invalid HTTP request
structure return HTTP 422 with `{"detail":"Invalid model graph request."}`.
The request body is limited to 128 KiB, including streamed bytes; exceeding the
limit returns HTTP 413. Additional limits cover JSON depth, values, container
size, string length, integer size, graph size, and aggregate hover work. Consult
the catalog for the exact limits.

Use the application's bearer authentication. Local session cookies also support
these endpoints; cookie-authenticated POST requests require a same-origin
`Origin`. Hosted access permits the exact catalog and evaluate paths; suffixes
and trailing slashes are refused.

`request_sha256` identifies the admitted request data, and `input_sha256` aliases
it. `evaluation_sha256` hashes the response record before that field is added.
Stage input/result hashes and transfer producer hashes support reproducibility;
array order remains request data. Hashes and declarations are not validation
evidence.

This stateless experimental interface is not a full M3 model registry. Evidence
is `unverified`; physical validation, numerical qualification, and runtime
identity are `NOT_ESTABLISHED`. Aircraft status and feasibility remain null.

## Experimental reference-air graph

The same authenticated, bounded model-graph endpoints now support selecting the four-adapter reference-air graph with evaluation ID `bounded_reference_air_graph_experimental`. This adds no query parameter or new path and does not enable arbitrary model dispatch.

The GET catalog retains its original top-level default `evaluation` and `adapters` metadata and additionally exposes an `evaluations` mapping containing metadata for each evaluation ID. Clients must explicitly select `bounded_reference_air_graph_experimental` and use its matching metadata. Unknown evaluation IDs are refused without fallback.

Air density, dynamic viscosity (`mu`), and speed of sound bind into the wing Reynolds-number, Mach-number, and drag calculations. `altitude_kind` is required and must be `geometric` or `geopotential`; the supported altitude range is 0–30,000 m. Transport properties use NASA CAPE Sutherland relations, not exact COESA transport.

Both evaluations share the existing caps, authentication, request-body limits, hashing, and CSRF protections.

This is a local prototype, not a deployed feature, a full M3 implementation, or a physically qualified model.
