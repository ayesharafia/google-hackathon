# P00.1 software review

Date: 3 October 2026. Fixed point: user-approved plan/source baseline `d17f97a6d37d4458e08f005a20ecf5db870b3235`. Initial candidate: `2a1371a`. Follow-up candidate: `26e7f77`. These are read-only software reviews by separate review contexts. They are not a new Claude physics review, human engineering approval, or a release authorization.

Diff: `git diff d17f97a...26e7f77`. Spec: `plan.md` P00.1 and applicable Sections 2, 5, 9 and 15. Standards: plan development/architecture/provenance/security requirements, `tests/architecture/test_layering.py`, existing results/artifact conventions and the user-supplied design law. No browser assets changed.

## Standards

No standards findings in `d17f97a...2a1371a`.

The new verifier respects the documented layer boundary (`tests/architecture/test_layering.py`), keeps published bytes immutable (`core/artifacts.py`; plan §5), and preserves the separate numerical, evidence and review statuses (`result_contract.py`; plan §5). Its public interface explicitly identifies unchecked native/vendor scopes, rejects changed or escaped files, and supports relocated evidence without changing retained provenance.

The launcher fixes the local bind address and reviewed configuration, verifies evidence before starting, and keeps credentials out of printed arguments and reports, consistent with plan §9. Meaningful refusal, portability and launcher tests support plan §1's verification requirement.

UI assets are unchanged, so the design-law visual requirements do not introduce a new interface-review obligation for these changes. Pending presentation, validation and release approvals remain explicit in the documentation, consistent with plan §15.

**Follow-up at `26e7f77`: zero standards findings.** The startup guard matches the existing API's result-directory eligibility rule and refuses an ambiguous presentation root before launch. Its regression test verifies refusal without starting another process. Read-only verification remains compatible with multi-study roots, and the documentation distinguishes the earlier fresh-checkout receipt from the current tooling fingerprints. No published evidence, physics semantics, layering rules or UI assets changed.

## Spec

No spec findings for candidate `2a1371a` against baseline `d17f97a`.

- Missing or partial P00.1 requirements: none, excluding the parent's then-pending fresh-checkout exercise and final task checkbox.
- Unrequested scope: none. The read-only verifier, inventory-bound demo launcher, refusal tests and documentation directly support P00.1's requirement to "make the active demo configuration explicit" and acceptance that "tampering is refused."
- Deceptive or incorrect implementation: none found. The records clearly distinguish the historical full CFD campaign, new backend fixtures, source snapshot, original solver provenance and Claude's reviewed candidate.

The spec reviewer independently ran native/vendor verification: 130 source files, 33 package members, 31 supporting files, 105 native outputs and all native input/record bindings matched. They compared every frozen source fingerprint against the Git objects at `d17f97a`, checked retained test receipts and new tooling fingerprints, and confirmed the superseded `demo-final` manifest remains present with its original hash.

The retained envelope remains `unverified` with machine review `pending`; aircraft validation remains `not_established`. This satisfies "No aircraft validation is asserted" and Section 5's distinction between integrity and validation. The scoped Claude PASS is documentary and is not extended to the new verifier or future physics changes.

**Follow-up at `26e7f77`: zero spec findings.** The single-group guard matches the API's directory/name filtering and prevents the existing browser default from selecting an unrelated study. It runs before launch, including `--check-only`; ordinary verification remains usable with multiple study directories. This supports "presenter selects the reviewed package." The reviewer independently ran all 25 baseline tests and the real reviewed preset check-only command successfully. The records did not misrepresent the earlier fresh-checkout as testing the later guard.

## Completion evidence

The parent subsequently verified the final candidate in the independent checkout, including the guard, all frozen native/vendor/package bytes and 26 baseline/architecture tests. Only documentary completion records and the task checkbox changed afterward; verification code and the frozen inventory/preset remained unchanged.

Standards: 0 findings. Spec: 0 findings. P00.1 is complete. G0 and the remaining production program are pending P00.2 and subsequent gates; no merge or release tag was performed.
