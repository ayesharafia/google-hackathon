# Reference air tabulated hover HTTP transport - V107

This transport calls the accepted V106 workflow. See the
[V106 request and response contract](reference-air-tabulated-hover.md) for the
exact payload, model assumptions, units and limitations. No model inputs are
defaulted by the transport.

The canonical routes are:

| Method | Path |
| --- | --- |
| GET | `/api/drone/reference-air-tabulated-hover/catalog` |
| POST | `/api/drone/reference-air-tabulated-hover/evaluate` |

Both inherit the application's existing authentication configuration before body
consumption, length checks or parsing. This transport introduces no new
authentication policy. Unsafe methods below mean methods other than GET, HEAD
and OPTIONS.

In protected local mode (`public_access=False`), startup requires a configured
nonblank `PHYSIMESH_API_TOKEN`. Requests may use either a valid bearer token or a
valid remembered browser-session cookie. An explicitly invalid `Authorization`
header receives 401 even when a valid cookie is present; without either valid
authentication method, the request also receives 401. Cookie-only unsafe requests
require a same-origin `Origin`, otherwise they receive 403.

Public local mode (`public_access=True`, or `PHYSIMESH_PUBLIC_ACCESS=1`) intentionally
permits these non-agent routes without a bearer token or browser-session cookie
and does not require a configured token. Unsafe requests that include `Origin`
must be same-origin; a different origin receives 403. Public mode does not enable
agent access. This caveat describes the preserved application policy, not an
intentional policy change in V107.

Hosted mode protects these exact canonical paths using an individual bearer
session or, when hosted browser sign-in is enabled, a valid hosted browser cookie
with no `Authorization` value. Unsafe cookie-authenticated requests require a
same-origin `Origin`. The local configured token is not an individual hosted
session, and public access is unavailable in hosted mode.

For an already running local app, save the exact JSON example from the V106
document as `request.json`, then use these commands. `TOKEN` is a dummy placeholder
for the configured local token or an individual hosted session token.

```sh
curl -H 'Authorization: Bearer TOKEN' \
  http://127.0.0.1:8000/api/drone/reference-air-tabulated-hover/catalog

curl -H 'Authorization: Bearer TOKEN' -H 'Content-Type: application/json' \
  --data-binary @request.json \
  http://127.0.0.1:8000/api/drone/reference-air-tabulated-hover/evaluate
```

GET returns exactly `{ "catalog": ..., "transport": ... }`. Each GET calls the
actual `reference_air_tabulated_hover_catalog()` afresh. Its nested fields, units,
limits and contracts remain unchanged; HTTP metadata lives in `transport`.

POST decodes a strict UTF-8 JSON object using the shared duplicate-key and
nonfinite-constant guards, then runs the actual
`workflow._JSON(body, workflow._LIMITS['input_json'])` before evaluation.
Duplicate keys at any level, nonfinite numbers including exponent overflow,
invalid UTF-8, unpaired surrogates, malformed JSON, nonobject roots and input
walker failures receive the same generic 422 response:

```json
{"detail":"Invalid reference air tabulated hover request."}
```

For a parsed, bounded object, the actual
`evaluate_reference_air_tabulated_hover` runs exactly once through
`run_in_threadpool`, off the event loop. V106 owns preflight, actual air and
child calls, returned-contract checks and child physical-domain refusals. The
HTTP layer does not convert those refusals into parser errors.

Structured workflow results receive HTTP 200 with the actual full V106 JSON
value returned unchanged. The transport adds no `input_sha256`, recomputes no
evaluation digest and does not reseal the response. HTTP 200 alone does not
establish a completed calculation. V106 status and nullable digest semantics are:

| Workflow outcome | Status | `request_sha256` | `evaluation_sha256` |
| --- | --- | --- | --- |
| Invalid preflight | `MODEL_INAPPLICABLE` | null | null |
| Other outer evaluation string | `SOLVER_UNSUPPORTED` | null | null |
| Actual child domain refusal | `MODEL_INAPPLICABLE` | Accepted request digest | null |
| Completed workflow | `COMPUTED_EXPERIMENTAL` | Accepted request digest | Actual completed response digest |
| Failure after request digest exists | `EXECUTION_FAILED` | Accepted request digest | Actual failed response digest |
| Snapshot failure before acceptance | `EXECUTION_FAILED` | null | null |

Ordinary exceptions remain workflow-owned and sanitized; `BaseException` is not
masked by the transport. Failure outputs, units, stages and transfers follow the
unchanged V106 atomic contract.

On success, `outputs.air` contains the full raw air object and `outputs.rotor`
contains the full unchanged child response, including its own request and
evaluation hashes. `output_units.air` covers the entire raw air object, including
its nested state. `output_units.rotor` covers only `outputs.rotor.outputs`, not
the child response envelope. Stages contain actual inputs and digests; they do
not duplicate full component results or annular result arrays. The scalar density
transfer and all stage, child and outer digests remain exactly those of V106.
Source classifications and unknown uncertainty remain unverified caller assertions.

The independent HTTP request limit is **131072 actual received bytes**, including
UTF-8 encoding and whitespace. Characters and JSON nodes are separate bounds.
The canonical POST counts actual chunks even with absent, understated or chunked
`Content-Length`. A negative or oversized declared length receives 413; malformed
length receives 400. Crossing the actual byte limit receives 413 before workflow
evaluation. A valid request padded to exactly 131072 bytes can succeed; one more
byte is refused.

| JSON budget inherited from V106 | Nodes including keys | Maximum depth, root = 1 | Items per container |
| --- | ---: | ---: | ---: |
| Outer input | 16384 | 11 | 256 |
| Injected child input | 8192 | 10 | 256 |
| Child output | 32768 | 10 | 2048 |
| Outer output | 65536 | 16 | 2048 |

Each walk also bounds strings to 2000 Unicode characters, integers to 1023 bits
and floats to finite values. Shape limits remain 256 stations, 2048 annuli and
32 blades. Shape bounds, input resources and request bytes apply independently.
The request byte limit is not a new response limit: the tested actual maximum
shape response exceeds 131072 bytes and is allowed under its own output budgets.

Hosted authorization adds only the two exact canonical paths to the existing
allowlist; those paths still require hosted authentication. After the existing
access checks allow a request, neighboring paths receive 403 in hosted mode and
404 locally. Hosted trailing-slash paths are not allowlisted and receive 403
before body consumption. Protected authentication still runs before slash
handling; a rejected request does not reach the redirect or workflow.

For local requests allowed by the existing access checks, the body middleware
matches the evaluation path after `rstrip('/')`: an oversized declared length
receives 413 even on a slash path; otherwise the existing router can return 307
to the canonical path without consuming the body or executing the workflow.
For example, an oversized body with a lying small declared length redirects on
the slash path, then receives 413 when submitted to the canonical path. Use the
canonical URLs above to avoid a redirect and repeat submission.

HTTP transport tests in protected local and hosted modes cover supported parsed
responses, hash preservation, strict parsing, authentication and route ordering,
request-byte boundaries, and worker-thread responsiveness. Public-mode and
browser-cookie behavior above is documented from the preserved application
policy, not claimed as coverage of these transport tests. This coverage
establishes neither deployed availability nor physical validation.
