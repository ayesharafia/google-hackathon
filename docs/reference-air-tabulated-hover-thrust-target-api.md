# Reference air tabulated hover thrust target HTTP transport - V111

This bounded local HTTP transport calls the accepted V110 reference-air thrust
target workflow. See the [V110 request and response contract](reference-air-tabulated-hover-thrust-target.md)
for the exact payload, model assumptions, units and limitations. All model
inputs remain explicit; the transport adds no defaults.

The canonical routes are:

| Method | Path |
| --- | --- |
| GET | `/api/drone/reference-air-tabulated-hover-thrust-target/catalog` |
| POST | `/api/drone/reference-air-tabulated-hover-thrust-target/evaluate` |

Both inherit the application's existing access configuration. Authentication and
access checks precede body consumption, declared-length checks and parsing.
V111 introduces no authentication policy change. Unsafe methods here mean
methods other than GET, HEAD and OPTIONS.

In protected local mode (`public_access=False`), configuration requires a
nonblank `PHYSIMESH_API_TOKEN`. Either a valid bearer token or a valid remembered
browser-session cookie permits access. An explicitly invalid `Authorization`
header receives 401 even with a valid cookie; missing both valid methods also
receives 401. Cookie-only unsafe requests require a same-origin `Origin`, or
receive 403. A valid bearer request does not acquire that cookie-only origin
requirement.

Public local mode (`public_access=True`, or `PHYSIMESH_PUBLIC_ACCESS=1`)
intentionally permits these routes without a token or cookie and requires no
configured token. An unsafe request with an `Origin` must be same-origin;
a different origin receives 403. An unsafe request without `Origin` is allowed
by this existing public policy. Public mode does not enable agent access.

Hosted mode requires an individual bearer session or, when hosted browser
sign-in is enabled and `Authorization` has no value, a valid hosted browser
cookie. Unsafe cookie-authenticated requests require a same-origin `Origin`.
An invalid nonempty authorization value does not fall back to the cookie.
The configured local token is not an individual hosted session. Public access
is forbidden in hosted mode.

For an already running app, save the exact JSON example from the V110 contract
as `request.json`. `TOKEN` below is a dummy placeholder for a configured local
bearer token or an individual hosted session token:

```sh
curl -H 'Authorization: Bearer TOKEN' \
  http://127.0.0.1:8000/api/drone/reference-air-tabulated-hover-thrust-target/catalog

curl -H 'Authorization: Bearer TOKEN' -H 'Content-Type: application/json' \
  --data-binary @request.json \
  http://127.0.0.1:8000/api/drone/reference-air-tabulated-hover-thrust-target/evaluate
```

GET returns exactly `{ "catalog": ..., "transport": ... }`. Every GET calls
`reference_air_tabulated_hover_thrust_target_catalog()` afresh. The actual
catalog, including its nested model metadata, units, limits and contracts,
remains unchanged. Separate HTTP metadata lives in `transport`; the transport
does not duplicate the model catalog there.

POST decodes a strict UTF-8 JSON object with the shared `_pairs` duplicate-key
guard and `_constant` nonfinite-constant guard, then calls the actual
`workflow._JSON(body, workflow._LIMITS['input_json'])` before dispatch.
Duplicate keys at any level, NaN and infinities, exponent overflow, invalid
UTF-8, unpaired surrogates, malformed JSON, nonobject roots and input-walker
failures receive the same generic 422 response, without evaluator calls:

```json
{"detail":"Invalid reference air tabulated hover thrust target request."}
```

For a parsed, bounded object, the actual
`evaluate_reference_air_tabulated_hover_thrust_target` runs exactly once through
`run_in_threadpool`, off the event loop. V110 owns preflight and component
execution. An accepted calculation calls actual reference air once and the
actual inverse once. The inverse owns its forward trials: a computed result
uses 2..64 actual forward evaluations within the caller's budget. One inverse
call does not mean one forward core call. Declared work remains
`max_evaluations * annuli <= 32768`; preflight failures can make no component
calls and an actual domain refusal can stop at the first forward trial.

Structured V110 results receive HTTP 200 with the actual full JSON value
unchanged. The transport adds no `input_sha256`, changes no nested digests and
does not reseal the evaluation. HTTP 200 does not establish that a calculation
completed or that a physical target is attainable. The V110 contract owns
statuses, exact reasons, nullable hashes and counts:

| V110 outcome | Status | `inverse_evaluation_count` | `request_sha256` | `evaluation_sha256` |
| --- | --- | --- | --- | --- |
| Invalid bounded preflight | `MODEL_INAPPLICABLE` | 0 | null | null |
| Another outer evaluation string | `SOLVER_UNSUPPORTED` | 0 | null | null |
| Snapshot failure before acceptance | `EXECUTION_FAILED` | 0 | null | null |
| Actual validated inverse success | `COMPUTED_EXPERIMENTAL` | Accepted count, 2..budget | Accepted outer request digest | Actual outer response digest |
| Actual endpoint range refusal | `TARGET_NOT_BRACKETED` | 2 | Accepted outer request digest | Actual outer response digest |
| Actual evaluation budget exhaustion | `ITERATION_LIMIT` | budget | Accepted outer request digest | Actual outer response digest |
| Actual representable midpoint limit | `NUMERICAL_LIMIT` | 2..budget-1 | Accepted outer request digest | Actual outer response digest |
| Actual physical or numerical domain refusal | `MODEL_INAPPLICABLE` | Accepted count, 1..budget | Accepted outer request digest | null |
| Actual validated inverse execution failure | `EXECUTION_FAILED` | Accepted count, 0..budget | Accepted outer request digest | Actual outer response digest |
| Invalid component result or exception before inverse guard acceptance | `EXECUTION_FAILED` | 0 | Accepted outer request digest, if available | Actual outer response digest, if request digest exists |
| Exception after inverse guard acceptance | `EXECUTION_FAILED` | Already accepted count | Accepted outer request digest | Actual outer response digest |

The count is always a builtin integer from 0 through 64. An invalid inverse
result cannot supply a trusted count. Every non-success result is atomic:
empty `outputs`, `output_units`, `stages` and `transfers`, with
`diagnostics_complete: false`. Ordinary exceptions remain sanitized by V110;
`BaseException` propagates. Hashes bind the accepted JSON snapshots using the
unchanged canonical encoding, not runtime identity. Each evaluation digest
omits only its own field. A fault before the outer request digest exists leaves
both outer hashes null.

Successful `outputs.air` contains the full actual validated raw air once.
`outputs.target` contains the full actual inverse response once, including its
selected full forward request and response. `output_units.air` covers the entire
raw air object, including its nested state. `output_units.target` covers only
`outputs.target.outputs`, not the inverse envelope. Selected forward units
cover `outputs.target.outputs.actual_forward_result.outputs`; the forward
request has its own unit mapping within the inverse outputs' units.

The ordered air and target stages contain actual inputs, `inputs_sha256` and
`result_sha256`, without duplicate full component results or annular arrays.
The sole density transfer binds `air.state.density_kg_m3` to
`target.rotor_template.density_kg_m3`, in `kg/m^3`, using the actual raw air digest
and injected inverse request digest. Caller data, injected snapshots and
component arguments remain separate. V110 detaches raw air and density before
the inverse and copies the inverse result before guard validation. Returned
JSON remains mutable; editing it invalidates its data hashes.

Intermediate inverse trace `full_actual_result_sha256` values remain
**FORMAT-ONLY producer-reported provenance**: their full payloads are absent.
Only the selected retained full forward response is content-verified by the
accepted guard. Necessary failure-count bounds are consistency checks, not
execution attestation. The narrow normal deterministic admission contract
excludes unexpected inverse infrastructure copy/hash fault envelopes; those
fail validation and become atomic outer `EXECUTION_FAILED` with count 0.
The transport does not rerun models or create substitute results for admission.

The independent HTTP request limit is **131072 actual received bytes**,
including UTF-8 encoding and whitespace. Actual chunks count even with absent,
understated or chunked `Content-Length`. A negative or oversized declared length
receives 413; malformed length receives 400. Crossing the actual received byte
limit receives 413 before evaluation. A valid request padded to exactly 131072
bytes can succeed; one extra byte is refused. These errors are separate from
the parser's generic 422.

| Independent V110 JSON boundary | Nodes including keys | Maximum depth, root = 1 | Items per container |
| --- | ---: | ---: | ---: |
| Outer input | 32768 | 12 | 256 |
| Injected inverse input | 16384 | 11 | 256 |
| Each forward input | 8192 | 10 | 256 |
| Each full forward output | 32768 | 10 | 2048 |
| Full inverse output | 65536 | 16 | 2048 |
| Outer output | 131072 | 20 | 2048 |

Every walker also limits strings to 2000 Unicode characters, integers to 1023
bits and floats to finite values, with strict UTF-8 strings. Shape maxima remain
256 stations, 512 annuli, 32 blades and 64 declared forward evaluations. Shape,
work, nested JSON and HTTP byte bounds apply independently; maximum shapes do
not promise acceptance in every combination.

The numeric **131072-node outer output budget is not the 131072-byte request
budget**. There is no new response byte limit. An actual endpoint-success fixture
with 256 stations, 512 annuli, 32 blades and a declared budget of 64 uses two
forward evaluations: its request measures 20207 bytes and its full response
142654 bytes, while passing the V110 output JSON bounds. These measurements
describe that fixture, not a universal response size or acceptance guarantee.

Hosted access adds only the two exact canonical paths above to the existing
allowlist. After valid access checks, neighboring paths receive 403 in hosted
mode and 404 locally. Hosted slash paths are not allowlisted and receive 403
before body consumption. Rejected authentication runs before slash handling,
body-length checks, parsing or evaluator dispatch.

For a local request allowed by existing access checks, the byte middleware
matches the evaluation path after `rstrip('/')`. An oversized declared length
therefore receives 413 even on a slash path. Otherwise the router can return
307 to the canonical path without consuming the body or running the evaluator.
For example, a slash request with an oversized body and a lying small declared
length redirects without reading it; submission to the canonical path then
receives 413. Use the canonical URLs to avoid repeat submission.

The HTTP checks cover protected local and hosted bearer access, public local
access without a configured token, issued local and hosted browser cookies,
explicit invalid authorization, origin enforcement, strict parsing, unchanged
full results and hashes, actual component counts, maximum shape, request-byte
boundaries, slash ordering and event-loop progress during worker execution.
Cookie checks use real issued sessions; external provider sign-in is outside
these transport checks. Public local checks also cover the preserved agent
access prohibition. These checks establish no deployed API availability.

This experimental density transfer supplies no Reynolds or Mach feedback,
polars, stall, swirl, losses, motor or structural limits, attainable RPM,
physical trim or aircraft feasibility. Source, geometry classification and
unknown uncertainty remain unverified caller assertions. Physical validation,
numerical qualification and runtime identity remain `NOT_ESTABLISHED`, with
null aircraft status and feasibility. No graph or mission capability, 80 percent
accuracy, novelty, publication or qualification claim is added.
