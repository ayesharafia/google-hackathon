# Next safe task: raw pack-input validation boundary audit

Kind: audit. Zone: green. Source: DOC-002 E03/E07 and its caller-boundary note in
docs/validation/fixed-pack-energy-provenance.md.

User outcome: determine whether invalid individual battery mass records could
yield a misleading pack-consistent status in any public authoring/screening path.
This is an investigation, not permission to change a physical formula.

Trace screening_scope.pack_consistency, authoring.inspect_inputs/candidate_mass,
the actual API callers and rendering of mass/pack outcomes. Locate relevant
existing fixtures. Distinguish a directly callable low-level helper from a
guarded user-facing path. Record exact paths/lines and concrete reachable or
unreachable conditions; label inference and unknowns. No runtime behavior claim
without actual evidence, and no test/model execution unless the user asks.

Acceptance: write a short source-backed audit with the caller chain, individual
mass/selection validation ownership, structured-refusal behavior and severity
of any observed gap. Recommend one bounded correction only if warranted; do
not manufacture a bug. Record source hashes and evidence in state/worklog.
Keep formulas, input datasets, tolerances, approved specs and existing tests
unchanged. No dependencies, third-party contact, GitHub issue publication,
deployment or branch deletion. Implementation, if needed, is a later task.
