# Pure chronological DC energy result guard (V120)

`validate_tabulated_target_dc_energy_result(actual, request)` returns `None` for
a full computed V118 contract and raises `ValueError` for invalid data. This is
deliberately **success-only**: every status other than `COMPUTED_EXPERIMENTAL`
is rejected, including legitimate V118 failures. Invalid or unsupported
requests also raise `ValueError`; no synthetic failure envelope is constructed.
This prerequisite for a future energy/temperature bridge is not a drop-in
validator for the whole V118 domain. Future bridge failure policy is separate.

The guard bounds both full builtin JSON trees before preflight, equality or
hashing, runs actual V118 pure preflight, and independently bounds each point
before passing its full retained result and actual power request to pure V117.
It checks closed shapes, native types, catalog metadata and units, full hashes,
exact counts, chronological duration prefixes, nine W-to-J products, prefix
energy sums, J/Wh totals, limit flags, stages and ordered scalar transfers.
Units describe only the nested actual point outputs. Durations retain their
request types and are bound by the root request hash.

Catalog metadata and the canonical power fields are captured privately at
import time. Validation executes no models, evaluator, thermal integrator,
catalog call, copying hook or mutation. Unexpected pure dependency exceptions,
including `RuntimeError` and `BaseException`, propagate. Arithmetic
`OverflowError` and `ZeroDivisionError` become `ValueError`.

The tests capture actual two- and eight-segment V118 results before blocking
models and catalogs. They cover repaired energy summaries, native types,
metadata, counts, closed shapes, provenance fields, full nested point guards,
actual noncomputed results, preflight limits, strict JSON resources and foreign
hooks, private import snapshots, and pure dependency exception behavior.

Consistent changes to durations or declared limits can validate when all
affected data and hashes agree. Hashes bind JSON content, not execution history.
V117's existing boundary is preserved: selected forward results are checked in
full; unretained trace result hashes have lowercase SHA256 format checks only.
Actual motor results have no evaluation hash; their full data is bound by the
point's motor stage digest. No intermediate result envelopes are fabricated.
There is no runtime, temperature, mission, physical or publication qualification.
