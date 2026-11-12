# Tabulated hover thrust target result validation

`physimesh.drone.tabulated_hover_thrust_target_validation.validate_tabulated_hover_thrust_target_result(actual, request)` validates a full actual V108 inverse response against its original request. It returns `None` on a valid contract and raises `ValueError` on invalid data. It neither mutates its arguments nor invokes inverse, forward, hover-core or air models. It does not reconstruct forward envelopes, construct model dataclasses, convert aliases or invoke caller copy hooks.

The original request passes strict bounded builtin JSON admission, exact root fields and evaluation dispatch, followed by the accepted V108 pure `_preflight` checks. Physical-domain admission remains the forward core's responsibility. Trusted accepted catalog metadata is captured privately at module import; runtime validation only reads it. The optional `tabulated_hover_thrust_target_validation_catalog()` returns a fresh description of the validation boundary, including its limitations.

The actual response has its own strict JSON walk: root depth 1, depth at most 16, at most 65,536 nodes including keys, at most 2,048 items per container, at most 2,000 characters per string, at most 1,023 bits per integer, finite floats and valid UTF-8. Aliased occurrences consume the same budget as repeated JSON text. Cycles, foreign containers and foreign scalars fail without invoking their conversion or copy methods. Exact root keys, builtin types, status, qualifications, limitations, limits, reasons and units follow the accepted contract. Metadata equality distinguishes booleans, integers and floats.

Accepted requests bind `request_sha256` to `sha256_record(request)`. Accepted outcomes other than `MODEL_INAPPLICABLE` bind `evaluation_sha256` to the entire actual inverse response with only that field omitted. Hashes use the accepted sorted compact UTF-8 JSON encoding. Data hashes establish no runtime identity, execution attestation or physical qualification.

## Success and retained provenance

Success requires exact scalar outputs, actual selected forward request and full actual selected forward response. The selected request equals the original template with only the actual trial speed injected, including numeric types. The accepted V106 `_validate_child` must return `True` for that full response; its V105 output helper checks the actual output slice and accepted governing arithmetic without a solver call. Forward result units cover **only `outputs.actual_forward_result.outputs`**, not the forward response envelope. Forward request units have their separate catalog scope.

Every trace entry has exactly the five accepted fields. All trial request digests are independently recomputed from the original template and actual trial speed. The selected trace's `full_actual_result_sha256` is independently checked against the entire retained actual selected response, including that response's evaluation digest.

**Intermediate full-result digests are producer-reported provenance only.** V108 retains no intermediate full response payloads. Their digests receive strict lowercase 64-character hexadecimal format checks, but cannot be independently content-verified. A well-formed replacement intermediate digest passes after the outer response is rehashed; a malformed digest fails. A well-formed incorrect selected result digest fails. No intermediate forward envelope is fabricated to bridge this missing evidence.

Scalar trace replay checks both actual endpoints, low then high, before choosing the earliest tolerable endpoint. Endpoint success ends after exactly two trials; the selected low endpoint need not be the last trace entry. Observed high thrust must exceed low thrust, except the accepted all-zero-angle, zero-thrust case. Otherwise the target must lie strictly inside the observed endpoint thrust range. Each later speed must equal `lo + (hi - lo) / 2` with the exact arithmetic type, be finite and strictly interior, and have thrust within the closed observed range. The first tolerable trial must be last and selected. Other trials narrow the bracket by residual sign while retaining the strict target bracket. Count, output evaluations and trace length agree and stay within the caller's budget.

All trace thrusts bind to the validated selected `thrust_coefficient` using the accepted SI operation order:

```python
area = _mul(pi, _mul(R, R))
tip = _mul(float(Omega), R)
scale = _mul(_mul(rho, area), _mul(tip, tip))
T = _mul(scale, CT)
```

`R` and `rho` are the accepted float conversions of original template values. This avoids different rounding from scaling selected thrust by a speed ratio. The coefficient is fixed by the accepted geometry model, not established physical truth. Residuals equal actual float thrust minus the original target; finite zero and subnormal residuals remain allowed. Positive controls must be normal; thrust must be a builtin float that is normal positive or zero. Selected achieved thrust, residual and tolerance bind exactly and satisfy the caller's absolute tolerance.

## Atomic failures

Failures discard all history: `outputs` and `output_units` are empty dictionaries, `trace` is an empty list and `diagnostics_complete` is `False`. Only their envelope, exact reason, status, request/evaluation digest rules and count bounds are validated. No failure trace is inferred and no model is rerun. A coherently rehashed history-free envelope within these bounds can validate; this is explicitly **not execution attestation**.

| Admitted status | Exact reason | Evaluation count |
| --- | --- | --- |
| `TARGET_NOT_BRACKETED` | `Target is outside the observed endpoint thrust range.` | 2 |
| `ITERATION_LIMIT` | `Actual forward evaluation budget exhausted.` | budget |
| `NUMERICAL_LIMIT` | `No finite representable strict interior midpoint.` | 2 through budget − 1 |
| `MODEL_INAPPLICABLE` | `Actual forward core refused the physical or numerical domain.` | 1 through budget |
| `EXECUTION_FAILED` | `Actual forward target execution failed.` | 0 through budget |

All admitted failure counts are builtin integers. Domain refusal keeps the accepted request digest and has no evaluation digest; other admitted failures carry both bindings.

A request that fails strict JSON, exact shape/types or supported-evaluation preflight admits only `MODEL_INAPPLICABLE`, reason `Invalid bounded target request.`, count zero and both hashes null. A strict JSON root with the exact fields and another outer evaluation string admits only `SOLVER_UNSUPPORTED`, reason `Unsupported evaluation.`, count zero and both hashes null. As in V108, unsupported dispatch precedes rotor/control preflight.

V108 also catches ordinary snapshot exceptions as `EXECUTION_FAILED` with reason `Request snapshot failed.`, and can report a null request digest if hashing fails before accepted execution preparation. These are observed infrastructure/fault paths, not outcomes justified by deterministic admission of bounded exact builtin JSON. This validator does not accept those as alternatives to a reproducible invalid, unsupported or admitted request branch: admitted requests require their computable request digest, while invalid and unsupported requests require their corresponding zero-count atomic response. Unexpected ordinary exceptions and `BaseException` from pure dependencies propagate; they are not broadly masked into data rejection or simulated execution failures.

This boundary adds no physical or air model, API, graph, assembly, trim, mission, accuracy, novelty or publication qualification. Accepted V108 evaluation and hash behavior remain unchanged.
