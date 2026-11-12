# Solved DC electrothermal HTTP API (experimental)

Authenticated routes:

- `GET /api/drone/solved-dc-electrothermal/catalog`
- `POST /api/drone/solved-dc-electrothermal/evaluate`

Both routes inherit the existing drone namespace authentication. Local bearer
and browser-session rules and hosted identity checks remain in force. Hosted
access adds only the two exact paths to the existing protected allowlist;
middleware order and authentication policy are unchanged. There is no bypass.

The catalog describes the actual evaluator, exact request fields, inherited
schema references, resource limits, residual-stop behavior, and qualifications.
It reports `evidence_level="unverified"`; physical validation, numerical
qualification, and runtime identity are `"NOT_ESTABLISHED"`. Feasibility and
aircraft status are null.

## Request and execution

The [accepted scientific contract](solved-dc-electrothermal.md) defines the full
request, arithmetic support, stage validation, and limitations. The exact root
fields are `evaluation`, `usable_energy_j`, `reserve_fraction`, `thermal_body`,
and `segments`. Evaluation is
`"solved_dc_electrothermal_mission_experimental"`.

Each segment has exactly `id`, `duration_s`, `point`, and `thermal`. The thermal
body, segment thermal declarations, and accepted V96 DC point schema retain
their scientific validation. Points supply complete solve, ordered motor,
motor-loss capture, and auxiliary declarations; the API adds no heat override.

After parsing, the API calls the actual
`physimesh.drone.solved_dc_electrothermal.evaluate_solved_dc_electrothermal`
once through the threadpool. Each reached segment evaluates its actual DC point
once. Motor loads use the selected solve speed and validated shaft torque.
Electrical energy uses total electrical power times duration; heat uses captured
motor loss plus allocated auxiliary heat. Auxiliary accounting occurs once,
reserve is withheld once, and captured heat is no additional electrical charge.

All-met execution runs one chronological lumped thermal evaluation, without
temperature feedback to point models. The first unmet residual stops execution
with the reached prefix, including the unmet segment, and mission state
`STOPPED_AT_UNMET_SEGMENT`. Energy, thermal, and their units are null; mission
transfers are empty. This remains `COMPUTED_EXPERIMENTAL` at HTTP 200.

## Parsing, resource limits, and responses

The HTTP byte budget is **131072 bytes**, separate from JSON resource limits.
The API uses the mission-specific JSON walk: root depth 1, maximum depth 12,
and a global 65536-value budget counting dictionary keys and values. Containers
have at most 256 entries, strings 2000 characters, and integers 1023 bits.

Strict JSON parsing rejects duplicate keys, NaN/Infinity, other nonfinite
numbers, invalid UTF-8, malformed JSON, and nonobject roots. Parsing/resource
failures return HTTP 422 with only
`{"detail":"Invalid solved DC electrothermal request."}`.

There are 1–16 segments. The global work bound is
`sum(segment_annuli * (segment_max_evaluations + 1)) <= 32768`.
Child budgets remain unchanged: per-point depth 10 and 49152 JSON values,
solver 32768 values, motor 4096 values, at most 15 rotors and 512 annuli per
rotor, and integer `max_evaluations` from 2 through 64. The per-point work
bound also remains `point_annuli * (max_evaluations + 1) <= 32768`.

Scientific schema failures return the actual `GRAPH_INVALID` result at HTTP
200, before internal model execution. Runtime exceptions contained by the
scientific evaluator return atomic `EXECUTION_FAILED` at HTTP 200 with generic
reasons, no private exception details, and empty stages, transfers, outputs,
and output units. The HTTP adapter does not replace these evaluator contracts.

When the result contains `request_sha256`, the API adds `input_sha256` equal to
that digest. It then computes `evaluation_sha256` using `sha256_record` on the
entire result including `input_sha256`, before adding `evaluation_sha256`.
The evaluation digest therefore excludes itself. These hashes record provenance,
not physical validation or runtime identity.

## Body limiting and routing

The ASGI limiter scopes only POST evaluate, including trailing slashes. Invalid
declared Content-Length returns 400; negative or oversized declarations return
413. Actual received bytes are counted across request messages, including
chunked requests without Content-Length and requests understating their size.
131073 consumed bytes return 413 before evaluator execution. A valid mission
padded with whitespace to exactly 131072 bytes can return HTTP 200; whitespace
alone at that boundary reaches parsing and returns 422.

A local trailing-slash request can return 307 before consuming an understated
body. Its Location is the canonical evaluate URL, where resending the same
oversized body returns 413. An oversized declaration still returns 413 with a
local trailing slash. Hosted trailing-slash requests remain 403 under the exact
allowlist, before body limiting. These behaviors preserve authentication order.

## Scope and verification

This API does not deploy anything or establish physical validation, aircraft
feasibility, production readiness, thermal adequacy, or continuous motor ratings.
The existing scientific implementation is unchanged.

Local software checks completed: 52 HTTP tests across local and hosted modes
passed in 3.75 s; the full drone suite had 4792 passed, 5 skipped, and 359
subtests in 67.44 s. Ruff passed for the Python adapter, application wiring,
and application test file. These checks do not establish independent acceptance,
which remains pending; physical validation remains `NOT_ESTABLISHED`.
