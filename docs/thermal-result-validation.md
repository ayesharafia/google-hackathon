# Pure thermal result validation

`physimesh.drone.thermal_result_validation.validate_thermal_result(actual, request)`
returns `None` for a consistent full actual `thermal.screen_thermal` computed
result and raises `ValueError` for a contract violation. This is intentionally
success-only: `MODEL_INAPPLICABLE` and `SOLVER_UNSUPPORTED` are outside admission.
No failure envelope is fabricated or accepted.
This is a prerequisite for a future energy/temperature bridge, not a blanket
replacement for the thermal evaluator or a guard for its entire result domain.
A future caller needs a separately designed policy for noncomputed results.

The guard bounds strict builtin JSON before structural checks or equality.
Requests allow 8192 nodes and depth 8; results allow 32768 nodes and depth 10.
Both allow 2048 items per container, 1023-bit integers and 2000-character valid
UTF-8 strings; floats must be finite. Root depth is one and keys count as nodes.
Request number conversion and checked operations preserve the actual thermal
admission, including finite subnormal inputs where the arithmetic permits them.
These JSON resource and builtin-type bounds deliberately narrow the evaluator's
otherwise unbounded request/result contract. They do not impose a global
normal-number gate: for example, the minimum positive subnormal Biot declaration
is accepted when the actual arithmetic succeeds. Subnormal derived values and
underflow are refused at the accepted checked operations.

Both complete JSON walks finish before envelope equality or structural request
admission; the actual result is walked first, then the request. Repeated aliases
consume their full serialized occurrence count. Cycles exceed the depth bound.
Foreign objects and builtin subclasses are rejected without invoking their
iteration, equality, conversion, encoding or copying hooks. No digest is computed.

Private import-time metadata uses thermal's model ID and limitations; units and
sources are literal copies of the accepted source contract. Root fields,
metadata, empty reasons, units, every row and every summary are exact, including
native scalar types. Thermal has no request or result digests; added fields fail.
The trusted source contract is the existing
[`thermal.py`](../src/physimesh/drone/thermal.py) implementation:
`screen_thermal` defines the envelope, request fields and units;
`integrate_segment` and the checked scalar helpers define arithmetic order.
The private input/output JSON limits belong to this guard; thermal exposes no
runtime catalog for them. The retained source URL and scope are metadata from
that implementation, not a freshly retrieved or independently verified citation.

The arithmetic binding checks the accepted binary64 ODE operation order, then
advances from each fully validated actual endpoint. It checks chronological
elapsed time, maximum temperature, energy sums and residual association.
Each row binds duration, elapsed time, start/end/ambient temperatures, input
energy, storage, convection and residual; its index is a builtin integer and
all remaining numeric outputs are builtin floats, even for integer requests.
The binding covers H=0, equilibrium, the small-x polynomial below `1e-4`, the
ordinary positive-H expression, exponential decay and checked final temperature.
Totals use `math.fsum` for input, storage and convection, then the accepted
left-associated total residual. No conservation-only repair can replace the
governing temperature relation.
It calls neither the screener nor integrator, and uses no runtime catalog,
hashing, copying hooks, mutation or fabricated result envelope. Expected
arithmetic overflow and zero division become `ValueError`; unexpected pure
dependency exceptions, including `RuntimeError` and `BaseException`, propagate.

Repeating these primitive operations binds the accepted binary64 contract; it
is not an independent numerical oracle or an independent thermal ODE
qualification. No physical qualification, aircraft assessment or validation
upgrade follows from admission. Existing thermal and mission behavior is
unchanged; this module implements no energy/temperature bridge.

The focused tests capture actual H=0, ordinary positive-H and small-x results
before blocking the screener and integrator. Expanded cases block loaded model,
solver, runtime catalog, compute, copy and hash entry points. They verify `None`
and unchanged actual/request JSON, including native integer request declarations
and float outputs. Coverage includes:

- A full 128-segment alternating heat/conductance/ambient history with cooling,
  negative convection, chronological continuity and elapsed time.
- H=0 and positive-H equilibrium, cooling, and `x = 1e-4` with conductance `0.05`
  and its immediate `math.nextafter` neighbors at capacity 500 and duration 1.
- Coherent forged endpoints raised by one kelvin, with storage, convection,
  residuals, all energy totals, maximum and final temperature repaired. The
  three-row forgery also repairs every subsequent start for continuity; both
  forgeries still fail the governing ODE binding.
- Every numeric row and summary field, exact native types, boolean rejection,
  metadata, closed root/output/row/unit/source structures and absent digest fields.
- Actual unsupported-evaluation and invalid-domain refusals, all deliberately
  rejected by this success-only boundary.
- Minimum positive subnormal Biot admission and private import-time metadata
  independence after public thermal metadata mutation.
- Helper-only exact node/depth/container/string/integer resource boundaries,
  key and alias occurrence counting, malformed JSON, cycles, invalid UTF-8 and
  foreign subclasses rejected before equality or structural admission.
- Ordinary pure `ValueError`, unexpected `RuntimeError` and `KeyboardInterrupt`
  propagation, including direct math calls, and the scoped conversion of
  expected arithmetic overflow/zero division to `ValueError`.

Resource helper probes are not fabricated valid thermal envelopes. These tests
exercise arithmetic contract consistency and refusal behavior; they provide no
independent physical oracle or claim of complete numerical qualification.
