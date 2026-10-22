# Pack-input validation boundary audit

22 October 2026. AUDIT-002, internal source review by Codex, not independent
validation or a runtime defect demonstration. No source values, assertions or
model policies changed. Source hashes are in the task's retained evidence.

## Finding

The helper's `consistent` result is a check of selected aggregate battery mass
and energy declarations. It cannot replace a complete mass-ledger check.
The inspected local capacity path does perform that separate check before
using the pack budget. Negative selected masses cancelling against positive
masses therefore do not, by source inspection, establish a route to local
capacity acceptance. No such runtime bypass was demonstrated.

| Caller | Observed ownership and outcome |
|---|---|
| [pack_consistency](../../src/physimesh/drone/screening_scope.py#L14) | Selects named energy items and checks summed mass; does not validate every mass/CG before summation. Raw helper callers must not interpret this as full ledger validity. Extraction errors return structured inputs_incomplete. |
| [inspect_inputs](../../src/physimesh/drone/authoring.py#L46) → [mass_items](../../src/physimesh/drone/authoring.py#L11) / [summarize](../../src/physimesh/drone/mass.py#L50) | Rejects malformed records, duplicate names and boolean item masses in mass_items; summarize reports negative/nonfinite masses, incomplete categories and missing/invalid CG. It returns separate mass and pack sections. A numerically consistent pack can coexist with an invalid mass section; neither is an overall pass. |
| [GET project inspection](../../src/physimesh/api/projects.py#L159) | Calls inspect_inputs, supplied-point readiness and map-based hover_readiness. Extraction exceptions go through the API operation boundary. No capacity is calculated here. |
| [prepare_hover](../../src/physimesh/drone/trim.py#L118) | candidate_mass must be complete before pack_consistency is called. Pack must then be consistent; fixed pack and constant bus are separate requirements. This guards the inspected local capacity path. |
| [POST screening](../../src/physimesh/api/screening.py#L40) | Calls project_from_mapping and readiness first; blockers return before the pack budget is accepted. It also constructs a mass summary for capacity_from_cases. No negative-mass bypass follows merely from aggregate pack consistency. |
| [Engineering Readiness](../../web/js/engineering-readiness.js) and [saved input details](../../web/js/input-editors.js) | New readiness panel separately displays mass and battery states and disclaims physical acceptance. Existing details also show Mass incomplete and Pack status separately. No positive aggregate headline is inferred by the new panel. |

## Remaining source-level robustness question

The local authoring path explicitly rejects boolean item masses. The broader
[readiness mass loop](../../src/physimesh/drone/models.py#L216) constructs
MassItem records and delegates to summarize, whose finite/nonnegative check
does not itself explicitly reject booleans. pack_consistency checks the summed
float rather than individual raw types. This suggests inconsistent raw-input
type handling between caller paths, not a demonstrated accepted aircraft result.
The entire supplied-point request has further requirements and was not executed
by this audit. A future bounded hardening proposal should reproduce that exact
path before claiming reachability/severity, then reuse one explicit per-item
numeric policy without changing numerical tolerances or physics acceptance.

Severity: no local-capacity bypass established; defensive input-consistency
candidate for the broader screening boundary. Do not market it as a security
exploit or claim the helper alone proves a flight/energy result.

## Existing evidence and limitations

Read [test_authoring.py](../../tests/drone/test_authoring.py) covering duplicate
names/boolean masses and pack consistency, plus the existing screening/mass/trim
source. No application test, model run, network request or mutation was executed
for AUDIT-002. Tests run for the separately approved UI feature have their own
scope and receipts. No external issue/contact, new source-data ingestion or
scientific approval follows from this audit.

The main product priority remains the owner's newly approved guided source
binding. This audit is complete as source investigation; any raw-input behavior
change requires a separate concrete design and targeted reproduction.
