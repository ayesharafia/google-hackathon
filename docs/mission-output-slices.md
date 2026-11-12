# Internal mission output slice validators

This local extraction is a prerequisite for actual-ledger integration with
V97 mission validation on accepted V98. No ledger wrapper is implemented yet.

The private helpers validate actual retained numeric outputs and their units
against the declared child request:

- `_point_output_values(outputs, units, request)` validates the selected solve
  point, motor rows, DC values, allocated heat, power totals, and unit bindings.
  It returns isolated motor rows and the selected candidate. An actual unmet
  point retains its accepted `None` power result.
- `_heat_output_values(outputs, units, request)` validates thermal output keys,
  actual types, integer indices, units, chronology, totals, and reconstruction
  of the governing thermal equations. It returns isolated thermal outputs.

These helpers accept slices directly. They neither fabricate raw envelopes nor
invoke extra evaluators. Thermal reconstruction uses `th.integrate_segment`
as arithmetic validation of the declared request.

The caller still owns validation of the real envelope, request and result
hashes, stages, transfers, provenance, and the actual child requests used to
produce the retained results. Slice acceptance alone establishes none of those
properties and does not make the helpers provenance validators.

`_point_outputs` retains its real-envelope guard, delegates value validation,
and retains the unmet-point transfer and minimum-stage checks.
`_validated_heat` first applies `em._validated_thermal` to the actual raw
result, delegates to `_heat_output_values`, and returns a deep copy of that
raw result. Existing full validators retain their provenance responsibilities.

The extraction preserves behavior for valid results. Strict binding of the
full solve-unit structure and explicit integer-index checks strengthen
rejection of forged types, including booleans that compare equal to numeric
indices. This is validator strengthening, not a claim of semantic equivalence
for every malformed input or a no-op change.

Existing V97 and V98 public schemas and qualification claims remain unchanged.
This prerequisite adds no physics and establishes no physical validation,
production readiness, or novelty claim.

The affected test count is 152: 14 new slice tests, 86 mission tests, and
52 HTTP tests. The completed full-suite receipt reports 4,806 passed,
5 skipped, and 359 subtests in 113.24 seconds.

A separate actual 50-case comparison against accepted V97/V98 passed for
the entire mission response: 48 residual-met grid cases and two unmet-prefix
cases. This bounds the equality evidence to finite valid behavior; it does
not establish equivalence for malformed inputs.

These results establish neither physical validation nor a CI-green claim.
Independent acceptance remains pending.
