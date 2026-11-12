# Atmosphere and hover run records

From a source checkout, send one UTF-8 JSON request on standard input:

```sh
PYTHONPATH=src python -m physimesh.drone.atmosphere_hover_run < request.json
```

Use the explicit request schema in [the workflow documentation](atmosphere-hover-workflow.md).
The command reads stdin and writes one canonical JSON line to stdout. It does
not write files, contact remote services, or launch jobs. Exit status is 0 for
`COMPUTED_EXPERIMENTAL`, 1 for a logical schema refusal, component refusal, or
numerical failure, and 2 for a strict input parse error. Error records do not
echo rejected input. The Python API is `run_record(request)`; `main` also accepts
binary input and text output streams, such as `BytesIO` and `StringIO`.

Input is limited to 64 KiB (65536 bytes). Trailing JSON documents, duplicate keys
at any depth, a UTF-8 BOM, invalid UTF-8, NaN, Infinity, overflowing float
magnitudes (including `1e999`), and integer tokens longer than 1024 digits are
parse errors. Integer magnitude must also be finite as a binary float. Excessive
JSON recursion is a parse error. The workflow separately limits builtin finite
JSON input to 512 nodes (including dictionary keys), depth 8, strings of 2000
characters, and 512 items per container. Schema refusals remain exit 1. The hover
component permits at most 2048 annuli; that nominal record fits the wrapper's
100000-node, depth-16, 2048-items-per-container result serialization budget.

The wrapper snapshots finite builtin input before invoking the accepted workflow
with a separate deep copy. Arbitrary Python objects are neither copied nor
represented for export. Only requests admitted by the workflow, identified by
its `inputs_sha256`, receive explicit `request` and `request_sha256` fields.
The root hash must match the canonical pre-call request hash. Completed stages
must have canonical input and result hashes, expected stage order and bound model
IDs. A mismatch yields a closed `NUMERICAL_FAILED` record with no request export,
partial stages, transfers, or final outputs. A normal hover refusal, for example
`annuli: 0`, retains its completed atmosphere stage and admitted request while
leaving final outputs empty. Density linkage remains owned by the accepted
workflow; the wrapper introduces no component physics.

`result_sha256` identifies the copied workflow result. All hashes identify
canonical data, not validation, freshness, or an immutable record. Environment
metadata contains only Python, NumPy, and SciPy versions plus explicit
`NOT_ESTABLISHED` flags for runtime code identity, portability, and replay. It
contains no account or private provider metadata. Version strings and semantic
model IDs do not establish runtime code identity or replay.

Physical validation and numerical qualification remain `NOT_ESTABLISHED`, evidence
is `unverified`, and aircraft status and feasibility remain null. The reference
atmosphere is not local weather; experimental isolated-hover shaft power is not
electrical input power. This fixed workflow is not a general DAG, does not
establish M3 completion, and its focused tests do not constitute full CI.
