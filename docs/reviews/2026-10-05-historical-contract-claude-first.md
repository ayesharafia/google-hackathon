# Claude historical contract review: correction required

Candidate: `031a4908bfd73e3a29d0c5ab21438093ffc12807`; packet SHA-256 `315733c0c032d3e94f449d469205978fb35dfd74ea7eb478b3bb1854271d4211`. Text-only review, no execution. The FAIL identified an overly broad historical policy. The correction dispatches known historical generations by exact source fingerprint and preserves original policies; unknown/later producers face current stronger checks. The original 07b9f19 validator was weaker than the f0e4c62 validator, so the reply's assertion that every earlier producer rejected those contradictions is not true for that first generation. New V3 never selects historical policies. Later acceptance requires a new review.

# Verdict: FAIL (medium; one contract defect, no physics or new-study regression found)

## Scope and limits

This is a textual review of the diff and full-file excerpts for `local_results.py`, `studies.py`, `reports.py`, the two test files and `mission-capacity.md` at 031a490. I ran nothing and read nothing outside the packet. Several items are not in the packet:

- the `retained-v2-sequence.json` fixture
- `capacity.py`
- the repository and artifact store
- the API routes and headers
- the web/browser code
- the V2 validator source from whichever commit produced the fixture

The I03 evidence verifier is out of scope.

I am treating the diff base as f0e4c62. The diff renames the old `LocalCapacityV2` body into `_CapacityRecord` plus the V3 `headline`, so the f0e4c62 V2 acceptance rules equal the current V3 `headline` validator.

## New-study acceptance: no regression found

- **V3 validator unchanged.** `LocalCapacityV3.headline` is textually the prior V2 validator. Only the class and `schema_version` literal changed.
- **Run path uses V3.** `run()` validates with V3 before retaining, and the artifact kind is `local_mission_capacity_v3`.
- **Schema bound in the spec.** `result_schema_version` in the spec changes the study hash, so V2 and V3 studies cannot collide on study identity.
- **Comparisons stay conservative.** `compare_records` already withholds the numeric delta across differing `schema_version`, so V2 vs V3 comparisons are not numerically compared.
- **No new optimistic text.** The PDF wording for V3 is unchanged ("Verified local payload lower bound"). V2 and V1 get a historical qualifier and the label "Reported historical payload bound".

## Defect H1 (medium): historical V2 validator is broader than earlier acceptance, not "exact"

`LocalCapacityV2.historical_consistency` (`src/physimesh/drone/local_results.py`) is a newly written validator. It is not the original one. The legacy fixture lacks `participating_case_bounds`, which justifies dropping only the participating-bound checks. But the new validator also drops checks that have nothing to do with that field.

It now accepts a feasible V2 headline when:

1. **Headline exceeds a required case's bound.** The headline is above a required case's own individual bound, because the `cases` loop (`headline exceeds a required feasible case bound`) is gone. A required case may even be `infeasible` or `unsupported` in `cases` while the headline is published.
2. **Limiting case does not attain the headline.** `limiting_case_id` names a participating case whose payload does not equal the headline. The attainment check is gone, yet the PDF prints it as "Reported limiting constraint".
3. **Aggregate limit does not bind.** `aggregate_limit='sequence_energy'` is accepted with nonzero remaining energy and/or a non-null `limiting_case_id`, which contradicts the doc's "without inventing a limiting case".

It also accepts an `infeasible` aggregate with no supported certificate. That is the coverage-refusal rule added in 0db6bb0 and present in the f0e4c62 V2.

**Why it matters:** retained bytes are hash-bound, so this mostly affects read-time defense against records that were never produced by a validator, such as injected or migrated records. But the docs and commit claim V2 reads "retain their original acceptance semantics". As written, V2 reads accept attribution and headline contradictions that every earlier V2 producer visible here rejected. Also, V2 bytes that were produced at f0e4c62, with participating bounds, are now re-read under weaker rules than they were written under.

**Fix:**
- Keep every f0e4c62 check except the participating-bound checks, applying those only when `participating_case_bounds` is absent. For no-sequence and non-binding cases, check attainment against `cases`.
- Alternatively, dispatch on the exact historical producer generation.
- Add negative V2 tests for items 1–3 and for the uncertified infeasible aggregate.

## Lower-severity observations

- **L1 (low): renderer hash covers one file.** `RENDERER_SOURCE_SHA256` hashes only `reports.py`. It does not cover `provenance.canonical_json` or other helpers that affect PDF bytes; ReportLab's version is recorded separately. The hash is computed at import, so an edit after import is not reflected. That matches the documented local-identity framing, but say so explicitly.
- **L2 (low, test gap): qualifier text not asserted.** The historical test asserts a 200 status and the JSON hash header. It does not assert that the historical qualifier or the "Reported historical" wording appears in the PDF. The browser qualifier claimed in the docs is not verifiable from this packet.
- **L3 (unverifiable here): rerun behavior.** If `retain_study` keys the "one winning association" by revision rather than by study hash, rerunning a revision that already holds a V2 result might return the V2 bytes, not a V3 study. Confirm in the repository code.
- **L4 (unverifiable here): fixture provenance.** I could not inspect the fixture's provenance or whether it is byte-identical to real historical output (I03 territory).

## Conclusion

The physics is unchanged and new-study (V3) acceptance shows no regression. The renderer identity is embedded in the PDF bytes and agrees with the retained metadata per the test. The "exact compatibility / preserved earlier acceptance" claim for V2 fails on its face because of H1. Once H1 is fixed with negative tests, I would expect PASS_BOUNDED_LOCAL within the limits above.
