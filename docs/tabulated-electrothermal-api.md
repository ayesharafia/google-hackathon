# Tabulated electrothermal HTTP transport (V122)

V122 exposes the accepted V121 workflow through two canonical routes:

- `GET /api/drone/tabulated-electrothermal/catalog`
- `POST /api/drone/tabulated-electrothermal/evaluate`

The transport calls the existing workflow without changing its science, result
guards, authentication policy, status vocabulary, counts, units, or hashes.
See [the V121 workflow contract](tabulated-electrothermal.md) for model details.
This is a local HTTP implementation; it establishes no deployed availability.

## Catalog

GET returns exactly two top-level keys: `catalog` and `transport`. `catalog` is
one fresh call to `workflow.tabulated_electrothermal_catalog()` per request.
`transport` holds separate HTTP metadata. Catalog retrieval runs no evaluator,
energy model, thermal model, or thermal integrator. Nested metadata is detached
by the existing catalog implementation.

## Evaluation

POST accepts a strict UTF-8 JSON object. The existing model-graph parser helpers
reject duplicate keys at every nesting level and nonfinite JSON constants. The
actual V121 `_json_walk(body, _LIMITS["input_json"])` runs before dispatch and
rejects invalid Unicode, nonfinite numbers, excessive depth, node count,
container size, string length, and integer size under its unchanged budget.
Parser and input-walker failures return HTTP 422 with exactly:

```json
{"detail":"Invalid tabulated electrothermal request."}
```

Exception text is not included. A parsed, bounded object is passed once to the
actual `evaluate_tabulated_electrothermal(body)` through `run_in_threadpool`.
The full actual JSON result is returned unchanged, including nested results,
statuses, reasons, units, counts, nullable hashes, stages, and transfers. The
transport neither reruns models nor constructs a substitute result envelope.

Every structured workflow result uses HTTP 200, including V121
`MODEL_INAPPLICABLE`, `SOLVER_UNSUPPORTED`, and `EXECUTION_FAILED` results.
HTTP 200 alone establishes no computational or physical success. Boundary
failure reasons do not establish the cause of an untrusted child failure.
Counts describe fully guarded results, not attempts or execution attestation.
Request and result hashes retain their existing data-binding semantics.

## Independent limits

| Bound | Limit | Meaning |
| --- | ---: | --- |
| HTTP request | 1,048,576 bytes (1 MiB) | Actual received bytes, including whitespace and UTF-8 encoding |
| Full workflow input | 1,048,576 nodes including keys | `catalog.limits.input_json` |
| Full workflow response | 8,388,608 nodes including keys | `catalog.limits.output_json` |

Bytes and nodes are independent units. The request byte cap is never applied
to responses. Child budgets and model shape limits remain those in the actual
catalog. Model shape maxima do not promise HTTP acceptance in all combinations.

The middleware follows the V113 framing policy. Negative or oversized declared
Content-Length returns 413; malformed declared length returns 400. Signed or
whitespace-bearing lengths follow the existing integer/range check followed by
the digits-only check. A missing header or a dishonestly small declared length
does not bypass counting of actual bytes. Crossing the actual byte cap returns
413 and stops consuming subsequent chunks. A declared oversize is rejected
before body consumption. The middleware does not add framing reconciliation
for declared lengths that differ from the received body.

Byte errors use `{"detail":"request byte budget exceeded"}`; malformed header
errors use `{"detail":"invalid content length"}`. The byte middleware also
matches trailing slashes. Existing router redirects and auth ordering remain
in force, so a local slash request can redirect before consuming a body; its
canonical follow-up is bounded independently.

## Authentication and scope

Existing authentication precedes body consumption, declared-length checks,
parsing, and evaluation. Protected local mode retains bearer and real browser
cookie behavior, including Origin checks for cookie-authenticated mutations.
Public local mode retains its existing Origin policy. Hosted mode retains
individual bearer sessions and real hosted cookies with Origin checks.

Hosted authorization adds only the two exact canonical paths above. Neighbor
paths and trailing-slash paths gain no prefix authorization. Existing methods,
authentication defaults, and unrelated routes remain unchanged.

The underlying one-way allocated-heat screening establishes no physical
temperature, hotspot or Biot validation, thermal feedback, battery behavior,
real-flight mission qualification, publication qualification, or deployed API
availability. The full child limitations remain applicable.

## Focused verification

The API tests use the V113 Settings/lifespan client pattern with a real,
preprovisioned hosted identity and the V121 `request(2)` fixture. They compare
complete actual workflow results in local and hosted modes, audit one worker
call with event-loop progress and actual energy/thermal calls, check fresh
catalogs without child execution, reject malformed JSON without dispatch,
compare actual invalid/unsupported workflow refusals, and check exact hosted
path authorization. Test execution evidence is supplied by the independent
runner; this document does not claim author-shell test passes.


## Gate vocabulary and verification limits

The actual V121 invalid-request and unsupported-evaluation gates return
`MODEL_INAPPLICABLE` and `SOLVER_UNSUPPORTED`, respectively. The transport does
not introduce `INVALID_INPUT` or `UNSUPPORTED` aliases. Child exception and
untrusted-status probes compare the actual root `EXECUTION_FAILED` result to
HTTP JSON exactly, with only the child boundary fault-injected. Private child
status, reasons and exception text are discarded by the unchanged root gates;
the retained boundary reason does not establish a child's failure cause.

Full input (1,048,576 nodes) and output (8,388,608 nodes) extrema are helper-only
checks of the actual walker using compact alias trees. They establish node
budget behavior, not HTTP acceptance or scientific result feasibility. A
separate reduced-node-budget unit probe checks rejection before dispatch;
it changes only its test fixture's limit. Production limits remain unchanged.
Depth, container, string, integer and overflowed-number failures also exercise
the actual input walker through HTTP before evaluator dispatch.

The response larger than 1 MiB test is explicitly a transport unit fixture:
it substitutes a labeled JSON payload for the evaluator and executes no child
model. It verifies that the request byte cap is not imposed on responses. It
does not establish that an actual computed workflow response has that size.
Raw ASGI byte probes use a small Starlette app with FastAPI-style JSON
HTTPException handling, separate from full-app authentication and route checks.
