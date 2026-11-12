# Tabulated-hover HTTP API - V104 local source

This checkout adds a bounded HTTP transport for the actual V103
`evaluate_tabulated_hover_bemt` adapter. It describes local source behavior and
does not establish deployment, hosted availability, or physical validation.
The accepted V102 kernel and closed V103 request adapter remain unchanged.

| Method | Canonical path | Result |
| --- | --- | --- |
| GET | `/api/drone/tabulated-hover/catalog` | Fresh actual adapter catalog and separate transport metadata |
| POST | `/api/drone/tabulated-hover/evaluate` | Actual adapter JSON returned unchanged |

Both routes inherit the existing application authentication. A protected local
workspace accepts its configured bearer token or existing browser session;
hosted mode requires its existing individual session and authorization checks.
A local API token does not replace hosted identity. Browser cookies retain
same-origin requirements, and existing public-access configurations retain
their application behavior. Authentication precedes parsing and body consumption,
including declared-length rejection. No credential is supplied here.

For an application already running locally, save the complete JSON object from
the [V103 local usage example](tabulated-hover-request.md#local-usage) as
`tabulated-hover-request.json`. That synthetic example includes all 13 required
root fields: `evaluation` plus the twelve core arguments. It supplies geometry,
source classification, and uncertainty explicitly; its values are example
declarations, not defaults or design recommendations. The V103 document's
Python-only availability statement describes that earlier stage; the routes
above are the V104 addition.

```bash
BASE_URL=http://127.0.0.1:8000
: "${PHYSIMESH_API_TOKEN:?Set your existing local API bearer token}"
curl --fail-with-body \
  --header "Authorization: Bearer ${PHYSIMESH_API_TOKEN}" \
  "${BASE_URL}/api/drone/tabulated-hover/catalog"

curl --fail-with-body \
  --header "Authorization: Bearer ${PHYSIMESH_API_TOKEN}" \
  --header 'Content-Type: application/json' \
  --data-binary @tabulated-hover-request.json \
  "${BASE_URL}/api/drone/tabulated-hover/evaluate"
```

GET returns the nested object `{ "catalog": ..., "transport": ... }`.
`catalog` is the actual fresh `tabulated_hover_bemt_catalog()` result, including
its identifiers, request contract, units, response contract, limits, and
interpretation. Nested objects are fresh on each call. `transport` is HTTP
metadata added by this route, separate from the adapter schema. In particular,
`transport.limits.body_bytes` is `131072`; it is not inserted into
`catalog.limits`. Transport references point to `catalog.limits.input_json`,
`catalog.limits.output_json`, and `catalog.limits.core_work` instead of defining
a second model schema. POST returns the adapter envelope directly, without a
`catalog` or `transport` wrapper.

The dedicated POST byte bound is **131072 actual received bytes**, including
UTF-8 encoding, JSON syntax, and whitespace. A request at that exact size can
be accepted. Received ASGI body chunks are accumulated even with chunked
transfer, absent `Content-Length`, or a length that understates the body.
A parsed negative or over-budget declared length returns HTTP 413 before body
consumption; malformed declared lengths return HTTP 400. An accumulated body
over the bound returns HTTP 413. The byte-budget detail is
`request byte budget exceeded`; the malformed-length detail is
`invalid content length`. Split UTF-8 characters across chunks are decoded only
after body assembly. A small or misleading declared length cannot authorize
additional received bytes.

These bounds are independent:

| Guard | Input JSON | Response JSON |
| --- | --- | --- |
| Root depth | 1 | 1 |
| Maximum depth | 10 | 10 |
| Maximum visited nodes, including dictionary keys | 8192 | 32768 |
| Maximum items per container | 256 | 2048 |
| Maximum string length | 2000 characters, valid UTF-8 | 2000 characters, valid UTF-8 |
| Maximum integer magnitude bit length | 1023 | 1023 |
| Floats | Finite | Finite |

The actual model shape permits 2–256 stations, 1–2048 annuli, and 1–32 blades,
subject to the unchanged kernel contract. Shape maxima do not guarantee that
every combination of declarations fits the HTTP byte bound. JSON nodes count
keys and values, not bytes. **Responses are not limited to 131072 bytes** by
this transport; the adapter's independent output JSON budget applies. The
maximum-shape HTTP case uses 256 stations, 2048 annuli, and 32 blades with an
actual encoded request below the byte bound and a response larger than that
request bound. The complete response includes all output fields, all nine
annular arrays, station units, envelope fields, and hashes within the output
node budget.

POST strictly decodes UTF-8 JSON using the shared duplicate-key and nonfinite
constant rejection hooks. The root must be a builtin object. Duplicate keys
at any nesting level, `NaN`, `Infinity`, invalid UTF-8, malformed JSON, nonobject
roots, and failures of the actual unchanged V103 input JSON walker return the
same generic HTTP 422 body:

```json
{"detail":"Invalid tabulated hover request."}
```

These transport refusals invoke neither the adapter nor the core. Once parsing
and that walker succeed, the route dispatches the actual
`evaluate_tabulated_hover_bemt` exactly once through `run_in_threadpool`.
The event loop can progress while the adapter runs in a worker thread. The
adapter owns snapshot, model, and returned-result checks; a supported request
reaching execution invokes the actual core once. Shape or evaluation refusals
can stop before any core call. The HTTP layer does not run an independent core
evaluation or reproduce its result.

Structured adapter responses remain HTTP **200**, including model refusals
and execution failures. HTTP 200 alone establishes neither computational nor
physical success. The actual status and nullable hash semantics are:

| Condition after transport parsing | Adapter status | Core calls | `request_sha256` | `evaluation_sha256` |
| --- | --- | --- | --- | --- |
| Missing/extra root fields or invalid evaluation type | `MODEL_INAPPLICABLE` | 0 | null | null |
| Exact root with a different evaluation string | `SOLVER_UNSUPPORTED` | 0 | null | null |
| Actual core input, geometry, or numerical-domain refusal | `MODEL_INAPPLICABLE` | 1 | Copied-input digest | null |
| Actual completed output passes adapter checks | `COMPUTED_EXPERIMENTAL` | 1 | Copied-input digest | Actual response digest |
| Unexpected ordinary core exception or returned-contract/export failure | `EXECUTION_FAILED` | 1 | Copied-input digest | Actual failure-response digest |
| Unexpected snapshot/preparation exception | `EXECUTION_FAILED` | 0 | Digest if already available, otherwise null | Failure-response digest only if request digest exists |

Failure envelopes retain empty `outputs` and `output_units`, false
`diagnostics_complete`, and null core markers. A coherently forged core result
can still fail the actual adapter's checks and produce `EXECUTION_FAILED`.
The route does not catch a replacement adapter exception to invent a structured
success; `BaseException` is not converted into an adapter envelope.

Both hashes already belong to V103 and are returned **unchanged**. The HTTP
layer adds no `input_sha256` and recomputes no digest. The actual evaluation
digest binds the adapter response including its request digest and excluding
`evaluation_sha256` itself, using the accepted provenance encoding. A null hash
means no digest is available. A core refusal with only a request digest records
the input, not a completed computation. Hashes bind data and establish neither
runtime identity nor physical correctness.

Canonical paths and existing trailing-slash ordering are preserved. With valid
authorization, hosted mode permits only the two exact paths; neighboring paths
and trailing slashes receive HTTP 403. Local neighboring paths receive HTTP
404, and canonical paths with unsupported methods receive HTTP 405. Locally,
a trailing slash normally redirects with HTTP 307. For POST `/evaluate/`, the
byte middleware matches the slash path: an over-budget declared length is
rejected with 413 before redirect. If the declaration passes or understates the
body, the router can redirect without consuming it; retrying the canonical path
then enforces the actual received-byte bound. Hosted authorization rejects the
slash path before those middleware/redirect steps. Missing or invalid credentials
in protected configurations are rejected before any of this body processing.

The [HTTP tests](../tests/drone/test_tabulated_hover_application.py) cover actual
HTTP/direct equality, unchanged hashes, adapter/core call counts, fresh catalog
metadata, full maximum-shape output units, the nullable-status matrix, worker
thread heartbeat, authentication ordering, and byte/UTF-8 boundaries in local
and hosted application modes. Zero blade angle yields zero thrust and induced
power while positive profile drag can still require positive mechanical shaft
power. This behavior does not establish physical validation.

This addition provides no registry, scalar graph, rotor assembly, trim, DC, or
mission integration. It does not upgrade Reynolds, Mach, stall, loss, non-hover,
or installed-system modeling or validation. Geometry labels and uncertainty are
caller assertions. Numerical results, units, residuals, and digests do not
establish physical accuracy, numerical qualification, aircraft feasibility, or
runtime identity. See the unchanged [V103 request contract](tabulated-hover-request.md)
and [V102 kernel guide](tabulated-hover-bemt.md) for the actual model scope.
