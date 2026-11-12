# Frozen-ledger solved DC electrothermal API - V101 local candidate

This source checkout adds an HTTP adapter for the actual V100
`evaluate_ledger_solved_dc_electrothermal` evaluator. It is a local candidate
pending main review. These instructions establish no deployed endpoint,
availability, acceptance, physical validation, or runtime identity.

The canonical routes are:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/drone/ledger-solved-dc-electrothermal/catalog` | Request shapes, independent limits, and interpretation |
| POST | `/api/drone/ledger-solved-dc-electrothermal/evaluate` | Evaluate one supplied frozen ledger and mission template |

## Authentication and local requests

Both routes use the existing application authentication middleware. In a
protected local workspace, use the configured API bearer token or the existing
browser session flow. Hosted mode uses its existing individual session and
authorization checks; the local API token does not replace that identity.
Browser cookie requests retain the existing same-origin requirements. Public
access configurations retain their existing application behavior.

For an application you have already started locally, supply your existing
credential through the environment. No credential is supplied by this guide:

```bash
BASE_URL=http://127.0.0.1:8000
: "${PHYSIMESH_API_TOKEN:?Set your existing local API bearer token}"
curl --fail-with-body \
  --header "Authorization: Bearer ${PHYSIMESH_API_TOKEN}" \
  "${BASE_URL}/api/drone/ledger-solved-dc-electrothermal/catalog"

curl --fail-with-body \
  --header "Authorization: Bearer ${PHYSIMESH_API_TOKEN}" \
  --header 'Content-Type: application/json' \
  --data-binary @ledger-mission-request.json \
  "${BASE_URL}/api/drone/ledger-solved-dc-electrothermal/evaluate"
```

The input file must contain supplied declarations. For a reproducible synthetic
example from the repository root, use the accepted test fixture with a Python
environment containing the project's test dependencies:

```bash
PYTHONPATH=src python - <<'PY'
import json
from pathlib import Path
from tests.drone.test_ledger_solved_dc_electrothermal import wrapper_request

request = wrapper_request.__wrapped__()
Path("ledger-mission-request.json").write_text(
    json.dumps(request, ensure_ascii=False), encoding="utf-8"
)
PY
```

This fixture is synthetic test input, not an aircraft design recommendation.
See the [V100 request and evaluator guide](ledger-solved-dc-electrothermal.md),
the [actual fixture](../tests/drone/test_ledger_solved_dc_electrothermal.py), and
the [HTTP tests](../tests/drone/test_ledger_solved_dc_electrothermal_application.py).

## Input and independent limits

The root object has exactly `evaluation`, `ledger`, and `mission_template`.
The evaluation identifier is
`ledger_solved_dc_electrothermal_mission_experimental`. The catalog describes the
ledger item, thermal body, segment, DC point, and assembly template shapes.

Every `mission_template.segments[*].point.solve.assembly_template` must omit
both `mass_kg` and `cg_body_m`. Supplying either is rejected even when it equals
the ledger value. The ledger retains its declared items, categories, property
source, mass, CG, and own-CG inertia requirements. The mission retains its
declared usable energy, reserve, thermal body, durations, motor parameters,
declared limits, heat capture fractions, auxiliary power, and thermal conditions.

The HTTP byte bound is **131,072 actual received bytes**. It includes JSON
syntax, UTF-8 encoding, and whitespace. Content-Length checks and accumulated
ASGI body bytes enforce the bound, including chunked requests, absent lengths,
and lengths that understate the received body. A valid JSON request padded with
whitespace to exactly the bound is permitted; exceeding it returns HTTP 413.
Malformed Content-Length returns 400. Negative lengths and parseable declared
lengths above the bound return 413; extremely long numeric headers that fail
Python integer parsing follow the existing 400 behavior.

This HTTP bound is independent of model shape and JSON budgets. A structurally
valid 16-segment, 128-item request can exceed it; the model maxima do not promise
HTTP acceptance for every combination.

The adapter uses V100's actual outer JSON guard: depth 13 with root depth one,
98,304 visited nodes including dictionary keys, at most 256 entries per
container, strings at most 2,000 characters encodable as UTF-8, integers at most
1,023 bits, and finite floating values. Duplicate keys at any depth, NaN,
Infinity, malformed UTF-8, and non-object roots return a generic HTTP 422.
Boolean JSON values remain invalid in numeric model fields.

The accepted independent child guards remain in force: ledger depth 10 and
16,384 nodes; instantiated mission depth 12 and 65,536 nodes; point depth 10
and 49,152 nodes; solver 32,768 nodes; motor 4,096 nodes. The accepted container,
string, integer, numeric, schema, arithmetic, graph, and per-child work checks
also remain unchanged. Model shape limits include 1–128 ledger items, 1–16
segments, at most 15 rotors per point, at most 512 annuli per rotor, and integer
solver evaluation limits from 2 through 64.

All segments must satisfy the mission-wide work constraint before any evaluator
runs:

```text
sum(segment_annuli * (segment_max_evaluations + 1)) <= 32768
```

Each point also retains its independent work bound. A later invalid segment or
excessive combined work prevents evaluation even if an earlier segment would
have stopped the mission.

## Actual execution and results

The adapter dispatches the actual V100 evaluator once through
`run_in_threadpool`. It parses and guards the outer request without duplicating
the ledger, mission, point, or thermal models or synthesizing result envelopes.

V100 preflights the ledger and every mission segment before any evaluator call.
After successful preflight, it evaluates the actual ledger once and validates
its returned contract and declared mass properties. It injects the validated
actual mass and CG into every mission point, preflights the complete instantiated
mission, then calls the actual mission evaluator once. Preflight or execution
failures can stop this sequence before later calls.

The ledger is frozen across the mission. There is no payload change, fuel
consumption, mass evolution, or mass inference from geometry. Ledger inertia is
reported and checked but unused by the mission solve. The separately declared
`thermal_body.mass_kg` is preserved and is never replaced by ledger mass.

Successful outputs and units are nested:

```text
outputs.ledger
outputs.mission.mission_state
outputs.mission.power_segments
outputs.mission.energy
outputs.mission.thermal
output_units.ledger
output_units.mission
transfers.mass_cg
transfers.mission
```

When all point residuals meet, `outputs.mission.mission_state` is
`COMPUTED_FROM_RESIDUAL_MET_SEGMENTS`. Electrical energy uses selected total
electrical power and duration, with reserve withheld once and auxiliary power
included once. Captured motor loss and declared auxiliary heat drive one
chronological lumped thermal evaluation. Electrical energy is independent of
captured heat, and captured heat is not an additional electrical charge. There
is no temperature feedback into point models. Exceeding declared energy remains
an experimental screen result and does not establish aircraft feasibility.

If a point residual is unmet, the outer status can still be
`COMPUTED_EXPERIMENTAL`, with mission state `STOPPED_AT_UNMET_SEGMENT`. The
mission retains exactly the reached chronological point prefix including that
segment. Later points and the thermal evaluator do not run.
`outputs.mission.energy`, `outputs.mission.thermal`, and their mission units are
null; `transfers.mission` is empty. The ledger outputs remain present, and
`transfers.mass_cg` covers every declared segment, including unreached segments.
There are no flat root energy or thermal outputs.

Model preflight failures return HTTP 200 with `GRAPH_INVALID`. Ordinary
execution errors or invalid returned child contracts return HTTP 200 with
`EXECUTION_FAILED` and empty outputs, units, stages, and transfers. HTTP status
200 alone does not establish a completed computation; inspect the model status,
diagnostics, and nested mission state. Parser, authentication, and transport
errors use their existing HTTP error statuses.

When the actual V100 result contains `request_sha256`, the adapter sets
`input_sha256` to that same value and computes `evaluation_sha256` over the
returned result including `input_sha256`, before adding `evaluation_sha256`
itself. Invalid requests without an actual request digest receive neither added
hash. These are request/result provenance hashes, not proof of physics or runtime
identity. Retained child result digests are opaque: absent raw child envelopes
are not reconstructed or claimed to have been independently authenticated.

Evidence remains `unverified`; physical validation, numerical qualification, and
runtime identity remain `NOT_ESTABLISHED`. `feasibility` and `aircraft_status`
remain null. Residuals, declared motor limits, energy, and thermal screens do not
establish flight trim, continuous ratings, thermal adequacy, battery or ESC
qualification, installed-system qualification, or production readiness.

## Canonical paths and trailing slashes

Use the exact paths in the table. The dedicated POST body middleware recognizes
the evaluate path with trailing slashes, matching the accepted HTTP wrapper.
In local mode, a trailing slash normally produces a 307 redirect to the canonical
route. An already oversized declared body can return 413 before that redirect.
If an understated length permits the 307, resending the body to the canonical
route still returns 413 when actual received bytes exceed the bound.

Hosted authorization allowlists only the two exact canonical paths. A trailing
slash or neighboring path receives 403 after authentication, before the body
middleware or router redirect. Missing or invalid credentials are handled by
the existing authentication layer first. This preserves the accepted V98 route
and authentication ordering; it does not add a broader namespace allowlist.
