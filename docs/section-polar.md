# Experimental section polar lookup

This is a local engineering request proposal. It adds a standalone, offline
lookup capability, with no API, UI or existing solver integration. It performs
no nonlinear BEMT or rotor solution and establishes no physical validity.

Import `evaluate_section_polar` and `section_polar_catalog` from
`physimesh.drone.section_polar`. The catalog returns fresh metadata without
executing a lookup. Requests have exactly `evaluation`, `polar`, `query`;
`evaluation` is `section_polar_lookup_experimental`. Response schema is
`section_polar_lookup_v1`.

All source identity, source classification, uncertainty and Mach applicability
are unverified caller declarations. Nothing fetches, verifies or hashes a source.
Changing query Mach within the declared interval leaves coefficients unchanged.
The interval is caller applicability scope, never measured coverage. Reynolds
numbers are explicit samples; continuous experimental coverage is not inferred.

Full contract, limits, units, formulas and status matrix are available in the
catalog. Tests use invented synthetic fixtures, never copied reference data.

## Exact request

`polar` contains exactly `airfoil_id`, `source`, `source_kind`,
`uncertainty_status`, `sampled_mach_number`, `declared_mach_interval`, and
`reynolds_tables`. Text fields must be nonblank builtin strings with at most
2000 characters, except `airfoil_id` has a 128-character limit. `source_kind`
is one of `measured`, `digitized_measurement`, `computed`, `synthetic`.
These labels do not rank evidence or confer validation.

`sampled_mach_number` is finite and nonnegative. The declared interval is a
builtin list of two finite nonnegative ordered bounds containing that sample.
It does not create coefficient dependence on Mach or measured Mach coverage.

There are 1..8 ordered tables. Each has exactly `reynolds_number` and `rows`.
Reynolds numbers are positive finite normal numbers, strictly increasing.
Each table has 2..256 rows with exactly `alpha_rad`, `cl`, `cd`. Alpha is
strictly increasing within [-pi, pi]. Alpha and lift accept signed finite normal
numbers and signed zero; drag accepts finite normal nonnegative numbers or zero.
Every table has the same alpha grid: exact numeric values, builtin types and
zero signs must agree (`full_exact`). Local angle bounds are a data restriction,
not an assertion that flow is physically valid throughout that range.

`query` contains exactly `alpha_rad`, `reynolds_number`, `mach_number`, with
the same respective numeric bounds. Numeric fields require builtin int/float;
bools and subclasses are rejected. A single Reynolds table accepts only exact
numeric equality with its sample; no tolerance or artificial interval is added.

## Interpolation and units

For a bracketed alpha, let `a = (alpha-alpha_lo)/(alpha_hi-alpha_lo)`.
For bracketed Reynolds samples, let
`r = log(Re/Re_lo)/log(Re_hi/Re_lo)`. Each coefficient is interpolated linearly
in alpha within each selected table, then linearly with weight `r` between tables.
There is no extrapolation, endpoint clamping or coefficient correction.

The logarithmic distance from `lo` to each `value` uses
`log1p((value-lo)/lo)` if that fraction is finite and positive; otherwise it uses
`log(value)-log(lo)`. Numerator and denominator choose their branches independently.
This avoids forming an unsafe direct Reynolds ratio. Adjacent or extreme values
can still be refused; full binary64 dynamic range is not promised.

At an exact knot, indices are `[i,i]` and its axis weight is zero. At an exact
alpha/Re knot the original coefficient type and value are retained, including
integers greater than 2**53 and signed zeros. Interpolation uses binary64 only
when needed. Strict interior queries require weights strictly between zero and
one; an interior weight rounding to an endpoint causes `EXECUTION_FAILED`.

`source_rows` contains exactly 1, 2 or 4 unique selected corners. Each row has
`table_index`, `row_index`, `reynolds_number`, `alpha_rad`, `cl`, `cd`, `weight`.
Corner weights are products of the applicable axis weights or complements;
a collapsed axis contributes a factor of one. No duplicate or zero-weight
corner is manufactured. Indices are zero based.

Alpha uses radians. Reynolds number, Mach number, coefficients, indices and
weights are dimensionless (`1`); labels and source text are nonphysical metadata.
Unit dictionaries describe every computed field and every source-row field.
Computed outputs contain exactly `query`, `sampled_mach_number`,
`declared_mach_interval`, `mach_dependence`, `cl`, `cd`, `interpolation`.
The query is copied with its native builtin numeric types.

Weighted contributions and results must be finite normal numbers or zero.
A nonzero contribution becoming zero or subnormal causes refusal. Opposite
rounded contributions may cancel to zero; zero does not establish aerodynamic
zero lift or physical validity. This numerical policy is deliberately limited.

## Status and data binding

| Status | Meaning | Hashes |
| --- | --- | --- |
| `RESEARCH_ONLY` | Fresh catalog metadata; no lookup | Null |
| `MODEL_INAPPLICABLE` | Invalid JSON, schema, table or numeric input | Null |
| `SOLVER_UNSUPPORTED` | Strict bounded exact root with another evaluation string | Null |
| `OUT_OF_POLAR_DOMAIN` | Valid query outside alpha, sampled Re extent or declared Mach scope | Both |
| `COMPUTED_EXPERIMENTAL` | Checked interpolation completed | Both |
| `EXECUTION_FAILED` | Sanitized ordinary execution/export failure | When available |

Every table is validated before coverage checks. Outside-domain responses list
all failed axes in alpha/Re/Mach order, have empty outputs and units, and mark
`diagnostics_complete` false. They contain no coefficients or weights. The full
request, including the query, is bound by `request_sha256` even when outputs are
empty. The response digest binds the full response except `evaluation_sha256`
itself. Encoding is sorted-key compact JSON, UTF8, `ensure_ascii=False`,
`allow_nan=False`, hashed with SHA256. These hashes establish data binding only.
No `source_sha256` or source-authenticity assertion is created.

Strict JSON walking precedes copying and hashing. Only exact builtin JSON types
are accepted; floats must be finite, strings valid UTF8, integers at most 1023
bits. Each container has at most 256 entries and each string at most 2000
characters. Input budget is 32768 nodes including dictionary keys, depth 10;
output budget is 8192 nodes, depth 12. Root depth is one. Aliases count once per
occurrence; cycles exceed depth. All response data is walked before and after
sealing. Ordinary exception details are sanitized; `BaseException` propagates.

Physical validation, numerical qualification and runtime identity remain
`NOT_ESTABLISHED`; aircraft status and feasibility remain null. No stall,
360-degree extension, compressibility, rotation, hysteresis or independently
established Mach/Re coverage is inferred.

## Reference context

The current [AeroDyn input documentation](https://openfast.readthedocs.io/en/main/source/user/aerodyn/input.html)
describes linear interpolation between Reynolds tables using logarithmic Reynolds
number for `AFTabMod=2`, and a choice of alpha interpolation. This local lookup
uses linear alpha interpolation. It is not an AeroDyn file reader or a claim of
full AeroDyn equivalence.

[Drela's QPROP formulation](https://web.mit.edu/drela/Public/web/qprop/qprop_theory.pdf)
provides context for section coefficients within a broader propeller formulation.
This module does not implement that rotor solution. Neither reference grants
physical validation or authorizes this local contract. No reference code or data
was copied, no external dataset is bundled, and no pinned-version comparison is
claimed. Tests use synthetic fixtures and independent numeric checks.

If response sealing repeatedly fails, the evaluator returns a fresh, bounded
`EXECUTION_FAILED` response with both hashes null. A digest that could not be
sealed is not presented as a completed binding. The tests inject ordinary
lookup, copying and hash failures, and check propagation of `BaseException`.
Snapshot-copy failure is classified as `MODEL_INAPPLICABLE` before acceptance.
Independent SHA256 reconstruction and 95-digit Decimal interpolation checks are
numerical verification only; they establish no physical qualification.
