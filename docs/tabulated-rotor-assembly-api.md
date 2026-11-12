# Tabulated rotor static assembly HTTP transport (V113)

V113 adds local HTTP transport for the independently accepted V112
`literal_tabulated_rotor_static_assembly_experimental` workflow. The
[V112 contract and runnable request example](tabulated-rotor-assembly.md)
remain the source for the exact science, guards, explicit inputs, units,
formulas, hashes, counts and limitations. This transport introduces no model
defaults, source fetching, scientific changes or deployment claim.

| Method | Canonical path |
| --- | --- |
| GET | `/api/drone/tabulated-rotor-assembly/catalog` |
| POST | `/api/drone/tabulated-rotor-assembly/evaluate` |

GET returns exactly `{ "catalog": ..., "transport": ... }`. Each request calls
`tabulated_rotor_assembly_catalog()` afresh and returns the actual complete V112
catalog unchanged. Separate transport metadata describes HTTP parsing,
execution, limits and ordering. Catalog requests execute no air or rotor model.

For an already running application, serialize the explicit request in the V112
example as `request.json`. These examples use a placeholder bearer credential
for protected local mode or an individual hosted session:

```sh
curl -H 'Authorization: Bearer TOKEN' \
  http://127.0.0.1:8000/api/drone/tabulated-rotor-assembly/catalog

curl -H 'Authorization: Bearer TOKEN' -H 'Content-Type: application/json' \
  --data-binary @request.json \
  http://127.0.0.1:8000/api/drone/tabulated-rotor-assembly/evaluate
```

## Existing access policy and ordering

Access depends on the application's existing configuration. V113 changes no
authentication policy. Unsafe methods mean methods other than GET, HEAD and
OPTIONS. Applicable authentication and access checks run before body
consumption, declared-length checks, parsing or evaluator dispatch.

In **protected local mode**, a nonblank configured `PHYSIMESH_API_TOKEN` is
required. Either a valid bearer token or a real issued browser-session cookie
permits access. An explicitly invalid `Authorization` header receives 401 even
with a valid cookie; missing both credentials also receives 401. This includes
an explicitly empty authorization header locally. Cookie-only unsafe requests
require a same-origin `Origin`, otherwise they receive 403. Valid bearer
requests do not acquire that cookie-only origin requirement.

In **intentionally public local mode** (`public_access=True`, or
`PHYSIMESH_PUBLIC_ACCESS=1`), these routes require no bearer token, cookie or
configured token. Unsafe requests with an `Origin` must be same-origin;
a different origin receives 403. Unsafe requests without `Origin` are allowed
by this existing policy. Public local mode preserves the prohibition on agent
access and cannot be enabled in hosted mode.

In **hosted mode**, access requires an individual bearer session or, when hosted
browser sign-in is enabled and `Authorization` has no value, a valid real issued
hosted browser cookie. Unsafe cookie-authenticated requests require a
same-origin `Origin`. An invalid nonempty authorization value receives 401 and
cannot fall back to the cookie. An empty value follows the existing hosted
cookie-selection policy. The configured local bearer token is not an
individual hosted session. Cookie tests use actual issued local and hosted
sessions; they do not establish external provider sign-in availability.

Only the two exact canonical paths above are added to the hosted allowlist.
After successful access checks, neighboring paths receive 403 hosted and 404
locally. Hosted trailing-slash paths receive 403 before reading the body.
Authentication failures precede that slash-path decision.

For local requests allowed by the existing access checks, the byte middleware
matches the evaluation path after `rstrip('/')`. An oversized declared length
therefore receives 413 even on a slash path. Otherwise the existing router can
return 307 to the canonical path without consuming the body or evaluating it.
For example, a slash request with a lying small declared length can redirect
without reading its oversized body; submitting that body to the canonical path
receives 413. Canonical routes avoid repeat submission. Unsupported methods on
canonical routes receive 405 after applicable access checks.

## Parsing, bytes and execution

POST requires a strict UTF-8 JSON object. The shared duplicate-key and
nonfinite-constant guards reject duplicate keys at any nesting level, NaN and
infinities. The actual V112 `_json(body, _LIMITS['input_json'])` walker runs
before dispatch. Malformed JSON, invalid UTF-8, unpaired surrogates, exponent
overflow, nonobject roots and walker failures receive the same generic 422,
without evaluator calls or disclosure of parser exception text:

```json
{"detail":"Invalid tabulated rotor assembly request."}
```

The independent request budget is **131072 actual received bytes**, including
UTF-8 encoding and whitespace. Received chunks count with missing,
understated or chunked length framing; `Content-Length` cannot replace actual
byte accounting. A negative or oversized declared length receives 413.
Malformed declared length receives 400. Crossing the actual byte budget
receives 413 before evaluation. A valid JSON request padded with whitespace to
exactly 131072 bytes can succeed; one extra byte is refused. UTF-8 sequences may
span received chunks: accounting uses bytes and decoding follows body assembly.

For a parsed and bounded object, `evaluate_tabulated_rotor_assembly` runs
**exactly once through `run_in_threadpool`**, off the event loop. V112 owns all
rotor preflight before any air or rotor work. A completed calculation calls
actual reference air once, then the actual forward adapter once per ordered
rotor, with one actual forward core call per rotor. Refusal or failure can stop
earlier; invalid preflight makes no component calls. The transport neither
reruns models nor creates replacement component results.

Structured workflow results receive HTTP 200 with the **complete actual V112
response unchanged**. HTTP 200 alone establishes neither computational success
nor physical success. The transport adds no `input_sha256` or other hash,
changes no digest, and does not rehash or reseal the returned evaluation.

## Response, counts and data bindings

| V112 outcome | Status | `rotor_evaluation_count` | Outer request hash | Outer evaluation hash |
| --- | --- | --- | --- | --- |
| Invalid bounded preflight | `MODEL_INAPPLICABLE` | 0 | null | null |
| Different outer evaluation label | `SOLVER_UNSUPPORTED` | 0 | null | null |
| Snapshot failure before request acceptance | `EXECUTION_FAILED` | 0 | null | null |
| Every rotor guarded and static load arithmetic completed | `COMPUTED_EXPERIMENTAL` | Number of rotors | Accepted request digest | Actual response digest |
| Validated actual rotor domain refusal | `MODEL_INAPPLICABLE` | Validated envelopes including the refusing rotor | Accepted request digest | null |
| Invalid component, ordinary exception or subsequent load/output failure | `EXECUTION_FAILED` | Only envelopes already fully guarded | Accepted request digest, if available | Actual response digest if request digest exists |

The count is a builtin integer from 0 through 8. It increments only after the
full child envelope guard succeeds, including a valid domain-refusal envelope.
It does not count attempted calls and does not attest execution. For example,
a malformed second child leaves count 1 despite two adapter attempts; a valid
second-child domain refusal leaves count 2.

Every non-success result is atomic: `outputs` and `output_units` are empty
objects, `stages` and `transfers` are empty lists, and `diagnostics_complete` is
false. Ordinary exceptions are sanitized by V112; `BaseException` propagates.
Hashes bind JSON data using the unchanged canonical SHA256 encoding. Each
`evaluation_sha256` excludes only its own field. Hashes establish no runtime
identity, physical validation or successful execution.

Successful `outputs.air` contains the full actual guarded raw air once,
including its nested state. Each ordered `outputs.rotors` row contains its
loads, the actual density-injected forward request and the unchanged complete
guarded forward result. V112 immediately detaches air and child snapshots
before subsequent use; returned JSON remains mutable, and edits invalidate its
data hashes. No immutable-object claim is made.

`output_units.air` covers the full raw air. Rotor load units are N and N*m;
`output_units.rotors.actual_forward_request` describes the injected request.
`output_units.rotors.actual_forward_result.outputs` applies only to each nested
forward result's `outputs`, not its response envelope. Full vector units and
caller input units remain as declared in the actual catalog.

Stages are ordered `air`, then `rotor:<id>`, including a possible `rotor:air`.
Each contains actual inputs, `inputs_sha256` and `result_sha256`, without
another full component result or duplicate annular arrays. Each density
transfer binds `air.state.density_kg_m3` to the corresponding rotor request's
`density_kg_m3` in kg/m^3, with the actual air-result digest and injected
consumer-request digest. Counts and digests remain data-contract checks,
without execution attestation.

## Independent resource bounds

| Actual V112 JSON boundary | Nodes including keys | Maximum depth, root = 1 | Items per container |
| --- | ---: | ---: | ---: |
| Assembly input | 65536 | 12 | 256 |
| Each injected forward input | 8192 | 10 | 256 |
| Each full forward output | 32768 | 10 | 2048 |
| Assembly output | 262144 | 20 | 2048 |

The walkers also bound strings to 2000 Unicode characters and integers to 1023
bits, require finite floats and strictly encodable UTF-8 strings, and retain
all V112 type guards. Shape limits remain 1..8 rotors, at most 4096 annuli
summed across rotors, at most 2048 annuli per rotor, 2..256 stations per rotor,
and 1..32 blades per rotor. Templates must omit caller-supplied density.

The **131072-byte request bound**, input/output node and depth bounds, child
bounds and model-work bounds apply independently. Maximum shape values do not
promise HTTP acceptance in every combination. In particular, eight rotors
cannot each use 2048 annuli under the aggregate 4096-annulus limit.

There is no response byte cap at 131072. The actual maximum aggregate fixture
uses eight rotors with 512 annuli each, 256 stations per rotor and 32 blades.
Its compact request is 120356 bytes; the complete response is 969646 bytes,
passes the actual output walker, and equals direct V112 evaluation. These are
measurements of that fixture, not universal size or acceptance guarantees.

## Static load scope and verification

V112 uses an explicitly declared right-handed forward/left/up body frame.
For each rotor, thrust acts along its declared unit axis, reaction torque
opposes its declared spin, and moment about the CG is
`(center - CG) cross force + reaction_torque`. Gravity is
`mass * actual_gravity * gravity_direction`, applied at the CG with zero
gravity moment. Net force and moment use per-component `math.fsum` under the
unchanged signed finite-normal-or-zero arithmetic guards. The catalog retains
the exact formulas and unit-vector declaration tolerance; no normalization
or calibration is added.

This remains experimental static linear superposition of isolated
attached-linear small-angle hover rotors. Source, geometry classification,
frame and spin are unverified caller declarations. The transport establishes
no interference or installed-loss model, trim, control authority, stability,
attainability, safety, feasibility, mission capability, physical or numerical
qualification, publication qualification, or deployed API availability.
`physical_validation`, `numerical_qualification` and `runtime_identity` remain
`NOT_ESTABLISHED`; aircraft status and feasibility remain null.

Transport tests cover access policy, strict parsing, request-byte boundaries,
chunked bodies, origin enforcement, issued browser cookies, slash ordering,
fresh catalogs, unchanged actual V112 results and hashes, component counts,
forgery refusal, global preflight and output budgets, and event-loop progress
during worker execution.
