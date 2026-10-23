# Case Trim Evidence delivery

23 October 2026, Asia/Kolkata. TRIM-001. Baseline main:
729b94e5245f75fa3e56aec40ca28124611d31bc. Owner approved “Proceed with Case Trim
Evidence”, including targeted tests/browser checks, full interface review and
publication to main. One primary agent; no independent scientific acceptance.

## Observable behavior

The retained-study viewer now has a native case/evidence-point inspector. It
keeps the shared mission-payload check separate from each individual case
candidate/bound. Exact candidate totals, per-rotor N/Nm/signed RPM/W/A, force and
moment residual components, recorded policies, constraints, command scope and
any torque-band interval are readable without decoding JSON. Exact selected and
full records remain available. Missing/duplicate/diagnostic/historical evidence
is explicit. [Usage and field mapping](../technical/case-trim-evidence.md).

The same frozen-case action reuses existing identity guards, preserves unsaved
drafts and restores inspector selection. The existing 3D viewer retains its
shared-payload context; the evidence-point choice affects only this sheet.
No equations, thresholds, API, dependencies, access, source bytes, result bytes
or historical fixtures changed. Numeric projection neither recomputes residuals
nor creates a new acceptance classification.

## Executed verification

| Check | Observed result | Retained receipt |
|---|---|---|
| Projection plus existing download/energy/comparison/readiness/binding units | 100 passed, including 19 new trim cases | [Node](../../.physicore/evidence/TRIM-001-test-20261023041457667173.json) |
| Existing study/report/summary/scenario regressions | 41 passed; existing Starlette/httpx warning | [Python](../../.physicore/evidence/TRIM-001-test-20261023041142422609.json) |
| New installed-Chrome inspector journey | 19 checks, no page JavaScript errors | [Inspector](../../.physicore/evidence/TRIM-001-test-20261023042016417909.json) |
| Existing mission-energy browser journey | 16 checks | [Energy](../../.physicore/evidence/TRIM-001-test-20261023041501796259.json) |
| Existing comparison browser journey | 15 checks | [Comparisons](../../.physicore/evidence/TRIM-001-test-20261023041508293896.json) |
| Existing Review Pack browser journey | 15 checks, including actual ZIP downloads | [Review Pack](../../.physicore/evidence/TRIM-001-test-20261023041501773054.json) |
| Changed JavaScript syntax | Passed | [Inspector](../../.physicore/evidence/TRIM-001-test-20261023042039054140.json), [workbench](../../.physicore/evidence/TRIM-001-test-20261023041548268684.json), [view](../../.physicore/evidence/TRIM-001-test-20261023041548355535.json) |

All browser journeys use an owned disposable loopback service/data root and
installed headless Chrome. Actual synthetic hover and conditioned/axial studies
are evaluated with existing code. Their displayed commands/totals/residuals/
policies are compared with retained API values; original study-export bytes stay
unchanged after inspection and unsaved edits. Existing Review Pack regressions
unpack and verify real downloads. This is software QA using labelled fixtures.

UI-only response fixtures exercise absent shared checks, partial/diagnostic
commands, malformed vectors, literal markup, torque-band interval rendering,
duplicates, absent cases and historical-schema warnings. They change browser
responses, not server evidence or model assertions. The historical unit test
reads the original retained V2 fixture without modifying it. A detached stale
button is deliberately re-enabled and clicked to exercise the context guard;
this is an injection test, not an ordinary user journey.

Pointer-driven disclosures and case actions work. Select-option interactions
exercise actual native change events and resulting values. Keyboard focus order,
Enter disclosures and focus return to the frozen viewer control pass. Pending
restoration disables both selectors and the navigation action. Viewport checks
cover 1440 px, 390 px and CSS body zoom=2, complete cell text containment, readable
single-line residual labels and horizontal access to final columns.

### Failures, corrections and limits

- [First browser receipt](../../.physicore/evidence/TRIM-001-test-20261023041155384865.json):
  selector accessible names included their option text. Fixed explicit accessible
  names in the UI. No data/model assertion changed.
- [Second receipt](../../.physicore/evidence/TRIM-001-test-20261023041218316308.json):
  expected ArrowDown/Enter to change a native select in headless macOS Chrome;
  it did not. Isolated probes confirmed this automation behavior. The harness now
  checks keyboard focus order/Enter disclosures and uses select-option interaction
  for value changes. Native popup option selection using keyboard remains
  unverified; no complete keyboard usability claim is made.
- Initial setup used system Python 3.9, whose datetime lacks UTC; the repo's
  Python 3.11 venv successfully starts/records the workflow. A timeout flag after
  the task ID was parsed as a command; corrected argument order before execution.
  An initial patch failed parsing before writing; corrected the patch.
- First screenshot pass split long exact decimals across lines. Numeric cells
  now stay whole and scroll horizontally. Subsequent original-size phone review
  caught a residual label column collapsing into character-wide wrapping after
  auto table sizing. Fixed its minimum width, shortened table captions and added
  single-line label assertions. Final images were opened and inspected again. The individual-case option was
  shortened so its native selected text also fits the enlarged layout.
- Missing constraint arrays now display unavailable distinctly from a retained
  empty array. Visible copy explains the evidence point without implementation
  field names; exact paths remain documented for developers.

Unexecuted: native browser zoom, native popup keyboard selection, screen-reader/
real-user usability, cross-browser/physical-device testing, provider/deployment/
load qualification and real-aircraft validation. CSS zoom=2 is not native zoom.
No production service/tunnel was restarted, no branch deleted and no data/model
or scientific acceptance threshold was changed.

## Full interface-law re-check

The entire supplied law was read initially and re-read from the owner's global
AGENTS.md before handover. Every heading is accounted for in the
[point-by-point ledger](case-trim-evidence-design-law-2026-10-23.md). This audit
covers the new inspector and its integration; it does not certify an unchanged
whole app or redesign the existing header, viewer, reports or typography.

The authored interaction is the choice between independently retained operating
points plus exact frozen-case navigation. Existing geometry, meaningful source
values, green/ink tones and display/body roles remain the workbench's identity.
There is no decorative motion, new font, icon pack, card stack or synthetic
illustration. Content is visible by default; numerical columns share table rows.
The final review fixed the real accessible-name and numerical/label-wrap issues
above. Table scroll is explicit and focusable; captions, copy and controls stay
within the surrounding gutters. Existing reduced-motion behavior is preserved.

Screenshots opened and reviewed: [desktop](assets/trim-evidence/desktop.png),
[desktop context](assets/trim-evidence/desktop-context.png),
[phone](assets/trim-evidence/phone.png), [phone context](assets/trim-evidence/phone-context.png),
[enlarged](assets/trim-evidence/enlarged.png),
[enlarged context](assets/trim-evidence/enlarged-context.png),
[individual selector at phone size](assets/trim-evidence/phone-individual-selector.png),
[individual selector enlarged](assets/trim-evidence/enlarged-individual-selector.png),
[diagnostic interval fixture](assets/trim-evidence/diagnostic-interval.png).
