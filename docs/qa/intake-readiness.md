# Declaration-only aircraft intake checklist (A06)

This offline helper inventories supplied metadata against the client data request
at `docs/client/aircraft-data-request.md`. It is not an evaluator, source verifier,
model acceptance decision, authenticated approval, payload estimate or flight gate.
No production source or equations are changed.

Run from the checkout with development dependencies installed:

```bash
python scripts/qa/intake_readiness.py --input tests/fixtures/intake_readiness/complete.json --output /tmp/intake-complete-new.json
python scripts/qa/intake_readiness.py --input tests/fixtures/intake_readiness/incomplete.json --output /tmp/intake-incomplete-new.json
pytest tests/test_intake_readiness.py
```

Outputs must be new files; an existing receipt is never replaced. Exit 0 means
only complete inventory declarations; exit 1 means declaration gaps; exit 2 is
sanitized input/output failure. Neither 0 nor any purpose-readiness result means
engineering acceptance. Output counts are intentionally sanitized; source data,
custom field names, contacts, tolerances and validation exception text are omitted.
The canonical packet digest binds the receipt to the exact supplied JSON values
(sorted-key compact UTF-8 JSON); it does not verify their truth or authenticate them.

Use JSON envelope `schema_version: intake_inventory_v1`, `project` containing the
existing `drone_manifest_v1` groups and `inventory` as shown in the fixtures.
Both fixtures are SYNTHETIC; their names, source tokens and values do not describe
an aircraft or a human approval. The complete fixture deliberately remains
incomplete for CFD/feasibility purposes. Never transplant its values into a client
design. Actual submission metadata must come from supplied source declarations.

The checklist covers geometry source/revision/units/frames/roles/transforms/context;
each rotor's raw source, map identity, conditions, coverage, units, uncertainty,
power basis, duty and rights; each mass item's mass/CG sources, uncertainty and
placement envelope; electrical source, capacity/energy and operating limits,
efficiency and auxiliaries; mission sources/cases/chronological segments/reserve;
and named engineer/independent approver with intended claim, comparison sources,
model envelope and owner-supplied tolerance/uncertainty policies.

Geometry revision, units, frames, component ID/role list and CAD transform bind to
the snapshot. Rotor IDs/map references and mass item names bind in supplied order.
Case/segment IDs, reserve convention and pack mode bind through the existing
`bound_mission` / `MissionDefinitionV1` contract (including case-condition hashes).
No new mission equations or chronological mission capability are implemented.

Null/blank/empty fields are `missing`; explicit `unknown` and `unsupported` tokens
remain visible as those states. Non-string source references and mismatches are
unsupported. Nested metadata must contain no unresolved child fields. Zero is a
present declaration, not a substituted physical default. Inventory completeness
only checks declared presence and these explicit bindings: it does not validate
raw datasets, sufficient rotor/installation coverage, numerical electrical limits,
structural allowables, tolerance suitability or provenance rights. The client data
request remains the full human review checklist; engineering owners must review
all detailed requirements before any claim. Named ownership is self-declared only.

Malformed or absent electrical inventory is reported against its electrical
fields. It does not invalidate an otherwise bound mission declaration: mission
contract validation and electrical metadata completeness are separate checks.

Existing `project_from_mapping` and `readiness` run separately for screening,
CFD and feasibility. Their blockers/warnings are reported as counts, not private
values; malformed nested structures receive a conservative unsupported result.
Readiness does not run screening/CFD or elevate scientific status.

Inputs are local regular JSON files (at most 1 MiB, depth 32 and 20,000 nodes).
Symlinks/devices, duplicate keys and nonfinite values are rejected. Source tokens
are opaque: referenced paths/URLs are never followed and no network is used.
Keep original sources in the approved private transfer channel; this helper does
not send, download, copy or authorize them. Retain each new receipt separately.
