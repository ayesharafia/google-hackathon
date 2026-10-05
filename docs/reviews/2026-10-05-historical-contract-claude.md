# Independent historical-contract follow-up

Candidate: `2cbbe3cc9a1b127cb6070db5bacd8ac6fa3d9a2d`. Packet SHA-256: `ea662919bd0ebc90828e0e5395ccc448aedce2d9a629c7f2d0a1dcb211b7e0f7`. User-authorized Claude textual review, no execution. Verdict: `PASS_BOUNDED_LOCAL`.

The earlier failed review is preserved in [its receipt](2026-10-05-historical-contract-claude-first.md). This follow-up accepts exact known-producer dispatch while retaining fail-closed limits. No physics equation or current V3 acceptance rule changed.

## Repository verification after the review

The producer-manifest hashes below were independently recomputed from exact Git blobs using the same canonical source-file manifest as `model_identity`.

| Commit | Source SHA-256 | Read policy |
|---|---|---|
| `07b9f192d55fd79c0cb209ece063bd029ce3d93e` | `5ea15ad323a3630b35d3b8d4428ea5b86b0ba4df80d78059cd0a7125c44a69b2` | Original first V2 |
| `0db6bb0e1d7de2aae564936fbc6e02019e9a737a` | `0940847e403ea7c9e42dada54e7cb7642ea06bdea43afd2623e4043971812310` | Corrected pre-minimum V2 |
| `3f9b01d4dfc6606fb26f279068a3711be7c6ccb5` | `b77a023e87cb59f9b2fcd6b295329303ceab8d591eb1bb2600e562093e4fe789` | Corrected pre-minimum V2 |
| `f0e4c62b2ae9a865ba0b11de1c20e5cbf31d8ed3` | `355f297c64dbe0d1df168ce01ad1443aa8b2128bf80af150f88339d7e8d1f845` | Strongest participating-bound policy |

Claude’s medium completeness concern is qualified by inspecting the actual f0e4c62 validator: f0e4c62 already requires every participating minimum and matches the strongest policy. It therefore does not need a weaker historical dispatch entry. Unknown working-tree fingerprints can still refuse old incomplete records. No claim is made that arbitrary edited-tree V2 results are readable. Known producer fingerprints are documentary identity, not authenticated attestations; historical reads do not requalify aircraft physics.

The source module docstring and contract wording have been corrected to state that unknown producers face the stronger rules. Negative test assertions now check specific refusal messages. UI checks are recorded separately; this packet did not contain the browser diff.

## Full reviewer response

**Verdict: PASS_BOUNDED_LOCAL.** No blocking defect in the four requested checks. One medium-severity completeness limit (fail-closed) is listed first.

## Checks

**Source dispatch: correct.** `LocalCapacityV2.historical_consistency` reads `specification.model.source_fingerprint_sha256` and requires an exact string match:
- A missing `model`, a non-dict `model`, a missing field, a non-string value, or any other digest all fall through to `LocalCapacityV3.check_headline(self)`, the full V3 rules.
- Calling the unbound method on a V2 instance is sound because the field sets are shared via `_CapacityRecord`.
- Production cannot emit V2. `studies.py` always writes and validates V3.

**No weaker fallback through missing fields: holds.** The policy is chosen only by the fingerprint, never by whether `participating_case_bounds` is present. An unknown source with a sequence and no bounds raises "every participating case". The `f*64` legacy-fixture test checks exactly this.

**Policy fidelity to the original validators: matches.**
- **07b9f19 branch:** line-for-line equivalent to the original `headline`. Only the messages changed, by dropping the "historical" prefix. There is no infeasible-certificate check and the limiting case must be in `required`, both as originally written.
- **0db6bb0/3f9b01d branch:** `check_headline(require_participating_bounds=False)` equals the 3f9b01d validator exactly. Against 0db6bb0 it adds a `source_domain_gaps` exclusion. That is unreachable for genuine 0db records because 0db's `Certificate` had no such field. Attainment still uses `participating_case_bounds` when sequence evidence exists, as in 0db.

**Exact-byte fixture read: holds.** The fixture's embedded fingerprint `5ea15ad3…` equals `FIRST_V2_SOURCE_SHA256`. The existing test verifies:
- the raw SHA-256,
- V2 acceptance,
- V3 refusal of the relabelled record,
- byte-identical export after restart,
- the PDF `X-Study-JSON-SHA256` header,
- that `capacity_from_snapshot` is not called.

**Negative regressions: adequate.**
- Current-source records relabelled as V2 are refused for these mutations: required-bound, required-outcome, attainment, and certificate-less infeasible.
- Unknown-source aggregates are refused when energy does not bind or when a limiting case is invented. I checked that the reduced-power mutation reaches the binding check with 360 J remaining, well above the 0.046 J tolerance.
- The parametrized pre-minimum test shows that a reduced participating bound is accepted under 0db/3f9 rules but refused under V3.

## Limits and findings

1. **Medium (fail-closed, not weakening): producer list may be incomplete.** You state the physics was unchanged at f0e4c62. But f0e4c62 changed `.py` files under `src/physimesh`, so its fingerprint differs from 3f9b01d's. If f0e4c62 (or any commit between 07b9f19 and 2abc801) emitted V2 records, those records get the strongest policy. Any genuine one without complete participating bounds would then be refused on read, even though 3f9 records with identical semantics are accepted. The same applies to records produced from a working tree with uncommitted or untracked `.py` edits, since `model_identity` hashes the working tree, not Git blobs. Before claiming that all retained V2 history is readable, confirm which commits emitted V2 and add f0e4c62's digest if needed.

2. **Low: the dispatch is self-declared, not authenticated.** `study_sha256` is recomputable by anyone who controls the record. Whoever can write artifacts and SQLite associations can tag a record with the 07b fingerprint to get the 07b rules. This is consistent with the documented "not an immutable deployment attestation" and with local-only scope.

3. **Low: the 07b branch accepts fields 07b never had.** It accepts `participating_case_bounds` and the newer certificate fields that 07b's schema lacked. These are unused for acceptance but could be rendered as evidence on a record carrying the 07b fingerprint. Consider requiring these fields to be empty under the 07b branch.

4. **Not independently verifiable here.** I can't check the three digest constants textually. Only `5ea15…` is corroborated, and only by self-consistency with a fixture generated now from 07b code. The 0db/3f9 digests have no fixtures produced by those commits; the tests use manufactured records.

5. **Test precision.** The four mutation cases use a bare `pytest.raises(ValueError)`, so an unrelated `ValidationError` would also pass. Add `match=` strings. There is no negative test that a 07b- or pre-minimum-tagged record violating its own original rules is refused. The risk is low because those are the same code paths.

6. **Documentation drift.** The `local_results.py` module docstring still says old bytes "are not retroactively subjected to successor acceptance rules". Unknown-source V2 records now are.

7. **Out of packet.** I can't verify the claim of a "visible historical qualifier in browser/PDF". `web/js/study-view.js` and `workbench.css` have uncommitted changes and are not part of 2cbbe3c.

**Scope:** this is a textual review of the supplied packet only. Nothing was executed.
