# V140 final private candidate audit, pending independent review and acceptance

The new standalone source is `tests/drone/stable_section_audit.py`. Run with the existing
`/downloads/physimesh-continuation-venv/bin/python`, `PYTHONDONTWRITEBYTECODE=1`, and `PYTHONPATH=src`:

```
python tests/drone/stable_section_audit.py --baseline --output docs/stable-section-baseline-audit.json
python tests/drone/stable_section_audit.py --output docs/stable-section-maximum-audit.json
```

Each fresh process had a 768 MiB address-space limit and 75 CPU-second limit.
Both runs used unchanged angle and residual tolerances of 1e-30 and an explicit budget of32.
Both returned COMPUTED_EXPERIMENTAL / EVALUATION_BUDGET_EXHAUSTED with32 actual evaluator
calls and32 independently guarded retained rows, including complete nested actual V133 results.
No child was fabricated and no solver/guard was replaced. A counting wrapper forwarded each actual request.

| Fixture | Solve response nodes including keys | Compact UTF8 bytes | Depth | Evaluator wall seconds | Process peak RSS KiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline, 2 tables × 3 rows | 41,607 | 548,661 | 15 | 0.7751 | 40,700 |
| Maximum admitted shape, 8 tables × 256 rows | 958,343 | 8,567,421 | 15 | 24.3871 | 87,308 |

The maximum table/row counts were read from the actual V132 catalog through V133,
then admitted by actual V133 input/output bounds and the full nested guards at all32 calls.
The declaration strings use the largest accepted character counts with escaped controls.
This establishes admission of the maximum table/row shape through the real child limits;
it does not establish that these numerical values maximize serialized bytes.
The JSON reports include request, actual V133 input/output, residual response, solve response,
and separate units-tree measurements. No full response file is retained by this audit.

The reference reports use113 values at each of80/120 digits, including the exact adjacent old
transition values 36.29755781272286 / 36.297557812722864 and the distinct new transition
36.97836504494759 / 36.978365044947594. At fixed emitted K=1, the observed maximum relative
differences were 1.805918928730635e-14 for deficit and 1.853916090295012e-11 for gamma.
For the separate prescribed emitted lift .125, the maximum relative residual difference was
1.454654098700712e-13. Both precisions agreed to the40 recorded significant digits.
These observations characterize these calculations; they are not libm bounds, geometry-error
bounds, solver-tolerance changes, confidence intervals, or physical qualification.

Open resource gaps: numeric token sizes have not been maximized; these are measured cases,
not exhaustive allocation proofs. Linux RSS is a process high-water mark including imports,
not incremental allocation. Streaming bounds do not eliminate the whole-string/byte temporaries
used by canonical hashing after those bounds. The proposed caps remain under independent review;
this audit does not establish API exposure readiness or candidate acceptance.

The final combined command used the specified existing Python, PYTHONDONTWRITEBYTECODE=1,
PYTHONPATH=src, pytest -q -p no:cacheprovider, and only these five test files:
test_stable_section_residual.py, test_stable_section_solve.py, test_section_load.py,
test_section_residual.py, and test_section_solve.py. Result:375 passed in8.39s,
comprising123 new checks plus252 existing checks. No solver criteria were loosened.

Native-bound tests reject oversize nodes, depth, containers, strings, integers, invalid UTF8,
circular data and serialized bytes before copying the untrusted request, hashing or calling a model.
Their small repeated-reference graphs do not allocate full output caps. Trusted refusal metadata
may be copied afterward. Separate tests check oversized output sanitization, accepted failure counts,
prior valid traces, persistent hash/export payload clearing, ordinary Exception sanitization and
BaseException propagation. They are boundary tests, not an allocation-cap proof.

Actual integrated NOT_BRACKETED and OOD cases pass. Exact-zero collapse and float stagnation
are covered by labeled synthetic unit-bisection cases; no actual integrated proof is claimed for them.
The fixed32-call maximum-shape probe and its measurements above were not rerun for this edge-test addition.
