# Tabulated solved electrothermal HTTP transport (V130)

V130 exposes the accepted V129 actual coupled solve/DC chronology and one-way
thermal workflow through two canonical routes:

- `GET /api/drone/tabulated-solved-electrothermal/catalog`
- `POST /api/drone/tabulated-solved-electrothermal/evaluate`

This is local API integration, not API deployment or live publication. The
[accepted V129 contract](tabulated-solved-electrothermal.md) and all child
limitations and qualification statements remain unchanged. No UI is added.

## Catalog

GET returns exactly `catalog` and `transport`. Each request makes exactly one
actual `tabulated_solved_electrothermal_catalog()` call, returning fresh metadata
without evaluator, solver, DC, thermal or core execution. Transport metadata
refers to `catalog.limits.input_json`, `catalog.limits.output_json` and
`catalog.limits` for independent JSON and model shape bounds. HTTP status
semantics refer to `catalog.status`, `catalog.reasons` and `catalog.limitations`.

## Evaluation

POST accepts a strict UTF-8 JSON object. The existing `_pairs` and `_constant`
parser helpers reject duplicate keys at every depth and nonfinite constants.
The actual V129 `_json_walk(body, _LIMITS["input_json"])` visits the whole body
before dispatch, including otherwise unused fields. Invalid Unicode, nonfinite
numbers, excessive JSON depth, nodes, container size, string length and integer
size produce the same generic HTTP 422 response as parser failures:

```json
{"detail":"Invalid tabulated solved electrothermal request."}
```

Raw parser causes are omitted. A parsed, bounded object is passed once to the
actual `evaluate_tabulated_solved_electrothermal` in the threadpool. The full
actual workflow result is returned unchanged, including nested results, statuses,
reasons, counts, units, hashes, stages and transfers. The transport adds no
result envelope and reruns no child model.

Every structured workflow result uses HTTP 200, including
`MODEL_INAPPLICABLE`, `SOLVER_UNSUPPORTED`, sanitized `EXECUTION_FAILED`, and
computed results with unmet residuals. Model preflight refusals remain structured
workflow results; they are distinct from transport JSON admission failures.
HTTP 200 establishes neither computational nor physical success.

All-met results retain actual energy and thermal results. Mixed unmet results
retain every ordered point and stage, with thermal state
`NOT_RUN_RESIDUAL_UNMET`, null thermal output and no outer thermal transfers or
temperature claim. Native integer durations survive transport and thermal
injection; the existing thermal model owns its float conversion. Counts record
fully guarded results, not attempts or execution attestation. Hashes bind data,
not execution identity. Untrusted child statuses, reasons and exception text are
sanitized by V129; boundary failure establishes no child failure cause.

## Independent bounds

| Bound | Limit | Reference |
| --- | --- | --- |
| Actual received request | 1,048,576 bytes (1 MiB) | Transport byte middleware |
| Full workflow input | 4,194,304 nodes including keys; depth 28 | `catalog.limits.input_json` |
| Full workflow response | 33,554,432 nodes including keys; depth 40 | `catalog.limits.output_json` |

Bytes include whitespace and UTF-8 encoding. The request byte cap is not a
response cap. Response JSON and child budgets remain independent. Neither model
shape maxima nor JSON node maxima promise HTTP acceptance in all combinations;
not all maximum settings fit this HTTP transport.

Both Content-Length and actual streamed bytes are checked. Negative or oversized
declared lengths return 413 before receiving the body. Malformed lengths return
400, following the accepted integer/range check then digits-only check. Missing
headers, chunked transfer and dishonestly small lengths cannot bypass actual
byte counting. Crossing the cap returns 413 and stops subsequent chunk reads.
There is no new exact framing reconciliation for an in-budget declaration.
Byte errors use `{"detail":"request byte budget exceeded"}` and malformed
lengths use `{"detail":"invalid content length"}`.

`TabulatedSolvedElectrothermalBodyLimit` also matches paths after stripping
trailing slashes. Existing router ordering is preserved: an authorized local
slash request may redirect without reading its body, while a declared oversize
is rejected before that redirect. Its canonical follow-up is independently
bounded. Hosted authorization permits only the two exact canonical paths.

## Authentication and route scope

Existing authentication always precedes receive, declared-length checks,
parsing and evaluation. Protected local mode retains bearer tokens and real
browser cookies with same-origin mutation checks. Public local mode retains
its existing origin policy. Hosted mode retains individual sessions and hosted
cookies with origin checks; the configured local bearer token does not become
a hosted individual session.

Neighbor paths, prefix lookalikes and hosted trailing slashes gain no
permission. No wildcard or private-project authorization is added. Existing
method handling, redirects, legacy routes and authentication behavior remain
unchanged.

## Verification scope

The API tests adapt the accepted V122 transport tests using the actual V129
`tests.drone.test_tabulated_solved_electrothermal.request` fixture. Local and
hosted cases compare full HTTP and direct results for all-met and both mixed
unmet orders, native integer duration 9007199254740993 with zero conductance and
mass 10**16, invalid later thermal fields before any model call, and sanitized
energy/thermal boundary failures. Wrapped actual children check point, solve,
assembly, forward, DC and thermal counts without substituting science results.
Other checks cover worker dispatch and event-loop progress, catalog freshness,
strict parsing, whole-body walking, actual byte boundaries and auth ordering.

Production node/depth/container budgets are asserted without allocating a full
32M-node tree. Reduced-budget helper tests exercise exact node and plus-one
refusal using the real walker; a reduced-budget transport probe checks refusal
before dispatch. Actual nominal requests exercise unchanged production limits.
A response larger than 1 MiB is explicitly a labeled transport unit fixture,
not an actual science result. It proves only that request bytes do not cap
responses. Raw byte-framing unit probes likewise make no science claim.

This integration establishes no physical temperature, hotspot or Biot
validation, thermal feedback, battery behavior, aircraft feasibility, real-flight
mission qualification, numerical qualification or publication qualification.
